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


class ContainerRebalancer(BaseRebalancer):

    STATIC_ATTRS = {"couchdb_handler", "opentsdb_handler"}
    REBALANCING_LEVEL = "container"

    def __init__(self, opentsdb_handler, couchdb_handler):
        super().__init__(couchdb_handler)
        self.opentsdb_handler = opentsdb_handler

    @staticmethod
    def select_donated_field(resource):
        return "max" if resource == "energy" else "current"

    @staticmethod
    def get_donor_slice_key(structure, resource):
        # Containers can only donate to and receive from other containers on the same host (and same disk if needed)
        return structure["host"] + "_{0}".format(structure["resources"]["disk"]["name"]) if resource == "disk" else ""

    def is_donor(self, data):
        # If current its near its maximum it is a donor -> (max - current) < diff_percentage * max
        return (data["max"] - data["current"]) < (self.diff_percentage * data["max"])

    def is_receiver(self, data):
        # If usage its near its current it is a receiver -> (current - usage) < diff_percentage * current
        return (data["current"] - data["usage"]) < (self.diff_percentage * data["current"])

    def fill_containers_with_usage_info(self, resources, containers):
        containers_with_usages = list()
        for container in containers:
            # Get the usages for each balanced resource
            usages = utils.get_structure_usages(resources, container, self.window_timelapse, self.window_delay, self.opentsdb_handler, self.debug)
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

    # HOSTS BY WEIGHT
    def rebalance_host_containers_by_weight(self, containers, host):

        balanceable_resources = {"cpu": {"diff_percentage": self.diff_percentage},
                                 "disk": {"diff_percentage": self.diff_percentage},
                                 "disk_read": {"diff_percentage": self.diff_percentage},
                                 "disk_write": {"diff_percentage": self.diff_percentage}}

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
                        self.generate_scaling_request(container["container_info"], resource, amount_to_scale, requests)

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
                            self.generate_scaling_request(container["container_info"], resource, amount_to_scale, requests)

        for resource in self.resources_balanced:

            if resource not in balanceable_resources:
                utils.log_warning("'{0}' not yet supported in host pair-swapping balancing, only '{1}' available at the moment".format(resource, list(balanceable_resources.keys())), self.debug)
                continue

            utils.log_info("Rebalancing resource '{0}' for host {1} by weights".format(resource, host["name"]), self.debug)

            requests = dict()

            if resource == "disk":
                if "disks" not in host["resources"]:
                    utils.log_error("There are no disks in host {0}".format(host["name"]), self.debug)
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

            self.send_final_requests(requests)

    def rebalance_containers(self):
        utils.log_info("--------------------- CONTAINER BALANCING ---------------------", self.debug)

        # Get the structures
        containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
        if not containers:
            utils.log_warning("No registered containers were found", self.debug)
            return

        # Get the resources needed to perform balancing
        needed_resource_usages = set(self.resources_balanced)
        if "energy" in self.resources_balanced:
            needed_resource_usages.add("cpu")

        ## Workaround to manage disk_read and disk_write at the same time if both are requested
        if "disk_read" in self.resources_balanced and "disk_write" in self.resources_balanced:
            self.resources_balanced.remove("disk_read")
            self.resources_balanced.remove("disk_write")
            self.resources_balanced.append("disk")

        # APPLICATION SCOPE: Balancing the resources between containers of the same application
        if self.containers_scope == "application":
            applications = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")

            # Filter out the ones that do not accept rebalancing or that do not need any internal rebalancing
            rebalanceable_apps = self.filter_rebalanceable_apps(applications)

            if not rebalanceable_apps:
                utils.log_warning("Trying to balance containers at 'application' scope but no rebalanceable applications were found", self.debug)
                return

            # Sort them according to each application they belong
            app_containers = dict()
            for app in rebalanceable_apps:
                app_name = app["name"]
                app_containers[app_name] = [c for c in containers if c["name"] in app["containers"]]
                # Get the container usages
                app_containers[app_name] = self.fill_containers_with_usage_info(list(needed_resource_usages), app_containers[app_name])

            # Rebalance applications
            for app in rebalanceable_apps:
                app_name = app["name"]
                utils.log_info("Going to rebalance app {0} now".format(app_name), self.debug)
                if self.balancing_method == "pair_swapping":
                    self.pair_swapping(app_containers[app_name])
                elif self.balancing_method == "weights":
                    utils.log_warning("Weights balancing method not yet supported in applications", self.debug)
                else:
                    utils.log_warning("Unknown balancing method, currently supported methods: 'pair_swapping' and 'weights'", self.debug)

        # HOST SCOPE: Balancing the resources between containers on the same host
        if self.containers_scope == "host":
            hosts = utils.get_structures(self.couchdb_handler, self.debug, subtype="host")
            if not hosts:
                utils.log_warning("Trying to balance containers at 'host' scope but no hosts were found", self.debug)
                return

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
                host_containers[host_name] = self.fill_containers_with_usage_info(list(needed_resource_usages), host_containers[host_name])

            # Rebalance hosts
            for host in hosts:
                host_name = host["name"]
                utils.log_info("Going to rebalance host {0} now".format(host_name), self.debug)
                if self.balancing_method == "pair_swapping":
                    self.pair_swapping(host_containers[host_name])
                elif self.balancing_method == "weights":
                    self.rebalance_host_containers_by_weight(host_containers[host_name], host)
                else:
                    utils.log_warning("Unknown balancing method, currently supported methods: 'pair_swapping' and 'weights'", self.debug)