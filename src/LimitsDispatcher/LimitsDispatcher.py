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

import traceback
from threading import Thread

import src.MyUtils.MyUtils as utils
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {"GENERATED_METRICS": ["energy"], "POLLING_FREQUENCY": 10, "DEBUG": True, "ACTIVE": True}


class LimitsDispatcher(Service):

    def __init__(self):
        super().__init__("limits_dispatcher", ConfigValidator(), CONFIG_DEFAULT_VALUES, sleep_attr="polling_frequency")
        self.polling_frequency, self.generated_metrics = None, None
        self.debug, self.active = None, None

    def dispatch_limits_by_ratio(self, parent_structure, child_structures):
        for resource in self.generated_metrics:
            global_limit = parent_structure["resources"][resource]["max"]

            total_ratio = sum(s["resources"][resource].get("alloc_ratio", 0) for s in child_structures)

            for s in child_structures:
                if "alloc_ratio" not in s["resources"][resource]:
                    new_ratio = min(s["resources"][resource]["max"] / global_limit, 1 - total_ratio)
                    total_ratio += new_ratio
                    s["resources"][resource]["alloc_ratio"] = s["resources"][resource]["max"] / global_limit

                if s["resources"][resource]["alloc_ratio"] == 0.0:
                    utils.log_warning("A new child structure has been added to {0} while not having {1} left"
                                      .format(parent_structure["name"], resource), self.debug)

                structure_limit = round(s["resources"][resource]["alloc_ratio"] * global_limit)
                structure_limit_db = s["resources"][resource]["max"]

                if structure_limit != structure_limit_db:
                    s["resources"][resource]["max"] = structure_limit
                    utils.log_warning("Updating structure {0} resource {1} limit from {2} to {3}".format(
                        s["name"], resource, structure_limit_db, structure_limit), self.debug)
                    self.couchdb_handler.update_structure(s)

    def dispatch_user(self, user, applications):
        utils.log_info("Dispatching user {0} limit to apps".format(user["name"]), self.debug)
        user_apps = [app for app in applications if app["name"] in user["clusters"]]
        self.dispatch_limits_by_ratio(user, user_apps)

    def dispatch_app(self, app, containers):
        utils.log_info("Dispatching app {0} limit to containers".format(app["name"]), self.debug)
        app_containers = [c for c in containers if c["name"] in app.get("containers", [])]
        self.dispatch_limits_by_ratio(app, app_containers)

    def dispatch_thread(self, ):
        try:
            containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
            applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            users = utils.get_users(self.couchdb_handler, self.debug)

            if users and applications:
                utils.run_in_threads(users, self.dispatch_user, applications)

            if applications and containers:
                utils.run_in_threads(applications, self.dispatch_app, containers)

        except Exception as e:
            utils.log_error("Some error ocurred dispatching limits: {0} {1}".format(str(e), str(traceback.format_exc())), self.debug)

    def work(self, ):
        thread = None
        if self.generated_metrics:
            thread = Thread(target=self.dispatch_thread(), args=())
            thread.start()
        else:
            utils.log_warning("No resources to dispatch, check GENERATED_METRICS", self.debug)
        return thread

    def dispatch(self, ):
        self.run_loop()


def main():
    try:
        limits_dispatcher = LimitsDispatcher()
        limits_dispatcher.dispatch()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
