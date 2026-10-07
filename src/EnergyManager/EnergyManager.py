#!/usr/bin/python
"""


The EnergyManager merges the functionality of the ReBalancer, the EnergyController and the Scaler in a single service,
in order to reduce synchronisation overheads and avoid conflicts between them. Every iteration:

  1. State: Get structures and limits from CouchDB (every STATE_PERIOD seconds, or in the next iteration when the
     Orchestrator changes STATE_UPDATE). Host physical limits and core maps are kept in memory, as this service is
     their only writer while it is active. The Orchestrator pauses the EnergyManager to subscribe or remove containers.
     Host info is resynchronised every RESYNC_PERIOD seconds, when containers change, on STATE_UPDATE or when the
     service is activated again.
  2. Telemetry: one OpenTSDB query for all containers and hosts every POLLING_FREQUENCY seconds, keeping only
     the points not read before. A container is evaluated when a new energy point arrives, with the mean of its last
     MIN_ENERGY_POINTS energy points and MIN_CPU_POINTS CPU points, all of them taken after its last action and after
     the application is started. Both CPU and energy are expected with the same granularity. The CPU quota is the
     CPU reference; CPU usage is only used for the triggering of scaling events.
  3. Budgets: the budget policy decides the budget of each container (default: "direct", budgets set on
     users/applications are propagated to their containers in the same iteration) and applies it.
  4. Control: the controller (built-in policy or plugin) computes the CPU scaling of each container.
  5. Actuation: CPU scalings are applied right away through the NodeRescaler. The CPUs of the container are chosen
     taking into account the host topology (CPU_LAYOUT=topology) or as the Scaler does, following a predefined core
     distribution (Group_PP_LL).
  6. Persistence: host core maps and structure fields are written to CouchDB in background, while the service
     sleeps (the iteration ends when they are written).

Guardian, Scaler, ReBalancer and EnergyController must be inactive on the hosts managed by this service.
"""
from __future__ import print_function

import json
import math
import time
import traceback
from copy import deepcopy
from threading import Thread

import requests

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
import src.WattWizard.WattWizardUtils as wattwizard
from src.EnergyManager import topology
from src.EnergyManager.actuator import Actuator
from src.EnergyManager.budgets import load_budget_policy
from src.EnergyManager.controllers import ControllerContext, ContainerView, HostView, load_controller
from src.EnergyManager.telemetry import Telemetry
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Scaler.DataLoader import DataContext
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 1, "POLL_OFFSET": 0.5, "MIN_ENERGY_POINTS": 3,
                         "MIN_CPU_POINTS": 3, "METER_LAG": 1, "QUERY_LOOKBACK": 10,
                         "STATE_PERIOD": 30, "RESYNC_PERIOD": 60, "CONTROLLER": "ppe-proportional",
                         "BUDGET_POLICY": "direct", "TRACE_FILE": "energy_manager_trace.jsonl", "DEBUG": True,
                         "CPU_LAYOUT": "topology", "MIN_SOCKET_SHARE": 0.25, "MIN_SOCKET_CPUS": 2,
                         "ACTIVE": True}

# A container is evaluated with points taken from APP_START_MARGIN seconds after its application starts: Containers
# signal their start via the Orchestrator (start_wrapper.sh from ServerlessYARN)
APP_START_MARGIN = 3

LEVELS = ("container", "application", "user")


