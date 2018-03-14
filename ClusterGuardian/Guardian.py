# /usr/bin/python
from __future__ import print_function
import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
from json_logic import jsonLogic
import StateDatabase.couchDB as couchDB
import StateDatabase.bdwatchdog as bdwatchdog

monitoring_handler = bdwatchdog.BDWatchdog()
db_handler = couchDB.CouchDBServer()

BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.mem.resident', 'proc.cpu.kernel', 'proc.mem.virtual']
GUARDIAN_METRICS = {
    'proc.cpu.user': ['proc.cpu.user', 'proc.cpu.kernel'],
    'proc.mem.resident': ['proc.mem.resident']}
RESOURCES = ['cpu', 'mem', 'disk', 'net']
CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "EVENT_TIMEOUT": 40, "DEBUG": True}
SERVICE_NAME = "guardian"
debug = True
translator_dict = {"cpu": "proc.cpu.user", "mem": "proc.mem.resident"}
NO_METRIC_DATA_DEFAULT_VALUE = -1
NOT_AVAILABLE_STRING = "n/a"


def get_structure_usages(structure, window_difference, window_delay):
    usages = dict()
    subquery = list()
    for metric in BDWATCHDOG_METRICS:
        usages[metric] = NO_METRIC_DATA_DEFAULT_VALUE
        subquery.append(dict(aggregator='sum', metric=metric, tags=dict(host=structure["name"])))

    start = int(time.time() - (window_difference + window_delay))
    end = int(time.time() - window_delay)
    query = dict(start=start, end=end, queries=subquery)
    result = monitoring_handler.get_points(query)

    for metric in result:
        dps = metric["dps"]
        summatory = sum(dps.values())
        if len(dps) > 0:
            average_real = summatory / len(dps)
        else:
            average_real = 0
        usages[metric["metric"]] = average_real

    final_values = dict()

    for value in GUARDIAN_METRICS:
        final_values[value] = NO_METRIC_DATA_DEFAULT_VALUE
        for metric in GUARDIAN_METRICS[value]:
            if usages[metric] != NO_METRIC_DATA_DEFAULT_VALUE:
                final_values[value] += usages[metric]

    return final_values


def filter_and_purge_old_events(structure, event_timeout):
    structure_events = db_handler.get_events(structure)
    filtered_events = list()
    for event in structure_events:
        if event["timestamp"] < time.time() - event_timeout:
            # Event is too old, remove it
            db_handler.delete_event(event)
        else:
            # Event is not too old, keep it
            filtered_events.append(event)
    return filtered_events


def reduce_structure_events(structure_events):
    # structure_events = db.get_events(structure)
    events_reduced = {"action": {}}
    for resource in RESOURCES:
        events_reduced["action"][resource] = {"events": {"scale": {"down": 0, "up": 0}}}

    for event in structure_events:
        key = event["action"]["events"]["scale"].keys()[0]
        value = event["action"]["events"]["scale"][key]
        events_reduced["action"][event["resource"]]["events"]["scale"][key] += value
    return events_reduced["action"]


def generate_event_name(event, resource):
    final_string = "none"
    if "down" in event["scale"].keys() and event["scale"]["down"] > 0:
        final_string = resource.title() + "Underuse"
    if "up" in event["scale"].keys() and event["scale"]["up"] > 0:
        final_string = resource.title() + "Bottleneck"
    return final_string


def match_container_limits(structure, usages, resources, limits, rules):
    events = []
    data = dict()

    for resource in RESOURCES:
        data[resource] = {
            "proc": {resource: {}},
            "limits": {resource: limits["resources"][resource]},
            "structure": {resource: resources["resources"][resource]}}
    for usage_metric in usages:
        keys = usage_metric.split(".")
        data[keys[1]][keys[0]][keys[1]][keys[2]] = usages[usage_metric]

    for rule in rules:
        if rule["generates"] == "events":
            if jsonLogic(rule["rule"], data[rule["resource"]]):
                events.append(dict(
                    name=generate_event_name(rule["action"]["events"], rule["resource"]),
                    resource=rule["resource"],
                    type="event",
                    structure=structure["name"],
                    action=rule["action"],
                    timestamp=int(time.time()))
                )
    return events


