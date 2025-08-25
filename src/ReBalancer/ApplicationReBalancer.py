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
from src.ReBalancer.Utils import app_can_be_rebalanced


class ApplicationRebalancer:

    def __init__(self, couchdb_handler):
        self.__config = None
        self.__couchdb_handler = couchdb_handler
        self.__debug = True

    def set_config(self, config):
        self.__config = config

    def __static_rebalancing(self, user, applications):
        for resource in self.__config.get_value("RESOURCES_BALANCED"):
            # Get user limit for this resource
            user_resource_limit = user[resource]["max"]

            # Add up all the shares
            # TODO: Check what's shares
            total_shares = sum([app["resources"][resource]["shares"] for app in applications])

            # For each application calculate the resource limit according to its shares
            for app in applications:
                percentage = app["resources"][resource]["shares"] / total_shares
                new_app_limit = int(user_resource_limit * percentage)
                app_current_limit = app["resources"][resource]["max"]  # TODO: Check if "current" should be used

                # If the database record and the new limit are not the same, update
                if app_current_limit != new_app_limit:
                    app["resources"][resource]["max"] = new_app_limit
                    self.__couchdb_handler.update_structure(app)
                    utils.log_info("Updated resource '{0}' limit for app {1}".format(resource, app["name"]), self.__debug)

                utils.log_info("Processed app {0} with a resource '{1}' share of {2}%, new limit is {3}".format(
                                app["name"], resource, str("%.2f" % (100 * percentage)), new_app_limit), self.__debug)

    def __pair_swapping(self, applications):
        for resource in self.__config.get_value("RESOURCES_BALANCED"):
            donors, receivers = list(), list()
            for app in applications:
                if app_can_be_rebalanced(app, resource, "application", self.__couchdb_handler):
                    diff = app["resources"][resource]["max"] - app["resources"][resource]["usage"]
                    if diff > self.__config.get_value("DIFF_PERCENTAGE") * app["resources"][resource]["max"]:
                        donors.append(app)
                    else:
                        receivers.append(app)

            if not receivers:
                utils.log_info("No applications in need of rebalancing for resource '{0}'".format(resource), self.__debug)
                continue

            # Order apps from lower to upper resource limit
            receivers = sorted(receivers, key=lambda c: c["resources"][resource]["current"])

            shuffling_tuples = list()
            for app in donors:
                diff = app["resources"][resource]["max"] - app["resources"][resource]["usage"]
                stolen_amount = self.__config.get_value("STOLEN_PERCENTAGE") * diff
                shuffling_tuples.append((app, stolen_amount))
            shuffling_tuples = sorted(shuffling_tuples, key=lambda c: c[1])

            # Give the resources to the bottlenecked applications
            for receiver in receivers:

                if shuffling_tuples:
                    donor, amount_to_scale = shuffling_tuples.pop(0)
                else:
                    utils.log_info("No more donors, app {0} left out".format(receiver["name"]), self.__debug)
                    continue

                donor["resources"][resource]["max"] -= amount_to_scale
                receiver["resources"][resource]["max"] += amount_to_scale

                utils.update_structure(donor, self.__couchdb_handler, self.__debug)
                utils.update_structure(receiver, self.__couchdb_handler, self.__debug)

                utils.log_info("Resource {0} swap between {1} (donor) and {2} (receiver) with amount {3}".format(
                                resource, donor["name"], receiver["name"], amount_to_scale), self.__debug)

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
            user_apps = [app for app in applications if app["name"] in user["clusters"]]
            # if "energy_policy" not in user:
            #     balancing_policy = "static"
            #     utils.log_info(
            #         "Energy balancing policy unset for user {0}, defaulting to 'static'".format(user["name"]),
            #         self.__debug)
            # else:
            #     balancing_policy = user["energy_policy"]
            #utils.log_info("User {0} has {1} policy".format(user["name"], balancing_policy), self.__debug)

            if self.__config.get_value("BALANCING_METHOD") == "static":
                self.__static_rebalancing(user, user_apps)

            elif self.__config.get_value("BALANCING_METHOD") == "pair_swapping":
                self.__pair_swapping(user_apps)

            else:
                utils.log_error("Unknown application balancing method '{0}'".format(self.__config.get_value("BALANCING_METHOD")), self.__debug)

        utils.log_info("_______________\n", self.__debug)
