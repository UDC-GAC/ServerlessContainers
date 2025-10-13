#!/usr/bin/python
from __future__ import print_function

from threading import Thread, Lock
import time
import traceback

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
import src.WattWizard.WattWizardUtils as wattwizard
import src.EnergyController.CacheUtils as cache_utils
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "EVENT_TIMEOUT": 20, "WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 0,
                         "DEBUG": True, "STRUCTURE_GUARDED": "container", "CONTROL_POLICY": "ppe-proportional",
                         "POWER_MODEL": "polyreg_General", "ACTIVE": True}


class EnergyController(Service):

    def __init__(self):
        super().__init__("energy_controller", ConfigValidator(min_delay=0), CONFIG_DEFAULT_VALUES, sleep_attr="polling_frequency")
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.wattwizard_handler = wattwizard.WattWizardUtils()
        self.host_cpu_info, self.host_cpu_info_lock = {}, Lock()
        self.polling_frequency, self.window_timelapse, self.window_delay, self.debug = None, None, None, None
        self.structure_guarded, self.active, self.control_policy, self.power_model = None, None, None, None
        self.event_timeout = None
        self.events_cache = cache_utils.EventsCache()
        self.pb_cache = cache_utils.PowerBudgetCache()
        self.alloc_cache = cache_utils.CPUAllocationCache()

    def get_resource_usage(self, resource, structure):
        name, host = structure["name"], structure["host"]
        return self.host_cpu_info[host][name]["usages"][utils.res_to_metric(resource)]

    def get_power_scaling(self, structure):
        name, host = structure["name"], structure["host"]
        return self.host_cpu_info[host][name]["scaling"]

    def _unpack_structure(self, structure):
        # Unpacks structure dictionary to values: (U_max, U_min, U_alloc, P_budget, U_usage, P_usage, P_scaling)
        res = structure["resources"]

        return  (res["cpu"]["max"], # U_max
                 res["cpu"]["min"], # U_min
                 res["cpu"]["current"], # U_alloc
                 res["energy"]["current"], # P_budget
                 self.get_resource_usage("cpu", structure), # U_usage
                 self.get_resource_usage("energy", structure), # P_usage
                 self.get_power_scaling(structure)) # P_scaling

    def _unpack_host(self, host):
        # Unpacks host dictionary to values: (U_alloc, U_user, U_system, P_usage, P_scaling)
        return (
            self.host_cpu_info[host]["total"]["allocation"], # U_alloc
            self.host_cpu_info[host]["total"]["usages"][utils.res_to_metric("user")], # U_user
            self.host_cpu_info[host]["total"]["usages"][utils.res_to_metric("kernel")], # U_system
            self.host_cpu_info[host]["total"]["usages"]["rapl"], # P_usage
            self.host_cpu_info[host]["total"]["scaling"] # P_scaling
        )

    @staticmethod
    def get_resource_margin(resource, structure, limits):
        boundary = limits["resources"][resource]["boundary"]
        ref_field = limits["resources"][resource]["boundary_type"].split("_")[-1]  # e.g., percentage_of_max -> max
        ref_value = structure["resources"][resource][ref_field]

        return int(ref_value * boundary / 100)

    @staticmethod
    def run_in_threads(f_name, structures, target, extra_args):
        threads = []
        for structure in structures:
            t = Thread(name="{0}_{1}".format(f_name, structure['name']), target=target, args=(structure, *extra_args))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

    def power_is_near_pb(self, structure, value):
        P_budget = structure["resources"]["energy"]["current"]
        is_near = (P_budget * 0.95) < value < (P_budget * 1.05) # P_budget < value < (P_budget + margin)
        if is_near:
            utils.log_warning(f"@{structure['name']} Power consumption is near power budget: {P_budget * 0.95} < {value} < {P_budget * 1.05}", self.debug)

        return is_near

    def error_is_below_potential_pb(self, structure, value):
        P_budget = structure["resources"]["energy"]["current"]
        P_max = structure["resources"]["energy"]["max"]
        error_is_below_potential_pb = (value > P_budget) and (value < P_max) # P_budget < value < (P_budget + margin)
        if error_is_below_potential_pb:
            utils.log_warning(f"@{structure['name']} Power consumption exceeds current limit but is below potential power budget: {value} < {P_max}", self.debug)

        return error_is_below_potential_pb

    def cpu_is_below_boundary(self, structure, limits, value):
        margin = self.get_resource_margin("cpu", structure, limits)
        U_alloc = structure["resources"]["cpu"]["current"]
        is_below = value < (U_alloc - margin)
        if is_below:
            utils.log_warning(f"@{structure['name']} CPU usage is below boundary: {value} < {U_alloc - margin} ({U_alloc} - {margin})", self.debug)

        return is_below

    def cpu_usage_is_above_allocation(self, structure, value):
        U_alloc = structure["resources"]["cpu"]["current"]
        is_above = value > U_alloc * 1.05 # A 5% error can be assumed
        if is_above:
            utils.log_warning(f"@{structure['name']} CPU usage is above current allocation: {value} > {U_alloc}", self.debug)

        return is_above

    def print_scaling_info(self, name, P_usage, P_budget, U_alloc, U_alloc_new):
        utils.log_info(f"@{name} POWER {P_usage} -> {P_budget} | CPU {U_alloc} -> {U_alloc_new}", self.debug)

    def get_amount_from_power_model(self, structure, ignore_system=False):
        host, name = structure["host"], structure["name"]

        # Get structure information
        U_max, U_min, U_alloc, P_budget, U_usage, P_usage, P_scaling = self._unpack_structure(structure)

        # Update pb value to indicate that the model has already been used with this structure and power budget
        self.pb_cache.add(structure["_id"], P_budget)

        # Get host information
        U_alloc_host, U_user_host, U_system_host, P_usage_host, P_scaling_host = self._unpack_host(host)

        if ignore_system:
            U_system_host = 0.0

        # Compute desired host power budget based on current scalings
        P_budget_host = P_usage_host + P_scaling_host

        # Get model estimation
        U_scaling_cap = 0
        try:
            # Use power model to get host CPU scaling required to comply with the new power budget
            result = self.wattwizard_handler.get_usage_meeting_budget("host", self.power_model, P_budget_host, user_load=U_user_host, system_load=U_system_host)
            U_scaling_host = result["value"] - U_alloc_host

            # Compute proportional CPU scaling for structure
            U_scaling = U_scaling_host * (P_scaling / P_scaling_host)
            U_scaling_cap = max(min(U_scaling, U_max - U_alloc), - (U_alloc - U_min))

            # Print scaling info
            self.print_scaling_info(host, P_usage_host, P_budget_host, U_alloc_host, result['value'])
            self.print_scaling_info(name, P_usage, P_budget, U_alloc, U_alloc + U_scaling_cap)

            # If we want to scale up power, avoid scaling down CPU and vice versa
            if P_scaling * U_scaling_cap < 0:
                utils.log_warning(f"@{name} MODEL CPU scaling ({U_scaling_cap}) is not coherent with power "
                                  f"scaling ({P_scaling}). Setting amount to 0.", self.debug)
                U_scaling_cap = 0

        except Exception as e:
            utils.log_error(f"@{name} Error trying to get estimated CPU from power models: {e}", self.debug)

        return int(U_scaling_cap)

    def get_amount_from_ppe(self, structure):
        host, name = structure["host"], structure["name"]

        # Unpack structure info
        U_max, U_min, U_alloc, P_budget, U_usage, P_usage, P_scaling = self._unpack_structure(structure)

        error = P_budget - P_usage
        U_alloc_new = U_alloc * (1 + (error/P_budget))
        U_alloc_new_cap = max(min(U_alloc_new, U_max), U_min)
        U_scaling = U_alloc_new_cap - U_alloc
        self.print_scaling_info(name, P_usage, P_budget, U_alloc, U_alloc_new_cap)

        return int(U_scaling)

    def structure_power_cap(self, structure, capping_method):
        try:
            # Check the necessary info for this structure is available
            if not self.host_cpu_info.get(structure["host"], {}).get(structure["name"], {}):
                return

            # If the structure doesn't need a power scaling it is skipped
            if self.get_power_scaling(structure) == 0:
                return

            amount = 0
            if capping_method == "modelling":
                amount = self.get_amount_from_power_model(structure)
            if capping_method == "ppe":
                amount = self.get_amount_from_ppe(structure)

            if amount != 0:
                request = utils.generate_request(structure, amount, "energy")
                self.couchdb_handler.add_request(request)
                self.alloc_cache.add(structure["_id"], structure["resources"]["cpu"]["current"],
                                     structure["resources"]["cpu"]["current"] + amount)

        except Exception as e:
            utils.log_error(f"{structure['name']} Error capping structure: {e}", self.debug)

    def print_events_info(self, structure, direction, dir_events, op_events):
        up_events = dir_events if direction == "up" else op_events
        down_events = dir_events if direction == "down" else op_events
        utils.log_info(f"@{structure['name']} EVENTS: DOWN {down_events} | UP {up_events}", self.debug)

    def compute_power_scaling(self, structure, limits, usages):
        structure_id = structure["_id"]
        U_usage, P_usage = usages[utils.res_to_metric("cpu")], usages[utils.res_to_metric("energy")]
        P_budget = structure["resources"]["energy"]["current"]
        P_scaling = P_budget - P_usage
        direction, opposite = ("up", "down") if P_scaling > 0 else ("down", "up")

        # If power is already near the power budget the structure doesn't need to scale power
        if self.power_is_near_pb(structure, P_usage):
            return 0

        # If power exceeds "current" and "current" < "max", Guardian should scale "current" instead of the Controller scaling down CPU
        if self.error_is_below_potential_pb(structure, P_usage):
            return 0

        # If CPU usage exceeds current allocation, power consumption won't show the effect of recent allocation changes
        if self.cpu_usage_is_above_allocation(structure, U_usage):
            return 0

        # If structure needs a power scale-up but CPU is below boundary (no CPU bottleneck), skip power scale
        if P_scaling > 0 and self.cpu_is_below_boundary(structure, limits, U_usage):
            return 0

        # Add event and get accumulated events
        self.events_cache.add_event(structure_id, direction)
        dir_events = self.events_cache.get_events(structure_id, direction)
        op_events = self.events_cache.get_events(structure_id, opposite)
        self.print_events_info(structure, direction, dir_events, op_events)

        # Higher error requires fewer consecutive events to trigger scaling
        abs_ppe = abs(P_scaling / P_budget)
        for ppe_threshold, event_threshold in [(0.25, 1), (0.15, 2), (0.05, 4)]:
            if abs_ppe >= ppe_threshold and dir_events >= event_threshold and op_events == 0:
                self.events_cache.clear_events(structure_id)
                return P_scaling

        return 0

    def usages_are_valid(self, structure, usages, timelapse):
        valid = True
        if not usages:
            valid = False
            utils.log_warning(f"@{structure['name']} No usage data could be retrieved with a timelapse of {timelapse} seconds", self.debug)
        else:
            for metric, value in usages.items():
                if value <= 0:
                    valid = False
                    utils.log_warning(f"@{structure['name']} Usage data for metric {metric} is below 0 ({value})", self.debug)
        return valid

    def collect_usages(self, structure):
        for timelapse in [self.window_timelapse, self.window_timelapse + 5, self.window_timelapse + 10]:
            # Remote database operation
            usages = utils.get_structure_usages(["cpu", "energy"], structure, timelapse, self.window_delay, self.opentsdb_handler, self.debug)
            if self.usages_are_valid(structure, usages, timelapse):
                # If DB request was successful with a higher timelapse, it means controller and power meter are desynchronized
                if timelapse > self.window_timelapse:
                    utils.log_warning(f"@{structure['name']} Got usages with a higher window timelapse {self.window_timelapse} -> {timelapse}", self.debug)
                return usages
        return None

    def collect_structure_info(self, structure):
        host, name = structure["host"], structure["name"]
        structure_scaling = 0
        try:
            usages = self.collect_usages(structure)
            if not usages:
                return

            # Make sure CPU allocation is up to date since last changes (i.e., CPU scalings from previous iterations)
            read_alloc = structure["resources"]["cpu"]["current"]
            old_alloc = self.alloc_cache.get_old(structure["_id"], read_alloc)
            new_alloc = self.alloc_cache.get_new(structure["_id"], read_alloc)
            if read_alloc != new_alloc:
                if read_alloc == old_alloc:
                    utils.log_warning(f"@{name} CPU allocation is not up to date, a cached value will be used (read = {read_alloc} | cached = {new_alloc})", self.debug)
                    structure["resources"]["cpu"]["current"] = new_alloc
                else:
                    utils.log_warning(f"@{name} Scaler had some trouble scaling from {old_alloc} to {new_alloc} (read = {read_alloc})", self.debug)

            # Retrieve structure resource limits
            limits = self.couchdb_handler.get_limits(structure)

            # Save the power scaling needed by the structure, only if it is guarded and also has energy guarded
            if structure.get("guard", False) and structure.get("resources", {}).get("energy", {}).get("guard", False):
                structure_scaling = self.compute_power_scaling(structure, limits, usages)

            # Register structure values and sum total host values
            with self.host_cpu_info_lock:
                host_dict = self.host_cpu_info.setdefault(host, {"total": {"usages": {}, "scaling": 0.0, "allocation": 0}})
                host_dict[name] = {"scaling": structure_scaling, "usages": usages}
                host_dict["total"]["scaling"] += structure_scaling
                host_dict["total"]["allocation"] += structure["resources"]["cpu"]["current"]
                for metric, delta in usages.items():
                    host_dict["total"]["usages"][metric] = host_dict["total"]["usages"].get(metric, 0.0) + delta

            # Get host power consumption from RAPL
            if not self.host_cpu_info[host]["total"]["usages"].get("rapl", None):
                rapl_report = utils.get_structure_usages(["energy"], {"name": f"{host}-rapl", "subtype": "container"}, self.window_timelapse, self.window_delay, self.opentsdb_handler, self.debug)
                with self.host_cpu_info_lock:
                    self.host_cpu_info[host]["total"]["usages"]["rapl"] = rapl_report[utils.res_to_metric("energy")]

        except Exception as e:
            utils.log_error(f"@{name} Error collecting info: {e}", self.debug)

    def collect_info(self, guarded_structures, supported_structures):
        self.host_cpu_info.clear()
        if self.control_policy == "model-boosted":
            modelling_candidates = [s for s in guarded_structures if self.pb_cache.is_new(s["_id"], s["resources"]["energy"]["current"])]
            ppe_candidates = [s for s in guarded_structures if s not in modelling_candidates]

            # Host global values including all containers running on each host are needed if modelling will be used
            if modelling_candidates:
                self.run_in_threads("collect_info", supported_structures, self.collect_structure_info, [])
            else:
                self.run_in_threads("collect_info", guarded_structures, self.collect_structure_info, [])

            capping_groups = zip(["modelling", "ppe"], [modelling_candidates, ppe_candidates])
        else:
            self.run_in_threads("collect_info", guarded_structures, self.collect_structure_info, [])
            capping_groups = zip(["ppe"], [guarded_structures])

        return capping_groups

    def control_structures(self, guarded_structures, supported_structures):
        # Remove old events
        self.events_cache.remove_old_events(self.event_timeout)

        # Check which power-capping method should be used for each structure and collect necessary info
        capping_groups = self.collect_info(guarded_structures, supported_structures)

        for capping_method, structures in capping_groups:
            self.run_in_threads("power_cap", structures, self.structure_power_cap, [capping_method])

    def validate(self, structures, validation_steps):
        valid_structures = structures
        if valid_structures:
            for cond, msg in validation_steps:
                valid_structures = [s for s in valid_structures if cond(s)]
                if not valid_structures:
                    utils.log_warning(msg, self.debug)
                    break
        return valid_structures

    def get_guarded_structures(self, structures):
        validation_steps = [
            # Get structures set to guard
            (lambda s: s.get("guard", False), "No structure set to guard, skipping"),
            # Get structures having 'energy' set to guard
            (lambda s: s.get("resources", {}).get("energy", {}).get("guard", False), "No structure has 'energy' set to guard, skipping"),
        ]
        return self.validate(structures, validation_steps)

    def get_supported_structures(self, structures):
        validation_steps = [
            # Check structures have supported subtype
            (lambda s: utils.structure_subtype_is_supported(s["subtype"]), "All the structures have an unknown structure subtype"),
        ]
        return self.validate(structures, validation_steps)

    def invalid_conf(self, service_config):
        if self.control_policy not in ["ppe-proportional", "model-boosted"]:
            return True, "Control policy '{0}' is invalid".format(self.control_policy)

        return self.config_validator.invalid_conf(service_config)

    def work(self, ):
        # Remote database operation
        structures = utils.get_structures(self.couchdb_handler, self.debug, subtype=self.structure_guarded)
        # Get all the structures supported by this controller (i.e. containers)
        supported_structures = self.get_supported_structures(structures)
        # Get the structures that have energy set to guarded
        thread = None
        guarded_structures = self.get_guarded_structures(supported_structures)
        if guarded_structures:
            utils.log_info("{0} Structures to process, launching threads".format(len(guarded_structures)), self.debug)
            thread = Thread(name="control_structures", target=self.control_structures, args=(guarded_structures, supported_structures,))
            thread.start()
        else:
            utils.log_info("No valid structures to process", self.debug)
        return thread

    def compute_sleep_time(self):
        return self.polling_frequency - (time.time() % self.polling_frequency)

    def control(self, ):
        self.run_loop()


def main():
    try:
        energy_controller = EnergyController()
        energy_controller.control()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
