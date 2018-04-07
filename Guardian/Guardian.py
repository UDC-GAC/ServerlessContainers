# /usr/bin/python
from __future__ import print_function
import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
import requests
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

BDWATCHDOG_APPLICATION_METRICS = ['structure.cpu.usage', 'structure.mem.usage']
GUARDIAN_APPLICATION_METRICS = {
    'structure.cpu.usage': ['structure.cpu.usage'],
    'structure.mem.usage': ['structure.mem.usage']}

GUARDIAN_METRICS = {"container": GUARDIAN_CONTAINER_METRICS, "application": GUARDIAN_APPLICATION_METRICS}
BDWATCHDOG_METRICS = {"container": BDWATCHDOG_CONTAINER_METRICS, "application": BDWATCHDOG_APPLICATION_METRICS}

TAGS = {"container": "host", "application": "structure"}

translator_dict = {"cpu": "structure.cpu.usage", "mem": "structure.mem.usage"}

RESOURCES = ['cpu', 'mem', 'disk', 'net', 'energy']
CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10,
                         "EVENT_TIMEOUT": 40, "DEBUG": True, "GUARD_POLICY": "serverless",
                         "STRUCTURE_GUARDED": "container"}
SERVICE_NAME = "guardian"
debug = True

NOT_AVAILABLE_STRING = "n/a"
MAX_PERCENTAGE_REDUCTION_ALLOWED = 50


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


def generate_event_name(event, resource):
    final_string = None

    if "scale" not in event:
        raise ValueError("Missing 'scale' key")

    if "up" not in event["scale"] and "down" not in event["scale"]:
        raise ValueError("Must have an 'up' or 'down count")

    elif "up" in event["scale"] and event["scale"]["up"] > 0 \
            and "down" in event["scale"] and event["scale"]["down"] > 0:
        # SPECIAL CASE OF HEAVY HYSTERESIS
        # raise ValueError("HYSTERESIS detected -> Can't have both up and down counts")
        return None

    elif "down" in event["scale"] and event["scale"]["down"] > 0:
        final_string = resource.title() + "Underuse"

    elif "up" in event["scale"] and event["scale"]["up"] > 0:
        final_string = resource.title() + "Bottleneck"

    return final_string


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
    if usages_dict[translator_dict[resource_label]] == NO_METRIC_DATA_DEFAULT_VALUE:
        usage_value_string = NOT_AVAILABLE_STRING
    else:
        usage_value_string = str("%.2f" % usages_dict[translator_dict[resource_label]])

    return \
        (str(try_get_value(resources_dict[resource_label], "max")) + "," +
         str(try_get_value(resources_dict[resource_label], "current")) + "," +
         str(try_get_value(limits_dict[resource_label], "upper")) + "," +
         usage_value_string + "," +
         str(try_get_value(limits_dict[resource_label], "lower")) + "," +
         str(try_get_value(resources_dict[resource_label], "min")))


def adjust_if_invalid_amount(amount, resource, structure, limits):
    upper_limit = limits["resources"][resource]["upper"] + amount
    lower_limit = limits["resources"][resource]["lower"] + amount
    max_limit = structure["resources"][resource]["max"]
    min_limit = structure["resources"][resource]["min"]

    if lower_limit < min_limit:
        # The amount to reduce is too big, adjust it so that the lower limit is
        # set to the minimum
        amount += (min_limit - lower_limit)
    elif upper_limit > max_limit:
        # The amount to increase is too big, adjust it so that the upper limit is
        # set to the maximum
        amount -= (upper_limit - max_limit)

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

    upper_to_lower_window = upper_resource_limit - lower_resource_limit
    current_to_upper_window = current_resource_limit - upper_resource_limit
    current_resource_usage = usages[translator_dict[resource]]

    # Set the limit so that the resource usage is placed in between the upper and lower limits
    # and keeping the boundary between the upper and the real resource limits
    desired_applied_resource_limit = \
        current_resource_usage + \
        upper_to_lower_window / 2 + \
        current_to_upper_window

    difference = current_resource_limit - desired_applied_resource_limit

    amount = -1 * difference
    return amount


def get_container_energy_str(resources_dict, limits_dict):
    return \
        (str(try_get_value(resources_dict["energy"], "max")) + "," +
         str(try_get_value(limits_dict["energy"], "upper")) + "," +
         str(try_get_value(resources_dict["energy"], "current")) + "," +
         str(try_get_value(limits_dict["energy"], "lower")) + "," +
         str(try_get_value(resources_dict["energy"], "min")))


