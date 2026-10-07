"""Actuator of the EnergyManager: applies CPU and energy changes to containers right away.

It reuses the container-level logic of the Scaler (ContainerPlanner.check_container_request for
limits and host free resources, ContainerRequest for the NodeRescaler call) on an in-memory DataContext.
The CPUs of a container are chosen with the host topology (topology.plan_layout, CPU_LAYOUT = topology) or
as the Scaler does (CPU_LAYOUT = scaler). Host changes (core map, free resources) are persisted to CouchDB
afterwards, outside the control path.
"""
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Thread

import src.MyUtils.MyUtils as utils
from src.EnergyManager import topology
from src.Scaler.ContainerPlanner import ContainerPlanner
from src.Scaler.ScalerUtils import ContainerRequest


class CachedTopologyContainerRequest(ContainerRequest):
    """ContainerRequest that reads the host CPU topology once instead of once per request."""

    TOPOLOGIES = topology.TOPOLOGIES
    TOPOLOGIES_LOCK = topology.TOPOLOGIES_LOCK

    def _get_cpu_topology(self, container):
        key = (container["host_rescaler_ip"], container["host_rescaler_port"])
        with self.TOPOLOGIES_LOCK:
            if key not in self.TOPOLOGIES:
                self.TOPOLOGIES[key] = super()._get_cpu_topology(container)
            return self.TOPOLOGIES[key]


class TopologyAwareContainerRequest(CachedTopologyContainerRequest):
    """ContainerRequest that chooses the CPUs of the container with topology.plan_layout when its CPU allocation
    changes (layout_params = {min_socket_share, min_socket_cpus}), instead of filling CPUs in the Scaler order.
    Only the CPUs of this container change; CPUs of other containers are only shared if there are not enough free
    CPUs (as few as possible). The Scaler logic is only used if the CPU topology of the host is not available."""

    def __init__(self, request, couchdb_handler, rescaler_session, debug=False, layout_params=None):
        super().__init__(request, couchdb_handler, rescaler_session, debug)
        self.layout_params = layout_params

    def apply_cpu_request(self, request, amount, data_context):
        if not self.layout_params:
            return super().apply_cpu_request(request, amount, data_context)
        name = request["structure"]
        try:
            topo = topology.parse(self._get_cpu_topology(request))
        except Exception as e:
            self.log_warning("@{0} CPU topology not available ({1}): CPUs chosen as the Scaler does".format(name, e))
            return super().apply_cpu_request(request, amount, data_context)

        current_cpu_limit = self._get_resource_phy_limit(data_context, name, "cpu")
        with self.host_lock:
            host_info = data_context.hosts.get(request["host"])
            core_usage_map = host_info["resources"]["cpu"]["core_usage_mapping"]
            for cpu in topo.socket_of:
                core_usage_map.setdefault(cpu, {"free": 100}).setdefault(name, 0)
            current = {cpu: m[name] for cpu, m in core_usage_map.items() if m.get(name, 0) > 0}
            target = sum(current.values()) + amount
            # The Scaler layout breaks ties in plan_layout and is logged next to the chosen one
            scaler = topology.scaler_layout(topo, core_usage_map, name, target)
            trace = []
            layout = topology.plan_layout(topo, core_usage_map, name, target, scaler=scaler, trace=trace, **self.layout_params)
            # As the Scaler, if the free shares are fewer than requested (the request is checked before against the
            # free shares of the host, so it should not happen), the container gets those it can
            applied = sum(layout.values()) - sum(current.values())
            if applied != amount:
                self.log_warning("Container {0} couldn't get as much CPU shares as intended ({1}), instead it got {2}"
                                 .format(name, amount, applied))
            # Shares move between CPUs of the container and 'free' (other containers keep theirs)
            core_map_journal = {}
            for cpu in set(current) | set(layout):
                delta = layout.get(cpu, 0) - current.get(cpu, 0)     # E.g., +100 in a new CPU, -100 in a left one
                if delta:
                    core_usage_map[cpu][name] += delta
                    core_usage_map[cpu]["free"] -= delta
                    core_map_journal[cpu] = {name: delta, "free": -delta}
            self.host_journal["core_map_journal"] = core_map_journal
            self.host_journal["delta"] = -applied
            host_info["resources"]["cpu"]["free"] -= applied
            cpu_changes = self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("cpu", {})
            cpu_changes["core_usage_mapping"] = core_usage_map
            cpu_changes["free"] = host_info["resources"]["cpu"]["free"]
            shared = topology.shared_cpus(core_usage_map, name, layout)

        old_layout, new_layout, scaler_text = topo.describe(current), topo.describe(layout), topo.describe(scaler)
        rules = topology.deciding_rules(trace)
        self.log_info("\t@{0} @cpu CPUs {1} -> {2}{3}{4}{5}".format(
            name, old_layout, new_layout, " ({0} shared with other containers)".format(len(shared)) if shared else "",
            " [rules {0}]".format(", ".join(rules)) if rules else "",
            "" if scaler_text == new_layout else " (Scaler: {0})".format(scaler_text)))
        return {"cpu": {"cpu_num": ",".join(sorted(layout, key=int)), "cpu_allowance_limit": int(current_cpu_limit + applied)}}


