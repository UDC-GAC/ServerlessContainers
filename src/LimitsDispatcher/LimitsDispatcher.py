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

    def dispatch_limits_by_ratio(self, parent_structure, child_structures, parent_type, child_type):
        for resource in self.generated_metrics:
            global_limit = parent_structure["resources"][resource]["max"]

            total_ratio = sum(s["resources"][resource].get("alloc_ratio", 0) for s in child_structures)

            for s in child_structures:
                utils.log_info("Processing {0} '{1}' from {2} '{3}'".format(child_type, s["name"], parent_type, parent_structure["name"]), self.debug)
                updated = False
                if "alloc_ratio" not in s["resources"][resource]:
                    # If "max" limit has been already rebalanced undo operation to compute allocation ratio based
                    # on its original "max" limit
                    original_limit = global_limit - parent_structure["resources"][resource].get("rebalanced", 0)
                    new_ratio = min(s["resources"][resource]["max"] / original_limit, 1 - total_ratio)
                    s["resources"][resource]["alloc_ratio"] = new_ratio
                    total_ratio += new_ratio
                    utils.log_warning("Allocation ratio for {0} '{1}' and resource {2} will be initialised to {3} ({4} / {5})".format(
                        child_type, s["name"], resource, new_ratio, s["resources"][resource]["max"], original_limit), self.debug)
                    updated = True

                if s["resources"][resource]["alloc_ratio"] == 0.0:
                    utils.log_warning("A new child structure has been added to {0} while not having {1} left"
                                      .format(parent_structure["name"], resource), self.debug)

                structure_limit = round(s["resources"][resource]["alloc_ratio"] * global_limit)
                structure_limit_db = s["resources"][resource]["max"]

                if structure_limit != structure_limit_db:
                    s["resources"][resource]["max"] = structure_limit
                    updated = True

                if updated:
                    self.couchdb_handler.update_structure(s)
                    utils.log_warning("Updated {0} '{1}' resource {2} limit from {3} to {4}".format(
                        child_type, s["name"], resource, structure_limit_db, structure_limit), self.debug)

    def reset_limits(self, parent_structure, parent_type):
        for resource in self.generated_metrics:
            _current = parent_structure["resources"][resource].get("current", -1)
            _max = parent_structure["resources"][resource]["max"]
            _rebalanced = parent_structure["resources"][resource].get("rebalanced", 0)
            if _current == 0 and _rebalanced != 0:
                original_limit = _max - _rebalanced
                parent_structure["resources"][resource]["max"] = original_limit
                parent_structure["resources"][resource]["rebalanced"] = 0
                self.couchdb_handler.update_structure(parent_structure)
                utils.log_warning("Reset {0} '{1}' resource {2} limit from {3} to {4}".format(
                    parent_type, parent_structure["name"], resource, _max, original_limit), self.debug)

    def dispatch_user(self, user, applications, users_running):
        user_apps = [app for app in applications if app["name"] in user["clusters"]]
        if user_apps:
            utils.log_info("Dispatching user {0} limit to apps".format(user["name"]), self.debug)
            self.dispatch_limits_by_ratio(user, user_apps, "user", "application")
        elif not users_running:
            utils.log_info("Check if user {0} limits must be reset".format(user["name"]), self.debug)
            self.reset_limits(user, "user")

    def dispatch_app(self, app, containers, apps_running):
        app_containers = [c for c in containers if c["name"] in app.get("containers", [])]
        if app_containers:
            utils.log_info("Dispatching app {0} limit to containers".format(app["name"]), self.debug)
            self.dispatch_limits_by_ratio(app, app_containers, "application", "container")
        elif not apps_running:
            utils.log_info("Check if app {0} limits must be reset".format(app["name"]), self.debug)
            self.reset_limits(app, "application")

    def dispatch_thread(self, ):
        try:
            containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
            applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            users = utils.get_users(self.couchdb_handler, self.debug)

            if users:
                users_running = any(any(app.get("containers", []) and app['name'] in user.get("clusters", []) for app in applications) for user in users)
                utils.run_in_threads(users, self.dispatch_user, applications, users_running)

            if applications:
                apps_running = any([app.get("containers", []) for app in applications])
                utils.run_in_threads(applications, self.dispatch_app, containers, apps_running)

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
