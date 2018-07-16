# /usr/bin/python
from __future__ import print_function

from threading import Thread

import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
from json_logic import jsonLogic
import StateDatabase.couchDB as couchDB
import StateDatabase.bdwatchdog as bdwatchdog

bdwatchdog_handler = bdwatchdog.BDWatchdog()
NO_METRIC_DATA_DEFAULT_VALUE = bdwatchdog_handler.NO_METRIC_DATA_DEFAULT_VALUE

db_handler = couchDB.CouchDBServer()

BDWATCHDOG_CONTAINER_METRICS = ['proc.cpu.user', 'proc.mem.resident', 'proc.cpu.kernel', 'proc.mem.virtual']
GUARDIAN_CONTAINER_METRICS = {
    'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel'],
    'structure.mem.usage': ['proc.mem.resident']}

BDWATCHDOG_APPLICATION_METRICS = ['structure.cpu.usage', 'structure.mem.usage', 'structure.energy.usage']
GUARDIAN_APPLICATION_METRICS = {
    'structure.cpu.usage': ['structure.cpu.usage'],
    'structure.mem.usage': ['structure.mem.usage'],
    'structure.energy.usage': ['structure.energy.usage']}

GUARDIAN_METRICS = {"container": GUARDIAN_CONTAINER_METRICS, "application": GUARDIAN_APPLICATION_METRICS}
BDWATCHDOG_METRICS = {"container": BDWATCHDOG_CONTAINER_METRICS, "application": BDWATCHDOG_APPLICATION_METRICS}

TAGS = {"container": "host", "application": "structure"}

translator_dict = {"cpu": "structure.cpu.usage", "mem": "structure.mem.usage", "energy": "structure.energy.usage"}

RESOURCES = ['cpu', 'mem', 'disk', 'net', 'energy']
CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10,
                         "EVENT_TIMEOUT": 40, "DEBUG": True, "STRUCTURE_GUARDED": "container"}
SERVICE_NAME = "guardian"
debug = True

NOT_AVAILABLE_STRING = "n/a"
MAX_PERCENTAGE_REDUCTION_ALLOWED = 50
MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER = 1.5


# TESTED

def check_unset_values(value, label):
    if value == NOT_AVAILABLE_STRING:
        raise ValueError("value for '{0}' is not set or is not available.".format(label))


def check_invalid_values(value1, label1, value2, label2, resource="n/a"):
    if value1 > value2:
        raise ValueError("in resources: {0} value for '{1}': {2} is greater than value for '{3}': {4}".format(
            resource, label1, str(value1), label2, str(value2)))


def try_get_value(d, key):
    try:
        return int(d[key])
    except KeyError:
        return NOT_AVAILABLE_STRING


def filter_old_events(structure_events, event_timeout):
    valid_events = list()
    invalid_events = list()
    for event in structure_events:
        # If event is too old, remove it, otherwise keep it
        if event["timestamp"] < time.time() - event_timeout:
            invalid_events.append(event)
        else:
            valid_events.append(event)
    return valid_events, invalid_events


def reduce_structure_events(structure_events):
    events_reduced = {"action": {}}
    for event in structure_events:
        resource = event["resource"]
        if resource not in events_reduced["action"]:
            events_reduced["action"][resource] = {"events": {"scale": {"down": 0, "up": 0}}}
        for key in event["action"]["events"]["scale"].keys():
            value = event["action"]["events"]["scale"][key]
            events_reduced["action"][resource]["events"]["scale"][key] += value
    return events_reduced["action"]


def get_container_resources_str(resource_label, resources_dict, limits_dict, usages_dict):
    if not usages_dict or usages_dict[translator_dict[resource_label]] == NO_METRIC_DATA_DEFAULT_VALUE:
        usage_value_string = NOT_AVAILABLE_STRING
    else:
        usage_value_string = str("%.2f" % usages_dict[translator_dict[resource_label]])

    if not limits_dict and not usages_dict:
        return ",".join([str(try_get_value(resources_dict[resource_label], "max")),
                         str(try_get_value(resources_dict[resource_label], "current")),
                         str(try_get_value(resources_dict[resource_label], "fixed")),
                         str(try_get_value(resources_dict[resource_label], "min"))])
    else:
        return ",".join([str(try_get_value(resources_dict[resource_label], "max")),
                     str(try_get_value(resources_dict[resource_label], "current")),
                     str(try_get_value(limits_dict[resource_label], "upper")),
                     usage_value_string,
                     str(try_get_value(limits_dict[resource_label], "lower")),
                     str(try_get_value(resources_dict[resource_label], "min"))])


