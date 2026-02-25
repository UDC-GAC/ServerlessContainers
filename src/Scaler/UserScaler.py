from copy import deepcopy

import src.MyUtils.MyUtils as utils
from src.Scaler.ApplicationScaler import ApplicationScaler
from src.Scaler.ScalerUtils import UserRequest


class UserScaler(ApplicationScaler):
    PARENT_LEVEL = "host"
    CURRENT_LEVEL = "user"

    @staticmethod
    def get_scalable_app(user_apps, amount, resource, field, priority):
        scalable_apps = list()
        # Look for applications that can be rescaled
        for app_name, app in user_apps.items():
            # Inconsistent state for app, it can't be scaled
            if bool(app.get("containers", [])) ^ app.get("running", False):
                continue

            # Rescale down: if app is running "max" can't be scaled below "min"
            if amount < 0:
                lower_limit = app["resources"][resource].get("min", 0) if app.get("running", False) else 0
                if app["resources"][resource]["max"] + amount >= lower_limit:
                    scalable_apps.append(app)
            # Rescale up: always
            elif amount > 0:
                scalable_apps.append(app)

        if not scalable_apps:
            return False, {}, None

        # Look for the best fit application for this resource and generate a rescaling request for it
        best_fit_app = utils.get_best_fit_app(scalable_apps, resource, amount)
        success = best_fit_app is not None

        return success, best_fit_app, utils.generate_request(best_fit_app, amount, resource, field, priority)

    def propagate_user_request(self, user, applications, user_request):
        amount, resource, field, priority = user_request["amount"], user_request["resource"], user_request["field"], user_request["priority"]
        user_apps = {app_name: applications.get(app_name) for app_name in user.get("clusters", [])}
        app_requests = {}
        if user_apps:
            # Partition total amount into small splits to distribute among applications
            split_amount = -self.SCALING_SPLIT_AMOUNT if amount < 0 else self.SCALING_SPLIT_AMOUNT
            app_splits = utils.split_amount_in_slices(amount, split_amount)

            # Try to distribute splits among applications
            app_requests, scaled_amount = self.distribute_splits(user_apps, app_splits, resource, field, priority, self.get_scalable_app)
        else:
            scaled_amount = amount

        return app_requests, scaled_amount

    def plan_operation(self, data_context, operation, swap_part=None):
        final_requests = []
        data_to_update = {"users": {}, "applications": {}, "containers": {}, "container_resources": {}}

        # Get info from operation
        op_type, resource = operation.type, operation.resource
        amount, structure_name = self._get_amount_and_structure(operation, swap_part)
        field, priority = operation.field, operation.priority

        # Get structures from data context
        user = data_context.users[structure_name]
        applications = data_context.applications

        # Generate user base request
        user_request = utils.generate_request(user, amount, resource, priority, field)

        # Propagate user request to applications (if they exist)
        applications_copy = deepcopy(applications)  # Make a copy to avoid modifying original applications here
        app_reqs, scaled_amount = self.propagate_user_request(user, applications_copy, user_request)
        if self.op_should_be_aborted(op_type, user_request, scaled_amount):
            return False, [], None

        # Update user data with the final scaled amount
        self.update_request(user_request, scaled_amount)
        user["resources"][resource][field] += scaled_amount

        # Check generated application requests can be fully performed
        flattened_app_reqs = self.flatten_requests_by_structure(app_reqs)
        for app_name, app_req in flattened_app_reqs.items():
            total_amount = app_req["amount"]
            bogus_op = self._create_bogus_operation("application", app_name, app_req, total_amount, resource, priority)
            success, child_requests, child_data = super().plan_operation(data_context, bogus_op)
            if not success:
                return False, [], None

            # Register data to update and generated requests
            data_to_update.update(child_data)
            final_requests.extend(child_requests)

            # Update user data with the final scaled amount
            scaled_amount = sum([r.request["amount"] for r in child_requests if r.get_type() == "application"])
            if scaled_amount != total_amount:
                user_request["amount"] -= (total_amount - scaled_amount)
                user["resources"][resource][field] -= (total_amount - scaled_amount)

        # Add user request and data to update
        final_requests.append(UserRequest(user_request, self.couchdb_handler, self.rescaler_session, self.debug))
        data_to_update["users"][structure_name] = user

        return True, final_requests, data_to_update



