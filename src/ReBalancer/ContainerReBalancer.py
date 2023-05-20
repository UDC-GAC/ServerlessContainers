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

import time
import traceback

import requests
from json_logic import jsonLogic

from src.MyUtils.MyUtils import log_info, get_config_value, log_error, log_warning, get_structures
from src.ReBalancer.Utils import CONFIG_DEFAULT_VALUES, app_can_be_rebalanced
from src.StateDatabase import opentsdb
from src.StateDatabase import couchdb

BDWATCHDOG_CONTAINER_METRICS = ['proc.cpu.user', 'proc.cpu.kernel']
GUARDIAN_CONTAINER_METRICS = {
    'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel']}

SWAP_SLICE_AMOUNT = 20

class ContainerRebalancer:
    def __init__(self):
        self.__opentsdb_handler = opentsdb.OpenTSDBServer()
        self.__couchdb_handler = couchdb.CouchDBServer()
        self.__NO_METRIC_DATA_DEFAULT_VALUE = self.__opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE

    def set_conf(self, config):
        self.__config = config
        self.window_difference = config.get_value("WINDOW_TIMELAPSE")
        self.window_delay = config.get_value("WINDOW_DELAY")
        self.debug = config.get_value("DEBUG")

    # @staticmethod
    # def __generate_request(structure_name, amount, resource, action):
    #     request = dict(
    #         type="request",
    #         resource=resource,
    #         amount=int(amount),
    #         structure=structure_name,
    #         action=action,
    #         timestamp=int(time.time()))
    #     return request

    def __get_container_usages(self, container):

        try:
            # Remote database operation
            usages = self.__opentsdb_handler.get_structure_timeseries({"host": container["name"]},
                                                                      self.window_difference,
                                                                      self.window_delay,
                                                                      BDWATCHDOG_CONTAINER_METRICS,
                                                                      GUARDIAN_CONTAINER_METRICS)

            # Skip this structure if all the usage metrics are unavailable
            if all([usages[metric] == self.__NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
                log_warning("container: {0} has no usage data".format(container["name"]), self.debug)
                return None

            return usages
        except Exception as e:
            log_error("error with structure: {0} {1} {2}".format(container["name"], str(e), str(traceback.format_exc())),
                      self.debug)

            return None

    def __fill_containers_with_usage_info(self, containers):
        # Get the usages
        containers_with_resource_usages = list()
        for container in containers:
            usages = self.__get_container_usages(container)
            if usages:
                for usage_metric in usages:
                    keys = usage_metric.split(".")
                    # Split the key from the retrieved data, e.g., structure.mem.usages, where mem is the resource
                    container["resources"][keys[1]][keys[2]] = usages[usage_metric]
                containers_with_resource_usages.append(container)
        return containers_with_resource_usages

    def __get_container_donors(self, containers):
        donors = list()
        for container in containers:
            try:
                data = {"cpu": {"structure": {"cpu": {
                    "usage": container["resources"]["cpu"]["usage"],
                    "min": container["resources"]["cpu"]["min"],
                    "max": container["resources"]["cpu"]["max"],
                    "current": container["resources"]["cpu"]["current"]}}}}
            except KeyError:
                continue

            # containers that have low resource usage (donors)
            rule_low_usage = self.__couchdb_handler.get_rule("default", "cpu_usage_low")
            if jsonLogic(rule_low_usage["rule"], data):
                donors.append(container)
        return donors

    def __get_container_receivers(self, containers):
        receivers = list()
        for container in containers:
            try:
                data = {"cpu": {"structure": {"cpu": {
                    "usage": container["resources"]["cpu"]["usage"],
                    "min": container["resources"]["cpu"]["min"],
                    "max": container["resources"]["cpu"]["max"],
                    "current": container["resources"]["cpu"]["current"]}}}}
            except KeyError:
                continue

            # containers that have a bottleneck (receivers)
            rule_high_usage = self.__couchdb_handler.get_rule("default", "cpu_usage_high")
            if jsonLogic(rule_high_usage["rule"], data):
                receivers.append(container)
        return receivers


    def __rebalance_containers_by_pair_swapping(self, containers, app_name):
        # Filter the containers between donors and receivers, according to usage and rules
        donors = self.__get_container_donors(containers)
        receivers = self.__get_container_receivers(containers)

        log_info("Nodes that will give: {0}".format(str([c["name"] for c in donors])), self.debug)
        log_info("Nodes that will receive:  {0}".format(str([c["name"] for c in receivers])), self.debug)

        if not receivers:
            log_info("No containers in need of rebalancing for {0}".format(app_name), self.debug)
            return
        else:
            # Order the containers from lower to upper current CPU limit
            receivers = sorted(receivers, key=lambda c: c["resources"]["cpu"]["current"])

        # Steal resources from the low-usage containers (givers), create 'slices' of resources
        donor_slices = list()
        id = 0
        for container in donors:
            # Ensure that this request will be successfully processed, otherwise we are 'giving' away extra resources
            current_value = container["resources"]["cpu"]["current"]
            min_value = container["resources"]["cpu"]["min"]
            usage_value = container["resources"]["cpu"]["usage"]
            stolen_amount = 0.5 * (current_value - max(min_value,  usage_value))

            acum = 0
            while acum + SWAP_SLICE_AMOUNT < stolen_amount:
                donor_slices.append((container, SWAP_SLICE_AMOUNT, id))
                acum += SWAP_SLICE_AMOUNT
                id += 1

            # Remaining
            if acum < stolen_amount:
                donor_slices.append((container, int(stolen_amount-acum), id))
                acum += SWAP_SLICE_AMOUNT
                id += 1

        donor_slices = sorted(donor_slices, key=lambda c: c[1])
        print("Donor slices are")
        for c in donor_slices:
            print(c[0]["name"], c[1])

        # Remove those donors that are of no use (there are no possible receivers for them)
        viable_donors = list()
        for c in donor_slices:
            viable = False
            for r in receivers:
                if r["host"] == c[0]["host"]:
                    viable = True
                    break
            if viable:
                viable_donors.append(c)
        print("VIABLE donor slices are")
        for c in viable_donors:
            print(c[0]["name"], c[1], c[2])
        donor_slices = viable_donors

        # Give the resources to the bottlenecked containers
        requests = dict()
        while donor_slices:
            print("Donor slices are")
            for c in donor_slices:
                print(c[0]["name"], c[1], c[2])

            for receiver in receivers:
                # Look for a donor container on the same host
                amount_to_scale, donor, id = None, None, None
                for c, amount, i in donor_slices:
                    if c["host"] == receiver["host"]:
                        amount_to_scale = amount
                        donor = c
                        id = i
                        break

                if not amount_to_scale:
                    log_info("No more donors on its host, container {0} left out".format(receiver["name"]), self.debug)
                    continue

                # Remove this slice from the list
                donor_slices = list(filter(lambda x: x[2] != id, donor_slices))

                max_receiver_amount = receiver["resources"]["cpu"]["max"] - receiver["resources"]["cpu"]["current"]
                # If this container can't be scaled anymore, skip
                if max_receiver_amount == 0:
                    continue

                # Trim the amount to scale if needed
                if amount_to_scale > max_receiver_amount:
                    amount_to_scale = max_receiver_amount

                # Create the pair of scaling requests
                # TODO This should use Guardians method to generate requests
                request = dict(
                    type="request",
                    resource="cpu",
                    amount=int(amount_to_scale),
                    structure=receiver["name"],
                    action="CpuRescaleUp",
                    timestamp=int(time.time()),
                    structure_type="container",
                    host=receiver["host"],
                    host_rescaler_ip=receiver["host_rescaler_ip"],
                    host_rescaler_port=receiver["host_rescaler_port"]
                )

                if receiver["name"] not in requests:
                    requests[receiver["name"]] = list()
                requests[receiver["name"]].append(request)

                # TODO This should use Guardians method to generate requests
                request = dict(
                    type="request",
                    resource="cpu",
                    amount=int(-amount_to_scale),
                    structure=donor["name"],
                    action="CpuRescaleDown",
                    timestamp=int(time.time()),
                    structure_type="container",
                    host=donor["host"],
                    host_rescaler_ip=donor["host_rescaler_ip"],
                    host_rescaler_port=donor["host_rescaler_port"]
                )

                if donor["name"] not in requests:
                    requests[donor["name"]] = list()
                requests[donor["name"]].append(request)
                log_info("Resource swap between {0}(donor) and {1}(receiver)".format(donor["name"], receiver["name"]), self.debug)

        log_info("No more donors", self.debug)

        final_requests = list()
        for container in requests:
            # Copy the first request as the base request
            flat_request = dict(requests[container][0])
            flat_request["amount"] = 0
            for request in requests[container]:
                flat_request["amount"] += request["amount"]
            final_requests.append(flat_request)

        log_info("REQUESTS ARE:", self.debug)
        for c in requests.values():
            for r in c:
                print(r)

        # TODO
        # Adjust requests amounts according to the maximums (trim), otherwise the scaling down will be performed but not the scaling up, and shares will be lost

        log_info("FINAL REQUESTS ARE:", self.debug)
        for r in final_requests:
            print(r)
            self.__couchdb_handler.add_request(r)


    def __app_containers_can_be_rebalanced(self, application):
        return app_can_be_rebalanced(application, "container", self.__couchdb_handler)

    def rebalance_containers(self, config):
        log_info("_______________", self.debug)
        log_info("Performing CONTAINER CPU Balancing", self.debug)

        # Get the containers and applications
        try:
            applications = get_structures(self.__couchdb_handler, self.debug, subtype="application")
            containers = get_structures(self.__couchdb_handler, self.debug, subtype="container")
        except requests.exceptions.HTTPError as e:
            log_error("Couldn't get applications", self.debug)
            log_error(str(e), self.debug)
            return

        # Filter out the ones that do not accept rebalancing or that do not need any internal rebalancing
        rebalanceable_apps = list()
        for app in applications:
            # TODO Improve this management
            if "rebalance" not in app or app["rebalance"] == True:
                pass
            else:
                continue
            if len(app["containers"]) <= 1:
                continue

            if self.__app_containers_can_be_rebalanced(app):
                rebalanceable_apps.append(app)

        # Sort them according to each application they belong
        app_containers = dict()
        for app in rebalanceable_apps:
            app_name = app["name"]
            app_containers[app_name] = list()
            app_containers_names = app["containers"]
            for container in containers:
                if container["name"] in app_containers_names:
                    app_containers[app_name].append(container)
            # Get the container usages
            app_containers[app_name] = self.__fill_containers_with_usage_info(app_containers[app_name])

        # Rebalance applications
        for app in rebalanceable_apps:
            app_name = app["name"]
            log_info("Going to rebalance {0} now".format(app_name), self.debug)
            self.__rebalance_containers_by_pair_swapping(app_containers[app_name], app_name)

        log_info("_______________", self.debug)
