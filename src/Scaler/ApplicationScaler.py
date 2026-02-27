from copy import deepcopy

import src.MyUtils.MyUtils as utils
from src.Scaler.ContainerScaler import ContainerScaler
from src.Scaler.ScalerUtils import ApplicationRequest


class ApplicationScaler(ContainerScaler):
    PARENT_LEVEL = "user"
    CURRENT_LEVEL = "application"

    def get_scalable_container(self, app_containers, amount, resource, field, priority):
        scalable_containers = []
        # Look for applications that can be rescaled
        for container_name, container in app_containers.items():
            max_value = container["resources"][resource]["max"]
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
            else:
                # TODO: Think if we should check the host free resources for a "max" scaling
                scalable_containers.append(container)

        if not scalable_containers:
            return False, {}, None

        # Look for the best fit container for this resource and generate a rescaling request for it
        best_fit_container = utils.get_best_fit_container(scalable_containers, resource, amount, field)
        success = best_fit_container is not None

        return success, best_fit_container, utils.generate_request(best_fit_container, amount, resource, priority, field)

    def propagate_application_request(self, app, containers, app_request):
        amount, resource, field, priority = app_request["amount"], app_request["resource"], app_request["field"], app_request["priority"]
        app_containers = {cont_name: containers.get(cont_name) for cont_name in app.get("containers", [])}
        container_requests = {}
        if app_containers:
            # Partition total amount into small splits to distribute among applications
            split_amount = -self.SCALING_SPLIT_AMOUNT if amount < 0 else self.SCALING_SPLIT_AMOUNT
            container_splits = utils.split_amount_in_slices(amount, split_amount)

            # Try to distribute splits among containers
            container_requests, scaled_amount = self.distribute_splits(app_containers, container_splits, resource, field, priority, self.get_scalable_container)
        else:
            scaled_amount = amount

        return container_requests, scaled_amount

    def plan_operation(self, data_context, operation, swap_part=None):
        final_requests = []
        data_to_update = {"applications": {}, "containers": {}, "container_resources": {}}

        # Get info from operation
        op_type, resource = operation.op_type, operation.resource
        amount, structure_name = self._get_amount_and_structure(operation, swap_part)
        field, priority = operation.field, operation.priority

        # Get structures from data context
        application = data_context.applications[structure_name]
        containers = data_context.containers

        # Generate application base request
        app_request = utils.generate_request(application, amount, resource, priority, field)

        # Propagate application request to containers (if they exist)
        containers_copy = deepcopy(containers)  # Make a copy to avoid modifying original containers here
        container_reqs, scaled_amount = self.propagate_application_request(application, containers_copy, app_request)
        if self.op_should_be_aborted(op_type, app_request, scaled_amount):
            return False, [], None
        # Update application data with the final scaled amount
        self.update_request(app_request, scaled_amount)
        application["resources"][resource][field] += scaled_amount

        # Check generated container requests can be fully performed
        flattened_container_reqs = self.flatten_requests_by_structure(container_reqs)
        for cont_name, cont_req in flattened_container_reqs.items():
            total_amount = cont_req["amount"]
            bogus_op = self._create_bogus_operation(op_type, "container", cont_name, cont_req, resource, field, total_amount, priority)
            success, child_requests, child_data = super().plan_operation(data_context, bogus_op, swap_part)
            if not success:
                return False, [], None

            # Register data to update and requests
            data_to_update.update(child_data)
            final_requests.extend(child_requests)

            # Update application data with the final scaled amount
            scaled_amount = sum([r.request["amount"] for r in child_requests if r.get_type() == "container"])
            if scaled_amount != total_amount:
                app_request["amount"] -= (total_amount - scaled_amount)
                application["resources"][resource][field] -= (total_amount - scaled_amount)

        # Add application request and data to update
        final_requests.append(ApplicationRequest(app_request, self.couchdb_handler, self.rescaler_session, self.debug))
        data_to_update["applications"][structure_name] = application

        return True, final_requests, data_to_update
