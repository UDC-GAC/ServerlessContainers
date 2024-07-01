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
    get_structures, generate_event_name, generate_request_name, wait_operation_thread, structure_is_container, generate_structure_usage_metric, update_structure, \
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
                                'disk': ['proc.disk.writes.mb', 'proc.disk.reads.mb'],
                                # 'net': ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb'],
                                'energy': ["sys.cpu.energy"]}

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 20, "GENERATED_METRICS": ["cpu", "mem"], "DEBUG": True}

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

    def generate_application_metrics(self, application):
        application_info = dict()

        if len(application["containers"]) > 0:
            for c in application["containers"]:
                container_info = self.get_container_usages(c)
                application_info = self.merge(application_info, container_info)

            for resource in application_info:
                if resource in application["resources"]:
                    application["resources"][resource]["usage"] = application_info[resource]
                else:
                    log_warning("No resource {0} info for application {1}".format(resource, application["name"]), debug=True)
        else:
            for resource in application["resources"]:
                application["resources"][resource]["usage"] = 0

        return application

    def refeed_applications(self, applications):
        for application in applications:
            application = self.generate_application_metrics(application)
            update_structure(application, self.couchdb_handler, self.debug)

    def refeed_user_used_energy(self, applications, users, db_handler, debug):
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
                        log_error("Application {0} of user {1} has no used {2} field or value".format(
                            app["name"], user["name"], resource), debug)

                if "current" in app["resources"]["cpu"] and app["resources"]["cpu"]["current"]:
                    total_user_current_cpu += app["resources"][resource]["current"]
                else:
                    log_error("Application {0} of user {1} has no current cpu field or value".format(
                        app["name"], user["name"]), debug)

            user["energy"]["used"] = total_user["energy"]
            user["cpu"]["usage"] = total_user["cpu"]
            user["cpu"]["current"] = total_user_current_cpu
            db_handler.update_user(user)
            log_info("Updated energy consumed by user {0}".format(user["name"]), debug)

    def refeed_thread(self, ):
        applications = get_structures(self.couchdb_handler, self.debug, subtype="application")
        if applications:
            self.refeed_applications(applications)

        # users = db_handler.get_users()
        # if users:
        #     refeed_user_used_energy(applications, users, db_handler, debug)

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
                containers = get_structures(self.couchdb_handler, debug, subtype="container")
                # if not containers:
                #     # As no container info is available, no application information will be able to be generated
                #     log_info("No structures to process", debug)
                #     time.sleep(self.window_difference)
                #     end_epoch(self.debug, self.window_difference, t0)
                #     continue
                # else:
                thread = Thread(target=self.refeed_thread, args=())
                thread.start()
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