def adjust_if_invalid_amount(amount, resource, structure, limits):
    # TODO special case for energy, try to fix
    if resource == "energy":
        return amount

    current_value = structure["resources"][resource]["current"] + amount
    lower_limit = limits["resources"][resource]["lower"] + amount
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


def get_amount_from_percentage_reduction(structure, usages, resource, percentage_reduction):
    current_resource_limit = structure["resources"][resource]["current"]
    current_resource_usage = usages[translator_dict[resource]]

    difference = current_resource_limit - current_resource_usage

    if percentage_reduction > MAX_PERCENTAGE_REDUCTION_ALLOWED:
        percentage_reduction = MAX_PERCENTAGE_REDUCTION_ALLOWED

    amount = int(-1 * (percentage_reduction * difference) / 100)
    return amount


def get_amount_from_fit_reduction(structure, usages, resource, limits):
    current_resource_limit = structure["resources"][resource]["current"]
    upper_to_lower_window = limits["resources"][resource]["boundary"]
    current_to_upper_window = limits["resources"][resource]["boundary"]
    current_resource_usage = usages[translator_dict[resource]]

    # Set the limit so that the resource usage is placed in between the upper and lower limits
    # and keeping the boundary between the upper and the real resource limits
    desired_applied_resource_limit = \
        current_resource_usage + \
        upper_to_lower_window / 2 + \
        current_to_upper_window

    difference = current_resource_limit - desired_applied_resource_limit
    return -1 * difference


# TODO only used for energy
def get_amount_from_proportional(structure, resource):
    max_resource_limit = structure["resources"][resource]["max"]
    current_resource_limit = structure["resources"][resource]["current"]
    difference = max_resource_limit - current_resource_limit
    energy_aplification = 10  # How many cpu shares to rescale per watt
    return difference * energy_aplification


def get_container_energy_str(resources_dict):
    return ",".join([str(try_get_value(resources_dict["energy"], "max")),
                     str(try_get_value(resources_dict["energy"], "current")),
                     str(try_get_value(resources_dict["energy"], "min"))])


def correct_container_state(resources, limits_document):
    limits = limits_document["resources"]
    for resource in ["cpu", "mem"]:
        current_value = try_get_value(resources[resource], "current")
        upper_value = try_get_value(limits[resource], "upper")
        lower_value = try_get_value(limits[resource], "lower")
        min_value = try_get_value(resources[resource], "min")
        boundary = limits[resource]["boundary"]

        # Can't correct this, so let it raise the exception
        # check_invalid_values(current_value, "current", max_value, "max")

        # Correct the chain current > upper > lower, including boundary between current and upper
        try:
            check_invalid_values(upper_value, "upper", current_value, "current", resource=resource)
            check_invalid_values(lower_value, "lower", upper_value, "upper", resource=resource)
            check_invalid_values(min_value, "min", lower_value, "lower", resource=resource)
            if current_value != NOT_AVAILABLE_STRING and current_value - boundary <= upper_value:
                raise ValueError()
            if current_value != NOT_AVAILABLE_STRING and current_value - int(
                    MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER * boundary) >= upper_value:
                raise ValueError()
        except ValueError:
            limits[resource]["upper"] = resources[resource]["current"] - boundary
            limits[resource]["lower"] = max(limits[resource]["upper"] - boundary, min_value)

    limits_document["resources"] = limits
    return limits_document


def invalid_container_state(resources, limits_document):
    limits = limits_document["resources"]
    # TODO add support for disk and net
    for resource in ["cpu", "mem"]:
        max_value = try_get_value(resources[resource], "max")
        current_value = try_get_value(resources[resource], "current")
        upper_value = try_get_value(limits[resource], "upper")
        lower_value = try_get_value(limits[resource], "lower")
        min_value = try_get_value(resources[resource], "min")
        boundary = limits[resource]["boundary"]

        # Check values are set and valid, except for current as it may have not been persisted yet
        check_unset_values(max_value, "max")
        check_unset_values(upper_value, "upper")
        check_unset_values(lower_value, "lower")
        check_unset_values(min_value, "min")

        # Check if the first value is greater than the second
        # check the full chain "max > upper > current > lower > min"
        if current_value != NOT_AVAILABLE_STRING:
            check_invalid_values(current_value, "current", max_value, "max")
        check_invalid_values(upper_value, "upper", current_value, "current", resource=resource)
        check_invalid_values(lower_value, "lower", upper_value, "upper", resource=resource)
        check_invalid_values(min_value, "min", lower_value, "lower", resource=resource)

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


