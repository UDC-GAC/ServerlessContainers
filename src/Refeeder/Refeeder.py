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
import time
import traceback

import src.MyUtils.MyUtils as utils
import src.StateDatabase.opentsdb as bdwatchdog
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 20, "STRUCTURES_REFEEDED": ["application"], "GENERATED_METRICS": ["cpu", "mem"], "DEBUG": True, "ACTIVE": True}


class ReFeeder(Service):
    """ ReFeeder class that implements all the logic for this service"""

    def __init__(self):
        super().__init__("refeeder", ConfigValidator(), CONFIG_DEFAULT_VALUES, sleep_attr="window_timelapse")
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.app_tracker, self.user_tracker = [], []
        self.window_timelapse, self.window_delay, self.structures_refeeded = None, None, None
        self.generated_metrics, self.debug, self.active = None, None, None
        self.config = {}

    @staticmethod
    def merge_dicts(in_dict, out_dict):
        for k, v in in_dict.items():
            out_dict[k] = out_dict.get(k, 0) + v
        return out_dict

    def generate_user_metrics(self, user, applications):
        # Get all applications belonging to user and aggregate usages
        user_apps = [app for app in applications if app["name"] in user["clusters"]]
        for resource in self.generated_metrics:
            user["resources"].setdefault(resource, {})["usage"] = 0
            for app in user_apps:
                value = app.get("resources", {}).get(resource, {}).get("usage", None)
                if value is None:
                    utils.log_warning("Missing usage for resource '{0}' in application {1} from user {2}".format(
                        resource, app["name"], user["name"]), self.debug)
                    continue
                user["resources"][resource]["usage"] += value

        self.user_tracker.append(user)

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
                    if resource == "disk":  # Generate aggregated I/O usage
                        application["resources"][resource]["usage"] = application_info.get(utils.res_to_metric("disk_read"), 0) + application_info.get(utils.res_to_metric("disk_write"), 0)
                    else:
                        application["resources"][resource]["usage"] = application_info[utils.res_to_metric(resource)]
                else:
                    utils.log_warning("No resource {0} info for application {1}".format(resource, application["name"]), self.debug)

        self.app_tracker.append(application)

    def refeed_thread(self, ):
        applications = None

        ts = time.time()
        if "application" in self.structures_refeeded:
            applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            if applications:
                utils.run_in_threads(applications, self.generate_application_metrics)
        utils.log_info("It took {0} seconds to refeed applications".format(str("%.2f" % (time.time() - ts))), self.debug)

        ts = time.time()
        if "user" in self.structures_refeeded:
            if not applications:
                applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            users = utils.get_users(self.couchdb_handler, self.debug)
            if users:
                utils.run_in_threads(users, self.generate_user_metrics, applications)
        utils.log_info("It took {0} seconds to refeed users".format(str("%.2f" % (time.time() - ts))), self.debug)

        ts = time.time()
        utils.run_in_threads(self.app_tracker + self.user_tracker, utils.persist_data, self.couchdb_handler, self.debug)
        self.app_tracker.clear()
        self.user_tracker.clear()
        utils.log_info("It took {0} seconds to persist refeeded data in StateDatabase".format(str("%.2f" % (time.time() - ts))), self.debug)

    def work(self):
        thread = None
        if self.structures_refeeded:
            thread = Thread(target=self.refeed_thread, args=())
            thread.start()
        else:
            utils.log_warning("No structures set to refeed, check STRUCTURES_REFEEDED", self.debug)
        return thread

    def refeed(self, ):
        self.run_loop()


def main():
    try:
        refeeder = ReFeeder()
        refeeder.refeed()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
