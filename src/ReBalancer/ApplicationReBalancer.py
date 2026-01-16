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

    @staticmethod
    def get_best_fit_child(scalable_apps, resource, amount):
        return utils.get_best_fit_app(scalable_apps, resource, amount)

    def is_donor(self, data):
        return (data["max"] - data["usage"]) > (self.diff_percentage * data["max"])

    def is_receiver(self, data):
        return (data["max"] - data["usage"]) < (self.diff_percentage * data["max"])

    def process_user_requests(self, users, user_requests, applications):
        for user in users:
            user_request = user_requests.get(user["name"], {})
            user_apps = [app for app in applications if app["name"] in user.get("clusters", [])]
            if user_request and user_apps:
                self.simulate_scaler_request_processing(user["name"], user_apps, user_request)

    def filter_rebalanceable_apps(self, applications):
        rebalanceable_apps = []
        for app in applications:
            # Unless otherwise specified, all applications are rebalanced
            if not app.get("rebalance", True):
                continue

            # Check applications are consistent before performing a rebalance
            if not self.app_state_is_valid(app):
                utils.log_warning("Inconsistent state for app {0}, it probably started too recently".format(app["name"]), self.debug)
                continue

            # If app match the criteria, it is added to the list
            rebalanceable_apps.append(app)

        return rebalanceable_apps

    def rebalance_applications(self, users, user_requests, applications):
        utils.log_info("-------------------- APPLICATION BALANCING --------------------", self.debug)
        final_app_requests = {}

        # First check if there are user requests to be processed
        self.process_user_requests(users, user_requests, applications)

        applications = self.filter_rebalanceable_apps(applications)
        if self.only_running:
            applications = [app for app in applications if app.get("running", False)]

        if not applications:
            utils.log_warning("No {0} applications to rebalance".format("running" if self.only_running else "registered"), self.debug)
            return final_app_requests

        if users:
            for user in users:
                app_requests = {}
                user_apps = [app for app in applications if app["name"] in user["clusters"]]
                utils.log_info("Processing user {0} who has {1} valid applications registered".format(user["name"], len(user_apps)), self.debug)
                if user_apps:
                    self.pair_swapping(user_apps, app_requests)
                final_app_requests.update(self.send_final_requests(app_requests))
        else:
            app_requests = {}
            self.pair_swapping(applications, app_requests)
            final_app_requests = self.send_final_requests(app_requests)

        return final_app_requests