def match_usages_and_limits(structure_name, rules, usages, limits, resources):
    events = []
    data = dict()

    for resource in RESOURCES:
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
                                                                  str(traceback.format_exc())), debug)

    return events


# TO BE TESTED
def is_application(structure):
    return structure["subtype"] == "application"


def is_container(structure):
    return structure["subtype"] == "container"


# NOT TESTED
def match_rules_and_events(structure, rules, events, limits, usages):
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
                if is_container(structure) and "current" not in structure["resources"][resource_label]:
                    MyUtils.logging_warning(
                        "No current value for container' {0}' and resource '{1}', can't rescale".format(
                            structure["name"], resource_label), debug)
                    continue

                if "rescale_by" in rule.keys():
                    try:
                        if rule["rescale_by"] == "amount":
                            amount = rule["amount"]

                        elif rule["rescale_by"] == "percentage_reduction":
                            amount = get_amount_from_percentage_reduction(
                                structure, usages, resource_label, int(rule["percentage_reduction"]))

                        elif rule["rescale_by"] == "fit_to_usage":
                            amount = get_amount_from_fit_reduction(structure, usages, resource_label, limits)

                        elif rule["rescale_by"] == "proportional" and rule["resource"] == "energy":
                            amount = get_amount_from_proportional(structure, resource_label)

                        else:
                            amount = rule["amount"]
                    except KeyError:
                        # Error because current value may not be available and it is
                        # required for methods like percentage reduction
                        MyUtils.logging_warning(
                            "error in trying to compute rescaling amount for rule '{0}' : {1}".format(
                                rule["name"], str(traceback.format_exc())), debug)
                        amount = rule["amount"]
                else:
                    amount = rule["amount"]
                    MyUtils.logging_warning(
                        "No rescale_by policy is set in rule : '{0}', falling back to default amount: {1}".format(
                            rule["name"], str(amount)), debug)

                amount = adjust_if_invalid_amount(amount, resource_label, structure, limits)

                request = dict(
                    type="request",
                    resource=resource_label,
                    amount=int(amount),
                    structure=structure["name"],
                    action=MyUtils.generate_request_name(amount, resource_label),
                    timestamp=int(time.time()))

                # TODO fix if necessary as energy is not a 'real' resource but an abstraction
                # For the moment, energy rescaling is mapped to cpu rescaling
                if resource_label == "energy":
                    request["resource"] = "cpu"

                if is_container(structure):
                    request["host"] = structure["host"]

                generated_requests.append(request)

                event_name = MyUtils.generate_event_name(events[resource_label]["events"], resource_label)
                if event_name not in events_to_remove:
                    events_to_remove[event_name] = 0

                events_to_remove[event_name] += rule["events_to_remove"]

        except KeyError as e:
            MyUtils.logging_warning(
                "rule: {0} is missing a parameter {1} {2} ".format(rule["name"], str(e),
                                                                   str(traceback.format_exc())),
                debug)

    return generated_requests, events_to_remove


# CAN'T OR DON'T HAVE TO BE TESTED
# Their logic is simple and the used functions inside them are tested
def print_debug_info(container, usages, limits, triggered_events, triggered_requests):
    resources = container["resources"]

    container_name_str = "@" + container["name"]
    container_guard_policy_str = "with policy: {0}".format(container["guard_policy"])
    resources_str = "cpu({0}) - mem({1}) - energy({2})".format(
        get_container_resources_str("cpu", resources, limits, usages),
        get_container_resources_str("mem", resources, limits, usages),
        get_container_energy_str(resources))

    ev, req = list(), list()
    for event in triggered_events:
        ev.append(event["name"])
    for request in triggered_requests:
        req.append(request["action"])
    triggered_requests_and_events = "#TRIGGERED EVENTS {0} AND TRIGGERED REQUESTS {1}".format(str(ev), str(req))
    MyUtils.logging_info(" ".join([container_name_str, container_guard_policy_str, resources_str, triggered_requests_and_events]), debug)