def process_events(events):
    for event in events:
        db_handler.add_doc("events", event)


def process_requests(generated_requests):
    for request in generated_requests:
        db_handler.add_doc("requests", request)


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


def get_amount_from_percentage_reduction(structure, usages, resource, percentage_reduction):
    current_resource_limit = structure["resources"][resource]["current"]
    current_resource_usage = usages[translator_dict[resource]]

    difference = current_resource_limit - current_resource_usage

    if percentage_reduction > 50:
        percentage_reduction = 50  # TMP hard fix just in case

    amount = int(-1 * (percentage_reduction * difference) / 100)
    return amount


def adjust_if_invalid_amount(amount, resource, structure, limits):
    lower_limit = limits["resources"][resource]["lower"] + amount
    current = structure["resources"][resource]["current"] + amount
    max_limit = structure["resources"][resource]["max"]
    min_limit = structure["resources"][resource]["min"]

    if lower_limit < min_limit:
        # The amount to reduce is too big, adjust it so that the lower limit is
        # set to the minimum
        amount += (min_limit - lower_limit)

    if current > max_limit:
        # The amount to increase is too big, adjust it so that the upper limit is
        # set to the maximum
        amount -= (current - max_limit)

    return amount


def match_structure_events(structure, events, rules, usages, limits):
    generated_requests = list()
    for rule in rules:
        resource_label = rule["resource"]
        if rule["generates"] == "requests" and (jsonLogic(rule["rule"], events[resource_label])):
            # Check that the current resource value exists, otherwise there is nothing to rescale
            if "current" not in structure["resources"][resource_label]:
                MyUtils.logging_warning("No current value for container'" + structure[
                    "name"] + "' and resource '" + resource_label + "', can't rescale", debug)
                continue

            # Match, generate request
            if "rescale_by" in rule.keys():
                try:
                    if rule["rescale_by"] == "amount":
                        amount = rule["amount"]
                    elif rule["rescale_by"] == "percentage_reduction":
                        amount = get_amount_from_percentage_reduction(
                            structure, usages, resource_label, int(rule["percentage_reduction"]))
                    elif rule["rescale_by"] == "fit_to_usage":
                        amount = get_amount_from_fit_reduction(
                            structure, usages, resource_label, limits)
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

            generated_requests.append(dict(
                type="request",
                resource=resource_label,
                amount=amount,
                structure=structure["name"],
                action=rule["action"]["requests"][0],
                timestamp=int(time.time()))
            )
            db_handler.delete_num_events_by_structure(
                structure,
                generate_event_name(events[resource_label]["events"], resource_label), rule["events_to_remove"]
            )
    return generated_requests


def try_get_value(d, key):
    try:
        return int(d[key])
    except KeyError:
        return NOT_AVAILABLE_STRING


def print_container_status(resource_label, resources_dict, limits_dict, usages_dict):
    if usages_dict[translator_dict[resource_label]] == -1:
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


def print_debug_info(container, usages, triggered_events, triggered_requests):
    resources = container["resources"]
    limits = db_handler.get_limits(container)["resources"]

    container_name_str = "@" + container["name"]

    resources_str = "#RESOURCES: " + \
                    "cpu(" + print_container_status("cpu", resources, limits, usages) + ")" + \
                    " - " + \
                    "mem(" + print_container_status("mem", resources, limits, usages) + ")"

    ev, req = list(), list()
    for event in triggered_events:
        ev.append(event["name"])
    for request in triggered_requests:
        req.append(request["action"])

    triggered_requests_and_events = "#TRIGGERED EVENTS " + str(ev) + " AND TRIGGERED REQUESTS " + str(req)

    MyUtils.logging_info(" ".join([container_name_str, resources_str, triggered_requests_and_events]), debug)


def check_unset_values(value, label):
    if value == NOT_AVAILABLE_STRING:
        raise ValueError("value for '" + label + "' is not set or is not available.")


def check_invalid_values(value1, label1, value2, label2):
    if value1 > value2:
        raise ValueError(
            "value for '" + label1 + "': " + str(value1) +
            " is greater than " +
            "value for '" + label2 + "': " + str(value2))


