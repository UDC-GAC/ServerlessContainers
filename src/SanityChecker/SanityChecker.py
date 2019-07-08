# /usr/bin/python
from __future__ import print_function

import requests
import time
import traceback
import logging

import src.MyUtils.MyUtils as MyUtils
import src.StateDatabase.couchdb as couchDB
from src.Rescaler.ClusterScaler import get_current_resource_value, set_container_resources

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
                MyUtils.log_warning("Database {0} could not be compacted".format(db), debug)
        MyUtils.log_info("Databases {0} have been compacted".format(str(compacted_dbs)), debug)
    except Exception as e:
        MyUtils.log_error(
            "Error doing database compaction: {0} {1}".format(str(e), str(traceback.format_exc())), debug)


def check_unstable_configuration():
    try:
        MyUtils.log_info("Checking for invalid configuration", debug)
        service = MyUtils.get_service(db_handler, "guardian")
        guardian_configuration = service["config"]
        event_timeout = MyUtils.get_config_value(guardian_configuration, CONFIG_DEFAULT_VALUES, "EVENT_TIMEOUT")
        window_timelapse = MyUtils.get_config_value(guardian_configuration, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")

        rules = db_handler.get_rules()
        for rule in rules:
            if "generates" in rule and rule["generates"] == "requests" and rule["active"]:
                event_count = int(rule["events_to_remove"])
                event_window_time_to_trigger = window_timelapse * (event_count + 1)
                # Leave a slight buffer time to account for window times skewness
                if event_window_time_to_trigger > event_timeout:
                    MyUtils.log_warning(
                        "Rule: '{0}' could never be activated -> guardian event timeout: '{1}', number of events".format(
                            rule["name"], str(event_timeout)) +
                        " required to trigger the rule: '{0}' and guardian polling time: '{1}'".format(
                            str(event_count), str(window_timelapse)), debug)
    except Exception as e:
        MyUtils.log_error(
            "Error doing configuration check up: {0} {1}".format(str(e), str(traceback.format_exc())), debug)


def fix_container_cpu_mapping(container, cpu_used_cores, cpu_used_shares, max_cpu_limit):
    if cpu_used_shares > max_cpu_limit:
        # TODO FIX container has, somehow, more shares than the maximum
        MyUtils.log_error("container {0} has, somehow, more shares than the maximum".format(container["name"]), debug)
        return False
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


def check_container_cpu_mapping(container, host_info, cpu_used_cores, cpu_used_shares):
    host_max_cores = int(host_info["resources"]["cpu"]["max"] / 100)
    host_cpu_list = [str(i) for i in range(host_max_cores)]
    core_usage_map = host_info["resources"]["cpu"]["core_usage_mapping"]

    cpu_accounted_shares = 0
    cpu_accounted_cores = list()
    container_name = container["name"]
    for core in core_usage_map:
        if core not in host_cpu_list:
            continue
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
                MyUtils.log_error(
                    "Couldn't get container's {0} resources, can't check its sanity".format(container["name"]), debug)
                continue

            host_info = host_info_cache[container["host"]]

            max_cpu_limit = database_resources["cpu"]["max"]
            current_cpu_limit = get_current_resource_value(container, real_resources, "cpu")
            cpu_list = MyUtils.get_cpu_list(real_resources["cpu"]["cpu_num"])

            success, actual_used_cores, actual_used_shares = \
                check_container_cpu_mapping(container, host_info, cpu_list, current_cpu_limit)

            if not success:
                MyUtils.log_error("Detected invalid core mapping, trying to automatically fix.", debug)
                if fix_container_cpu_mapping(container, actual_used_cores, actual_used_shares, max_cpu_limit):
                    MyUtils.log_error("Succeded fixing {0} container's core mapping".format(container["name"]),
                                      debug)
                else:
                    MyUtils.log_error("Failed in fixing {0} container's core mapping".format(container["name"]),
                                      debug)
        MyUtils.log_info("Core mapping has been validated", debug)
    except Exception as e:
        MyUtils.log_error(
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
        MyUtils.log_info("Sanity checked at {0}".format(MyUtils.get_time_now_string()), debug)

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
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