def process_serverless_structure(config, structure, usages, limits, rules):
    event_timeout = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "EVENT_TIMEOUT")

    # Match usages and rules to generate events
    triggered_events = match_usages_and_limits(structure["name"], rules, usages, limits["resources"],
                                               structure["resources"])

    # Remote database operation
    db_handler.add_events(triggered_events)

    # Remote database operation
    all_events = db_handler.get_events(structure)

    # Filter the events according to timestamp
    filtered_events, old_events = filter_old_events(all_events, event_timeout)

    if old_events:
        # Remote database operation
        db_handler.delete_events(old_events)

    # If there are no events, nothing else to do as no requests will be generated
    if filtered_events:
        # Merge all the event counts
        reduced_events = reduce_structure_events(filtered_events)

        # Match events and rules to generate requests
        triggered_requests, events_to_remove = match_rules_and_events(structure, rules, reduced_events, limits,
                                                                      usages)

        # Remove events that generated the request
        # Remote database operation
        for event in events_to_remove:
            db_handler.delete_num_events_by_structure(structure, event, events_to_remove[event])

        if triggered_requests:
            # Remote database operation
            db_handler.add_requests(triggered_requests)

    else:
        triggered_requests = list()

    # DEBUG AND INFO OUTPUT
    if debug:
        limits = db_handler.get_limits(structure)["resources"]
        print_debug_info(structure, usages, limits, triggered_events, triggered_requests)


def serverless(config, structure, rules):
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
        usages = bdwatchdog_handler.get_structure_usages({tag: structure["name"]}, window_difference,
                                                         window_delay,
                                                         metrics_to_retrieve, metrics_to_generate)

        # Skip this structure if all the usage metrics are unavailable
        if all([usages[metric] == NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
            MyUtils.logging_warning("structure: {0} has no usage data".format(structure["name"]), debug)
            return

        resources = structure["resources"]

        # Remote database operation
        limits = db_handler.get_limits(structure)

        if not limits:
            MyUtils.logging_warning("structure: {0} has no limits".format(structure["name"]), debug)
            return

        try:
            invalid_container_state(resources, limits)
        except ValueError as e:
            MyUtils.logging_warning(
                "structure: {0} has invalid state with its limits and resources, will try to correct: {1}".format(
                    structure["name"], str(e)), debug)
            limits = correct_container_state(resources, limits)

            # Remote database operation
            db_handler.update_limit(limits)

        process_serverless_structure(config, structure, usages, limits, rules)

    except Exception as e:
        MyUtils.logging_error(
            "error with structure: {0} {1} {2}".format(structure["name"], str(e), str(traceback.format_exc())),
            debug)


def process_fixed_resources_structure(resources, structure):
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

                if is_container(structure):
                    request["host"] = structure["host"]

                db_handler.add_request(request)
                triggered_requests.append(request)
        else:
            MyUtils.logging_warning(
                "structure: {0} has no 'current' or 'fixed' value for resource: {1}".format(
                    structure["name"], resource), debug)

    # DEBUG AND INFO OUTPUT
    if debug:
        print_debug_info(structure, {}, {}, [], triggered_requests)


def fixed_resource_amount(structure):
    try:
        # Check if structure is guarded
        if "guard" not in structure or not structure["guard"]:
            return

        process_fixed_resources_structure(structure["resources"], structure)

    except Exception as e:
        MyUtils.logging_error(
            "error with structure: {0} {1} {2}".format(structure["name"], str(e), str(traceback.format_exc())),
            debug)


def guard_structures(config, structures):
    for structure in structures:
        # Remote database operation
        rules = db_handler.get_rules()

        if structure["guard_policy"] == "serverless":
            serverless(config, structure, rules)
        elif structure["guard_policy"] == "fixed":
            fixed_resource_amount(structure)
        else:
            # Default option will be serverless
            serverless(config, structure, rules)


def guard():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    global debug
    while True:

        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)

        # CONFIG
        config = service["config"]
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")
        window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
        structure_guarded = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "STRUCTURE_GUARDED")
        thread = None

        # Data retrieving, slow
        structures = MyUtils.get_structures(db_handler, debug, subtype=structure_guarded)
        if structures:
            thread = Thread(target=guard_structures, args=(config, structures,))
            thread.start()

        MyUtils.logging_info(
            "Epoch processed at {0}".format(MyUtils.get_time_now_string()), debug)
        time.sleep(window_difference)

        if thread and thread.isAlive():
            delay_start = time.time()
            MyUtils.logging_warning(
                "Previous thread didn't finish before next poll is due, with window time of " +
                "{0} seconds, at {1}".format(str(window_difference), MyUtils.get_time_now_string()), debug)
            MyUtils.logging_warning("Going to wait until thread finishes before proceeding", debug)
            thread.join()
            delay_end = time.time()
            MyUtils.logging_warning("Resulting delay of: {0} seconds".format(str(delay_end - delay_start)), debug)


def main():
    try:
        guard()
    except Exception as e:
        MyUtils.logging_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
