# /usr/bin/python
from __future__ import print_function

from threading import Thread

import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
from json_logic import jsonLogic
import StateDatabase.couchdb as couchDB
import StateDatabase.opentsdb as bdwatchdog

BDWATCHDOG_CONTAINER_METRICS = ['proc.cpu.user', 'proc.mem.resident', 'proc.cpu.kernel', 'proc.mem.virtual']
# BDWATCHDOG_CONTAINER_METRICS = ['proc.cpu.user', 'proc.cpu.kernel', 'proc.mem.resident', 'proc.disk.writes.mb',
#                                'proc.disk.reads.mb', 'proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']

GUARDIAN_CONTAINER_METRICS = {
    'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel'],
    'structure.mem.usage': ['proc.mem.resident']}
# GUARDIAN_CONTAINER_METRICS = {
#     'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel'],
#     'structure.mem.usage': ['proc.mem.resident'],
#     'structure.disk.usage': ['proc.disk.reads.mb'],
#     'structure.net.usage': ['proc.disk.reads.mb', 'proc.net.tcp.in.mb']}

BDWATCHDOG_APPLICATION_METRICS = ['structure.cpu.usage', 'structure.mem.usage', 'structure.energy.usage']
GUARDIAN_APPLICATION_METRICS = {
    'structure.cpu.usage': ['structure.cpu.usage'],
    'structure.mem.usage': ['structure.mem.usage'],
    'structure.energy.usage': ['structure.energy.usage']}
# GUARDIAN_APPLICATION_METRICS = {
#    'structure.cpu.usage': ['structure.cpu.usage'],
#    'structure.mem.usage': ['structure.mem.usage'],
#    'structure.disk.usage': ['structure.disk.usage'],
#    'structure.net.usage': ['structure.net.usage'],
#    'structure.energy.usage': ['structure.energy.usage']}

GUARDIAN_METRICS = {"container": GUARDIAN_CONTAINER_METRICS, "application": GUARDIAN_APPLICATION_METRICS}
BDWATCHDOG_METRICS = {"container": BDWATCHDOG_CONTAINER_METRICS, "application": BDWATCHDOG_APPLICATION_METRICS}

TAGS = {"container": "host", "application": "structure"}

translator_dict = {"cpu": "structure.cpu.usage", "mem": "structure.mem.usage", "energy": "structure.energy.usage"}
# translator_dict = {"cpu": "structure.cpu.usage", "mem": "structure.mem.usage", "energy": "structure.energy.usage",
#                   "disk": "structure.disk.usage", "net": "structure.net.usage"}

# RESOURCES = ['cpu', 'mem', 'disk', 'net', 'energy']

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10,
                         "EVENT_TIMEOUT": 40, "DEBUG": True, "STRUCTURE_GUARDED": "container"}
SERVICE_NAME = "guardian"

NOT_AVAILABLE_STRING = "n/a"
MAX_PERCENTAGE_REDUCTION_ALLOWED = 50
MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER = 1

NON_ADJUSTABLE_RESOURCES = ["energy"]
CPU_SHARES_PER_WATT = 10  # 7  # How many cpu shares to rescale per watt


