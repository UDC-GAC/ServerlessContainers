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
from abc import ABC, abstractmethod
from json_logic import jsonLogic

import src.MyUtils.MyUtils as utils


class BaseRebalancer(ABC):

    STATIC_ATTRS = {"couchdb_handler"}
    BALANCEABLE_RESOURCES = {"cpu", "disk", "energy"}
    REBALANCING_LEVEL = "base"

    def __init__(self, couchdb_handler):
        self.couchdb_handler = couchdb_handler
        self.window_timelapse, self.window_delay, self.diff_percentage, self.stolen_percentage = None, None, None, None
        self.resources_balanced, self.structures_balanced, self.containers_scope = None, None, None
        self.balancing_policy, self.balancing_method, self.only_running, self.debug = None, None, None, None

    def set_config(self, config):
        for attr in self.__dict__.keys():
            if attr in self.STATIC_ATTRS:
                continue
            val = config.get_value(attr.upper())
            if val is None:
                raise ValueError("Missing configuration parameter '{0}'".format(attr.upper()))
            setattr(self, attr, val)

    # --------- Functions to be overwritten by specific services ---------

    @staticmethod
    @abstractmethod
    def select_donated_field(resource):
        pass

    @abstractmethod
    def is_donor(self, data):
        pass

    @abstractmethod
    def is_receiver(self, data):
        pass

    @staticmethod
    @abstractmethod
    def get_donor_slice_key(structure, resource):
        pass

    # --------- Auxiliar functions ---------

    @staticmethod
    def has_required_fields(structure, resource, required_fields):
        for field in required_fields:
            if field not in structure.get("resources", {}).get(resource, {}):
                return False
        return True

    def scale_and_adjust_alloc_ratio(self, structure, resource, d_field, amount_to_scale, max_tries=3):
        old_value = structure["resources"][resource][d_field]
        new_value = old_value + amount_to_scale
        old_ratio, new_ratio = None, None
        tries, put_done = 0, False
        while not put_done:
            tries += 1
            structure["resources"][resource][d_field] = new_value

            # If "max" is updated register the amount rebalanced so the LimitsDispatcher can take it into account
            if d_field == "max":
                structure["resources"][resource]["rebalanced"] = structure["resources"][resource].get("rebalanced", 0) + amount_to_scale
                # If allocation ratio is defined, adjust it according to the new max
                if "alloc_ratio" in structure["resources"][resource]:
                    old_ratio = structure["resources"][resource]["alloc_ratio"]
                    new_ratio = float(old_ratio * new_value / structure["resources"][resource][d_field])
                    structure["resources"][resource]["alloc_ratio"] = new_ratio

            utils.persist_data(structure, self.couchdb_handler, self.debug)

            time.sleep(0.5)

            structure = self.couchdb_handler.get_structure(structure["name"])
            put_done = structure["resources"][resource][d_field] == new_value

            if tries >= max_tries:
                utils.log_error("Could not update {0} value for structure {1} for {2} tries, aborting".format(resource, structure["name"], max_tries), self.debug)
                return

        utils.log_info("Resource {0} value for structure {1} has been successfully updated from {2} to {3}".format(resource, structure["name"], old_value, new_value), self.debug)
        if old_ratio is not None and new_ratio is not None:
            utils.log_warning("Also updated allocation ratio from {0} to {1}".format(old_ratio, new_ratio), self.debug)

    @staticmethod
    def split_amount_in_slices(total_amount, slice_amount):
        number_of_slices = int(total_amount // slice_amount)
        last_slice_amount = total_amount % slice_amount
        return [slice_amount] * number_of_slices + ([last_slice_amount] if last_slice_amount > 0 else [])

    def print_donors_and_receivers(self, donors, receivers):
        utils.log_info("Nodes that will give: {0}".format(str([c["name"] for c in donors])), self.debug)
        utils.log_info("Nodes that will receive:  {0}".format(str([c["name"] for c in receivers])), self.debug)

    def print_scaling_info(self, container, amount_to_scale, resource, d_field):
        if amount_to_scale > 0:  # Receiver
            utils.log_info("Node {0} will receive: {1} for {2} '{3}' limit".format(container["name"], amount_to_scale, resource, d_field), self.debug)
        if amount_to_scale < 0:  # Donor
            utils.log_info("Node {0} will give: {1} for {2} '{3}' limit".format(container["name"], abs(amount_to_scale), resource, d_field), self.debug)

    def print_donor_slices(self, donor_slices, msg="Donor slices are:"):
        utils.log_info(msg, self.debug)
        for key in donor_slices:
            for donor, slice_amount in donor_slices[key]:
                utils.log_info("({0})\t{1}\t{2}".format(key, donor["name"], slice_amount), self.debug)

    def filter_rebalanceable_apps(self, applications):
        rebalanceable_apps = []

        for app in applications:
            # Unless otherwise specified, all applications are rebalanced
            if "rebalance" in app and not app["rebalance"]:
                continue
            # Single-container applications do not need internal rebalancing
            if self.REBALANCING_LEVEL == "container" and len(app["containers"]) <= 1:
                continue
            # If app match the criteria, it is added to the list
            rebalanceable_apps.append(app)

        return rebalanceable_apps

    def generate_scaling_request(self, structure, resource, amount_to_scale, requests):
        self.print_scaling_info(structure, amount_to_scale, resource, "current")
        request = utils.generate_request(structure, int(amount_to_scale), resource, priority=2 if amount_to_scale > 0 else -1)
        requests.setdefault(structure["name"], []).append(request)

    def update_resource_in_couchdb(self, structure, resource, d_field, amount_to_scale):
        self.print_scaling_info(structure, amount_to_scale, resource, d_field)
        self.scale_and_adjust_alloc_ratio(structure, resource, d_field, amount_to_scale)

    def manage_rebalancing(self, donor, receiver, resource, d_field, amount_to_scale, requests):
        if amount_to_scale == 0:
            utils.log_info("Amount to rebalance from {0} to {1} is 0, skipping".format(donor["name"], receiver["name"]), self.debug)
            return

        # Create the pair of scaling requests
        if d_field == "current" and resource != "energy":
            self.generate_scaling_request(receiver, resource, amount_to_scale, requests)
            self.generate_scaling_request(donor, resource, -amount_to_scale, requests)
        # Max limits are directly updated in CouchDB. Energy "current" is also updated in CouchDB as NodeRescaler
        # cannot modify an energy physical limit
        else:
            self.update_resource_in_couchdb(receiver, resource, d_field, amount_to_scale)
            self.update_resource_in_couchdb(donor, resource, d_field, -amount_to_scale)

    def map_role_to_rule(self, resource, role):
        if role == "donors":
            return "{0}_{1}_usage_low".format(self.REBALANCING_LEVEL, resource)
        if role == "receivers":
            return "{0}_{1}_usage_high".format(self.REBALANCING_LEVEL, resource)
        raise ValueError("Invalid role '{0}' for resource '{1}'. It must be donors or receivers.".format(role, resource))

    def split_structures_using_rules(self, structures, resource):
        filtered_structures = {"donors": list(), "receivers": list()}
        rule = {"donors": dict(), "receivers": dict()}
        valid_roles = list()
        for role in ["donors", "receivers"]:
            try:
                rule_name = self.map_role_to_rule(resource, role)
                rule[role] = self.couchdb_handler.get_rule(rule_name)
                valid_roles.append(role)
            except ValueError as e:
                utils.log_warning("No rule found for resource {0} and role {1}: {2}".format(resource, role, str(e)), self.debug)

        for structure in structures:
            data = {}
            for r in structure["resources"]:
                try:
                    data[r] = {"structure": {r: {
                        "usage": structure["resources"][r]["usage"],
                        "min": structure["resources"][r]["min"],
                        "max": structure["resources"][r]["max"],
                        "current": structure["resources"][r]["current"]}}}
                except KeyError:
                    continue
            # Check if container activate the rule: it has low resource usage (donors) or a bottleneck (receivers)
            for role in valid_roles:
                if jsonLogic(rule[role]["rule"], data):
                    filtered_structures[role].append(structure)

        return filtered_structures["donors"], filtered_structures["receivers"]

    def split_structures_using_thresholds(self, structures, resource):
        donors, receivers = [], []
        for structure in structures:
            try:
                data = {
                    "usage": structure["resources"][resource]["usage"],
                    "min": structure["resources"][resource]["min"],
                    "max": structure["resources"][resource]["max"],
                    "current": structure["resources"][resource]["current"]}
            except KeyError:
                continue

            if self.is_donor(data):
                donors.append(structure)
            elif self.is_receiver(data):
                receivers.append(structure)

        return donors, receivers

    def split_structures_by_role(self, structures, resource):
        donors, receivers = list(), list()

        if self.balancing_policy == "rules":
            # Split structures using rules
            donors, receivers = self.split_structures_using_rules(structures, resource)

        if self.balancing_policy == "thresholds":
            # Split structures using configuration parameters
            donors, receivers = self.split_structures_using_thresholds(structures, resource)

        return donors, receivers

    def send_final_requests(self, requests):
        # For each structure, aggregate all its requests in a single request
        final_requests = list()
        for structure in requests:
            # Copy the first request as the base request
            flat_request = dict(requests[structure][0])
            flat_request["amount"] = sum(req["amount"] for req in requests[structure])
            final_requests.append(flat_request)

        utils.log_info("REQUESTS ARE:", self.debug)
        for c in requests.values():
            for r in c:
                utils.debug_info(r, self.debug)

        # TODO: Adjust requests amounts according to the maximums (trim), otherwise the scaling down will be performed
        #  but not the scaling up, and shares will be lost
        utils.log_info("FINAL REQUESTS ARE:", self.debug)
        for r in final_requests:
            utils.debug_info(r, self.debug)
            self.couchdb_handler.add_request(r)

    # --------- Rebalancing algorithms ---------

    def pair_swapping(self, structures):
        for resource in self.resources_balanced:
            if resource not in self.BALANCEABLE_RESOURCES:
                utils.log_warning("'{0}' not yet supported in pair-swapping balancing, only '{1}' available at the "
                                  "moment".format(resource, list(self.BALANCEABLE_RESOURCES)), self.debug)
                continue
            utils.log_info("Rebalancing resource '{0}' at {1} level by pair-swapping".format(resource, self.REBALANCING_LEVEL), self.debug)

            donors, receivers = self.split_structures_by_role(structures, resource)

            if not receivers:
                utils.log_info("No structure to receive resource {0} shares".format(resource), self.debug)
                return

            self.print_donors_and_receivers(donors, receivers)

            # Select the field to be rebalanced for this resource
            d_field = self.select_donated_field(resource)

            # Order the structures from lower to upper resource limit
            receivers = sorted(receivers, key=lambda s: s["resources"][resource][d_field])

            donor_slices = dict()
            for container in donors:
                # Ensure this request will be successfully processed, otherwise we are 'giving' away extra resources
                _max = container["resources"][resource]["max"]
                _current = container["resources"][resource]["current"]
                _min = container["resources"][resource]["min"]
                _usage = container["resources"][resource]["usage"]

                stolen_amount = None
                # Give stolen percentage of the gap between max and current limit (or usage if current is lower)
                if d_field == "max":
                    stolen_amount = self.stolen_percentage * (_max - max(_current,  _usage))

                # Give stolen percentage of the gap between current limit and current usage (or min if usage is lower)
                if d_field == "current":
                    stolen_amount = self.stolen_percentage * (_current - max(_min,  _usage))

                if not stolen_amount:
                    utils.log_warning("It wasn't possible to compute a stolen amount for structure {0} "
                                      "(donated field = {1})".format(container["name"], d_field), self.debug)
                    continue

                # Divide the total amount to donate in slices of 25 units
                key = self.get_donor_slice_key(container, resource)
                for slice_amount in self.split_amount_in_slices(int(stolen_amount), 25):
                    donor_slices.setdefault(key, []).append((container, slice_amount))

            # Remove donor slices that cannot be given to any receiver
            for key in list(donor_slices.keys()):
                if all(key != self.get_donor_slice_key(r, resource) for r in receivers):
                    del donor_slices[key]
                else:
                    donor_slices[key] = sorted(donor_slices[key], key=lambda c: c[1])

            requests = {}
            received_amount = {}
            while donor_slices:
                # Print current donor slices
                self.print_donor_slices(donor_slices)

                if not receivers:
                    break

                # The loop iterates over a copy so that the list of receivers can be modified inside the loop
                for receiver in list(receivers):
                    receiver_name = receiver["name"]
                    key = self.get_donor_slice_key(receiver, resource)

                    if key not in donor_slices:
                        utils.log_info("No suitable donors have been found for receiver {0}, searched for by key '{1}'".format(receiver["name"], key), self.debug)
                        receivers.remove(receiver)
                        continue

                    # When donating "current", structure can't receive more than its max also taking into account its previous donations
                    max_receiver_amount = (receiver["resources"][resource]["max"] -
                                           receiver["resources"][resource]["current"] -
                                           received_amount.setdefault(receiver_name, 0))

                    if d_field == "current" and max_receiver_amount <= 0:
                        receivers.remove(receiver)
                        continue

                    # Get and remove one slice from the list
                    donor, amount_to_scale = donor_slices[key].pop()

                    # Trim the amount to scale if needed and return the remaining amount to the donor slices
                    if d_field == "current" and amount_to_scale > max_receiver_amount:
                        donor_slices[key].append((donor, amount_to_scale - max_receiver_amount))
                        amount_to_scale = max_receiver_amount

                    # If all the resources from the donors corresponding to this key have been donated, key is removed
                    if not donor_slices[key]:
                        del donor_slices[key]

                    # Manage necessary scalings to rebalance resource between donor and receiver
                    self.manage_rebalancing(donor, receiver, resource, d_field, amount_to_scale, requests)

                    # Update the received amount for this container
                    received_amount[receiver_name] += amount_to_scale

                    utils.log_info("Resource {0} swap between {1} (donor) and {2} (receiver) with amount {3}".format(
                        resource, donor["name"], receiver["name"], amount_to_scale), self.debug)

            # If some requests have been generated, send them to CouchDB
            if requests:
                self.send_final_requests(requests)
