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

    @staticmethod
    def split_amount_in_slices(total_amount, slice_amount):
        number_of_slices = int(total_amount // slice_amount)
        last_slice_amount = total_amount % slice_amount
        return [slice_amount] * number_of_slices + ([last_slice_amount] if last_slice_amount > 0 else [])

    @staticmethod
    def generate_scaling_request(structure, resource, amount_to_scale, requests):
        request = utils.generate_request(structure, int(amount_to_scale), resource, priority=2 if amount_to_scale > 0 else -1)
        if resource == "energy":
            request["resource"] = "energy"
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

    def filter_rebalanceable_apps(self, applications):
        rebalanceable_apps = []
        for app in applications:
            # Unless otherwise specified, all applications are rebalanced
            if "rebalance" in app and not app["rebalance"]:
                continue
            # Applications not running do not need internal rebalancing
            if self.REBALANCING_LEVEL == "container" and len(app["containers"]) == 0:
                continue
            # Check applications are consistent before performing a rebalance
            if self.REBALANCING_LEVEL == "application" and app.get("running", False):
                inconsistent_state = False
                # If app has been recently started, containers may not be subscribed
                if len(app["containers"]) == 0:
                    inconsistent_state = True

                if not inconsistent_state:
                    for resource in self.resources_balanced:
                        # The "current" limit can only be zero if the application has been started recently
                        # and StructureSnapshoter has not yet added its "current" value
                        if app.get("resources", {}).get(resource, {}).get("current", 0) <= app.get("resources", {}).get(resource, {}).get("min", 0):
                            inconsistent_state = True
                            break

                if inconsistent_state:
                    utils.log_warning("Inconsistent state for app {0}, it probably started too recently".format(app["name"]), self.debug)
                    continue

            # If app match the criteria, it is added to the list
            rebalanceable_apps.append(app)

        return rebalanceable_apps

    def distribute_parent_limit(self, parent_structure, child_structures, requests):
        for resource in self.resources_balanced:
            d_field = self.select_donated_field(resource)
            if d_field != "max":
                continue

            agg_limit = sum(s["resources"][resource]["max"] for s in child_structures)
            parent_limit = parent_structure.get("resources", {}).get(resource, {}).get("max", None)
            if parent_limit is not None and agg_limit > 0 and agg_limit != parent_limit:
                utils.log_warning("Adjust the aggregate {0} limit of {1}s subscribed to {2} ({3}) to the limit of {2} ({4})."
                                  .format(resource, self.REBALANCING_LEVEL, parent_structure["name"], agg_limit, parent_limit), self.debug)
                direction = 1 if agg_limit < parent_limit else -1
                total_amount = abs(int(parent_limit - agg_limit))
                child_structures = sorted(child_structures, key=lambda s: s["resources"][resource]["max"] - s["resources"][resource]["current"], reverse=(agg_limit > parent_limit))
                slices_to_distribute = self.split_amount_in_slices(int(total_amount), 25)
                num_childs = len(child_structures)
                while slices_to_distribute:
                    empty_structures = 0
                    for structure in child_structures:
                        if not slices_to_distribute:
                            break
                        _max = structure["resources"][resource]["max"]
                        _current = structure["resources"][resource]["current"]
                        _min = structure["resources"][resource]["min"]
                        max_scale_down = _max - max(_current, _min)
                        amount_to_scale = slices_to_distribute.pop() * direction
                        # If scaling down, ensure that structure will not scale "max" below its "current" limit
                        if direction == -1 and abs(amount_to_scale) > max_scale_down:
                            if max_scale_down <= 0:
                                empty_structures += 1
                            slices_to_distribute.append(amount_to_scale + max_scale_down)
                            amount_to_scale = -max_scale_down
                        if amount_to_scale != 0:
                            self.generate_scaling_request(structure, resource, amount_to_scale, requests)
                            # Update the value in dict in order to properly split structures in donors/receivers later
                            structure["resources"][resource]["max"] = _max + amount_to_scale

                    if empty_structures == num_childs:
                        utils.log_error("Parent structure {0} has donated more {1} than it could. Childs cannot be "
                                        "adjusted to limit.".format(parent_structure["name"], resource), self.debug)
                        break

    def manage_rebalancing(self, donor, receiver, resource, amount_to_scale, requests):
        if amount_to_scale == 0:
            utils.log_info("Amount to rebalance from {0} to {1} is 0, skipping".format(donor.get("name"), receiver.get("name")), self.debug)
            return
        # Create the pair of scaling requests
        if receiver:
            self.generate_scaling_request(receiver, resource, amount_to_scale, requests)
        if donor:
            self.generate_scaling_request(donor, resource, -amount_to_scale, requests)

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
            for r in self.get_needed_resources():
                data[r] = {"structure": {r: {}}}
                if self.has_required_fields(structure, resource, self.MANDATORY_FIELDS):
                    for f in self.MANDATORY_FIELDS:
                        data[r]["structure"][r][f] = structure["resources"][r][f]
                else:
                    utils.log_warning("Structure is missing {0} some mandatory fields for resource '{1}': {2}"
                                      .format(structure["name"], r, self.MANDATORY_FIELDS), self.debug)
                    continue

            # Check if structure activates the rule: it has low resource usage (donors) or a bottleneck (receivers)
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

    def send_final_requests(self, structures, requests):
        if not requests:
            return
        for resource in self.resources_balanced:
            d_field = self.select_donated_field(resource)
            # For each structure, aggregate all its requests in a single request
            final_requests = []
            final_requests_by_name = {}
            for structure in requests:
                # Copy the first request as the base request
                flat_request = dict(requests[structure][0])
                flat_request["amount"] = sum(req["amount"] for req in requests[structure])
                final_requests.append(flat_request)
                final_requests_by_name[structure] = flat_request

            # Sort requests so the ones that increase the limit are first
            final_requests = sorted(final_requests, key=lambda r: r["amount"], reverse=True)
            utils.log_info("FINAL REQUESTS ARE:", self.debug)
            if d_field == "current" and resource != "energy":
                for r in final_requests:
                    utils.log_info("    {0}: {1}".format(r["structure"], r["amount"]), self.debug)
                    self.couchdb_handler.add_request(r)
            else:
                # Max limits are directly updated in CouchDB.
                # Energy "current" is also updated in CouchDB as NodeRescaler cannot modify an energy physical limit
                self.update_structures_in_couchdb(structures, resource, d_field, final_requests_by_name)

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
                    # Give stolen percentage of the gap between max and current limit (or usage/min if current is lower)
                    if d_field == "max":
                        stolen_amount = self.stolen_percentage * (_max - max(max(_current,  _usage), _min))

                    # Give stolen percentage of the gap between current limit and current usage (or min if usage is lower)
                    if d_field == "current":
                        stolen_amount = self.stolen_percentage * (_current - max(_min,  _usage))

                    if not stolen_amount:
                        utils.log_warning("It wasn't possible to compute a stolen amount for structure {0} "
                                          "(donated field = {1})".format(structure["name"], d_field), self.debug)
                        continue

                    # Divide the total amount to donate in slices of 25 units
                    key = self.get_donor_slice_key(structure, resource)
                    for slice_amount in self.split_amount_in_slices(int(stolen_amount), 25):
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
                        self.manage_rebalancing(donor, receiver, resource, amount_to_scale, requests)

                        # Update the received amount for this container
                        received_amount[receiver_name] += amount_to_scale

                        utils.log_info("Resource {0} swap between {1} (donor) and {2} (receiver) with amount {3}".format(
                            resource, donor["name"], receiver["name"], amount_to_scale), self.debug)
            else:
                utils.log_info("No structure to receive resource {0} shares".format(resource), self.debug)


