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
from src.ReBalancer.BaseRebalancer import BaseRebalancer


class UserRebalancer(BaseRebalancer):

    REBALANCING_LEVEL = "user"

    def __init__(self, couchdb_handler):
        super().__init__(couchdb_handler)

    @staticmethod
    def select_donated_field(resource):
        return "max"

    @staticmethod
    def get_donor_slice_key(structure, resource):
        # Users can donate to and receive from any other user
        return "all"

    @staticmethod
    def get_best_fit_child(scalable_users, resource, amount):
        raise NotImplementedError("Users do not have a parent structure (maybe hosts in the future)")

    def is_donor(self, data):
        return (data["max"] - data["usage"]) > (self.diff_percentage * data["max"])

    def is_receiver(self, data):
        return (data["max"] - data["usage"]) < (self.diff_percentage * data["max"])

    def rebalance_users(self, users):
        utils.log_info("------------------------ USER BALANCING -----------------------", self.debug)
        user_requests, final_user_requests = {}, {}

        # Filter only users that have at least one application running
        if self.only_running:
            users = [user for user in users if any(app.get("running", False) for app in user.get("clusters", []))]

        if not users:
            utils.log_warning("No {0} users to rebalance".format("running" if self.only_running else "registered"), self.debug)
            return final_user_requests

        self.pair_swapping(users, user_requests)
        final_user_requests = self.send_final_requests(user_requests)

        return final_user_requests
