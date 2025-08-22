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

import time
import traceback
import logging

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
import src.ReBalancer.ContainerReBalancer as containerReBalancer
import src.ReBalancer.ApplicationReBalancer as applicationReBalancer
import src.ReBalancer.UserReBalancer as userReBalancer

CONFIG_DEFAULT_VALUES = {
    "WINDOW_DELAY": 10,
    "WINDOW_TIMELAPSE": 30,
    "DIFF_PERCENTAGE": 0.40,
    "STOLEN_PERCENTAGE": 0.40,
    "RESOURCES_BALANCED": ["cpu"],
    "STRUCTURES_BALANCED": ["containers"],
    "CONTAINERS_SCOPE": "applications",
    "BALANCING_POLICY": "rules",
    "BALANCING_METHOD": "pair_swapping",
    "DEBUG": True
}

SERVICE_NAME = "rebalancer"


class ReBalancer:
    """ ReBalancer class that implements all the logic for this service"""

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.config = utils.MyConfig(CONFIG_DEFAULT_VALUES)
        self.containerRebalancer = containerReBalancer.ContainerRebalancer(self.config, self.opentsdb_handler, self.couchdb_handler)
        self.applicationReBalancer = applicationReBalancer.ApplicationRebalancer(self.config, self.couchdb_handler)
        self.userReBalancer = userReBalancer.UserRebalancer(self.config, self.couchdb_handler)
        self.window_timelapse, self.window_delay, self.diff_percentage, self.stolen_percentage = None, None, None, None
        self.resources_balanced, self.structures_balanced, self.containers_scope = None, None, None
        self.balancing_policy, self.balancing_method, self.debug = None, None, None

    def invalid_conf(self, ):
        for res in self.resources_balanced:
            if res not in {"cpu", "mem", "disk_read", "disk_write", "net", "energy"}:
                return True, "Resource to be balanced '{0}' is invalid".format(res)

        for structure in self.structures_balanced:
            if structure not in {"containers", "applications", "users"}:
                return True, "Structure to be balanced '{0}' is invalid".format(structure)

        if self.containers_scope not in {"applications", "hosts"}:
            return True, "Containers scope '{0}' to perform container balancing is invalid".format(self.containers_scope)

        if self.balancing_policy not in {"rules", "thresholds"}:
            return True, "Balancing policy '{0}' is invalid".format(self.balancing_policy)

        return False, ""

    def rebalance(self, ):
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO, format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        while True:
            utils.update_service_config(self, SERVICE_NAME, self.config, self.couchdb_handler)

            t0 = utils.start_epoch(self.debug)

            utils.print_service_config(self, self.config, self.debug)

            invalid, message = self.invalid_conf()
            if invalid:
                utils.log_error(message, self.debug)

            # Run rebalancers from upper to lower level of granularity
            if not invalid:
                if "users" in self.structures_balanced:
                    self.userReBalancer.rebalance_users()

                if "applications" in self.structures_balanced:
                    #self.applicationReBalancer.rebalance_applications()
                    pass

                if "containers" in self.structures_balanced or "hosts" in self.structures_balanced:
                    #self.containerRebalancer.rebalance_containers()
                    pass

            time.sleep(self.window_timelapse)

            utils.end_epoch(t0, self.window_timelapse, t0)


def main():
    try:
        rebalancer = ReBalancer()
        rebalancer.rebalance()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
