# /usr/bin/python
from __future__ import print_function

from threading import Thread
import requests
import time
import traceback
import logging

import src.MyUtils.MyUtils as MyUtils
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.opentsdb as OpenTSDB

bdwatchdog = OpenTSDB.OpenTSDBServer()
NO_METRIC_DATA_DEFAULT_VALUE = bdwatchdog.NO_METRIC_DATA_DEFAULT_VALUE
db_handler = couchDB.CouchDBServer()

BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.cpu.kernel', 'proc.mem.resident', 'proc.disk.writes.mb',
                      'proc.disk.reads.mb', 'proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']
BDWATCHDOG_ENERGY_METRICS = ['sys.cpu.user', 'sys.cpu.kernel', 'sys.cpu.energy']
GUARDIAN_METRICS = {'proc.cpu.user': ['proc.cpu.user', 'proc.cpu.kernel'], 'proc.mem.resident': ['proc.mem.resident'],
                    'proc.disk.writes.mb': ['proc.disk.writes.mb'], 'proc.disk.reads.mb': ['proc.disk.reads.mb'],
                    'proc.net.tcp.in.mb': ['proc.net.tcp.in.mb'], 'proc.net.tcp.out.mb': ['proc.net.tcp.out.mb']}
REFEEDER_ENERGY_METRICS = {'cpu': ['sys.cpu.user', 'sys.cpu.kernel'], 'energy': ['sys.cpu.energy']}
REFEEDER_APPLICATION_METRICS = {'cpu': ['proc.cpu.user', 'proc.cpu.kernel'], 'mem': ['proc.mem.resident'],
                                'disk': ['proc.disk.writes.mb', 'proc.disk.reads.mb'],
                                'net': ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']}

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "DEBUG": True}
SERVICE_NAME = "refeeder"
debug = True
NOT_AVAILABLE_STRING = "n/a"

CONTAINER_ENERGY_METRIC = "structure.energy.current"

# Default values
window_difference = 10
window_delay = 10
host_info_cache = dict()

REFEED_ENERGY = True

def merge(output_dict, input_dict):
    for key in input_dict:
        if key in output_dict:
            output_dict[key] = output_dict[key] + input_dict[key]
        else:
            output_dict[key] = input_dict[key]
    return output_dict


def get_container_usages(container_name):
    global window_difference
    global window_delay
    try:
        container_info = bdwatchdog.get_structure_timeseries({"host": container_name}, window_difference, window_delay,
                                                             BDWATCHDOG_METRICS, REFEEDER_APPLICATION_METRICS,
                                                             downsample=window_difference)
    except requests.ConnectionError as e:
        MyUtils.log_error("Connection error: {0} {1}".format(str(e), str(traceback.format_exc())), debug=True)
        raise e
    return container_info


def get_host_usages(host_name):
    global host_info_cache, window_difference, window_delay
    if host_name in host_info_cache:
        # Get data from cache
        host_info = host_info_cache[host_name]
    else:
        # Data retrieving, slow

        try:
            host_info = bdwatchdog.get_structure_timeseries({"host": host_name}, window_difference,
                                                            window_delay, BDWATCHDOG_ENERGY_METRICS,
                                                            REFEEDER_ENERGY_METRICS)
        except requests.ConnectionError as e:
            MyUtils.log_error("Connection error: {0} {1}".format(str(e), str(traceback.format_exc())), debug=True)
            raise e

        host_info_cache[host_name] = host_info
    return host_info


def generate_application_metrics(application):
    global window_difference
    global window_delay
    application_info = dict()
    for c in application["containers"]:
        container_info = get_container_usages(c)
        application_info = merge(application_info, container_info)

    for resource in application_info:
        application["resources"][resource]["usage"] = application_info[resource]

    return application


def refeed_applications(applications):
    for application in applications:
        application = generate_application_metrics(application)
        MyUtils.update_structure(application, db_handler, debug)


def refeed_thread():
    # Process and measure time
    epoch_start = time.time()

    applications = MyUtils.get_structures(db_handler, debug, subtype="application")
    if applications:
        refeed_applications(applications)

    epoch_end = time.time()
    processing_time = epoch_end - epoch_start
    MyUtils.log_info("It took {0} seconds to refeed".format(str("%.2f" % processing_time)), debug)


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
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

        # Data retrieving, slow
        host_info_cache = dict()
        containers = MyUtils.get_structures(db_handler, debug, subtype="container")
        if not containers:
            # As no container info is available, no application information will be able to be generated
            continue

        thread = Thread(target=refeed_thread, args=())
        thread.start()
        MyUtils.log_info("Refeed processed at {0}".format(MyUtils.get_time_now_string()), debug)
        time.sleep(window_difference)

        if thread.isAlive():
            delay_start = time.time()
            MyUtils.log_warning(
                "Previous thread didn't finish before next poll is due, with window time of {0} seconds, at {1}".format(
                    str(window_difference), MyUtils.get_time_now_string()), debug)
            MyUtils.log_warning("Going to wait until thread finishes before proceeding", debug)
            thread.join()
            delay_end = time.time()
            MyUtils.log_warning("Resulting delay of: {0} seconds".format(str(delay_end - delay_start)), debug)


def main():
    try:
        refeed()
    except Exception as e:
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
