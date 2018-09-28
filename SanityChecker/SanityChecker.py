# /usr/bin/python
from __future__ import print_function

import requests

import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
import StateDatabase.couchDB as couchDB
from Rescaler.ClusterScaler import get_current_resource_value, set_container_resources

db_handler = couchDB.CouchDBServer()
rescaler_http_session = requests.Session()
SERVICE_NAME = "sanity_checker"
debug = True
CONFIG_DEFAULT_VALUES = {"DELAY": 120, "DEBUG": True}
DATABASES = ["events", "requests", "services", "structures", "limits"]


def compact_databases():
    try:
        compacted_dbs = list()
        for db in DATABASES:
            success = db_handler.compact_database(db)
            if success:
                compacted_dbs.append(db)
            else:
                MyUtils.logging_warning("Database {0} could not be compacted".format(db), debug)
        MyUtils.logging_info("Databases {0} have been compacted".format(str(compacted_dbs)), debug)
    except Exception as e:
        MyUtils.logging_error(
            "Error doing database compaction: {0} {1}".format(str(e), str(traceback.format_exc())), debug)


def check_unstable_configuration():
    try:
        MyUtils.logging_info("Checking for invalid configuration", debug)
        service = MyUtils.get_service(db_handler, "guardian")
        guardian_configuration = service["config"]
        event_timeout = MyUtils.get_config_value(guardian_configuration, CONFIG_DEFAULT_VALUES, "EVENT_TIMEOUT")
        window_timelapse = MyUtils.get_config_value(guardian_configuration, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")

        rules = db_handler.get_rules()
        for rule in rules:
            if rule["generates"] == "requests":
                event_count = int(rule["events_to_remove"])
                event_window_time_to_trigger = window_timelapse * (event_count + 1)
                # Leave a slight buffer time to account for window times skewness
                if event_window_time_to_trigger > event_timeout:
                    MyUtils.logging_warning(
                        "Rule: '{0}' could never be activated -> guardian event timeout: '{1}', number of events".format(
                            rule["name"], str(event_timeout)) +
                        " required to trigger the rule: '{0}' and guardian polling time: '{1}'".format(
                            str(event_count), str(window_timelapse)), debug)
    except Exception as e:
        MyUtils.logging_error(
            "Error doing configuration check up: {0} {1}".format(str(e), str(traceback.format_exc())), debug)


def fix_container_cpu_mapping(container, cpu_used_cores, cpu_used_shares):
    rescaler_ip = container["host_rescaler_ip"]
    rescaler_port = container["host_rescaler_port"]
    structure_name = container["name"]
    resource_dict = {"cpu": {}}
    resource_dict["cpu"]["cpu_num"] = ",".join(cpu_used_cores)
    resource_dict["cpu"]["cpu_allowance_limit"] = int(cpu_used_shares)
    try:
        # TODO FIX this error should be further diagnosed, in case it affects other modules who use this call too
        try:
            set_container_resources(structure_name, rescaler_ip, rescaler_port, resource_dict, rescaler_http_session)
        except ValueError:
            return False
        return True
    except requests.HTTPError:
        return False


def check_container_cpu_mapping(container, core_usage_map, cpu_used_cores, cpu_used_shares):
    cpu_accounted_shares = 0
    cpu_accounted_cores = list()
    container_name = container["name"]
    for core in core_usage_map:
        if container_name in core_usage_map[core] and core_usage_map[core][container_name] != 0:
            cpu_accounted_shares += core_usage_map[core][container_name]
            cpu_accounted_cores.append(core)

    if sorted(cpu_used_cores) != sorted(cpu_accounted_cores) or cpu_used_shares != cpu_accounted_shares:
        return False, cpu_accounted_cores, cpu_accounted_shares
    else:
        return True, None, None


def check_core_mapping():
    try:
        containers = MyUtils.get_structures(db_handler, debug, subtype="container")
        host_info_cache = dict()

        for container in containers:
            if container["host"] not in host_info_cache:
                host_info_cache[container["host"]] = db_handler.get_structure(container["host"])

            database_resources = container["resources"]
            real_resources = MyUtils.get_container_resources(container, rescaler_http_session, debug)
            if not real_resources:
                MyUtils.logging_error(
                    "Couldn't get container's {0} resources, can't check its sanity".format(container["name"]), debug)
                continue

            host_info = host_info_cache[container["host"]]
            core_usage_map = host_info["resources"]["cpu"]["core_usage_mapping"]

            current_cpu_limit = get_current_resource_value(database_resources, real_resources, "cpu")
            cpu_list = MyUtils.get_cpu_list(real_resources["cpu"]["cpu_num"])

            success, actual_used_cores, actual_used_shares = \
                check_container_cpu_mapping(container, core_usage_map, cpu_list, current_cpu_limit)
            if not success:
                MyUtils.logging_error("Detected invalid core mapping, trying to automatically fix.", debug)
                if fix_container_cpu_mapping(container, actual_used_cores, actual_used_shares):
                    MyUtils.logging_error("Succeded fixing {} container's core mapping".format(container["name"]), debug)
                else:
                    MyUtils.logging_error("Failed in fixing {} container's core mapping".format(container["name"]), debug)
        MyUtils.logging_info("Core mapping has been validated", debug)
    except Exception as e:
        MyUtils.logging_error(
            "Error doing core mapping check up: {0} {1}".format(str(e), str(traceback.format_exc())), debug)

def check_sanity():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    global debug
    while True:
        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # CONFIG
        config = service["config"]
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")
        delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DELAY")

        compact_databases()
        check_unstable_configuration()
        check_core_mapping()
        MyUtils.logging_info("Sanity checked at {0}".format(MyUtils.get_time_now_string()), debug)

        time_waited = 0
        heartbeat_delay = 10  # seconds

        while time_waited < delay:
            # Heartbeat
            MyUtils.beat(db_handler, SERVICE_NAME)
            time.sleep(heartbeat_delay)
            time_waited += heartbeat_delay


def main():
    try:
        check_sanity()
    except Exception as e:
        MyUtils.logging_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
