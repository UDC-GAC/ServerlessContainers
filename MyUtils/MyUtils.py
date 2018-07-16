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


def beat(db_handler, service_name):
    resilient_beat(db_handler, service_name, max_tries=5)


def get_config_value(config, default_config, key):
    try:
        return config[key]
    except KeyError:
        return default_config[key]


def logging_info(message, debug):
    logging.info(message)
    if debug:
        print("INFO: " + message)


def logging_warning(message, debug):
    logging.warning(message)
    if debug:
        print("WARN: " + message)


def logging_error(message, debug):
    logging.error(message)
    if debug:
        eprint("ERROR: " + message)


def get_time_now_string():
    return str(time.strftime("%D %H:%M:%S", time.localtime()))


def get_container_resources(container_name):
    r = requests.get("http://dante:8000/container/" + container_name, headers={'Accept': 'application/json'})
    if r.status_code == 200:
        return dict(r.json())
    else:
        r.raise_for_status()


def register_service(db_handler, service):
    try:
        existing_service = db_handler.get_service(service["name"])
        # Service is registered, remove it
        db_handler.delete_service(existing_service)
    except ValueError:
        # Service is not registered, everything is fine
        pass
    db_handler.add_service(service)


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
                logging_error(message, True)
                raise Exception(message)
            else:
                time.sleep(time_backoff_seconds)

    if not service or "config" not in service:
        message = "Fatal error, couldn't retrieve service configuration."
        logging_error(message, True)
        raise Exception(message)

    return service


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
    keys_to_copy = ["_id", "type", "host", "subtype", "name", "resources"]
    new_struct = dict()
    for key in keys_to_copy:
        new_struct[key] = structure[key]
    return new_struct


def get_resource(structure, resource):
    return structure["resources"][resource]


def update_structure(structure, db_handler, debug, max_tries=10):
    try:
        db_handler.update_structure(structure, max_tries=max_tries)
        print("Structure : " + structure["subtype"] + " -> " + structure["name"] + " updated at time: "
              + time.strftime("%D %H:%M:%S", time.localtime()))
    except requests.exceptions.HTTPError:
        logging_error("Error updating container " + structure["name"] + " " + traceback.format_exc(), debug)


def get_structures(db_handler, debug, subtype="application"):
    try:
        return db_handler.get_structures(subtype=subtype)
    except (requests.exceptions.HTTPError, ValueError):
        logging_warning("Couldn't retrieve " + subtype + " info.", debug=debug)
        return None


def generate_request_name(amount, resource):
    if amount < 0:
        return resource.title() + "RescaleDown"
    elif amount > 0:
        return resource.title() + "RescaleUp"
    else:
        return None


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