class EnergyManager(Service):

    def __init__(self):
        super().__init__("energy_manager", ConfigValidator(min_frequency=1, min_delay=0), CONFIG_DEFAULT_VALUES,
                         sleep_attr="polling_frequency")
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.rescaler_session = requests.Session()
        self.polling_frequency, self.min_energy_points, self.min_cpu_points = None, None, None
        self.meter_lag, self.query_lookback = None, None
        self.poll_offset = None
        self.cpu_layout, self.min_socket_share, self.min_socket_cpus = None, None, None
        self._topology_errors = {}         # Host -> time of the last failed reading of its CPU topology
        self.state_period, self.resync_period, self.controller, self.budget_policy, self.trace_file = None, None, None, None, None

        self.telemetry = Telemetry(self.opentsdb_handler)
        self.actuator = Actuator(self.couchdb_handler, self.rescaler_session, self.log_info, self.log_warning, self.log_error)
        self.controller_ctx = ControllerContext(self.opentsdb_handler, self.couchdb_handler, self.log_info, self.log_warning,
                                                self.log_error, wattwizard_factory=wattwizard.WattWizardUtils)
        self._controller, self._controller_spec = None, None
        self._budget_policy, self._budget_policy_spec = None, None

        self.ctx = DataContext()           # In-memory state: containers, hosts and physical limits
        self.persisted_hosts = {}          # Host documents as they are in CouchDB
        self.limits = {}
        self.seen = {level: {} for level in LEVELS}   # Last budget known to be in CouchDB for each structure
        self.last_action = {}              # Container -> timestamp of the last applied CPU scaling
        self.container_ids = {}            # Container -> CouchDB _id (names are reused by new containers)
        self.last_eval_ts = {}             # Container -> timestamp of the last energy point used in a decision
        self.app_started = {}              # Container -> start of its application ('app_started'), once known
        self.last_state_load, self.last_resync = 0, 0
        self.applications, self.users = {}, {}
        self.state_update, self._state_update_seen, self._state_update_pending = None, "unset", False
        self._was_active = None
        self._printed_config = None

    # ----------------------------------------------------------------- configuration
    def on_config_updated(self, service_config):
        config = service_config.get_config()
        # STATE_UPDATE is changed by the Orchestrator (e.g., budgets set through its API): reload the state now.
        # The value found at start is only remembered (the state is loaded in the first iteration anyway)
        state_update = config.get("STATE_UPDATE")
        if state_update != self._state_update_seen:
            self._state_update_pending = self._state_update_seen != "unset"
            self._state_update_seen = state_update
        # While inactive (e.g., paused by the Orchestrator to change a host) its in-memory state may have become
        # stale: it is reloaded when the service is activated again
        if self.active and self._was_active is False:
            self._state_update_pending = True
        self._was_active = self.active
        try:
            if self.controller != self._controller_spec:
                self._controller = load_controller(self.controller, self.controller_ctx)
                self._controller_spec = self.controller
                self.log_info("Loaded controller '{0}'".format(self.controller))
            # Controllers also read service settings (e.g., METER_LAG, MIN_ENERGY_POINTS for N_max)
            self._controller.configure({**CONFIG_DEFAULT_VALUES, **config})
        except Exception as e:
            self._controller, self._controller_spec = None, None
            self.log_error("Cannot load controller '{0}': {1}".format(self.controller, e))
        try:
            if self.budget_policy != self._budget_policy_spec:
                self._budget_policy = load_budget_policy(self.budget_policy, self.log_info, self.log_warning, self.log_error)
                self._budget_policy_spec = self.budget_policy
            self._budget_policy.configure(config)
        except Exception as e:
            self._budget_policy, self._budget_policy_spec = None, None
            self.log_error("Cannot load budget policy '{0}': {1}".format(self.budget_policy, e))
        self.actuator.debug = self.debug
        self.actuator.layout_params = dict(min_socket_share=self.min_socket_share, min_socket_cpus=self.min_socket_cpus) \
            if self.cpu_layout == "topology" else None

    def invalid_conf(self, service_config):
        if self._controller is None:
            return True, "Controller '{0}' could not be loaded".format(self.controller)
        if self._budget_policy is None:
            return True, "Budget policy '{0}' could not be loaded".format(self.budget_policy)
        if self.min_energy_points < 1 or self.min_cpu_points < 1:
            return True, "MIN_ENERGY_POINTS and MIN_CPU_POINTS must be at least 1"
        if not self.polling_frequency >= 1 or int(self.polling_frequency) != self.polling_frequency:
            return True, "POLLING_FREQUENCY must be a whole number of seconds"
        if self.query_lookback < self.polling_frequency:
            return True, "QUERY_LOOKBACK must be at least POLLING_FREQUENCY"
        if not 0 <= self.poll_offset < self.polling_frequency:
            return True, "POLL_OFFSET must be in [0, POLLING_FREQUENCY)"
        if self.cpu_layout not in {"topology", "scaler"}:
            return True, "CPU_LAYOUT must be 'topology' or 'scaler', got '{0}'".format(self.cpu_layout)
        if not 0 <= self.min_socket_share <= 1 or self.min_socket_cpus < 1:
            return True, "MIN_SOCKET_SHARE must be in [0, 1] and MIN_SOCKET_CPUS at least 1"
        invalid, msg = self._controller.invalid_conf()
        if invalid:
            return invalid, msg
        return self.config_validator.invalid_conf(service_config)

    # ----------------------------------------------------------------- state
    @staticmethod
    def _energy_max(structure):
        return structure.get("resources", {}).get("energy", {}).get("max")

    def _load_structures(self):
        containers = utils.get_structures(self.couchdb_handler, self.debug, "container") or []
        containers = {c["name"]: c for c in containers if utils.structure_subtype_is_supported(c["subtype"])}
        applications = {a["name"]: a for a in (utils.get_structures(self.couchdb_handler, self.debug, "application") or [])}
        users = {u["name"]: u for u in (utils.get_structures(self.couchdb_handler, self.debug, "user") or [])}
        return containers, applications, users

    @staticmethod
    def _is_guarded(c):
        return c.get("guard", False) and c.get("resources", {}).get("energy", {}).get("guard", False)

    def _resync(self, containers, hosts):
        t0 = time.time()
        host_docs = {h["name"]: h for h in (utils.get_structures(self.couchdb_handler, self.debug, "host") or []) if h["name"] in hosts}
        phys = utils.get_container_physical_resources(list(containers.values()), {"cpu", "energy"}, self.rescaler_session, self.debug)
        self.ctx = DataContext(container=containers, host=host_docs, container_resources=phys)
        self.persisted_hosts = deepcopy(host_docs)
        self.limits = {l["name"]: l for l in (self.couchdb_handler.get_all_limits() or [])}
        self.log_info("State resynchronised ({0} hosts, {1} containers) in {2:.2f} seconds".format(len(host_docs), len(containers), time.time() - t0))

    def _print_config(self, service_config):
        # This service iterates every second: the configuration is only printed when it changes
        config = dict(service_config.get_config())
        if config != self._printed_config:
            super()._print_config(service_config)
            self._printed_config = config

    def forget_container(self, name):
        self.app_started.pop(name, None)
        self.seen["container"].pop(name, None)
        self.last_action.pop(name, None)
        self.last_eval_ts.pop(name, None)
        self.telemetry.forget(name)

    def check_app_started(self, containers):
        # The Orchestrator notifies the start of an application (STATE_UPDATE), so it is known within 1-2 s
        for name, c in containers.items():
            started = c.get("app_started")
            if started is not None and self.app_started.get(name) != started:
                self.app_started[name] = started
                self.log_info("@{0} Application started at {1}: evaluated with points taken from {2} on".format(
                    name, time.strftime("%H:%M:%S", time.localtime(started)),
                    time.strftime("%H:%M:%S", time.localtime(started + APP_START_MARGIN))))

    def ready_at(self, name):
        # Points taken before are not used (inf until its application starts)
        started = self.app_started.get(name)
        return math.inf if started is None else started + APP_START_MARGIN

    def load_state(self, now, force_resync=False):
        containers, applications, users = self._load_structures()
        guarded = {n: c for n, c in containers.items() if self._is_guarded(c)}
        hosts = {c["host"] for c in guarded.values()}
        # All the containers on the managed hosts are kept (the model needs the full host load)
        containers = {n: c for n, c in containers.items() if c["host"] in hosts}

        container_ids = {n: c["_id"] for n, c in containers.items()}
        must_resync = (force_resync or now - self.last_resync >= self.resync_period or container_ids != self.container_ids
                       or set(hosts) != set(self.ctx.hosts))
        if must_resync:
            self._resync(containers, hosts)
            self.last_resync = now
            # Forget removed containers and start new ones (maybe reusing a name) with a clean state
            for name in set(self.container_ids) | set(container_ids):
                if self.container_ids.get(name) != container_ids.get(name):
                    self.forget_container(name)
                    if name in container_ids and "app_started" not in containers[name]:
                        self.log_info("@{0} New container: evaluated once its application starts".format(name))
            self.container_ids = container_ids
            for name in containers:
                self.seen["container"].setdefault(name, self.applied_budget(name))
        else:
            # Refresh structure documents, physical limits stay as known by this service
            self.ctx.containers.update(containers)
        self.check_app_started(containers)
        for level, structures in (("application", applications), ("user", users)):
            for name, s in structures.items():
                self.seen[level].setdefault(name, self._energy_max(s))
        return applications, users

    def applied_budget(self, name):
        try:
            return int(self.ctx.container_resources[name]["resources"]["energy"]["energy_limit"])
        except (KeyError, TypeError, ValueError):
            return None

    def detect_external_changes(self, applications, users):
        # Budget changes made in CouchDB by the user (e.g., through the Orchestrator) since last iteration
        external = {level: {} for level in LEVELS}
        for level, structures in (("container", self.ctx.containers), ("application", applications), ("user", users)):
            for name, s in structures.items():
                value, seen = self._energy_max(s), self.seen[level].get(name)
                if value is not None and seen is not None and value != seen:
                    external[level][name] = value - seen
                    self.log_info("@{0} Budget changed externally: {1} -> {2} W".format(name, seen, value))
                self.seen[level][name] = value
        return external

    # ----------------------------------------------------------------- iteration phases
    def update_budgets(self, applications, users, usages):
        applied = {n: self.applied_budget(n) for n, c in self.ctx.containers.items()
                   if "energy" in c.get("resources", {}) and self.applied_budget(n) is not None}
        external = self.detect_external_changes(applications, users)
        # The policy works on copies of the containers (it may add fields needed for its decisions)
        new_budgets, to_persist = self._budget_policy.compute(deepcopy(self.ctx.containers), applications, users,
                                                              applied, usages, external)
        applied_budgets = {}
        if new_budgets:
            applied_budgets = self.actuator.apply_energy(self.ctx, new_budgets)
            for name, budget in applied_budgets.items():
                self.log_info("@{0} Power budget {1} -> {2} W".format(name, applied[name], budget))
                self._controller.on_budget_changed(name, applied[name], budget)
            for name in new_budgets:
                budget = self.applied_budget(name)
                self.ctx.containers[name]["resources"]["energy"]["max"] = budget
                to_persist[name] = (self.ctx.containers[name], {"resources": {"energy": {"max": budget, "current": budget}}})
        for name, (structure, _) in to_persist.items():
            if structure.get("subtype") in LEVELS:
                self.seen[structure["subtype"]][name] = self._energy_max(structure)
        return applied_budgets, to_persist

    def build_views(self, now):
        views, usages = {}, {}
        for hostname, host in self.ctx.hosts.items():
            host_containers = {n: c for n, c in self.ctx.containers.items() if c["host"] == hostname}
            host_last_action = max([self.last_action.get(n, 0) for n in host_containers] or [0])
            # Points of the host taken before its applications start are not used either (containers whose application
            # has not started yet are idle and do not delay it)
            host_ready = max([r for r in map(self.ready_at, host_containers) if r < math.inf] or [0])
            cviews = {}
            for name, c in host_containers.items():
                phys_cpu = self.ctx.container_resources.get(name, {}).get("resources", {}).get("cpu", {})
                last = self.last_action.get(name, 0)
                # Points taken after its last action (and after its application started)
                since = max(last + self.meter_lag, self.ready_at(name))
                c_usages, info = self.telemetry.container_usages(name, since, self.min_energy_points, self.min_cpu_points)
                # Budget decisions do not depend on the last CPU scaling: latest points, even before the action
                energy_points = self.telemetry.points_since(name, "structure.energy.usage", 0)[-self.min_energy_points:]
                if energy_points:
                    usages[name] = {"structure.energy.usage": sum(v for _, v in energy_points) / len(energy_points)}
                window = (info["last_ts"] - info["first_ts"] + self.polling_frequency) if info["last_ts"] is not None else 0
                # New samples since the last decision (several may arrive in the same query): energy mean of the window
                # of MIN_ENERGY_POINTS ending at each one, as if each sample had been evaluated when it arrived
                post = self.telemetry.points_since(name, "structure.energy.usage", since)
                n, last_eval = self.min_energy_points, self.last_eval_ts.get(name, -1)
                new_samples = [sum(v for _, v in post[i - n + 1:i + 1]) / n for i in range(n - 1, len(post)) if post[i][0] > last_eval]
                energy_zeros = next((i for i, (_, v) in enumerate(reversed(post)) if v != 0), len(post))
                cviews[name] = ContainerView(
                    name=name, structure=c, limits=self.limits.get(name, {}), guarded=self._is_guarded(c),
                    cpu_alloc=int(phys_cpu.get("cpu_allowance_limit", c["resources"]["cpu"]["current"])),
                    cpu_list=utils.get_cpu_list(phys_cpu["cpu_num"]) if phys_cpu.get("cpu_num") else [],
                    budget=float(self.applied_budget(name) or 0), usages=c_usages, ready=c_usages is not None,
                    last_action=last, window=window,
                    fresh=info["last_ts"] is not None and info["last_ts"] > self.last_eval_ts.get(name, -1),
                    new_samples=new_samples, energy_ts=info["last_ts"],
                    energy_points=info["energy_points"], energy_zeros=energy_zeros, cpu_points=info["cpu_points"], cpu_ts=info["cpu_ts"],
                    ready_at=self.ready_at(name))
            power, _ = self.telemetry.host_power(hostname, max(host_last_action + self.meter_lag, host_ready), self.min_energy_points)
            any_c = next(iter(host_containers.values()), {})
            views[hostname] = HostView(name=hostname, now=now, host=host, containers=cviews, power=power,
                                       power_ready=power is not None, last_action=host_last_action,
                                       rescaler_ip=any_c.get("host_rescaler_ip", ""), rescaler_port=any_c.get("host_rescaler_port", ""),
                                       extra={"telemetry": self.telemetry, "cpu_topology": self.host_topology(hostname, any_c)},
                                       ready_at=host_ready)
        return views, usages

    def host_topology(self, hostname, container):
        """CPU topology of the host (read once from its NodeRescaler, retried every RESYNC_PERIOD seconds if it
        fails), None if it is not available."""
        if not container or time.time() - self._topology_errors.get(hostname, 0) < self.resync_period:
            return None
        try:
            return topology.get_host_topology(self.rescaler_session, container["host_rescaler_ip"], container["host_rescaler_port"])
        except Exception as e:
            self._topology_errors[hostname] = time.time()
            self.log_warning("@{0} Cannot read the CPU topology from its NodeRescaler: {1}".format(hostname, e))
            return None

    def register_decisions(self, views):
        # Containers evaluated in this iteration: remember the last point used
        for view in views.values():
            for name, cv in view.containers.items():
                if cv.ready and cv.fresh:
                    self.last_eval_ts[name] = cv.energy_ts

    def refresh_budgets_in_views(self, views):
        for view in views.values():
            for name, cv in view.containers.items():
                cv.budget = float(self.applied_budget(name) or 0)

    def control(self, views):
        amounts = {}

        def _control_host(view):
            try:
                amounts.update(self._controller.control_host(view) or {})
            except Exception as e:
                self.log_error("@{0} Controller error: {1} {2}".format(view.name, e, traceback.format_exc()))

        threads = [Thread(target=_control_host, args=(v,)) for v in views.values()]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return amounts

    def log_missing_points(self, updated, now):
        missing = self.telemetry.missing(list(self.ctx.containers), updated, now)
        if not missing:
            return
        hms = lambda ts: time.strftime("%H:%M:%S", time.localtime(ts))
        fmt = lambda last, age: "never" if last is None else "last {0}, {1:.1f} s old".format(hms(last), age)
        self.log_info("No new points in query [{0}, {1}]: {2}".format(
            hms(self.telemetry.last_query[0]), hms(self.telemetry.last_query[1]),
            " | ".join("{0} {1} ({2})".format(name, label, fmt(last, age)) for name, label, last, age in missing)))

    def write_trace(self, entry):
        if not self.trace_file:
            return
        try:
            with open(self.trace_file, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError as e:
            self.log_warning("Cannot write trace: {0}".format(e))

    # ----------------------------------------------------------------- main loop
    def work(self):
        t = {"start": time.time()}
        try:
            # Previous persistence must be finished so CouchDB reflects this service's own changes
            self.actuator.wait_persistence()
            state_update, self._state_update_pending = self._state_update_pending, False
            state_loaded = state_update or t["start"] - self.last_state_load >= self.state_period
            if state_loaded:
                if state_update:
                    self.log_info("State update requested (STATE_UPDATE), reloading state")
                self.applications, self.users = self.load_state(t["start"], force_resync=state_update)
                self.last_state_load = t["start"]
            if not self.ctx.hosts:
                self.log_info("No structure has energy guarded, skipping")
                return None
            t["state"] = time.time()

            names = list(self.ctx.containers) + ["{0}-{1}".format(h, s) for h in self.ctx.hosts for s in ("rapl", "sensor")]
            updated = self.telemetry.poll(names, self.query_lookback, int(self.polling_frequency))
            now = time.time()
            self.log_missing_points(updated, now)
            views, usages = self.build_views(now)
            t["telemetry"] = time.time()

            applied_budgets, to_persist = {}, {}
            if state_loaded:
                applied_budgets, to_persist = self.update_budgets(self.applications, self.users, usages)
                if applied_budgets:
                    self.refresh_budgets_in_views(views)
            t["budgets"] = time.time()

            # Only hosts with new data are controlled (decisions traced by the controller are for this iteration)
            if isinstance(getattr(self._controller, "last_trace", None), dict):
                self._controller.last_trace.clear()
            views_to_control = {h: v for h, v in views.items() if any(c.fresh and c.ready for c in v.containers.values())}
            amounts = self.control(views_to_control) if views_to_control else {}
            self.register_decisions(views_to_control)
            t["control"] = time.time()

            applied = self.actuator.apply_cpu(self.ctx, amounts) if amounts else {}
            t_applied = time.time()
            for name, amount in applied.items():
                if amount != 0:
                    self.last_action[name] = t_applied
                    new_alloc = int(self.ctx.container_resources[name]["resources"]["cpu"]["cpu_allowance_limit"])
                    self.ctx.containers[name]["resources"]["cpu"]["current"] = new_alloc
                    changes = to_persist.get(name, (self.ctx.containers[name], {}))[1]
                    changes.setdefault("resources", {})["cpu"] = {"current": new_alloc}
                    to_persist[name] = (self.ctx.containers[name], changes)
            for view in views_to_control.values():
                host_applied = {n: a for n, a in applied.items() if n in view.containers}
                self._controller.on_applied(view, host_applied)
            t["actuation"] = time.time()

            self.actuator.persist(self.ctx, self.persisted_hosts, to_persist)

            if views_to_control or applied_budgets:
                self.log_info("Iteration: state {0:.2f}s | telemetry {1:.2f}s (query {2:.2f}s) | budgets {3:.2f}s | "
                              "control {4:.2f}s | actuation {5:.2f}s".format(
                                  t["state"] - t["start"], t["telemetry"] - t["state"], self.telemetry.query_time,
                                  t["budgets"] - t["telemetry"], t["control"] - t["budgets"], t["actuation"] - t["control"]))
                self.write_trace(dict(
                    ts=t["start"], controller=self.controller, budget_policy=self.budget_policy,
                    timings={k: round(v - t["start"], 4) for k, v in t.items() if k != "start"},
                    query_time=round(self.telemetry.query_time, 4), budgets=applied_budgets, requested=amounts, applied=applied,
                    controller_trace=getattr(self._controller, "last_trace", None),
                    hosts={h: dict(power=v.power, containers={
                        n: dict(budget=cv.budget, cpu_alloc=cv.cpu_alloc, usages=cv.usages, ready=cv.ready, fresh=cv.fresh,
                                energy_ts=cv.energy_ts, window=cv.window, new_samples=len(cv.new_samples),
                                guarded=cv.guarded) for n, cv in v.containers.items()})
                           for h, v in views.items()}))
        except Exception as e:
            self.log_error("Error in iteration: {0} {1}".format(e, traceback.format_exc()))
        # The loop waits for the persistence (while sleeping) before the next iteration and its heartbeat, so an
        # iteration only ends once its changes are in CouchDB (the Orchestrator relies on it to pause this service)
        return self.actuator.persist_thread

    def compute_sleep_time(self):
        # Wake up POLL_OFFSET seconds after each period boundary (e.g., at x.5 s), so the point of the previous
        # second has usually been ingested by OpenTSDB when it is queried. With periods of T > 1 s, the period that has
        # just ended is read (e.g., T = 3 s: at 12.5 s, the points of seconds 9 to 11), so its last point has had 1 s
        # more: a late point would not leave a missing sample, as with T = 1 s, but a partial one
        return self.polling_frequency - ((time.time() - self.poll_offset) % self.polling_frequency)

    def manage(self):
        self.run_loop()


def main():
    try:
        EnergyManager().manage()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
