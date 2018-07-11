# /usr/bin/python
from __future__ import print_function

from threading import Thread

import requests
import json
import time
import traceback
import logging
import StateDatabase.couchDB as couchDB
import MyUtils.MyUtils as MyUtils

db_handler = couchDB.CouchDBServer()
RESOURCES = ["cpu", "mem", "net", "disk"]
translate_map = {
    "cpu": {"metric": "structure.cpu.current", "limit_label": "effective_cpu_limit"},
    "mem": {"metric": "structure.mem.current", "limit_label": "mem_limit"},
    "disk": {"metric": "structure.disk.current", "limit_label": "disk_read_limit"},  # FIXME missing write value
    "net": {"metric": "structure.net.current", "limit_label": "net_limit"}
}
SERVICE_NAME = "structures_snapshoter"
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True}
MAX_FAIL_NUM = 5
debug = True


def generate_timeseries(container_name, resources):
    timestamp = int(time.time())

    for resource in RESOURCES:
        value = resources[resource][translate_map[resource]["limit_label"]]
        metric = translate_map[resource]["metric"]
        timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags=dict(host=container_name))

        print(json.dumps(timeseries))


def update_container_current_values(container_name, resources):
    database_structure = db_handler.get_structure(container_name)
    new_structure = MyUtils.copy_structure_base(database_structure)

    for resource in RESOURCES:
        if resource not in new_structure:
            new_structure["resources"][resource] = dict()

        #TODO FIX disk limit is retrieved in bytes/s but it is expected in Mbits
        if resource is "disk":
            bandwidth = resources[resource][translate_map[resource]["limit_label"]]
            bandwidth = int( bandwidth / 1048576)
            new_structure["resources"][resource]["current"] = bandwidth
        else:
            new_structure["resources"][resource]["current"] = resources[resource][translate_map[resource]["limit_label"]]

    MyUtils.update_structure(new_structure, db_handler, debug, max_tries=1)



def thread_persist_container(container, container_resources_dict):
    container_name = container["name"]

    # Try to get the container resources, if unavailable, continue with others
    try:
        resources = MyUtils.get_container_resources(container_name)
    except requests.exceptions.HTTPError as e:
        MyUtils.logging_error("Error trying to get container " +
                              str(container_name) + " info " + str(e) + traceback.format_exc(), debug)
        return

    # Persist by updating the Database current value
    update_container_current_values(container_name, resources)

    # Add the container info to the container info cache
    container_resources_dict[container_name] = container
    container_resources_dict[container_name]["resources"] = resources

    # Persist through time series sent to OpenTSDB
    # generate_timeseries(container_name, resources)

def persist_containers():
    # Try to get the containers, if unavailable, return
    containers = MyUtils.get_structures(db_handler, debug, subtype="container")
    if not containers:
        return

    # Retrieve each container resources, persist them and store them to generate host info
    container_resources_dict = dict()
    threads = []
    for container in containers:
        process = Thread(target=thread_persist_container, args=(container, container_resources_dict,))
        process.start()
        threads.append(process)

    for process in threads:
        process.join()

    return container_resources_dict



# def persist_containers():
#     # Try to get the containers, if unavailable, return
#     containers = MyUtils.get_structures(db_handler, debug, subtype="container")
#     if not containers:
#         return
#
#     # Retrieve each container resources, persist them and store them to generate host info
#     container_resources_dict = dict()
#     for container in containers:
#         container_name = container["name"]
#
#         # Try to get the container resources, if unavailable, continue with others
#         try:
#             resources = MyUtils.get_container_resources(container_name)
#         except requests.exceptions.HTTPError as e:
#             MyUtils.logging_error("Error trying to get container " +
#                                   str(container_name) + " info " + str(e) + traceback.format_exc(), debug)
#             continue
#
#         # Persist by updating the Database current value
#         update_container_current_values(container_name, resources)
#
#         # Add the container info to the container info cache
#         container_resources_dict[container_name] = container
#         container_resources_dict[container_name]["resources"] = resources
#
#         # Persist through time series sent to OpenTSDB
#         # generate_timeseries(container_name, resources)
#
#     return container_resources_dict


def persist_applications(container_resources_dict):
    # Try to get the applications, if unavailable, return
    applications = MyUtils.get_structures(db_handler, debug, subtype="application")
    if not applications:
        return

    # Generate the applications current resource values
    for app in applications:
        for resource in RESOURCES:
            app["resources"][resource]["current"] = 0

        application_containers = app["containers"]
        for c in application_containers:
            for resource in RESOURCES:
                if c in container_resources_dict:

                    app["resources"][resource]["current"] += \
                        container_resources_dict[c]["resources"][resource][translate_map[resource]["limit_label"]]
                else:
                    if "name" in c and "name" in app:
                        MyUtils.logging_error(
                            "Container info " + c["name"] + "is missing for app : " +
                            app["name"] + ", app info will not be accurate", debug)
                    else:
                        MyUtils.logging_error("Error with app or container info", debug)
                        #TODO this error should be more self-explanatory

        MyUtils.update_structure(app, db_handler, debug)


def persist_thread():
    # Process and measure time
    epoch_start = time.time()

    container_resources_dict = persist_containers()
    persist_applications(container_resources_dict)

    epoch_end = time.time()
    processing_time = epoch_end - epoch_start

    MyUtils.logging_info("It took " + str("%.2f" % processing_time) + " seconds to snapshot structures", debug)



def persist():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

    global debug
    while True:
        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)

        # CONFIG
        config = service["config"]
        polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

        thread = Thread(target=persist_thread, args=())
        thread.start()

        MyUtils.logging_info("Structures snapshoted at " + MyUtils.get_time_now_string(), debug)
        time.sleep(polling_frequency)

        if thread.isAlive():
            delay_start = time.time()
            MyUtils.logging_warning("Previous thread didn't finish before next poll is due, with polling time of " + str(
                polling_frequency) + " seconds, at " + MyUtils.get_time_now_string(), debug)
            MyUtils.logging_warning("Going to wait until thread finishes before proceeding", debug)
            thread.join()
            delay_end = time.time()
            MyUtils.logging_warning("Resulting delay of: " + str(delay_end - delay_start) + " seconds", debug)


def main():
    try:
        persist()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()
