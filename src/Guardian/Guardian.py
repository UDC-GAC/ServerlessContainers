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

from threading import Thread
import time
import traceback
import logging

from json_logic import jsonLogic
from termcolor import colored

from src.MyUtils.MyUtils import MyConfig, log_error, get_service, beat, log_info, log_warning, \
    get_structures, generate_event_name, generate_request_name, wait_operation_thread, structure_is_container, generate_structure_usage_metric, start_epoch, end_epoch
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog

BDWATCHDOG_CONTAINER_METRICS = {"cpu": ['proc.cpu.user', 'proc.cpu.kernel'], "mem": ['proc.mem.resident', 'proc.mem.virtual']}
BDWATCHDOG_APPLICATION_METRICS = {"cpu": ['structure.cpu.usage'], "mem": ['structure.mem.usage'], "energy": ['structure.energy.usage']}

GUARDIAN_CONTAINER_METRICS = {
    'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel'],
    'structure.mem.usage': ['proc.mem.resident']
}
GUARDIAN_APPLICATION_METRICS = {
    'structure.cpu.usage': ['structure.cpu.usage'],
    'structure.mem.usage': ['structure.mem.usage'],
    'structure.energy.usage': ['structure.energy.usage']
}
GUARDIAN_METRICS = {"container": GUARDIAN_CONTAINER_METRICS, "application": GUARDIAN_APPLICATION_METRICS}
BDWATCHDOG_METRICS = {"container": BDWATCHDOG_CONTAINER_METRICS, "application": BDWATCHDOG_APPLICATION_METRICS}

TAGS = {"container": "host", "application": "structure"}

translator_dict = {"cpu": "structure.cpu.usage", "mem": "structure.mem.usage", "energy": "structure.energy.usage"}

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "EVENT_TIMEOUT": 40, "DEBUG": True,
                         "STRUCTURE_GUARDED": "container", "GUARDABLE_RESOURCES": ["cpu"],
                         "CPU_SHARES_PER_WATT": 5, "ACTIVE": True}
SERVICE_NAME = "guardian"

NOT_AVAILABLE_STRING = "n/a"

NON_ADJUSTABLE_RESOURCES = ["energy"]


