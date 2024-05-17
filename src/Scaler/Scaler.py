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


from __future__ import print_function

import json
import time
from threading import Thread

import requests
import traceback
import logging

from requests import HTTPError

import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.opentsdb as bdwatchdog
from src.Guardian.Guardian import Guardian
from src.Snapshoters.StructuresSnapshoter import get_container_resources_dict

from src.MyUtils.MyUtils import MyConfig, log_error, get_service, beat, log_info, log_warning, \
    get_structures, update_structure, generate_request_name, structure_is_application, structure_is_container
from src.StateDatabase import couchdb

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "REQUEST_TIMEOUT": 60, "self.debug": True, "CHECK_CORE_MAP": True, "ACTIVE": True}
SERVICE_NAME = "scaler"

BDWATCHDOG_CONTAINER_METRICS = {"cpu": ['proc.cpu.user', 'proc.cpu.kernel'],
                                "mem": ['proc.mem.resident'],
                                "disk": ['proc.disk.reads.mb', 'proc.disk.writes.mb'],
                                "net": ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']}
RESCALER_CONTAINER_METRICS = {'cpu': ['proc.cpu.user', 'proc.cpu.kernel'], 'mem': ['proc.mem.resident'],
                              'disk': ['proc.disk.reads.mb', 'proc.disk.writes.mb'],
                              'net': ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']}

APP_SCALING_SPLIT_AMOUNT = 5


def set_container_resources(rescaler_http_session, container, resources, debug):
    rescaler_ip = container["host_rescaler_ip"]
    rescaler_port = container["host_rescaler_port"]
    container_name = container["name"]
    r = rescaler_http_session.put(
        "http://{0}:{1}/container/{2}".format(rescaler_ip, rescaler_port, container_name),
        data=json.dumps(resources),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    if r.status_code == 201:
        return dict(r.json())
    else:
        log_error(str(json.dumps(r.json())), debug)
        r.raise_for_status()


class Scaler:
    """
    Scaler class that implements the logic for this microservice.
    """

    def __init__(self):
        self.couchdb_handler = couchdb.CouchDBServer()
        self.db_handler = couchDB.CouchDBServer()
        self.rescaler_http_session = requests.Session()
        self.bdwatchdog_handler = bdwatchdog.OpenTSDBServer()
        self.host_info_cache = dict()
        self.container_info_cache = dict()
        self.apply_request_by_resource = {"cpu": self.apply_cpu_request, "mem": self.apply_mem_request, "disk": self.apply_disk_request, "net": self.apply_net_request}

    #### CHECKS ####
    def fix_container_cpu_mapping(self, container, cpu_used_cores, cpu_used_shares):

        resource_dict = {"cpu": {}}
        resource_dict["cpu"]["cpu_num"] = ",".join(cpu_used_cores)
        resource_dict["cpu"]["cpu_allowance_limit"] = int(cpu_used_shares)
        try:
            # TODO FIX this error should be further diagnosed, in case it affects other modules who use this call too
            set_container_resources(self.rescaler_http_session, container, resource_dict, self.debug)
            return True
        except (Exception, RuntimeError, ValueError, requests.HTTPError) as e:
            log_error("Error when setting container resources: {0}".format(str(e)), self.debug)
            return False

    def check_host_cpu_limits(self):
        errors_detected = False
        for host in self.host_info_cache.values():
            all_accounted_shares = 0
            map = host["resources"]["cpu"]["core_usage_mapping"]
            for core in map.values():
                for container in core:
                    if container != "free":
                        all_accounted_shares += core[container]
            if all_accounted_shares > host["resources"]["cpu"]["max"]:
                log_error("Host {0} has more mapped shares than its maximum".format(host["name"]), self.debug)
                errors_detected = True
        return errors_detected

    def get_bound_disk(self, container_name):
        container = self.db_handler.get_structure(container_name)
        return container["resources"]["disk"]["name"]

    def check_host_has_enough_free_resources(self, host_info, needed_resources, resource, container_name):
        if resource == "disk":
            bound_disk = self.get_bound_disk(container_name)
            host_shares = host_info["resources"]["disks"][bound_disk]["free"]
        else:
            host_shares = host_info["resources"][resource]["free"]

        if host_shares == 0:
            raise ValueError("No resources available for resource {0} in host {1} ".format(resource, host_info["name"]))
        elif host_shares < needed_resources:
            missing_shares = needed_resources - host_shares
            # raise ValueError("Error in setting {0}, couldn't get the resources needed, missing {1} shares".format(resource, missing_shares))
            log_warning(
                "Beware, there are not enough free shares for resource {0} in the host, there are {1},  missing {2}".format(resource, host_shares, missing_shares),
                self.debug)

    def check_containers_cpu_limits(self, containers):
        errors_detected = False
        for container in containers:
            database_resources = container["resources"]

            if "max" not in database_resources["cpu"]:
                log_error("container {0} has not a maximum value set, check its configuration".format(container["name"]), self.debug)
                errors_detected = True
                continue

            max_cpu_limit = database_resources["cpu"]["max"]
            real_resources = self.container_info_cache[container["name"]]["resources"]
            try:
                current_cpu_limit = self.get_current_resource_value(real_resources, "cpu")
                if current_cpu_limit > max_cpu_limit:
                    log_error("container {0} has, somehow, more shares ({1}) than the maximum ({2}), check the max "
                              "parameter in its configuration".format(container["name"], current_cpu_limit, max_cpu_limit), self.debug)
                    errors_detected = True
            except ValueError as e:
                log_error("Current value of structure {0} is not valid: {1}".format(container["name"], str(e)), self.debug)
                errors_detected = True

        return errors_detected

    def check_container_cpu_mapping(self, container, host_info, cpu_used_cores, cpu_used_shares):
        host_max_cores = int(host_info["resources"]["cpu"]["max"] / 100)
        host_cpu_list = [str(i) for i in range(host_max_cores)]
        core_usage_map = host_info["resources"]["cpu"]["core_usage_mapping"]

        cpu_accounted_shares = 0
        cpu_accounted_cores = list()
        container_name = container["name"]
        for core in core_usage_map:
            if core not in host_cpu_list:
                continue
            if container_name in core_usage_map[core] and core_usage_map[core][container_name] != 0:
                cpu_accounted_shares += core_usage_map[core][container_name]
                cpu_accounted_cores.append(core)

        if sorted(cpu_used_cores) != sorted(cpu_accounted_cores) or cpu_used_shares != cpu_accounted_shares:
            return False, cpu_accounted_cores, cpu_accounted_shares
        else:
            return True, cpu_accounted_cores, cpu_accounted_shares

    def check_container_core_mapping(self, container, real_resources):
        errors_detected = False
        database_resources = container["resources"]

        if container["host"] not in self.host_info_cache:
            log_error("Host info '{0}' for container {1} is missing".format(container["host"], container["name"]), self.debug)
            return True
        elif "max" not in database_resources["cpu"]:
            # This error should have been previously detected
            return True
        else:
            try:
                current_cpu_limit = self.get_current_resource_value(real_resources, "cpu")
            except ValueError as e:
                log_error(e, self.debug)
                return True

        host_info = self.host_info_cache[container["host"]]
        max_cpu_limit = database_resources["cpu"]["max"]
        cpu_list = self.get_cpu_list(real_resources["cpu"]["cpu_num"])
        c_name = container["name"]

        map_host_valid, actual_used_cores, actual_used_shares = self.check_container_cpu_mapping(container, host_info, cpu_list, current_cpu_limit)

        if not map_host_valid:
            log_error(
                "Detected invalid core mapping for container {0}, has {1}-{2}, should be {3}-{4}".format(c_name, cpu_list, current_cpu_limit, actual_used_cores, actual_used_shares),
                self.debug)
            log_error("trying to automatically fix", self.debug)
            success = self.fix_container_cpu_mapping(container, actual_used_cores, actual_used_shares)
            if success:
                log_error("Succeeded fixing {0} container's core mapping".format(container["name"]), self.debug)
                errors_detected = True
            else:
                log_error("Failed in fixing {0} container's core mapping".format(container["name"]), self.debug)
                errors_detected = False
        return errors_detected

    def check_core_mapping(self, containers):
        errors_detected = False
        for container in containers:
            c_name = container["name"]
            log_info("Checking container {0}".format(c_name), self.debug)
            if c_name not in self.container_info_cache or "resources" not in self.container_info_cache[c_name]:
                log_error("Couldn't get container's {0} resources, can't check its sanity".format(c_name), self.debug)
                continue
            real_resources = self.container_info_cache[c_name]["resources"]
            errors = self.check_container_core_mapping(container, real_resources)
            errors_detected = errors_detected or errors
        return errors_detected

    def check_invalid_resource_value(self, database_resources, amount, current, resource):
        max_resource_limit = int(database_resources["resources"][resource]["max"])
        min_resource_limit = int(database_resources["resources"][resource]["min"])
        resource_limit = int(current + amount)

        if resource_limit < 0:
            raise ValueError("Error in setting {0}, it would be lower than 0".format(resource))
        elif resource_limit < min_resource_limit:
            raise ValueError("Error in setting {0}, new value {1} it would be lower than min {2}".format(resource, resource_limit, min_resource_limit))
        elif resource_limit > max_resource_limit:
            raise ValueError("Error in setting {0}, new value {1} it would be higher than max {2}".format(resource, resource_limit, max_resource_limit))

    ######################################################

    #### REQUEST MANAGEMENT ####
    def filter_requests(self, request_timeout):
        fresh_requests, purged_requests, final_requests = list(), list(), list()
        # Remote database operation
        all_requests = self.db_handler.get_requests()
        purged_counter = 0
        duplicated_counter = 0

        # First purge the old requests
        for request in all_requests:
            if request["timestamp"] < time.time() - request_timeout:
                purged_requests.append(request)
                purged_counter += 1
            else:
                fresh_requests.append(request)

        # Then remove repeated requests for the same structure if found
        structure_requests_dict = {}
        for request in fresh_requests:
            structure = request["structure"]  # The structure name (string), acting as an id
            action = request["action"]  # The action name (string)
            if structure not in structure_requests_dict:
                structure_requests_dict[structure] = {}

            if action not in structure_requests_dict[structure]:
                structure_requests_dict[structure][action] = request
            else:
                # A previous request was found for this structure, remove old one and leave the newer one
                stored_request = structure_requests_dict[structure][action]
                if stored_request["timestamp"] > request["timestamp"]:
                    # The stored request is newer, leave it and mark the retrieved one to be removed
                    purged_requests.append(request)
                else:
                    # The stored request is older, mark it to be remove and save the retrieved one
                    purged_requests.append(stored_request)
                    structure_requests_dict[structure][action] = request

                duplicated_counter += 1

        self.db_handler.delete_requests(purged_requests)

        for structure in structure_requests_dict:
            for action in structure_requests_dict[structure]:
                final_requests.append(structure_requests_dict[structure][action])

        log_info("Number of purged/duplicated requests was {0}/{1}".format(purged_counter, duplicated_counter), True)
        return final_requests

    def sort_requests(self, new_requests):
        container_reqs, app_reqs = list(), list()
        for r in new_requests:
            if r["structure_type"] == "container":
                container_reqs.append(r)
            elif r["structure_type"] == "application":
                app_reqs.append(r)
            else:
                pass
        return container_reqs, app_reqs

    ######################################################

    #### RESOURCE REQUEST MANAGEMENT ####
    def process_request(self, request, real_resources, database_resources):
        # Create a 'fake' container structure with only the required info
        container = {"host_rescaler_ip": request["host_rescaler_ip"],
                     "host_rescaler_port": request["host_rescaler_port"],
                     "name": request["structure"]}

        # Apply the request and get the new resources to set
        try:
            new_resources = self.apply_request(request, real_resources, database_resources)
            if new_resources:
                log_info("Request: {0} for container : {1} for new resources : {2}".format(
                    request["action"], request["structure"], json.dumps(new_resources)), self.debug)

                # Apply changes through a REST call
                set_container_resources(self.rescaler_http_session, container, new_resources, self.debug)
        except (ValueError) as e:
            log_error("Error with container {0} in applying the request -> {1}".format(request["structure"], str(e)), self.debug)
            return
        except (HTTPError) as e:
            log_error("Error setting container {0} resources -> {1}".format(request["structure"], str(e)), self.debug)
            return
        except (Exception) as e:
            log_error("Error with container {0} -> {1}".format(request["structure"], str(e)), self.debug)
            return

    def apply_request(self, request, real_resources, database_resources):

        amount = int(request["amount"])

        host_info = self.host_info_cache[request["host"]]
        resource = request["resource"]

        # Get the current resource limit, if unlimited, then max, min or mean
        current_resource_limit = self.get_current_resource_value(real_resources, resource)

        # Check that the resource limit is respected, not lower than min or higher than max
        self.check_invalid_resource_value(database_resources, amount, current_resource_limit, resource)

        if amount > 0:
            # If the request is for scale up, check that the host has enough free resources before proceeding
            self.check_host_has_enough_free_resources(host_info, amount, resource, request['structure'])

        fun = self.apply_request_by_resource[resource]
        result = fun(request, database_resources, real_resources, amount)

        return result

    def apply_cpu_request(self, request, database_resources, real_resources, amount):
        resource = request["resource"]
        structure_name = request["structure"]
        host_info = self.host_info_cache[request["host"]]

        core_usage_map = host_info["resources"][resource]["core_usage_mapping"]

        current_cpu_limit = self.get_current_resource_value(real_resources, resource)
        cpu_list = self.get_cpu_list(real_resources["cpu"]["cpu_num"])

        host_max_cores = int(host_info["resources"]["cpu"]["max"] / 100)
        host_cpu_list = [str(i) for i in range(host_max_cores)]
        for core in host_cpu_list:
            if core not in core_usage_map:
                core_usage_map[core] = dict()
                core_usage_map[core]["free"] = 100
            if structure_name not in core_usage_map[core]:
                core_usage_map[core][structure_name] = 0

        used_cores = list(cpu_list)  # copy

        if amount > 0:
            # Rescale up, so look for free shares to assign and maybe add cores
            needed_shares = amount

            # First fill the already used cores so that no additional cores are added unnecessarily
            for core in cpu_list:
                if core_usage_map[core]["free"] > 0:
                    if core_usage_map[core]["free"] > needed_shares:
                        core_usage_map[core]["free"] -= needed_shares
                        core_usage_map[core][structure_name] += needed_shares
                        needed_shares = 0
                        break
                    else:
                        core_usage_map[core][structure_name] += core_usage_map[core]["free"]
                        needed_shares -= core_usage_map[core]["free"]
                        core_usage_map[core]["free"] = 0

            # Next try to satisfy the request by looking and adding a single core
            if needed_shares > 0:
                for core in host_cpu_list:
                    if core_usage_map[core]["free"] >= needed_shares:
                        core_usage_map[core]["free"] -= needed_shares
                        core_usage_map[core][structure_name] += needed_shares
                        needed_shares = 0
                        used_cores.append(core)
                        break

            # Finally, if unsuccessful, add as many cores as necessary, starting with the ones with the largest free shares to avoid too much spread
            if needed_shares > 0:
                l = list()
                for core in host_cpu_list:
                    l.append((core, core_usage_map[core]["free"]))
                l.sort(key=lambda tup: tup[1], reverse=True)
                less_used_cores = [i[0] for i in l]

                for core in less_used_cores:
                    # If this core has free shares
                    if core_usage_map[core]["free"] > 0 and needed_shares > 0:
                        # If it has more free shares than needed, assign them and finish
                        if core_usage_map[core]["free"] >= needed_shares:
                            core_usage_map[core]["free"] -= needed_shares
                            core_usage_map[core][structure_name] += needed_shares
                            needed_shares = 0
                            used_cores.append(core)
                            break
                        else:
                            # Otherwise, assign as many as possible and continue
                            core_usage_map[core][structure_name] += core_usage_map[core]["free"]
                            needed_shares -= core_usage_map[core]["free"]
                            core_usage_map[core]["free"] = 0
                            used_cores.append(core)

            if needed_shares > 0:
                # raise ValueError("Error in setting cpu, couldn't get the resources needed, missing {0} shares".format(needed_shares))
                log_warning("Structure {0} couldn't get as much CPU shares as intended ({1}), "
                            "instead it got {2}".format(structure_name, amount, amount - needed_shares), self.debug)
                amount = amount - needed_shares
                # FIXME couldn't do rescale up properly as shares to get remain

        elif amount < 0:
            # Rescale down so free all shares and claim new one to see how many cores can be freed
            shares_to_free = abs(amount)

            # First try to find cores with less shares for this structure (less allocated) and remove them
            l = list()
            for core in cpu_list:
                l.append((core, core_usage_map[core][structure_name]))
            l.sort(key=lambda tup: tup[1], reverse=False)
            less_allocated_cores = [i[0] for i in l]

            for core in less_allocated_cores:
                # Equal or less allocated shares than amount to be freed, remove this core altogether and if shares remain to be freed, continue
                if core_usage_map[core][structure_name] <= shares_to_free:
                    core_usage_map[core]["free"] += core_usage_map[core][structure_name]
                    shares_to_free -= core_usage_map[core][structure_name]
                    core_usage_map[core][structure_name] = 0
                    used_cores.remove(core)
                    # In the event that the amount to be freed was equal to the allocated one, finish
                    if shares_to_free == 0:
                        break
                # More allocated shares than amount to be freed, reduce allocation and finish
                elif core_usage_map[core][structure_name] > shares_to_free:
                    core_usage_map[core]["free"] += shares_to_free
                    core_usage_map[core][structure_name] -= shares_to_free
                    shares_to_free = 0
                    break

            if shares_to_free > 0:
                raise ValueError("Error in setting cpu, couldn't free the resources properly")

        # No error thrown, so persist the new mapping to the cache
        self.host_info_cache[request["host"]]["resources"]["cpu"]["core_usage_mapping"] = core_usage_map
        self.host_info_cache[request["host"]]["resources"]["cpu"]["free"] -= amount

        resource_dict = {resource: {}}
        resource_dict["cpu"]["cpu_num"] = ",".join(used_cores)
        resource_dict["cpu"]["cpu_allowance_limit"] = int(current_cpu_limit + amount)

        return resource_dict

    def apply_mem_request(self, request, database_resources, real_resources, amount):
        resource_dict = {request["resource"]: {}}
        current_mem_limit = self.get_current_resource_value(real_resources, request["resource"])
        current_mem_free = self.host_info_cache[request["host"]]["resources"]["mem"]["free"]

        if amount > current_mem_free:
            ## It is trying to get more resources than available
            amount = current_mem_free

        # No error thrown, so persist the new mapping to the cache
        self.host_info_cache[request["host"]]["resources"]["mem"]["free"] -= amount

        # Return the dictionary to set the resources
        resource_dict["mem"]["mem_limit"] = str(int(amount + current_mem_limit))

        return resource_dict

    def apply_disk_request(self, request, database_resources, real_resources, amount):
        resource_dict = {request["resource"]: {}}
        bound_disk = self.get_bound_disk(request['structure'])
        current_disk_limit = self.get_current_resource_value(real_resources, request["resource"])
        current_disk_free = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free"]

        if amount > current_disk_free:
            ## It is trying to get more resources than available
            amount = current_disk_free

        # No error thrown, so persist the new mapping to the cache
        self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free"] -= amount

        # Return the dictionary to set the resources
        resource_dict["disk"]["disk_read_limit"] = str(int(amount + current_disk_limit))
        resource_dict["disk"]["disk_write_limit"] = str(int(amount + current_disk_limit))

        return resource_dict

    def apply_net_request(self, request, database_resources, real_resources, amount):
        resource_dict = {request["resource"]: {}}
        current_net_limit = self.get_current_resource_value(real_resources, request["resource"])

        # Return the dictionary to set the resources
        resource_dict["net"]["net_limit"] = str(int(amount + current_net_limit))

        return resource_dict

    ######################################################

    ##### CONTAINER SCALING ######
    def rescale_container(self, request, structure):
        try:
            # Needed for the resources reported in the database (the 'max, min' values)
            database_resources = structure

            # Get the resources the container is using from its host NodeScaler (the 'current' value)
            c_name = structure["name"]
            if c_name not in self.container_info_cache or "resources" not in self.container_info_cache[c_name]:
                log_error("Couldn't get container's {0} resources, can't rescale".format(c_name), self.debug)
                return
            real_resources = self.container_info_cache[c_name]["resources"]

            # Process the request
            self.process_request(request, real_resources, database_resources)
        except Exception as e:
            log_error(str(e) + " " + str(traceback.format_exc()), self.debug)

    ######################################################

    ##### APPLICATION SCALING ######
    def sort_containers_by_usage_margin(self, container1, container2, resource):
        """
        Parameters:
            container1: dict -> A container structure
            container2: dict -> A container structure
            resource: str -> the resource to be used for sorting
        Returns:
            The tuple of the containers with the (lowest,highest) margin between resources used and resources set
        """
        c1_current_amount = container1["resources"][resource]["current"]
        c1_usage_amount = container1["resources"][resource]["usage"]
        c2_current_amount = container2["resources"][resource]["current"]
        c2_usage_amount = container2["resources"][resource]["usage"]
        if c1_current_amount - c1_usage_amount < c2_current_amount - c2_usage_amount:
            lowest, highest = container1, container2
        else:
            lowest, highest = container2, container1

        return lowest, highest

    def lowest_current_to_usage_margin(self, container1, container2, resource):
        # Return the container with the lowest margin between resources used and resources set (closest bottleneck)
        lowest, _ = self.sort_containers_by_usage_margin(container1, container2, resource)
        return lowest

    def highest_current_to_usage_margin(self, container1, container2, resource):
        # Return the container with the highest margin between resources used and resources set (lowest use)
        _, highest = self.sort_containers_by_usage_margin(container1, container2, resource)
        return highest

    def generate_requests(self, new_requests, app_label):
        rescaled_containers = list()
        total_amount = 0
        for req in new_requests:
            self.db_handler.add_request(req)
            rescaled_containers.append((req["structure"], req["amount"]))
            total_amount += req["amount"]
        log_info("App {0} rescaled {1} shares by rescaling containers: {2}".format(app_label, total_amount, str(rescaled_containers)), self.debug)

    def single_container_rescale(self, request, app_containers, resource_usage_cache):
        amount, resource_label = request["amount"], request["resource"]
        scalable_containers = list()
        resource_shares = abs(amount)

        # Look for containers that can be rescaled
        for container in app_containers:
            usages = resource_usage_cache[container["name"]]
            container["resources"][resource_label]["usage"] = usages[resource_label]
            current_value = container["resources"][resource_label]["current"]

            # Rescale down
            if amount < 0:
                # Check that the container has enough free resource shares
                # available to be released and that it would be able
                # to be rescaled without dropping under the minimum value
                if current_value < resource_shares:
                    # Container doesn't have enough resources to free
                    # ("Container doesn't have enough resources to free", self.debug)
                    pass
                elif current_value + amount < container["resources"][resource_label]["min"]:
                    # Container can't free that amount without dropping under the minimum
                    # log_error("Container {0} can't free that amount without dropping under the minimum".format(container["name"]), self.debug)
                    pass
                else:
                    scalable_containers.append(container)

            # Rescale up
            else:
                # Check that the container has enough free resource shares available in the host and that it would be able
                # to be rescaled without exceeded the maximum value
                container_host = container["host"]

                if self.host_info_cache[container_host]["resources"][resource_label]["free"] < resource_shares:
                    # Container's host doesn't have enough free resources
                    # log_error("Container's host doesn't have enough free resources", self.debug)
                    pass
                elif current_value + amount > container["resources"][resource_label]["max"]:
                    # Container can't get that amount without exceeding the maximum
                    # log_error("Container can't get that amount without exceeding the maximum", self.debug)
                    pass
                else:
                    scalable_containers.append(container)

        # Look for the best fit container for this resource and launch the rescaling request for it
        if scalable_containers:
            best_fit_container = scalable_containers[0]

            for container in scalable_containers[1:]:
                if amount < 0:
                    # If scaling down, look for containers with usages far from the limit (underuse)
                    best_fit_container = self.highest_current_to_usage_margin(container, best_fit_container, resource_label)
                else:
                    # If scaling up, look for containers with usages close to the limit (bottleneck)
                    best_fit_container = self.lowest_current_to_usage_margin(container, best_fit_container, resource_label)

            # Generate the new request
            new_request = Guardian.generate_request(best_fit_container, amount, resource_label)

            return True, best_fit_container, new_request
        else:
            return False, {}, {}

    def rescale_application(self, request, structure):

        # Get container names that this app uses
        app_containers_names = structure["containers"]
        app_containers = list()

        for cont_name in app_containers_names:
            # Get the container
            container = self.db_handler.get_structure(cont_name)
            app_containers.append(container)

            # Retrieve host info and cache it in case other containers or applications need it
            if container["host"] not in self.host_info_cache:
                self.host_info_cache[container["host"]] = self.db_handler.get_structure(container["host"])

        total_amount = request["amount"]

        requests = list()
        remaining_amount = total_amount
        split_amount = APP_SCALING_SPLIT_AMOUNT * (request["amount"] / abs(request["amount"]))  # This sets the sign
        request["amount"] = split_amount

        # Create smaller requests of 'split_amount' size
        while abs(remaining_amount) > 0 and abs(remaining_amount) > abs(split_amount):
            requests.append(dict(request))
            remaining_amount -= split_amount

        # If some remaining amount is left, create the last request
        if abs(remaining_amount) > 0:
            request["amount"] = remaining_amount
            requests.append(dict(request))

        # Get the request usage for all the containers and cache it
        resource_usage_cache = dict()
        for container in app_containers:
            amount, resource = request["amount"], request["resource"]
            metrics_to_retrieve = BDWATCHDOG_CONTAINER_METRICS[resource]
            resource_usage_cache[container["name"]] = self.bdwatchdog_handler.get_structure_timeseries(
                {"host": container["name"]}, 10, 20,
                metrics_to_retrieve, RESCALER_CONTAINER_METRICS)

        success, iterations = True, 0
        generated_requests = dict()

        while success and len(requests) > 0:
            request = requests.pop(0)
            success, container_to_rescale, generated_request = self.single_container_rescale(request, app_containers, resource_usage_cache)
            if success:
                # If rescaling was successful, update the container's resources as they have been rescaled
                for c in app_containers:
                    container_name = c["name"]
                    if container_name == container_to_rescale["name"]:
                        # Initialize
                        if container_name not in generated_requests:
                            generated_requests[container_name] = list()

                        generated_requests[container_name].append(generated_request)
                        container_to_rescale["resources"][request["resource"]]["current"] += request["amount"]
                        app_containers.remove(c)
                        app_containers.append(container_to_rescale)
                        break
            else:
                break

            iterations += 1

        # Collapse all the requests to generate just 1 per container
        final_requests = list()
        for container in generated_requests:
            # Copy the first request as the base request
            flat_request = dict(generated_requests[container][0])
            flat_request["amount"] = 0
            for request in generated_requests[container]:
                flat_request["amount"] += request["amount"]
            final_requests.append(flat_request)
        self.generate_requests(final_requests, structure["name"])

        if len(requests) > 0:
            # Couldn't completely rescale the application as some split of a major rescaling operation could not be completed
            log_warning("App {0} could not be completely rescaled, only: {1} shares of resource: {2} have been scaled".format(
                request["structure"], str(int(iterations * split_amount)), request["resource"]), self.debug)

    ######################################################

    ### SERVICE METHODS ####
    def invalid_conf(self, config):
        # TODO This code is duplicated on the structures and database snapshoters
        for key, num in [("POLLING_FREQUENCY", config.get_value("POLLING_FREQUENCY")), ("REQUEST_TIMEOUT", config.get_value("REQUEST_TIMEOUT"))]:
            if num < 5:
                return True, "Configuration item '{0}' with a value of '{1}' is likely invalid".format(key, num)
        return False, ""

    def get_cpu_list(self, cpu_num_string):
        # Translate something like '2-4,7' to [2,3,7]
        cpu_list = list()
        parts = cpu_num_string.split(",")
        for part in parts:
            ranges = part.split("-")
            if len(ranges) == 1:
                cpu_list.append(ranges[0])
            else:
                for n in range(int(ranges[0]), int(ranges[1]) + 1):
                    cpu_list.append(str(n))
        return cpu_list

    def get_current_resource_value(self, real_resources, resource):
        translation_dict = {"cpu": "cpu_allowance_limit", "mem": "mem_limit", "disk": "disk_write_limit"}

        if resource not in translation_dict:
            raise ValueError("Resource '{0}' unknown".format(resource))
        else:
            resource_translated = translation_dict[resource]

        if resource not in real_resources:
            raise ValueError("Resource '{0}' info missing from host".format(resource))

        if resource_translated not in real_resources[resource]:
            raise ValueError("Current value for resource '{0}' missing from host resource info".format(resource))

        current_resource_limit = real_resources[resource][resource_translated]

        if current_resource_limit == -1:
            raise ValueError("Resource {0} has not a 'current' value set, that is, it is unlimited".format(resource))
        else:
            try:
                current_resource_limit = int(current_resource_limit)
            except ValueError:
                raise ValueError("Bad current {0} limit value".format(resource))
        return current_resource_limit

    def process_requests(self, reqs):
        for request in reqs:
            structure_name = request["structure"]

            # Retrieve structure info
            try:
                structure = self.db_handler.get_structure(structure_name)
            except (requests.exceptions.HTTPError, ValueError):
                log_error("Error, couldn't find structure {0} in database".format(structure_name), self.debug)
                continue

            # Rescale the structure accordingly, whether it is a container or an application
            if structure_is_container(structure):
                self.rescale_container(request, structure)
            elif structure_is_application(structure):
                self.rescale_application(request, structure)
            else:
                log_error("Unknown type of structure '{0}'".format(structure["subtype"]), self.debug)

            # Remove the request from the database
            self.db_handler.delete_request(request)

    def split_requests(self, all_requests):
        scale_down, scale_up = list(), list()
        for request in all_requests:
            if "action" not in request or not request["action"]:
                continue
            elif request["action"].endswith("Down"):
                scale_down.append(request)
            elif request["action"].endswith("Up"):
                scale_up.append(request)
        return scale_down, scale_up

    def fill_host_info_cache(self, containers):
        self.host_info_cache = dict()
        for container in containers:
            if container["host"] not in self.host_info_cache:
                self.host_info_cache[container["host"]] = self.db_handler.get_structure(container["host"])
        return

    def persist_new_host_information(self, ):
        def persist_thread(self, host):
            data = self.host_info_cache[host]
            update_structure(data, self.db_handler, self.debug)

        threads = list()
        for host in self.host_info_cache:
            t = Thread(target=persist_thread, args=(self, host,))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

    def scale_structures(self, new_requests):
        log_info("Processing requests", self.debug)

        t0 = time.time()

        # Split the requests between scale down and scale up
        scale_down, scale_up = self.split_requests(new_requests)

        # Process first the requests that free resources, then the one that use them
        self.process_requests(scale_down)
        self.process_requests(scale_up)

        # Persist the new host information
        self.persist_new_host_information()

        t1 = time.time()
        log_info("It took {0} seconds to process requests".format(str("%.2f" % (t1 - t0))), self.debug)

    ######################################################

    def scale(self, ):
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

        myConfig = MyConfig(CONFIG_DEFAULT_VALUES)

        # Remove previous requests
        log_info("Purging any previous requests", True)
        self.filter_requests(0)
        log_info("----------------------\n", True)

        while True:
            # Remote database operation
            service = get_service(self.db_handler, SERVICE_NAME)

            # Heartbeat
            beat(self.db_handler, SERVICE_NAME)

            # CONFIG
            myConfig.set_config(service["config"])
            polling_frequency = myConfig.get_value("POLLING_FREQUENCY")
            request_timeout = myConfig.get_value("REQUEST_TIMEOUT")
            self.debug = myConfig.get_value("self.debug")
            CHECK_CORE_MAP = myConfig.get_value("CHECK_CORE_MAP")
            SERVICE_IS_ACTIVATED = myConfig.get_value("ACTIVE")

            log_info("----------------------", self.debug)
            log_info("Starting Epoch", self.debug)
            t0 = time.time()

            ## CHECK INVALID CONFIG ##
            # TODO This code is duplicated on the structures and database snapshoters
            invalid, message = self.invalid_conf(myConfig)
            if invalid:
                log_error(message, self.debug)
                time.sleep(polling_frequency)
                if polling_frequency < 5:
                    log_error("Polling frequency is too short, replacing with DEFAULT value '{0}'".format(CONFIG_DEFAULT_VALUES["POLLING_FREQUENCY"]), self.debug)
                    polling_frequency = CONFIG_DEFAULT_VALUES["POLLING_FREQUENCY"]

                log_info("----------------------\n", self.debug)
                time.sleep(polling_frequency)
                continue

            if SERVICE_IS_ACTIVATED:

                # Get the container structures and their resource information as such data is going to be needed
                containers = get_structures(self.db_handler, self.debug, subtype="container")
                try:
                    self.container_info_cache = get_container_resources_dict()  # Reset the cache
                except (Exception, RuntimeError) as e:
                    log_error("Error getting host document, skipping epoch altogether", self.debug)
                    log_error(str(e), self.debug)
                    time.sleep(polling_frequency)
                    continue

                # Fill the host information cache
                log_info("Getting host and container info", self.debug)
                try:
                    self.fill_host_info_cache(containers)
                except (Exception, RuntimeError) as e:
                    log_error("Error getting host document, skipping epoch altogether", self.debug)
                    log_error(str(e), self.debug)
                    time.sleep(polling_frequency)
                    continue

                # Do the core mapping check-up
                if CHECK_CORE_MAP:
                    log_info("Doing container CPU limits check", self.debug)
                    log_info("First hosts", self.debug)
                    errors_detected = self.check_host_cpu_limits()
                    if errors_detected:
                        log_error("Errors detected during host CPU limits check", self.debug)

                    log_info("Second containers", self.debug)
                    errors_detected = self.check_containers_cpu_limits(containers)
                    if errors_detected:
                        log_error("Errors detected during container CPU limits check", self.debug)

                    log_info("Doing core mapping check", self.debug)
                    errors_detected = self.check_core_mapping(containers)
                    if errors_detected:
                        log_error("Errors detected during container CPU map check", self.debug)
                else:
                    log_warning("Core map check has been disabled", self.debug)

                # Get the requests
                new_requests = self.filter_requests(request_timeout)
                container_reqs, app_reqs = self.sort_requests(new_requests)

                # Process first the application requests, as they generate container ones
                if app_reqs:
                    log_info("Processing applications requests", self.debug)
                    self.scale_structures(app_reqs)
                else:
                    log_info("No applications requests", self.debug)

                # Then process container ones
                if container_reqs:
                    log_info("Processing container requests", self.debug)
                    self.scale_structures(container_reqs)
                else:
                    log_info("No container requests", self.debug)

                t1 = time.time()
                log_info("Epoch processed in {0} seconds".format(str("%.2f" % (t1 - t0))), self.debug)

            else:
                log_warning("Scaler service is not activated", self.debug)

            log_info("----------------------\n", self.debug)
            time.sleep(polling_frequency)


def main():
    try:
        scaler = Scaler()
        scaler.scale()
    except Exception as e:
        log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
