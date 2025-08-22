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
import src.StateDatabase.couchdb as couchDB

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "STRUCTURES_PERSISTED": ["applications"], "RESOURCES_PERSISTED": ["cpu", "mem"], "DEBUG": True, "ACTIVE": True}
SERVICE_NAME = "structures_snapshoter"


class StructuresSnapshoter:

    def __init__(self):
        self.couchdb_handler = couchDB.CouchDBServer()
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

    @staticmethod
    def run_in_threads(structures, worker_fn, *worker_args):
        threads = []
        for structure in structures:
            process = Thread(target=worker_fn, args=(structure, *worker_args))
            process.start()
            threads.append(process)

        for process in threads:
            process.join()

    def persist_data(self, data):
        if data["type"] == "structure":
            utils.update_structure(data, self.couchdb_handler, self.debug)  # Remote database operation
        elif data["type"] == "user":
            self.couchdb_handler.update_user(data)
        else:
            utils.log_error("Trying to persist unknown data type '{0}'".format(data["type"]), self.debug)  # Remote database operation

    def update_user(self, user, applications):
        # Aggregate resources for all the applications belonging to the user
        user_apps = [app for app in applications if app["name"] in user["clusters"]]
        for resource in self.resources_persisted:
            if not user.get(resource, None):
                utils.log_error("User {0} is missing info of resource {1}".format(user["name"], resource), self.debug)
                continue
            user[resource]["current"] = 0

            for app in user_apps:
                value = app["resources"].get(resource, {}).get("current", None)
                if value is None:
                    utils.log_warning("Application {0} info is missing for user {1} and resource {2}, user info will not be "
                                      "totally accurate".format(app["name"], user["name"], resource), self.debug)
                    continue
                user[resource]["current"] += int(value)

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
                    app["resources"].setdefault("disk", {})["current"] = 0
            else:
                app["resources"].setdefault(resource, {})["current"] = 0

        application_containers = app["containers"]
        for container_name in application_containers:
            if container_name not in container_resources_dict:
                utils.log_error("Container info {0} is missing for app : {1}, app info will not be totally accurate".format(
                    container_name, app["name"]), self.debug)
                continue
            disk_found_metrics = 0
            for resource in self.resources_persisted:
                try:
                    container_resources = container_resources_dict[container_name]["resources"]
                    if not container_resources.get(resource, None):
                        utils.log_error("Unable to get info for resource {0} and container {1} when computing app {2} resources".format(
                            resource, container_name, app["name"]), self.debug)
                        continue
                    current_resource_label = translate_map[resource]["limit_label"]
                    app["resources"][resource]["current"] += container_resources[resource][current_resource_label]
                    if resource in {"disk_read", "disk_write"}:
                        disk_found_metrics += 1
                        if disk_found_metrics == 2:  # Disk need both disk_read and disk_write to be persisted
                            app["resources"]["disk"]["current"] += app["resources"]["disk_read"]["current"] + app["resources"]["disk_write"]["current"]

                except KeyError:
                    utils.log_error("Container {0} info is missing for app {1} and resource {2}, app info will not be totally"
                              " accurate".format(container_name, app.get("name"), resource), self.debug)

        # Remote database operation
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

    def host_info_request(self, host, container_info, valid_containers):
        host_containers = utils.get_host_containers(host["host_rescaler_ip"], host["host_rescaler_port"], self.rescaler_http_session, self.debug)
        for container_name in host_containers:
            if container_name in valid_containers:
                container_info[container_name] = host_containers[container_name]

    def fill_container_dict(self, hosts_info, containers):
        container_info = {}
        threads = []
        valid_containers = [c["name"] for c in containers]
        for hostname in hosts_info:
            host = hosts_info[hostname]
            t = Thread(target=self.host_info_request, args=(host, container_info, valid_containers))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return container_info

    def get_container_resources_dict(self, containers):
        if not containers:
            return {}

        # Get all the different hosts of the containers
        hosts_info = {}
        for container in containers:
            host = container["host"]
            if host not in hosts_info:
                hosts_info[host] = {}
                hosts_info[host]["host_rescaler_ip"] = container["host_rescaler_ip"]
                hosts_info[host]["host_rescaler_port"] = container["host_rescaler_port"]

        # Retrieve all the containers on the host and persist the ones that we look for
        container_info = self.fill_container_dict(hosts_info, containers)
        container_resources_dict = {}
        for container in containers:
            container_name = container["name"]
            if container_name not in container_info:
                utils.log_warning("Container info for {0} not found, check that it is really living in its supposed "
                                  "host '{1}', and that the host is alive and with the Node Scaler service running"
                                  .format(container_name, container["host"]), self.debug)
                continue
            # Manually add energy limit as there is no physical limit that can be obtained from NodeRescaler
            if "energy" in container["resources"]:
                container_info[container_name]["energy"] = {"energy_limit": container["resources"]["energy"]["current"]}
            container["resources"] = container_info[container_name]
            container_resources_dict[container_name] = container

        return container_resources_dict

    def persist_thread(self,):
        containers, applications = None, None
        # Get containers information
        t0 = time.time()
        containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
        container_resources_dict = self.get_container_resources_dict(containers)
        utils.log_info("It took {0} seconds to get container info".format(str("%.2f" % (time.time() - t0))), self.debug)

        # Update containers if information is available
        t0 = time.time()
        if containers:
            self.run_in_threads(containers, self.update_container, container_resources_dict)
        utils.log_info("It took {0} seconds to update containers".format(str("%.2f" % (time.time() - t0))), self.debug)

        # Update applications if information is available
        t0 = time.time()
        if "applications" in self.structures_persisted:
            applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            if applications:
                self.run_in_threads(applications, self.update_application, container_resources_dict)
        utils.log_info("It took {0} seconds to update applications".format(str("%.2f" % (time.time() - t0))), self.debug)

        # Update users if information is available
        t0 = time.time()
        if "users" in self.structures_persisted:
            if not applications:
                applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            users = self.couchdb_handler.get_users()
            if users:
                self.run_in_threads(users, self.update_user, users, applications)
        utils.log_info("It took {0} seconds to update users".format(str("%.2f" % (time.time() - t0))), self.debug)

        # Persist structures and users in database
        t0 = time.time()
        if self.structure_tracker:
            self.run_in_threads(self.structure_tracker + self.user_tracker, self.persist_data)
            # Clear the trackers after persisting
            self.structure_tracker.clear()
            self.user_tracker.clear()
        utils.log_info("It took {0} seconds to persist updated structures in StateDatabase".format(str("%.2f" % (time.time() - t0))), self.debug)

    def invalid_conf(self, ):
        for key, num in [("POLLING_FREQUENCY", self.polling_frequency)]:
            if num < 3:
                return True, "Configuration item '{0}' with a value of '{1}' is likely invalid".format(key, num)
        return False, ""

    def persist(self,):
        myConfig = utils.MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO, format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        while True:

            utils.update_service_config(self, SERVICE_NAME, myConfig, self.couchdb_handler)
            t0 = utils.start_epoch(self.debug)

            utils.print_service_config(self, myConfig, self.debug)

            # Check invalid configuration
            invalid, message = self.invalid_conf()
            if invalid:
                utils.log_error(message, self.debug)

            thread = None
            if self.active and not invalid:
                thread = Thread(target=self.persist_thread, args=())
                thread.start()
            else:
                utils.log_warning("StructureSnapshoter is not activated", self.debug)

            time.sleep(self.polling_frequency)

            utils.wait_operation_thread(thread, self.debug)

            utils.end_epoch(self.debug, self.polling_frequency, t0)


def main():
    try:
        structure_snapshoter = StructuresSnapshoter()
        structure_snapshoter.persist()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
