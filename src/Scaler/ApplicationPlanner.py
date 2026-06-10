from copy import deepcopy

import src.MyUtils.MyUtils as utils
from src.Scaler.ContainerPlanner import ContainerPlanner
from src.Scaler.ScalerUtils import ApplicationRequest


class ApplicationPlanner(ContainerPlanner):
    PARENT_LEVEL = "user"
    CURRENT_LEVEL = "application"

    def get_scalable_container(self, app_containers, amount, resource, field, priority, prev_scalings):
        scalable_containers = []
        # Look for applications that can be rescaled
        for container_name, container in app_containers.items():
            max_value = container["resources"][resource]["max"] + prev_scalings.get(container_name, 0)
            min_value = container["resources"][resource]["min"]

            if container_name not in self.data_context.container_usages:
                self.log_warning("Usage information for container {0} could not be retrieved, "
                                 "skipping container in app splits distribution".format(container_name))
                continue

            if "usage" not in container["resources"][resource]:
                raise ValueError("Usage information is not available for container '{0}' during app request propagation".format(container_name))

            # Rescale down: "max" can't be scaled below "min"
            if amount < 0 and max_value + amount >= min_value:
                scalable_containers.append(container)
            # Rescale up
            elif amount > 0:
                # TODO: Think if we should check the host free resources for a "max" scaling
                scalable_containers.append(container)

        if not scalable_containers:
            return False, {}, None

        # Look for the best fit container for this resource and generate a rescaling request for it
        best_fit_container = utils.get_best_fit_container(scalable_containers, resource, amount, field)
        success = best_fit_container is not None

        return success, best_fit_container, utils.generate_request(best_fit_container, amount, resource, priority, field)

    def propagate_application_request(self, app, containers, app_request, num_containers):
        amount, resource, field, priority = app_request["amount"], app_request["resource"], app_request["field"], app_request["priority"]
        app_containers = {cont_name: containers.get(cont_name) for cont_name in app.get("containers", [])}
        container_requests = {}
        if app_containers:
            # Check application limit is consistent with aggregated container limits
            containers_agg_value = sum(cont["resources"][resource][field] for cont in app_containers.values())
            if containers_agg_value != app["resources"][resource][field]:
                # TODO: Fix containers scaled amount, while application amount remains the same
                new_amount = amount + (app["resources"][resource][field] - containers_agg_value)
                self.log_warning("Application '{0}' containers have an aggregated {1} {2} = {3}, which differs from "
                                 "application value {4}.").format(app["name"], resource, field, containers_agg_value, app["resources"][resource][field])
                self.log_warning("Amount for containers belonging to application '{0}' should be changed from "
                                 "{1} to {2} ".format(app["name"], amount, new_amount))

            # Partition total amount into small splits
            container_splits = utils.split_amount_in_num_slices(amount, num_containers)

            # Try to distribute splits among containers
            container_requests, scaled_amount = self.distribute_splits(app_containers, container_splits, resource, field, priority, self.get_scalable_container)
        else:
            scaled_amount = amount

        return container_requests, scaled_amount

    def plan_operation(self, operation, host_tracker=None, swap_part=None):
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
            lower_limit = application["resources"][resource].get("min", 0) if application.get("running", False) else 0
            new_amount = max(min(lower_limit - application["resources"][resource][field], 0), amount)
            if self.op_should_be_aborted(op_type, app_request, new_amount):
                return False, []
            app_request["amount"] = new_amount

        # Propagate application request to containers (if they exist)
        container_reqs, scaled_amount = self.propagate_application_request(application, containers, app_request, num_containers)
        if self.op_should_be_aborted(op_type, app_request, scaled_amount):
            return False, []

        # Update application request with the final scaled amount
        self.update_request_amount(app_request, scaled_amount)

        # Check generated container requests can be fully performed
        flattened_container_reqs = self.flatten_requests_by_structure(container_reqs)
        host_tracker = {} if host_tracker is None else host_tracker
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
