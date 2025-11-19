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

import src.MyUtils.MyUtils as utils
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "STRUCTURES_PERSISTED": ["application"], "RESOURCES_PERSISTED": ["cpu", "mem"], "DEBUG": True, "ACTIVE": True}


class StructuresSnapshoter(Service):

    def __init__(self):
        super().__init__("structures_snapshoter", ConfigValidator(min_frequency=3), CONFIG_DEFAULT_VALUES, sleep_attr="polling_frequency")
        self.rescaler_http_session = requests.Session()
        self.structure_tracker, self.user_tracker = [], []
        self.polling_frequency, self.structures_persisted, self.resources_persisted = None, None, None
        self.debug, self.active = None, None

    @staticmethod
    def translate_resource(resource, to="metric"):
        if to == "metric":
            return "structure.{0}.current".format(resource)
        if to == "limit_label":
            return "effective_cpu_limit" if resource == "cpu" else "{0}_limit".format(resource)
        raise ValueError("Trying to translate bad resource '{0}' or target '{1}'".format(resource, to))

    def update_user(self, user, applications):
        # Aggregate resources for all the applications belonging to the user
        user_apps = [app for app in applications if app["name"] in user["clusters"]]
        for resource in self.resources_persisted:
            if not user.get("resources", {}).get(resource, None):
                utils.log_error("User {0} is missing info of resource {1}".format(user["name"], resource), self.debug)
                continue
            user["resources"][resource]["current"] = 0

            for app in user_apps:
                value = app["resources"].get(resource, {}).get("current", None)
                if value is None:
                    utils.log_warning("Application {0} info is missing for user {1} and resource {2}, user info will not be "
                                      "totally accurate".format(app["name"], user["name"], resource), self.debug)
                    continue
                user["resources"][resource]["current"] += int(value)

        # Register in tracker to persist later
        self.user_tracker.append(user)

    def update_application(self, app, container_resources_dict):
        valid_containers = []
        for container_name in app["containers"]:
            if container_name not in container_resources_dict:
                utils.log_error("Container info {0} is missing for app {1}, app info will not be totally accurate"
                                .format(container_name, app["name"]), self.debug)
                continue
            valid_containers.append(container_name)

        disk_found_metrics = 0
        for resource in self.resources_persisted:
            if not app["resources"].get(resource, None):
                utils.log_error("Application {0} is missing info of resource {1}".format(app["name"], resource), self.debug)
                continue
            app["resources"][resource]["current"] = 0

            limit_label = self.translate_resource(resource, to="limit_label")
            for container_name in valid_containers:
                value = container_resources_dict[container_name]["resources"].get(resource, {}).get(limit_label, None)
                if value is None:
                    utils.log_warning("Container {0} info is missing for app {1} and resource {2}, app info will not be "
                                      "totally accurate".format(container_name, app["name"], resource), self.debug)
                    continue
                app["resources"][resource]["current"] += int(value)

            if resource in {"disk_read", "disk_write"}:
                disk_found_metrics += 1
                if disk_found_metrics == 2:  # Disk need both disk_read and disk_write to be persisted
                    app["resources"].setdefault("disk", {})["current"] = app["resources"]["disk_read"]["current"] + app["resources"]["disk_write"]["current"]

        # Register in tracker to persist later
        self.structure_tracker.append(app)

    def update_container(self, container, container_resources_dict):
        container_name = container["name"]
        # Try to get the container resources, if unavailable, continue with others
        limits = container_resources_dict[container_name]["resources"]
        if not limits:
            utils.log_error("Couldn't get container's {0} limits".format(container_name), self.debug)
            return

        # Remote database operation
        db_structure = self.couchdb_handler.get_structure(container_name)
        if "resources" not in db_structure:
            db_structure["resources"] = dict()

        disk_found_metrics = 0
        for resource in self.resources_persisted:
            # Update only structure resources already in the database; as structures are already initialized in Orchestrator.
            # This allows processing structures without resources that are in the resources_persisted list
            if resource in db_structure["resources"]:
                db_structure["resources"][resource]["current"] = int(limits.get(resource, {}).get(self.translate_resource(resource, to="limit_label"), 0))
                if resource in {"disk_read", "disk_write"}:
                    disk_found_metrics += 1
                    if disk_found_metrics == 2:  # Disk need both disk_read and disk_write to be persisted
                        db_structure["resources"]["disk"]["current"] = db_structure["resources"]["disk_read"]["current"] + db_structure["resources"]["disk_write"]["current"]

        # Register in tracker to persist later
        self.structure_tracker.append(db_structure)

    def persist_current(self, data):
        changes = {"resources": {}}
        for resource in data["resources"]:
            changes["resources"][resource] = {"current": data["resources"][resource]["current"]}
        if data["type"] == "user" or data["subtype"] == "user":
            utils.partial_update_user(data, changes, self.couchdb_handler, self.debug)  # Remote database operation
        elif data["type"] == "structure":
            utils.partial_update_structure(data, changes, self.couchdb_handler, self.debug)  # Remote database operation
        else:
            utils.log_error("Trying to persist unknown data type '{0}'".format(data["type"]), self.debug)

    def persist_thread(self,):
        applications = None
        # Get containers information
        ts = time.time()
        containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
        container_resources_dict = utils.get_container_resources_dict(containers, self.rescaler_http_session, self.debug)
        utils.log_info("It took {0} seconds to get container info".format(str("%.2f" % (time.time() - ts))), self.debug)

        # Update containers if information is available
        ts = time.time()
        if containers:
            utils.run_in_threads(containers, self.update_container, container_resources_dict)
        utils.log_info("It took {0} seconds to update containers".format(str("%.2f" % (time.time() - ts))), self.debug)

        # Update applications if information is available
        ts = time.time()
        if "application" in self.structures_persisted:
            applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            if applications:
                utils.run_in_threads(applications, self.update_application, container_resources_dict)
        utils.log_info("It took {0} seconds to update applications".format(str("%.2f" % (time.time() - ts))), self.debug)

        # Update users if information is available
        ts = time.time()
        if "user" in self.structures_persisted:
            if not applications:
                applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            users = utils.get_users(self.couchdb_handler, self.debug)
            if users:
                utils.run_in_threads(users, self.update_user, applications)
        utils.log_info("It took {0} seconds to update users".format(str("%.2f" % (time.time() - ts))), self.debug)

        # Persist structures and users in database
        ts = time.time()
        utils.run_in_threads(self.structure_tracker + self.user_tracker, self.persist_current)
        # Clear the trackers after persisting
        self.structure_tracker.clear()
        self.user_tracker.clear()
        utils.log_info("It took {0} seconds to persist updated structures in StateDatabase".format(str("%.2f" % (time.time() - ts))), self.debug)

    def work(self, ):
        thread = None
        if self.structures_persisted:
            thread = Thread(target=self.persist_thread, args=())
            thread.start()
        else:
            utils.log_warning("No structures to persist, check STRUCTURES_PERSISTED", self.debug)
        return thread

    def persist(self,):
        self.run_loop()


def main():
    try:
        structure_snapshoter = StructuresSnapshoter()
        structure_snapshoter.persist()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
