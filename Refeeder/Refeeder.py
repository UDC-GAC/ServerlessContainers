# /usr/bin/python
from __future__ import print_function
import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
import requests
import StateDatabase.couchDB as couchDB
import StateDatabase.bdwatchdog
import json

bdwatchdog = StateDatabase.bdwatchdog.BDWatchdog()
NO_METRIC_DATA_DEFAULT_VALUE = bdwatchdog.NO_METRIC_DATA_DEFAULT_VALUE
db_handler = couchDB.CouchDBServer()

BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.cpu.kernel', 'proc.mem.resident']
GUARDIAN_METRICS = {'proc.cpu.user': ['proc.cpu.user', 'proc.cpu.kernel'], 'proc.mem.resident': ['proc.mem.resident']}

BDWATCHDOG_ENERGY_METRICS = ['sys.cpu.user', 'sys.cpu.kernel', 'sys.cpu.energy']
ANALYZER_ENERGY_METRICS = {'cpu': ['sys.cpu.user', 'sys.cpu.kernel'],
                           'energy': ['sys.cpu.energy']}

ANALYZER_APPLICATION_METRICS = {'cpu': ['proc.cpu.user', 'proc.cpu.kernel'], 'mem': ['proc.mem.resident']}

RESOURCES = ['cpu']
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "DEBUG": True}
SERVICE_NAME = "refeeder"
debug = True
NOT_AVAILABLE_STRING = "n/a"

CONTAINER_ENERGY_METRIC = "structure.energy.current"

window_difference = 10
window_delay = 10
host_info_cache = dict()


def merge(output, input):
    for key in input:
        if key in output:
            output[key] = output[key] + input[key]
        else:
            output[key] = input[key]
    return output


def update_structure(structure):
    fail_count = 0
    MAX_FAILS = 3
    TIME_BACKOFF = 2  # seconds
    while fail_count < MAX_FAILS:
        try:
            db_handler.update_structure(structure)
            print("Structure : " + structure["subtype"] + " -> " + structure["name"] + " updated at time: "
                  + time.strftime("%D %H:%M:%S", time.localtime()))
            break
        except requests.exceptions.HTTPError as e:
            # FIX TODO probably tried to update a document that has already been updated by other service
            # since it was retrieved, silence it
            # MyUtils.logging_error("Error " + str(e) + " " + str(traceback.format_exc()), debug)
            fail_count += 1
            time.sleep(TIME_BACKOFF)


def generate_container_energy_metrics(container, host_info):
    global window_difference
    global window_delay
    container_name = container["name"]
    host_name = container["host"]

    if host_info["cpu"] == NO_METRIC_DATA_DEFAULT_VALUE or host_info["energy"] == NO_METRIC_DATA_DEFAULT_VALUE:
        MyUtils.logging_error(
            "Error, no host info available for: " + host_name
            + " so no info can be generated for container: " + container_name, debug)
        return container

    container_info = get_container_info(container_name)

    if container_info["cpu"] == NO_METRIC_DATA_DEFAULT_VALUE:
        MyUtils.logging_error("Error, no container info available for: " + container_name, debug)
        return container

    if "energy" not in container["resources"]:
        container["resources"]["energy"] = dict()

    container["resources"]["energy"]["current"] = float(
        host_info["energy"] * (container_info["cpu"] / host_info["cpu"]))
    return container


def get_host_info(host_name):
    global host_info_cache
    global window_difference
    global window_delay
    if host_name in host_info_cache:
        # Get data from cache
        host_info = host_info_cache[host_name]
    else:
        # Data retrieving, slow
        host_info = bdwatchdog.get_structure_usages({"host":host_name}, window_difference,
                                                    window_delay, BDWATCHDOG_ENERGY_METRICS,
                                                    ANALYZER_ENERGY_METRICS)
        host_info_cache[host_name] = host_info
    return host_info


def refeed_containers(containers):
    updated_containers = list()
    for container in containers:
        host_name = container["host"]
        host_info = get_host_info(host_name)
        container = generate_container_energy_metrics(container, host_info)
        update_structure(container)
        updated_containers.append(container)
    return updated_containers


def get_container_info(container_name):
    global window_difference
    global window_delay
    container_info = bdwatchdog.get_structure_usages({"host":container_name}, window_difference, window_delay,
                                                     BDWATCHDOG_METRICS, ANALYZER_APPLICATION_METRICS)
    return container_info


def generate_application_energy_metrics(application, updated_containers):
    total_energy = 0
    for c in updated_containers:
        # Check if container is used for this application and if it has energy information
        if c["name"] in application["containers"] and "energy" in c["resources"] and "current" in c["resources"][
            "energy"]:
            total_energy += c["resources"]["energy"]["current"]
    if "energy" not in application["resources"]:
        application["resources"]["energy"] = dict()

    application["resources"]["energy"]["usage"] = total_energy
    return application


def generate_application_metrics(application):
    global window_difference
    global window_delay
    application_info = dict()
    for c in application["containers"]:
        container_info = get_container_info(c)
        application_info = merge(application_info, container_info)

    for resource in application_info:
        application["resources"][resource]["usage"] = application_info[resource]

    return application


def refeed_applications(applications, updated_containers):
    for application in applications:
        application = generate_application_metrics(application)
        application = generate_application_energy_metrics(application, updated_containers)
        update_structure(application)


def refeed():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    global debug
    global host_info_cache
    global window_difference
    global window_delay
    while True:
        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)

        # CONFIG
        config = service["config"]
        window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
        window_delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")
        polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

        # Data retrieving, slow
        try:
            host_info_cache = dict()
            containers = db_handler.get_structures(subtype="container")
            containers = refeed_containers(containers)
        except (requests.exceptions.HTTPError, ValueError):
            MyUtils.logging_warning("Couldn't retrieve containers info.", debug=True)
            # As no container info is available, no application information will be able to be generated
            continue

        try:
            applications = db_handler.get_structures(subtype="application")
            refeed_applications(applications, containers)
        except (requests.exceptions.HTTPError, ValueError):
            MyUtils.logging_warning("Couldn't retrieve applications info.", debug=True)

        time.sleep(polling_frequency)


def main():
    try:
        refeed()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()
