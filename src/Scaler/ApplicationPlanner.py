from copy import deepcopy

import src.MyUtils.MyUtils as utils
from src.Scaler.ContainerPlanner import ContainerPlanner
from src.Scaler.ScalerUtils import ApplicationRequest


class ApplicationPlanner(ContainerPlanner):
    PARENT_LEVEL = "user"
    CURRENT_LEVEL = "application"

    def plan_operation(self, operation, host_tracker, swap_part=None):
        final_requests = []

        # Get info from operation
        op_type, resource = operation.op_type, operation.resource
        amount, structure_name = self._get_amount_and_structure(operation, swap_part)
        field, priority = operation.field, operation.priority

        # Get structures from data context
        application = self.data_context.applications[structure_name]
        containers = self.data_context.containers

        # Generate application base request
        app_request = utils.generate_request(application, amount, resource, priority, field)

        num_containers = len(application.get("containers", []))
        # Check application can be scaled respecting QoS contraints
        if amount < 0:
            lower_limit = max(application["resources"][resource].get("min", 0), 1) if application.get("state", "") == "running" else 0
            new_amount = max(min(lower_limit - application["resources"][resource][field], 0), amount)
            if self.op_should_be_aborted(op_type, app_request, new_amount):
                return False, []
            app_request["amount"] = new_amount

        # Propagate application request to containers (if they exist)
        container_reqs, scaled_amount = utils.propagate_application_request(application, containers, app_request)
        if self.op_should_be_aborted(op_type, app_request, scaled_amount):
            return False, []

        # Update application request with the final scaled amount
        self.update_request_amount(app_request, scaled_amount)

        # Check generated container requests can be fully performed
        flattened_container_reqs = self.flatten_requests_by_structure(container_reqs)
        for cont_name, cont_req in flattened_container_reqs.items():
            container_amount = cont_req["amount"]
            bogus_op = self._create_bogus_operation(op_type, "container", cont_name, cont_req, resource, field, container_amount, priority)
            success, child_requests = super().plan_operation(bogus_op, host_tracker, swap_part)
            if not success:
                return False, []

            # Save generated requests
            final_requests.extend(child_requests)

            # Update application request with the container's scaled amount
            container_scaled_amount = sum([r.request["amount"] for r in child_requests if r.get_type() == "container"])
            if container_scaled_amount != container_amount:
                app_request["amount"] -= (container_amount - container_scaled_amount)

        # Add application request and data to update
        if app_request["amount"] != 0:
            final_requests.append(ApplicationRequest(app_request, self.couchdb_handler, self.rescaler_session, self.debug))

        return True, final_requests
