from abc import ABC, abstractmethod

import src.MyUtils.MyUtils as utils
from src.Scaler.ScalerUtils import ResourceOperation


class BasePlanner(ABC):
    """Common interface for all planners (container, application, user)"""

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
    def plan_operation(self, operation, host_tracker, swap_part=None):
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
        amount = -operation.amount if operation.op_type == "SCALE_DOWN" else operation.amount
        structure = operation.donor if operation.op_type == "SCALE_DOWN" else operation.receiver
        if operation.op_type == "SWAP":
            if swap_part is None:
                raise ValueError("Swap part not indicated in a swap operation: {0}".format(operation))
            if swap_part not in {"donor", "receiver"}:
                raise ValueError("Invalid swap part indicated in a swap operation: '{0}'".format(swap_part))
            amount = -operation.amount if swap_part == "donor" else operation.amount
            structure = operation.donor if swap_part == "donor" else operation.receiver
        return amount, structure

    @staticmethod
    def _create_bogus_operation(op_type, scope, structure_name, request, resource, field, amount, priority):
        donor = structure_name if amount < 0 else "system"
        receiver = structure_name if amount > 0 else "system"
        return ResourceOperation(op_type, scope, request, donor, receiver, resource, field, abs(amount), priority)

    @staticmethod
    def _apply_execution_priority(items):
        def _priority(_i):
            amount, field = _i.get("amount"), _i.get("field")
            # 1) First, "current" is scaled down to free host resources and ensure "max" scale-downs are valid
            # 2) Then, "max" is scaled down
            if amount < 0:
                return 2 if field == "max" else 3
            # 3) Now "max" is scaled up first to give more "space" for "current" scale-ups
            # 4) Then, "current" is scaled up
            elif amount > 0:
                return 1 if field == "max" else 0
            raise ValueError("Amount is 0 for request {0}".format(_i))
        return sorted(items, key=lambda _i: (_priority(_i), _i.get("priority", 0)), reverse=True)

    @staticmethod
    def distribute_splits(childs, splits, resource, field, priority, selector):
        success, scaled_amount, generated_requests = True, 0, {}
        prev_scalings = {}
        while success and len(splits) > 0:
            amount = splits.pop(0)
            success, best_child, generated_request = selector(childs, amount, resource, field, priority, prev_scalings)
            if success:
                child_name = best_child["name"]

                # Save generated request for the best fit child
                generated_requests.setdefault(child_name, []).append(generated_request)

                # Register scaling for next iterations
                prev_scalings.setdefault(best_child["name"], 0)
                prev_scalings[best_child["name"]] += amount

                # Update the child's resources for next iteration
                scaled_amount += amount

        return generated_requests, scaled_amount

    def op_should_be_aborted(self, op_type, request, scaled_amount):
        if scaled_amount == 0:
            self.log_warning("Structure '{0}' scaling was {1} and has become zero, aborting operation".format(request["structure"], request["amount"]))
            return True

        if scaled_amount != request["amount"] and op_type == "SWAP":
            self.log_warning("Structure '{0}' scaling could not be fully planned ({1} out of {2}) and request is part "
                             "of a pair-swapping operation, aborting".format(request["structure"], scaled_amount, request["amount"]))
            return True

        if 0 > request["amount"] > scaled_amount:
            self.log_warning("Structure '{0}' inconsistent scaling, scaling down more than suggested (amount was {1} and"
                             " scaled amount is {2}, aborting".format(request["structure"], request["amount"], scaled_amount))
            return True

        if 0 < request["amount"] < scaled_amount:
            self.log_warning("Structure '{0}' inconsistent scaling, scaling up more than suggested (amount was {1} and"
                             " scaled amount is {2}, aborting".format(request["structure"], request["amount"], scaled_amount))
            return True

        return False

    def update_request_amount(self, request, scaled_amount):
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
            field = req["field"]
            amount = abs(req["amount"])
            donor, receiver = None, None

            if op_type == "SCALE_UP":
                donor = req.get("pair_structure", "system")
                receiver = req["structure"]

            if op_type == "SCALE_DOWN":
                donor = req["structure"]
                receiver = req.get("pair_structure", "system")

            # Check if the request is part of a pair-swapping
            if "pair_structure" in req:
                op_type = "SWAP"

            operations.append(ResourceOperation(op_type, scope, req, donor, receiver, resource, field, amount, priority))

        return operations

    def apply_changes(self, generated_requests):
        for r in generated_requests:
            data_type = "{0}s".format(r.get_type())
            structure = self.data_context.get(data_type, {}).get(r.get("structure_name"))
            field, amount, resource = r.get("field"), r.get("amount"), r.get("_request", {}).get("resource")

            # Update structure resources
            structure["resources"][resource][field] += amount

            # Containers must also update host free resources and container physical resources
            if data_type == "containers":
                host = self.data_context.hosts.get(structure["host"], None)
                cont_resources = self.data_context.get("container_resources").get(r.get("structure_name"))
                resource_limit = r.translate(resource)
                scaled_current_amount = amount

                # Update host resources
                if resource in {"disk_read", "disk_write"}:
                    disk_op = resource.split("_")[-1]
                    bound_disk = structure["resources"].get("disk", {}).get("name")
                    host["resources"]["disks"][bound_disk]["free_{0}".format(disk_op)] -= scaled_current_amount
                else:
                    if field == "max":
                        scaled_current_amount = structure["resources"][resource]["max"] - structure["resources"][resource]["current"]
                    host["resources"][resource]["free"] -= scaled_current_amount

                # Update container physical resources
                cont_resources["resources"][resource][resource_limit] += scaled_current_amount

    def check_operation_consistency(self, operation):
        resource, request, op_type = operation.resource, operation.original_request, operation.op_type
        if resource == "cpu" and "power_budget" in request and op_type != "SWAP":
            # Try getting request structure from data context
            structure_type_str = str(request["structure_type"]) + "s"
            structure_name = operation.receiver if op_type == "SCALE_UP" else operation.donor
            structure = self.data_context.get(structure_type_str, {}).get(structure_name)
            if structure is None:
                raise ValueError("Structure {0} (type={1}) not found checking operation consistency: {2}"
                                 .format(structure_name, structure_type_str, operation))

            current_pb = structure["resources"]["energy"]["current"]
            request_pb = request["power_budget"]
            # If request scales CPU up, but power budget has been decreased since generation, cancel operation
            if op_type == "SCALE_UP" and request_pb > current_pb:
                return False, "Aborting CPU scale-up because power budget has been decreased since the request was generated"

            # If request scales CPU down, but power budget has been increased since generation, cancel operation
            if op_type == "SCALE_DOWN" and request_pb < current_pb:
                return False, "Aborting CPU scale-down because power budget has been increased since the request was generated"

        return True, ""

    def plan_operations_execution(self, operations):
        """ For each operation, plans the execution of the generated requests and checks if they can be fully performed.
            If not, the operation is discarded"""
        valid_operations = []
        for op in operations:
            success, donor_success, receiver_success = False, False, False
            generated_requests, donor_requests, receiver_requests = [], [], []

            consistent, msg = self.check_operation_consistency(op)
            if not consistent:
                self.log_warning(msg)
                continue

            if op.op_type == "SWAP":
                donor_success, donor_requests = self.plan_operation(op, {}, swap_part="donor")
                if donor_success:
                    receiver_success, receiver_requests = self.plan_operation(op, {}, swap_part="receiver")
                success = donor_success and receiver_success
                generated_requests = donor_requests + receiver_requests

            if op.op_type == "SCALE_UP":
                success, generated_requests = self.plan_operation(op, {})

            if op.op_type == "SCALE_DOWN":
                success, generated_requests = self.plan_operation(op, {})

            if success and generated_requests:
                # Add generated requests to operations
                op.add_requests(generated_requests)
                # Update data context as operation was successful
                self.apply_changes(generated_requests)
                # Save operation as valid
                valid_operations.append(op)
            else:
                # Don't apply changes in data context as operation was aborted
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

        return sorted_operations
