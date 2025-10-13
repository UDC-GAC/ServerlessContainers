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
import src.StateDatabase.opentsdb as bdwatchdog
from src.ReBalancer.ContainerReBalancer import ContainerRebalancer
from src.ReBalancer.ApplicationReBalancer import ApplicationRebalancer
from src.ReBalancer.UserReBalancer import UserRebalancer
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {
    "WINDOW_DELAY": 10,
    "WINDOW_TIMELAPSE": 30,
    "DIFF_PERCENTAGE": 0.40,
    "STOLEN_PERCENTAGE": 0.40,
    "RESOURCES_BALANCED": ["cpu"],
    "STRUCTURES_BALANCED": ["container"],
    "CONTAINERS_SCOPE": "application",
    "BALANCING_POLICY": "rules",
    "BALANCING_METHOD": "pair_swapping",
    "ONLY_RUNNING": False,
    "DEBUG": True,
    "ACTIVE": True
}


class ReBalancer(Service):
    """ ReBalancer class that implements all the logic for this service"""

    def __init__(self):
        super().__init__("rebalancer", ConfigValidator(), CONFIG_DEFAULT_VALUES, sleep_attr="window_timelapse")
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.container_rebalancer = ContainerRebalancer(self.opentsdb_handler, self.couchdb_handler)
        self.application_rebalancer = ApplicationRebalancer(self.couchdb_handler)
        self.user_rebalancer = UserRebalancer(self.couchdb_handler)
        self.window_timelapse, self.window_delay, self.diff_percentage, self.stolen_percentage = None, None, None, None
        self.resources_balanced, self.structures_balanced, self.containers_scope = None, None, None
        self.balancing_policy, self.balancing_method, self.only_running, self.debug = None, None, None, None

    def on_config_updated(self, service_config):
        self.container_rebalancer.set_config(service_config)
        self.application_rebalancer.set_config(service_config)
        self.user_rebalancer.set_config(service_config)

    def invalid_conf(self, service_config):
        if self.containers_scope not in {"application", "host"}:
            return True, "Containers scope '{0}' to perform container balancing is invalid".format(self.containers_scope)

        if self.balancing_policy not in {"rules", "thresholds"}:
            return True, "Balancing policy '{0}' is invalid".format(self.balancing_policy)

        if "applications" in self.structures_balanced and "containers" in self.structures_balanced and self.containers_scope == "host":
            return True, "Inconsistent configuration, 'application' scope must be used for container balancing when also performing application balancing"

        return self.config_validator.invalid_conf(service_config)

    def get_structures(self):
        users, applications, containers = [], [], []
        if "user" in self.structures_balanced:
            users = utils.get_users(self.couchdb_handler, self.debug)
        if "application" in self.structures_balanced:
            applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
        if "container" in self.structures_balanced:
            containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")

        return users, applications, containers

    def rebalance_structures(self,):
        users, applications, containers = self.get_structures()
        user_requests, app_requests = {}, {}
        if "user" in self.structures_balanced:
            user_requests = self.user_rebalancer.rebalance_users(users)

        if "application" in self.structures_balanced:
            app_requests = self.application_rebalancer.rebalance_applications(users, user_requests, applications)

        if "container" in self.structures_balanced:
            self.container_rebalancer.rebalance_containers(applications, app_requests, containers)

        utils.log_info("---------------------------------------------------------------", self.debug)

    def work(self,):
        thread = Thread(name="rebalance_structures", target=self.rebalance_structures, args=())
        thread.start()
        return thread

    def rebalance(self, ):
        self.run_loop()


def main():
    try:
        rebalancer = ReBalancer()
        rebalancer.rebalance()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
