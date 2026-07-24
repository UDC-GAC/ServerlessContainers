from copy import deepcopy

import src.MyUtils.MyUtils as utils
from src.Scaler.ApplicationPlanner import ApplicationPlanner
from src.Scaler.ScalerUtils import UserRequest


class UserPlanner(ApplicationPlanner):
    PARENT_LEVEL = "host"
    CURRENT_LEVEL = "user"

    def plan_operation(self, operation, host_tracker, swap_part=None):
        final_requests = []
        # Get info from operation
        op_type, resource = operation.op_type, operation.resource
        amount, structure_name = self._get_amount_and_structure(operation, swap_part)
        field, priority = operation.field, operation.priority

        # Get structures from data context
        user = self.data_context.users[structure_name]
        applications = self.data_context.applications

        # Generate user base request
        user_request = utils.generate_request(user, amount, resource, priority, field)

        # Count user apps and user running apps
        num_apps, num_active_apps = 0, 0
        for app_name in user.get("clusters", []):
            num_apps +=1
            if applications.get(app_name).get("state", "") == "running":
                num_active_apps += 1

        # Check user can be scaled respecting QoS contraints
        if amount < 0:
            lower_limit = 0 if num_active_apps <= 0 else max(user["resources"][resource]["min"], 1)
            new_amount = max(min(lower_limit - user["resources"][resource][field], 0), amount)
            if self.op_should_be_aborted(op_type, user_request, new_amount):
                return False, []
            user_request["amount"] = new_amount

        # When scaling user down, check if max/current limit will go below min
        if user_request["amount"] < 0 and user["resources"][resource][field] < user["resources"][resource]["min"]:
            # If user has at least one application running, "max"/"current" can't be scaled below "min"
            if num_active_apps > 0:
                return False, []

        # Propagate user request to applications (if they exist)
        app_reqs, scaled_amount = utils.propagate_user_request(user, applications, user_request)
        if self.op_should_be_aborted(op_type, user_request, scaled_amount):
            return False, []

        # Update user request with the final scaled amount
        self.update_request_amount(user_request, scaled_amount)

        # Check generated application requests can be fully performed
        flattened_app_reqs = self.flatten_requests_by_structure(app_reqs)
        for app_name, app_req in flattened_app_reqs.items():
            app_amount = app_req["amount"]
            bogus_op = self._create_bogus_operation(op_type, "application", app_name, app_req, resource, field, app_amount, priority)
            success, child_requests = super().plan_operation(bogus_op, host_tracker, swap_part)
            if not success:
                return False, []

            # Save generated requests
            final_requests.extend(child_requests)

            # Update user request with the application's scaled amount
            app_scaled_amount = sum([r.request["amount"] for r in child_requests if r.get_type() == "application"])
            if app_scaled_amount != app_amount:
                user_request["amount"] -= (app_amount - app_scaled_amount)

        # Add user request and data to update
        if user_request["amount"] != 0:
            final_requests.append(UserRequest(user_request, self.couchdb_handler, self.rescaler_session, self.debug))

        return True, final_requests



