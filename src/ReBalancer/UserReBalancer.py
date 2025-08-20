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
from src.ReBalancer.Utils import CONFIG_DEFAULT_VALUES, app_can_be_rebalanced, get_user_apps
from src.StateDatabase import couchdb


class UserRebalancer:
    def __init__(self):
        self.__couchdb_handler = couchdb.CouchDBServer()
        self.__debug = True
        self.__config = {}

    def update_user_used_energy(self, applications, users):
        for user in users:
            total_user = {"cpu": 0, "energy": 0}
            total_user_current_cpu = 0
            user_apps = get_user_apps(applications, user)
            for app in user_apps:
                for resource in ["energy", "cpu"]:
                    if "usage" in app["resources"][resource] and app["resources"][resource]["usage"]:
                        total_user[resource] += app["resources"][resource]["usage"]
                    else:
                        utils.log_error("Application {0} of user {1} has no used {2} field or value".format(
                            app["name"], user["name"], resource), self.__debug)

                if "current" in app["resources"]["cpu"] and app["resources"]["cpu"]["usage"]:
                    total_user_current_cpu += app["resources"][resource]["current"]
                else:
                    utils.log_error("Application {0} of user {1} has no current cpu field or value".format(
                        app["name"], user["name"]), self.__debug)

            user["energy"]["used"] = total_user["energy"]
            user["cpu"]["usage"] = total_user["cpu"]
            user["cpu"]["current"] = total_user_current_cpu
            self.__couchdb_handler.update_user(user)
            utils.log_info("Updated energy consumed by user {0}".format(user["name"]), self.__debug)

    def __inter_user_rebalancing(self, users):
        donors, receivers = list(), list()
        for user in users:
            diff = user["energy"]["max"] - user["energy"]["used"]
            if diff > self.__ENERGY_DIFF_PERCENTAGE * user["energy"]["max"]:
                donors.append(user)
            else:
                receivers.append(user)

        if not receivers:
            utils.log_info("No user to give energy shares", self.__debug)
            return
        else:
            # Order the apps from lower to upper energy limit
            users_to_receive = sorted(receivers, key=lambda c: c["energy"]["max"])

        shuffling_tuples = list()
        for user in donors:
            diff = user["energy"]["max"] - user["energy"]["used"]
            stolen_amount = self.__ENERGY_STOLEN_PERCENTAGE * diff
            shuffling_tuples.append((user, stolen_amount))
        shuffling_tuples = sorted(shuffling_tuples, key=lambda c: c[1])

        # Give the resources to the other users
        for receiver in users_to_receive:
            if shuffling_tuples:
                donor, amount_to_scale = shuffling_tuples.pop(0)
            else:
                utils.log_info("No more donors, user {0} left out".format(receiver["name"]), self.__debug)
                continue

            donor["energy"]["max"] -= amount_to_scale
            receiver["energy"]["max"] += amount_to_scale

            utils.update_user(donor, self.__couchdb_handler, self.__debug)
            utils.update_user(receiver, self.__couchdb_handler, self.__debug)

            utils.log_info(
                "Energy swap between {0}(donor) and {1}(receiver)".format(donor["name"], receiver["name"]),
                self.__debug)

    def rebalance_users(self, config):
        self.__config = config
        self.__debug = utils.get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "DEBUG")

        rebalance_users = utils.get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "REBALANCE_USERS")

        self.__ENERGY_DIFF_PERCENTAGE = utils.get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "ENERGY_DIFF_PERCENTAGE")
        self.__ENERGY_STOLEN_PERCENTAGE = utils.get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "ENERGY_STOLEN_PERCENTAGE")
        utils.log_info("ENERGY_DIFF_PERCENTAGE -> {0}".format(self.__ENERGY_DIFF_PERCENTAGE), self.__debug)
        utils.log_info("ENERGY_STOLEN_PERCENTAGE -> {0}".format(self.__ENERGY_STOLEN_PERCENTAGE), self.__debug)

        utils.log_info("_______________", self.__debug)
        utils.log_info("Performing USER ENERGY Balancing", self.__debug)

        try:
            #applications = utils.get_structures(self.__couchdb_handler, self.__debug, subtype="application")
            users = self.__couchdb_handler.get_users()
        except requests.exceptions.HTTPError as e:
            utils.log_error("Couldn't get users and/or applications", self.__debug)
            utils.log_error(str(e), self.__debug)
            return

        #self.update_user_used_energy(applications, users)

        if rebalance_users:
            self.__inter_user_rebalancing(users)

        utils.log_info("_______________\n", self.__debug)
