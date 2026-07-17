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

from abc import ABC, abstractmethod
from json_logic import jsonLogic

import src.MyUtils.MyUtils as utils
from src.ReBalancer.Trackers import RebalancerTracker, ResourcesTracker


class BaseRebalancer(ABC):

    STATIC_ATTRS = {"couchdb_handler", "rebalance_tracker", "resources_tracker"}
    MANDATORY_FIELDS = {"max", "current", "usage", "min"}
    BALANCEABLE_RESOURCES = {"cpu", "energy"}
    REBALANCING_LEVEL = "base"

    def __init__(self, couchdb_handler):
        self.couchdb_handler = couchdb_handler
        self.rebalance_tracker = RebalancerTracker()
        self.resources_tracker = None
        self.window_timelapse, self.window_delay, self.diff_percentage, self.stolen_percentage = None, None, None, None
        self.resources_balanced, self.structures_balanced, self.containers_scope, self.compensate = None, None, None, None
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
        resources_balanced_set = set(self.resources_balanced)
        # Change 'disk' resource to 'disk_read' and 'disk_write'
        if "disk" in resources_balanced_set:
            resources_balanced_set.remove("disk")
            resources_balanced_set = resources_balanced_set.union(set(["disk_read", "disk_write"]))

        return resources_balanced_set.union(set(["cpu"] if "energy" in self.resources_balanced else []))

    # --------- Functions to be overwritten by specific services ---------

    @staticmethod
    @abstractmethod
    def select_donated_field(resource):
        pass

    @staticmethod
    @abstractmethod
    def get_donor_slice_key(structure, resource):
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
            requests.setdefault((structure["name"], pair_structure["name"]), []).append(request)
        else:
            requests.setdefault((structure["name"], None), []).append(request)

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
        if app.get("state", "") == "running":
            # If app has been recently started, containers may not yet be subscribed
            if len(app["containers"]) == 0:
                return False

            for resource in self.resources_balanced:
                # The "current" limit can only be zero if the application has been started recently
                # and StructureSnapshoter has not yet added its actual "current" value
                if app.get("resources", {}).get(resource, {}).get("current", 0) < app.get("resources", {}).get(resource, {}).get("min", 0):
                    return False
        return True

    @staticmethod
    def simulate_scaler_request_processing(parent, childs, parent_request, propagate):
        app_requests, scaled_amount = propagate(parent, childs, parent_request)
        for r in app_requests:
            structure = childs.get(r["structure"])
            field, amount, resource = r.get("field"), r.get("amount"), r.get("_request", {}).get("resource")
            structure["resources"][resource][field] += amount

    def manage_swap(self, donor, receiver, resource, d_field, amount_to_scale, requests):
        if amount_to_scale == 0:
            utils.log_info("Amount to rebalance from {0} to {1} is 0, skipping".format(donor.get("name"), receiver.get("name")), self.debug)
            return
        # Create the pair of scaling requests
        if donor and receiver:
            # Donor acquires a credit or pays off old debts
            self.rebalance_tracker.record_donation(donor["_id"], resource, amount_to_scale)
            self.resources_tracker.update_structure_resource(donor["_id"], resource, d_field, -amount_to_scale)
            # Receiver takes on debt or uses old credit to compensate it
            self.rebalance_tracker.record_reception(receiver["_id"], resource, amount_to_scale)
            self.resources_tracker.update_structure_resource(receiver["_id"], resource, d_field, amount_to_scale)
            # Create and add request to list
            self.add_scaling_request(receiver, resource, d_field, amount_to_scale, requests, donor)

    def map_role_to_rule(self, resource, role):
        if role == "donor":
            return "{0}_{1}_usage_low".format(self.REBALANCING_LEVEL, resource)
        if role == "receiver":
            return "{0}_{1}_usage_high".format(self.REBALANCING_LEVEL, resource)
        raise ValueError("Invalid role '{0}' for resource '{1}'. It must be donors or receivers.".format(role, resource))

    def split_structures_using_rules(self, structures, resource, roles):
        filtered_structures = {role: [] for role in roles}
        rule = {role: {} for role in roles}
        valid_roles = set()
        for role in roles:
            try:
                rule_name = self.map_role_to_rule(resource, role)
                rule[role] = self.couchdb_handler.get_rule(rule_name)
                valid_roles.add(role)
            except ValueError as e:
                utils.log_warning("No rule found for resource {0} and role {1}: {2}".format(resource, role, str(e)), self.debug)

        for structure in structures:
            # Get updated data from resources tracker
            data = self.resources_tracker.get_structure_data(structure["_id"])
            if not data:
                utils.log_warning("Structure {0} is missing some data for resource '{1}': {2}"
                                  .format(structure["name"], resource, self.MANDATORY_FIELDS), self.debug)
                continue

            # Check if structure activates the rule: it has low resource usage (donors) or a bottleneck (receivers)
            for role in valid_roles:
                if jsonLogic(rule[role]["rule"], data):
                    filtered_structures[role].append(structure)

        return filtered_structures

    def split_structures_using_thresholds(self, structures, resource, roles):
        filtered_structures = {role: [] for role in roles}
        for structure in structures:
            # Get updated data from resources tracker
            data = self.resources_tracker.get_structure_data(structure["_id"])
            if not data:
                utils.log_warning("Structure {0} is missing some data for resource '{1}': {2}"
                                  .format(structure["name"], resource, self.MANDATORY_FIELDS), self.debug)
                continue

            for role in roles:
                checker = getattr(self, "is_{0}".format(role), None)
                if checker is None or not callable(checker):
                    continue
                if checker(data[resource]["structure"][resource]):
                    filtered_structures[role].append(structure)

        return filtered_structures

    def split_structures_by_role(self, structures, resource, roles):
        split_structures = {}
        if self.balancing_policy == "rules":
            # Split structures using rules
            split_structures = self.split_structures_using_rules(structures, resource, roles)

        if self.balancing_policy == "thresholds":
            # Split structures using configuration parameters
            split_structures = self.split_structures_using_thresholds(structures, resource, roles)

        return split_structures.get("donor", []), split_structures.get("receiver", [])

    def get_donor_slices(self, donors, receivers, resource, d_field):
        donor_slices = {}
        for structure in donors:
            # Ensure this request will be successfully processed, otherwise we are 'giving' away extra resources
            data = self.resources_tracker.get_structure_resource(structure["_id"], resource)
            stolen_amount = None
            # Give stolen percentage of the gap between max and current usage
            if d_field == "max":
                lower_limit = data["min"] if data["usage"] > 0 else 0 # Running structures doesn't donate below min (QoS constraint)
                if structure["subtype"] == "application":
                    lower_limit = data["min"] if structure.get("state", "") == "running" else 0  # Additional protection for apps
                stolen_amount = max(self.stolen_percentage * (data["max"] - max(lower_limit, data["usage"])), 0)
                # Avoid leaving residual budget, especially when structure is not running
                if stolen_amount < 1 <= (data["max"] - lower_limit):
                    stolen_amount = 1

            # Give stolen percentage of the gap between current limit and current usage (or min if usage is lower)
            if d_field == "current":
                stolen_amount = self.stolen_percentage * (data["current"] - max(data["min"],  data["usage"]))

            if not stolen_amount:
                utils.log_warning("It wasn't possible to compute a stolen amount for structure {0} "
                                  "(donated field = {1})".format(structure["name"], d_field), self.debug)
                continue

            if stolen_amount == 0:
                continue

            # Divide the total amount in as many slices as available receivers
            key = self.get_donor_slice_key(structure, resource)
            slice_amount = 1 if resource == "energy" else 5
            for split in utils.split_amount_in_slices(int(stolen_amount), slice_amount):
                donor_slices.setdefault(key, []).append((structure, split))

        # Sort donor slices and remove slices that cannot be given to any receiver
        for key in list(donor_slices.keys()):
            if all(key != self.get_donor_slice_key(r, resource) for r in receivers):
                del donor_slices[key]
            else:
                donor_slices[key] = sorted(donor_slices[key], key=lambda c: c[1])

        return donor_slices

    def send_final_requests(self, requests):
        if not requests:
            return {}

        # For each structure, aggregate all its requests in a single request
        final_requests = []
        final_requests_by_name = {}
        for (structure, pair_structure), req_list in requests.items():
            # Copy the first request as the base request
            flat_request = dict(req_list[0])
            flat_request["amount"] = sum(r["amount"] for r in req_list)
            final_requests.append(flat_request)
            final_requests_by_name[structure] = flat_request
            if pair_structure is not None:
                pair_request = dict(req_list[0])
                pair_request["structure"] = pair_structure
                pair_request["amount"] = -flat_request["amount"]
                final_requests_by_name[pair_structure] = pair_request

        # Sort requests so the ones that decrease the limit (free host resources) are first
        final_requests = sorted(final_requests, key=lambda r: r["amount"])
        utils.log_info("FINAL REQUESTS ARE:", self.debug)
        for r in final_requests:
            if r["amount"] < 0:
                utils.log_info("    {0} --|{1}|--> {2}".format(r["structure"], abs(r["amount"]), r.get("pair_structure", "System")), self.debug)
            else:
                utils.log_info("    {0} --|{1}|--> {2}".format(r.get("pair_structure", "System"), abs(r["amount"]), r["structure"]), self.debug)
            self.couchdb_handler.add_request(r)

        return final_requests_by_name

    # --------- Rebalancing algorithms ---------
    def perform_compensation(self, valid_structures, receivers, resource, d_field, requests):
        # Check which structures still need to receive after swaps and have credit to use
        _, receivers = self.split_structures_by_role(receivers, resource, {"receiver"})
        receivers = [r for r in receivers if self.rebalance_tracker.get_net_balance(r["_id"], resource) > 0]
        sorted_receivers = sorted(receivers, key=lambda r: self.rebalance_tracker.get_net_balance(r["_id"], resource), reverse=True)

        # Check which structures have a debt and are forced to donate
        forced_donors = []
        for structure in valid_structures:
            # If structure has pending debts it must donate
            if self.rebalance_tracker.get_net_balance(structure["_id"], resource) < 0:
                lower_limit = 0 if structure["resources"][resource]["usage"] == 0 and d_field == "max" else structure["resources"][resource]["min"]
                # Check if the structure can donate respecting QoS contraints
                if structure["resources"][resource][d_field] > lower_limit:
                    forced_donors.append(structure)

        # Those that are still receivers and have a credit can receive from those that have a debt
        for receiver in sorted_receivers:
            receiver_balance = self.rebalance_tracker.get_net_balance(receiver["_id"], resource)
            # Add the while to iterate until receiver is fully balanced, current approach only associates best
            # receiver with best donor and pass. I believe this is better because the receiver will take some time
            # to reuse the amount of resources taken back from debt
            # while receiver_balance > 0:
            if not forced_donors:
                break

            # Take the donor with the highest debt
            forced_donors = sorted(forced_donors, key=lambda d: self.rebalance_tracker.get_net_balance(d["_id"], resource))
            best_donor = forced_donors[0]

            # If donor with the highest debt does not have any debt, we have finished
            donor_balance = self.rebalance_tracker.get_net_balance(best_donor["_id"], resource)
            needed_amount = min(-donor_balance, receiver_balance)
            if needed_amount <= 0:
                utils.log_info("Either donor {0} has a positive balance ({1}) or receiver {2} has a negative one ({3})"
                               .format(best_donor["name"], donor_balance, receiver["name"], receiver_balance), self.debug)
                break

            lower_limit = 0 if best_donor["resources"][resource]["usage"] == 0 and d_field == "max" else best_donor["resources"][resource]["min"]
            max_donation = self.resources_tracker.get_structure_resource(best_donor["_id"], resource).get(d_field) - lower_limit
            stolen_amount = min(needed_amount, max_donation)

            # If the donor give all the amount it can, it is removed from the donors list
            if stolen_amount == max_donation:
                forced_donors.remove(best_donor)

            # Manage necessary scalings to rebalance resource between donor and receiver
            self.manage_swap(best_donor, receiver, resource, d_field, stolen_amount, requests)

            utils.log_info("Donor {0} paying off {1} debt to receiver {2} with amount {3}".format(
                best_donor["name"], resource, receiver["name"], stolen_amount), self.debug)

            # Add with the "while" clause to do full receiver balancing
            #receiver_balance = self.rebalance_tracker.get_net_balance(receiver["_id"], resource)

        # It should be a zero-sum game, every debt has a credit counterpart
        # There is an exception, if some structure finish execution with pending debts or credits, this is lost
        # In that case the amount is lost and will be balanced again when the counterpart also finish execution

    def pair_swapping(self, structures, requests):
        self.resources_tracker = ResourcesTracker(self.MANDATORY_FIELDS)
        valid_structures = self.resources_tracker.record_structures(structures, self.get_needed_resources())
        for resource in self.resources_balanced:
            if resource not in self.BALANCEABLE_RESOURCES:
                utils.log_warning("'{0}' not yet supported in pair-swapping balancing, only '{1}' available at the "
                                  "moment".format(resource, list(self.BALANCEABLE_RESOURCES)), self.debug)
                continue
            utils.log_info("Rebalancing resource '{0}' at {1} level by pair-swapping".format(resource, self.REBALANCING_LEVEL), self.debug)

            # Field to be donated: "max" or "current"
            d_field = self.select_donated_field(resource)
            donors, receivers = self.split_structures_by_role(valid_structures, resource, {"donor", "receiver"})
            if not receivers:
                utils.log_info("No structure to receive resource {0} shares".format(resource), self.debug)
                continue

            self.print_donors_and_receivers(donors, receivers)

            # Compute amount that can be stolen from donors and split in slices
            donor_slices = self.get_donor_slices(donors, receivers, resource, d_field)

            # Print current donor slices
            self.print_donor_slices(donor_slices)

            while donor_slices:
                # If no receivers left, stop redistribution process
                if not receivers:
                    break

                # Order receivers to prioritise donations
                receivers = sorted(receivers, key=lambda s: self.resources_tracker.get_receiver_priority(s["_id"], resource, d_field))

                # The loop iterates over a copy so that the list of receivers can be modified inside the loop
                for receiver in list(receivers):
                    receiver_data = self.resources_tracker.get_structure_resource(receiver["_id"], resource)
                    key = self.get_donor_slice_key(receiver, resource)

                    if key not in donor_slices:
                        utils.log_info("No suitable donors have been found for receiver {0}, searched for by key '{1}'".format(receiver["name"], key), self.debug)
                        receivers.remove(receiver)
                        continue

                    # When donating "current", structure can't receive more than its "max" limit
                    max_receiver_amount = receiver_data["max"] - receiver_data["current"]
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
                    self.manage_swap(donor, receiver, resource, d_field, amount_to_scale, requests)

                    utils.log_info("Resource {0} swap between {1} (donor) and {2} (receiver) with amount {3}".format(
                        resource, donor["name"], receiver["name"], amount_to_scale), self.debug)

            if self.compensate:
                self.perform_compensation(valid_structures, receivers, resource, d_field, requests)

