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


class UserRebalancer:
    def __init__(self, config, couchdb_handler):
        self.__config = config
        self.__couchdb_handler = couchdb_handler
        self.__debug = True

    def __inter_user_rebalancing(self, users):
        for resource in self.__config.get_value("RESOURCES_BALANCED"):
            donors, receivers = [], []
            for user in users:
                diff = user[resource]["max"] - user[resource]["usage"]
                if diff > self.__config.get_value("DIFF_PERCENTAGE") * user[resource]["max"]:
                    donors.append(user)
                else:
                    receivers.append(user)

            if not receivers:
                utils.log_info("No user to receive resource {0} shares".format(resource), self.__debug)
                return

            # Order the users from lower to upper resource limit
            receivers = sorted(receivers, key=lambda c: c[resource]["max"])

            shuffling_tuples = list()
            for user in donors:
                diff = user["energy"]["max"] - user["energy"]["used"]
                stolen_amount = self.__config.get_value("STOLEN_PERCENTAGE") * diff
                shuffling_tuples.append((user, stolen_amount))
            shuffling_tuples = sorted(shuffling_tuples, key=lambda c: c[1])

            # Give the resources to the other users
            for receiver in receivers:
                if shuffling_tuples:
                    donor, amount_to_scale = shuffling_tuples.pop(0)
                else:
                    utils.log_info("No more donors, user {0} left out".format(receiver["name"]), self.__debug)
                    continue

                donor[resource]["max"] -= amount_to_scale
                receiver[resource]["max"] += amount_to_scale

                utils.update_user(donor, self.__couchdb_handler, self.__debug)
                utils.update_user(receiver, self.__couchdb_handler, self.__debug)

                utils.log_info("Resource {0} swap between {1} (donor) and {2} (receiver) with amount {3}".format(
                    resource, donor["name"], receiver["name"], amount_to_scale), self.__debug)

    def rebalance_users(self):
        self.__debug = self.__config.get_value("DEBUG")

        utils.log_info("_______________", self.__debug)
        utils.log_info("Performing USER Balancing", self.__debug)

        try:
            users = self.__couchdb_handler.get_users()
        except requests.exceptions.HTTPError as e:
            utils.log_error("Couldn't get users and/or applications", self.__debug)
            utils.log_error(str(e), self.__debug)
            return

        self.__inter_user_rebalancing(users)

        utils.log_info("_______________\n", self.__debug)
