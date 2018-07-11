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

translator_dict = {"cpu": "structure.cpu.usage", "mem": "structure.mem.usage", "energy": "structure.energy.usage",}

RESOURCES = ['cpu', 'mem', 'disk', 'net', 'energy']
CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10,
                         "EVENT_TIMEOUT": 40, "DEBUG": True, "GUARD_POLICY": "serverless",
                         "STRUCTURE_GUARDED": "container"}
SERVICE_NAME = "guardian"
debug = True

NOT_AVAILABLE_STRING = "n/a"
MAX_PERCENTAGE_REDUCTION_ALLOWED = 50
MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER = 1.5


# TESTED

def check_unset_values(value, label):
    if value == NOT_AVAILABLE_STRING:
        raise ValueError("value for '" + label + "' is not set or is not available.")


def check_invalid_values(value1, label1, value2, label2, resource="n/a"):
    if value1 > value2:
        raise ValueError(
            "in resources: " + resource +
            " value for '" + label1 + "': " + str(value1) +
            " is greater than " +
            " value for '" + label2 + "': " + str(value2))


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

    if resource_label not in limits_dict:
        limits_dict[resource_label] = {}

    return (str(try_get_value(resources_dict[resource_label], "max")) + "," +
            str(try_get_value(resources_dict[resource_label], "current")) + "," +
            str(try_get_value(limits_dict[resource_label], "upper")) + "," +
            usage_value_string + "," +
            str(try_get_value(limits_dict[resource_label], "lower")) + "," +
            str(try_get_value(resources_dict[resource_label], "min")))


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
    upper_resource_limit = limits["resources"][resource]["upper"]
    lower_resource_limit = limits["resources"][resource]["lower"]

    upper_to_lower_window = limits["resources"][resource]["boundary"]
    current_to_upper_window = limits["resources"][resource]["boundary"]
    # upper_to_lower_window = upper_resource_limit - lower_resource_limit
    # current_to_upper_window = current_resource_limit - upper_resource_limit
    current_resource_usage = usages[translator_dict[resource]]

    # Set the limit so that the resource usage is placed in between the upper and lower limits
    # and keeping the boundary between the upper and the real resource limits
    desired_applied_resource_limit = \
        current_resource_usage + \
        upper_to_lower_window / 2 + \
        current_to_upper_window

    difference = current_resource_limit - desired_applied_resource_limit
    return -1 * difference


def get_container_energy_str(resources_dict, limits_dict):
    if "energy" not in limits_dict:
        limits_dict["energy"] = {}

    return (str(try_get_value(resources_dict["energy"], "max")) + "," +
            str(try_get_value(resources_dict["energy"], "current")) + "," +
            str(try_get_value(resources_dict["energy"], "min")))

    # return (str(try_get_value(resources_dict["energy"], "max")) + "," +
    #         str(try_get_value(limits_dict["energy"], "upper")) + "," +
    #         str(try_get_value(resources_dict["energy"], "usage")) + "," +
    #         str(try_get_value(limits_dict["energy"], "lower")) + "," +
    #         str(try_get_value(resources_dict["energy"], "min")))


def correct_container_state(resources, limits_document):
    limits = limits_document["resources"]
    for resource in ["cpu", "mem"]:
        max_value = try_get_value(resources[resource], "max")
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
                    "value for 'current': " + str(current_value) +
                    " is too close (less than " + str(boundary) + ") to " +
                    "value for 'upper': " + str(upper_value))
            elif current_value - int(MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER * boundary) > upper_value:
                raise ValueError(
                    "value for 'current': " + str(current_value) +
                    " is too far (more than " + str(
                        int(MAX_ALLOWED_DIFFERENCE_CURRENT_TO_UPPER * boundary)) + ") from " +
                    "value for 'upper': " + str(upper_value))


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
                "rule: " + rule["name"] + " is missing a parameter " + str(e) + " " + str(traceback.format_exc()),
                debug)

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
                    MyUtils.logging_warning("No current value for container' " + structure[
                        "name"] + "' and resource '" + resource_label + "', can't rescale", debug)
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

                        else:
                            amount = rule["amount"]
                    except KeyError:
                        # Error because current value may not be available and it is
                        # required for methods like percentage reduction
                        MyUtils.logging_warning(
                            "error in trying to compute rescaling amount for rule '" + rule["name"] + "' : " + str(
                                traceback.format_exc()), debug)
                        amount = rule["amount"]
                else:
                    amount = rule["amount"]
                    MyUtils.logging_warning("No rescale_by policy is set in rule : '" + rule[
                        "name"] + "', falling back to default amount: " + str(amount), debug)

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
                "rule: " + rule["name"] + " is missing a parameter " + str(e) + " " + str(traceback.format_exc()),
                debug)

    return generated_requests, events_to_remove


