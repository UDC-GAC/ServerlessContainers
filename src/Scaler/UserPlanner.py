from copy import deepcopy

import src.MyUtils.MyUtils as utils
from src.Scaler.ApplicationPlanner import ApplicationPlanner
from src.Scaler.ScalerUtils import UserRequest


class UserPlanner(ApplicationPlanner):
    PARENT_LEVEL = "host"
    CURRENT_LEVEL = "user"

    @staticmethod
    def get_scalable_app(user_apps, amount, resource, field, priority, prev_scalings):
        scalable_apps = list()
        # Look for applications that can be rescaled
        for app_name, app in user_apps.items():
            # Inconsistent state for app, it can't be scaled
            if bool(app.get("containers", [])) ^ app.get("running", False):
                continue

            # Rescale down: if app is running, "max" can't be scaled below "min"
            if amount < 0:
                lower_limit = app["resources"][resource].get("min", 0) if app.get("running", False) else 0
                if app["resources"][resource]["max"] + amount + prev_scalings.get(app["name"], 0) >= lower_limit:
                    scalable_apps.append(app)
            # Rescale up: always
            elif amount > 0:
                scalable_apps.append(app)

        if not scalable_apps:
            return False, {}, None

        # Look for the best fit application for this resource and generate a rescaling request for it
        best_fit_app = utils.get_best_fit_app(scalable_apps, resource, amount, prev_scalings)
        success = best_fit_app is not None

        return success, best_fit_app, utils.generate_request(best_fit_app, amount, resource, priority, field)

    def propagate_user_request(self, user, user_request, applications, num_apps):
        amount, resource, field, priority = user_request["amount"], user_request["resource"], user_request["field"], user_request["priority"]
        user_apps = {app_name: applications.get(app_name) for app_name in user.get("clusters", [])}
        app_requests = {}
        if user_apps:
            # Check user limit is consistent with aggregated application limits
            apps_agg_value = sum(app["resources"][resource][field] for app in user_apps.values())
            if apps_agg_value != user["resources"][resource][field]:
                # TODO: Fix applications scaled amount, while user amount remains the same
                new_amount = amount + (user["resources"][resource][field] - apps_agg_value)
                self.log_warning("User '{0}' applications have an aggregated {1} {2} = {3}, which differs from user "
                                 "value {4}.").format(user["name"], resource, field, apps_agg_value, user["resources"][resource][field])
                self.log_warning("Amount for applications belonging to user '{0}' should be changed from "
                                 "{1} to {2}".format(user["name"], amount, new_amount))

            # Partition total amount into small splits to distribute among applications
            app_splits = utils.split_amount_in_num_slices(amount, num_apps)

            # Try to distribute splits among applications
            app_requests, scaled_amount = self.distribute_splits(user_apps, app_splits, resource, field, priority, self.get_scalable_app)
        else:
            scaled_amount = amount

        return app_requests, scaled_amount

    def plan_operation(self, operation, host_tracker=None, swap_part=None):
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
            if applications.get(app_name).get("running", False):
                num_active_apps += 1

        # Check user can be scaled respecting QoS contraints
        if amount < 0:
            lower_limit = 0 if num_active_apps <= 0 else user["resources"][resource]["min"]
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
        app_reqs, scaled_amount = self.propagate_user_request(user, user_request, applications, num_apps)
        if self.op_should_be_aborted(op_type, user_request, scaled_amount):
            return False, []

        # Update user request with the final scaled amount
        self.update_request_amount(user_request, scaled_amount)

        # Check generated application requests can be fully performed
        flattened_app_reqs = self.flatten_requests_by_structure(app_reqs)
        host_tracker = {} if host_tracker is None else host_tracker
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



