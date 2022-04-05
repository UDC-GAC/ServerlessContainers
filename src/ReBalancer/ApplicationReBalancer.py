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

from src.MyUtils import MyUtils
from src.ReBalancer.Utils import CONFIG_DEFAULT_VALUES, app_can_be_rebalanced, get_user_apps
from src.StateDatabase import couchdb


class ApplicationRebalancer:
    def __init__(self):
        self.__couchdb_handler = couchdb.CouchDBServer()
        self.__debug = True
        self.__config = {}
        self.__ENERGY_DIFF_PERCENTAGE = 0.20
        self.__ENERGY_STOLEN_PERCENTAGE = 0.20

    def __app_energy_can_be_rebalanced(self, application):
        return app_can_be_rebalanced(application, "application", self.__couchdb_handler)

    def __static_app_rebalancing(self, applications, max_energy):
        # Add up all the shares
        total_shares = sum([app["resources"]["energy"]["shares"] for app in applications])

        # For each application calculate the energy according to its shares
        for app in applications:
            percentage = app["resources"]["energy"]["shares"] / total_shares

            limit_energy = int(max_energy * percentage)
            current_energy = app["resources"]["energy"]["max"]

            # If the database record and the new limit are not the same, update
            if current_energy != limit_energy:
                app["resources"]["energy"]["max"] = limit_energy
                self.__couchdb_handler.update_structure(app)
                MyUtils.log_info("Updated energy limit of app {0}".format(app["name"]), self.__debug)

            # MyUtils.log_info("Processed app {0} with an energy share of {1}% and {2} Watts".format(
            #     app["name"], str("%.2f" % (100 * percentage)), limit_energy), self.__debug)

    def __dynamic_app_rebalancing(self, applications):
        donors, receivers = list(), list()
        for app in applications:
            if self.__app_energy_can_be_rebalanced(app):
                diff = app["resources"]["energy"]["max"] - app["resources"]["energy"]["usage"]
                if diff > self.__ENERGY_DIFF_PERCENTAGE * app["resources"]["energy"]["max"]:
                    donors.append(app)
                else:
                    receivers.append(app)

        if not receivers:
            MyUtils.log_info("No app to give energy shares", self.__debug)
            return
        else:
            # Order the apps from lower to upper energy limit
            apps_to_receive = sorted(receivers, key=lambda c: c["resources"]["energy"]["max"])

        shuffling_tuples = list()
        for app in donors:
            diff = app["resources"]["energy"]["max"] - app["resources"]["energy"]["usage"]
            stolen_amount = self.__ENERGY_STOLEN_PERCENTAGE * diff
            shuffling_tuples.append((app, stolen_amount))
        shuffling_tuples = sorted(shuffling_tuples, key=lambda c: c[1])

        # Give the resources to the bottlenecked applications
        for receiver in apps_to_receive:

            if shuffling_tuples:
                donor, amount_to_scale = shuffling_tuples.pop(0)
            else:
                MyUtils.log_info("No more donors, app {0} left out".format(receiver["name"]), self.__debug)
                continue

            donor["resources"]["energy"]["max"] -= amount_to_scale
            receiver["resources"]["energy"]["max"] += amount_to_scale

            MyUtils.update_structure(donor, self.__couchdb_handler, self.__debug)
            MyUtils.update_structure(receiver, self.__couchdb_handler, self.__debug)

            MyUtils.log_info(
                "Energy swap between {0}(donor) and {1}(receiver)".format(donor["name"], receiver["name"]),
                self.__debug)

    def rebalance_applications(self, config):
        self.__config = config
        self.__debug = MyUtils.get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "DEBUG")
        MyUtils.log_info("_______________", self.__debug)
        MyUtils.log_info("Performing APP ENERGY Balancing", self.__debug)

        try:
            applications = MyUtils.get_structures(self.__couchdb_handler, self.__debug, subtype="application")
            users = self.__couchdb_handler.get_users()
        except requests.exceptions.HTTPError as e:
            MyUtils.log_error("Couldn't get users and/or applications", self.__debug)
            MyUtils.log_error(str(e), self.__debug)
            return

        for user in users:
            MyUtils.log_info("Processing user {0}".format(user["name"]), self.__debug)
            user_apps = get_user_apps(applications, user)
            if "energy_policy" not in user:
                balancing_policy = "static"
                MyUtils.log_info(
                    "Energy balancing policy unset for user {0}, defaulting to 'static'".format(user["name"]),
                    self.__debug)
            else:
                balancing_policy = user["energy_policy"]

            MyUtils.log_info("User {0} has {1} policy".format(user["name"], balancing_policy), self.__debug)
            if balancing_policy == "static":
                max_energy = user["energy"]["max"]
                self.__static_app_rebalancing(user_apps, max_energy)

            elif balancing_policy == "dynamic":
                self.__dynamic_app_rebalancing(user_apps)

            else:
                MyUtils.log_error("Unkwnown energy balancing policy '{0}'".format(balancing_policy), self.__debug)

        MyUtils.log_info("_______________\n", self.__debug)