def invalid_container_state(resources, limits, resources_boundaries):
    try:
        for resource in ["cpu", "mem"]:
            max_value = try_get_value(resources[resource], "max")
            current_value = try_get_value(resources[resource], "current")
            upper_value = try_get_value(limits[resource], "upper")
            lower_value = try_get_value(limits[resource], "lower")
            min_value = try_get_value(resources[resource], "min")

            # Check values are set and valid, except for current as it may have not been persisted yet
            check_unset_values(max_value, "max")
            check_unset_values(upper_value, "upper")
            check_unset_values(lower_value, "lower")
            check_unset_values(min_value, "min")

            # Check if the first value is greater than the second
            # check the full chain "max > upper > current > lower > min"
            if current_value != NOT_AVAILABLE_STRING:
                # FIXME current should never be higher than max but it is for some odd reason
                # so this check is temporally disabled so as to allow the rescaling process to take the resource
                # down
                pass
                #check_invalid_values(current_value, "current", max_value, "max")
            check_invalid_values(upper_value, "upper", current_value, "current", resource=resource)
            check_invalid_values(lower_value, "lower", upper_value, "upper", resource=resource)
            check_invalid_values(min_value, "min", lower_value, "lower", resource=resource)

            # Check that there is a boundary between values, like the current and upper, so
            # that the limit can be surpassed
            if current_value != NOT_AVAILABLE_STRING:
                if current_value - resources_boundaries[resource] <= upper_value:
                    # return True
                    raise ValueError(
                        "value for 'current': " + str(current_value) +
                        " is too close (" + str(resources_boundaries[resource]) + ") to " +
                        "value for 'upper': " + str(upper_value))
    except ValueError:
        # return True
        raise


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
            if rule["active"] and rule["generates"] == "events" and jsonLogic(rule["rule"], data[rule["resource"]]):
                # FIXME
                event_name = generate_event_name(rule["action"]["events"], rule["resource"])
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

                if is_container(structure) and "current" not in structure["resources"][resource_label]:
                    # If rescaling a container, check that the current resource value exists,
                    # otherwise there is nothing to rescale

                    MyUtils.logging_warning("No current value for container'" + structure[
                        "name"] + "' and resource '" + resource_label + "', can't rescale", debug)
                    continue
                elif is_application(structure) and "rescale_by" in rule.keys() and rule["rescale_by"] != "amount":
                    # Only rescale by amount is allowed for application rescaling, for now
                    rule["rescale_by"] = "amount"
                    MyUtils.logging_warning(
                        "application rescaling only allows rescaling by 'amount' policy, coercing to it.", debug)

                # Match, generate request
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
                    amount=amount,
                    structure=structure["name"],
                    action=rule["action"]["requests"][0],
                    timestamp=int(time.time()))

                # TODO FIX ME Should the host be specified by the guardian or retrieved by the scaler
                if is_container(structure):
                    request["host"] = structure["host"]

                generated_requests.append(request)

                event_name = generate_event_name(events[resource_label]["events"], resource_label)
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
def print_debug_info(container, usages, triggered_events, triggered_requests):
    resources = container["resources"]
    limits = db_handler.get_limits(container)["resources"]

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

    # Create events, data movement, slow
    db_handler.add_events(triggered_events)

    # Get all the events, data movement, slow
    all_events = db_handler.get_events(structure)

    # Filter the events according to timestamp
    filtered_events, old_events = filter_old_events(all_events, event_timeout)

    # Remove the old events, data movement, slow
    db_handler.delete_events(old_events)

    # If there are no events, nothing else to do as no requests will be generated
    if filtered_events:
        # Merge all the event counts
        reduced_events = reduce_structure_events(filtered_events)

        # Match events and rules to generate requests
        triggered_requests, events_to_remove = match_rules_and_events(structure, rules, reduced_events, limits, usages)

        # Remove events that generated the request, data movement, slow
        for event in events_to_remove:
            db_handler.delete_num_events_by_structure(structure, event, events_to_remove[event])

        # Create requests, data movement, slow
        db_handler.add_requests(triggered_requests)
    else:
        triggered_requests = list()

    # DEBUG AND INFO OUTPUT
    if debug:
        print_debug_info(structure, usages, triggered_events, triggered_requests)


def serverless(config, structures):
    window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
    window_delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")
    rules = db_handler.get_rules()

    for structure in structures:
        try:
            resources = structure["resources"]

            # Data retrieving, slow
            limits = db_handler.get_limits(structure)

            if not limits:
                MyUtils.logging_warning(
                    "structure: " + structure["name"] + " has no limits", debug)
                continue

            resources_boundaries = {"cpu": 15, "mem": 170}  # Better don't set multiples of steps
            try:
                invalid_container_state(resources, limits["resources"], resources_boundaries)
            except ValueError as e:
                MyUtils.logging_warning(
                    "structure: " + structure["name"] + " has invalid state with its limits and resources" + str(
                        e) + " " + str(traceback.format_exc()), debug)
                continue

            # Data retrieving, slow
            try:
                metrics_to_retrieve = BDWATCHDOG_METRICS[structure["subtype"]]
                metrics_to_generate = GUARDIAN_METRICS[structure["subtype"]]
                tag = TAGS[structure["subtype"]]
            except KeyError:
                # Default is container
                metrics_to_retrieve = BDWATCHDOG_CONTAINER_METRICS
                metrics_to_generate = GUARDIAN_CONTAINER_METRICS
                tag = "host"

            usages = bdwatchdog_handler.get_structure_usages({tag: structure["name"]}, window_difference, window_delay,
                                                             metrics_to_retrieve, metrics_to_generate)

            process_serverless_structure(config, structure, usages, limits, rules)

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
        benchmark = False
        guard_policy = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "GUARD_POLICY")
        structure_guarded = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "STRUCTURE_GUARDED")

        # Data retrieving, slow
        try:
            structures = db_handler.get_structures(subtype=structure_guarded)
        except (requests.exceptions.HTTPError, ValueError):
            MyUtils.logging_warning("Couldn't retrieve containers info.", debug=True)
            continue
        # Process and measure time
        epoch_start = time.time()

        if guard_policy == "serverless":
            serverless(config, structures)
        # Default option will be serverless
        else:
            serverless(config, structures)

        epoch_end = time.time()
        processing_time = epoch_end - epoch_start

        if benchmark:
            MyUtils.logging_info("It took " + str("%.2f" % processing_time) + " seconds to process " + str(
                len(structures)) + " nodes at " + MyUtils.get_time_now_string(), debug)

        time.sleep(window_difference)


def main():
    try:
        guard()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()
