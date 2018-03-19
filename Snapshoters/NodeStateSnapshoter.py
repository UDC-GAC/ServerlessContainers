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
translate_map = {
    "cpu": {"metric": "structure.cpu.current", "limit_label": "effective_cpu_limit"},
    "mem": {"metric": "structure.mem.current", "limit_label": "mem_limit"}
}
SERVICE_NAME = "node_state_snapshoter"
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


def persist():
    logging.basicConfig(filename='DatabaseSnapshoter.log', level=logging.INFO)
    fail_count = 0
    global debug
    while True:

        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)

        try:
            containers = db_handler.get_structures(subtype="container")
        except (requests.exceptions.HTTPError, ValueError):
            MyUtils.logging_warning("Couldn't retrieve containers info.", debug=True)
            continue

        # CONFIG
        config = service["config"]
        polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

        for container in containers:
            container_name = container["name"]

            try:
                resources = MyUtils.get_container_resources(container_name)
            except requests.exceptions.HTTPError as e:
                MyUtils.logging_error("Error trying to get container " +
                                      str(container_name) + " info " + str(e) + traceback.format_exc(), debug)
                fail_count += 1

            try:

                # Persist by updating the Database current value and letting the DatabaseSnapshoter update the value
                update_container_current_values(container_name, resources)

                # Persist through time series sent to OpenTSDB
                # generate_timeseries(container_name, resources)
            except Exception:
                MyUtils.logging_error("Error " + traceback.format_exc() + " with container data of: " + str(
                    container_name) + " with resources: " + str(resources), debug)
                fail_count += 1

        if fail_count >= MAX_FAIL_NUM:
            MyUtils.logging_error("[NodeStateDatabase] failed for " + str(fail_count) + " times, exiting.", debug)
            exit(1)
        else:
            fail_count = 0

        time.sleep(polling_frequency)


def main():
    try:
        persist()
    except Exception:
        MyUtils.logging_error("Error " + traceback.format_exc(), debug=True)


if __name__ == "__main__":
    main()
