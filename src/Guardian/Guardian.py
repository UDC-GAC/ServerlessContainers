#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es)
#     - Roberto R. Expósito
#     - Juan Touriño
#
# This file is part of the ServerlessContainers framework, from
# now on referred to as ServerlessContainers.
#
# ServerlessContainers is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# ServerlessContainers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ServerlessContainers. If not, see <http://www.gnu.org/licenses/>.


from __future__ import print_function

from threading import Thread, Lock, Condition
from collections import Counter
import time
import traceback
import logging

from json_logic import jsonLogic
from termcolor import colored

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
import src.WattWizard.WattWizardUtils as wattwizard

MODELS_STRUCTURE = "host"

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "EVENT_TIMEOUT": 40, "DEBUG": True,
                         "STRUCTURE_GUARDED": "container", "GUARDABLE_RESOURCES": ["cpu"], "CPU_SHARES_PER_WATT": 5,
                         "ENERGY_MODEL_NAME": "polyreg_General", "ENERGY_MODEL_RELIABILITY": "low", "ACTIVE": True}
SERVICE_NAME = "guardian"

NOT_AVAILABLE_STRING = "n/a"


class Guardian:
    """
    Guardian class that implements the logic for this microservice. The Guardian takes care of matching the resource
    time series with a subset of rules to generate Events and then, matches the event against another subset of rules
    to generate scaling Requests.

    For more information you can visit: https://bdwatchdog.dec.udc.es/ServerlessContainers/documentation/web/architecture
    """

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.wattwizard_handler = wattwizard.WattWizardUtils()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.power_budget = {}
        self.window_timelapse, self.window_delay, self.event_timeout, self.debug = None, None, None, None
        self.structure_guarded, self.guardable_resources, self.cpu_shares_per_watt, self.active = None, None, None, None
        self.energy_model_name, self.energy_model_reliability, self.current_structures = None, None, None
        self.last_used_energy_model, self.current_scalings, self.model_is_hw_aware = None, None, None

    def __init_iteration_vars(self, structures):
        def _create_dict_value(count):
            lock = Lock()
            return {"lock": lock, "condition": Condition(lock), "up": [], "down": [], "expected_count": count, "register": []}
        if structures != self.current_structures:
            host_counter = Counter(s["host"] for s in structures)
            self.current_scalings = {host: _create_dict_value(count) for host, count in host_counter.items()}
            self.current_structures = list(structures)
        else:
            for scaling in self.current_scalings.values():
                scaling["register"].clear()
                scaling["up"].clear()
                scaling["down"].clear()

    def __do_condition_register(self, structure, value=None):
        current_host = structure["host"]
        name = structure["name"]

        # If structure was already registered, skip
        if name in self.current_scalings[current_host]["register"]:
            return False

        # Update the register with current structure
        self.current_scalings[current_host]["register"].append(name)

        # If some scaling was performed save its value
        if value:
            rescale_type = "up" if value > 0 else "down"
            self.current_scalings[current_host][rescale_type].append(value)

        return True

    def __do_condition_wakeup(self, structure):
        current_host = structure["host"]
        if len(self.current_scalings[current_host]["register"]) == self.current_scalings[current_host]["expected_count"]:
            self.current_scalings[current_host]["condition"].notify_all()
            return True
        return False

    def __do_condition_wait(self, structure):
        current_host = structure["host"]
        self.current_scalings[current_host]["condition"].wait()

    @staticmethod
    def check_unset_values(value, label, resource):
        """Check if a value has the N/A value and, if that is the case, raise an informative exception

        Args:
            value (integer): The value to be inspected
            label (string): Resource label name (e.g., upper limit), used for the exception string creation
            resource (string): Resource name (e.g., cpu), used for the exception string creation

        Returns:
            None

        Raises:
            Exception if value is N/A
        """
        if value == NOT_AVAILABLE_STRING:
            raise ValueError(
                "value for '{0}' in resource '{1}' is not set or is not available.".format(label, resource))

    @staticmethod
    def check_invalid_boundary(value, resource="n/a"):
        """ Check that boundary has a proper value set with the policy 0 <= boundary <= 100, otherwise raise ValueError

        Args:
            value (integer): Boundary value
            resource (string): Resource name (e.g., cpu), used for the exception string creation

        Returns:
            None

        Raises:
            ValueError if value < 0 or value > 100
        """
        if value < 0:
            raise ValueError("in resources: {0} value for boundary percentage is below 0%: {1}%".format(
                resource, str(value)))
        if value > 100:
            raise ValueError("in resources: {0} value for boundary percentage is above 100%: {1}%".format(
                resource, str(value)))

    @staticmethod
    def check_invalid_values(value1, label1, value2, label2, resource="n/a"):
        """ Check that two values have properly values set with the policy value1 < value2, otherwise raise ValueError

        Args:
            value1 (integer): First value
            label1 (string): First resource label name (e.g., upper limit), used for the exception string creation
            value2 (integer): Second value
            label2 (string): Second resource label name (e.g., lower limit), used for the exception string creation
            resource (string): Resource name (e.g., cpu), used for the exception string creation

        Returns:
            None

        Raises:
            ValueError if value1 > value2
            RuntimeError if value1 > value2 and value1 is current and value2 is max, that is the current is higher than the max
        """
        if value1 > value2 and label1 == "current" and label2 == "max":
            raise ValueError(
                "somehow this structure has a resource limit applied higher than maximum for {0}".format(resource))
        if value1 > value2:
            raise ValueError("in resources: {0} value for '{1}': {2} is greater than value for '{3}': {4}".format(
                resource, label1, str(value1), label2, str(value2)))

    @staticmethod
    def try_get_value(d, key):
        """Get the value stored in the dictionary or return a N/A string value if:

        * it is not in it
        * it is not an valid integer

        Args:
            d (dict): A dictionary storing values
            key (string): A string key

        Returns:
            (integer/string) int-mapped value stored in dict
        """
        try:
            return int(d[key])
        except (KeyError, ValueError):
            return NOT_AVAILABLE_STRING

    @staticmethod
    def get_margin_from_boundary(boundary, boundary_type, resource_values, resource_label):
        """
        Get the margin value applying boundary percentage to a baseline value. The baseline value can be the max value
        or the current value, depending on the boundary type.

        Args:
            boundary (integer): Boundary percentage
            boundary_type (string): Type of boundary, either percentage_of_max or percentage_of_current
            resource_values (dict): Dictionary containing the values (e.g., max, current) of the resource
            resource_label (string): Resource name (e.g., cpu), used for the exception string creation

        Returns:
            (integer) Margin value

        Raises:
            ValueError if the boundary type is not valid
        """
        if boundary_type == "percentage_of_max":
            return int(resource_values["max"] * boundary / 100)
        elif boundary_type == "percentage_of_current":
            return int(resource_values["current"] * boundary / 100)
        else:
            raise ValueError("Invalid boundary type for resource {0}: {1}".format(resource_label, boundary_type))

    @staticmethod
    def sort_events(structure_events, event_timeout):
        """Sorts the events according to a simple policy regarding the _[now - timeout <----> now]_ time window (TW):

        * The event is **inside** the TW -> valid event
        * The event is **outside** the TW -> invalid event

        The 'now' time reference is taken inside this function

        Args:
            structure_events (list): A list of the events triggered in the past for a specific structure
            event_timeout (integer): A timeout in seconds

        Returns:
            (tuple[list,list]) A tuple of lists of events, first the valid and then the invalid.

        """
        valid, invalid = list(), list()
        for event in structure_events:
            if event["timestamp"] < time.time() - event_timeout:
                invalid.append(event)
            else:
                valid.append(event)
        return valid, invalid

    @staticmethod
    def reduce_structure_events(structure_events):
        """Reduces a list of events that have been generated for a single Structure into one single event. Considering
        that each event is a dictionary with an integer value for either a 'down' or 'up' event, all of the dictionaries
        can be reduced to one that can have two values for either 'up' and 'down' events, considering that the Structure
        resource may have a high hysteresis.

        Args:
            structure_events (list): A list of events for a single Structure

        Returns:
            (dict) A dictionary with the added up events in a signle dictionary

        """
        events_reduced = {"action": {}}
        for event in structure_events:
            resource = event["resource"]
            if resource not in events_reduced["action"]:
                events_reduced["action"][resource] = {"events": {"scale": {"down": 0, "up": 0}}}
            for key in event["action"]["events"]["scale"].keys():
                value = event["action"]["events"]["scale"][key]
                events_reduced["action"][resource]["events"]["scale"][key] += value
        return events_reduced["action"]

    def get_resource_summary(self, resource_label, resources_dict, limits_dict, usages_dict, disable_color=False):
        """Produces a string to summarize the current state of a resource with all of its information and
        the following format: _[max, current, upper limit, usage, lower limit, min]_

        Args:
            resource_label (string): The resource name label, used to create the string and to access the dictionaries
            resources_dict (dict): a dictionary with the metrics (e.g., max, min) of the resources
            limits_dict (dict): a dictionary with the limits (e.g., lower, upper) of the resources
            usages_dict (dict): a dictionary with the usages of the resources
            disable_color (bool): disable coloured strings

        Returns:
            (string) A summary string that contains all of the appropriate values for all of the resources

        """
        metrics = resources_dict[resource_label]
        limits = limits_dict[resource_label]
        color_map = {"max": "red", "current": "magenta", "upper": "yellow", "usage": "cyan", "lower": "green", "min": "blue"}

        if not usages_dict or usages_dict[utils.res_to_metric(resource_label)] == self.NO_METRIC_DATA_DEFAULT_VALUE:
            usage_value_string = NOT_AVAILABLE_STRING
        else:
            usage_value_string = str("%.2f" % usages_dict[utils.res_to_metric(resource_label)])

        strings = list()
        for key, values in [("max", metrics), ("current", metrics), ("upper", limits), ("lower", limits), ("min", metrics)]:
            strings.append(colored(str(self.try_get_value(values, key)), color_map[key], no_color=disable_color))
        strings.insert(3, colored(usage_value_string, color_map["usage"], no_color=disable_color))  # Manually add the usage metric

        return ",".join(strings)

    @staticmethod
    def adjust_amount(amount, structure_resources, structure_limits):
        """Pre-check and, if needed, adjust the scaled amount with the policy:

        * If lower limit < min value -> Amount to reduce too large, adjust it so that the lower limit is set to the minimum
        * If new applied value > max value -> Amount to increase too large, adjust it so that the current value is set to the maximum

        Args:
            amount (integer): A number representing the amount to reduce or increase from the current value
            structure_resources (dict): Dictionary with the structure resource control values (min,current,max)
            structure_limits (dict): Dictionary with the structure resource limit values (lower,upper)

        Returns:
            (integer) The amount adjusted (trimmed) in case it would exceed any limit
        """
        expected_value = structure_resources["current"] + amount
        lower_limit = structure_limits["lower"] + amount
        max_limit = structure_resources["max"]
        min_limit = structure_resources["min"]

        if lower_limit < min_limit:
            amount += min_limit - lower_limit
        elif expected_value > max_limit:
            amount -= expected_value - max_limit

        return amount

    @staticmethod
    def adjust_cpu_amount_to_manage_energy(amount, structure_resources):
        """Pre-check and, if needed, adjust the scaled amount with the policy:

        * If new applied value < min value -> Amount to reduce too large, adjust it so that the current value is set to the minimum
        * If new applied value > max value -> Amount to increase too large, adjust it so that the current value is set to the maximum

        Args:
            amount (integer): A number representing the amount to reduce or increase from the current value
            structure_resources (dict): Dictionary with the structure resource control values (min,current,max)

        Returns:
            (integer) The amount adjusted (trimmed) in case it would exceed any limit
        """
        expected_value = structure_resources["current"] + amount
        max_limit = structure_resources["max"]
        min_limit = structure_resources["min"]

        if expected_value < min_limit:
            amount += min_limit - expected_value
        elif expected_value > max_limit:
            amount -= expected_value - max_limit

        return amount

    @staticmethod
    def get_amount_from_fit_reduction(current_resource_limit, resource_margin, current_resource_usage):
        """Get an amount that will be reduced from the current resource limit using a policy of *fit to the usage*.
        With this policy it is aimed at setting a new current value that gets close to the usage but leaving a boundary
        to avoid causing a severe bottleneck. More specifically, using the boundary configured this policy tries to
        find a scale down amount that makes the usage value stay between the _now new_ lower and upper limits.

        Args:
            current_resource_limit (integer): The current applied limit for this resource
            resource_margin (integer): The margin used between limits
            current_resource_usage (integer): The usage value for this resource

        Returns:
            (int) The amount to be reduced using the fit to usage policy.

        """
        upper_to_lower_window = resource_margin
        current_to_upper_window = resource_margin

        # Set the limit so that the resource usage is placed in between the upper and lower limits
        # and keeping the boundary between the upper and the real resource limits
        desired_applied_resource_limit = \
            current_resource_usage + int(upper_to_lower_window / 2) + current_to_upper_window

        return -1 * (current_resource_limit - desired_applied_resource_limit)

    @staticmethod
    def aggregate_containers_resource_info(containers, resource):
        """Get the aggregated resource values of a list of container structures

        Args:
            containers (list): List of container structures

        Returns:
            (dict) Dictionary containing the aggregated values

        """
        agg_resource = {"max": 0, "min": 0, "current": 0}
        for structure in containers:
            if resource in structure["resources"]:
                for key in ["max", "min", "current"]:
                    if key in structure["resources"][resource]:
                        agg_resource[key] += structure["resources"][resource][key]

        return agg_resource

    def register_scaling(self, structure, value=None, wait=True):
        current_host = structure["host"]
        # Take the lock to update the register
        with self.current_scalings[current_host]["lock"]:
            # If structure was registered, check the wake up condition and wait in case it is not met
            if self.__do_condition_register(structure, value) and not self.__do_condition_wakeup(structure) and wait:
                self.__do_condition_wait(structure)

    def get_host_containers(self, host):
        """Get a list of container structures running on the specified host

        Args:
            host (string): Host name

        Returns:
            (list) List of container structures

        """
        return [c for c in self.current_structures if c["host"] == host and c["subtype"] == "container"]

    def get_aggregated_containers_usages(self, containers, resources):
        """Get the aggregated usages of a list of container structures

        Args:
            containers (list): List of container structures
            resources (list): List of resources to retrieve and aggregate

        Returns:
            (dict) Dictionary containing the aggregated resources

        """
        # For each container in list get and sum its usages
        total_usages = {}
        for c in containers:
            container_usages = utils.get_structure_usages(resources, c, self.window_timelapse,
                                                          self.window_delay, self.opentsdb_handler, self.debug)

            # Aggregate container data into a global dictionary
            for metric in container_usages:
                if metric not in total_usages:
                    total_usages[metric] = 0
                total_usages[metric] += container_usages[metric]

        return total_usages

    def get_core_usages(self, structure):
        """Get the usage of a host disaggregated by core. The usage of each core will be used to predict power
        with hardware aware models that need this information. The models also need the host cores mapping to know
        which cores are free in order to rescale up/down.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            structure (dict): The dictionary containing all of the structure resource information

        Returns:
            host_cores_mapping (dict): Dictionary containing the mapping between host cores and containers
            core_usages (dict): Dictionary containing the CPU cores as a key and their usage as values

        """
        tag = utils.get_tag(structure["subtype"])
        metrics_to_retieve = ["sys.cpu.user", "sys.cpu.kernel"]
        metrics_to_generate = {
            "user_load": ["sys.cpu.user"],
            "system_load": ["sys.cpu.kernel"]
        }

        core_usages = {}
        host_info = self.couchdb_handler.get_structure(structure["host"])
        try:
            host_cores_mapping = host_info["resources"]["cpu"]["core_usage_mapping"]
        except KeyError:
            raise KeyError("No available cores info for structure {0}. HW aware models can't predict power without this information".format(structure['name']), self.debug)

        for core in host_cores_mapping:
            # Remote database operation
            core_usage = self.opentsdb_handler.get_structure_timeseries({tag: structure["name"], "core": core},
                                                                        self.window_timelapse, self.window_delay,
                                                                        metrics_to_retieve, metrics_to_generate)
            core_usages[core] = core_usage

        return host_cores_mapping, core_usages

    def power_budget_is_new(self, structure):
        """Check if we have already applied a rule with this power budget. This is useful for a *modelling-based CPU
        scaling* policy. The first time a power budget is applied the needed CPU is estimated through power models.
        Then, the subsequent estimations will be done using a 'proportional' policy to adjust the model error.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            structure (dict): The dictionary containing all of the structure resource information

        Returns:
            (bool) Whether the power budget has already been used or not

        """
        power_budget = structure["resources"]["energy"]["max"]
        structure_id = structure['_id']

        # Initialise with a non-possible value
        if structure_id not in self.power_budget:
            self.power_budget[structure_id] = -1

        if self.power_budget[structure_id] != power_budget:
            return True

        return False

    @staticmethod
    def power_is_near_power_budget(structure, usages, limits):
        """Check whether the current energy usage of a structure is close to its power budget.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            structure (dict): The dictionary containing all of the structure resource information
            usages (dict): A dictionary with the usages of the resources
            limits (dict): Dictionary with the structure resource limit values

        Returns:
            (bool) If energy is close to PB or not

        """
        power_margin = limits["energy"]["boundary"] / 100
        power_budget = structure["resources"]["energy"]["max"]
        current_energy_usage = usages[utils.res_to_metric("energy")]

        # If power is within some reasonable limits we do nothing
        if power_budget < current_energy_usage < power_budget * (1 + power_margin):
            return True

        return False

    def get_amount_from_energy_modelling(self, structure, usages, rescale_type, ignore_system=False):
        """Get an amount that will be reduced from the current resource limit using *modelling-based CPU scaling*
        policy, that is, using a power model that relates resource usage with power usage.
        Using this model it is aimed at setting a new current CPU value that makes the energy consumed by a Structure
        get closer to a limit.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            structure (dict): Dictionary containing all the structure resource information
            usages (dict): Dictionary with the usages of the resources
            rescale_type (str): Direction of the scaling action ("up", "down", "both")
            ignore_system (bool): If True current system usage is considered zero to get the power model estimation

        Returns:
            (int) The amount to be reduced using the fit to usage policy.

        """
        # Update container power budget in order to know that the model has been already applied to this structure
        self.power_budget[structure['_id']] = structure["resources"]["energy"]["max"]

        # Get container information
        structure_name = structure['name']
        container_power_budget = structure["resources"]["energy"]["max"]
        container_cpu_limit = structure["resources"]["cpu"]["current"]
        container_power_usage = usages[utils.res_to_metric("energy")]
        container_power_diff = container_power_budget - container_power_usage

        # Check that the needed scaling is coherent with the rescale type
        if (container_power_diff > 0 and rescale_type == "down") or (container_power_diff < 0 and rescale_type == "up"):
            utils.log_warning("[{0}] Power scaling amount ({1:.2f}) is not coherent with the rescale type ({2}). Amount"
                              " will be 0".format(structure_name, container_power_diff, rescale_type), self.debug)
            return 0

        # Get host information
        current_host = structure["host"]
        host_containers = self.get_host_containers(current_host)
        host_cpu_info = self.aggregate_containers_resource_info(host_containers, "cpu")
        host_usages = self.get_aggregated_containers_usages(host_containers, ["cpu"])
        cpu_usage_limit = host_cpu_info["current"]

        # Get host power consumption (RAPL)
        rapl_structure = {"name": f"{current_host}-rapl", "subtype": "container"}
        rapl_report = utils.get_structure_usages(["energy"], rapl_structure, self.window_timelapse,
                                                 self.window_delay, self.opentsdb_handler, self.debug)
        cpu_power_usage = rapl_report[utils.res_to_metric("energy")]

        # Register scaling and wait for other containers on this host to be registered
        self.register_scaling(structure, value=container_power_diff)

        # Compute CPU desired power based on current scalings of the same rescale type
        host_scalings = sum(self.current_scalings[current_host][rescale_type])
        cpu_desired_power = cpu_power_usage + host_scalings

        # Get model estimation
        container_amount = 0
        try:
            # Set model prediction parameters
            kwargs = {
                "user_load": host_usages[utils.res_to_metric("user")],
                "system_load": host_usages[utils.res_to_metric("kernel")] if not ignore_system else 0.0
            }
            # If model is HW aware it also needs core usages information
            if self.wattwizard_handler.is_hw_aware(MODELS_STRUCTURE, self.energy_model_name):
                kwargs["host_cores_mapping"], kwargs["core_usages"] = self.get_core_usages(structure)

            result = self.wattwizard_handler.get_usage_meeting_budget(MODELS_STRUCTURE, self.energy_model_name,
                                                                      cpu_desired_power, **kwargs)

            cpu_amount = (result["value"] - cpu_usage_limit)

            utils.log_warning("[{0}] The whole CPU needs a power scale-{1} of {2:.2f}W from {3:.2f} to {4:.2f}W which "
                              "means a CPU scale-{5} from {6:.2f} shares to {7:.2f} shares"
                              .format(structure_name, rescale_type, host_scalings, cpu_power_usage,
                                      cpu_desired_power, rescale_type, cpu_usage_limit, result["value"]), self.debug)

            # Update amount proportionally to the container scaling
            container_scale_ratio = container_power_diff / host_scalings
            container_amount = cpu_amount * container_scale_ratio
            utils.log_warning("[{0}] Current container just need a scale-{1} of {2:.2f}W, so it will modify its CPU "
                              "limit from {3:.2f} to {4:.2f} shares ({5:.2f} * {6:.2f})"
                              .format(structure_name, rescale_type, container_power_diff, container_cpu_limit,
                                      container_cpu_limit + container_amount, cpu_amount, container_scale_ratio), self.debug)

            # If we want to rescale up, avoid rescaling down and vice versa
            if (rescale_type == "up" and container_amount < 0) or (rescale_type == "down" and container_amount > 0):
                container_amount = 0

        except Exception as e:
            utils.log_error("There was an error trying to get estimated CPU from power models {0}".format(str(e)),
                            self.debug)

        return int(container_amount)

    def check_power_modelling_rules(self, structure, rules, limits, usages, events):
        """Manage power modelling rules, when power models are used to apply power budgets (*modelling-based CPU
        scaling* policy), when the reliability of the model is high enough the current CPU value of all the structures
        is initially limited to the value indicated in the power model (even if no rule has been activated), then a
        *proportional energy-based CPU scaling* policy will be applied.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            structure (dict): The dictionary containing all of the structure resource information
            rules (dict): Dictionary with the current active rules
            limits (dict): Dictionary with the structure resource limit values (lower,upper)
            usages (dict): Dictionary with the structure resource usage values
            events (list): List of triggered events

        Returns:
            None

        """

        # Power models are only used when power budgeting (using "energy" as a first class resource)
        if "energy" not in structure["resources"] or "energy" not in limits:
            return

        # If Guardian don't trust energy models it is better to wait for events to rescale up/down
        if self.energy_model_reliability == "low":
            return

        # If structure has already applied a power budget there's nothing to do, i.e. its resources have already been
        # limited according to the power model
        if not self.power_budget_is_new(structure):
            return

        # We check if there exists at least one power modelling rule
        apply_initial_model_rescaling = False
        for rule in rules:
            is_power_modelling_rule = (rule["generates"] == "requests" and
                                       rule["rescale_type"] in ["up", "down"] and
                                       rule["rescale_policy"] == "modelling" and
                                       rule["resource"] == "energy")

            if is_power_modelling_rule:
                apply_initial_model_rescaling = True
                break

        # When reliability is set to medium, at least 1 event must have been generated to perform the rescaling
        if self.energy_model_reliability == "medium":
            apply_initial_model_rescaling = False
            for event in events:
                if "resource" in event and event["resource"] == "energy":
                    apply_initial_model_rescaling = True
                    break

        if not apply_initial_model_rescaling:
            return

        # At this point there's at least one power modelling rule and the structure has a power budget pending to apply
        # Then, the new current CPU value is estimated using the power model
        amount = self.get_amount_from_energy_modelling(structure, usages, "both", ignore_system=True)
        self.print_energy_rescale_info(structure, usages, limits, amount)

        # Ensure that amount is an integer, either by converting float -> int, or string -> int
        amount = int(amount)

        # Check CPU does not surpass any limit
        new_amount = self.adjust_cpu_amount_to_manage_energy(amount, structure["resources"]["cpu"])
        if new_amount != amount:
            utils.log_warning("Amount generated for structure {0} during initial rescaling "
                              "through power models has been trimmed from {1} to {2}"
                              .format(structure["name"], amount, new_amount), self.debug)

        # # If amount is 0 ignore this request else generate the request and append it
        if new_amount == 0:
            utils.log_warning("Initial rescaling through power models for structure {0} will be ignored "
                              "because amount is 0".format(structure["name"]), self.debug)
        else:
            request = utils.generate_request(structure, new_amount, "energy", priority=1)
            self.couchdb_handler.add_request(request)

    def get_amount_from_proportional_energy_rescaling(self, structure, usages, resource):
        """Get an amount that will be reduced from the current resource limit using a policy of *proportional
        energy-based CPU scaling*.
        With this policy it is aimed at setting a new current CPU value that makes the energy consumed by a Structure
        get closer to a limit.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            structure (dict): The dictionary containing all of the structure resource information
            usages (dict): a dictionary with the usages of the resources
            resource (string): The resource name, used for indexing purposes

        Returns:
            (int) The amount to be reduced using the fit to usage policy.

        """
        power_budget = structure["resources"][resource]["max"]
        current_cpu_limit = structure["resources"]["cpu"]["current"]
        current_energy_usage = usages[utils.res_to_metric("energy")]

        percentage_error = (power_budget - current_energy_usage) / power_budget
        amount = current_cpu_limit * percentage_error

        return int(amount)

    def get_amount_from_fixed_ratio(self, structure, resource):
        """Get an amount that will be reduced from the current resource limit using a policy of *fixed ratio
        energy-based CPU scaling*.
        With this policy it is aimed at setting a new current CPU value that makes the energy consumed by a Structure
        get closer to a limit.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            structure (dict): The dictionary containing all of the structure resource information
            resource (string): The resource name, used for indexing purposes

        Returns:
            (int) The amount to be reduced using the fit to usage policy.

        """
        power_budget = structure["resources"][resource]["max"]
        current_energy_usage = structure["resources"][resource]["usage"]
        error = power_budget - current_energy_usage
        energy_amplification = error * self.cpu_shares_per_watt  # How many cpu shares to rescale per watt
        return int(energy_amplification)

    def get_container_energy_str(self, resources_dict):
        """Get a summary string but for the energy resource, which has a different behavior from others such as CPU or
        Memory.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            resources_dict (dict): A dictionary with all the resources' information, including energy

        Returns:
            (string) A string that summarizes the state of the energy resource

        """
        energy_dict = resources_dict["energy"]
        string = list()
        for field in ["max", "usage", "min"]:
            string.append(str(self.try_get_value(energy_dict, field)))
        return ",".join(string)

    def adjust_container_state(self, resources, limits, resources_to_adjust):
        for resource in resources_to_adjust:
            if "boundary" not in limits[resource]:
                raise RuntimeError("Missing boundary value for resource {0}".format(resource))
            if "boundary_type" not in limits[resource]:
                raise RuntimeError("Missing boundary type value for resource {0}".format(resource))
            if "current" not in resources[resource]:
                raise RuntimeError("Missing current value for resource {0}".format(resource))
            if "max" not in resources[resource]:
                raise RuntimeError("Missing max value for resource {0}".format(resource))

            n_loop, errors = 0, True
            while errors:
                n_loop += 1
                try:
                    self.check_invalid_container_state(resources, limits, resource)
                    errors = False
                except ValueError:
                    # Correct the chain max >= current > upper > lower, including boundary between current and upper
                    if resources[resource]["current"] > resources[resource]["max"]:
                        resources[resource]["current"] = resources[resource]["max"]
                    # Compute boundary based on max or current
                    margin_resource = self.get_margin_from_boundary(limits[resource]["boundary"], limits[resource]["boundary_type"], resources[resource], resource)
                    limits[resource]["upper"] = int(resources[resource]["current"] - margin_resource)
                    limits[resource]["lower"] = int(limits[resource]["upper"] - margin_resource)
                except RuntimeError as e:
                    utils.log_error(str(e), self.debug)
                    raise e
                if n_loop >= 10:
                    raise RuntimeError("Limits for {0} can't be adjusted, check the configuration (max:{1}, current:{2}, boundary:{3}, min:{4})".format(
                        resource, resources[resource]["max"], int(resources[resource]["current"]), limits[resource]["boundary"], resources[resource]["min"]))
                    # TODO This prevents from checking other resources
        return limits

    def check_invalid_container_state(self, resources, limits, resource):
        if resource not in resources:
            raise RuntimeError("resource values not available for resource {0}".format(resource))
        if resource not in limits:
            raise RuntimeError("limit values not available for resource {0}".format(resource))
        data = {"res": resources, "lim": limits}
        values_tuples = [("max", "res"), ("current", "res"), ("upper", "lim"), ("lower", "lim"), ("min", "res")]
        values = dict()
        for value, vtype in values_tuples:
            values[value] = self.try_get_value(data[vtype][resource], value)

        # Check values are set and valid, except for current as it may have not been persisted yet
        for value in values:
            self.check_unset_values(values[value], value, resource)

        # Check if the first value is greater than the second
        # check the full chain max > upper > current > lower
        if values["current"] != NOT_AVAILABLE_STRING:
            self.check_invalid_values(values["current"], "current", values["max"], "max", resource=resource)
        self.check_invalid_values(values["upper"], "upper", values["current"], "current", resource=resource)
        self.check_invalid_values(values["lower"], "lower", values["upper"], "upper", resource=resource)

        # Check that boundary is a percentage (value between 0 and 100) and get margin applying boundary to max/current
        boundary = int(limits[resource]["boundary"])
        self.check_invalid_boundary(boundary, resource)
        resource_margin = self.get_margin_from_boundary(boundary, limits[resource]["boundary_type"], values, resource)

        # Check that there is a margin between values, like the current and upper, so
        # that the limit can be surpassed
        if values["current"] != NOT_AVAILABLE_STRING:
            if values["current"] - resource_margin < values["upper"]:
                raise ValueError("value for 'current': {0} is too close (less than {1}) to value for 'upper': {2}".format(
                    str(values["current"]), str(resource_margin), str(values["upper"])))

            elif values["current"] - resource_margin > values["upper"]:
                raise ValueError("value for 'current': {0} is too far (more than {1}) from value for 'upper': {2}".format(
                    str(values["current"]), str(resource_margin), str(values["upper"])))

    @staticmethod
    def rule_triggers_event(rule, data, resources):
        if rule["resource"] not in resources:
            return False
        else:
            return rule["active"] and \
                resources[rule["resource"]]["guard"] and \
                rule["generates"] == "events" and \
                jsonLogic(rule["rule"], data)

    def match_usages_and_limits(self, structure_name, rules, usages, limits, resources):

        resources_with_rules = list()
        for rule in rules:
            if rule["resource"] in resources_with_rules:
                pass
            else:
                resources_with_rules.append(rule["resource"])
                if rule["resource"] == "energy":
                    resources_with_rules.append("cpu")

        useful_resources = list()
        for resource in self.guardable_resources:
            if resource not in resources_with_rules:
                utils.log_warning("Resource {0} has no rules applied to it".format(resource), self.debug)
            elif usages[utils.res_to_metric(resource)] != self.NO_METRIC_DATA_DEFAULT_VALUE:
                useful_resources.append(resource)

        data = dict()
        for resource in useful_resources:
            if resource in resources:
                data[resource] = {
                    "limits": {resource: limits[resource]},
                    "structure": {resource: resources[resource]}}

        for usage_metric in usages:
            keys = usage_metric.split(".")
            struct_type, usage_resource = keys[0], keys[1]
            # Split the key from the retrieved data, e.g., structure.mem.usages, where mem is the resource
            if usage_resource in useful_resources:
                data[usage_resource][struct_type][usage_resource][keys[2]] = usages[usage_metric]

        events = []
        for rule in rules:
            try:
                # Check that the rule is active, the resource to watch is guarded and that the rule is activated
                if self.rule_triggers_event(rule, data, resources):
                    event_name = utils.generate_event_name(rule["action"]["events"], rule["resource"])
                    event = self.generate_event(event_name, structure_name, rule["resource"], rule["action"])
                    events.append(event)

            except KeyError as e:
                utils.log_warning("rule: {0} is missing a parameter {1} {2}".format(
                    rule["name"], str(e), str(traceback.format_exc())), self.debug)

        return events

    @staticmethod
    def generate_event(event_name, structure_name, resource, action):
        event = dict(
            name=event_name,
            resource=resource,
            type="event",
            structure=structure_name,
            action=action,
            timestamp=int(time.time()))
        return event

    def print_energy_rescale_info(self, structure, usages, limits, amount):
        for res in ["energy", "cpu"]:
            current_limit = structure["resources"][res]["current"]
            max_limit = structure["resources"][res]["max"]
            upper_limit = limits[res]["upper"]
            res_usage = usages[utils.res_to_metric(res)]
            if res == "energy":
                utils.log_warning("POWER BUDGETING -> max : {0} | usa: {1}".format(max_limit, res_usage), self.debug)
            else:
                utils.log_warning("PROPORTIONAL CPU -> cur : {0} | upp : {1} | usa: {2} | amount {3}".format(
                    current_limit, upper_limit, res_usage, amount), self.debug)

    def match_rules_and_events(self, structure, rules, events, limits, usages):
        generated_requests = list()
        events_to_remove = dict()

        for rule in rules:
            # Check that the rule has the required parameters
            rule_invalid = False
            for key in ["active", "resource", "generates", "name", ]:
                if key not in rule:
                    utils.log_warning("Rule: {0} is missing a key parameter '{1}', skipping it".format(rule["name"], key), self.debug)
                    rule_invalid = True
            if rule_invalid:
                continue

            if rule["generates"] == "requests":
                if "rescale_policy" not in rule or "rescale_type" not in rule:
                    utils.log_warning("Rule: {0} is missing the 'rescale_type' or the 'rescale_policy' parameter, skipping it".format(rule["name"]), self.debug)
                    continue

                if rule["rescale_type"] == "up" and "amount" not in rule:
                    utils.log_warning("Rule: {0} is missing a the amount parameter, skipping it".format(rule["name"]), self.debug)
                    continue

            resource_label = rule["resource"]

            rule_activated = rule["active"] and \
                             rule["generates"] == "requests" and \
                             resource_label in events and \
                             jsonLogic(rule["rule"], events[resource_label])

            if not rule_activated:
                continue

            # RULE HAS BEEN ACTIVATED

            # If rescaling a container, check that the current resource value exists, otherwise there is nothing to rescale
            if utils.structure_is_container(structure) and "current" not in structure["resources"][resource_label]:
                utils.log_warning("No current value for container' {0}' and "
                                  "resource '{1}', can't rescale".format(structure["name"], resource_label), self.debug)
                continue

            valid_rescale = True
            # Get the amount to be applied from the policy set
            if rule["rescale_type"] == "up":
                if rule["rescale_policy"] == "amount":
                    amount = rule["amount"]
                elif rule["rescale_policy"] == "fixed-ratio" and resource_label == "energy":
                    amount = self.get_amount_from_fixed_ratio(structure, resource_label)
                elif rule["rescale_policy"] == "proportional" and resource_label == "energy":
                    amount = self.get_amount_from_proportional_energy_rescaling(structure, usages, resource_label)
                elif rule["rescale_policy"] == "modelling" and resource_label == "energy":
                    if self.power_budget_is_new(structure):
                        amount = self.get_amount_from_energy_modelling(structure, usages, "up")
                    else:
                        amount = self.get_amount_from_proportional_energy_rescaling(structure, usages, resource_label)
                elif rule["rescale_policy"] == "proportional":
                    amount = rule["amount"]
                    current_resource_limit = structure["resources"][resource_label]["current"]
                    upper_limit = limits[resource_label]["upper"]
                    usage = usages[utils.res_to_metric(resource_label)]
                    ratio = min((usage - upper_limit) / (current_resource_limit - upper_limit), 1)
                    amount = int(ratio * amount)
                    utils.log_warning("PROP -> cur : {0} | upp : {1} | usa: {2} | ratio {3} | amount {4}".format(
                        current_resource_limit, upper_limit, usage, ratio, amount), self.debug)
                else:
                    valid_rescale = False
                    utils.log_warning("Invalid rescale policy '{0} for Rule {1}, skipping it".format(rule["rescale_policy"], rule["name"]), self.debug)
                    continue
            elif rule["rescale_type"] == "down":
                if rule["rescale_policy"] == "amount":
                    amount = rule["amount"]
                elif rule["rescale_policy"] == "fit_to_usage":
                    current_resource_limit = structure["resources"][resource_label]["current"]
                    resource_margin = self.get_margin_from_boundary(limits[resource_label]["boundary"],
                                                                    limits[resource_label]["boundary_type"],
                                                                    structure["resources"][resource_label],
                                                                    resource_label)
                    usage = usages[utils.res_to_metric(resource_label)]
                    amount = self.get_amount_from_fit_reduction(current_resource_limit, resource_margin, usage)
                elif rule["rescale_policy"] == "fixed-ratio" and resource_label == "energy":
                    amount = self.get_amount_from_fixed_ratio(structure, resource_label)
                elif rule["rescale_policy"] == "proportional" and resource_label == "energy":
                    amount = self.get_amount_from_proportional_energy_rescaling(structure, usages, resource_label)
                elif rule["rescale_policy"] == "modelling" and resource_label == "energy":
                    if self.power_budget_is_new(structure):
                        amount = self.get_amount_from_energy_modelling(structure, usages, "down")
                    else:
                        amount = self.get_amount_from_proportional_energy_rescaling(structure, usages, resource_label)
                else:
                    valid_rescale = False
                    utils.log_warning("Invalid rescale policy '{0} for Rule {1}, skipping it".format(rule["rescale_policy"], rule["name"]), self.debug)
                    continue

            else:
                valid_rescale = False
                utils.log_warning("Invalid rescale type '{0} for Rule {1}, skipping it".format(rule["rescale_type"], rule["name"]), self.debug)
                continue

            # Adjust energy rescaling and print extra information
            if valid_rescale and resource_label == "energy":
                # If power is within some reasonable limits we do nothing
                if self.power_is_near_power_budget(structure, usages, limits):
                    utils.log_warning("Current energy usage ({0:.2f}) for structure {1} is close to its power budget ({2:.2f}), "
                                      "setting amount to 0".format(usages[utils.res_to_metric("energy")], structure["name"],
                                                                   structure["resources"]["energy"]["max"]), self.debug)
                    amount = 0
                self.print_energy_rescale_info(structure, usages, limits, amount)

            # Ensure that amount is an integer, either by converting float -> int, or string -> int
            amount = int(amount)

            # If it is 0, because there was a previous floating value between -1 and 1, set it to 0 so that it does not generate any Request
            if amount == 0:
                utils.log_warning("Amount generated for structure {0} with rule {1} is 0".format(structure["name"], rule["name"]), self.debug)

            # Ensure that the resource does not surpass any limit
            if resource_label == "energy":
                # Energy is governed by different rules (it is adjusted indirectly via CPU throttling)
                new_amount = self.adjust_cpu_amount_to_manage_energy(amount, structure["resources"]["cpu"])
            else:
                new_amount = self.adjust_amount(amount, structure["resources"][resource_label], limits[resource_label])

            if new_amount != amount:
                utils.log_warning("Amount generated for structure {0} with rule {1} has been trimmed from {2} to {3}"
                                  .format(structure["name"], rule["name"], amount, new_amount), self.debug)

            # # If amount is 0 ignore this request else generate the request and append it
            if new_amount == 0:
                utils.log_warning("Request generated with rule {0} for structure {1} will be ignored "
                                  "because amount is 0".format(rule["name"], structure["name"]), self.debug)
            else:
                request = utils.generate_request(structure, new_amount, resource_label)
                generated_requests.append(request)

            # Remove the events that triggered the request
            event_name = utils.generate_event_name(events[resource_label]["events"], resource_label)
            if event_name not in events_to_remove:
                events_to_remove[event_name] = 0
            events_to_remove[event_name] += rule["events_to_remove"]

        return generated_requests, events_to_remove

    def print_structure_info(self, container, usages, limits, triggered_events, triggered_requests):
        resources = container["resources"]

        container_name_str = "@" + container["name"]
        coloured_resources_str = "| "
        uncoloured_resources_str = "| "
        for resource in self.guardable_resources:
            if container["resources"][resource]["guard"]:
                coloured_resources_str += resource + "({0})".format(self.get_resource_summary(resource, resources, limits, usages)) + " | "
                uncoloured_resources_str += resource + "({0})".format(self.get_resource_summary(resource, resources, limits, usages, disable_color=True)) + " | "

        ev, req = list(), list()
        for event in triggered_events:
            ev.append(event["name"])
        for request in triggered_requests:
            req.append(request["action"])
        triggered_requests_and_events = "#TRIGGERED EVENTS {0} AND TRIGGERED REQUESTS {1}".format(str(ev), str(req))

        # Debug coloured string
        utils.debug_info(" ".join([container_name_str, coloured_resources_str, triggered_requests_and_events]), self.debug)

        # Log uncoloured string
        utils.log_info(" ".join([container_name_str, uncoloured_resources_str, triggered_requests_and_events]), debug=False)

    def process_serverless_structure(self, structure, usages, limits, rules):

        # Match usages and rules to generate events
        triggered_events = self.match_usages_and_limits(structure["name"], rules, usages, limits, structure["resources"])

        # If energy model reliability is high power modelling rules are independent of events the first time they are applied
        self.check_power_modelling_rules(structure, rules, limits, usages, triggered_events)

        # Remote database operation
        if triggered_events:
            self.couchdb_handler.add_events(triggered_events)

        # Remote database operation
        all_events = self.couchdb_handler.get_events(structure)

        # Filter the events according to timestamp
        filtered_events, old_events = self.sort_events(all_events, self.event_timeout)

        if old_events:
            # Remote database operation
            self.couchdb_handler.delete_events(old_events)

        # If there are no events, nothing else to do as no requests will be generated
        if filtered_events:
            # Merge all the event counts
            reduced_events = self.reduce_structure_events(filtered_events)

            # Match events and rules to generate requests
            triggered_requests, events_to_remove = self.match_rules_and_events(structure, rules, reduced_events, limits, usages)

            # Remove events that generated the request
            # Remote database operation
            for event in events_to_remove:
                self.couchdb_handler.delete_num_events_by_structure(structure, event, events_to_remove[event])

            if triggered_requests:
                # Remote database operation
                self.couchdb_handler.add_requests(triggered_requests)

        else:
            triggered_requests = list()

        # DEBUG AND INFO OUTPUT
        if self.debug:
            self.print_structure_info(structure, usages, limits, triggered_events, triggered_requests)

    def serverless(self, structure, rules):
        structure_subtype = structure["subtype"]

        # Check if structure is guarded
        if "guard" not in structure or not structure["guard"]:
            utils.log_warning("structure: {0} is set to leave alone, skipping".format(structure["name"]), self.debug)
            self.register_scaling(structure, wait=False)  # Ensure the structure is registered, even when no scaling is performed
            return

        # Check if the structure has any resource set to guarded
        struct_guarded_resources = list()
        for res in self.guardable_resources:
            if res in structure["resources"] and "guard" in structure["resources"][res] and structure["resources"][res]["guard"]:
                struct_guarded_resources.append(res)
        if not struct_guarded_resources:
            utils.log_warning("Structure {0} is set to guarded but has no resource marked to guard".format(structure["name"]), self.debug)
            self.register_scaling(structure, wait=False)
            return

        # Check if structure is being monitored, otherwise, ignore
        if not utils.structure_subtype_is_supported(structure_subtype):
            utils.log_error("Unknown structure subtype '{0}'".format(structure_subtype), self.debug)
            self.register_scaling(structure, wait=False)
            return

        try:
            metrics_to_retrieve, metrics_to_generate = utils.get_metrics_to_retrieve_and_generate(struct_guarded_resources, structure_subtype)
            tag = utils.get_tag(structure["subtype"])

            # Remote database operation
            usages = self.opentsdb_handler.get_structure_timeseries({tag: structure["name"]},
                                                                    self.window_timelapse, self.window_delay,
                                                                    metrics_to_retrieve, metrics_to_generate)

            for metric in usages:
                if usages[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE:
                    utils.log_warning("structure: {0} has no usage data for {1}".format(structure["name"], metric), self.debug)

            # Skip this structure if all the usage metrics are unavailable
            if all([usages[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
                utils.log_warning("structure: {0} has no usage data for any metric, skipping".format(structure["name"]), self.debug)
                return

            resources = structure["resources"]

            # Remote database operation
            limits = self.couchdb_handler.get_limits(structure)
            limits_resources = limits["resources"]

            if not limits_resources:
                utils.log_warning("structure: {0} has no limits".format(structure["name"]), self.debug)
                return

            # Adjust the structure limits according to the current value
            limits["resources"] = self.adjust_container_state(resources, limits_resources, self.guardable_resources)

            # Remote database operation
            self.couchdb_handler.update_limit(limits)

            self.process_serverless_structure(structure, usages, limits_resources, rules)

        except Exception as e:
            utils.log_error("Error with structure {0}: {1}".format(structure["name"], str(e)), self.debug)
        finally:
            self.register_scaling(structure, wait=False)

    def guard_structures(self, structures):
        # Remote database operation
        rules = self.couchdb_handler.get_rules()

        # Initialise iteration dependent variables
        self.__init_iteration_vars(structures)

        threads = []
        for structure in self.current_structures:
            thread = Thread(name="process_structure_{0}".format(structure["name"]), target=self.serverless,
                            args=(structure, rules,))
            thread.start()
            threads.append(thread)

        for process in threads:
            process.join()

    def invalid_conf(self, ):
        for res in self.guardable_resources:
            if res not in ["cpu", "mem", "disk", "net", "energy"]:
                return True, "Resource to be guarded '{0}' is invalid".format(res)

        if self.structure_guarded not in ["container", "application"]:
            return True, "Structure to be guarded '{0}' is invalid".format(self.structure_guarded)

        for key, num in [("WINDOW_TIMELAPSE", self.window_timelapse), ("WINDOW_DELAY", self.window_delay), ("EVENT_TIMEOUT", self.event_timeout)]:
            if num < 5:
                return True, "Configuration item '{0}' with a value of '{1}' is likely invalid".format(key, num)
        return False, ""

    def guard(self, ):
        myConfig = utils.MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO,
                            format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        while True:

            utils.update_service_config(self, SERVICE_NAME, myConfig, self.couchdb_handler)

            # If power model has changed all the power budgets are restarted (we try to rescale using the new model)
            if self.energy_model_name != self.last_used_energy_model:
                self.last_used_energy_model = self.energy_model_name
                self.power_budget = {}
                self.model_is_hw_aware = None

            t0 = utils.start_epoch(self.debug)

            utils.print_service_config(self, myConfig, self.debug)

            ## CHECK INVALID CONFIG ##
            invalid, message = self.invalid_conf()
            if invalid:
                utils.log_error(message, self.debug)
                if self.window_timelapse < 5:
                    utils.log_error("Window difference is too short, replacing with DEFAULT value '{0}'".format(CONFIG_DEFAULT_VALUES["WINDOW_TIMELAPSE"]), self.debug)
                    self.window_timelapse = CONFIG_DEFAULT_VALUES["WINDOW_TIMELAPSE"]
                time.sleep(self.window_timelapse)
                utils.end_epoch(self.debug, self.window_timelapse, t0)
                continue

            thread = None
            if self.active:
                # Remote database operation
                structures = utils.get_structures(self.couchdb_handler, self.debug, subtype=self.structure_guarded)
                if structures:
                    utils.log_info("{0} Structures to process, launching threads".format(len(structures)), self.debug)
                    thread = Thread(name="guard_structures", target=self.guard_structures, args=(structures,))
                    thread.start()
                else:
                    utils.log_info("No structures to process", self.debug)
            else:
                utils.log_warning("Guardian is not activated", self.debug)

            time.sleep(self.window_timelapse)

            utils.wait_operation_thread(thread, self.debug)

            utils.end_epoch(t0, self.window_timelapse, t0)


def main():
    try:
        guardian = Guardian()
        guardian.guard()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
