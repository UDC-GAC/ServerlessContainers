from abc import ABC, abstractmethod
from copy import deepcopy

import src.MyUtils.MyUtils as utils
from src.Scaler.ScalerUtils import ResourceOperation


class BaseScaler(ABC):
    """Common interface for all scalers (container, application, user)"""

    SCALING_SPLIT_AMOUNT = 5
    PARENT_LEVEL = None
    CURRENT_LEVEL = None

    def __init__(self, couchdb_handler, rescaler_session, data_context, debug=False):
        self.couchdb_handler = couchdb_handler
        self.rescaler_session = rescaler_session
        self.data_context = data_context
        self.debug = debug

    def log_info(self, msg):
        utils.log_info(msg, self.debug)

    def log_error(self, msg):
        utils.log_error(msg, self.debug)

    def log_warning(self, msg):
        utils.log_warning(msg, self.debug)

    # --------- Functions to be overwritten by specific scalers ---------

    @abstractmethod
    def plan_operation(self, data_context, operation, swap_part=None):
        """ Plans the full execution of a single operation, generating the needed requests to carry it out"""
        pass

    # --------- Auxiliar functions ---------

    @staticmethod
    def requests_are_pairs(request1, request2):
        return (request1["resource"] == request2["resource"] and
                request1["pair_structure"] == request2["structure"] and
                request2["pair_structure"] == request1["structure"] and
                abs(request1["amount"]) == abs(request2["amount"]))

    @staticmethod
    def flatten_requests_by_structure(requests_by_structure):
        flattened_requests = {}
        for structure_name in requests_by_structure:
            # Copy the first request as the base request
            flat_request = dict(requests_by_structure[structure_name][0])
            flat_request["amount"] = sum([r["amount"] for r in requests_by_structure[structure_name]])
            flattened_requests[structure_name] = flat_request

        return flattened_requests

    @staticmethod
    def _get_amount_and_structure(operation, swap_part=None):
        """Get amount and structure name from operation info"""
        amount = -operation.amount if operation.type == "SCALE_DOWN" else operation.amount
        structure = operation.donor if operation.type == "SCALE_DOWN" else operation.receiver
        if operation.type == "SWAP":
            if swap_part is None:
                raise ValueError("Swap part not indicated in a swap operation: {0}".format(operation))
            if swap_part not in {"donor", "receiver"}:
                raise ValueError("Invalid swap part indicated in a swap operation: '{0}'".format(swap_part))
            amount = -operation.amount if swap_part == "donor" else operation.amount
            structure = operation.donor if swap_part == "donor" else operation.receiver
        return amount, structure

    @staticmethod
    def _create_bogus_operation(scope, structure_name, request, amount, resource, priority):
        return ResourceOperation("SCALE_DOWN" if amount < 0 else "SCALE_UP", scope, request,
                                 structure_name if "SCALE_DOWN" else "system",
                                 structure_name if "SCALE_UP" else "system",
                                 resource, amount, priority)

    @staticmethod
    def _apply_execution_priority(items):
        def _intra_priority_order(_i):
            # 1) First, "current" is scaled down to free host resources and ensure "max" scale-downs are valid
            if _i.get("amount") < 0 and _i.get("field") == "current":
                return 3
            # 2) Then, "max" is scaled down
            elif _i.get("amount") < 0 and _i.get("field") == "max":
                return 2
            # 3) Now "max" is scaled up first to give more "space" for "current" scale-ups
            elif _i.get("amount") > 0 and _i.get("field") == "max":
                return 1
            # 4) Then, "current" is scaled up
            elif _i.get("amount") > 0 and _i.get("field") == "current":
                return 0
            else:
                raise ValueError("Unexpected combination: {0}, {1}".format(_i.get("amount"), _i.get("field")))

        return sorted(items, key=lambda _i: (_i.get("priority", 0), _intra_priority_order(_i)), reverse=True)

    @staticmethod
    def distribute_splits(childs, splits, resource, field, priority, selector):
        success, scaled_amount, generated_requests, received = True, 0, {}, {}
        while success and len(splits) > 0:
            amount = splits.pop(0)
            success, best_child, generated_request = selector(childs, amount, resource, field, priority)
            if success:
                child_name = best_child["name"]

                # Save generated request for the best fit child
                generated_requests.setdefault(child_name, []).append(generated_request)

                # Update the child's resources for next iteration
                received[child_name] = received.get(child_name, 0) + amount
                best_child["resources"][resource][field] += amount
                childs[child_name] = best_child
                scaled_amount += amount

        return generated_requests, scaled_amount

    def op_should_be_aborted(self, op_type, request, scaled_amount):
        if scaled_amount != request["amount"] and op_type == "SWAP":
            self.log_warning("Structure '{0}' scaling could not be fully planned ({1} out of {2}) and request is part "
                             "of a pair-swapping operation, aborting".format(request["structure"], scaled_amount, request["amount"]))
            return True
        return False

    def update_request(self, request, scaled_amount):
        if scaled_amount != request["amount"]:
            self.log_warning("Structure '{0}' scaling could not be fully planned, only {1} shares out of {2}"
                             .format(request["structure"], scaled_amount, request["amount"]))
            request["amount"] = scaled_amount

    def create_operations(self, requests):
        scope = self.CURRENT_LEVEL
        already_added_pairs = set()
        operations = []
        for req in requests:
            resource, priority = req["resource"], req.get("priority", 0)
            op_type = "SCALE_UP" if req["amount"] > 0 else "SCALE_DOWN"
            amount = abs(req["amount"])
            donor, receiver = None, None

            if op_type == "SCALE_UP":
                donor = req.get("pair_structure", "system")
                receiver = req["structure_name"]

            if op_type == "SCALE_DOWN":
                donor = req["structure_name"]
                receiver = req.get("pair_structure", "system")

            # Check if the request is part of a pair-swapping
            if "pair_structure" in req:
                # If operation was created when processing the pair request, skip it to avoid duplicates
                # TODO: If ReBalancer only sends one request per swap this is not necessary
                if (req["pair_structure"], req["structure_name"], resource, amount) in already_added_pairs:
                    continue
                op_type = "SWAP"
                already_added_pairs.add((req["structure_name"], req["pair_structure"], resource, amount))

            operations.append(ResourceOperation(op_type, scope, req, donor, receiver, resource, amount, priority))

        return operations

    def plan_operations_execution(self, operations):
        """ For each operation, plans the execution of the generated requests and checks if they can be fully performed.
            If not, the operation is discarded"""
        valid_operations = []
        # Create a copy of data context to persist only successful operations
        data_context_copy = deepcopy(self.data_context)
        for op in operations:
            success, donor_success, receiver_success = False, False, False
            generated_requests, donor_requests, receiver_requests = [], [], []
            data_to_update = {}

            if op.type == "SWAP":
                donor_success, donor_requests, data_to_update = self.plan_operation(data_context_copy, op, "donor")
                if donor_success:
                    receiver_success, receiver_requests, receiver_data = self.plan_operation(data_context_copy, op, "receiver")
                    data_to_update.update(receiver_data)
                success = donor_success and receiver_success
                generated_requests = donor_requests, receiver_requests

            if op.type == "SCALE_UP":
                success, generated_requests, data_to_update = self.plan_operation(data_context_copy, op)

            if op.type == "SCALE_DOWN":
                success, generated_requests, data_to_update = self.plan_operation(data_context_copy, op)

            if success:
                # Add generated requests to operations
                op.add_requests(generated_requests)
                # Update data context as operation was successful
                for data_type in data_to_update:
                    self.data_context.get(data_type, {}).update(data_to_update[data_type])
                # Save operation as valid
                valid_operations.append(op)
            else:
                # Revert changes in data context copy as operation was aborted
                data_context_copy = deepcopy(self.data_context)
                self.log_warning("Some error found while planning operation (aborted): {0}".format(op))

        return valid_operations

    def plan(self, requests):
        """ Creates and plan a list of operations with the given requests"""
        # Order requests by execution priority
        sorted_requests = self._apply_execution_priority(requests)

        # Create operation objects based on received requests
        operations = self.create_operations(sorted_requests)

        # Plan the requests that need to be executed in order to complete the full operation
        final_operations = self.plan_operations_execution(operations)

        # Order operations and order generated requests inside each operation by execution priority
        sorted_operations = self._apply_execution_priority(final_operations)
        for op in sorted_operations:
            op.set_generated_requests(self._apply_execution_priority(op.generated_requests))

        return sorted_operations
