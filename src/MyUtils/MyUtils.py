# /usr/bin/python
from __future__ import print_function

import random
import time
import logging
import sys
import requests
import traceback


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


# DON'T NEED TO TEST
def resilient_beat(db_handler, service_name, max_tries=10):
    try:
        service = db_handler.get_service(service_name)
        service["heartbeat_human"] = time.strftime("%D %H:%M:%S", time.localtime())
        service["heartbeat"] = time.time()
        db_handler.update_service(service)
    except requests.HTTPError as e:
        if max_tries > 0:
            time.sleep((1000 + random.randint(1, 200)) / 1000)
            resilient_beat(db_handler, service_name, max_tries - 1)
        else:
            raise e


# DON'T NEED TO TEST
def beat(db_handler, service_name):
    resilient_beat(db_handler, service_name, max_tries=5)


# DON'T NEED TO TEST
def get_config_value(config, default_config, key):
    try:
        return config[key]
    except KeyError:
        return default_config[key]


# DON'T NEED TO TEST
def log_info(message, debug):
    logging.info(message)
    if debug:
        print("INFO: " + message)


# DON'T NEED TO TEST
def log_warning(message, debug):
    logging.warning(message)
    if debug:
        print("WARN: " + message)


# DON'T NEED TO TEST
def log_error(message, debug):
    logging.error(message)
    if debug:
        eprint("ERROR: " + message)


# DON'T NEED TO TEST
def get_time_now_string():
    return str(time.strftime("%D %H:%M:%S", time.localtime()))


def get_host_containers(container_host_ip, container_host_port, rescaler_http_session, debug):
    try:
        full_address = "http://{0}:{1}/container/".format(container_host_ip, container_host_port)
        r = rescaler_http_session.get(full_address, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            return dict(r.json())
        else:
            r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        log_error(
            "Error trying to get container info {0} {1}".format(str(e), traceback.format_exc()),
            debug)
        return None




# CAN'T TEST
def get_container_resources(container, rescaler_http_session, debug):
    container_name = container["name"]
    try:
        container_host_ip = container["host_rescaler_ip"]
        container_host_port = container["host_rescaler_port"]

        full_address = "http://{0}:{1}/container/{2}".format(container_host_ip, container_host_port, container_name)
        r = rescaler_http_session.get(full_address, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            return dict(r.json())
        else:
            r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        log_error(
            "Error trying to get container {0} info {1} {2}".format(container_name, str(e), traceback.format_exc()),
            debug)
        return None


# CAN'T TEST
def register_service(db_handler, service):
    try:
        existing_service = db_handler.get_service(service["name"])
        # Service is registered, remove it
        db_handler.delete_service(existing_service)
    except ValueError:
        # Service is not registered, everything is fine
        pass
    db_handler.add_service(service)


# CAN'T TEST
def get_service(db_handler, service_name, max_allowed_failures=10, time_backoff_seconds=2):
    fails = 0
    success = False
    service = None
    # Get service info
    while not success:
        try:
            service = db_handler.get_service(service_name)
            success = True
        except (requests.exceptions.HTTPError, ValueError):
            # An error might have been thrown because database was recently updated or created
            # try again up to a maximum number of retries
            fails += 1
            if fails >= max_allowed_failures:
                message = "Fatal error, couldn't retrieve service."
                log_error(message, True)
                raise Exception(message)
            else:
                time.sleep(time_backoff_seconds)

    if not service or "config" not in service:
        message = "Fatal error, couldn't retrieve service configuration."
        log_error(message, True)
        raise Exception(message)

    return service


# TESTED
# Tranlsate something like '2-5,7' to [2,3,4,7]
def get_cpu_list(cpu_num_string):
    cpu_list = list()
    parts = cpu_num_string.split(",")
    for part in parts:
        ranges = part.split("-")
        if len(ranges) == 1:
            # Single core, no range (e.g., '5')
            cpu_list.append(ranges[0])
        else:
            # Range (e.g., '4-7' -> 4,5,6)
            cpu_list += range(int(ranges[0]), int(ranges[-1]) + 1)
    return [str(i) for i in cpu_list]


def copy_structure_base(structure):
    keys_to_copy = ["_id", "type", "subtype", "name"]
    # TODO FIX, some structures types have specific fields, fix accordingly
    if structure["subtype"] is "container":
        keys_to_copy.append("host")
    new_struct = dict()
    for key in keys_to_copy:
        new_struct[key] = structure[key]
    return new_struct


# DON'T NEED TO TEST
def get_resource(structure, resource):
    return structure["resources"][resource]


# CAN'T TEST
def update_structure(structure, db_handler, debug, max_tries=10):
    try:
        db_handler.update_structure(structure, max_tries=max_tries)
        print("Structure : " + structure["subtype"] + " -> " + structure["name"] + " updated at time: "
              + time.strftime("%D %H:%M:%S", time.localtime()))
    except requests.exceptions.HTTPError:
        log_error("Error updating container " + structure["name"] + " " + traceback.format_exc(), debug)


# CAN'T TEST
def get_structures(db_handler, debug, subtype="application"):
    try:
        return db_handler.get_structures(subtype=subtype)
    except (requests.exceptions.HTTPError, ValueError):
        log_warning("Couldn't retrieve " + subtype + " info.", debug=debug)
        return None


# TESTED
def generate_request_name(amount, resource):
    if not amount:
        raise ValueError()
    if int(amount) < 0:
        return resource.title() + "RescaleDown"
    elif int(amount) > 0:
        return resource.title() + "RescaleUp"
    else:
        raise ValueError()


# TESTED
def generate_event_name(event, resource):
    if "scale" not in event:
        raise ValueError("Missing 'scale' key")

    if "up" not in event["scale"] and "down" not in event["scale"]:
        raise ValueError("Must have an 'up' or 'down count")

    elif "up" in event["scale"] and event["scale"]["up"] > 0 \
            and "down" in event["scale"] and event["scale"]["down"] > 0:
        # SPECIAL CASE OF HEAVY HYSTERESIS
        # raise ValueError("HYSTERESIS detected -> Can't have both up and down counts")
        if event["scale"]["up"] > event["scale"]["down"]:
            final_string = resource.title() + "Bottleneck"
        else:
            final_string = resource.title() + "Underuse"

    elif "down" in event["scale"] and event["scale"]["down"] > 0:
        final_string = resource.title() + "Underuse"

    elif "up" in event["scale"] and event["scale"]["up"] > 0:
        final_string = resource.title() + "Bottleneck"
    else:
        raise ValueError("Error generating event name")

    return final_string
