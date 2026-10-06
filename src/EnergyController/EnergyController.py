#!/usr/bin/python
from __future__ import print_function

from threading import Thread, Lock
import time
import math
import requests
import traceback

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
import src.WattWizard.WattWizardUtils as wattwizard
import src.EnergyController.CacheUtils as cache_utils
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "EVENT_TIMEOUT": 20, "WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 0,
                         "ALLOWED_ERROR": 0.05, "STRUCTURE_GUARDED": "container", "CONTROL_POLICY": "ppe-proportional",
                         "POWER_MODEL": "polyreg_General", "EVENTS_SYSTEM": "dynamic", "REACTION_TIME": 20,
                         "EV_RATIO": 5, "IDLE_POWER": 40, "DEBUG": True, "ACTIVE": True}

# Fallback capping method when a power model is not used
POLICY_CAPPING_METHOD = {"ev": "ev", "tdp": "tdp", "ppe-proportional": "ppe", "model-boosted": "ppe", "model-only": None}
# Control policies that apply the power model to each new budget
MODEL_POLICIES = {"model-boosted", "model-only"}

class EnergyController(Service):

    def __init__(self):
        super().__init__("energy_controller", ConfigValidator(min_delay=0), CONFIG_DEFAULT_VALUES, sleep_attr="polling_frequency")
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.wattwizard_handler = wattwizard.WattWizardUtils()
        self.P_idle = self.wattwizard_handler.get_idle_consumption("host", "polyreg_General")
        self.host_cpu_info, self.host_cpu_info_lock = {}, Lock()
        self.polling_frequency, self.event_timeout, self.window_timelapse, self.window_delay = None, None, None, None
        self.allowed_error, self.structure_guarded, self.control_policy, self.power_model = None, None, None, None
        self.events_system, self.reaction_time, self.debug, self.active = None, None, None, None
        self.ev_ratio, self.idle_power = None, None
        self.host_max_values = {}
        self.events_cache = cache_utils.EventsCache()
        self.pb_cache = cache_utils.ResourceCache()
        self.alloc_cache = cache_utils.ResourceCache()
        self.budget_cache = cache_utils.ResourceCache()

    def get_resource_usage(self, resource, structure):
        name, host = structure["name"], structure["host"]
        return self.host_cpu_info[host][name]["usages"][utils.res_to_metric(resource)]

    def get_power_scaling(self, structure):
        name, host = structure["name"], structure["host"]
        return self.host_cpu_info[host][name]["scaling"]

    def _unpack_structure(self, structure):
        # Unpacks structure dictionary to values: (U_max, U_min, U_alloc, P_budget, U_usage, P_usage, P_scaling)
        res = structure["resources"]

        return (res["cpu"]["max"],  # U_max
                res["cpu"]["min"],  # U_min
                res["cpu"]["current"],  # U_alloc
                res["energy"]["current"],  # P_budget
                self.get_resource_usage("cpu", structure),  # U_usage
                self.get_resource_usage("energy", structure),  # P_usage
                self.get_power_scaling(structure))  # P_scaling

    def _unpack_host(self, host):
        # Unpacks host dictionary to values: (U_alloc, U_user, U_system, P_usage, P_scaling)
        return (
            self.host_cpu_info[host]["total"]["allocation"], # U_alloc
            self.host_cpu_info[host]["total"]["usages"][utils.res_to_metric("user")], # U_user
            self.host_cpu_info[host]["total"]["usages"][utils.res_to_metric("kernel")], # U_system
            self.host_cpu_info[host]["total"]["usages"]["global"], # P_usage
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
        upper_limit = P_budget * (1 + self.allowed_error / 2)
        lower_limit = P_budget * (1 - self.allowed_error / 2)
        is_near = lower_limit < value < upper_limit
        if is_near:
            utils.log_warning(f"@{structure['name']} Power consumption is near power budget: {lower_limit} < {value} < {upper_limit}", self.debug)

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

        # Host model (with the prediction method of POWER_MODEL): the General model, or the Single_Core model while the
        # host uses less than one CPU
        method = self.power_model.split("_")[0]
        power_model = f"{method}_Single_Core" if U_user_host + U_system_host < 100 else f"{method}_General"

        # TODO: Distribute proportionally across scale downs and scale ups:
        #   1. Compute CPU scaling for total scale-up or scale-down
        #   2. Distribute scaling action between the containers scaling in that direction, proportionally to their power scaling
        #   3. When scaling up, assume the scale downs were already performed
        #       The P_budget_host will be P_usage_host - P_scale_downs + P_scale_ups
        #       The U_scaling_host will be result["value"] - (U_user_host - U_scale_downs)
        #       Maybe compute the CPU scalings just once outside the loop, instead of repeating the same for every container
        #   In the past we saw this approach has a problem, sum of scalings does not correspond with net scale, but I think this
        #   happened because I didn't consider the scale downs were already performed when computing the scale ups, or vice versa.

        # Get model estimation
        U_scaling_cap = 0
        try:
            # Use power model to get host CPU scaling required to comply with the new power budget
            result = self.wattwizard_handler.get_usage_meeting_budget("host", power_model, P_budget_host, user_load=U_user_host, system_load=U_system_host)
            U_scaling_host = result["value"] - U_user_host

            # Compute proportional CPU scaling for structure
            U_scaling = U_scaling_host * (P_scaling / P_scaling_host)
            U_scaling_cap = max(min(U_scaling, U_max - U_alloc), - (U_alloc - U_min))

            # Print scaling info
            self.print_scaling_info(host, P_usage_host, P_budget_host, U_user_host, result['value'])
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

        error = P_budget - P_usage  # This would be + P_idle in both sides of the subtraction, so it can be omitted
        U_alloc_new = U_alloc * (1 + (error / (P_budget + self.P_idle)))
        U_alloc_new_cap = max(min(U_alloc_new, U_max), U_min)
        U_scaling = U_alloc_new_cap - U_alloc
        self.print_scaling_info(name, P_usage, P_budget, U_alloc, U_alloc_new_cap)

        return int(U_scaling)

    def get_host_max_values(self, host):
        # Host maximum CPU shares and power (the host energy 'max' is the TDP of its CPUs)
        if host not in self.host_max_values:
            host_structure = utils.get_structures(self.couchdb_handler, self.debug, "host", structure_name=host)
            self.host_max_values[host] = (host_structure["resources"]["cpu"]["max"], host_structure["resources"]["energy"]["max"])
        return self.host_max_values[host]

    def get_tdp_ratio(self, structure):
        # k = (U_max - U_idle) / (P_tdp - P_idle), with U_idle = 0 and U_max being the host maximum CPU shares
        U_max_host, P_tdp_host = self.get_host_max_values(structure["host"])
        if P_tdp_host <= self.idle_power:
            raise ValueError("Host TDP ({0} W) must be higher than idle power ({1} W)".format(P_tdp_host, self.idle_power))
        return U_max_host / (P_tdp_host - self.idle_power)

    def get_amount_from_ratio(self, structure, ratio):
        name = structure["name"]

        # Unpack structure info
        U_max, U_min, U_alloc, P_budget, U_usage, P_usage, P_scaling = self._unpack_structure(structure)

        # U_alloc = U_alloc + k * (P_budget - P_usage)
        U_scaling = ratio * P_scaling
        U_scaling_cap = max(min(U_scaling, U_max - U_alloc), - (U_alloc - U_min))
        utils.log_info(f"@{name} CPU-power ratio k = {ratio:.2f} shares/W", self.debug)
        self.print_scaling_info(name, P_usage, P_budget, U_alloc, U_alloc + U_scaling_cap)

        return int(U_scaling_cap)

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
            if capping_method == "ev":
                amount = self.get_amount_from_ratio(structure, self.ev_ratio)
            if capping_method == "tdp":
                amount = self.get_amount_from_ratio(structure, self.get_tdp_ratio(structure))

            if amount != 0:
                request = utils.generate_request(structure, amount, "cpu")
                request["power_budget"] = structure["resources"]["energy"]["current"]
                self.couchdb_handler.add_request(request)
                self.alloc_cache.add(structure["_id"], structure["resources"]["cpu"]["current"] + amount)

        except Exception as e:
            utils.log_error(f"{structure['name']} Error capping structure: {e}", self.debug)

    def print_events_info(self, structure, direction, dir_events, op_events, required_events):
        up_events = dir_events if direction == "up" else op_events
        down_events = dir_events if direction == "down" else op_events
        utils.log_info(f"@{structure['name']} EVENTS: DOWN {down_events} | UP {up_events} | REQUIRED {required_events} ({direction})", self.debug)

    def reset_events_if_budget_changed(self, structure):
        # Events accumulated with a previous power budget do not apply to the new one. Only changes of 'max' (the
        # budget set by users or applications) reset them: 'current' also changes when the ReBalancer moves energy
        structure_id, P_max = structure["_id"], structure["resources"]["energy"]["max"]
        previous = self.budget_cache.get(structure_id)
        self.budget_cache.add(structure_id, P_max)
        if previous is not None and previous != P_max:
            up, down = self.events_cache.get_events(structure_id, "up"), self.events_cache.get_events(structure_id, "down")
            self.events_cache.clear_events(structure_id)
            if up or down:
                utils.log_info(f"@{structure['name']} EVENTS reset: power budget {previous} -> {P_max} W "
                               f"(discarded DOWN {down} | UP {up})", self.debug)

    def compute_power_scaling(self, structure, limits, usages):
        structure_id = structure["_id"]
        self.reset_events_if_budget_changed(structure)
        U_usage, P_usage = usages[utils.res_to_metric("cpu")], usages[utils.res_to_metric("energy")]
        P_budget = structure["resources"]["energy"]["current"]
        if P_budget == 0:
            utils.log_warning(f"@{structure['name']} Ignored because power budget is zero", self.debug)
            return 0

        P_scaling = P_budget - P_usage
        abs_ppe = abs(P_scaling / P_budget)
        direction, opposite = ("up", "down") if P_scaling > 0 else ("down", "up")

        if self.pb_cache.is_new(structure_id, P_budget) and self.control_policy in MODEL_POLICIES:
            utils.log_warning(f"Model is activated and budget is new (high reliability): {structure['name']} will be scaled regardless of the generated events", self.debug)
            return P_scaling

        # If power is already near the power budget the structure doesn't need to scale power
        if self.power_is_near_pb(structure, P_usage):
            return 0

        # If power exceeds "current" and "current" < "max", energy "current" must be scaled instead of the controller scaling down CPU
        if self.error_is_below_potential_pb(structure, P_usage):
            return 0

        # If CPU usage exceeds current allocation, power consumption won't show the effect of recent allocation changes
        if P_scaling < 0 and self.cpu_usage_is_above_allocation(structure, U_usage):
            # However, if power error is too high avoid blocking chained scale-downs
            if abs_ppe >= self.allowed_error:
                utils.log_warning(f"@{structure['name']} Power error is too high ({abs_ppe:.2f}), adding event anyway",self.debug)
            else:
                return 0

        # If structure needs a power scale-up but CPU is below boundary (no CPU bottleneck), skip power scale
        if P_scaling > 0 and self.cpu_is_below_boundary(structure, limits, U_usage):
            return 0

        # Add event and get accumulated events
        self.events_cache.add_event(structure_id, direction)

        # Static events threshold -> Threshold is the same regardless of the error
        # N_max keeps the reaction time: maximum time a power error must persist before scaling (e.g., 20 s -> 4 events at 5 s)
        N_max = max(1, int(self.reaction_time / self.polling_frequency + 1e-6))
        required_events = N_max
        if self.events_system == "dynamic":
            # Dynamic events threshold -> Higher error requires fewer consecutive events to trigger scaling
            N_min, alpha = 1, 1
            required_events = N_max * (self.allowed_error / abs_ppe) ** alpha
            required_events = max(min(math.ceil(required_events), N_max), N_min)

        self.events_cache.keep_last_n_events(structure_id, required_events)
        dir_events = self.events_cache.get_events(structure_id, direction)
        op_events = self.events_cache.get_events(structure_id, opposite)
        self.print_events_info(structure, direction, dir_events, op_events, required_events)
        if dir_events >= required_events:
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
                # The power of a container can be 0 W (e.g., the power meter gives no power to a container that uses
                # little CPU): the mean of the window is 0 W only if it has been 0 W during the whole window
                if value < 0 or (value == 0 and metric != utils.res_to_metric("energy")):
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
            cached_alloc = self.alloc_cache.get(structure["_id"], default=read_alloc)
            if read_alloc != cached_alloc:
                utils.log_warning(f"@{name} CPU allocation is not up to date (read = {read_alloc} | cached = {cached_alloc}), getting actual value from NodeRescaler ", self.debug)
                try:
                    container_resources = utils.get_container_physical_resources([structure], {"cpu"}, requests.Session(), self.debug)
                    actual_alloc = container_resources.get(structure["name"], {}).get("resources", {}).get("cpu", {}).get("cpu_allowance_limit")
                except Exception as e:
                    actual_alloc = None
                    utils.log_warning(f"@{name} Error getting CPU allocation from NodeRescaler: {str(e)}", self.debug)
                if actual_alloc is None:
                    utils.log_warning(f"@{name} CPU allocation couldn't be obtained from NodeRescaler, using cached value {cached_alloc}", self.debug)
                    structure["resources"]["cpu"]["current"] = cached_alloc
                else:
                    utils.log_warning(f"@{name} Actual CPU allocation is {actual_alloc}, setting this value", self.debug)
                    structure["resources"]["cpu"]["current"] = actual_alloc
                    self.alloc_cache.add(structure["_id"], actual_alloc)

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
                sensor_report = utils.get_structure_usages(["energy"], {"name": f"{host}-sensor", "subtype": "container"}, self.window_timelapse, self.window_delay, self.opentsdb_handler, self.debug)
                rapl_value = rapl_report[utils.res_to_metric("energy")]
                sensor_value = sensor_report[utils.res_to_metric("energy")]
                global_value = rapl_value - sensor_value
                utils.log_info(f"Global consumption = {rapl_value} (RAPL) - {sensor_value} (sensor) = {global_value} W", self.debug)
                with self.host_cpu_info_lock:
                    self.host_cpu_info[host]["total"]["usages"]["rapl"] = rapl_value
                    # Ignore sensor power to avoid side effects. Example:
                    # - Host consumes 70W apps + 20W sensor and P_scaling = 20W -> Compute CPU for 110W
                    # Apps scale up CPU, thus they absorb 20W from sensor, increasing their power a total of 40W instead of the initial 20W
                    self.host_cpu_info[host]["total"]["usages"]["global"] = global_value

        except Exception as e:
            utils.log_error(f"@{name} Error collecting info: {e}", self.debug)

    def collect_info(self, guarded_structures, supported_structures):
        self.host_cpu_info.clear()
        if self.control_policy in MODEL_POLICIES:
            modelling_candidates = [s for s in guarded_structures if self.pb_cache.is_new(s["_id"], s["resources"]["energy"]["current"])]
            # model-only does not correct the budgets already modelled (open loop)
            ppe_candidates = [s for s in guarded_structures if s not in modelling_candidates] if POLICY_CAPPING_METHOD[self.control_policy] else []

            # Host global values including all containers running on each host are needed if modelling will be used
            if modelling_candidates:
                self.run_in_threads("collect_info", supported_structures, self.collect_structure_info, [])
            else:
                self.run_in_threads("collect_info", guarded_structures, self.collect_structure_info, [])

            capping_groups = zip(["modelling", "ppe"], [modelling_candidates, ppe_candidates])
        else:
            self.run_in_threads("collect_info", guarded_structures, self.collect_structure_info, [])
            capping_groups = zip([POLICY_CAPPING_METHOD[self.control_policy]], [guarded_structures])

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
            (lambda s: utils.structure_subtype_is_supported(s["subtype"]), "Some structures subtype is not supported"),
        ]
        return self.validate(structures, validation_steps)

    def invalid_conf(self, service_config):
        if self.control_policy not in POLICY_CAPPING_METHOD:
            return True, "Control policy '{0}' is invalid".format(self.control_policy)

        if self.reaction_time is None or self.reaction_time <= 0:
            return True, "REACTION_TIME must be positive, got '{0}'".format(self.reaction_time)

        if self.event_timeout < self.reaction_time:
            return True, "EVENT_TIMEOUT ({0}) must be at least REACTION_TIME ({1})".format(self.event_timeout, self.reaction_time)

        if self.control_policy == "ev" and (self.ev_ratio is None or self.ev_ratio <= 0):
            return True, "EV ratio must be positive, got '{0}'".format(self.ev_ratio)

        if self.control_policy == "tdp" and (self.idle_power is None or self.idle_power < 0):
            return True, "Control policy is TDP, it needs a valid idle power value ({0})".format(self.idle_power)

        return self.config_validator.invalid_conf(service_config)

    def work(self, ):
        # Remote database operation
        structures = utils.get_structures(self.couchdb_handler, self.debug, self.structure_guarded)
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
