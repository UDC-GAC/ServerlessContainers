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

from src.MyUtils.MyUtils import log_info, debug_info, get_config_value, log_error, log_warning, get_structures, \
                                generate_request, get_container_usages
from src.ReBalancer.Utils import CONFIG_DEFAULT_VALUES, filter_rebalanceable_apps
from src.StateDatabase import opentsdb
from src.StateDatabase import couchdb


class ContainerRebalancer:

    def __init__(self):
        self.__opentsdb_handler = opentsdb.OpenTSDBServer()
        self.__couchdb_handler = couchdb.CouchDBServer()
        self.__NO_METRIC_DATA_DEFAULT_VALUE = self.__opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.__debug = True
        self.__config = {}

    @staticmethod
    def __split_amount_in_slices(total_amount, slice_amount):
        number_of_slices = total_amount // slice_amount
        last_slice_amount = total_amount % slice_amount
        slices = [slice_amount for _ in range(number_of_slices)]
        if last_slice_amount > 0:
            slices.append(last_slice_amount)
        return slices

    def __print_donors_and_receivers(self, donors, receivers):
        log_info("Nodes that will give: {0}".format(str([c["name"] for c in donors])), self.__debug)
        log_info("Nodes that will receive:  {0}".format(str([c["name"] for c in receivers])), self.__debug)

    def __print_donor_slices(self, donor_slices, msg="Donor slices are:"):
        debug_info(msg, self.__debug)
        for host in donor_slices:
            for donor, slice_amount in donor_slices[host]:
                debug_info("({0})\t{1}\t{2}".format(host, donor["name"], slice_amount), self.__debug)

    def __fill_containers_with_usage_info(self, resources, containers):
        containers_with_usages = list()
        for container in containers:
            # Get the usages for each balanced resource
            usages = get_container_usages(resources, container, self.__window_difference,
                                          self.__window_delay, self.__opentsdb_handler, self.__debug)
            # Save data following the format ["resources"][<resource>]["usage"]
            # e.g., structure.mem.usage -> container["resources"]["mem"]["usage"]
            if usages:
                for usage_metric in usages:
                    # Split the key from the retrieved data
                    keys = usage_metric.split(".")
                    if keys[1] == "disk" and "disk" not in container["resources"]: continue
                    if keys[1] == "energy" and "energy" not in container["resources"]: continue
                    container["resources"][keys[1]][keys[2]] = usages[usage_metric]
                containers_with_usages.append(container)
        return containers_with_usages

    def __filter_containers_by_role(self, role, resource, containers):
        filtered_containers = list()

        # Check filter is valid
        if role not in ["donors", "receivers"]:
            log_warning("Invalid role '{0}' for containers. It must be donors or receivers.".format(role), self.__debug)
            return filtered_containers

        # Try getting the rule
        rule_type = "low" if role == "donors" else "high"
        try:
            rule = self.__couchdb_handler.get_rule("{0}_usage_{1}".format(resource, rule_type))
        except ValueError as e:
            log_warning("No rule found for {0} usage {1}: {2}".format(resource, rule_type, str(e)), self.__debug)
            return filtered_containers

        for container in containers:
            try:
                data = {resource: {"structure": {resource: {
                    "usage": container["resources"][resource]["usage"],
                    "min": container["resources"][resource]["min"],
                    "max": container["resources"][resource]["max"],
                    "current": container["resources"][resource]["current"]}}}}
            except KeyError:
                continue

            # Check if container activate the rule: it has low resource usage (donors) or a bottleneck (receivers)
            if jsonLogic(rule["rule"], data):
                filtered_containers.append(container)
        return filtered_containers

    def __generate_scaling_request(self, container, resource, amount_to_scale, requests):
        request = generate_request(container, int(amount_to_scale), resource)
        if container["name"] not in requests:
            requests[container["name"]] = list()
        requests[container["name"]].append(request)

        if amount_to_scale > 0:  # Receiver
            log_info("Node {0} will receive: {1}".format(container["name"], amount_to_scale), self.__debug)
        elif amount_to_scale < 0:  # Donor
            log_info("Node {0} will give: {1}".format(container["name"], amount_to_scale), self.__debug)
        else:
            log_info("Node {0} doesn't need to scale".format(container["name"]), self.__debug)

    def __send_final_requests(self, requests):
        final_requests = list()
        for container in requests:
            # Copy the first request as the base request
            flat_request = dict(requests[container][0])
            flat_request["amount"] = 0
            for request in requests[container]:
                flat_request["amount"] += request["amount"]
            final_requests.append(flat_request)

        log_info("REQUESTS ARE:", self.__debug)
        for c in requests.values():
            for r in c:
                print(r)

        # TODO
        # Adjust requests amounts according to the maximums (trim), otherwise the scaling down will be performed but not the scaling up, and shares will be lost

        log_info("FINAL REQUESTS ARE:", self.__debug)
        for r in final_requests:
            print(r)
            self.__couchdb_handler.add_request(r)

    ## Balancing methods
    # Apps by pair swapping
    def __rebalance_containers_by_pair_swapping(self, containers, app_name):

        balanceable_resources = {"cpu"}

        for resource in self.__resources_balanced:

            if resource not in balanceable_resources:
                log_warning("'{0}' not yet supported in app '{1}' balancing, only '{2}' available at the moment".format(
                    resource, self.__balancing_method, list(balanceable_resources)), self.__debug)
                continue

            # Filter the containers between donors and receivers, according to usage and rules
            donors = self.__filter_containers_by_role("donors", resource, containers)
            receivers = self.__filter_containers_by_role("receivers", resource, containers)

            if not receivers:
                log_info("No containers in need of rebalancing for {0}".format(app_name), self.__debug)
                continue

            # Print info about current donors and receivers
            self.__print_donors_and_receivers(donors, receivers)

            # Order the containers from lower to upper current resource limit
            receivers = sorted(receivers, key=lambda c: c["resources"][resource]["current"])

            # Steal resources from the low-usage containers (donors), create 'slices' of resources
            donor_slices = dict()
            for container in donors:
                # Ensure this request will be successfully processed, otherwise we are 'giving' away extra resources
                current_value = container["resources"]["cpu"]["current"]
                min_value = container["resources"]["cpu"]["min"]
                usage_value = container["resources"]["cpu"]["usage"]
                host = container["host"]
                stolen_amount = 0.5 * (current_value - max(min_value,  usage_value))

                # Divide the total amount to donate in slices of 25 units
                for slice_amount in self.__split_amount_in_slices(stolen_amount, 25):
                    try:
                        donor_slices[host].append((container, slice_amount))
                    except KeyError:
                        donor_slices[host] = [(container, slice_amount)]

            # Sort slices by donated amount
            for host in donor_slices:
                donor_slices[host] = sorted(donor_slices[host], key=lambda c: c[1])

            # Print current donor slices
            self.__print_donor_slices(donor_slices)

            # Remove slices that can't be donated, as there is no receiver in the same host
            for host in donor_slices:
                if any(r["host"] == host for r in receivers):
                    del donor_slices[host]

            # Print viable donor slices
            self.__print_donor_slices(donor_slices, msg="VIABLE donor slices are:")

            # Give the resources to the bottlenecked containers
            requests = dict()
            while donor_slices:
                # Print current donor slices
                self.__print_donor_slices(donor_slices)

                for receiver in receivers:
                    receiver_host = receiver["host"]
                    if receiver_host not in donor_slices:
                        log_info("No more donors on its host ({0}), container {1} left out".format(
                            receiver_host, receiver["name"]), self.__debug)
                        continue

                    max_receiver_amount = receiver["resources"]["cpu"]["max"] - receiver["resources"]["cpu"]["current"]
                    # If this container can't be scaled anymore, skip
                    if max_receiver_amount == 0:
                        continue

                    # Get and remove one slice from the list
                    donor, amount_to_scale = donor_slices[receiver_host].pop()
                    # If no more slices left in this host, the host is removed
                    if not donor_slices[receiver_host]:
                        del donor_slices[receiver_host]

                    # Trim the amount to scale if needed
                    amount_to_scale = min(amount_to_scale, max_receiver_amount)

                    # Create the pair of scaling requests
                    self.__generate_scaling_request(receiver, resource, amount_to_scale, requests)
                    self.__generate_scaling_request(donor, resource, -amount_to_scale, requests)
                    log_info("Resource swap between {0}(donor) and {1}(receiver)".format(
                        donor["name"], receiver["name"]), self.__debug)

            log_info("No more donors", self.__debug)
            self.__send_final_requests(requests)

    # Hosts by pair swapping
    def __rebalance_host_containers_by_pair_swapping(self, containers, host):

        balanceable_resources = {"cpu": {"diff_percentage":self.__DIFF_PERCENTAGE, "stolen_percentage":self.__STOLEN_PERCENTAGE}, 
                                "disk": {"diff_percentage":self.__DIFF_PERCENTAGE, "stolen_percentage":self.__STOLEN_PERCENTAGE}
                                }

        for resource in self.__resources_balanced:

            if resource not in balanceable_resources:
                log_warning("'{0}' not yet supported in host '{1}' balancing, only '{2}' available at the moment".format(resource, self.__balancing_method, list(balanceable_resources.keys())), self.__debug)
                continue

            log_info("Going to rebalance {0} by {1}".format(resource, self.__balancing_method), self.__debug)

            requests = dict()
            donors, receivers = list(), list()

            # Filter the containers between donors and receivers
            for container in containers:
                if resource in container["resources"]:
                    diff = container["resources"][resource]["max"] - container["resources"][resource]["current"]
                    if diff < balanceable_resources[resource]["diff_percentage"] * container["resources"][resource]["max"]:
                        donors.append(container)
                    elif container["resources"][resource]["current"] - container["resources"][resource]["usage"] < balanceable_resources[resource]["diff_percentage"] * container["resources"][resource]["current"]:
                        receivers.append(container)

            if not receivers:
                log_info("No containers in need of rebalancing for {0}".format(host["name"]), self.__debug)
                continue

            # Print info about current donors and receivers
            self.__print_donors_and_receivers(donors, receivers)

            # Order the containers from lower to upper current resource limit
            receivers = sorted(receivers, key=lambda c: c["resources"][resource]["current"])

            shuffling_tuples = list()
            for donor in donors:
                stolen_amount = balanceable_resources[resource]["stolen_percentage"] * donor["resources"][resource]["current"]
                shuffling_tuples.append((donor, stolen_amount))
            shuffling_tuples = sorted(shuffling_tuples, key=lambda c: c[1])

            # Give the resources to the bottlenecked containers
            for receiver in receivers:

                max_receiver_amount = receiver["resources"][resource]["max"] - receiver["resources"][resource]["current"]
                # If this container can't be scaled anymore, skip
                if max_receiver_amount == 0:
                    continue

                if resource == "disk" and "disks" in host and host["disks"] > 1:
                    ## if host has more than one disk, each receiver can only receive from a donor on the same disk
                    i = 0
                    initial_donors = len(shuffling_tuples)
                    disk_match = False

                    while not disk_match and shuffling_tuples and i < initial_donors:
                        donor, amount_to_scale = shuffling_tuples.pop(0)
                        i += 1
                        if donor["resources"]["disk"]["name"] == receiver["resources"]["disk"]["name"]:
                            disk_match = True
                        else:
                            shuffling_tuples.append(donor, amount_to_scale)

                    if not disk_match:
                        log_info("No more donors or no donors suited for container {0}".format(receiver["name"]), self.__debug)
                        continue
                else:
                    if shuffling_tuples:
                        donor, amount_to_scale = shuffling_tuples.pop(0)
                    else:
                        log_info("No more donors, container {0} left out".format(receiver["name"]), self.__debug)
                        continue

                # Trim the amount to scale if needed
                if amount_to_scale > max_receiver_amount:
                    amount_to_scale = max_receiver_amount

                # Create the pair of scaling requests
                self.__generate_scaling_request(receiver, resource, amount_to_scale, requests)
                self.__generate_scaling_request(donor, resource, -amount_to_scale, requests)
                log_info("Resource swap between {0}(donor) and {1}(receiver) with amount {2}".format(donor["name"], receiver["name"], amount_to_scale), self.__debug)

            log_info("No more receivers", self.__debug)
            self.__send_final_requests(requests)

        log_info("_______________", self.__debug)

    # Hosts by weight
    def __rebalance_host_containers_by_weight(self, containers, host):

        balanceable_resources = {"cpu": {"diff_percentage":self.__DIFF_PERCENTAGE, "stolen_percentage":self.__STOLEN_PERCENTAGE}, 
                                "disk": {"diff_percentage":self.__DIFF_PERCENTAGE, "stolen_percentage":self.__STOLEN_PERCENTAGE}
                                }

        def get_new_allocations(resource, containers, requests):
            ## Get total allocation and weight
            total_allocation_amount = 0
            weight_sum = 0
            participants = []
            for container in containers:
                if resource in container["resources"]:
                    usage_threshold = container["resources"][resource]["current"] - container["resources"][resource]["usage"] < balanceable_resources[resource]["diff_percentage"] * container["resources"][resource]["current"]
                    if "weight" in container["resources"][resource] and usage_threshold:
                        participants.append(container)
                        total_allocation_amount += container["resources"][resource]["current"]
                        weight_sum += container["resources"][resource]["weight"]
                    # else: containers with low usage that won't participate in the distribution

            if weight_sum > 0:
                alloc_slice = total_allocation_amount / weight_sum

                ## Distribute slices between containers considering their weights
                for container in participants:
                    new_alloc = round(alloc_slice * container["resources"][resource]["weight"])

                    # TODO: consider that new_alloc may be higher than the max for some containers
                    # if new_alloc > container["resources"][resource]["max"]:
                    #     new_alloc = container["resources"][resource]["max"]
                    #     total_allocation_amount -= container["resources"][resource]["max"]
                    #     weight_sum -= container["resources"][resource]["weight"]
                    #     alloc_slice = total_allocation_amount / weight_sum

                    amount_to_scale = new_alloc - container["resources"][resource]["current"]
                    self.__generate_scaling_request(container, resource, amount_to_scale, requests)

        for resource in self.__resources_balanced:

            if resource not in balanceable_resources:
                log_warning("'{0}' not yet supported in host '{1}' balancing, only '{2}' available at the moment".format(resource, self.__balancing_method, list(balanceable_resources.keys())), self.__debug)
                continue

            log_info("Going to rebalance {0} by {1}".format(resource, self.__balancing_method), self.__debug)

            requests = dict()

            if resource == "disk" and "disks" in host and host["disks"] > 1:
                ## if host has more than one disk the balancing needs to be performed on each disk
                for disk in host["disks"]:
                    disk_containers = []
                    for container in containers:
                        if "disk" in container["resources"] and container["resources"]["disk"]["name"] == disk: disk_containers.append(container)

                    get_new_allocations(resource, disk_containers, requests)

            else:
                get_new_allocations(resource, containers, requests)

            self.__send_final_requests(requests)

        log_info("_______________", self.__debug)

    def rebalance_containers(self, config):
        self.__config = config
        self.__debug = get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "DEBUG")

        ## ATM we are using the energy percentage parameters to balance other resources (such as disk)
        self.__DIFF_PERCENTAGE = get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "ENERGY_DIFF_PERCENTAGE")
        self.__STOLEN_PERCENTAGE = get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "ENERGY_STOLEN_PERCENTAGE")
        self.__structures_balanced = get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "STRUCTURES_BALANCED")
        self.__resources_balanced = get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "RESOURCES_BALANCED")
        self.__balancing_method = get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "BALANCING_METHOD")
        self.__window_difference = get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
        self.__window_delay = get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")

        log_info("_______________", self.__debug)
        log_info("Performing CONTAINER Balancing", self.__debug)

        # Get the structures
        try:
            applications = get_structures(self.__couchdb_handler, self.__debug, subtype="application")
            containers = get_structures(self.__couchdb_handler, self.__debug, subtype="container")
            hosts = get_structures(self.__couchdb_handler, self.__debug, subtype="host")
        except requests.exceptions.HTTPError as e:
            log_error("Couldn't get structures", self.__debug)
            log_error(str(e), self.__debug)
            return

        ## Apps Rebalancing (balancing the resources of the containers of each application, i.e., apps with only one container won't be affected)
        if "applications" in self.__structures_balanced:

            # Filter out the ones that do not accept rebalancing or that do not need any internal rebalancing
            rebalanceable_apps = filter_rebalanceable_apps(applications, "container", self.__couchdb_handler)

            # Sort them according to each application they belong
            app_containers = dict()
            for app in rebalanceable_apps:
                app_name = app["name"]
                app_containers_names = app["containers"]
                app_containers[app_name] = [c for c in containers if c["name"] in app_containers_names]
                # Get the container usages
                app_containers[app_name] = self.__fill_containers_with_usage_info(self.__resources_balanced, app_containers[app_name])

            # Rebalance applications
            for app in rebalanceable_apps:
                app_name = app["name"]
                log_info("Going to rebalance app {0} now".format(app_name), self.__debug)
                if self.__balancing_method == "pair_swapping":
                    self.__rebalance_containers_by_pair_swapping(app_containers[app_name], app_name)
                elif self.__balancing_method == "weights":
                    log_warning("Weights balancing method not yet supported in applications", self.__debug)
                else:
                    log_warning("Unknown balancing method, currently supported methods: 'pair_swapping' and 'weights'", self.__debug)

        ## Hosts Rebalancing (balancing the resources of the containers of each host)
        if "hosts" in self.__structures_balanced:

            # Get hosts' containers
            host_containers = dict()
            for host in hosts:
                host_name = host["name"]
                host_containers[host_name] = list()
                host_containers_names = [c["name"] for c in containers if c["host"] == host_name]
                for container in containers:
                    if container["name"] in host_containers_names:
                        host_containers[host_name].append(container)
                # Get the container usages
                host_containers[host_name] = self.__fill_containers_with_usage_info(self.__resources_balanced, host_containers[host_name])

            # Rebalance hosts
            for host in hosts:
                host_name = host["name"]
                log_info("Going to rebalance host {0} now".format(host_name), self.__debug)
                if self.__balancing_method == "pair_swapping":
                    self.__rebalance_host_containers_by_pair_swapping(host_containers[host_name], host)
                elif self.__balancing_method == "weights":
                    self.__rebalance_host_containers_by_weight(host_containers[host_name], host)
                else:
                    log_warning("Unknown balancing method, currently supported methods: 'pair_swapping' and 'weights'", self.__debug)