class Guardian:
    """
    Guardian class that implements the logic for this microservice. The Guardian takes care of matching the resource
    time series with a subset of rules to generate Events and then, matches the event against another subset of rules
    to generate scaling Requests.

    For more information you can visit: https://serverlesscontainers.readthedocs.io/en/latest/#architecture-and-microservices
    """

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE

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

    def get_resource_summary(self, resource_label, resources_dict, limits_dict, usages_dict):
        """Produces a string to summarize the current state of a resource with all of its information and
        the following format: _[max, current, upper limit, usage, lower limit, min]_

        Args:
            resource_label (string): The resource name label, used to create the string and to access the dictionaries
            resources_dict (dict): a dictionary with the metrics (e.g., max, min) of the resources
            limits_dict (dict): a dictionary with the limits (e.g., lower, upper) of the resources
            usages_dict (dict): a dictionary with the usages of the resources

        Returns:
            (string) A summary string that contains all of the appropriate values for all of the resources

        """
        metrics = resources_dict[resource_label]
        limits = limits_dict[resource_label]
        color_map = {"max": "red", "current": "magenta", "upper": "yellow", "usage": "cyan", "lower": "green", "min": "blue"}

        if not usages_dict or usages_dict[translator_dict[resource_label]] == self.NO_METRIC_DATA_DEFAULT_VALUE:
            usage_value_string = NOT_AVAILABLE_STRING
        else:
            usage_value_string = str("%.2f" % usages_dict[translator_dict[resource_label]])

        strings = list()
        for key, values in [("max", metrics), ("current", metrics), ("upper", limits), ("lower", limits), ("min", metrics)]:
            strings.append(colored(str(self.try_get_value(values, key)), color_map[key]))
        strings.insert(3, colored(usage_value_string, color_map["usage"]))  # Manually add the usage metric

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
    def get_amount_from_fit_reduction(current_resource_limit, boundary, current_resource_usage):
        """Get an amount that will be reduced from the current resource limit using a policy of *fit to the usage*.
        With this policy it is aimed at setting a new current value that gets close to the usage but leaving a boundary
        to avoid causing a severe bottleneck. More specifically, using the boundary configured this policy tries to
        find a scale down amount that makes the usage value stay between the _now new_ lower and upper limits.

        Args:
            current_resource_limit (integer): The current applied limit for this resource
            boundary (integer): The boundary used between limits
            current_resource_usage (integer): The usage value for this resource

        Returns:
            (int) The amount to be reduced using the fit to usage policy.

        """
        upper_to_lower_window = boundary
        current_to_upper_window = boundary

        # Set the limit so that the resource usage is placed in between the upper and lower limits
        # and keeping the boundary between the upper and the real resource limits
        desired_applied_resource_limit = \
            current_resource_usage + int(upper_to_lower_window / 2) + current_to_upper_window

        return -1 * (current_resource_limit - desired_applied_resource_limit)

    def get_amount_from_proportional_energy_rescaling(self, structure, resource):
        """Get an amount that will be reduced from the current resource limit using a policy of *proportional
        energy-based CPU scaling*.
        With this policy it is aimed at setting a new current CPU value that makes the energy consumed by a Structure
        get closer to a limit.

        *THIS FUNCTION IS USED WITH THE ENERGY CAPPING SCENARIO*, see: http://bdwatchdog.dec.udc.es/energy/index.html

        Args:
            structure (dict): The dictionary containing all of the structure resource information
            resource (string): The resource name, used for indexing puroposes

        Returns:
            (int) The amount to be reduced using the fit to usage policy.

        """
        max_resource_limit = structure["resources"][resource]["max"]
        current_resource_limit = structure["resources"][resource]["usage"]
        difference = max_resource_limit - current_resource_limit
        energy_amplification = difference * self.cpu_shares_per_watt  # How many cpu shares to rescale per watt
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
            if "current" not in resources[resource]:
                raise RuntimeError("Missing current value for resource {0}".format(resource))

            n_loop, errors = 0, True
            while errors:
                n_loop += 1
                try:
                    self.check_invalid_container_state(resources, limits, resource)
                    errors = False
                except ValueError:
                    # Correct the chain current > upper > lower, including boundary between current and upper
                    boundary = int(limits[resource]["boundary"])
                    limits[resource]["upper"] = int(resources[resource]["current"] - boundary)
                    limits[resource]["lower"] = int(limits[resource]["upper"] - boundary)
                except RuntimeError as e:
                    log_error(str(e), self.debug)
                    raise e
                if n_loop >= 10:
                    message = "Limits for {0} can't be adjusted, check the configuration (max:{1},current:{2}, boundary:{3}, min:{4})".format(
                        resource, resources[resource]["max"], int(resources[resource]["current"]), limits[resource]["boundary"], resources[resource]["min"])
                    raise RuntimeError(message)
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
        values["boundary"] = data["lim"][resource]["boundary"]

        # Check values are set and valid, except for current as it may have not been persisted yet
        for value in values:
            self.check_unset_values(values[value], value, resource)

        # Check if the first value is greater than the second
        # check the full chain max > upper > current > lower
        if values["current"] != NOT_AVAILABLE_STRING:
            self.check_invalid_values(values["current"], "current", values["max"], "max", resource=resource)
        self.check_invalid_values(values["upper"], "upper", values["current"], "current", resource=resource)
        self.check_invalid_values(values["lower"], "lower", values["upper"], "upper", resource=resource)

        # Check that there is a boundary between values, like the current and upper, so
        # that the limit can be surpassed
        if values["current"] != NOT_AVAILABLE_STRING:
            if values["current"] - values["boundary"] < values["upper"]:
                raise ValueError("value for 'current': {0} is too close (less than {1}) to value for 'upper': {2}".format(
                    str(values["current"]), str(values["boundary"]), str(values["upper"])))

            elif values["current"] - values["boundary"] > values["upper"]:
                raise ValueError("value for 'current': {0} is too far (more than {1}) from value for 'upper': {2}".format(
                    str(values["current"]), str(values["boundary"]), str(values["upper"])))

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

        useful_resources = list()
        for resource in self.guardable_resources:
            if resource not in resources_with_rules:
                log_warning("Resource {0} has no rules applied to it".format(resource), self.debug)
            else:
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
                    event_name = generate_event_name(rule["action"]["events"], rule["resource"])
                    event = self.generate_event(event_name, structure_name, rule["resource"], rule["action"])
                    events.append(event)

            except KeyError as e:
                log_warning("rule: {0} is missing a parameter {1} {2}".format(
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

    @staticmethod
    def generate_request(structure, amount, resource_label):
        action = generate_request_name(amount, resource_label)
        request = dict(
            type="request",
            resource=resource_label,
            amount=int(amount),
            structure=structure["name"],
            action=action,
            timestamp=int(time.time()),
            structure_type=structure["subtype"]
        )
        # For the moment, energy rescaling is uniquely mapped to cpu rescaling
        if resource_label == "energy":
            request["resource"] = "cpu"
            request["for_energy"] = True

        # If scaling a container, add its host information as it will be needed
        if structure_is_container(structure):
            request["host"] = structure["host"]
            request["host_rescaler_ip"] = structure["host_rescaler_ip"]
            request["host_rescaler_port"] = structure["host_rescaler_port"]

        return request

    def match_rules_and_events(self, structure, rules, events, limits, usages):
        generated_requests = list()
        events_to_remove = dict()

        for rule in rules:
            # Check that the rule has the required parameters
            rule_invalid = False
            for key in ["active", "resource", "generates", "name", ]:
                if key not in rule:
                    log_warning("Rule: {0} is missing a key parameter '{1}', skipping it".format(rule["name"], key), self.debug)
                    rule_invalid = True
            if rule_invalid:
                continue

            if rule["generates"] == "requests":
                if "rescale_policy" not in rule or "rescale_type" not in rule:
                    log_warning("Rule: {0} is missing the 'rescale_type' or the 'rescale_policy' parameter, skipping it".format(rule["name"]), self.debug)
                    continue

                if rule["rescale_type"] == "up" and "amount" not in rule:
                    log_warning("Rule: {0} is missing a the amount parameter, skipping it".format(rule["name"]), self.debug)
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
            if structure_is_container(structure) and "current" not in structure["resources"][resource_label]:
                log_warning("No current value for container' {0}' and "
                            "resource '{1}', can't rescale".format(structure["name"], resource_label), self.debug)
                continue

            # Get the amount to be applied from the policy set
            if rule["rescale_type"] == "up":
                if rule["rescale_policy"] == "amount":
                    amount = rule["amount"]
                elif rule["rescale_policy"] == "proportional":
                    amount = rule["amount"]
                    current_resource_limit = structure["resources"][resource_label]["current"]
                    upper_limit = limits[resource_label]["upper"]
                    usage = usages[translator_dict[resource_label]]
                    ratio = min((usage - upper_limit) / (current_resource_limit - upper_limit), 1)
                    amount = int(ratio * amount)
                    log_warning("PROP -> cur : {0} | upp : {1} | usa: {2} | ratio {3} | amount {4}".format(
                        current_resource_limit, upper_limit, usage, ratio, amount), self.debug)
                else:
                    log_warning("Invalid rescale policy '{0} for Rule {1}, skipping it".format(rule["rescale_policy"], rule["name"]), self.debug)
                    continue
            elif rule["rescale_type"] == "down":
                if rule["rescale_policy"] == "amount":
                    amount = rule["amount"]
                elif rule["rescale_policy"] == "fit_to_usage":
                    current_resource_limit = structure["resources"][resource_label]["current"]
                    boundary = limits[resource_label]["boundary"]
                    usage = usages[translator_dict[resource_label]]
                    amount = self.get_amount_from_fit_reduction(current_resource_limit, boundary, usage)
                elif rule["rescale_policy"] == "proportional" and rule["resource"] == "energy":
                    amount = self.get_amount_from_proportional_energy_rescaling(structure, resource_label)
                else:
                    log_warning("Invalid rescale policy '{0} for Rule {1}, skipping it".format(rule["rescale_policy"], rule["name"]), self.debug)
                    continue
            else:
                log_warning("Invalid rescale type '{0} for Rule {1}, skipping it".format(rule["rescale_type"], rule["name"]), self.debug)
                continue

            # Ensure that amount is an integer, either by converting float -> int, or string -> int
            amount = int(amount)

            # If it is 0, because there was a previous floating value between -1 and 1, set it to 0 so that it does not generate any Request
            if amount == 0:
                log_warning("Amount generated for structure {0} with rule {1} is 0, "
                            "will not generate a request, but events will be removed".format(structure["name"], rule["name"]), self.debug)
            else:
                # If the resource is susceptible to check, ensure that it does not surpass any limit
                new_amount = amount
                if resource_label not in NON_ADJUSTABLE_RESOURCES:
                    structure_resources = structure["resources"][resource_label]
                    structure_limits = limits[resource_label]
                    new_amount = self.adjust_amount(amount, structure_resources, structure_limits)
                    if new_amount != amount:
                        log_warning("Amount generated for structure {0} with rule {1} has been trimmed from {2} to {3}".format(
                            structure["name"], rule["name"], amount, new_amount), self.debug)

                # Generate the request and append it
                request = self.generate_request(structure, new_amount, resource_label)
                generated_requests.append(request)

            # Remove the events that triggered the request
            event_name = generate_event_name(events[resource_label]["events"], resource_label)
            if event_name not in events_to_remove:
                events_to_remove[event_name] = 0
            events_to_remove[event_name] += rule["events_to_remove"]

        return generated_requests, events_to_remove

    def print_structure_info(self, container, usages, limits, triggered_events, triggered_requests):
        resources = container["resources"]

        container_name_str = "@" + container["name"]
        resources_str = "| "
        for resource in self.guardable_resources:
            if container["resources"][resource]["guard"]:
                resources_str += resource + "({0})".format(self.get_resource_summary(resource, resources, limits, usages)) + " | "

        ev, req = list(), list()
        for event in triggered_events:
            ev.append(event["name"])
        for request in triggered_requests:
            req.append(request["action"])
        triggered_requests_and_events = "#TRIGGERED EVENTS {0} AND TRIGGERED REQUESTS {1}".format(str(ev), str(req))
        log_info(
            " ".join([container_name_str, resources_str, triggered_requests_and_events]),
            self.debug)

    def process_serverless_structure(self, structure, usages, limits, rules):

        # Match usages and rules to generate events
        triggered_events = self.match_usages_and_limits(structure["name"], rules, usages, limits, structure["resources"])

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
        # for r in rules:
        #     print("Using rule '{0}' for structure '{1}'".format(r["_id"], structure["name"]))
        structure_subtype = structure["subtype"]

        # Check if structure is guarded
        if "guard" not in structure or not structure["guard"]:
            log_warning("structure: {0} is set to leave alone, skipping".format(structure["name"]), self.debug)
            return

        # Check if the structure has any resource set to guarded
        struct_guarded_resources = list()
        for res in self.guardable_resources:
            if res in structure["resources"] and "guard" in structure["resources"][res] and structure["resources"][res]["guard"]:
                struct_guarded_resources.append(res)
        if not struct_guarded_resources:
            log_warning("Structure {0} is set to guarded but has no resource marked to guard".format(structure["name"]), self.debug)
            return

        # Check if structure is being monitored, otherwise, ignore
        if structure_subtype not in BDWATCHDOG_METRICS or structure_subtype not in GUARDIAN_METRICS or structure_subtype not in TAGS:
            log_error("Unknown structure subtype '{0}'".format(structure_subtype), self.debug)
            return

        try:
            metrics_to_retrieve = list()
            metrics_to_generate = dict()
            for res in struct_guarded_resources:
                metrics_to_retrieve += BDWATCHDOG_METRICS[structure_subtype][res]
                metrics_to_generate[generate_structure_usage_metric(res)] = GUARDIAN_METRICS[structure_subtype][generate_structure_usage_metric(res)]
            tag = TAGS[structure_subtype]

            # Remote database operation
            usages = self.opentsdb_handler.get_structure_timeseries({tag: structure["name"]},
                                                                    self.window_difference, self.window_delay,
                                                                    metrics_to_retrieve, metrics_to_generate)

            for metric in usages:
                if usages[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE:
                    log_warning("structure: {0} has no usage data for {1}".format(structure["name"], metric), self.debug)

            # Skip this structure if all the usage metrics are unavailable
            if all([usages[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
                log_warning("structure: {0} has no usage data for any metric, skipping".format(structure["name"]), self.debug)
                return

            resources = structure["resources"]

            # Remote database operation
            limits = self.couchdb_handler.get_limits(structure)
            limits_resources = limits["resources"]

            if not limits_resources:
                log_warning("structure: {0} has no limits".format(structure["name"]), self.debug)
                return

            # Adjust the structure limits according to the current value
            limits["resources"] = self.adjust_container_state(resources, limits_resources, self.guardable_resources)

            # Remote database operation
            self.couchdb_handler.update_limit(limits)

            self.process_serverless_structure(structure, usages, limits_resources, rules)

        except Exception as e:
            log_error("Error with structure {0}: {1}".format(structure["name"], str(e)), self.debug)

    @staticmethod
    def classify_rules(rules):
        rules_per_profile = dict()
        for r in rules:
            if r["profile"] not in rules_per_profile:
                rules_per_profile[r["profile"]] = [r]
            else:
                rules_per_profile[r["profile"]].append(r)
        return rules_per_profile

    def guard_structures(self, structures):
        # Remote database operation
        rules = self.couchdb_handler.get_rules()
        rules_per_profile = self.classify_rules(rules)

        threads = []
        for structure in structures:
            if "profile" not in structure:
                rules = rules_per_profile["default"]
                log_warning("Structure '{0}' has not any profile associated, "
                            "using 'default' profile".format(structure["name"]), self.debug)
            else:
                if structure["profile"] not in rules_per_profile:
                    log_warning("Profile '{0}' as used in structure '{1}' has not any rule associated with it, "
                                "using 'default' profile".format(structure["profile"],structure["name"]), self.debug)
                    rules = rules_per_profile["default"]
                else:
                    rules = rules_per_profile[structure["profile"]]
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

        for key, num in [("WINDOW_TIMELAPSE", self.window_difference), ("WINDOW_DELAY", self.window_delay), ("EVENT_TIMEOUT", self.event_timeout)]:
            if num < 5:
                return True, "Configuration item '{0}' with a value of '{1}' is likely invalid".format(key, num)
        return False, ""


    def guard(self, ):
        myConfig = MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

        while True:
            # Get service info
            service = get_service(self.couchdb_handler, SERVICE_NAME)

            # Heartbeat
            beat(self.couchdb_handler, SERVICE_NAME)

            # CONFIG
            myConfig.set_config(service["config"])
            self.debug = myConfig.get_value("DEBUG")
            debug = self.debug
            self.guardable_resources = myConfig.get_value("GUARDABLE_RESOURCES")
            self.cpu_shares_per_watt = myConfig.get_value("CPU_SHARES_PER_WATT")
            self.window_difference = myConfig.get_value("WINDOW_TIMELAPSE")
            self.window_delay = myConfig.get_value("WINDOW_DELAY")
            self.structure_guarded = myConfig.get_value("STRUCTURE_GUARDED")
            self.event_timeout = myConfig.get_value("EVENT_TIMEOUT")
            SERVICE_IS_ACTIVATED = myConfig.get_value("ACTIVE")

            t0 = start_epoch(self.debug)

            log_info("Config is as follows:", debug)
            log_info(".............................................", debug)
            log_info("Time window lapse -> {0}".format(self.window_difference), debug)
            log_info("Delay -> {0}".format(self.window_delay), debug)
            log_info("Event timeout -> {0}".format(self.event_timeout), debug)
            log_info("Resources guarded are -> {0}".format(self.guardable_resources), debug)
            log_info("Structure type guarded is -> {0}".format(self.structure_guarded), debug)
            log_info(".............................................", debug)

            ## CHECK INVALID CONFIG ##
            invalid, message = self.invalid_conf()
            if invalid:
                log_error(message, debug)
                if self.window_difference < 5:
                    log_error("Window difference is too short, replacing with DEFAULT value '{0}'".format(CONFIG_DEFAULT_VALUES["WINDOW_TIMELAPSE"]), self.debug)
                    self.window_difference = CONFIG_DEFAULT_VALUES["WINDOW_TIMELAPSE"]
                time.sleep(self.window_difference)
                end_epoch(self.debug, self.window_difference, t0)
                continue

            thread = None
            if SERVICE_IS_ACTIVATED:
                # Remote database operation
                structures = get_structures(self.couchdb_handler, debug, subtype=self.structure_guarded)
                if structures:
                    log_info("{0} Structures to process, launching threads".format(len(structures)), debug)
                    thread = Thread(name="guard_structures", target=self.guard_structures, args=(structures,))
                    thread.start()
                else:
                    log_info("No structures to process", debug)
            else:
                log_warning("Guardian is not activated", debug)

            time.sleep(self.window_difference)

            wait_operation_thread(thread, debug)

            end_epoch(t0, self.window_difference, t0)


def main():
    try:
        guardian = Guardian()
        guardian.guard()
    except Exception as e:
        log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
