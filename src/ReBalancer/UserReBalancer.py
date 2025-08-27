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
from src.ReBalancer.Utils import pair_swapping


class UserRebalancer:
    def __init__(self, couchdb_handler):
        self.__config = None
        self.__couchdb_handler = couchdb_handler
        self.__debug = True

    def set_config(self, config):
        self.__config = config

    def rebalance_users(self):
        self.__debug = self.__config.get_value("DEBUG")

        utils.log_info("_______________", self.__debug)
        utils.log_info("Performing USER Balancing", self.__debug)

        try:
            users = self.__couchdb_handler.get_users()
        except requests.exceptions.HTTPError as e:
            utils.log_error("Couldn't get users", self.__debug)
            utils.log_error(str(e), self.__debug)
            return

        pair_swapping(users, self.__config.get_value("RESOURCES_BALANCED"), self.__config.get_value("DIFF_PERCENTAGE"),
                      self.__config.get_value("STOLEN_PERCENTAGE"), self.__couchdb_handler, self.__debug)

        utils.log_info("_______________\n", self.__debug)
