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

from json_logic import jsonLogic

from src.MyUtils.MyUtils import log_info, debug_info, get_config_value, log_error, log_warning, get_structures, \
                                generate_request, get_structure_usages
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
        number_of_slices = int(total_amount // slice_amount)
        last_slice_amount = total_amount % slice_amount
        return [slice_amount] * number_of_slices + ([last_slice_amount] if last_slice_amount > 0 else [])

    def __print_donors_and_receivers(self, donors, receivers):
        log_info("Nodes that will give: {0}".format(str([c["name"] for c in donors])), self.__debug)
        log_info("Nodes that will receive:  {0}".format(str([c["name"] for c in receivers])), self.__debug)

    def __print_donor_slices(self, donor_slices, msg="Donor slices are:"):
        debug_info(msg, self.__debug)
        for host in donor_slices:
            for donor, slice_amount in donor_slices[host]:
                log_info("({0})\t{1}\t{2}".format(host, donor["name"], slice_amount), self.__debug)

    def __fill_containers_with_usage_info(self, resources, containers):
        containers_with_usages = list()
        for container in containers:
            # Get the usages for each balanced resource
            usages = get_structure_usages(resources, container, self.__window_difference,
                                          self.__window_delay, self.__opentsdb_handler, self.__debug)
            # Save data following the format ["resources"][<resource>]["usage"]
            # e.g., structure.mem.usage -> container["resources"]["mem"]["usage"]
            if usages:
                for usage_metric in usages:
                    # Split the key from the retrieved data
                    keys = usage_metric.split(".")
                    if any(keys[1] == res and res not in container["resources"] for res in ["disk_read", "disk_write", "energy"]): continue
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
            data = {}
            for r in container["resources"]:
                try:
                    data[r] =  {"structure": {r: {
                        "usage": container["resources"][r]["usage"],
                        "min": container["resources"][r]["min"],
                        "max": container["resources"][r]["max"],
                        "current": container["resources"][r]["current"]
                    }}}
                except KeyError:
                    continue

            # Check if container activate the rule: it has low resource usage (donors) or a bottleneck (receivers)
            if jsonLogic(rule["rule"], data):
                filtered_containers.append(container)
        return filtered_containers

    def __print_scaling_info(self, container, amount_to_scale, resource):
        if amount_to_scale > 0:  # Receiver
            log_info("Node {0} will receive: {1} for resource {2}".format(container["name"], amount_to_scale, resource), self.__debug)
        if amount_to_scale < 0:  # Donor
            log_info("Node {0} will give: {1} for resource {2}".format(container["name"], amount_to_scale, resource), self.__debug)

    def __generate_scaling_request(self, container, resource, amount_to_scale, requests):
        self.__print_scaling_info(container, amount_to_scale, resource)
        request = generate_request(container, int(amount_to_scale), resource, priority=2 if amount_to_scale > 0 else -1)
        if container["name"] not in requests:
            requests[container["name"]] = list()
        requests[container["name"]].append(request)

    def __update_resource_in_couchdb(self, container, resource, amount_to_scale):
        current_limit = container.get("resources", {}).get(resource, {}).get("current", -1)
        new_current = current_limit + amount_to_scale
        self.__print_scaling_info(container, amount_to_scale, resource)
        # Update container "current" value in CouchDB
        put_done = False
        tries = 0
        while not put_done:
            tries += 1
            container["resources"][resource]["current"] = new_current
            self.__couchdb_handler.update_structure(container)

            time.sleep(0.5)

            container = self.__couchdb_handler.get_structure(container['name'])
            put_done = container["resources"][resource]["current"] == new_current

            if tries >= 3:
                log_error("Node {0} 'current' value couldn't be updated in document database from {1} to {2}".format(container["name"], current_limit, new_current), self.__debug)
                return


    def __manage_rebalancing(self, donor, receiver, resource, amount_to_scale, requests):
        if amount_to_scale == 0:
            log_info("Amount to rebalance from {0} to {1} is 0, skipping".format(donor["name"], receiver["name"]), self.__debug)
            return
        # Create the pair of scaling requests
        if resource != "energy":
            self.__generate_scaling_request(receiver, resource, amount_to_scale, requests)
            self.__generate_scaling_request(donor, resource, -amount_to_scale, requests)
        # Energy is directly updated in CouchDB as NodeRescaler cannot modify an energy physical limit
        else:
            self.__update_resource_in_couchdb(receiver, resource, amount_to_scale)
            self.__update_resource_in_couchdb(donor, resource, -amount_to_scale)

    def __send_final_requests(self, requests):
        # For each container, aggregate all its requests in a single request
        final_requests = list()
        for container in requests:
            # Copy the first request as the base request
            flat_request = dict(requests[container][0])
            flat_request["amount"] = sum(req["amount"] for req in requests[container])
            final_requests.append(flat_request)

        log_info("REQUESTS ARE:", self.__debug)
        for c in requests.values():
            for r in c:
                debug_info(r, self.__debug)

        # TODO: Adjust requests amounts according to the maximums (trim), otherwise the scaling down will be performed
        #  but not the scaling up, and shares will be lost

        log_info("FINAL REQUESTS ARE:", self.__debug)
        for r in final_requests:
            debug_info(r, self.__debug)
            self.__couchdb_handler.add_request(r)

    ## BALANCING METHODS
    # APPS BY PAIR SWAPPING
    def __rebalance_app_containers_by_pair_swapping(self, containers, app_name):

        balanceable_resources = {"cpu", "energy"}

        for resource in self.__resources_balanced:

            if resource not in balanceable_resources:
                log_warning("'{0}' not yet supported in app '{1}' balancing, only '{2}' available at the moment".format(
                    resource, self.__balancing_method, list(balanceable_resources)), self.__debug)
                continue
            log_info("Going to rebalance '{0}' by {1} for {2}".format(resource, self.__balancing_method, app_name), self.__debug)

            # Filter the containers between donors and receivers, according to usage and rules
            donors = self.__filter_containers_by_role("donors", resource, containers)
            receivers = self.__filter_containers_by_role("receivers", resource, containers)

            # Print info about current donors and receivers
            self.__print_donors_and_receivers(donors, receivers)

            if not receivers:
                log_info("No containers in need of rebalancing for {0}".format(app_name), self.__debug)
                continue

            # Order the containers from lower to upper current resource limit
            # TODO: Maybe is better to order by (max - current) -> Those containers with a bigger gap receive first
            receivers = sorted(receivers, key=lambda c: c["resources"][resource]["current"])

            # Steal resources from the low-usage containers (donors), create 'slices' of resources
            donor_slices = dict()
            for container in donors:
                # Ensure this request will be successfully processed, otherwise we are 'giving' away extra resources
                current_limit = container["resources"][resource]["current"]
                min_value = container["resources"][resource]["min"]
                usage_value = container["resources"][resource]["usage"]
                host = container["host"]
                # Give stolen percentage of the gap between current limit and current usage (or min if usage is lower)
                stolen_amount = self.__STOLEN_PERCENTAGE * (current_limit - max(min_value,  usage_value))

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

            # Give the resources to the bottlenecked containers (receivers)
            requests = dict()
            received_amount = dict()
            while donor_slices:
                # Print current donor slices
                self.__print_donor_slices(donor_slices)

                for receiver in receivers:
                    receiver_name = receiver["name"]
                    receiver_host = receiver["host"]
                    if receiver_host not in donor_slices:
                        log_info("No more donors on its host ({0}), container {1} left out".format(
                            receiver_host, receiver["name"]), self.__debug)
                        continue

                    if receiver_name not in received_amount:
                        received_amount[receiver_name] = 0

                    # Container can't receive more than its maximum also taking into account its previous donations
                    max_receiver_amount = (receiver["resources"][resource]["max"] -
                                           receiver["resources"][resource]["current"] -
                                           received_amount.setdefault(receiver_name, 0))

                    # If this container can't be scaled anymore, skip
                    if max_receiver_amount <= 0:
                        continue

                    # Get and remove one slice from the list
                    donor, amount_to_scale = donor_slices[receiver_host].pop()

                    # Trim the amount to scale if needed and return the remaining amount to the donor slices
                    if amount_to_scale > max_receiver_amount:
                        donor_slices[receiver_host].append((donor, amount_to_scale - max_receiver_amount))
                        amount_to_scale = max_receiver_amount

                    # If all the resources from the donors on this host have been donated, the host is removed
                    if not donor_slices[receiver_host]:
                        del donor_slices[receiver_host]

                    # Manage necessary scalings to rebalance resource between donor and receiver
                    self.__manage_rebalancing(donor, receiver, resource, amount_to_scale, requests)

                    # Update the received amount for this container
                    received_amount[receiver_name] += amount_to_scale

                    log_info("Resource swap between {0} (donor) and {1} (receiver) with amount {2}".format(
                        donor["name"], receiver["name"], amount_to_scale), self.__debug)

            log_info("No more donors", self.__debug)
            self.__send_final_requests(requests)

    # HOSTS BY PAIR SWAPPING
    # TODO: adapt disk resource to disk_read and disk_write
    def __rebalance_host_containers_by_pair_swapping(self, containers, host):

        balanceable_resources = {"cpu": {"diff_percentage":self.__DIFF_PERCENTAGE, "stolen_percentage":self.__STOLEN_PERCENTAGE}, 
                                "disk": {"diff_percentage":self.__DIFF_PERCENTAGE, "stolen_percentage":self.__STOLEN_PERCENTAGE}}

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
                    # If current its near its maximum it is a donor -> (max - current) < diff_percentage * max
                    if diff < balanceable_resources[resource]["diff_percentage"] * container["resources"][resource]["max"]:
                        donors.append(container)
                    # If usage its near its current it is a receiver -> (current - usage) < diff_percentage * current
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

                if resource == "disk" and "disks" in host["resources"] and len(host["resources"]["disks"]) > 1:
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

                # Manage necessary scalings to rebalance resource between donor and receiver
                self.__manage_rebalancing(donor, receiver, resource, amount_to_scale, requests)
                log_info("Resource swap between {0} (donor) and {1} (receiver) with amount {2}".format(donor["name"], receiver["name"], amount_to_scale), self.__debug)

            log_info("No more receivers", self.__debug)
            self.__send_final_requests(requests)

        log_info("_______________", self.__debug)

    # HOSTS BY WEIGHT
    def __rebalance_host_containers_by_weight(self, containers, host):

        balanceable_resources = {"cpu": {"diff_percentage":self.__DIFF_PERCENTAGE},
                                 "disk": {"diff_percentage":self.__DIFF_PERCENTAGE},
                                 "disk_read": {"diff_percentage":self.__DIFF_PERCENTAGE},
                                 "disk_write": {"diff_percentage":self.__DIFF_PERCENTAGE}}

        def get_new_allocations(resource, containers, requests):
            ## Get total allocation and weight
            total_allocation_amount = 0
            weight_sum = 0
            participants = []
            for container in containers:
                if resource in container["resources"]:
                    usage_threshold = container["resources"][resource]["current"] - container["resources"][resource]["usage"] < balanceable_resources[resource]["diff_percentage"] * container["resources"][resource]["current"]
                    if "weight" in container["resources"][resource] and usage_threshold:
                        participants.append({"container_info": container})
                        total_allocation_amount += container["resources"][resource]["current"]
                        weight_sum += container["resources"][resource]["weight"]
                    # else: containers with low usage that won't participate in the distribution

            if weight_sum > 0:
                alloc_slice = total_allocation_amount / weight_sum

                ## Adjust alloc until every container is allocated an amount below their maximum
                adjust_finished = False
                while not adjust_finished:
                    adjust_finished = True

                    for container in participants:

                        ## Update new_alloc if needed
                        if "new_alloc" not in container or container["new_alloc"] < container["container_info"]["resources"][resource]["max"]:
                            container["new_alloc"] = round(alloc_slice * container["container_info"]["resources"][resource]["weight"])

                        ## Check if new_alloc exceeds container maximum
                        if container["new_alloc"] > container["container_info"]["resources"][resource]["max"]:
                            ## Set new_alloc to max and recalculate allocs
                            container["new_alloc"] = container["container_info"]["resources"][resource]["max"]
                            total_allocation_amount -= container["container_info"]["resources"][resource]["max"]
                            weight_sum -= container["container_info"]["resources"][resource]["weight"]
                            if weight_sum > 0: alloc_slice = total_allocation_amount / weight_sum
                            else: alloc_slice = 0

                            adjust_finished = False
                            break # try again adjusting allocs

                ## Send scaling requests
                for container in participants:
                    amount_to_scale = container["new_alloc"] - container["container_info"]["resources"][resource]["current"]
                    if amount_to_scale != 0:
                        self.__generate_scaling_request(container["container_info"], resource, amount_to_scale, requests)

        def get_new_allocations_by_disk(containers, requests, disk_name):
            total_allocated_bw = 0
            weight_sum = 0
            weight_read_sum = 0
            weight_write_sum = 0
            participants = {"disk_read": [], "disk_write": []}
            for container in containers:
                if all("weight" in container.get("resources", {}).get(res, {}) for res in ["disk_read", "disk_write"]):
                    read_usage_threshold = container["resources"]["disk_read"]["current"] - container["resources"]["disk_read"]["usage"] < balanceable_resources["disk_read"]["diff_percentage"] * container["resources"]["disk_read"]["current"]
                    write_usage_threshold = container["resources"]["disk_write"]["current"] - container["resources"]["disk_write"]["usage"] < balanceable_resources["disk_write"]["diff_percentage"] * container["resources"]["disk_write"]["current"]

                    if read_usage_threshold:
                        participants["disk_read"].append({"container_info": container})
                        total_allocated_bw += container["resources"]["disk_read"]["current"]
                        weight_sum      += container["resources"]["disk_read"]["weight"]
                        weight_read_sum += container["resources"]["disk_read"]["weight"]

                    if write_usage_threshold:
                        participants["disk_write"].append({"container_info": container})
                        total_allocated_bw += container["resources"]["disk_write"]["current"]
                        weight_sum       += container["resources"]["disk_write"]["weight"]
                        weight_write_sum += container["resources"]["disk_write"]["weight"]

            if weight_sum > 0:
                read_distribution = total_allocated_bw * (weight_read_sum / weight_sum)
                write_distribution = total_allocated_bw * (weight_write_sum / weight_sum)

                ## Adjust distributions to host maximums
                read_adjusted, write_adjusted, surplus_io = False, False, 0
                while not read_adjusted or not write_adjusted:
                    write_distribution += surplus_io
                    surplus_io = 0
                    write_adjusted = write_distribution <= host["resources"]["disks"][disk_name]["max_write"]
                    if not write_adjusted:
                        surplus_io = write_distribution - host["resources"]["disks"][disk_name]["max_write"]
                        write_distribution = host["resources"]["disks"][disk_name]["max_write"]

                    read_distribution += surplus_io
                    surplus_io = 0
                    read_adjusted = read_distribution <= host["resources"]["disks"][disk_name]["max_read"]
                    if not read_adjusted:
                        surplus_io = read_distribution - host["resources"]["disks"][disk_name]["max_read"]
                        read_distribution = host["resources"]["disks"][disk_name]["max_read"]

                    if read_distribution == host["resources"]["disks"][disk_name]["max_read"] and write_distribution == host["resources"]["disks"][disk_name]["max_write"]:
                        break
                ##
                if weight_read_sum > 0: read_slice = read_distribution / weight_read_sum
                else: read_slice = 0
                if weight_write_sum > 0: write_slice = write_distribution / weight_write_sum 
                else: write_slice = 0

                ## Adjust alloc until every container is allocated an amount below their maximum
                adjust_finished = False
                while not adjust_finished:
                    adjust_finished = True

                    for resource, alloc_slice in [("disk_read", read_slice), ("disk_write", write_slice)]:
                        for container in participants[resource]:

                            ## Update new_alloc if needed
                            if "new_alloc" not in container or container["new_alloc"] < container["container_info"]["resources"][resource]["max"]:
                                container["new_alloc"] = round(alloc_slice * container["container_info"]["resources"][resource]["weight"])

                            ## Check if new_alloc exceeds container maximum
                            if container["new_alloc"] > container["container_info"]["resources"][resource]["max"]:
                                ## Set new_alloc to max and recalculate allocs
                                container["new_alloc"] = container["container_info"]["resources"][resource]["max"]
                                if resource == "disk_read":
                                    read_distribution -= container["container_info"]["resources"][resource]["max"]
                                    weight_read_sum -= container["container_info"]["resources"][resource]["weight"]
                                    if weight_read_sum > 0: read_slice = read_distribution / weight_read_sum
                                    else: read_slice = 0
                                elif resource == "disk_write":
                                    write_distribution -= container["container_info"]["resources"][resource]["max"]
                                    weight_write_sum -= container["container_info"]["resources"][resource]["weight"]
                                    if weight_write_sum > 0: write_slice = write_distribution / weight_write_sum
                                    else: write_slice = 0

                                adjust_finished = False
                                break # try again adjusting allocs

                        if not adjust_finished: break

                ## Send scaling requests
                for resource in ["disk_read", "disk_write"]:
                    for container in participants[resource]:
                        amount_to_scale = container["new_alloc"] - container["container_info"]["resources"][resource]["current"]
                        if amount_to_scale != 0:
                            self.__generate_scaling_request(container["container_info"], resource, amount_to_scale, requests)

        for resource in self.__resources_balanced:

            if resource not in balanceable_resources:
                log_warning("'{0}' not yet supported in host '{1}' balancing, only '{2}' available at the moment".format(resource, self.__balancing_method, list(balanceable_resources.keys())), self.__debug)
                continue

            log_info("Going to rebalance {0} by {1}".format(resource, self.__balancing_method), self.__debug)

            requests = dict()

            if resource == "disk":
                if "disks" not in host["resources"]:
                    log_error("There are no disks in host {0}".format(host["name"]), self.__debug)
                    continue
                if len(host["resources"]["disks"]) > 1:
                    ## if host has more than one disk the balancing needs to be performed on each disk
                    for disk in host["resources"]["disks"]:
                        disk_containers = []
                        for container in containers:
                            if "disk" in container["resources"] and container["resources"]["disk"]["name"] == disk: disk_containers.append(container)

                        get_new_allocations_by_disk(disk_containers, requests, disk)
                else:
                    ## There is only one disk in the host
                    disk_name = next(iter(host["resources"]["disks"]))
                    get_new_allocations_by_disk(containers, requests, disk_name)

            elif (resource == "disk_read" or resource == "disk_write") and "disks" in host["resources"] and len(host["resources"]["disks"]) > 1:
                ## if host has more than one disk the balancing needs to be performed on each disk
                for disk in host["resources"]["disks"]:
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
        containers = get_structures(self.__couchdb_handler, self.__debug, subtype="container")
        applications = get_structures(self.__couchdb_handler, self.__debug, subtype="application")
        hosts = get_structures(self.__couchdb_handler, self.__debug, subtype="host")

        # If some of the needed structures couldn't be retrieved, no rebalancing is performed
        if any(var is None for var in (containers, applications, hosts)):
            log_error("Couldn't get structures", self.__debug)
            return

        # APPS REBALANCING: Balancing the resources between containers of the same application
        if "applications" in self.__structures_balanced:

            # Filter out the ones that do not accept rebalancing or that do not need any internal rebalancing
            rebalanceable_apps = filter_rebalanceable_apps(applications, "container", self.__couchdb_handler)

            # Sort them according to each application they belong
            app_containers = dict()
            for app in rebalanceable_apps:
                app_name = app["name"]
                app_containers[app_name] = [c for c in containers if c["name"] in app["containers"]]
                # Get the container usages
                app_containers[app_name] = self.__fill_containers_with_usage_info(self.__resources_balanced, app_containers[app_name])

            # Rebalance applications
            for app in rebalanceable_apps:
                app_name = app["name"]
                log_info("Going to rebalance app {0} now".format(app_name), self.__debug)
                if self.__balancing_method == "pair_swapping":
                    self.__rebalance_app_containers_by_pair_swapping(app_containers[app_name], app_name)
                elif self.__balancing_method == "weights":
                    log_warning("Weights balancing method not yet supported in applications", self.__debug)
                else:
                    log_warning("Unknown balancing method, currently supported methods: 'pair_swapping' and 'weights'", self.__debug)

        # HOSTS REBALANCING: Balancing the resources between container on the same host
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

            ## Workaround to manage disk_read and disk_write at the same time if both are requested
            if "disk_read" in self.__resources_balanced and "disk_write" in self.__resources_balanced:
                self.__resources_balanced.remove("disk_read")
                self.__resources_balanced.remove("disk_write")
                self.__resources_balanced.append("disk")

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