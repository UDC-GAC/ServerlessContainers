# /usr/bin/python
from __future__ import print_function

from threading import Thread

from requests import HTTPError

import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
import StateDatabase.couchDB as couchDB
import StateDatabase.bdwatchdog

bdwatchdog = StateDatabase.bdwatchdog.BDWatchdog()
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
    container_info = bdwatchdog.get_structure_usages({"host": container_name}, window_difference, window_delay,
                                                     BDWATCHDOG_METRICS, REFEEDER_APPLICATION_METRICS,
                                                     downsample=window_difference)
    return container_info


def get_host_usages(host_name):
    global host_info_cache, window_difference, window_delay
    if host_name in host_info_cache:
        # Get data from cache
        host_info = host_info_cache[host_name]
    else:
        # Data retrieving, slow
        host_info = bdwatchdog.get_structure_usages({"host": host_name}, window_difference,
                                                    window_delay, BDWATCHDOG_ENERGY_METRICS,
                                                    REFEEDER_ENERGY_METRICS)
        host_info_cache[host_name] = host_info
    return host_info


def generate_container_energy_metrics(container, host_info):
    global window_difference, window_delay
    container_name = container["name"]

    # Get the container infomation
    container_info = get_container_usages(container_name)

    # Check that the container has cpu information available
    if container_info["cpu"] == NO_METRIC_DATA_DEFAULT_VALUE:
        MyUtils.logging_error("Error, no container info available for: {0}".format(container_name), debug)
        return None

    # Generate the container energy information from the container cpu and the host cpu and energy info
    new_container = MyUtils.copy_structure_base(container)
    new_container["resources"] = {}
    new_container["resources"]["energy"] = {}
    new_container["resources"]["energy"]["usage"] = float(
        host_info["energy"] * (container_info["cpu"] / host_info["cpu"]))

    return new_container


def generate_application_energy_metrics(application, updated_containers):
    total_energy = 0
    for c in updated_containers:
        # Check if container is used for this application and if it has energy information
        if c["name"] in application["containers"] and "energy" in c["resources"] \
                and "usage" in c["resources"]["energy"]:
            total_energy += c["resources"]["energy"]["usage"]
    if "energy" not in application["resources"]:
        application["resources"]["energy"] = dict()

    application["resources"]["energy"]["usage"] = total_energy
    return application


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


def refeed_container(container, updated_containers):
    # Get the host cpu and energy usages
    try:
        host_name = container["host"]
        host_info = get_host_usages(host_name)

        # Check that both cpu and energy information have been retrieved for the host
        for required_info in ["cpu", "energy"]:
            if host_info[required_info] == NO_METRIC_DATA_DEFAULT_VALUE:
                MyUtils.logging_error("Error, no host '{0}' info available for: {1} so no info can be generated for "
                                      "container: {2}".format(required_info, host_name, container["name"]), debug)
                continue

    except HTTPError:
        MyUtils.logging_error("Error, no info available for: {0}".format(container["host"]), debug)
        return

    # Generate the energy information, if unsuccessful, None will be returned
    container = generate_container_energy_metrics(container, host_info)
    if container:
        MyUtils.update_structure(container, db_handler, debug)
        updated_containers.append(container)


def refeed_containers(containers):
    updated_containers = list()
    threads = []
    for container in containers:
        process = Thread(target=refeed_container, args=(container, updated_containers,))
        process.start()
        threads.append(process)

    for process in threads:
        process.join()

    return updated_containers


def refeed_applications(applications, updated_containers):
    for application in applications:
        application = generate_application_metrics(application)
        application = generate_application_energy_metrics(application, updated_containers)
        MyUtils.update_structure(application, db_handler, debug)


def refeed_thread(containers):
    # Process and measure time
    epoch_start = time.time()

    containers = refeed_containers(containers)

    applications = MyUtils.get_structures(db_handler, debug, subtype="application")
    if applications:
        refeed_applications(applications, containers)

    epoch_end = time.time()
    processing_time = epoch_end - epoch_start
    MyUtils.logging_info("It took {0} seconds to refeed".format(str("%.2f" % processing_time)), debug)


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

        thread = Thread(target=refeed_thread, args=(containers,))
        thread.start()
        MyUtils.logging_info("Refeed processed at {0}".format(MyUtils.get_time_now_string()), debug)
        time.sleep(window_difference)

        if thread.isAlive():
            delay_start = time.time()
            MyUtils.logging_warning(
                "Previous thread didn't finish before next poll is due, with window time of {0} seconds, at {1}".format(
                    str(window_difference), MyUtils.get_time_now_string()), debug)
            MyUtils.logging_warning("Going to wait until thread finishes before proceeding", debug)
            thread.join()
            delay_end = time.time()
            MyUtils.logging_warning("Resulting delay of: {0} seconds".format(str(delay_end - delay_start)), debug)


def main():
    try:
        refeed()
    except Exception as e:
        MyUtils.logging_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
