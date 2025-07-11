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

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
from src.ReBalancer.Utils import get_user_apps

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 20, "GENERATED_METRICS": ["cpu", "mem"], "DEBUG": True}

host_info_cache = dict()

SERVICE_NAME = "refeeder"


class ReFeeder:
    """ ReFeeder class that implements all the logic for this service"""

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.window_timelapse, self.window_delay, self.generated_metrics, self.debug, self.active = None, None, None, None, None
        self.config = {}

    @staticmethod
    def merge_dicts(in_dict, out_dict):
        for k, v in in_dict.items():
            out_dict[k] = out_dict.get(k, 0) + v
        return out_dict

    def generate_user_metrics(self, user, applications):
        resource_field_map = [("cpu", "current"), ("cpu", "usage"), ("energy", "usage")]

        # Initialize user values to zero
        user.setdefault("cpu", {})
        user.setdefault("energy", {})
        total_user = {"cpu_current": 0, "cpu_usage": 0, "energy_usage": 0}

        # Get all applications belonging to user and aggregate metrics
        for app in get_user_apps(applications, user):
            for resource, field in resource_field_map:
                if app.get("resources", {}).get(resource, {}).get(field, None):
                    total_user[f"{resource}_{field}"] += app["resources"][resource][field]
                else:
                    utils.log_error("Missing field '{0}' for resource '{1}' in application {2} from user {3}".format(
                        field, resource, app["name"], user["name"]), self.debug)

        # Update user values
        for resource, field in resource_field_map:
            user[resource][field] = total_user[f"{resource}_{field}"]

        return user

    def generate_application_metrics(self, application):
        application_info = dict()

        # Initialize application usage values to zero
        for resource in application["resources"]:
            application["resources"][resource]["usage"] = 0

        # Get all containers belonging to application and aggregate metrics
        for c in application["containers"]:
            container_info = utils.get_structure_usages(self.generated_metrics, {"name": c, "subtype": "container"},
                                                        self.window_timelapse, self.window_delay,
                                                        self.opentsdb_handler, self.debug)
            application_info = self.merge_dicts(container_info, application_info)

        # Update application values
        if application_info: # check that application_info has been loaded with the information of at least one container
            for resource in self.generated_metrics:
                if resource in application["resources"]:
                    application["resources"][resource]["usage"] = application_info[utils.res_to_metric(resource)]
                else:
                    utils.log_warning("No resource {0} info for application {1}".format(resource, application["name"]), self.debug)

        ## Generate aggregated I/O usage
        if "disk" in application["resources"] and utils.res_to_metric("disk_read") in application_info and utils.res_to_metric("disk_write") in application_info:
            application["resources"]["disk"]["usage"] = application_info[utils.res_to_metric("disk_read")] + application_info[utils.res_to_metric("disk_write")]

        return application

    def refeed_users(self, users, applications):
        for user in users:
            user = self.generate_user_metrics(user, applications)
            utils.update_user(user, self.couchdb_handler, self.debug)

    def refeed_applications(self, applications):
        for application in applications:
            application = self.generate_application_metrics(application)
            utils.update_structure(application, self.couchdb_handler, self.debug)

    def refeed_thread(self, ):
        applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
        if applications:
            self.refeed_applications(applications)

        # users = db_handler.get_users()
        # if users:
        #     self.refeed_users(users, applications)

    def refeed(self, ):
        myConfig = utils.MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO, format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        while True:

            utils.update_service_config(self, SERVICE_NAME, myConfig, self.couchdb_handler)

            t0 = utils.start_epoch(self.debug)

            utils.print_service_config(self, myConfig, self.debug)

            thread = None
            if self.active:
                # Remote database operation
                host_info_cache = dict()
                thread = Thread(target=self.refeed_thread, args=())
                thread.start()
            else:
                utils.log_warning("Refeeder is not activated", self.debug)

            time.sleep(self.window_timelapse)

            utils.wait_operation_thread(thread, self.debug)
            utils.log_info("Refeed processed", self.debug)

            utils.end_epoch(self.debug, self.window_timelapse, t0)


def main():
    try:
        refeeder = ReFeeder()
        refeeder.refeed()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
