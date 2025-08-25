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

from json_logic import jsonLogic

import src.MyUtils.MyUtils as utils

def app_can_be_rebalanced(application, resource, rebalancing_level, couchdb_handler):
    try:
        _ = {
                "cpu":
                    {"structure":
                         {"cpu":
                              {"usage": application["resources"][resource]["usage"],
                               "min": application["resources"][resource]["min"],
                               "current": application["resources"][resource]["current"]}}}
                }
    except KeyError:
        return False

    # TODO: Review this, now it simply enables container balancing and disables app balancing
    # This was supossed to filter the following scenarios:
    # 1. ContainerRebalancer: Application is overusing energy, so Guardian must scale containers to deal with it
    # 2. ContainerRebalancer: Application is underusing energy, so Guardian must scale containers to deal with it
    # 3. ApplicationRebalancer: Application is overusing energy, so it may be a receiver for dynamic energy rebalancing
    # 4. ApplicationRebalancer: Application is underusing energy, so it may be a donor for dynamic energy rebalancing
    # Now ContainerRebalancer does not check app limits, so we dont need this filter

    # 5. ContainerRebalancer: Application is in the middle area of energy utilization, rebalance containers within app
    # 6. ApplicationRebalancer: Application is in the middle area of energy utilization, don't rebalance app (is already balanced)
    # Now Application Rebalancer will check app limits to see if it is in the middle
    # Regarding ContainerRebalancer, it also checks this with other methods

    # Maybe we could create a similar method like this but taking into account new techniques

    #    but it is an application rebalancing
    # rule_low_usage = couchdb_handler.get_rule("energy_exceeded_upper")
    # if jsonLogic(rule_low_usage["rule"], data):
    #     # Application is overusing energy
    #     if rebalancing_level == "container":
    #         # Let the Guardian or the dynamic energy balancing deal with it
    #         return False
    #     elif rebalancing_level == "application":
    #         # It may be a receiver for dynamic energy rebalancing
    #         return True
    #
    # rule_high_usage = couchdb_handler.get_rule("energy_dropped_lower")
    # if jsonLogic(rule_high_usage["rule"], data):
    #     # Application is underusing energy
    #     if rebalancing_level == "container":
    #         # Let the Guardian or the dynamic energy balancing deal with it
    #         return False
    #         # It may be a donor for dynamic energy rebalancing
    #     elif rebalancing_level == "application":
    #         return True

    # The application is in the middle area of energy utilization
    if rebalancing_level == "container":
        # Perform an internal balancing through container cpu limit rebalancing
        return True
    elif rebalancing_level == "application":
        # It may need internal container rebalancing
        return False


def filter_rebalanceable_apps(applications, rebalancing_level, couchdb_handler):
    rebalanceable_apps = list()

    # If a bad rebalancing level is specified, no app will be balanced
    if rebalancing_level not in ["container", "application"]:
        utils.log_error("Invalid app rebalancing level '{0}'".format(rebalancing_level), debug=True)
        return rebalanceable_apps

    for app in applications:
        # Unless otherwise specified, all applications are rebalanced
        if "rebalance" in app and not app["rebalance"]:
            continue
        # Single-container applications do not need rebalancing
        if len(app["containers"]) <= 1:
            continue
        # If app match the criteria, it is added to the list
        if app_can_be_rebalanced(app, rebalancing_level, couchdb_handler):
            rebalanceable_apps.append(app)

    return rebalanceable_apps