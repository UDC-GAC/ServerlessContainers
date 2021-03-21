# Copyright (c) 2019 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es, jonatan.enes.alvarez@gmail.com)
#     - Roberto R. Expósito
#     - Juan Touriño
#
# This file is part of the ServerlessContainers framework, from
# now on referred to as ServerlessContainers.
#
# ServerlessContainers is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# ServerlessContainers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ServerlessContainers. If not, see <http://www.gnu.org/licenses/>.


from __future__ import print_function

from threading import Thread
import requests
import time
import traceback
import logging

import src.MyUtils.MyUtils as MyUtils
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.opentsdb as OpenTSDB
from src.ReBalancer.Utils import get_user_apps

bdwatchdog = OpenTSDB.OpenTSDBServer()
NO_METRIC_DATA_DEFAULT_VALUE = bdwatchdog.NO_METRIC_DATA_DEFAULT_VALUE
db_handler = couchDB.CouchDBServer()

BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.cpu.kernel', 'proc.mem.resident', 'proc.disk.writes.mb',
                      'proc.disk.reads.mb', 'proc.net.tcp.in.mb', 'proc.net.tcp.out.mb', 'sys.cpu.energy']
BDWATCHDOG_ENERGY_METRICS = ['sys.cpu.user', 'sys.cpu.kernel', 'sys.cpu.energy']
GUARDIAN_METRICS = {'proc.cpu.user': ['proc.cpu.user', 'proc.cpu.kernel'], 'proc.mem.resident': ['proc.mem.resident'],
                    'proc.disk.writes.mb': ['proc.disk.writes.mb'], 'proc.disk.reads.mb': ['proc.disk.reads.mb'],
                    'proc.net.tcp.in.mb': ['proc.net.tcp.in.mb'], 'proc.net.tcp.out.mb': ['proc.net.tcp.out.mb']}
REFEEDER_ENERGY_METRICS = {'cpu': ['sys.cpu.user', 'sys.cpu.kernel'], 'energy': ['sys.cpu.energy']}

REFEEDER_APPLICATION_METRICS = {'cpu': ['proc.cpu.user', 'proc.cpu.kernel'],
                                'mem': ['proc.mem.resident'],
                                # 'disk': ['proc.disk.writes.mb', 'proc.disk.reads.mb'],
                                # 'net': ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb'],
                                'energy': ["sys.cpu.energy"]}

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 15, "DEBUG": True}
SERVICE_NAME = "refeeder"
debug = True
NOT_AVAILABLE_STRING = "n/a"

# Default values
window_difference = 10
window_delay = 15
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
                                                             BDWATCHDOG_METRICS, REFEEDER_APPLICATION_METRICS)

        for metric in REFEEDER_APPLICATION_METRICS:
            if container_info[metric] == NO_METRIC_DATA_DEFAULT_VALUE:
                MyUtils.log_warning("No metric info for {0} in container {1}".format(metric, container_name), debug=True)


    except requests.ConnectionError as e:
        MyUtils.log_error("Connection error: {0} {1}".format(str(e), str(traceback.format_exc())), debug=True)
        raise e
    return container_info


def generate_application_metrics(application):
    global window_difference
    global window_delay
    application_info = dict()
    for c in application["containers"]:
        container_info = get_container_usages(c)
        application_info = merge(application_info, container_info)

    for resource in application_info:
        if resource in application["resources"]:
            application["resources"][resource]["usage"] = application_info[resource]
        else:
            MyUtils.log_warning("No resource {0} info for application {1}".format(resource,application["name"]), debug=True)

    return application


def refeed_applications(applications):
    for application in applications:
        application = generate_application_metrics(application)
        MyUtils.update_structure(application, db_handler, debug)


def refeed_user_used_energy(applications, users, db_handler, debug):
    for user in users:
        if "cpu" not in user:
            user["cpu"] = {}
        if "energy" not in user:
            user["energy"] = {}
        total_user = {"cpu": 0, "energy": 0}
        total_user_current_cpu = 0
        user_apps = get_user_apps(applications, user)
        for app in user_apps:
            for resource in ["energy", "cpu"]:
                if "usage" in app["resources"][resource] and app["resources"][resource]["usage"]:
                    total_user[resource] += app["resources"][resource]["usage"]
                else:
                    MyUtils.log_error("Application {0} of user {1} has no used {2} field or value".format(
                        app["name"], user["name"], resource), debug)

            if "current" in app["resources"]["cpu"] and app["resources"]["cpu"]["usage"]:
                total_user_current_cpu += app["resources"][resource]["current"]
            else:
                MyUtils.log_error("Application {0} of user {1} has no current cpu field or value".format(
                    app["name"], user["name"]), debug)

        user["energy"]["used"] = total_user["energy"]
        user["cpu"]["usage"] = total_user["cpu"]
        user["cpu"]["current"] = total_user_current_cpu
        db_handler.update_user(user)
        MyUtils.log_info("Updated energy consumed by user {0}".format(user["name"]), debug)


def refeed_thread():
    # Process and measure time
    epoch_start = time.time()

    applications = MyUtils.get_structures(db_handler, debug, subtype="application")
    if applications:
        refeed_applications(applications)

    users = db_handler.get_users()
    if users:
        refeed_user_used_energy(applications, users, db_handler, debug)

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

        if thread.is_alive():
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
