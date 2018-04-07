# /usr/bin/python
from __future__ import print_function
import requests
import json
import time
import traceback
import logging
import StateDatabase.couchDB as couchDB
import MyUtils.MyUtils as MyUtils

db_handler = couchDB.CouchDBServer()
RESOURCES = ["cpu", "mem"]
translate_map = {
    "cpu": {"metric": "structure.cpu.current", "limit_label": "effective_cpu_limit"},
    "mem": {"metric": "structure.mem.current", "limit_label": "mem_limit"}
}
SERVICE_NAME = "structures_snapshoter"
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True}
MAX_FAIL_NUM = 5
debug = True


def generate_timeseries(container_name, resources):
    timestamp = int(time.time())

    for resource in resources:
        if resource == "disks":
            continue
        if resource == "networks":
            continue

        value = resources[resource][translate_map[resource]["limit_label"]]
        metric = translate_map[resource]["metric"]
        timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags=dict(host=container_name))

        print(json.dumps(timeseries))


def update_container_current_values(container_name, resources):
    updated_structure = db_handler.get_structure(container_name)

    for resource in resources:
        if resource == "disks":
            continue
        if resource == "networks":
            continue
        updated_structure["resources"][resource]["current"] = resources[resource][
            translate_map[resource]["limit_label"]]

    db_handler.update_structure(updated_structure)
    print("Success with container : " + str(container_name) + " at time: " + time.strftime("%D %H:%M:%S",
                                                                                           time.localtime()))


def persist_containers():
    fail_count = 0

    # Try to get the containers, if unavailable, return
    try:
        containers = db_handler.get_structures(subtype="container")
    except (requests.exceptions.HTTPError, ValueError):
        MyUtils.logging_warning("Couldn't retrieve containers info.", debug=True)
        return

    # Retrieve each container resources, persist them and store them to generate host info
    container_resources_dict = dict()
    for container in containers:
        container_name = container["name"]

        # Try to get the container resources, if unavailable, return
        try:
            resources = MyUtils.get_container_resources(container_name)
        except requests.exceptions.HTTPError as e:
            MyUtils.logging_error("Error trying to get container " +
                                  str(container_name) + " info " + str(e) + traceback.format_exc(), debug)
            continue

        try:

            # Persist by updating the Database current value and letting the DatabaseSnapshoter update the value
            update_container_current_values(container_name, resources)

            container_resources_dict[container_name] = container
            container_resources_dict[container_name]["resources"] = resources

            # Persist through time series sent to OpenTSDB
            # generate_timeseries(container_name, resources)
        except Exception:
            MyUtils.logging_error("Error " + traceback.format_exc() + " with container data of: " + str(
                container_name) + " with resources: " + str(resources), debug)
            fail_count += 1

    return container_resources_dict


def persist_hosts(container_resources_dict):
    # Try to get the containers, if unavailable, return
    try:
        hosts = db_handler.get_structures(subtype="host")
    except (requests.exceptions.HTTPError, ValueError):
        MyUtils.logging_warning("Couldn't retrieve containers info.", debug=True)
        return

    # Generate the host resource state from the containers it hosts

    # Revert the dictionary to be indexed by host
    host_containers = dict()
    for c in container_resources_dict:
        container_host = container_resources_dict[c]["host"]
        if container_host not in host_containers:
            host_containers[container_host] = list()
        host_containers[container_host].append(container_resources_dict[c])

    used_resources = dict()
    for host in hosts:
        host_name = host["name"]
        if host_name not in host_containers:
            continue
        containers = host_containers[host_name]
        used_resources[host_name] = dict()

        for resource in RESOURCES:
            used_resources[host_name][resource] = 0

        for c in containers:
            for resource in RESOURCES:
                used_resources[host_name][resource] += c["resources"][resource][translate_map[resource]["limit_label"]]

        for resource in RESOURCES:
            host["resources"][resource]["free"] = host["resources"][resource]["max"] - used_resources[host_name][
                resource]

        db_handler.update_structure(host)
        print("Success with host : " + str(host_name) + " at time: " + time.strftime("%D %H:%M:%S",
                                                                                     time.localtime()))


def persist_applications(container_resources_dict):
    # Try to get the containers, if unavailable, return
    try:
        applications = db_handler.get_structures(subtype="application")
    except (requests.exceptions.HTTPError, ValueError):
        MyUtils.logging_warning("Couldn't retrieve applications info.", debug=True)
        return

    # Generate the applications current resource values
    for app in applications:

        for resource in RESOURCES:
            app["resources"][resource]["current"] = 0

        application_containers = app["containers"]
        for c in application_containers:
            for resource in RESOURCES:
                app["resources"][resource]["current"] += container_resources_dict[c]["resources"][resource][
                    translate_map[resource]["limit_label"]]

        db_handler.update_structure(app)
        print("Success with app : " + str(app["name"]) + " at time: " + time.strftime("%D %H:%M:%S",
                                                                                      time.localtime()))


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

        container_resources_dict = persist_containers()
        persist_applications(container_resources_dict)
        persist_hosts(container_resources_dict)

        time.sleep(polling_frequency)


def main():
    try:
        persist()
    except Exception:
        MyUtils.logging_error("Error " + traceback.format_exc(), debug=True)


if __name__ == "__main__":
    main()
