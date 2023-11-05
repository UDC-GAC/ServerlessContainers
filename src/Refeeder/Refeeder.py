#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es)
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

from src.MyUtils.MyUtils import MyConfig, log_error, get_service, beat, log_info, log_warning, \
    get_structures, wait_operation_thread, update_structure, \
    end_epoch, start_epoch
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
from src.ReBalancer.Utils import get_user_apps

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

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10,
                         "WINDOW_DELAY": 20,
                         "GENERATED_METRICS": ["cpu", "mem"],
                         "DEBUG": True
                         }

host_info_cache = dict()

SERVICE_NAME = "refeeder"

class ReFeeder:
    """ ReFeeder class that implements all the logic for this service"""

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.debug = True
        self.config = {}

    def merge(self, output_dict, input_dict):
        for key in input_dict:
            if key in output_dict:
                output_dict[key] = output_dict[key] + input_dict[key]
            else:
                output_dict[key] = input_dict[key]
        return output_dict

    def get_container_usages(self, container_name):
        try:
            container_info = self.opentsdb_handler.get_structure_timeseries({"host": container_name},
                                                                            self.window_difference,
                                                                            self.window_delay,
                                                                            BDWATCHDOG_METRICS,
                                                                            REFEEDER_APPLICATION_METRICS)

            for metric in REFEEDER_APPLICATION_METRICS:
                if metric not in CONFIG_DEFAULT_VALUES["GENERATED_METRICS"]:
                    continue
                if container_info[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE:
                    log_warning("No metric info for {0} in container {1}".format(metric, container_name), debug=True)


        except requests.ConnectionError as e:
            log_error("Connection error: {0} {1}".format(str(e), str(traceback.format_exc())), debug=True)
            raise e
        return container_info

    def refeed_applications(self, applications):
        for application in applications:
            application_usages = {"cpu": 0, "mem": 0}

            for c in application["containers"]:
                container_usages = self.get_container_usages(c)
                application_usages = self.merge(application_usages, container_usages)

            for resource in application_usages:
                if resource in application["resources"]:
                    application["resources"][resource]["used"] = application_usages[resource]
                else:
                    log_warning("No resource {0} info for application {1}".format(resource, application["name"]), debug=True)

            update_structure(application, self.couchdb_handler, self.debug)
            log_info("Updated Application {0}".format(application["name"]), self.debug)

    def refeed_users(self, applications, users):
        def print_missing(field):
            log_warning("Missing field '{0}' for app '{1}' of user '{2}'".format(
                field, app["name"], user["name"]), self.debug)

        for user in users:
            user_apps = get_user_apps(applications, user)

            if "cpu" not in user:
                user["cpu"] = {}
            if "energy" not in user:
                user["energy"] = {}

            user["cpu"]["current"] = 0
            user["cpu"]["used"] = 0
            user["energy"]["used"] = 0

            for app in user_apps:
                if "cpu" in app["resources"] and "used" in app["resources"]["cpu"]:
                    user["cpu"]["used"] += int(app["resources"]["cpu"]["used"])
                else:
                    print_missing("cpu.used")

                if "current" in app["resources"]["cpu"] and "current" in app["resources"]["cpu"]:
                    user["cpu"]["current"] += app["resources"]["cpu"]["current"]
                else:
                    print_missing("cpu.current")

                if "energy" in app["resources"] and "used" in app["resources"]["energy"]:
                    user["energy"]["used"] += int(app["resources"]["energy"]["used"])
                else:
                    print_missing("energy.used")

            self.couchdb_handler.update_user(user)
            log_info("Updated User {0}".format(user["name"]), self.debug)

    def refeed_thread(self, ):
        applications = get_structures(self.couchdb_handler, self.debug, subtype="application")
        if applications:
            self.refeed_applications(applications)

        users = self.couchdb_handler.get_users()
        if users:
            # Retrieve again the application as they have been updated (in other threads)
            applications = get_structures(self.couchdb_handler, self.debug, subtype="application")
            self.refeed_users(applications, users)


    def refeed(self, ):
        myConfig = MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

        while True:
            # Get service info
            service = get_service(self.couchdb_handler, SERVICE_NAME)

            # Heartbeat
            beat(self.couchdb_handler, SERVICE_NAME)

            # CONFIG
            myConfig.set_config(service["config"])
            self.debug = myConfig.get_value("DEBUG")
            debug = self.debug
            self.window_difference = myConfig.get_value("WINDOW_TIMELAPSE")
            self.window_delay = myConfig.get_value("WINDOW_DELAY")
            SERVICE_IS_ACTIVATED = myConfig.get_value("ACTIVE")

            t0 = start_epoch(self.debug)

            log_info("Config is as follows:", debug)
            log_info(".............................................", debug)
            log_info("Time window lapse -> {0}".format(self.window_difference), debug)
            log_info("Delay -> {0}".format(self.window_delay), debug)
            log_info(".............................................", debug)

            thread = None
            if SERVICE_IS_ACTIVATED:
                # Remote database operation
                host_info_cache = dict()
                #containers = get_structures(self.couchdb_handler, debug, subtype="container")
                thread = Thread(target=self.refeed_thread, args=())
                thread.start()
                # if not containers:
                #     # As no container info is available, no application information will be able to be generated
                #     log_info("No structures to process", debug)
                #     time.sleep(self.window_difference)
                #     end_epoch(self.debug, self.window_difference, t0)
                #     continue
                # else:
                #     thread = Thread(target=self.refeed_thread, args=())
                #     thread.start()
            else:
                log_warning("Refeeder is not activated", debug)

            time.sleep(self.window_difference)

            wait_operation_thread(thread, debug)
            log_info("Refeed processed", debug)

            end_epoch(self.debug, self.window_difference, t0)


def main():
    try:
        refeeder = ReFeeder()
        refeeder.refeed()
    except Exception as e:
        log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