def check_close_boundaries(value1, label1, value2, label2, boundary):
    if value1 - boundary <= value2:
        raise ValueError(
            "value for '" + label1 + "': " + str(value1) +
            " is too close (" + str(boundary) + ") to " +
            "value for '" + label2 + "': " + str(value2))


def check_invalid_state(container):
    resources = container["resources"]
    limits = db_handler.get_limits(container)["resources"]

    resources_boundaries = {"cpu": 15, "mem": 170}  # Better don't set multiples of steps

    for resource in ["cpu", "mem"]:
        max_value = try_get_value(resources[resource], "max")
        current_value = try_get_value(resources[resource], "current")
        upper_value = try_get_value(limits[resource], "upper")
        lower_value = try_get_value(limits[resource], "lower")
        min_value = try_get_value(resources[resource], "min")

        # Check values are set, except for current as it may have not been persisted yet
        check_unset_values(max_value, "max")
        check_unset_values(upper_value, "upper")
        check_unset_values(lower_value, "lower")
        check_unset_values(min_value, "min")

        # Check if the first value is greater than the second
        # check the full chain "max > upper > current > lower > min"
        try:
            if current_value != NOT_AVAILABLE_STRING:
                check_invalid_values(current_value, "current", max_value, "max")
            check_invalid_values(upper_value, "upper", current_value, "current")
            check_invalid_values(lower_value, "lower", upper_value, "upper")
            check_invalid_values(min_value, "min", lower_value, "lower")
        except ValueError as e:
            # An error was detected, try to correct the invalid state
            MyUtils.logging_warning(str(e) + " , I will try to correct it", debug)

            # If the current values has overflowed the maximum, what do we do oh god?
            # wait for rescale down?
            if current_value != NOT_AVAILABLE_STRING and current_value > max_value:
                raise

            # Reset the limits using the current value if available, otherwise just correct them as they are
            if current_value != NOT_AVAILABLE_STRING:
                interlimit_boundary = try_get_value(limits[resource], "boundary")
                upper_value = current_value - interlimit_boundary  # FIX OR LEAVE IT, DECIDE
                lower_value = upper_value - interlimit_boundary
            else:
                # swap
                upper_value, lower_value = lower_value, upper_value

            MyUtils.logging_warning(
                "New limits should be (upper,lower): (" + str(upper_value) + "," + str(lower_value) + ")", debug)

        # Check that there is a boundary between values, like the current and upper, so
        # that the limit can be surpassed
        try:
            if current_value != NOT_AVAILABLE_STRING:
                check_close_boundaries(current_value, "current", upper_value, "upper", resources_boundaries[resource])
        except ValueError:
            # An error was detected, try to correct the invalid state
            # utils.logging_error(str(e), debug)
            raise


def guard():
    logging.basicConfig(filename='Guardian.log', level=logging.INFO)
    global debug
    while True:

        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)

        epoch_start = time.time()

        # CONFIG
        rules = db_handler.get_rules()
        config = service["config"]
        window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
        window_delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")
        event_timeout = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "EVENT_TIMEOUT")
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")
        benchmark = False

        containers = db_handler.get_structures(subtype="container")
        for container in containers:
            try:
                check_invalid_state(container)

                usages = get_structure_usages(container, window_difference, window_delay)
                limits = db_handler.get_limits(container)
                triggered_events = match_container_limits(
                    container,
                    usages,
                    container,
                    limits,
                    rules)
                process_events(triggered_events)

                events = reduce_structure_events(filter_and_purge_old_events(container, event_timeout))
                triggered_requests = match_structure_events(
                    container,
                    events,
                    rules,
                    usages,
                    limits)
                process_requests(triggered_requests)

                # DEBUG AND INFO OUTPUT
                if debug:
                    print_debug_info(container, usages, triggered_events, triggered_requests)

            except Exception as e:
                MyUtils.logging_error(
                    "error with container: " + container["name"] + " " + str(e) + " " + str(traceback.format_exc()),
                    debug)

        epoch_end = time.time()
        processing_time = epoch_end - epoch_start

        if benchmark:
            MyUtils.logging_info("It took " + str("%.2f" % processing_time) + " seconds to process " + str(
                len(containers)) + " nodes at " + MyUtils.get_time_now_string(), debug)

        time.sleep(window_difference)


def main():
    try:
        guard()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()
