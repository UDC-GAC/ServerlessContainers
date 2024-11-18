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

import src.MyUtils.MyUtils as MyUtils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
import src.ReBalancer.ContainerReBalancer as containerReBalancer
import src.ReBalancer.ApplicationReBalancer as applicationReBalancer
import src.ReBalancer.UserReBalancer as userReBalancer
from src.ReBalancer.Utils import CONFIG_DEFAULT_VALUES

SERVICE_NAME = "rebalancer"


class ReBalancer:
    """ ReBalancer class that implements all the logic for this service"""

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.containerRebalancer = containerReBalancer.ContainerRebalancer()
        self.applicationReBalancer = applicationReBalancer.ApplicationRebalancer()
        self.userReBalancer = userReBalancer.UserRebalancer()
        self.debug = True
        self.config = {}

    def rebalance(self, ):
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO, format=MyUtils.LOGGING_FORMAT, datefmt=MyUtils.LOGGING_DATEFMT)
        while True:
            # Get service info
            service = MyUtils.get_service(self.couchdb_handler, SERVICE_NAME)

            # Heartbeat
            MyUtils.beat(self.couchdb_handler, SERVICE_NAME)

            # CONFIG
            self.config = service["config"]
            self.debug = MyUtils.get_config_value(self.config, CONFIG_DEFAULT_VALUES, "DEBUG")
            window_difference = MyUtils.get_config_value(self.config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")

            #self.userReBalancer.rebalance_users(self.config)
            #self.applicationReBalancer.rebalance_applications(self.config)
            self.containerRebalancer.rebalance_containers(self.config)

            MyUtils.log_info("Epoch processed at {0}".format(MyUtils.get_time_now_string()), self.debug)

            time.sleep(window_difference)


def main():
    try:
        rebalancer = ReBalancer()
        rebalancer.rebalance()
    except Exception as e:
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