class Guardian():

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchDB.CouchDBServer()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.guardable_resources = ['cpu', 'mem', 'energy']
        self.debug = True

    def check_unset_values(self, value, label):
        if value == NOT_AVAILABLE_STRING:
            raise ValueError("value for '{0}' is not set or is not available.".format(label))

    def check_invalid_values(self, value1, label1, value2, label2, resource="n/a"):
        if value1 > value2:
            raise ValueError("in resources: {0} value for '{1}': {2} is greater than value for '{3}': {4}".format(
                resource, label1, str(value1), label2, str(value2)))

    def try_get_value(self, d, key):
        try:
            return int(d[key])
        except (KeyError, ValueError):
            return NOT_AVAILABLE_STRING

    def filter_old_events(self, structure_events, event_timeout):
        valid_events = list()
        invalid_events = list()
        for event in structure_events:
            # If event is too old, remove it, otherwise keep it
            if event["timestamp"] < time.time() - event_timeout:
                invalid_events.append(event)
            else:
                valid_events.append(event)
        return valid_events, invalid_events

    def reduce_structure_events(self, structure_events):
        events_reduced = {"action": {}}
        for event in structure_events:
            resource = event["resource"]
            if resource not in events_reduced["action"]:
                events_reduced["action"][resource] = {"events": {"scale": {"down": 0, "up": 0}}}
            for key in event["action"]["events"]["scale"].keys():
                value = event["action"]["events"]["scale"][key]
                events_reduced["action"][resource]["events"]["scale"][key] += value
        return events_reduced["action"]

    def get_container_resources_str(self, resource_label, resources_dict, limits_dict, usages_dict):
        if not usages_dict or usages_dict[translator_dict[resource_label]] == self.NO_METRIC_DATA_DEFAULT_VALUE:
            usage_value_string = NOT_AVAILABLE_STRING
        else:
            usage_value_string = str("%.2f" % usages_dict[translator_dict[resource_label]])

        if not limits_dict and not usages_dict:
            return ",".join([str(self.try_get_value(resources_dict[resource_label], "max")),
                             str(self.try_get_value(resources_dict[resource_label], "current")),
                             str(self.try_get_value(resources_dict[resource_label], "fixed")),
                             str(self.try_get_value(resources_dict[resource_label], "min"))])
        else:
            return ",".join([str(self.try_get_value(resources_dict[resource_label], "max")),
                             str(self.try_get_value(resources_dict[resource_label], "current")),
                             str(self.try_get_value(limits_dict[resource_label], "upper")),
                             usage_value_string,
                             str(self.try_get_value(limits_dict[resource_label], "lower")),
                             str(self.try_get_value(resources_dict[resource_label], "min"))])

    def adjust_if_invalid_amount(self, amount, resource, structure, limits):
        if resource in NON_ADJUSTABLE_RESOURCES:
            return amount

        current_value = structure["resources"][resource]["current"] + amount
        lower_limit = limits[resource]["lower"] + amount
        max_limit = structure["resources"][resource]["max"]
        min_limit = structure["resources"][resource]["min"]

        if lower_limit < min_limit:
            # The amount to reduce is too big, adjust it so that the lower limit is
            # set to the minimum
            amount += (min_limit - lower_limit)
        elif current_value > max_limit:
            # The amount to increase is too big, adjust it so that the current limit is
            # set to the maximum
            amount -= (current_value - max_limit)

        return amount

    def get_amount_from_percentage_reduction(self, structure, usages, resource, percentage_reduction):
        current_resource_limit = structure["resources"][resource]["current"]
        current_resource_usage = usages[translator_dict[resource]]

        difference = current_resource_limit - current_resource_usage

        if percentage_reduction > MAX_PERCENTAGE_REDUCTION_ALLOWED:
            percentage_reduction = MAX_PERCENTAGE_REDUCTION_ALLOWED

        amount = int(-1 * (percentage_reduction * difference) / 100)
        return amount

    def get_amount_from_fit_reduction(self, structure, usages, resource, limits):
        current_resource_limit = structure["resources"][resource]["current"]
        upper_to_lower_window = limits[resource]["boundary"]
        current_to_upper_window = limits[resource]["boundary"]
        current_resource_usage = usages[translator_dict[resource]]

        # Set the limit so that the resource usage is placed in between the upper and lower limits
        # and keeping the boundary between the upper and the real resource limits
        desired_applied_resource_limit = \
            current_resource_usage + \
            upper_to_lower_window / 2 + \
            current_to_upper_window

        difference = current_resource_limit - desired_applied_resource_limit
        return -1 * difference

    def get_amount_from_proportional_energy_rescaling(self, structure, resource):
        max_resource_limit = structure["resources"][resource]["max"]
        current_resource_limit = structure["resources"][resource]["usage"]
        difference = max_resource_limit - current_resource_limit
        energy_aplification = CPU_SHARES_PER_WATT  # How many cpu shares to rescale per watt
        return int(difference * energy_aplification)

    def get_container_energy_str(self, resources_dict):
        return ",".join([str(self.try_get_value(resources_dict["energy"], "max")),
                         str(self.try_get_value(resources_dict["energy"], "usage")),
                         str(self.try_get_value(resources_dict["energy"], "min"))])

    def correct_container_state(self, resources, limits):
        for resource in ["cpu", "mem"]:
            current_value = self.try_get_value(resources[resource], "current")
            upper_value = self.try_get_value(limits[resource], "upper")
            lower_value = self.try_get_value(limits[resource], "lower")
            min_value = self.try_get_value(resources[resource], "min")
            boundary = limits[resource]["boundary"]

            # Can't correct this, so let it raise the exception
            # check_invalid_values(current_value, "current", max_value, "max")

            # Correct the chain current > upper > lower, including boundary between current and upper
            try:
                self.check_invalid_values(upper_value, "upper", current_value, "current", resource=resource)
                self.check_invalid_values(lower_value, "lower", upper_value, "upper", resource=resource)
                self.check_invalid_values(min_value, "min", lower_value, "lower", resource=resource)
                if current_value != NOT_AVAILABLE_STRING and current_value - boundary < upper_value:
                    raise ValueError()
                if current_value != NOT_AVAILABLE_STRING and current_value - int(
                        MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER * boundary) > upper_value:
                    raise ValueError()
            except ValueError:
                limits[resource]["upper"] = resources[resource]["current"] - boundary
                limits[resource]["lower"] = max(limits[resource]["upper"] - boundary, min_value)

        return limits

    def invalid_container_state(self, resources, limits):
        for resource in ["cpu", "mem"]:
            max_value = self.try_get_value(resources[resource], "max")
            current_value = self.try_get_value(resources[resource], "current")
            upper_value = self.try_get_value(limits[resource], "upper")
            lower_value = self.try_get_value(limits[resource], "lower")
            min_value = self.try_get_value(resources[resource], "min")
            boundary = limits[resource]["boundary"]

            # Check values are set and valid, except for current as it may have not been persisted yet
            self.check_unset_values(max_value, "max")
            self.check_unset_values(upper_value, "upper")
            self.check_unset_values(lower_value, "lower")
            self.check_unset_values(min_value, "min")

            # Check if the first value is greater than the second
            # check the full chain "max > upper > current > lower > min"
            if current_value != NOT_AVAILABLE_STRING:
                self.check_invalid_values(current_value, "current", max_value, "max")
            self.check_invalid_values(upper_value, "upper", current_value, "current", resource=resource)
            self.check_invalid_values(lower_value, "lower", upper_value, "upper", resource=resource)
            self.check_invalid_values(min_value, "min", lower_value, "lower", resource=resource)

            # Check that there is a boundary between values, like the current and upper, so
            # that the limit can be surpassed
            if current_value != NOT_AVAILABLE_STRING:
                if current_value - boundary < upper_value:
                    raise ValueError(
                        "value for 'current': {0} is too close (less than {1}) to value for 'upper': {2}".format(
                            str(current_value), str(boundary), str(upper_value)))

                elif current_value - int(MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER * boundary) > upper_value:
                    raise ValueError(
                        "value for 'current': {0} is too far (more than {1}) from value for 'upper': {2}".format(
                            str(current_value), str(
                                int(MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER * boundary)), str(upper_value)))

    def match_usages_and_limits(self, structure_name, rules, usages, limits, resources):
        events = []
        data = dict()

        for resource in self.guardable_resources:
            if resource in resources:
                data[resource] = {
                    "limits": {resource: limits[resource]},
                    "structure": {resource: resources[resource]}}

        for usage_metric in usages:
            keys = usage_metric.split(".")
            # Split the key from the retrieved data, e.g., structure.mem.usages, where mem is the resource
            data[keys[1]][keys[0]][keys[1]][keys[2]] = usages[usage_metric]

        for rule in rules:
            try:
                # Check that the rule is active, the resource to watch is guarded and that the rule is activated
                if rule["active"] and \
                        resources[rule["resource"]]["guard"] and \
                        rule["generates"] == "events" and \
                        jsonLogic(rule["rule"], data[rule["resource"]]):

                    event_name = MyUtils.generate_event_name(rule["action"]["events"], rule["resource"])
                    if event_name:
                        events.append(dict(
                            name=event_name,
                            resource=rule["resource"],
                            type="event",
                            structure=structure_name,
                            action=rule["action"],
                            timestamp=int(time.time()))
                        )
            except KeyError as e:
                MyUtils.logging_warning(
                    "rule: {0} is missing a parameter {1} {2}".format(rule["name"], str(e),
                                                                      str(traceback.format_exc())), self.debug)

        return events

    # TO BE TESTED
    def is_application(self, structure):
        return structure["subtype"] == "application"

    def is_container(self, structure):
        return structure["subtype"] == "container"

    # NOT TESTED
    def match_rules_and_events(self, structure, rules, events, limits, usages):
        generated_requests = list()
        events_to_remove = dict()
        for rule in rules:
            try:
                resource_label = rule["resource"]
                if rule["active"] and rule["generates"] == "requests" and resource_label in events and jsonLogic(
                        rule["rule"], events[resource_label]):

                    # Match, generate request

                    # If rescaling a container, check that the current resource value exists, otherwise there
                    # is nothing to rescale
                    if self.is_container(structure) and "current" not in structure["resources"][resource_label]:
                        MyUtils.logging_warning(
                            "No current value for container' {0}' and resource '{1}', can't rescale".format(
                                structure["name"], resource_label), self.debug)
                        continue

                    if "rescale_by" in rule.keys():
                        try:
                            if rule["rescale_by"] == "amount":
                                amount = rule["amount"]

                            elif rule["rescale_by"] == "percentage_reduction":
                                amount = self.get_amount_from_percentage_reduction(
                                    structure, usages, resource_label, int(rule["percentage_reduction"]))

                            elif rule["rescale_by"] == "fit_to_usage":
                                amount = self.get_amount_from_fit_reduction(structure, usages, resource_label, limits)

                            elif rule["rescale_by"] == "proportional" and rule["resource"] == "energy":
                                amount = self.get_amount_from_proportional_energy_rescaling(structure, resource_label)

                            else:
                                amount = rule["amount"]
                        except KeyError:
                            # Error because current value may not be available and it is
                            # required for methods like percentage reduction
                            MyUtils.logging_warning(
                                "error in trying to compute rescaling amount for rule '{0}' : {1}".format(
                                    rule["name"], str(traceback.format_exc())), self.debug)
                            amount = rule["amount"]
                    else:
                        amount = rule["amount"]
                        MyUtils.logging_warning(
                            "No rescale_by policy is set in rule : '{0}', falling back to default amount: {1}".format(
                                rule["name"], str(amount)), self.debug)

                    amount = self.adjust_if_invalid_amount(amount, resource_label, structure, limits)

                    request = dict(
                        type="request",
                        resource=resource_label,
                        amount=int(amount),
                        structure=structure["name"],
                        action=MyUtils.generate_request_name(amount, resource_label),
                        timestamp=int(time.time()))

                    # TODO fix if necessary as energy is not a 'real' resource but an abstraction
                    # For the moment, energy rescaling is uniquely mapped to cpu rescaling
                    if resource_label == "energy":
                        request["resource"] = "cpu"
                        request["for_energy"] = True

                    if self.is_container(structure):
                        request["host"] = structure["host"]
                        request["host_rescaler_ip"] = structure["host_rescaler_ip"]
                        request["host_rescaler_port"] = structure["host_rescaler_port"]

                    generated_requests.append(request)

                    event_name = MyUtils.generate_event_name(events[resource_label]["events"], resource_label)
                    if event_name not in events_to_remove:
                        events_to_remove[event_name] = 0

                    events_to_remove[event_name] += rule["events_to_remove"]

            except KeyError as e:
                MyUtils.logging_warning(
                    "rule: {0} is missing a parameter {1} {2} ".format(rule["name"], str(e),
                                                                       str(traceback.format_exc())),
                    self.debug)

        return generated_requests, events_to_remove

    # CAN'T OR DON'T HAVE TO BE TESTED
    # Their logic is simple and the used functions inside them are tested
    def print_debug_info(self, container, usages, limits, triggered_events, triggered_requests):
        resources = container["resources"]

        container_name_str = "@" + container["name"]
        container_guard_policy_str = "with policy: {0}".format(container["guard_policy"])
        resources_str = "cpu({0}) - mem({1}) - energy({2})".format(
            self.get_container_resources_str("cpu", resources, limits, usages),
            self.get_container_resources_str("mem", resources, limits, usages),
            self.get_container_energy_str(resources))

        ev, req = list(), list()
        for event in triggered_events:
            ev.append(event["name"])
        for request in triggered_requests:
            req.append(request["action"])
        triggered_requests_and_events = "#TRIGGERED EVENTS {0} AND TRIGGERED REQUESTS {1}".format(str(ev), str(req))
        MyUtils.logging_info(
            " ".join([container_name_str, container_guard_policy_str, resources_str, triggered_requests_and_events]),
            self.debug)

    def process_serverless_structure(self, config, structure, usages, limits, rules):
        event_timeout = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "EVENT_TIMEOUT")

        # Match usages and rules to generate events
        triggered_events = self.match_usages_and_limits(structure["name"], rules, usages, limits,
                                                        structure["resources"])

        # Remote database operation
        self.couchdb_handler.add_events(triggered_events)

        # Remote database operation
        all_events = self.couchdb_handler.get_events(structure)

        # Filter the events according to timestamp
        filtered_events, old_events = self.filter_old_events(all_events, event_timeout)

        if old_events:
            # Remote database operation
            self.couchdb_handler.delete_events(old_events)

        # If there are no events, nothing else to do as no requests will be generated
        if filtered_events:
            # Merge all the event counts
            reduced_events = self.reduce_structure_events(filtered_events)

            # Match events and rules to generate requests
            triggered_requests, events_to_remove = self.match_rules_and_events(structure, rules, reduced_events, limits,
                                                                               usages)

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
            limits = self.couchdb_handler.get_limits(structure)["resources"]
            self.print_debug_info(structure, usages, limits, triggered_events, triggered_requests)

    def serverless(self, config, structure, rules):
        window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
        window_delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")

        try:
            # Check if structure is guarded
            if "guard" not in structure or not structure["guard"]:
                return

            # Check if structure is being monitored, otherwise, ignore
            try:
                metrics_to_retrieve = BDWATCHDOG_METRICS[structure["subtype"]]
                metrics_to_generate = GUARDIAN_METRICS[structure["subtype"]]
                tag = TAGS[structure["subtype"]]
            except KeyError:
                # Default is container
                metrics_to_retrieve = BDWATCHDOG_CONTAINER_METRICS
                metrics_to_generate = GUARDIAN_CONTAINER_METRICS
                tag = "host"

            # Remote database operation
            usages = self.opentsdb_handler.get_structure_timeseries({tag: structure["name"]}, window_difference,
                                                                    window_delay,
                                                                    metrics_to_retrieve, metrics_to_generate)

            # Skip this structure if all the usage metrics are unavailable
            if all([usages[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
                MyUtils.logging_warning("structure: {0} has no usage data".format(structure["name"]), self.debug)
                return

            resources = structure["resources"]

            # Remote database operation
            limits = self.couchdb_handler.get_limits(structure)["resources"]

            if not limits:
                MyUtils.logging_warning("structure: {0} has no limits".format(structure["name"]), self.debug)
                return

            try:
                self.invalid_container_state(resources, limits)
            except ValueError as e:
                MyUtils.logging_warning(
                    "structure: {0} has invalid state with its limits and resources, will try to correct: {1}".format(
                        structure["name"], str(e)), self.debug)
                limits = self.correct_container_state(resources, limits)

                # Remote database operation
                self.couchdb_handler.update_limit(dict(resources=limits))

            self.process_serverless_structure(config, structure, usages, limits, rules)

        except Exception as e:
            MyUtils.logging_error(
                "error with structure: {0} {1} {2}".format(structure["name"], str(e), str(traceback.format_exc())),
                self.debug)

    def process_fixed_resources_structure(self, resources, structure):
        triggered_requests = list()
        for resource in resources:
            if not resources[resource]["guard"]:
                continue

            if "fixed" in structure["resources"][resource] and "current" in structure["resources"][resource]:
                fixed_value = structure["resources"][resource]["fixed"]
                current_value = structure["resources"][resource]["current"]
                if fixed_value != current_value:
                    amount = fixed_value - current_value
                    request = dict(
                        type="request",
                        resource=resource,
                        amount=int(amount),
                        structure=structure["name"],
                        action=MyUtils.generate_request_name(amount, resource),
                        timestamp=int(time.time()))

                    if self.is_container(structure):
                        request["host"] = structure["host"]
                        request["host_rescaler_ip"] = structure["host_rescaler_ip"]
                        request["host_rescaler_port"] = structure["host_rescaler_port"]

                    self.couchdb_handler.add_request(request)
                    triggered_requests.append(request)
            else:
                MyUtils.logging_warning(
                    "structure: {0} has no 'current' or 'fixed' value for resource: {1}".format(
                        structure["name"], resource), self.debug)

        # DEBUG AND INFO OUTPUT
        if self.debug:
            self.print_debug_info(structure, {}, {}, [], triggered_requests)

    def fixed_resource_amount(self, structure):
        try:
            # Check if structure is guarded
            if "guard" not in structure or not structure["guard"]:
                return

            self.process_fixed_resources_structure(structure["resources"], structure)

        except Exception as e:
            MyUtils.logging_error(
                "error with structure: {0} {1} {2}".format(structure["name"], str(e), str(traceback.format_exc())),
                self.debug)

    def guard_structures(self, config, structures):
        # Remote database operation
        rules = self.couchdb_handler.get_rules()

        for structure in structures:
            if "guard_policy" not in structure:
                # Default option will be serverless
                self.serverless(config, structure, rules)
            else:
                if structure["guard_policy"] == "serverless":
                    self.serverless(config, structure, rules)
                elif structure["guard_policy"] == "fixed":
                    self.fixed_resource_amount(structure)
                else:
                    self.serverless(config, structure, rules)

    def guard(self, ):
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
        while True:

            # Get service info
            service = MyUtils.get_service(self.couchdb_handler, SERVICE_NAME)

            # Heartbeat
            MyUtils.beat(self.couchdb_handler, SERVICE_NAME)

            # CONFIG
            config = service["config"]
            self.debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")
            window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
            structure_guarded = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "STRUCTURE_GUARDED")
            thread = None

            # Data retrieving, slow
            structures = MyUtils.get_structures(self.couchdb_handler, self.debug, subtype=structure_guarded)
            if structures:
                thread = Thread(target=self.guard_structures, args=(config, structures,))
                thread.start()

            MyUtils.logging_info(
                "Epoch processed at {0}".format(MyUtils.get_time_now_string()), self.debug)
            time.sleep(window_difference)

            if thread and thread.isAlive():
                delay_start = time.time()
                MyUtils.logging_warning(
                    "Previous thread didn't finish before next poll is due, with window time of " +
                    "{0} seconds, at {1}".format(str(window_difference), MyUtils.get_time_now_string()), self.debug)
                MyUtils.logging_warning("Going to wait until thread finishes before proceeding", self.debug)
                thread.join()
                delay_end = time.time()
                MyUtils.logging_warning("Resulting delay of: {0} seconds".format(str(delay_end - delay_start)),
                                        self.debug)


def main():
    try:
        guardian = Guardian()
        guardian.guard()
    except Exception as e:
        MyUtils.logging_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
