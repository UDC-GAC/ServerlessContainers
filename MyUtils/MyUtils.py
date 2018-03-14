# /usr/bin/python
from __future__ import print_function
import time
import logging
import sys
import requests


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def beat(db_handler, service_name):
    service = db_handler.get_service(service_name)
    service["heartbeat_human"] = time.strftime("%D %H:%M:%S", time.localtime())
    service["heartbeat"] = time.time()
    db_handler.update_doc("services", service)


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
        return None


def get_service(db_handler, service_name):
    # Get service info
    service = None
    try:
        service = db_handler.get_service(service_name)
    except (requests.exceptions.HTTPError, ValueError):
        # An error might have been thrown because database was recently updated or created
        logging_error("Fatal error, couldn't retrieve service.", True)
        exit(1)

    if "config" not in service:
        logging_error("Fatal error, couldn't retrieve service configuration.", True)
        exit(1)

    return service
