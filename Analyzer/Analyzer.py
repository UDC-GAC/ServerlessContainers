# /usr/bin/python
from __future__ import print_function
import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
import requests
import StateDatabase.couchDB as couchDB
import StateDatabase.bdwatchdog as bdwatchdog

monitoring_handler = bdwatchdog.BDWatchdog()
db_handler = couchDB.CouchDBServer()

BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.cpu.kernel']
GUARDIAN_METRICS = {'proc.cpu.user': ['proc.cpu.user', 'proc.cpu.kernel']}
RESOURCES = ['cpu']
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "DEBUG": True}
SERVICE_NAME = "analyzer"
debug = True
translator_dict = {"cpu": "proc.cpu.user"}
NO_METRIC_DATA_DEFAULT_VALUE = -1
NOT_AVAILABLE_STRING = "n/a"

import pipes.send_to_OpenTSDB as OpenTSDB_sender


def get_host_data(hostname, window_difference, window_delay):
    usages = dict()
    subquery = list()
    for metric in ['sys.cpu.user', 'sys.cpu.kernel', 'sys.cpu.energy']:
        usages[metric] = NO_METRIC_DATA_DEFAULT_VALUE
        subquery.append(dict(aggregator='zimsum', metric=metric, tags=dict(host=hostname)))

    start = int(time.time() - (window_difference + window_delay))
    end = int(time.time() - window_delay)
    query = dict(start=start, end=end, queries=subquery)
    result = monitoring_handler.get_points(query)

    for metric in result:
        dps = metric["dps"]
        summatory = sum(dps.values())
        if len(dps) > 0:
            average_real = summatory / len(dps)
        else:
            average_real = 0
        usages[metric["metric"]] = average_real

    final_values = dict()

    METRICS = {
        'cpu': ['sys.cpu.user', 'sys.cpu.kernel'],
        'energy': ['sys.cpu.energy']}

    for value in METRICS:
        final_values[value] = NO_METRIC_DATA_DEFAULT_VALUE
        for metric in METRICS[value]:
            if usages[metric] != NO_METRIC_DATA_DEFAULT_VALUE:
                final_values[value] += usages[metric]

    return final_values


def get_structure_usages(structure, window_difference, window_delay):
    usages = dict()
    subquery = list()
    for metric in BDWATCHDOG_METRICS:
        usages[metric] = NO_METRIC_DATA_DEFAULT_VALUE
        subquery.append(dict(aggregator='sum', metric=metric, tags=dict(host=structure["name"])))

    start = int(time.time() - (window_difference + window_delay))
    end = int(time.time() - window_delay)
    query = dict(start=start, end=end, queries=subquery)
    result = monitoring_handler.get_points(query)

    for metric in result:
        dps = metric["dps"]
        summatory = sum(dps.values())
        if len(dps) > 0:
            average_real = summatory / len(dps)
        else:
            average_real = 0
        usages[metric["metric"]] = average_real

    final_values = dict()

    for value in GUARDIAN_METRICS:
        final_values[value] = NO_METRIC_DATA_DEFAULT_VALUE
        for metric in GUARDIAN_METRICS[value]:
            if usages[metric] != NO_METRIC_DATA_DEFAULT_VALUE:
                final_values[value] += usages[metric]

    return final_values


CONTAINER_ENERGY_METRIC = "structure.energy.current"


def get_container_energy(container_name, host_metrics, container_metrics):
    percentage = float(container_metrics[translator_dict["cpu"]]) / host_metrics["cpu"]
    estimated_container_energy = percentage * host_metrics["energy"]

    # Timeseries
    # return dict(metric=CONTAINER_ENERGY_METRIC, value=estimated_container_energy, timestamp = int(time.time()), tags=dict(host=container_name))

    return estimated_container_energy


def analyze():
    logging.basicConfig(filename='Analyzer.log', level=logging.INFO)
    global debug
    while True:
        try:
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
            window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
            window_delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")
            polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
            debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

            for container in containers:
                container_name = container["name"]
                host_info = get_host_data(container["host"], window_difference, window_delay)
                container_info = get_structure_usages(container, window_difference, window_delay)

                if "energy" not in container["resources"]:
                    container["resources"]["energy"] = dict()

                container["resources"]["energy"]["current"] = get_container_energy(container_name, host_info, container_info)
                db_handler.update_doc("structures", container)
                print("Success with container : " + str(container_name) + " at time: " + time.strftime("%D %H:%M:%S",
                                                                                                   time.localtime()))

        except requests.exceptions.HTTPError as e:
            # FIX TODO probably tried to update a document that has already been updated by other service since it was retrieved
            MyUtils.logging_error("Error " + str(e) + " " + str(traceback.format_exc()), debug)

        time.sleep(polling_frequency)


def main():
    try:
        analyze()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()