# CAN'T OR DON'T HAVE TO BE TESTED
# Their logic is simple and the used functions inside them are tested
def print_debug_info(container, usages, limits, triggered_events, triggered_requests):
    resources = container["resources"]

    container_name_str = "@" + container["name"]

    resources_str = "#RESOURCES: " + \
                    "cpu(" + get_container_resources_str("cpu", resources, limits, usages) + ")" + \
                    " - " + \
                    "mem(" + get_container_resources_str("mem", resources, limits, usages) + ")" + \
                    " - " + \
                    "energy(" + get_container_energy_str(resources, limits) + ")"

    ev, req = list(), list()
    for event in triggered_events:
        ev.append(event["name"])
    for request in triggered_requests:
        req.append(request["action"])

    triggered_requests_and_events = "#TRIGGERED EVENTS " + str(ev) + " AND TRIGGERED REQUESTS " + str(req)

    MyUtils.logging_info(" ".join([container_name_str, resources_str, triggered_requests_and_events]), debug)


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
        triggered_requests, events_to_remove = match_rules_and_events(structure, rules, reduced_events, limits, usages)

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


def serverless(config, structures):
    window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
    window_delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")

    # Remote database operation
    rules = db_handler.get_rules()

    for structure in structures:
        try:
            # Check if structure is guarded
            if "guard" not in structure or not structure["guard"]:
                continue

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
            usages = bdwatchdog_handler.get_structure_usages({tag: structure["name"]}, window_difference, window_delay,
                                                             metrics_to_retrieve, metrics_to_generate)

            # Skip this structure if all the usage metrics are unavailable
            if all([usages[metric] == NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
                MyUtils.logging_warning(
                    "structure: " + structure["name"] + " has no usage data", debug)
                continue

            resources = structure["resources"]

            # Remote database operation
            limits = db_handler.get_limits(structure)

            if not limits:
                MyUtils.logging_warning(
                    "structure: " + structure["name"] + " has no limits", debug)
                continue

            try:
                invalid_container_state(resources, limits)
            except ValueError as e:
                MyUtils.logging_warning(
                    "structure: " + structure[
                        "name"] + " has invalid state with its limits and resources, will try to correct: " + str(e),
                    debug)
                # str(e) + " " + str(traceback.format_exc()), debug)
                limits = correct_container_state(resources, limits)

                # Remote database operation
                db_handler.update_limit(limits)

            process_serverless_structure(config, structure, usages, limits, rules)

        except Exception as e:
            MyUtils.logging_error(
                "error with structure: " + structure["name"] + " " + str(e) + " " + str(traceback.format_exc()),
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
                "structure: " + structure["name"] + " has no 'current' or 'fixed' value for resource: " + resource, debug)

    # DEBUG AND INFO OUTPUT
    if debug:
        print_debug_info(structure, {}, {}, [], triggered_requests)

def fixed_resource_amount(structures):
    for structure in structures:
        try:
            # Check if structure is guarded
            if "guard" not in structure or not structure["guard"]:
                continue

            resources = structure["resources"]

            process_fixed_resources_structure(resources, structure)

        except Exception as e:
            MyUtils.logging_error(
                "error with structure: " + structure["name"] + " " + str(e) + " " + str(traceback.format_exc()),
                debug)


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
        benchmark = True
        guard_policy = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "GUARD_POLICY")
        structure_guarded = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "STRUCTURE_GUARDED")

        # Data retrieving, slow
        structures = MyUtils.get_structures(db_handler, debug, subtype=structure_guarded)
        if not structures:
            continue

        if guard_policy == "serverless":
            thread = Thread(target=serverless, args=(config, structures,))
        elif guard_policy == "fixed_amount":
            thread = Thread(target=fixed_resource_amount, args=(structures,))
        # Default option will be serverless
        else:
            thread = Thread(target=serverless, args=(config, structures,))

        thread.start()

        MyUtils.logging_info("Epoch processed at " + MyUtils.get_time_now_string() + " with " + guard_policy + " policy", debug)
        time.sleep(window_difference)

        if thread.isAlive():
            delay_start = time.time()
            MyUtils.logging_warning("Previous thread didn't finish before next poll is due, with window time of " + str(
                window_difference) + " seconds, at " + MyUtils.get_time_now_string(), debug)
            MyUtils.logging_warning("Going to wait until thread finishes before proceeding", debug)
            thread.join()
            delay_end = time.time()
            MyUtils.logging_warning("Resulting delay of: " + str(delay_end - delay_start) + " seconds", debug)



def main():
    try:
        guard()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()
