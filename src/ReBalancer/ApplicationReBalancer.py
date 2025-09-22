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
from copy import deepcopy

import src.MyUtils.MyUtils as utils
from src.ReBalancer.BaseRebalancer import BaseRebalancer


class ApplicationRebalancer(BaseRebalancer):

    REBALANCING_LEVEL = "application"

    def __init__(self, couchdb_handler):
        super().__init__(couchdb_handler)

    @staticmethod
    def select_donated_field(resource):
        return "max"

    @staticmethod
    def get_donor_slice_key(structure, resource):
        # Applications can donate to and receive from any other application
        return "all"

    def is_donor(self, data):
        return (data["max"] - data["usage"]) > (self.diff_percentage * data["max"])

    def is_receiver(self, data):
        return (data["max"] - data["usage"]) < (self.diff_percentage * data["max"])

    def rebalance_applications(self):
        utils.log_info("-------------------- APPLICATION BALANCING --------------------", self.debug)

        applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
        original_apps = deepcopy(applications)
        users = []
        try:
            users = self.couchdb_handler.get_users()
        except requests.exceptions.HTTPError:
            utils.log_warning("No registered users were found on the platform, all the applications will be balanced as a single cluster", self.debug)

        # Distribute user limit across applications if user_max != sum(app_max)
        requests_by_user = {}
        for user in users:
            requests_by_user[user["name"]] = {}
            user_apps = [app for app in applications if app["name"] in user["clusters"]]
            if user_apps:
                self.distribute_parent_limit(user, user_apps, requests_by_user[user["name"]])

        applications = self.filter_rebalanceable_apps(applications)
        # If we want to distribute user limit only across running applications move this condition above
        if self.only_running:
            applications = [app for app in applications if app.get("running", False)]

        if not applications:
            utils.log_warning("No {0} applications to rebalance".format("running" if self.only_running else "registered"), self.debug)
            return

        if users:
            for user in users:
                user_apps = [app for app in applications if app["name"] in user["clusters"]]
                utils.log_info("Processing user {0} who has {1} valid applications registered".format(user["name"], len(user_apps)), self.debug)
                if user_apps:
                    self.pair_swapping(user_apps, requests_by_user.get(user["name"], {}))
                self.send_final_requests(original_apps, requests_by_user.get(user["name"], {}))
        else:
            _requests = {}
            self.pair_swapping(applications, _requests)
            self.send_final_requests(original_apps, _requests)

