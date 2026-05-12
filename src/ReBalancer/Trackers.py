from cachetools import LRUCache
from threading import Lock

from enum import Enum


class BalanceType(Enum):
    CREDIT = "credit"
    DEBT = "debt"


class RebalancerTracker:

    def __init__(self):
        self._tracker = {}
        self._lock = Lock()

    def _get_balance(self, structure_id, balance_type, resource):
        with self._lock:
            return self._tracker.get(resource, {}).get(structure_id, {}).get(balance_type, 0)

    def get_credit(self, structure_id, resource):
        return self._get_balance(structure_id, BalanceType.CREDIT, resource)

    def get_debt(self, structure_id, resource):
        return self._get_balance(structure_id, BalanceType.DEBT, resource)

    def get_net_balance(self, structure_id, resource):
        # A positive number means the structure can receive, a negative number means the structure is required to donate
        return self.get_credit(structure_id, resource) - self.get_debt(structure_id, resource)

    def _record(self, structure_id, balance_type, resource, amount):
        amount = abs(amount)
        counter_type = BalanceType.CREDIT if balance_type == BalanceType.DEBT else BalanceType.DEBT
        with self._lock:
            entry = self._tracker.setdefault(resource, LRUCache(maxsize=128)).setdefault(structure_id, {BalanceType.CREDIT: 0, BalanceType.DEBT: 0})

            # First, check if there is any amount in the counterpart to compensate (credit for debt, debt for credit)
            counterpart = entry[counter_type]
            compensated = min(counterpart, amount)
            entry[counter_type] -= compensated
            amount -= compensated

            # Then, add the remaining amount
            entry[balance_type] += amount

    def record_donation(self, structure_id, resource, amount):
        self._record(structure_id, BalanceType.CREDIT, resource, amount)

    def record_reception(self, structure_id, resource, amount):
        self._record(structure_id, BalanceType.DEBT, resource, amount)

    def _remove_balance(self, structure_id, balance_type, resource, amount):
        with self._lock:
            entry = self._tracker.get(resource).get(structure_id)
            if not entry:
                raise ValueError("No tracked rebalancings for {0}".format(structure_id))

            if entry[balance_type] < amount:
                raise ValueError("Not enough {0} to reset".format(balance_type.value))

            entry[balance_type] -= amount

    def use_credit(self, structure_id, resource, amount):
        self._remove_balance(structure_id, BalanceType.CREDIT, resource, amount)

    def payoff_debt(self, structure_id, resource, amount):
        self._remove_balance(structure_id, BalanceType.DEBT, resource, amount)


class ResourcesTracker:

    def __init__(self, mandatory_fields):
        self._tracker = {}
        self._mandatory_fields = mandatory_fields

    @staticmethod
    def has_required_fields(structure, resource, required_fields):
        for field in required_fields:
            if field not in structure.get("resources", {}).get(resource, {}):
                return False
        return True

    def _record(self, structure, resources):
        data = {}
        for r in resources:
            data[r] = {"structure": {r: {}}}
            if self.has_required_fields(structure, r, self._mandatory_fields):
                for f in self._mandatory_fields:
                    # Avoid division by zero when "max" is zero
                    data[r]["structure"][r][f] = max(structure["resources"][r][f], 1e-30) if f == "max" else structure["resources"][r][f]
            else:
                return False

        self._tracker[structure["_id"]] = data
        return True

    def record_structures(self, structures, resources):
        valid_structures = []
        for structure in structures:
            if self._record(structure, resources):
                valid_structures.append(structure)
        return valid_structures

    def get_structure_data(self, structure_id):
        return self._tracker.get(structure_id, {})

    def get_structure_resource(self, structure_id, resource):
        return self._tracker.get(structure_id, {}).get(resource, {}).get("structure", {}).get(resource, {})

    def get_receiver_priority(self, structure_id, resource, field):
        data = self.get_structure_resource(structure_id, resource)
        if field == "max":
            # Structures that have usage closer to its "max" limit receive first
            return 1 - data["usage"] / data["max"]
        else:
            # Structures that have a lower "current" limit receive first
            return data["current"]

    def update_structure_resource(self, structure_id, resource, field, amount):
        value = self.get_structure_resource(structure_id, resource).get(field)
        if value is None:
            raise ValueError("Structure {0} with resource {1} and field {2} not found in tracker"
                             .format(structure_id, resource, field))

        self._tracker[structure_id][resource]["structure"][resource][field] = value + amount
