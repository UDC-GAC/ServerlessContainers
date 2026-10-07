"""
Budget policies of the EnergyManager: they decide the power budget of each container.

- "direct": container budgets follow the budgets set by the user (on containers, applications or
  users). A change in the budget of an application or user is propagated to its applications and
  containers in the same iteration, with the same distribution as the Scaler
  (MyUtils.propagate_user_request / propagate_application_request, in 1 W slices).
- Other policies (e.g., automatic rebalancing) can be plugged in as "package.module:ClassName"
  extending BudgetPolicy.
"""
import importlib

import src.MyUtils.MyUtils as utils


class BudgetPolicy:

    def __init__(self, log_info, log_warning, log_error):
        self.log_info, self.log_warning, self.log_error = log_info, log_warning, log_error

    def configure(self, config):
        self.config = config

    def compute(self, containers, applications, users, applied, usages, external):
        """
        Args:
            containers/applications/users: CouchDB documents by name (in-memory copies that can be modified)
            applied: {container: budget currently applied (W)}
            usages: {container: {"structure.energy.usage": W, ...}}
            external: {"container"|"application"|"user": {name: delta (W)}} budget changes made directly in
                CouchDB since the last iteration (the documents already hold the new values, except containers)
        Returns:
            ({container: new budget}, {structure name: (structure, changes to persist)})
        """
        raise NotImplementedError


class DirectBudgetPolicy(BudgetPolicy):

    @staticmethod
    def _energy(structure, field):
        return structure.get("resources", {}).get("energy", {}).get(field)

    def _propagate(self, parent, children, children_field, amount, propagate_fn):
        request = {"amount": amount, "resource": "energy", "field": "max", "priority": 0}
        requests, scaled = propagate_fn(parent, children, request)
        if scaled != amount:
            self.log_warning("@{0} Only {1} W out of {2} W could be propagated".format(parent["name"], scaled, amount))
        deltas = {}
        for name, reqs in requests.items():
            deltas[name] = sum(r["amount"] for r in reqs)
        return deltas

    @staticmethod
    def _parents(structure_name, level, applications, users):
        if level == "container":
            return [("application", a) for a in applications.values() if structure_name in a.get("containers", [])]
        if level == "application":
            return [("user", u) for u in users.values() if structure_name in u.get("clusters", [])]
        return []

    def _propagate_up(self, level, name, delta, applications, users, to_persist):
        # A budget set directly on a structure also changes the budget of its ancestors, so that the
        # downward propagation keeps it instead of reverting it
        for parent_level, parent in self._parents(name, level, applications, users):
            if self._energy(parent, "max") is None:
                continue
            parent["resources"]["energy"]["max"] += delta
            to_persist[parent["name"]] = (parent, {"resources": {"energy": {"max": parent["resources"]["energy"]["max"]}}})
            self.log_info("@{0} Budget changed by {1} W because of {2} '{3}'".format(parent["name"], delta, level, name))
            self._propagate_up(parent_level, parent["name"], delta, applications, users, to_persist)

    def compute(self, containers, applications, users, applied, usages, external):
        targets = {name: applied[name] for name in applied}
        to_persist = {}
        for name, delta in external.get("container", {}).items():
            if name in targets:
                targets[name] += delta
                self._propagate_up("container", name, delta, applications, users, to_persist)
        for name, delta in external.get("application", {}).items():
            self._propagate_up("application", name, delta, applications, users, to_persist)

        # Containers carry the usage needed by the propagation priorities
        for name, c in containers.items():
            if "energy" in c.get("resources", {}):
                c["resources"]["energy"]["usage"] = usages.get(name, {}).get("structure.energy.usage", 0)
            if name in targets:
                c["resources"]["energy"]["max"] = targets[name]

        # 1) Users -> applications
        for user in users.values():
            user_max = self._energy(user, "max")
            user_apps = [applications[a] for a in user.get("clusters", []) if a in applications]
            if user_max is None or not user_apps or any(self._energy(a, "max") is None for a in user_apps):
                continue
            diff = user_max - sum(self._energy(a, "max") for a in user_apps)
            if diff != 0:
                self.log_info("@{0} User budget {1} W differs from its applications by {2} W, propagating".format(user["name"], user_max, diff))
                for app_name, delta in self._propagate(user, applications, "max", diff, utils.propagate_user_request).items():
                    app = applications[app_name]
                    app["resources"]["energy"]["max"] += delta
                    to_persist[app_name] = (app, {"resources": {"energy": {"max": app["resources"]["energy"]["max"]}}})

        # 2) Applications -> containers
        for app in applications.values():
            app_max = self._energy(app, "max")
            app_containers = [n for n in app.get("containers", []) if n in targets]
            if app_max is None or not app_containers or len(app_containers) != len(app.get("containers", [])):
                continue
            diff = app_max - sum(targets[n] for n in app_containers)
            if diff != 0:
                self.log_info("@{0} Application budget {1} W differs from its containers by {2} W, propagating".format(app["name"], app_max, diff))
                managed = {n: containers[n] for n in app_containers}
                for name, delta in self._propagate(app, managed, "max", diff, utils.propagate_application_request).items():
                    targets[name] += delta
                    containers[name]["resources"]["energy"]["max"] = targets[name]

        return {name: b for name, b in targets.items() if b != applied.get(name)}, to_persist


BUILTIN_BUDGET_POLICIES = {"direct": DirectBudgetPolicy}


def load_budget_policy(spec, log_info, log_warning, log_error):
    if ":" in spec:
        module_name, class_name = spec.split(":", 1)
        cls = getattr(importlib.import_module(module_name), class_name)
        if not issubclass(cls, BudgetPolicy):
            raise ValueError("Budget policy '{0}' does not extend BudgetPolicy".format(spec))
    elif spec in BUILTIN_BUDGET_POLICIES:
        cls = BUILTIN_BUDGET_POLICIES[spec]
    else:
        raise ValueError("Unknown budget policy '{0}'. Built-in: {1}".format(spec, sorted(BUILTIN_BUDGET_POLICIES)))
    return cls(log_info, log_warning, log_error)
