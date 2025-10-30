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

from requests import HTTPError
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

import src.MyUtils.MyUtils as utils
import src.StateDatabase.opentsdb as bdwatchdog

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
USER_SCALING_SPLIT_AMOUNT = 5
MIN_SHARES_PER_SOCKET = 200

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "REQUEST_TIMEOUT": 60, "DEBUG": True, "CHECK_CORE_MAP": True, "ACTIVE": True}


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


class Scaler(Service):
    """
    Scaler class that implements the logic for this microservice.
    """

    def __init__(self):
        super().__init__("scaler", ConfigValidator(min_frequency=3), CONFIG_DEFAULT_VALUES, sleep_attr="polling_frequency")
        self.rescaler_http_session = requests.Session()
        self.bdwatchdog_handler = bdwatchdog.OpenTSDBServer()
        self.host_info_cache, self.host_changes, self.container_info_cache = {}, {}, {}
        self.last_request_retrieval = None
        self.rollbacks_tracker = {"container": [], "application": [], "user": []}
        self.apply_request_by_resource = {"cpu": self.apply_cpu_request, "mem": self.apply_mem_request, "disk_read": self.apply_disk_read_request, "disk_write": self.apply_disk_write_request, "energy": self.apply_energy_request, "net": self.apply_net_request}
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
        if resource in {"disk_read", "disk_write"}:
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

        if resource in {"disk_read", "disk_write"}:
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
            real_resources = self.container_info_cache.get(c_name, {}).get("resources", {})
            if not real_resources:
                utils.log_error("Couldn't get container's {0} resources, can't check its sanity".format(c_name), self.debug)
                continue

            errors = self.check_container_core_mapping(container, real_resources)
            errors_detected = errors_detected or errors
        return errors_detected

    @staticmethod
    def check_invalid_resource_value(database_resources, amount, current, resource, field):
        max_resource_limit = int(database_resources["resources"][resource]["max"])
        min_resource_limit = int(database_resources["resources"][resource]["min"])

        if field == "max":
            new_value = int(max_resource_limit + amount)
            if new_value < current:
                raise ValueError("Error in setting {0}, new max {1} would be lower than current {2}".format(resource, new_value, current))

        if field == "current":
            new_value = int(current + amount)
            if new_value < 0:
                raise ValueError("Error in setting {0}, current would be lower than 0".format(resource))
            elif new_value < min_resource_limit:
                raise ValueError("Error in setting {0}, new current {1} would be lower than min {2}".format(resource, new_value, min_resource_limit))
            elif new_value > max_resource_limit:
                raise ValueError("Error in setting {0}, new current {1} would be higher than max {2}".format(resource, new_value, max_resource_limit))

    ####################################################################################################################
    # REQUEST MANAGEMENT
    ####################################################################################################################
    def filter_requests(self, request_timeout):
        fresh_requests, purged_requests, final_requests = [], [], []
        purged_counter = 0
        duplicated_counter = 0

        # Remote database operation
        all_requests = self.couchdb_handler.get_requests()
        self.last_request_retrieval = time.time()

        # First purge the old requests
        for request in all_requests:
            if request["timestamp"] < self.last_request_retrieval - request_timeout:
                purged_requests.append(request)
                purged_counter += 1
            else:
                fresh_requests.append(request)

        # Then remove repeated requests for the same structure if found
        structure_requests_dict = {}
        for request in fresh_requests:
            structure_name = request["structure"]  # The structure name (string), acting as an id
            action = request["action"]  # The action name (string)
            field = request["field"]  # Structure field that will be modified (i.e., "current" or "max")
            action_field = "{0}_{1}".format(action, field)  # Used as a unique identifier
            stored_request = structure_requests_dict.get(structure_name, {}).get(action_field,  None)
            if stored_request:
                # A previous request was found for this structure, remove old one and leave the newer one
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
                    structure_requests_dict[structure_name][action_field] = request

                duplicated_counter += 1
            else:
                structure_requests_dict[structure_name] = {action_field: request}

        self.couchdb_handler.delete_requests(purged_requests)

        for structure in structure_requests_dict:
            for action_field in structure_requests_dict[structure]:
                final_requests.append(structure_requests_dict[structure][action_field])

        utils.log_info("Number of purged/duplicated requests was {0}/{1}".format(purged_counter, duplicated_counter), True)
        return final_requests

    @staticmethod
    def split_requests_by_structure_type(new_requests):
        container_reqs, app_reqs, user_reqs = [], [], []
        for r in new_requests:
            if r["structure_type"] == "container":
                container_reqs.append(r)
            if r["structure_type"] == "application":
                app_reqs.append(r)
            if r["structure_type"] == "user":
                user_reqs.append(r)
        return container_reqs, app_reqs, user_reqs

    @staticmethod
    def split_requests_by_action(all_requests):
        # Sort requests by priority. This is important for prioritizing requests of different structures
        # Example: ReBalancer requests to scale down container1 and scale up container2, while Guardian requests to
        # scale up both containers. The scaling down of container1 is executed first. Then, if no priority order is
        # enforced, the scaling up of container1 could be executed before the scaling up of container2, thus making
        # the ReBalancer scale down request useless
        sorted_requests = sorted(all_requests, key=lambda r: r.get("priority", 0), reverse=True)
        scale_down, scale_up = [], []
        for request in sorted_requests:
            if not request.get("action", None):
                continue
            elif request["action"].endswith("Down"):
                scale_down.append(request)
            elif request["action"].endswith("Up"):
                scale_up.append(request)
        return scale_down, scale_up

    @staticmethod
    def split_requests_by_field(all_requests):
        # This is important to avoid collisions in rebalancer "max" donations. Donors donate a "max" amount based on its
        # "current" value. Then, if "current" value is changed before "max" donation, the donated amount may become invalid
        scale_max, scale_current = [], []
        for request in all_requests:
            field = request.get("field", "current")
            if field == "max":
                scale_max.append(request)
            elif field == "current":
                scale_current.append(request)
        return scale_max, scale_current

    @staticmethod
    def flatten_requests(all_requests):
        final_requests = []
        requests_dict = {}
        for request in all_requests:
            structure_name = request["structure"]  # The structure name (string), acting as an id
            action = request["action"]  # The action name (string)
            field = request["field"]  # Structure field that will be modified (i.e., "current" or "max")
            action_field = "{0}_{1}".format(action, field)  # Used as a unique identifier
            if not requests_dict.get(structure_name, {}).get(action_field, None):
                requests_dict[structure_name] = {action_field: request}
            else:
                requests_dict[structure_name][action_field]["amount"] += request["amount"]

        for structure in requests_dict:
            for action_field in requests_dict[structure]:
                final_requests.append(requests_dict[structure][action_field])

        return final_requests

    @staticmethod
    def flatten_requests_by_structure(requests_by_structure):
        final_requests, rescaled_structures = [], []
        for structure_name in requests_by_structure:
            # Copy the first request as the base request
            flat_request = dict(requests_by_structure[structure_name][0])
            flat_request["amount"] = sum([r["amount"] for r in requests_by_structure[structure_name]])
            final_requests.append(flat_request)
            rescaled_structures.append((structure_name, flat_request["amount"]))

        return final_requests, rescaled_structures

    @staticmethod
    def rollback_pair_requests(rollback_reqs, pair_reqs):
        # Create a dict with the amount of each resource pair-swapping that it's going through a rollback
        rollback_amount = {}
        unprocessed_rollbacks = []
        for r in rollback_reqs:
            _id = "{0}-{1}-{2}".format(r["structure"], r["pair_structure"], r["resource"])
            rollback_amount[_id] = rollback_amount.get(_id, 0) + abs(r["amount"])

        # Remove the requests that are the counterpart of a pair-swapping request that has suffered a rollback
        new_reqs = []
        for r in pair_reqs:
            if r.get("pair_structure", ""):
                _id = "{0}-{1}-{2}".format(r["pair_structure"], r["structure"], r["resource"])
                if rollback_amount.get(_id, 0) > 0:
                    # Rollback is done -> request is not added to new_reqs
                    rollback_amount[_id] -= abs(r["amount"])
                else:
                    new_reqs.append(r)
            else:
                new_reqs.append(r)

        for r in rollback_reqs:
            _id = "{0}-{1}-{2}".format(r["structure"], r["pair_structure"], r["resource"])
            if rollback_amount[_id] > 0:
                new_amount = rollback_amount[_id] if r["amount"] > 0 else -rollback_amount[_id]
                r["amount"] = new_amount
                unprocessed_rollbacks.append(r)
                rollback_amount[_id] = 0

        return new_reqs, unprocessed_rollbacks

    def rollback_generated_requests(self, rollback_reqs, child_reqs, field):
        parent_type, threads = None, []
        rollback_amount, updated_parents = {}, {}

        # Create a dict with the amount of each resource pair-swapping that it's going through a rollback
        for r in rollback_reqs:
            _id = "{0}-{1}-{2}".format(r["structure"], r["pair_structure"], r["resource"])
            rollback_amount[_id] = rollback_amount.get(_id, 0) + abs(r["amount"])
            if parent_type is None:
                parent_type = r["structure_type"]

        # Remove the child requests that has been generated as part or a pair-swapping that is suffering a rollback
        new_child_reqs = []
        for r in child_reqs:
            structure_key = "for_{0}".format(parent_type)
            pair_key = "pair_{0}".format(parent_type)
            if r.get(pair_key, "") and r.get(structure_key, ""):
                _id = "{0}-{1}-{2}".format(r[pair_key], r[structure_key], r["resource"])
                if rollback_amount.get(_id, 0) > 0:
                    # Rollback is done -> request is not added to new_child_reqs
                    rollback_amount[_id] -= abs(r["amount"])
                    if field == "max":
                        updated_parents.setdefault(r[structure_key], {}).setdefault(r["resource"], 0)
                        updated_parents[r[structure_key]][r["resource"]] += r["amount"]
                else:
                    new_child_reqs.append(r)
            else:
                new_child_reqs.append(r)

        # If the requests modify "max" field, reset the parent structure to its original "max" value
        for parent_name, resources in updated_parents.items():
            if parent_type == "user":
                parent = self.couchdb_handler.get_user(parent_name)
            else:
                parent = self.couchdb_handler.get_structure(parent_name)
            # Reset "max" value for each affected resource
            for resource in resources:
                parent["resources"][resource][field] += updated_parents[parent_name][resource]

            thread = Thread(name="persist_{0}".format(parent["name"]), target=utils.persist_data, args=(parent, self.couchdb_handler, self.debug))
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        return new_child_reqs

    def rollback_scale_ups(self, rollback_reqs):
        threads = []
        for r in rollback_reqs:
            # Example: structure=cont1, pair_structure=cont0 -> cont0 scales -12 and cont1 scales +12
            # First, cont0 scales -12, then cont1 attempts to scale +12 and fails, so we create a request to
            # scale cont0 +12 (returning it to its original state)
            pair_structure_name = r["pair_structure"] # e.g., cont0

            # Retrieve structure info
            try:
                pair_structure = self.couchdb_handler.get_structure(pair_structure_name)
            except (requests.exceptions.HTTPError, ValueError):
                utils.log_error("Error, couldn't find pair structure {0} in database".format(pair_structure_name), self.debug)
                continue

            pair_request = dict(r)
            pair_request["structure"] = r["pair_structure"] # e.g., cont0
            pair_request["pair_structure"] = r["structure"] # e.g., cont1
            pair_request["amount"] = r["amount"] # e.g., + 12 shares

            thread, rollback = self.rescale_container(pair_request, pair_structure)

            if rollback:
                utils.log_error("Another rollback has been triggered while scaling up container '{0}' to rollback pair-swapping "
                                "with '{1}'".format(pair_request["structure"], pair_request["pair_structure"]))

            threads.append(thread)

        for thread in threads:
            thread.join()

    def check_unprocessed_rollbacks(self, current_reqs, structure_type):
        # If no rollback requests from previous iterations, return the original requests list
        if not self.rollbacks_tracker[structure_type]:
            return current_reqs

        # Check if some requests correspond with any unprocessed rollback from previous iterations
        filtered_reqs, unprocesed_rollbacks = self.rollback_pair_requests(self.rollbacks_tracker[structure_type], current_reqs)

        # Update unprocessed rollbacks list for this structure type
        self.rollbacks_tracker[structure_type].clear()
        self.rollbacks_tracker[structure_type].extend(unprocesed_rollbacks)

        return filtered_reqs

    ####################################################################################################################
    # RESOURCE REQUEST MANAGEMENT
    ####################################################################################################################
    def process_container_request(self, request, real_resources, database_resources):
        thread = None
        # Create a 'fake' container structure with only the required info
        container = {"host_rescaler_ip": request["host_rescaler_ip"],
                     "host_rescaler_port": request["host_rescaler_port"],
                     "name": request["structure"]}
        # Apply the request and get the new resources to set
        try:
            if request["field"] == "max":
                thread, new_resources = self.update_container_in_couchdb(request, real_resources, database_resources)
            else:
                new_resources = self.apply_request(request, real_resources, database_resources)

            if new_resources:
                # If field is "current" and resource is not energy, we need to send a request to NodeRescaler
                if request["field"] != "max":
                    utils.log_info("Request: {0} for container : {1} for new resources : {2}".format(
                        request["action"], request["structure"], json.dumps(new_resources)), self.debug)

                    # Apply changes through a REST call to NodeRescaler
                    set_container_resources(self.rescaler_http_session, container, new_resources, self.debug)

                # Update container info in cache (useful if there are multiple requests for the same container)
                self.container_info_cache[request["structure"]]["resources"][request["resource"]] = new_resources[request["resource"]]

        except ValueError as e:
            utils.log_error("Error with container {0} in applying the request -> {1}".format(request["structure"], str(e)), self.debug)
            return thread
        except HTTPError as e:
            utils.log_error("Error setting container {0} resources -> {1}".format(request["structure"], str(e)), self.debug)
            return thread
        except Exception as e:
            utils.log_error("Error with container {0} -> {1}".format(request["structure"], str(e)), self.debug)
            return thread

        return thread

    def update_container_in_couchdb(self, request, real_resources, database_resources):
        amount = int(request["amount"])
        resource = request["resource"]
        field = request["field"]
        resource_dict = {resource: {}}

        # Get the current resource limit, if unlimited, then max, min or mean
        _max = database_resources["resources"][resource]["max"]
        _current = self.get_current_resource_value(real_resources, resource)

        # Check that the resource limits are respected (min <= current <= max)
        self.check_invalid_resource_value(database_resources, amount, _current, resource, field)

        new_value = _max + amount
        resource_dict[resource]["{0}_limit".format(resource)] = _current

        # Update container in CouchDB
        thread = Thread(name="update_{0}".format(database_resources["name"]), target=utils.update_resource_in_couchdb,
                        args=(database_resources, resource, field, new_value, self.couchdb_handler, self.debug),
                        kwargs={"max_tries": 5, "backoff_time_ms": 500})
        thread.start()

        return thread, resource_dict

    def apply_request(self, request, real_resources, database_resources):
        amount = int(request["amount"])

        host_info = self.host_info_cache[request["host"]]
        resource = request["resource"]

        # Get the current resource limit, if unlimited, then max, min or mean
        current_resource_limit = self.get_current_resource_value(real_resources, resource)

        # Check that the resource limit is respected, not lower than min or higher than max
        self.check_invalid_resource_value(database_resources, amount, current_resource_limit, resource, request["field"])

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
        supported_distributions = {"Group_P&L", "Group_1P_2L", "Group_PP_LL", "Spread_P&L", "Spread_PP_LL"}
        if dist_name not in supported_distributions:
            raise ValueError("Invalid core distribution: {0}. Supported: {1}.".format(dist_name, supported_distributions))

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

        # First physical cores, then logical cores, alternating between sockets
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
        self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("cpu", {})["core_usage_mapping"] = core_usage_map
        self.host_info_cache[request["host"]]["resources"]["cpu"]["free"] -= amount
        self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("cpu", {})["free"] = self.host_info_cache[request["host"]]["resources"]["cpu"]["free"]

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
        self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("mem", {})["free"] = self.host_info_cache[request["host"]]["resources"]["mem"]["free"]

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
        self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("disks", {}).setdefault(bound_disk, {})["free_read"] = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free_read"]

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
        self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("disks", {}).setdefault(bound_disk, {})["free_write"] = self.host_info_cache[request["host"]]["resources"]["disks"][bound_disk]["free_write"]

        # Return the dictionary to set the resources
        current_write_limit = self.get_current_resource_value(real_resources, request["resource"])
        resource_dict["disk_write"]["disk_write_limit"] = str(int(amount + current_write_limit))

        return resource_dict

    def apply_energy_request(self, request, database_resources, real_resources, amount):
        resource_dict = {request["resource"]: {}}
        current_energy_limit = self.get_current_resource_value(real_resources, request["resource"])
        current_energy_free = self.host_info_cache[request["host"]]["resources"]["energy"]["free"]

        amount = min(amount, current_energy_free)

        # No error thrown, so persist the new mapping to the cache
        self.host_info_cache[request["host"]]["resources"]["energy"]["free"] -= amount
        self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("energy", {})["free"] = self.host_info_cache[request["host"]]["resources"]["energy"]["free"]

        # Return the dictionary to set the resources
        resource_dict["energy"]["energy_limit"] = str(int(current_energy_limit + amount))

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
        thread = None
        try:
            # Needed for the resources reported in the database (the 'max, min' values)
            database_resources = structure

            # Get the resources the container is using from its host NodeScaler (the 'current' value)
            c_name = structure["name"]
            if self.container_info_cache.get(c_name, {}).get("resources", None) is None:
                utils.log_error("Couldn't get container's {0} resources, can't rescale".format(c_name), self.debug)
                return thread, True if request.get("pair_structure", "") else False
            real_resources = self.container_info_cache[c_name]["resources"]

            # Process the request
            thread = self.process_container_request(request, real_resources, database_resources)
        except Exception as e:
            utils.log_error(str(e) + " " + str(traceback.format_exc()), self.debug)
            return thread, True if request.get("pair_structure", "") else False

        return thread, False

    ####################################################################################################################
    # APPLICATION SCALING
    ####################################################################################################################
    def single_container_rescale(self, request, app_containers, resource_usage_cache):
        amount, field, resource_label = request["amount"], request["field"], request["resource"]
        scalable_containers = list()
        resource_shares = abs(amount)

        # Look for containers that can be rescaled
        for container_name, container in app_containers.items():
            max_value = container["resources"][resource_label]["max"]
            min_value = container["resources"][resource_label]["min"]
            current_value = container["resources"][resource_label]["current"]

            # When scaling "current" usage information is also needed
            if field == "current":
                container["resources"][resource_label]["usage"] = resource_usage_cache[container_name][resource_label]

            # Rescale down
            if amount < 0:
                # "max" can't be scaled below "current"
                if field == "max" and max_value + amount >= current_value:
                    scalable_containers.append(container)

                # "current" can't be scaled below "min"
                if field == "current" and current_value + amount >= min_value:
                    scalable_containers.append(container)

            # Rescale up
            else:
                # TODO: Think if we should check the host free resources for a "max" scaling
                if field == "max":
                    scalable_containers.append(container)

                if field == "current":
                    container_host = container["host"]
                    # Check container's host have enough free resources and "current" is not scaled above "max"
                    if self.host_info_cache[container_host]["resources"][resource_label]["free"] >= resource_shares and current_value + amount <= max_value:
                        scalable_containers.append(container)

        # Look for the best fit container for this resource and generate a rescaling request for it
        if scalable_containers:
            success, new_request = False, {}
            best_fit_container = utils.get_best_fit_container(scalable_containers, resource_label, amount, field)
            # Generate the new request
            if best_fit_container:
                new_request = utils.generate_request(best_fit_container, amount, resource_label, field=field)
                success = True

            return success, best_fit_container, new_request
        else:
            return False, {}, {}

    def rescale_application(self, app_request, app):
        thread = None
        resource, field, total_amount = app_request["resource"], app_request["field"], app_request["amount"]

        # Get container names that this app uses
        app_containers = {}
        for cont_name in app["containers"]:
            # Get the container
            container = self.couchdb_handler.get_structure(cont_name)
            app_containers[cont_name] = container
            # Retrieve host info and cache it in case other containers or applications need it
            if container["host"] not in self.host_info_cache:
                self.host_info_cache[container["host"]] = self.couchdb_handler.get_structure(container["host"])

        # When the app is running, generate scaling requests for its containers
        if app_containers and app.get("running", False):
            # Create smaller requests of 'split_amount' size
            split_amount = -APP_SCALING_SPLIT_AMOUNT if total_amount < 0 else APP_SCALING_SPLIT_AMOUNT
            base_request = dict(app_request)
            cont_requests = []
            for slice_amount in utils.split_amount_in_slices(total_amount, split_amount):
                base_request["amount"] = slice_amount
                cont_requests.append(dict(base_request))

            # Get the request usage for all the containers and cache it (not needed when scaling "max")
            resource_usage_cache = {}
            if app_request["field"] == "current":
                for container_name in app_containers:
                    metrics_to_retrieve = BDWATCHDOG_CONTAINER_METRICS[resource]
                    resource_usage_cache[container_name] = self.bdwatchdog_handler.get_structure_timeseries(
                        {"host": container_name}, 10, 20, metrics_to_retrieve, RESCALER_CONTAINER_METRICS)

            # Try to generate requests for the containers belonging to the application
            success, scaled_amount, generated_requests = True, 0, {}
            while success and len(cont_requests) > 0:
                request = cont_requests.pop(0)
                success, container_to_rescale, generated_request = self.single_container_rescale(request, app_containers, resource_usage_cache)
                if success:
                    container_name = container_to_rescale["name"]

                    # Add application info to the container request (useful context for pair-swapping management)
                    generated_request["for_application"] = app["name"]
                    if app_request.get("pair_structure", ""):
                        generated_request["pair_application"] = app_request["pair_structure"]

                    # Save generated request for the best fit container
                    generated_requests.setdefault(container_name, []).append(generated_request)

                    # Update the container's resources for next iteration
                    container_to_rescale["resources"][resource][field] += request["amount"]
                    app_containers[container_name] = container_to_rescale

                    scaled_amount += request["amount"]

            # Collapse all the requests to generate just 1 per container
            final_requests, rescaled_containers = self.flatten_requests_by_structure(generated_requests)
            utils.log_info("App '{0}' rescaled {1} shares for resource {2} by rescaling containers: {3}".format(app["name"], scaled_amount, app_request["resource"], str(rescaled_containers)), self.debug)

            # Check if application was scaled successfully
            if len(cont_requests) > 0 and scaled_amount != total_amount:
                # Couldn't completely rescale the application as some split of a major rescaling operation could not be completed
                utils.log_warning("App '{0}' could not be completely rescaled, only {1} shares out of {2}".format(app["name"], scaled_amount, total_amount), self.debug)

                # Rollback the scaling if this request was generated from a pair-swapping
                if app_request.get("pair_structure", ""):
                    utils.log_warning("This request is part of a pair-swapping between '{0}' and '{1}', both requests will "
                                      "be aborted (rollback)".format(app["name"], app_request["pair_structure"]), self.debug)
                    return thread, [], True

        # When app is not running, we directly update it in CouchDB
        elif not app_containers and not app.get("running", False):
            scaled_amount = total_amount
            final_requests = []

        # Any other state is inconsistent (app have containers while it's not running or app is running while not having containers)
        else:
            utils.log_warning("Inconsistent state for app '{0}' aborting scaling request for {1} {2} shares".format(app["name"], total_amount, resource), self.debug)
            rollback = True if app_request.get("pair_structure", "") else False # Also rollback pair requests if needed
            return thread, [], rollback

        # Update app if "max" is scaled -> field must be updated in StateDatabase ("current" is updated by StructureSnapshoter)
        if field == "max" and scaled_amount != 0:
            new_value = app["resources"][resource][field] + scaled_amount
            thread = Thread(name="update_{0}".format(app["name"]), target=utils.update_resource_in_couchdb,
                            args=(app, resource, field, new_value, self.couchdb_handler, self.debug),
                            kwargs={"max_tries": 5, "backoff_time_ms": 500})
            thread.start()

        return  thread, final_requests, False

    ####################################################################################################################
    # USER SCALING
    ####################################################################################################################
    @staticmethod
    def single_application_rescale(request, user_apps):
        amount, field, resource_label = request["amount"], request["field"], request["resource"]
        scalable_apps = list()

        # Look for applications that can be rescaled
        for app_name, app in user_apps.items():
            # Rescale down: "max" can't be scaled below "current"
            if amount < 0 and app["resources"][resource_label]["max"] + amount >= app["resources"][resource_label].get("current", 0):
                scalable_apps.append(app)
            # Rescale up
            else:
                scalable_apps.append(app)

        if not scalable_apps:
            return False, {}, {}

        # Look for the best fit application for this resource and generate a rescaling request for it
        best_fit_app = utils.get_best_fit_app(scalable_apps, resource_label, amount)

        return True, best_fit_app, utils.generate_request(best_fit_app, amount, resource_label, field=field)

    def rescale_user(self, user_request, user):
        thread = None
        resource, field, total_amount = user_request["resource"], user_request["field"], user_request["amount"]

        if field != "max":
            utils.log_error("Users can only rescale 'max' field, skipping", self.debug)
            return thread, {}, False

        # Get app names associated to this user
        user_apps = {}
        for app_name in user["clusters"]:
            # Get the application
            app = self.couchdb_handler.get_structure(app_name)
            user_apps[app_name] = app

        if user_apps:
            split_amount = -USER_SCALING_SPLIT_AMOUNT if total_amount < 0 else USER_SCALING_SPLIT_AMOUNT
            base_request = dict(user_request)
            app_requests = []
            for slice_amount in utils.split_amount_in_slices(total_amount, split_amount):
                base_request["amount"] = slice_amount
                app_requests.append(dict(base_request))

            success, scaled_amount, generated_requests = True, 0, {}
            while success and len(app_requests) > 0:
                request = app_requests.pop(0)
                success, app_to_rescale, generated_request = self.single_application_rescale(request, user_apps)
                if success:
                    app_name = app_to_rescale["name"]

                    # Add user info to the application request (useful context for pair-swapping management)
                    generated_request["for_user"] = user["name"]
                    if user_request.get("pair_structure", ""):
                        generated_request["pair_user"] = user_request["pair_structure"]

                    # Save generated request for the best fit container
                    generated_requests.setdefault(app_name, []).append(generated_request)

                    # Update the container's resources for next iteration
                    app_to_rescale["resources"][resource][field] += request["amount"]
                    user_apps[app_name] = app_to_rescale

                    scaled_amount += request["amount"]

            # Collapse all the requests to generate just 1 per application
            final_requests, rescaled_apps = self.flatten_requests_by_structure(generated_requests)
            utils.log_info("User '{0}' rescaled {1} shares for resource {2} by rescaling apps: {3}".format(user["name"], scaled_amount, user_request["resource"], str(rescaled_apps)), self.debug)
            if len(app_requests) > 0 and scaled_amount != total_amount:
                # Couldn't completely rescale the application as some split of a major rescaling operation could not be completed
                utils.log_warning("User '{0}' could not be completely rescaled, only {1} shares out of {2}".format(user["name"], scaled_amount, total_amount), self.debug)

                # Rollback the scaling if this request was generated from a pair-swapping
                if user_request.get("pair_structure", ""):
                    utils.log_warning("This request is part of a pair-swapping between '{0}' and '{1}', both requests will "
                                      "be aborted (rollback)".format(user["name"], user_request["pair_structure"]), self.debug)
                    return thread, [], True
        else:
            # TODO: Think if we want to scale users that does not have subscribed applications
            # In that case this branch should return without updating user and set rollback=True if the request comes from a pair-swapping
            scaled_amount = total_amount
            final_requests = []

        # Update user in StateDatabase
        new_value = user["resources"][resource][field] + scaled_amount
        thread = Thread(name="update_{0}".format(user["name"]), target=utils.update_resource_in_couchdb,
                        args=(user, resource, field, new_value, self.couchdb_handler, self.debug),
                        kwargs={"max_tries": 5, "backoff_time_ms": 500})
        thread.start()

        return thread, final_requests, False

    ####################################################################################################################
    # SERVICE METHODS
    ####################################################################################################################
    @staticmethod
    def get_cpu_list(cpu_num_string):
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

    @staticmethod
    def get_current_resource_value(real_resources, resource):
        translation_dict = {"cpu": "cpu_allowance_limit", "mem": "mem_limit", "disk_read": "disk_read_limit",
                            "disk_write": "disk_write_limit", "energy": "energy_limit"}

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
        new_reqs, rollback_reqs, threads = [], [], []
        for request in reqs:
            structure_name = request["structure"]

            # Retrieve structure info
            try:
                if request["structure_type"] == "user":
                    structure = self.couchdb_handler.get_user(structure_name)
                else:
                    structure = self.couchdb_handler.get_structure(structure_name)
            except (requests.exceptions.HTTPError, ValueError):
                utils.log_error("Error, couldn't find structure {0} in database".format(structure_name), self.debug)
                continue

            # Rescale the structure accordingly, whether it is a container or an application
            generated_requests, rollback, thread = [], False, None
            if utils.structure_is_user(structure):
                thread, generated_requests, rollback = self.rescale_user(request, structure)
            elif utils.structure_is_application(structure):
                thread, generated_requests, rollback = self.rescale_application(request, structure)
            elif utils.structure_is_container(structure):
                thread, rollback = self.rescale_container(request, structure)
            else:
                utils.log_error("Unknown type of structure '{0}'".format(structure["subtype"]), self.debug)

            # If some thread has been launched to update structure, save it
            if thread:
                threads.append(thread)

            # Save the request if a rollback has been done
            if rollback:
                rollback_reqs.append(request)

            # Ensure the request has been persisted in database, otherwise there is no need to remove
            if request["timestamp"] <= self.last_request_retrieval and request.get("_id", ""):
                # Remove the request from the database
                self.couchdb_handler.delete_request(request)

            # Add new generated requests
            new_reqs.extend(generated_requests)

        # Wait for threads that update structures
        for thread in threads:
            thread.join()

        return new_reqs, rollback_reqs

    def fill_host_info_cache(self, containers):
        self.host_info_cache = dict()
        for container in containers:
            if container["host"] not in self.host_info_cache:
                self.host_info_cache[container["host"]] = self.couchdb_handler.get_structure(container["host"])
        return

    def persist_new_host_information(self, ):
        def persist_thread(self, host):
            data = self.host_info_cache[host]
            changes = self.host_changes[host]
            utils.partial_update_structure(data, changes, self.couchdb_handler, self.debug)

        threads = list()
        for host in self.host_info_cache:
            if host in self.host_changes:
                t = Thread(target=persist_thread, args=(self, host))
                t.start()
                threads.append(t)
            else:
                utils.log_info("Host {0} has not been modified, skipping persist", self.debug)

        for t in threads:
            t.join()

        # Clean changes as they have been persisted
        self.host_changes.clear()

    def scale_structures(self, new_requests, structure_type):
        utils.log_info("Processing requests", self.debug)

        t0 = time.time()

        # Split the requests between scale down and scale up
        scale_down, scale_up = self.split_requests_by_action(new_requests)

        scale_down_max, scale_down_current = self.split_requests_by_field(scale_down)
        scale_up_max, scale_up_current = self.split_requests_by_field(scale_up)
        new_reqs_acum = []
        rollback_count = 0

        # 1) First, "current" is scaled down to free host resources and ensure "max" scale-downs are valid
        new_reqs, rollback_reqs = self.process_requests(scale_down_current)
        new_reqs_acum.extend(new_reqs)
        if rollback_reqs:
            rollback_count += len(rollback_reqs)
            scale_up_current, unprocessed_rollbacks = self.rollback_pair_requests(rollback_reqs, scale_up_current)
            self.rollbacks_tracker[structure_type].extend(unprocessed_rollbacks)

        # 2) Then, "max" is scaled down
        new_reqs, rollback_reqs = self.process_requests(scale_down_max)
        new_reqs_acum.extend(new_reqs)
        if rollback_reqs:
            rollback_count += len(rollback_reqs)
            scale_up_max, unprocessed_rollbacks = self.rollback_pair_requests(rollback_reqs, scale_up_max)
            self.rollbacks_tracker[structure_type].extend(unprocessed_rollbacks)

        # 3) Now "max" is scaled up first to give more "space" for "current" scale-ups
        new_reqs, rollback_reqs = self.process_requests(scale_up_max)
        new_reqs_acum.extend(new_reqs)
        if rollback_reqs:
            rollback_count += len(rollback_reqs)
            if structure_type == "container":
                self.rollback_scale_ups(rollback_reqs)
            else:
                new_reqs_acum = self.rollback_generated_requests(rollback_reqs, new_reqs_acum, "max")

        # 4) Then, "current" is scaled up
        new_reqs, rollback_reqs = self.process_requests(scale_up_current)
        new_reqs_acum.extend(new_reqs)
        if rollback_reqs:
            rollback_count += len(rollback_reqs)
            if structure_type == "container":
                self.rollback_scale_ups(rollback_reqs)
            else:
                new_reqs_acum = self.rollback_generated_requests(rollback_reqs, new_reqs_acum, "current")

        # Persist the new host information
        self.persist_new_host_information()

        t1 = time.time()
        utils.log_info("It took {0} seconds to process requests".format(str("%.2f" % (t1 - t0))), self.debug)

        if len(new_reqs) > 0:
            utils.log_info("Another {0} new requests have been generated".format(len(new_reqs)), self.debug)

        return new_reqs_acum, rollback_count

    ####################################################################################################################
    # MAIN LOOP
    ####################################################################################################################
    def on_start(self):
        utils.log_info("Purging any previous requests", True)
        self.filter_requests(0)
        utils.log_info("----------------------\n", True)

    def work_thread(self, containers):
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
        container_reqs, app_reqs, user_reqs = self.split_requests_by_structure_type(new_requests)

        # 1) Process user requests, as they can generate application requests
        if user_reqs:
            utils.log_info("Processing user requests", self.debug)
            user_reqs = self.check_unprocessed_rollbacks(user_reqs, "user")
            new_app_reqs, rollback_count = self.scale_structures(user_reqs, "user")
            app_reqs = self.flatten_requests(app_reqs + new_app_reqs)
            if rollback_count > 0:
                utils.log_info("User requests that have been rolled back: {0}".format(rollback_count), self.debug)
        else:
            utils.log_info("No user requests", self.debug)

        # 2) Process application requests, as they can generate container requests
        if app_reqs:
            utils.log_info("Processing application requests", self.debug)
            app_reqs = self.check_unprocessed_rollbacks(app_reqs, "application")
            new_container_reqs, rollback_count = self.scale_structures(app_reqs, "application")
            container_reqs = self.flatten_requests(container_reqs + new_container_reqs)
            if rollback_count > 0:
                utils.log_info("Application requests that have been rolled back: {0}".format(rollback_count), self.debug)
        else:
            utils.log_info("No application requests", self.debug)

        # 3) Process container requests
        if container_reqs:
            utils.log_info("Processing container requests", self.debug)
            container_reqs = self.check_unprocessed_rollbacks(container_reqs, "container")
            _, rollback_count = self.scale_structures(container_reqs, "container")
            if rollback_count > 0:
                utils.log_info("Container requests that have been rolled back: {0}".format(rollback_count), self.debug)
        else:
            utils.log_info("No container requests", self.debug)

        return None

    def work(self):
        thread = None
        # Get the container structures and their resource information as such data is going to be needed
        containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
        try:
            # Reset the container information cache
            self.container_info_cache = utils.get_container_resources_dict(containers, self.rescaler_http_session, self.debug)

            # Fill the host information cache
            utils.log_info("Getting host and container info", self.debug)
            self.fill_host_info_cache(containers)
        except (Exception, RuntimeError) as e:
            utils.log_error("Error getting host document, skipping epoch altogether", self.debug)
            utils.log_error(str(e), self.debug)
            return thread

        thread = Thread(name="scale_structures", target=self.work_thread, args=(containers,))
        thread.start()

        return thread

    def scale(self, ):
        self.run_loop()


def main():
    try:
        scaler = Scaler()
        scaler.scale()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
