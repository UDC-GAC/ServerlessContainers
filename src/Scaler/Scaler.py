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
from src.Guardian.Guardian import Guardian

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog


CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "REQUEST_TIMEOUT": 60, "DEBUG": True, "CHECK_CORE_MAP": True, "ACTIVE": True}
SERVICE_NAME = "scaler"

BDWATCHDOG_CONTAINER_METRICS = {"cpu": ['proc.cpu.user', 'proc.cpu.kernel'],
                                "mem": ['proc.mem.resident'],
                                #"disk": ['proc.disk.reads.mb', 'proc.disk.writes.mb'],
                                "disk_read": ['proc.disk.reads.mb'],
                                "disk_write": ['proc.disk.writes.mb'],
                                "net": ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']}
RESCALER_CONTAINER_METRICS = {'cpu': ['proc.cpu.user', 'proc.cpu.kernel'], 'mem': ['proc.mem.resident'],
                              #'disk': ['proc.disk.reads.mb', 'proc.disk.writes.mb'],
                              'disk_read': ['proc.disk.reads.mb'],
                              'disk_write': ['proc.disk.writes.mb'],
                              'net': ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']}

APP_SCALING_SPLIT_AMOUNT = 5
MIN_SHARES_PER_SOCKET = 200


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
        utils.log_error("Error processing container resource change in host in IP {0}".format(rescaler_ip), debug)
        utils.log_error(str(json.dumps(r.json())), debug)
        r.raise_for_status()


def get_cpu_topology(rescaler_http_session, container, debug):
    rescaler_ip = container["host_rescaler_ip"]
    rescaler_port = container["host_rescaler_port"]
    r = rescaler_http_session.get("http://{0}:{1}/host/cpu_topology".format(rescaler_ip, rescaler_port),
                                  headers={'Accept': 'application/json'})
    if r.status_code == 200:
        return dict(r.json())

    utils.log_error("Error getting CPU topology from host in IP {0}".format(rescaler_ip), debug)
    r.raise_for_status()


class Scaler:
    """
    Scaler class that implements the logic for this microservice.
    """

    def __init__(self):
        self.couchdb_handler = couchdb.CouchDBServer()
        self.rescaler_http_session = requests.Session()
        self.bdwatchdog_handler = bdwatchdog.OpenTSDBServer()
        self.host_info_cache, self.container_info_cache = dict(), dict()
        self.apply_request_by_resource = {"cpu": self.apply_cpu_request, "mem": self.apply_mem_request, "disk_read": self.apply_disk_read_request, "disk_write": self.apply_disk_write_request, "net": self.apply_net_request}
        self.polling_frequency, self.request_timeout, self.debug, self.check_core_map, self.active = None, None, None, None, None

    ####################################################################################################################
    # CHECKS
    ####################################################################################################################
    def fix_container_cpu_mapping(self, container, cpu_used_cores, cpu_used_shares):
        resource_dict = {
            "cpu": {"cpu_num": ",".join(cpu_used_cores), "cpu_allowance_limit": int(cpu_used_shares)}
        }
        try:
            # TODO FIX this error should be further diagnosed, in case it affects other modules who use this call too
            set_container_resources(self.rescaler_http_session, container, resource_dict, self.debug)
            return True
        except (Exception, RuntimeError, ValueError, requests.HTTPError) as e:
            utils.log_error("Error when setting container resources: {0}".format(str(e)), self.debug)
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
                utils.log_error("Host {0} has more mapped shares than its maximum".format(host["name"]), self.debug)
                errors_detected = True
        return errors_detected

    def get_bound_disk(self, container_name):
        container = self.couchdb_handler.get_structure(container_name)
        return container["resources"]["disk"]["name"]

    def check_host_has_enough_free_resources(self, host_info, needed_resources, resource, container_name):
        if resource in ["disk_read", "disk_write"]:
            bound_disk = self.get_bound_disk(container_name)
            disk_op = resource.split("_")[-1]
            host_shares = host_info["resources"]["disks"][bound_disk]["free_{0}".format(disk_op)]
        else:
            host_shares = host_info["resources"][resource]["free"]

        if host_shares == 0:
            raise ValueError("No resources available for resource {0} in host {1} ".format(resource, host_info["name"]))
        elif host_shares < needed_resources:
            missing_shares = needed_resources - host_shares
            utils.log_warning("Beware, there are not enough free shares for container {0} for resource {1} in the host, "
                              "there are {2}, missing {3}".format(container_name, resource, host_shares, missing_shares), self.debug)

        if resource == "disk_read" or resource == "disk_write":
            max_read = host_info["resources"]["disks"][bound_disk]["max_read"]
            max_write = host_info["resources"]["disks"][bound_disk]["max_write"]
            consumed_read = max_read - host_info["resources"]["disks"][bound_disk]["free_read"]
            consumed_write = max_write - host_info["resources"]["disks"][bound_disk]["free_write"]
            current_disk_free = max(max_read, max_write) - consumed_read - consumed_write
            if current_disk_free < needed_resources:
                missing_shares = needed_resources - current_disk_free
                utils.log_warning("Beware, there is not enough free total bandwidth for container {0} for resource "
                                  "{1} in the host, there are {2},  missing {3}".format(container_name, resource, current_disk_free, missing_shares), self.debug)

    def check_containers_cpu_limits(self, containers):
        errors_detected = False
        for container in containers:
            database_resources = container["resources"]

            if "max" not in database_resources["cpu"]:
                utils.log_error("container {0} has not a maximum value set, check its configuration".format(container["name"]), self.debug)
                errors_detected = True
                continue

            max_cpu_limit = database_resources["cpu"]["max"]
            try:
                real_resources = self.container_info_cache[container["name"]]["resources"]
                current_cpu_limit = self.get_current_resource_value(real_resources, "cpu")
                if current_cpu_limit > max_cpu_limit:
                    utils.log_error("container {0} has, somehow, more shares ({1}) than the maximum ({2}), check the max "
                                    "parameter in its configuration".format(container["name"], current_cpu_limit, max_cpu_limit), self.debug)
                    errors_detected = True
            except KeyError:
                utils.log_error("container {0} not found, maybe is down or has been desubscribed"
                                .format(container["name"]), self.debug)
                errors_detected = True
            except ValueError as e:
                utils.log_error("Current value of structure {0} is not valid: {1}".format(container["name"], str(e)), self.debug)
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
            if core_usage_map.get(core, {}).get(container_name, 0) != 0:
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
            utils.log_error("Host info '{0}' for container {1} is missing".format(container["host"], container["name"]), self.debug)
            return True
        elif "max" not in database_resources["cpu"]:
            # This error should have been previously detected
            return True
        else:
            try:
                current_cpu_limit = self.get_current_resource_value(real_resources, "cpu")
            except ValueError as e:
                utils.log_error(e, self.debug)
                return True

        host_info = self.host_info_cache[container["host"]]
        max_cpu_limit = database_resources["cpu"]["max"]
        cpu_list = self.get_cpu_list(real_resources["cpu"]["cpu_num"])
        c_name = container["name"]

        map_host_valid, actual_used_cores, actual_used_shares = self.check_container_cpu_mapping(container, host_info, cpu_list, current_cpu_limit)

        if not map_host_valid:
            utils.log_error("Detected invalid core mapping for container {0}, has {1}-{2}, should be {3}-{4}".format(
                c_name, cpu_list, current_cpu_limit, actual_used_cores, actual_used_shares), self.debug)
            utils.log_error("Trying to automatically fix", self.debug)
            success = self.fix_container_cpu_mapping(container, actual_used_cores, actual_used_shares)
            if success:
                utils.log_error("Succeeded fixing {0} container's core mapping".format(container["name"]), self.debug)
                errors_detected = True
            else:
                utils.log_error("Failed in fixing {0} container's core mapping".format(container["name"]), self.debug)
                errors_detected = False
        return errors_detected

    def check_core_mapping(self, containers):
        errors_detected = False
        for container in containers:
            c_name = container["name"]
            utils.log_info("Checking container {0}".format(c_name), self.debug)
            real_resources = self.container_info_cache.get(c_name, {}).get("resources", None)
            if real_resources is None:
                utils.log_error("Couldn't get container's {0} resources, can't check its sanity".format(c_name), self.debug)
                continue

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

    ####################################################################################################################
    # REQUEST MANAGEMENT
    ####################################################################################################################
    def filter_requests(self, request_timeout):
        fresh_requests, purged_requests, final_requests = list(), list(), list()
        # Remote database operation
        all_requests = self.couchdb_handler.get_requests()
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

                if "priority" in stored_request and "priority" in request and stored_request["priority"] != request["priority"]:
                    # First, try comparing priorities
                    higher_priority_request = stored_request if stored_request["priority"] > request["priority"] else request
                else:
                    # If no priorities available, compare timestamps (newer requests are prioritised)
                    higher_priority_request = stored_request if stored_request["timestamp"] > request["timestamp"] else request

                if higher_priority_request is stored_request:
                    # The stored request has a higher priority or is newer, leave it and mark the retrieved one to be removed
                    purged_requests.append(request)
                else:
                    # The stored request has a lower priority or is older, mark it to be removed and save the retrieved one
                    purged_requests.append(stored_request)
                    structure_requests_dict[structure][action] = request

                duplicated_counter += 1

        self.couchdb_handler.delete_requests(purged_requests)

        for structure in structure_requests_dict:
            for action in structure_requests_dict[structure]:
                final_requests.append(structure_requests_dict[structure][action])

        utils.log_info("Number of purged/duplicated requests was {0}/{1}".format(purged_counter, duplicated_counter), True)
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

    ####################################################################################################################
    # RESOURCE REQUEST MANAGEMENT
    ####################################################################################################################
    def process_request(self, request, real_resources, database_resources):
        # Create a 'fake' container structure with only the required info
        container = {"host_rescaler_ip": request["host_rescaler_ip"],
                     "host_rescaler_port": request["host_rescaler_port"],
                     "name": request["structure"]}

        # Apply the request and get the new resources to set
        try:
            new_resources = self.apply_request(request, real_resources, database_resources)
            if new_resources:
                utils.log_info("Request: {0} for container : {1} for new resources : {2}".format(
                    request["action"], request["structure"], json.dumps(new_resources)), self.debug)

                # Apply changes through a REST call
                set_container_resources(self.rescaler_http_session, container, new_resources, self.debug)

                ## Update container info in cache (useful if there are multiple requests for the same container)
                self.container_info_cache[request["structure"]]["resources"][request["resource"]] = new_resources[request["resource"]]

        except (ValueError) as e:
            utils.log_error("Error with container {0} in applying the request -> {1}".format(request["structure"], str(e)), self.debug)
            return
        except (HTTPError) as e:
            utils.log_error("Error setting container {0} resources -> {1}".format(request["structure"], str(e)), self.debug)
            return
        except (Exception) as e:
            utils.log_error("Error with container {0} -> {1}".format(request["structure"], str(e)), self.debug)
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

    @staticmethod
    def __scale_cpu(core_usage_map, take_core_list, used_cores, structure_name, amount, scale_up=True):
        # When scaling up, we take shares from 'free' and put them into the structure_name
        # when scaling down, we take shares from the structure_name and put them into 'free'
        from_key = "free" if scale_up else structure_name
        to_key = structure_name if scale_up else "free"

        original_amount = amount
        for core in take_core_list:
            if amount <= 0:
                break
            if core_usage_map.get(core, {}).get(from_key, 0) > 0:
                take = min(core_usage_map[core][from_key], amount)
                core_usage_map[core][from_key] -= take
                core_usage_map[core][to_key] += take
                amount -= take

                # If we are scaling up, we add the core to the used_cores list if it is not already there
                if scale_up:
                    if core not in used_cores:
                        used_cores.append(core)
                # If we are scaling down, we remove the core from used_cores if it has no shares left
                else:
                    if core_usage_map[core][structure_name] == 0 and core in used_cores:
                        used_cores.remove(core)
        return amount, original_amount - amount

    @staticmethod
    def __generate_core_dist(topology, dist_name):
        core_dist = []
        supported_distributions = ["Group_P&L", "Group_1P_2L", "Group_PP_LL", "Spread_P&L", "Spread_PP_LL"]
        if dist_name not in supported_distributions:
            raise ValueError("Invalid core distribution: {0}. Supported {1}.".format(dist_name, supported_distributions))

        # Pairs of physical and logical cores, one socket at a time
        if dist_name == "Group_P&L":
            for sk_id in topology:
                for core_id in topology[sk_id]:
                    core_dist.extend(topology[sk_id][core_id])

        # First physical cores, then logical cores, one socket at a time
        if dist_name == "Group_1P_2L":
            for sk_id in topology:
                phy_c, log_c = [], []
                for core_id in topology[sk_id]:
                    phy_c.append(topology[sk_id][core_id][0])
                    log_c.extend(topology[sk_id][core_id][1:])
                core_dist.extend(phy_c)
                core_dist.extend(log_c)

        # First physical cores, from both sockets, then logical cores
        if dist_name == "Group_PP_LL":
            phy_c, log_c = [], []
            for sk_id in topology:
                for core_id in topology[sk_id]:
                    phy_c.append(topology[sk_id][core_id][0])
                    log_c.extend(topology[sk_id][core_id][1:])
            core_dist.extend(phy_c)
            core_dist.extend(log_c)

        # Pairs of physical and logical cores, alternating between sockets
        if dist_name == "Spread_P&L":
            other_sk = sorted(topology, key=lambda sk: len(topology[sk]))
            sk_id = other_sk.pop()
            for core_id in topology[sk_id]:
                core_dist.extend(topology[sk_id][core_id])
                for sk2_id in other_sk:
                    core_dist.extend(topology[sk2_id].get(core_id, []))

        # Phirst physical cores, then logical cores, alternating between sockets
        if dist_name == "Spread_PP_LL":
            other_sk = sorted(topology, key=lambda sk: len(topology[sk]))
            sk_id = other_sk.pop()
            phy_c, log_c = [], []
            for core_id in topology[sk_id]:
                phy_c.append(topology[sk_id][core_id][0])
                log_c.extend(topology[sk_id][core_id][1:])
                for sk2_id in other_sk:
                    phy_c.extend(topology[sk2_id].get(core_id, [])[0:1])
                    log_c.extend(topology[sk2_id][core_id][1:])
            core_dist.extend(phy_c)
            core_dist.extend(log_c)

        return [str(c) for c in core_dist]

    def apply_cpu_request(self, request, database_resources, real_resources, amount):
        resource = request["resource"]
        structure_name = request["structure"]
        host_info = self.host_info_cache[request["host"]]
        core_usage_map = host_info["resources"][resource]["core_usage_mapping"]
        current_cpu_limit = self.get_current_resource_value(real_resources, resource)
        structure_cpu_list = self.get_cpu_list(real_resources["cpu"]["cpu_num"])

        host_max_cores = int(host_info["resources"]["cpu"]["max"] / 100)
        host_cpu_list = [str(i) for i in range(host_max_cores)]
        for core in host_cpu_list:
            if core not in core_usage_map:
                core_usage_map[core] = dict()
                core_usage_map[core]["free"] = 100
            if structure_name not in core_usage_map[core]:
                core_usage_map[core][structure_name] = 0

        used_cores = list(structure_cpu_list)  # copy

        # Get CPU topology from host and generate core distribution
        cpu_topology = get_cpu_topology(self.rescaler_http_session, request, self.debug)
        # TODO: Add core_distribution as a tunable service parameter
        core_distribution = self.__generate_core_dist(cpu_topology, "Group_PP_LL")

        # RESCALE UP
        if amount > 0:
            needed_shares = amount

            # 1) Fill first the already used cores following core distribution order
            used_cores_sorted = [c for c in core_distribution if c in used_cores]
            needed_shares, assigned = self.__scale_cpu(core_usage_map, used_cores_sorted, used_cores, structure_name, needed_shares)

            # 2) Fill the completely free cores following core distribution order
            completely_free_cores = [c for c in core_distribution if c not in used_cores and core_usage_map[c]["free"] == 100]
            needed_shares, assigned = self.__scale_cpu(core_usage_map, completely_free_cores, used_cores, structure_name, needed_shares)

            # 3) Fill the remaining cores that are not completely free, following core distribution order
            remaining_cores = [c for c in core_distribution if c not in used_cores and core_usage_map[c]["free"] < 100]
            needed_shares, assigned = self.__scale_cpu(core_usage_map, remaining_cores, used_cores, structure_name, needed_shares)

            if needed_shares > 0:
                utils.log_warning("Structure {0} couldn't get as much CPU shares as intended ({1}), instead it got {2}"
                                  .format(structure_name, amount, amount - needed_shares), self.debug)
                amount = amount - needed_shares

        # RESCALE DOWN
        elif amount < 0:
            shares_to_free = abs(amount)

            # Sort cores by reverse core distribution order
            rev_core_distribution = list(reversed(core_distribution))
            used_cores_sorted = [c for c in rev_core_distribution if c in used_cores]

            # 1) Free cores starting with the least used ones and following reverse core distribution order
            least_used_cores = sorted(used_cores_sorted, key=lambda c: core_usage_map[c][structure_name])
            shares_to_free, freed = self.__scale_cpu(core_usage_map, least_used_cores, used_cores, structure_name, shares_to_free, scale_up=False)

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

    def apply_disk_read_request(self, request, database_resources, real_resources, amount):
        resource_dict = {request["resource"]: {}}
        bound_disk = self.get_bound_disk(request['structure'])
        current_read_free = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free_read"]
        current_write_free = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free_write"]

        if amount > current_read_free:
            ## It is trying to get more resources than available
            amount = current_read_free

        max_read = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["max_read"]
        max_write = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["max_write"]
        consumed_read = max_read - current_read_free
        consumed_write = max_write - current_write_free
        current_disk_free = max(max_read, max_write) - consumed_read - consumed_write
        if amount > current_disk_free:
            ## It is trying to get more resources than total available bandwidth
            amount = current_disk_free

        # No error thrown, so persist the new mapping to the cache
        self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free_read"] -= amount

        # Return the dictionary to set the resources
        current_read_limit = self.get_current_resource_value(real_resources, request["resource"])
        resource_dict["disk_read"]["disk_read_limit"] = str(int(amount + current_read_limit))

        return resource_dict

    def apply_disk_write_request(self, request, database_resources, real_resources, amount):
        resource_dict = {request["resource"]: {}}
        bound_disk = self.get_bound_disk(request['structure'])
        current_read_free = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free_read"]
        current_write_free = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free_write"]

        if amount > current_write_free:
            ## It is trying to get more resources than available
            amount = current_write_free

        max_read = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["max_read"]
        max_write = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["max_write"]
        consumed_read = max_read - current_read_free
        consumed_write = max_write - current_write_free
        current_disk_free = max(max_read, max_write) - consumed_read - consumed_write
        if amount > current_disk_free:
            ## It is trying to get more resources than total available bandwidth
            amount = current_disk_free

        # No error thrown, so persist the new mapping to the cache
        self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free_write"] -= amount

        # Return the dictionary to set the resources
        current_write_limit = self.get_current_resource_value(real_resources, request["resource"])
        resource_dict["disk_write"]["disk_write_limit"] = str(int(amount + current_write_limit))

        return resource_dict

    def apply_net_request(self, request, database_resources, real_resources, amount):
        resource_dict = {request["resource"]: {}}
        current_net_limit = self.get_current_resource_value(real_resources, request["resource"])

        # Return the dictionary to set the resources
        resource_dict["net"]["net_limit"] = str(int(amount + current_net_limit))

        return resource_dict

    ####################################################################################################################
    # CONTAINER SCALING
    ####################################################################################################################
    def rescale_container(self, request, structure):
        try:
            # Needed for the resources reported in the database (the 'max, min' values)
            database_resources = structure

            # Get the resources the container is using from its host NodeScaler (the 'current' value)
            c_name = structure["name"]
            if c_name not in self.container_info_cache or "resources" not in self.container_info_cache[c_name]:
                utils.log_error("Couldn't get container's {0} resources, can't rescale".format(c_name), self.debug)
                return
            real_resources = self.container_info_cache[c_name]["resources"]

            # Process the request
            self.process_request(request, real_resources, database_resources)
        except Exception as e:
            utils.log_error(str(e) + " " + str(traceback.format_exc()), self.debug)

    ####################################################################################################################
    # APPLICATION SCALING
    ####################################################################################################################
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
            self.couchdb_handler.add_request(req)
            rescaled_containers.append((req["structure"], req["amount"]))
            total_amount += req["amount"]
        utils.log_info("App {0} rescaled {1} shares by rescaling containers: {2}".format(app_label, total_amount, str(rescaled_containers)), self.debug)

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
                    # utils.log_error("Container {0} can't free that amount without dropping under the minimum".format(container["name"]), self.debug)
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
                    # utils.log_error("Container's host doesn't have enough free resources", self.debug)
                    pass
                elif current_value + amount > container["resources"][resource_label]["max"]:
                    # Container can't get that amount without exceeding the maximum
                    # utils.log_error("Container can't get that amount without exceeding the maximum", self.debug)
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
            container = self.couchdb_handler.get_structure(cont_name)
            app_containers.append(container)

            # Retrieve host info and cache it in case other containers or applications need it
            if container["host"] not in self.host_info_cache:
                self.host_info_cache[container["host"]] = self.couchdb_handler.get_structure(container["host"])

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
            utils.log_warning("App {0} could not be completely rescaled, only: {1} shares of resource: {2} have been scaled".format(
                request["structure"], str(int(iterations * split_amount)), request["resource"]), self.debug)

    ####################################################################################################################
    # SERVICE METHODS
    ####################################################################################################################
    def invalid_conf(self, ):
        # TODO This code is duplicated on the structures and database snapshoters
        for key, num in [("POLLING_FREQUENCY", self.polling_frequency), ("REQUEST_TIMEOUT", self.request_timeout)]:
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
        translation_dict = {"cpu": "cpu_allowance_limit", "mem": "mem_limit", "disk_read": "disk_read_limit", "disk_write": "disk_write_limit"}

        if resource not in translation_dict:
            raise ValueError("Resource '{0}' unknown".format(resource))
        else:
            resource_translated = translation_dict[resource]

        if resource not in real_resources:
            raise ValueError("Resource '{0}' info missing from host ({1})".format(resource, real_resources))

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
                structure = self.couchdb_handler.get_structure(structure_name)
            except (requests.exceptions.HTTPError, ValueError):
                utils.log_error("Error, couldn't find structure {0} in database".format(structure_name), self.debug)
                continue

            # Rescale the structure accordingly, whether it is a container or an application
            if utils.structure_is_container(structure):
                self.rescale_container(request, structure)
            elif utils.structure_is_application(structure):
                self.rescale_application(request, structure)
            else:
                utils.log_error("Unknown type of structure '{0}'".format(structure["subtype"]), self.debug)

            # Remove the request from the database
            self.couchdb_handler.delete_request(request)

    def split_requests(self, all_requests):
        ## Sort requests by priority
        # This is important for prioritizing requests of different structures
        # Example: ReBalancer requests to scale down container1 and scale up container2, while Guardian requests to scale up both containers
        # The scaling down of container1 is executed first. Then, if no priority order is enforced, the scaling up of container1 could be executed before the scaling up of container2, thus making the ReBalancer scale down request useless
        sorted_requests = sorted(all_requests, key=lambda request: request["priority"] if "priority" in request else 0, reverse=True)

        scale_down, scale_up = list(), list()
        for request in sorted_requests:
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
                self.host_info_cache[container["host"]] = self.couchdb_handler.get_structure(container["host"])
        return

    def persist_new_host_information(self, ):
        def persist_thread(self, host):
            data = self.host_info_cache[host]
            utils.update_structure(data, self.couchdb_handler, self.debug)

        threads = list()
        for host in self.host_info_cache:
            t = Thread(target=persist_thread, args=(self, host,))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

    def scale_structures(self, new_requests):
        utils.log_info("Processing requests", self.debug)

        t0 = time.time()

        # Split the requests between scale down and scale up
        scale_down, scale_up = self.split_requests(new_requests)

        # Process first the requests that free resources, then the one that use them
        self.process_requests(scale_down)
        self.process_requests(scale_up)

        # Persist the new host information
        self.persist_new_host_information()

        t1 = time.time()
        utils.log_info("It took {0} seconds to process requests".format(str("%.2f" % (t1 - t0))), self.debug)

    ####################################################################################################################
    # MAIN LOOP
    ####################################################################################################################
    def scale(self, ):
        myConfig = utils.MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO,
                            format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        # Remove previous requests
        utils.log_info("Purging any previous requests", True)
        self.filter_requests(0)
        utils.log_info("----------------------\n", True)

        while True:
            utils.update_service_config(self, SERVICE_NAME, myConfig, self.couchdb_handler)

            t0 = utils.start_epoch(self.debug)

            utils.print_service_config(self, myConfig, self.debug)

            ## CHECK INVALID CONFIG ##
            # TODO This code is duplicated on the structures and database snapshoters
            invalid, message = self.invalid_conf()
            if invalid:
                utils.log_error(message, self.debug)
                time.sleep(self.polling_frequency)
                if self.polling_frequency < 5:
                    utils.log_error("Polling frequency is too short, replacing with DEFAULT value '{0}'".format(CONFIG_DEFAULT_VALUES["POLLING_FREQUENCY"]), self.debug)
                    self.polling_frequency = CONFIG_DEFAULT_VALUES["POLLING_FREQUENCY"]

                utils.log_info("----------------------\n", self.debug)
                time.sleep(self.polling_frequency)
                continue

            if self.active:
                # Get the container structures and their resource information as such data is going to be needed
                containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
                try:
                    self.container_info_cache = utils.get_container_resources_dict(containers, self.rescaler_http_session, self.debug)  # Reset the cache
                except (Exception, RuntimeError) as e:
                    utils.log_error("Error getting host document, skipping epoch altogether", self.debug)
                    utils.log_error(str(e), self.debug)
                    time.sleep(self.polling_frequency)
                    continue

                # Fill the host information cache
                utils.log_info("Getting host and container info", self.debug)
                try:
                    self.fill_host_info_cache(containers)
                except (Exception, RuntimeError) as e:
                    utils.log_error("Error getting host document, skipping epoch altogether", self.debug)
                    utils.log_error(str(e), self.debug)
                    time.sleep(self.polling_frequency)
                    continue

                # Do the core mapping check-up
                if self.check_core_map:
                    utils.log_info("Doing container CPU limits check", self.debug)
                    utils.log_info("First hosts", self.debug)
                    errors_detected = self.check_host_cpu_limits()
                    if errors_detected:
                        utils.log_error("Errors detected during host CPU limits check", self.debug)

                    utils.log_info("Second containers", self.debug)
                    errors_detected = self.check_containers_cpu_limits(containers)
                    if errors_detected:
                        utils.log_error("Errors detected during container CPU limits check", self.debug)

                    utils.log_info("Doing core mapping check", self.debug)
                    errors_detected = self.check_core_mapping(containers)
                    if errors_detected:
                        utils.log_error("Errors detected during container CPU map check", self.debug)
                else:
                    utils.log_warning("Core map check has been disabled", self.debug)

                # Get the requests
                new_requests = self.filter_requests(self.request_timeout)
                container_reqs, app_reqs = self.sort_requests(new_requests)

                # Process first the application requests, as they generate container ones
                if app_reqs:
                    utils.log_info("Processing applications requests", self.debug)
                    self.scale_structures(app_reqs)
                else:
                    utils.log_info("No applications requests", self.debug)

                # Then process container ones
                if container_reqs:
                    utils.log_info("Processing container requests", self.debug)
                    self.scale_structures(container_reqs)
                else:
                    utils.log_info("No container requests", self.debug)

                t1 = time.time()
                utils.log_info("Epoch processed in {0} seconds".format(str("%.2f" % (t1 - t0))), self.debug)

            else:
                utils.log_warning("Scaler service is not activated", self.debug)

            utils.log_info("----------------------\n", self.debug)
            time.sleep(self.polling_frequency)


def main():
    try:
        scaler = Scaler()
        scaler.scale()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
