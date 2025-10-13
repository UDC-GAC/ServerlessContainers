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

from threading import Thread
from abc import ABC, abstractmethod
from json_logic import jsonLogic

import src.MyUtils.MyUtils as utils


class BaseRebalancer(ABC):

    STATIC_ATTRS = {"couchdb_handler"}
    MANDATORY_FIELDS = {"max", "current", "usage", "min"}
    BALANCEABLE_RESOURCES = {"cpu", "disk", "energy"}
    REBALANCING_LEVEL = "base"
    PARENT_SPLIT_AMOUNT = 5  # TODO: Geneneralise split amount for Scaler and Rebalancer

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

    def get_needed_resources(self):
        return set(self.resources_balanced).union(set(["cpu"] if "energy" in self.resources_balanced else []))

    # --------- Functions to be overwritten by specific services ---------

    @staticmethod
    @abstractmethod
    def select_donated_field(resource):
        pass

    @staticmethod
    @abstractmethod
    def get_donor_slice_key(structure, resource):
        pass

    @staticmethod
    @abstractmethod
    def get_best_fit_child(scalable_structures, resource, amount):
        pass

    @abstractmethod
    def is_donor(self, data):
        pass

    @abstractmethod
    def is_receiver(self, data):
        pass

    # --------- Auxiliar functions ---------

    @staticmethod
    def has_required_fields(structure, resource, required_fields):
        for field in required_fields:
            if field not in structure.get("resources", {}).get(resource, {}):
                return False
        return True

    @staticmethod
    def add_scaling_request(structure, resource, d_field, amount_to_scale, requests, pair_structure=None):
        request = utils.generate_request(structure, int(amount_to_scale), resource, priority=2 if amount_to_scale > 0 else -1, field=d_field)
        if pair_structure:
            request["pair_structure"] = pair_structure["name"]
        requests.setdefault(structure["name"], []).append(request)

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

    def app_state_is_valid(self, app):
        # Check applications are consistent before performing a rebalance
        if app.get("running", False):
            # If app has been recently started, containers may not yet be subscribed
            if len(app["containers"]) == 0:
                return False

            for resource in self.resources_balanced:
                # The "current" limit can only be zero if the application has been started recently
                # and StructureSnapshoter has not yet added its actual "current" value
                if app.get("resources", {}).get(resource, {}).get("current", 0) <= app.get("resources", {}).get(resource, {}).get("min", 0):
                    return False
        return True

    def simulate_scaler_request_processing(self, parent, childs, parent_request):
        resource = parent_request["resource"]
        total_amount = parent_request["amount"]

        if parent_request["field"] != "max":
            utils.log_warning("Parent request processing can only manage requests to scale 'max' limits, skipping "
                              "request for structure '{0}'".format(parent["name"]), self.debug)
            return

        # Create smaller requests of 'split_amount' size for childs
        split_amount = -self.PARENT_SPLIT_AMOUNT if total_amount < 0 else self.PARENT_SPLIT_AMOUNT
        base_request = dict(parent_request)
        child_requests = []
        for slice_amount in utils.split_amount_in_slices(total_amount, split_amount):
            base_request["amount"] = slice_amount
            child_requests.append(dict(base_request))

        success, scaled_amount = True, 0
        while success and len(child_requests) > 0:
            success = False
            request = child_requests.pop(0)
            # Look for childs that can be rescaled
            if request["amount"] < 0:
                scalable_childs = [s for s in childs if s["resources"][resource]["max"] + request["amount"] > s["resources"][resource]["current"]]
            else:
                scalable_childs = childs

            if not scalable_childs:
                continue

            # Look for the best fit child to rescale
            best_fit_child = self.get_best_fit_child(scalable_childs, resource, request["amount"])

            # Update the child's resources as if the request was already processed
            best_fit_child["resources"][resource]["max"] += request["amount"]
            scaled_amount += request["amount"]
            success = True

    def manage_rebalancing(self, donor, receiver, resource, d_field, amount_to_scale, requests):
        if amount_to_scale == 0:
            utils.log_info("Amount to rebalance from {0} to {1} is 0, skipping".format(donor.get("name"), receiver.get("name")), self.debug)
            return
        # Create the pair of scaling requests
        if receiver:
            self.add_scaling_request(receiver, resource, d_field, amount_to_scale, requests, donor)
        if donor:
            self.add_scaling_request(donor, resource, d_field, -amount_to_scale, requests, receiver)

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
            valid_resources = True
            for r in self.get_needed_resources():
                data[r] = {"structure": {r: {}}}
                if self.has_required_fields(structure, resource, self.MANDATORY_FIELDS):
                    for f in self.MANDATORY_FIELDS:
                        data[r]["structure"][r][f] = structure["resources"][r][f]
                else:
                    valid_resources = False
                    utils.log_warning("Structure {0} is missing some mandatory fields for resource '{1}': {2}"
                                      .format(structure["name"], r, self.MANDATORY_FIELDS), self.debug)
                    continue

            # Check if structure activates the rule: it has low resource usage (donors) or a bottleneck (receivers)
            if valid_resources:
                for role in valid_roles:
                    if jsonLogic(rule[role]["rule"], data):
                        filtered_structures[role].append(structure)

        return filtered_structures["donors"], filtered_structures["receivers"]

    def split_structures_using_thresholds(self, structures, resource):
        donors, receivers = [], []
        for structure in structures:
            data = {}
            if self.has_required_fields(structure, resource, self.MANDATORY_FIELDS):
                for f in self.MANDATORY_FIELDS:
                    data[f] = structure["resources"][resource][f]
            else:
                utils.log_warning("Structure is missing {0} some mandatory fields for resource '{1}': {2}"
                                  .format(structure["name"], resource, self.MANDATORY_FIELDS), self.debug)
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

    def update_structures_in_couchdb(self, structures, resource, d_field, requests):
        threads = []
        for structure in structures:
            amount_to_scale = requests.get(structure["name"], {}).get("amount", 0)
            if amount_to_scale != 0:
                utils.log_info("    {0}: {1}".format(structure["name"], amount_to_scale), self.debug)
                new_value = structure["resources"][resource][d_field] + amount_to_scale
                thread = Thread(name="update_{0}".format(structure["name"]), target=utils.update_resource_in_couchdb,
                                args=(structure, resource, d_field, new_value, self.couchdb_handler, self.debug),
                                kwargs={"max_tries": 5, "backoff_time_ms": 500})
                thread.start()
                threads.append(thread)

        for thread in threads:
            thread.join()

    def send_final_requests(self, requests):
        if not requests:
            return {}

        # For each structure, aggregate all its requests in a single request
        final_requests = []
        final_requests_by_name = {}
        for structure in requests:
            # Copy the first request as the base request
            flat_request = dict(requests[structure][0])
            flat_request["amount"] = sum(req["amount"] for req in requests[structure])
            final_requests.append(flat_request)
            final_requests_by_name[structure] = flat_request

        # Sort requests so the ones that decrease the limit (free host resources) are first
        final_requests = sorted(final_requests, key=lambda r: r["amount"])
        utils.log_info("FINAL REQUESTS ARE:", self.debug)
        for r in final_requests:
            utils.log_info("    {0}: {1}".format(r["structure"], r["amount"]), self.debug)
            self.couchdb_handler.add_request(r)
            # if d_field == "current" and resource != "energy":
            #     for r in final_requests:
            #         utils.log_info("    {0}: {1}".format(r["structure"], r["amount"]), self.debug)
            #         self.couchdb_handler.add_request(r)
            # else:
            #     # Max limits are directly updated in CouchDB.
            #     # Energy "current" is also updated in CouchDB as NodeRescaler cannot modify an energy physical limit
            #     self.update_structures_in_couchdb(structures, resource, d_field, final_requests_by_name)
        return final_requests_by_name

    # --------- Rebalancing algorithms ---------

    def pair_swapping(self, structures, requests):
        for resource in self.resources_balanced:
            if resource not in self.BALANCEABLE_RESOURCES:
                utils.log_warning("'{0}' not yet supported in pair-swapping balancing, only '{1}' available at the "
                                  "moment".format(resource, list(self.BALANCEABLE_RESOURCES)), self.debug)
                continue
            utils.log_info("Rebalancing resource '{0}' at {1} level by pair-swapping".format(resource, self.REBALANCING_LEVEL), self.debug)

            # Field to be donated: "max" or "current"
            d_field = self.select_donated_field(resource)
            donors, receivers = self.split_structures_by_role(structures, resource)
            if receivers:
                self.print_donors_and_receivers(donors, receivers)

                # Structures that have a "current" closer to its "max" receive first
                if d_field == "max":
                    receivers = sorted(receivers, key=lambda s: (1 - s["resources"][resource]["current"] / s["resources"][resource]["max"]))
                # Order the structures from lower to upper resource limit
                else:
                    receivers = sorted(receivers, key=lambda s: s["resources"][resource][d_field])

                donor_slices = dict()
                for structure in donors:
                    # Ensure this request will be successfully processed, otherwise we are 'giving' away extra resources
                    _max = structure["resources"][resource]["max"]
                    _current = structure["resources"][resource]["current"]
                    _min = structure["resources"][resource]["min"]
                    _usage = structure["resources"][resource]["usage"]

                    stolen_amount = None
                    # Give stolen percentage of the gap between max and current limit (or usage if current is lower)
                    if d_field == "max":
                        stolen_amount = self.stolen_percentage * (_max - max(_current,  _usage))

                    # Give stolen percentage of the gap between current limit and current usage (or min if usage is lower)
                    if d_field == "current":
                        stolen_amount = self.stolen_percentage * (_current - max(_min,  _usage))

                    if not stolen_amount:
                        utils.log_warning("It wasn't possible to compute a stolen amount for structure {0} "
                                          "(donated field = {1})".format(structure["name"], d_field), self.debug)
                        continue

                    # Divide the total amount to donate in slices of 25 units
                    key = self.get_donor_slice_key(structure, resource)
                    for slice_amount in utils.split_amount_in_slices(int(stolen_amount), 25):
                        donor_slices.setdefault(key, []).append((structure, slice_amount))

                # Remove donor slices that cannot be given to any receiver
                for key in list(donor_slices.keys()):
                    if all(key != self.get_donor_slice_key(r, resource) for r in receivers):
                        del donor_slices[key]
                    else:
                        donor_slices[key] = sorted(donor_slices[key], key=lambda c: c[1])

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
            else:
                utils.log_info("No structure to receive resource {0} shares".format(resource), self.debug)