def merge_changes(doc, changes):
    for key, value in changes.items():
        if isinstance(value, dict):
            merge_changes(doc.setdefault(key, {}), value)
        else:
            doc[key] = value
    return doc


def compute_differences(original, updated):
    # Same as Scaler._compute_differences: numbers as deltas, other values as they are
    diff = {}
    for key, new_val in updated.items():
        if isinstance(new_val, dict) and key in original and isinstance(original[key], dict):
            sub_differences = compute_differences(original[key], new_val)
            if sub_differences:
                diff[key] = sub_differences
        elif key in original:
            if isinstance(new_val, (int, float)) and isinstance(original[key], (int, float)):
                if new_val - original[key] != 0:
                    diff[key] = new_val - original[key]
            elif new_val != original[key]:
                diff[key] = new_val
        else:
            diff[key] = new_val
    return diff


class Actuator:

    def __init__(self, couchdb_handler, rescaler_session, log_info, log_warning, log_error, debug=False):
        self.couchdb_handler = couchdb_handler
        self.rescaler_session = rescaler_session
        self.log_info, self.log_warning, self.log_error = log_info, log_warning, log_error
        self.debug = debug
        self.layout_params = None          # CPU_LAYOUT = topology: {min_socket_share, min_socket_cpus}; None: Scaler
        self.host_locks = {}
        self.host_changes = {}
        self.persist_thread = None

    # ----------------------------------------------------------------- planning (Scaler logic)
    def _plan(self, ctx, container, resource, amount, field="current"):
        request = utils.generate_request(container, amount, resource, 0, field)
        planner = ContainerPlanner(self.couchdb_handler, self.rescaler_session, ctx, self.debug)
        # Host free resources are updated when each request is executed, so no tracker is carried over
        scaled_amount = planner.check_container_request(container, ctx.container_resources[container["name"]],
                                                        request, {}, "SCALE_UP" if amount > 0 else "SCALE_DOWN", None)
        if scaled_amount != amount:
            self.log_warning("@{0} {1} scaling trimmed from {2} to {3}".format(container["name"], resource, amount, scaled_amount))
        if scaled_amount == 0 or amount * scaled_amount < 0:
            return None
        request["amount"] = int(scaled_amount)
        return request

    def _execute(self, ctx, request):
        req = TopologyAwareContainerRequest(request, self.couchdb_handler, self.rescaler_session, self.debug,
                                            layout_params=self.layout_params)
        success = req.execute(ctx, host_changes=self.host_changes, host_lock=self.host_locks.setdefault(req.host, Lock()))
        return request["structure"], (request["amount"] if success else 0)

    def _run(self, ctx, requests):
        applied = {}
        if not requests:
            return applied
        with ThreadPoolExecutor(max_workers=min(32, len(requests))) as executor:
            for name, amount in executor.map(lambda r: self._execute(ctx, r), requests):
                applied[name] = amount
        return applied

    # ----------------------------------------------------------------- public API
    def apply_cpu(self, ctx, amounts):
        """Apply CPU scalings {container: shares}. Scale-downs go first to free host shares for scale-ups.
        Returns {container: applied shares}."""
        applied = {}
        for sign in (-1, 1):
            requests = []
            for name, amount in amounts.items():
                if amount * sign > 0 and name in ctx.containers:
                    request = self._plan(ctx, ctx.containers[name], "cpu", int(amount))
                    if request:
                        requests.append(request)
            applied.update(self._run(ctx, requests))
        return applied

    def apply_energy(self, ctx, budgets):
        """Set the power budget of containers {container: W}: 'max' and 'current' (energy_limit) are both set
        to the new budget, as the Scaler does with 'max' requests. Returns {container: applied budget}."""
        applied = {}
        for sign in (-1, 1):
            requests = []
            for name, budget in budgets.items():
                container = ctx.containers[name]
                energy = container["resources"]["energy"]
                current = int(ctx.container_resources[name]["resources"]["energy"]["energy_limit"])
                amount = int(budget) - current
                if amount * sign <= 0:
                    continue
                # The new budget is the new 'max', so 'current' can reach it
                old_max, energy["max"] = energy["max"], max(int(budget), energy.get("min", 0))
                request = self._plan(ctx, container, "energy", amount)
                if request:
                    requests.append(request)
                else:
                    energy["max"] = old_max
            for name, amount in self._run(ctx, requests).items():
                new_budget = int(ctx.container_resources[name]["resources"]["energy"]["energy_limit"])
                ctx.containers[name]["resources"]["energy"]["max"] = new_budget
                applied[name] = new_budget
        return applied

    # ----------------------------------------------------------------- persistence
    def persist(self, ctx, persisted_hosts, container_changes):
        """Persist host changes (as deltas, like the Scaler) and container fields in a background thread.
        persisted_hosts holds the host documents as they are in CouchDB and is updated afterwards."""
        self.wait_persistence()
        hosts = {h: deepcopy(ctx.hosts[h]) for h in self.host_changes if h in ctx.hosts}
        # CouchDB partial updates post the whole document (changes are only merged on conflicts), so the
        # changes are applied to a copy of the document first
        container_changes = {name: (merge_changes(deepcopy(structure), changes), changes)
                             for name, (structure, changes) in container_changes.items()}
        self.host_changes = {}
        if not hosts and not container_changes:
            return

        def _persist():
            t0 = time.time()
            for hostname, host in hosts.items():
                try:
                    changes = compute_differences(persisted_hosts[hostname], host)
                    if changes:
                        self.couchdb_handler.safe_update_structure(host["_id"], changes)
                    persisted_hosts[hostname] = host
                except Exception as e:
                    self.log_error("Error persisting host {0}: {1}".format(hostname, e))
            for name, (structure, changes) in container_changes.items():
                try:
                    if structure.get("subtype") == "user":
                        self.couchdb_handler.partial_update_user(structure, changes)
                    else:
                        self.couchdb_handler.partial_update_structure(structure, changes)
                except Exception as e:
                    self.log_error("Error persisting structure {0}: {1}".format(name, e))
            self.log_info("Persisted {0} hosts and {1} structures in {2:.2f} seconds".format(len(hosts), len(container_changes), time.time() - t0))

        self.persist_thread = Thread(name="persist", target=_persist)
        self.persist_thread.start()

    def wait_persistence(self):
        if self.persist_thread and self.persist_thread.is_alive():
            self.persist_thread.join()

