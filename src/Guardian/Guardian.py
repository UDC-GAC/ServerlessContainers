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

from json_logic import jsonLogic
from termcolor import colored

import src.MyUtils.MyUtils as utils

import src.StateDatabase.opentsdb as bdwatchdog
import src.WattWizard.WattWizardUtils as wattwizard
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

MODELS_STRUCTURE = "host"

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "EVENT_TIMEOUT": 40, "DEBUG": True,
                         "STRUCTURE_GUARDED": "container", "GUARDABLE_RESOURCES": ["cpu"], "ACTIVE": True}

NOT_AVAILABLE_STRING = "n/a"


class Guardian(Service):
    """
    Guardian class that implements the logic for this microservice. The Guardian takes care of matching the resource
    time series with a subset of rules to generate Events and then, matches the event against another subset of rules
    to generate scaling Requests.

    For more information you can visit: https://bdwatchdog.dec.udc.es/ServerlessContainers/documentation/web/architecture
    """

    def __init__(self):
        super().__init__("guardian", ConfigValidator(), CONFIG_DEFAULT_VALUES, sleep_attr="window_timelapse")
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.wattwizard_handler = wattwizard.WattWizardUtils()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.window_timelapse, self.window_delay, self.event_timeout, self.debug = None, None, None, None
        self.structure_guarded, self.guardable_resources, self.active = None, None, None

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
            return max(int(resource_values["max"] * boundary / 100), 1)
        elif boundary_type == "percentage_of_current":
            return max(int(resource_values["current"] * boundary / 100), 1)
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
    def get_amount_from_fit_to_usage(current_resource_limit, resource_margin, current_resource_usage):
        """Get an amount that will be adjusted in the current resource limit using a policy of *fit to the usage*.
        With this policy it is aimed at setting a new current value that gets close to the usage but leaving a boundary
        to avoid causing a severe bottleneck. More specifically, using the boundary configured this policy tries to
        find a scale up/down amount that makes the usage value stay between the _now new_ lower and upper limits.

        Args:
            current_resource_limit (integer): The current applied limit for this resource
            resource_margin (integer): The margin used between limits
            current_resource_usage (integer): The usage value for this resource

        Returns:
            (int) The amount to be scaled using the fit to usage policy.

        """
        upper_to_lower_window = resource_margin
        current_to_upper_window = resource_margin

        # Set the limit so that the resource usage is placed in between the upper and lower limits
        # and keeping the boundary between the upper and the real resource limits
        desired_limit = current_resource_usage + int(upper_to_lower_window / 2) + current_to_upper_window

        return desired_limit - current_resource_limit

    def adjust_container_state(self, resources, limits, resources_to_adjust):
        for resource in resources_to_adjust:
            for field, d in [("boundary", limits), ("boundary_type", limits), ("current", resources), ("max", resources)]:
                if field not in d[resource]:
                    raise RuntimeError("Missing {0} value for resource {1}".format(field, resource))

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
        resources_with_rules = set()
        for rule in rules:
            resources_with_rules.add(rule["resource"])

        useful_resources = []
        for resource in self.guardable_resources:
            if resource not in resources_with_rules:
                utils.log_warning("Resource {0} has no rules applied to it".format(resource), self.debug)
            elif usages[utils.res_to_metric(resource)] != self.NO_METRIC_DATA_DEFAULT_VALUE:
                useful_resources.append(resource)

        # Set proper data structure to match the rules using jsonLogic
        data = {}
        for resource in useful_resources:
            if resource in resources:
                data[resource] = {
                    "limits": {resource: limits[resource]},
                    "structure": {resource: resources[resource]}}

        for usage_metric in usages:
            struct_type, usage_resource, field = usage_metric.split(".")
            # Split the key from the retrieved data, e.g., structure.mem.usages, where mem is the resource
            if usage_resource in useful_resources:
                data[usage_resource][struct_type][usage_resource][field] = usages[usage_metric]

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

                if rule["rescale_policy"] in ["amount", "proportional"] and "amount" not in rule:
                    utils.log_warning("Rule: {0} is missing the 'amount' parameter, skipping it".format(rule["name"]), self.debug)
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
                utils.log_warning("No current value for container' {0}' and resource '{1}', can't rescale"
                                  .format(structure["name"], resource_label), self.debug)
                continue

            if rule["rescale_type"] not in ["up", "down"]:
                utils.log_warning("Invalid rescale type '{0} for Rule {1}, skipping it".format(rule["rescale_type"], rule["name"]), self.debug)
                continue

            # Get the amount to be applied from the policy set
            if rule["rescale_policy"] == "amount":
                amount = rule["amount"]
            elif rule["rescale_policy"] == "fit_to_usage":
                current_resource_limit = structure["resources"][resource_label]["current"]
                resource_margin = self.get_margin_from_boundary(limits[resource_label]["boundary"], limits[resource_label]["boundary_type"],
                                                                structure["resources"][resource_label], resource_label)
                usage = usages[utils.res_to_metric(resource_label)]
                amount = self.get_amount_from_fit_to_usage(current_resource_limit, resource_margin, usage)
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
                utils.log_warning("Invalid rescale policy '{0} for rule {1}, skipping it".format(rule["rescale_policy"], rule["name"]), self.debug)
                continue

            # Ensure that amount is an integer, either by converting float -> int, or string -> int
            amount = int(amount)

            # Ensure that the resource does not surpass any limit
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
            if resource in container["resources"] and container["resources"][resource]["guard"]:
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
            return

        # Check if the structure has any resource set to guarded
        struct_guarded_resources = list()
        for res in self.guardable_resources:
            if structure.get("resources", {}).get(res, {}).get("guard", False):
                struct_guarded_resources.append(res)
        if not struct_guarded_resources:
            utils.log_warning("Structure {0} is set to guarded but has no resource marked to guard".format(structure["name"]), self.debug)
            return

        # Check if structure is being monitored, otherwise, ignore
        if not utils.structure_subtype_is_supported(structure_subtype):
            utils.log_error("Unknown structure subtype '{0}'".format(structure_subtype), self.debug)
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
            limits["resources"] = self.adjust_container_state(resources, limits_resources, struct_guarded_resources)

            # Remote database operation
            self.couchdb_handler.update_limit(limits)
            # TODO: If resources are updated in adjust_container_state, make sure they are persisted in the DB

            self.process_serverless_structure(structure, usages, limits_resources, rules)

        except Exception as e:
            utils.log_error("Error with structure {0}: {1}".format(structure["name"], str(e)), self.debug)

    def guard_structures(self, structures):
        # Remote database operation
        rules = self.couchdb_handler.get_rules()

        threads = []
        for structure in structures:
            thread = Thread(name="process_structure_{0}".format(structure["name"]), target=self.serverless,
                            args=(structure, rules,))
            thread.start()
            threads.append(thread)

        for process in threads:
            process.join()

    def work(self, ):
        thread = None
        structures = utils.get_structures(self.couchdb_handler, self.debug, subtype=self.structure_guarded)
        if structures:
            utils.log_info("{0} Structures to process, launching threads".format(len(structures)), self.debug)
            thread = Thread(name="guard_structures", target=self.guard_structures, args=(structures,))
            thread.start()
        else:
            utils.log_info("No structures to process", self.debug)
        return thread

    def guard(self, ):
        self.run_loop()


def main():
    try:
        guardian = Guardian()
        guardian.guard()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
