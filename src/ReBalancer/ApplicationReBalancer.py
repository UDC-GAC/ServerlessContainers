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

import requests

import src.MyUtils.MyUtils as utils
from src.ReBalancer.Utils import pair_swapping, has_required_fields


class ApplicationRebalancer:

    def __init__(self, couchdb_handler):
        self.__config = None
        self.__couchdb_handler = couchdb_handler
        self.__debug = True

    def set_config(self, config):
        self.__config = config
        self.__debug = self.__config.get_value("DEBUG")

    def rebalance_applications(self):
        utils.log_info("-------------------- APPLICATION BALANCING --------------------", self.__debug)

        applications = utils.get_structures(self.__couchdb_handler, self.__debug, subtype="application")
        users = []
        try:
            users = self.__couchdb_handler.get_users()
        except requests.exceptions.HTTPError:
            utils.log_warning("No registered users were found on the platform, all the applications will be balanced as a single cluster", self.__debug)

        running_apps = [app for app in applications if app.get("containers", [])]
        if not running_apps:
            utils.log_warning("No registered registered app is running right now", self.__debug)
            return

        if users:
            for user in users:
                user_apps = [app for app in running_apps if app["name"] in user["clusters"]]
                utils.log_info("Processing user {0} who has {1} applications registered".format(user["name"], len(user_apps)), self.__debug)
                if user_apps:
                    pair_swapping(user_apps, self.__config.get_value("RESOURCES_BALANCED"), self.__config.get_value("DIFF_PERCENTAGE"),
                                  self.__config.get_value("STOLEN_PERCENTAGE"), self.__couchdb_handler, self.__debug)
        else:
            pair_swapping(running_apps, self.__config.get_value("RESOURCES_BALANCED"), self.__config.get_value("DIFF_PERCENTAGE"),
                          self.__config.get_value("STOLEN_PERCENTAGE"), self.__couchdb_handler, self.__debug)
