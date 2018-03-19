# /usr/bin/python
from __future__ import print_function
import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
import requests
import StateDatabase.couchDB as couchDB
import StateDatabase.bdwatchdog

bdwatchdog = StateDatabase.bdwatchdog.BDWatchdog()
NO_METRIC_DATA_DEFAULT_VALUE = bdwatchdog.NO_METRIC_DATA_DEFAULT_VALUE
db_handler = couchDB.CouchDBServer()

BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.cpu.kernel']
GUARDIAN_METRICS = {'proc.cpu.user': ['proc.cpu.user', 'proc.cpu.kernel']}

BDWATCHDOG_ENERGY_METRICS = ['sys.cpu.user', 'sys.cpu.kernel', 'sys.cpu.energy']
ANALYZER_ENERGY_METRICS = {'cpu': ['sys.cpu.user', 'sys.cpu.kernel'],
                           'energy': ['sys.cpu.energy']}

RESOURCES = ['cpu']
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "DEBUG": True}
SERVICE_NAME = "analyzer"
debug = True
translator_dict = {"cpu": "proc.cpu.user"}
NOT_AVAILABLE_STRING = "n/a"

CONTAINER_ENERGY_METRIC = "structure.energy.current"


def get_container_energy(host_metrics, container_metrics):
    percentage = float(container_metrics[translator_dict["cpu"]]) / host_metrics["cpu"]
    return percentage * host_metrics["energy"]


def analyze():
    logging.basicConfig(filename='Analyzer.log', level=logging.INFO)
    global debug
    while True:
        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)

        # Data retrieving, slow
        try:
            containers = db_handler.get_structures(subtype="container")
        except (requests.exceptions.HTTPError, ValueError):
            MyUtils.logging_warning("Couldn't retrieve containers info.", debug=True)
            continue

        # CONFIG
        config = service["config"]
        window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
        window_delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")
        polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

        host_info_cache = dict()

        for container in containers:
            container_name = container["name"]
            host_name = container["host"]

            if host_name in host_info_cache:
                # Get data from cache
                host_info = host_info_cache[host_name]
            else:
                # Data retrieving, slow
                host_info = bdwatchdog.get_structure_usages(host_name, window_difference,
                                                            window_delay, BDWATCHDOG_ENERGY_METRICS,
                                                            ANALYZER_ENERGY_METRICS)
                host_info_cache[host_name] = host_info

            if host_info["cpu"] == NO_METRIC_DATA_DEFAULT_VALUE or host_info["energy"] == NO_METRIC_DATA_DEFAULT_VALUE:
                MyUtils.logging_error(
                    "Error, no host info available for: " + host_name
                    + " so no info can be generated for container: " + container_name, debug)
                continue

            container_info = bdwatchdog.get_structure_usages(container_name, window_difference,
                                                             window_delay,
                                                             BDWATCHDOG_METRICS, GUARDIAN_METRICS)

            if container_info["proc.cpu.user"] == NO_METRIC_DATA_DEFAULT_VALUE:
                MyUtils.logging_error("Error, no container info available for: " + container_name, debug)
                continue

            if "energy" not in container["resources"]:
                container["resources"]["energy"] = dict()

            container["resources"]["energy"]["current"] = get_container_energy(host_info, container_info)
            try:
                db_handler.update_structure(container)
                print("Success with container : " + str(container_name) + " at time: "
                      + time.strftime("%D %H:%M:%S", time.localtime()))
            except requests.exceptions.HTTPError as e:
                # FIX TODO probably tried to update a document that has already been updated by other service
                # since it was retrieved
                MyUtils.logging_error("Error " + str(e) + " " + str(traceback.format_exc()), debug)

        time.sleep(polling_frequency)


def main():
    try:
        analyze()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()
