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

    def __static_rebalancing(self, user, applications):
        for resource in self.__config.get_value("RESOURCES_BALANCED"):
            # Get user "max" limit for this resource
            user_max = user["resources"][resource]["max"]

            # Filter applications that have the required fields
            valid_apps = [app for app in applications if has_required_fields(app, resource, ["max", "shares"])]

            # Add up all the shares
            total_shares = sum([app["resources"][resource]["shares"] for app in valid_apps])

            # For each application calculate the resource limit according to its shares
            for app in valid_apps:
                percentage = app["resources"][resource]["shares"] / total_shares
                new_app_max = int(user_max * percentage)
                app_max = app["resources"][resource]["max"]

                # If the database record and the new limit are not the same, update
                if app_max != new_app_max:
                    app["resources"][resource]["max"] = new_app_max
                    self.__couchdb_handler.update_structure(app)
                    utils.log_info("Updated resource '{0}' max limit for app {1}".format(resource, app["name"]), self.__debug)

                utils.log_info("Processed app {0} with a resource '{1}' share of {2}%, new limit is {3}".format(
                                app["name"], resource, str("%.2f" % (100 * percentage)), new_app_max), self.__debug)

    def rebalance_applications(self):
        self.__debug = self.__config.get_value("DEBUG")

        utils.log_info("_______________", self.__debug)
        utils.log_info("Performing APP Balancing", self.__debug)

        try:
            applications = utils.get_structures(self.__couchdb_handler, self.__debug, subtype="application")
            users = self.__couchdb_handler.get_users()
        except requests.exceptions.HTTPError as e:
            utils.log_error("Couldn't get users and/or applications: {0}".format(str(e)), self.__debug)
            return

        for user in users:
            utils.log_info("Processing user {0}".format(user["name"]), self.__debug)

            balancing_method = user.get("balancing_method", None)
            if not balancing_method:
                balancing_method = "pair_swapping"
                utils.log_info("User {0} has no balancing method, using default: {1}".format(user["name"], balancing_method), self.__debug)
            else:
                utils.log_info("User {0} has set {1} balancing method".format(user["name"], balancing_method), self.__debug)

            user_apps = [app for app in applications if app["name"] in user["clusters"]]
            if balancing_method == "static":
                self.__static_rebalancing(user, user_apps)

            elif balancing_method == "pair_swapping":
                pair_swapping(user_apps, self.__config.get_value("RESOURCES_BALANCED"), self.__config.get_value("DIFF_PERCENTAGE"),
                              self.__config.get_value("STOLEN_PERCENTAGE"), self.__couchdb_handler, self.__debug)

            else:
                utils.log_error("Unknown application balancing method '{0}'".format(balancing_method), self.__debug)

        utils.log_info("_______________\n", self.__debug)
