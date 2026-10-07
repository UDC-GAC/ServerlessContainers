"""
Built-in power-capping policies of the EnergyManager: EV, TDP, PPE, MB and MO (model-only, MB without PPE).

Same decision logic as the EnergyController (events, skip conditions and CPU-power ratios), but it
works on a HostView and returns the CPU scalings instead of writing requests to CouchDB.
"""
import math
import time

from src.EnergyController.CacheUtils import EventsCache, ResourceCache
from src.EnergyManager import topology
from src.EnergyManager.controllers import Controller, ContainerView, HostView

# Capping method applied by each policy when the power model is not used (model-only: none)
BUILTIN_POLICIES = {"ev": "ev", "tdp": "tdp", "ppe-proportional": "ppe", "model-boosted": "ppe", "model-only": None}
# Policies that apply the power model of WattWizard to each new budget
MODEL_POLICIES = {"model-boosted", "model-only"}

CPU_USAGE = "structure.cpu.usage"
CPU_USER = "structure.cpu.user"
CPU_KERNEL = "structure.cpu.kernel"
CPU_WAIT = "structure.cpu.wait"
CPU_PRESSURE = "structure.cpu.pressure"
ENERGY_USAGE = "structure.energy.usage"


def resolve_cpu_target(first, predict, model_after):
    """Power model of a decision on a host: the model of the core distribution that the host will have after the
    scaling that the model itself predicts. 'first' is the model of the host now, predict(model) returns the host CPU
    target (U) that meets the host budget with a model and model_after(U) the new model of the host after scaling to U.

    Each model predicts its target and the model of the host after that target is taken, until it is the same model
    (consistent: the model of the resulting distribution has predicted that target) or one already used comes back
    (cycle: the target of each model lies in the distribution of the next one, so none is consistent and the target is
    at the frontier between their distributions, see frontier). The prediction of a model only depends on the model
    (the budget and the host load are fixed in the decision), so a model is never predicted twice: there are at most
    as many predictions as models, i.e., at most (models - 1) changes of model.

    If a prediction fails after the first one, the previous one is kept as fallback (the model of the host before it).
    Returns (model, U, {model: U} in the order of the predictions, "consistent" | "frontier" | "fallback")."""
    predictions = {}
    model = first
    while model not in predictions:
        try:
            U = predict(model)
        except Exception:
            if not predictions:
                raise
            previous = list(predictions)[-1]
            return previous, predictions[previous], predictions, "fallback"
        predictions[model] = U
        next_model = model_after(U)
        if next_model == model:
            return model, U, predictions, "consistent"
        model = next_model

    # ------------------------------------------------------------
    # Cycle: A -> B -> C -> D -> B
    # Example:
    # e.g., predictions = {A: 60, B: 50, C: 55, D: 52} and D predicts B, so model=B
    # ------------------------------------------------------------
    order = list(predictions)
    # e.g. order = [A, B, C, D]
    cycle = [predictions[m] for m in order[order.index(model):]]
    # e.g., cycle = [50, 55, 52] (B, C, and D, respectively, A is not part of the cycle)

    def within_budget(U):
        # Which model/topology we would actually obtain if we applied CPU target U
        after = model_after(U)
        # U is considered safe if:
        #   1. the resulting model is one of the models in the cycle
        #   2. that resulting model itself predicts at least U.
        # After applying U, does the resulting model still consider U to be small enough to satisfy the power budget?"
        return after in predictions and U <= predictions[after]


    # The minimum value of the cycle is guaranteed to be safe, because the other models only predicted higher U values
    # e.g.,  U = 50 -> model_after(50) = C -> C predicts 55 -> 50 <= 55 -> safe
    #
    # The maximum value is necessarily unsafe, because the other models only predicted lower U values
    # e.g., U = 55 -> model_after(55) = D -> D predicts 52 -> 55 > 52 -> unsafe
    #
    # The desired U is the largest value that results in a distribution whose power model
    # predicts at least that value (within_budget).
    U = frontier(min(cycle), max(cycle), within_budget)
    return model_after(U), U, predictions, "frontier"


def frontier(lo, hi, ok, tolerance=1):
    """Largest value of [lo, hi] for which ok holds, given ok(lo), by bisection (ok holds up to a frontier): with
    resolve_cpu_target, the largest host CPU target (within 1 share) that the model of its own distribution keeps within
    the budget."""
    if ok(hi):
        return hi
    while hi - lo > tolerance:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


class BuiltinController(Controller):

    # REACTION_TIME: maximum time (s) of data, since the last action, until scaling with the smallest errors
    # (N_max events, see get_max_events). METER_LAG, MIN_ENERGY_POINTS and POLLING_FREQUENCY (seconds of each sample)
    # are EnergyManager settings (it passes its defaults)
    # SCALE_UP_CHECK: how to know if a container would use more CPU before scaling it up
    #   boundary: CPU usage is not below the CPU quota minus its boundary (as the EnergyController)
    #   pressure: CPU pressure (share of its CPU demand waiting for a CPU) is at least PRESSURE_THRESHOLD
    # POWER_MODEL_ROUTING: MB uses the host model of WattWizard (with the prediction method of POWER_MODEL) whose core
    # distribution is closest to the CPUs that the host will have after the scaling (topology.closest_distribution).
    # Otherwise (or without topology or models), the General model, and the Single_Core model while the host would use
    # less than one CPU
    # MODEL_RELIABILITY: with 'high', MB applies a budget it has not modelled yet (a new container or a new budget)
    # with the power model in its first evaluation, without waiting for events; with 'low', as the other methods
    # (also model-only, which then keeps that CPU until the budget changes)
    CONFIG_DEFAULT_VALUES = {"ALLOWED_ERROR": 0.05, "EVENT_TIMEOUT": 30, "EVENTS_SYSTEM": "dynamic", "REACTION_TIME": 20,
                             "EV_RATIO": 5, "IDLE_POWER": 40, "POWER_MODEL": "polyreg_General",
                             "SCALE_UP_CHECK": "boundary", "PRESSURE_THRESHOLD": 0.05, "POWER_MODEL_ROUTING": True,
                             "MODEL_RELIABILITY": "low"}

    def __init__(self, ctx, name):
        super().__init__(ctx, name)
        self.policy = name
        self.events_cache = EventsCache()
        self.pb_cache = ResourceCache()
        self.budget_cache = ResourceCache()    # Budget of the events accumulated for each container
        self._idle_power = None
        self._no_pressure_warned = set()
        self._host_models = None    # Host models of WattWizard (read once: they only change if the platform is restarted)
        # Host -> model predicted for the host after the scaling of this iteration, checked with the CPUs applied
        self._model_checks = {}
        # Decision of each container in the current iteration (written to the EnergyManager trace)
        self.last_trace = {}

    def invalid_conf(self):
        if self.policy == "ev" and not self.cfg("EV_RATIO") > 0:
            return True, "EV ratio must be positive, got '{0}'".format(self.cfg("EV_RATIO"))
        if self.policy == "tdp" and (self.cfg("IDLE_POWER") is None or self.cfg("IDLE_POWER") < 0):
            return True, "Control policy is TDP, it needs a valid idle power value ({0})".format(self.cfg("IDLE_POWER"))
        if self.cfg("EVENTS_SYSTEM") not in {"dynamic", "static"}:
            return True, "Events system '{0}' is invalid".format(self.cfg("EVENTS_SYSTEM"))
        if self.cfg("MODEL_RELIABILITY") not in {"low", "high"}:
            return True, "MODEL_RELIABILITY must be 'low' or 'high', got '{0}'".format(self.cfg("MODEL_RELIABILITY"))
        if self.cfg("SCALE_UP_CHECK") not in {"boundary", "pressure"}:
            return True, "SCALE_UP_CHECK must be 'boundary' or 'pressure', got '{0}'".format(self.cfg("SCALE_UP_CHECK"))
        if not 0 <= self.cfg("PRESSURE_THRESHOLD") < 1:
            return True, "PRESSURE_THRESHOLD must be in [0, 1), got '{0}'".format(self.cfg("PRESSURE_THRESHOLD"))
        if not self.cfg("REACTION_TIME") > 0:
            return True, "REACTION_TIME must be positive, got '{0}'".format(self.cfg("REACTION_TIME"))
        if self.cfg("EVENT_TIMEOUT") < self.cfg("REACTION_TIME"):
            return True, "EVENT_TIMEOUT ({0}) must be at least REACTION_TIME ({1})".format(self.cfg("EVENT_TIMEOUT"), self.cfg("REACTION_TIME"))
        # The first decision after an action needs METER_LAG s and both windows of points
        min_reaction = self.cfg("METER_LAG") + max(self.cfg("MIN_ENERGY_POINTS"), self.cfg("MIN_CPU_POINTS")) * self.cfg("POLLING_FREQUENCY")
        if self.cfg("REACTION_TIME") < min_reaction - 1e-6:
            return True, ("REACTION_TIME ({0}) must be at least METER_LAG + max(MIN_ENERGY_POINTS, MIN_CPU_POINTS) * "
                          "POLLING_FREQUENCY ({1})".format(self.cfg("REACTION_TIME"), min_reaction))
        return False, ""

    @property
    def idle_power(self):
        if self._idle_power is None:
            self._idle_power = self.ctx.wattwizard.get_idle_consumption("host", self.cfg("POWER_MODEL"))
        return self._idle_power

    # ----------------------------------------------------------------- decision logs
    # One line per evaluated container: HOLD (no scaling, and why), WAIT (missing data), EVENTS (event added)
    # and SCALE (scaling triggered)
    def trace_decision(self, c: ContainerView, **fields):
        self.last_trace.setdefault(c.name, {}).update(fields)

    def log_decision(self, c: ContainerView, outcome, reason):
        self.trace_decision(c, outcome=outcome, reason=reason)
        P = c.usages[ENERGY_USAGE] if c.usages else float("nan")
        relation = "<" if P < c.budget else ">"
        error = (c.budget - P) / c.budget * 100 if c.budget else float("nan")
        pressure = f" | pressure {c.usages[CPU_PRESSURE]:.1%}" if c.usages and CPU_PRESSURE in c.usages else ""
        self.ctx.log_info(f"@{c.name} {outcome} ({reason}) | P {P:.2f} W {relation} B {c.budget:.1f} W (error {error:+.1f} %)"
                          f" | quota {c.cpu_alloc}{pressure}")

    # ----------------------------------------------------------------- skip conditions
    def power_is_near_pb(self, c: ContainerView, value):
        allowed_error = self.cfg("ALLOWED_ERROR")
        upper_limit, lower_limit = c.budget * (1 + allowed_error / 2), c.budget * (1 - allowed_error / 2)
        is_near = lower_limit < value < upper_limit
        if is_near:
            self.log_decision(c, "HOLD", f"near budget: {lower_limit:.2f} < P < {upper_limit:.2f} W")
        return is_near

    def error_is_below_potential_pb(self, c: ContainerView, value):
        P_max = c.structure["resources"]["energy"]["max"]
        is_below = c.budget < value < P_max
        if is_below:
            self.log_decision(c, "HOLD", f"above budget but below energy max {P_max} W")
        return is_below

    def cpu_is_below_boundary(self, c: ContainerView, value):
        cpu_limits = c.limits.get("resources", {}).get("cpu", {})
        if "boundary" not in cpu_limits:
            return False
        ref_field = cpu_limits["boundary_type"].split("_")[-1]  # e.g., percentage_of_max -> max
        margin = int(c.structure["resources"]["cpu"][ref_field] * cpu_limits["boundary"] / 100)
        is_below = value < (c.cpu_alloc - margin)
        if is_below:
            self.log_decision(c, "HOLD", f"CPU usage below boundary: usage {value:.0f} < {c.cpu_alloc - margin}"
                                         f" = quota {c.cpu_alloc} - boundary {margin}")
        return is_below

    def cpu_pressure_is_low(self, c: ContainerView):
        threshold = self.cfg("PRESSURE_THRESHOLD")
        pressure = c.usages[CPU_PRESSURE]
        is_low = pressure < threshold
        if is_low:
            self.log_decision(c, "HOLD", f"CPU pressure below threshold: {pressure:.1%} < {threshold:.1%} (wait "
                                         f"{c.usages[CPU_WAIT]:.0f}, usage {c.usages[CPU_USAGE]:.0f} shares)")
        return is_low

    def would_not_use_more_cpu(self, c: ContainerView):
        if self.cfg("SCALE_UP_CHECK") == "pressure":
            if CPU_PRESSURE in c.usages:
                return self.cpu_pressure_is_low(c)
            # Without CPU wait points (e.g., atop instead of lite_feeder), the CPU boundary is checked instead
            if c.name not in self._no_pressure_warned:
                self._no_pressure_warned.add(c.name)
                self.ctx.log_warning(f"@{c.name} No CPU wait points (proc.cpu.wait, sent by lite_feeder): checking "
                                     f"the CPU boundary instead of the CPU pressure")
        return self.cpu_is_below_boundary(c, c.usages[CPU_USAGE])

    # ----------------------------------------------------------------- events
    def reset_events_if_budget_changed(self, c: ContainerView):
        # Events accumulated with a previous power budget do not apply to the new one
        _id = c.structure["_id"]
        previous = self.budget_cache.get(_id)
        self.budget_cache.add(_id, c.budget)
        if previous is not None and previous != c.budget:
            up, down = self.events_cache.get_events(_id, "up"), self.events_cache.get_events(_id, "down")
            self.events_cache.clear_events(_id)
            if up or down:
                self.ctx.log_info(f"@{c.name} EVENTS reset: power budget {previous:.1f} -> {c.budget:.1f} W "
                                  f"(discarded DOWN {down} | UP {up})")

    def compute_power_scaling(self, c: ContainerView):
        self.reset_events_if_budget_changed(c)
        P_usage = c.usages[ENERGY_USAGE]
        if c.budget == 0:
            self.log_decision(c, "HOLD", "power budget is zero")
            return 0

        P_scaling = c.budget - P_usage
        abs_ppe = abs(P_scaling / c.budget)
        direction, opposite = ("up", "down") if P_scaling > 0 else ("down", "up")
        allowed_error = self.cfg("ALLOWED_ERROR")

        # The power model is trusted: a budget not modelled yet is applied right away (MB uses the model for it)
        if self.policy in MODEL_POLICIES and self.cfg("MODEL_RELIABILITY") == "high" and self.pb_cache.is_new(c.structure["_id"], c.budget):
            self.log_decision(c, f"SCALE {direction}", f"new budget with {self.policy} and high model reliability: power model used without events")
            return P_scaling

        # Open loop: once the power model has set the CPU for this budget, model-only does not correct it
        if BUILTIN_POLICIES[self.policy] is None and not self.pb_cache.is_new(c.structure["_id"], c.budget):
            self.log_decision(c, "HOLD", "model-only: budget already applied with the power model (open loop)")
            return 0

        if self.power_is_near_pb(c, P_usage):
            return 0

        if self.error_is_below_potential_pb(c, P_usage):
            return 0

        # Scaling up is only useful if the container is limited by its CPU quota
        if P_scaling > 0 and self.would_not_use_more_cpu(c):
            return 0

        # One event per new sample showing the error in the same direction (several may arrive in the same query)
        new_events = max(1, self.count_new_events(c, P_scaling))
        self.events_cache.add_event(c.structure["_id"], direction, new_events)

        N_max = self.get_max_events()
        required_events = N_max
        if self.cfg("EVENTS_SYSTEM") == "dynamic":
            # Higher error requires fewer consecutive events to trigger scaling
            N_min, alpha = 1, 1
            required_events = N_max * (allowed_error / abs_ppe) ** alpha
            required_events = max(min(math.ceil(required_events), N_max), N_min)

        self.events_cache.keep_last_n_events(c.structure["_id"], required_events)
        dir_events = self.events_cache.get_events(c.structure["_id"], direction)
        op_events = self.events_cache.get_events(c.structure["_id"], opposite)
        up_events, down_events = (dir_events, op_events) if direction == "up" else (op_events, dir_events)
        self.ctx.log_info(f"@{c.name} EVENTS: DOWN {down_events} | UP {up_events} | REQUIRED {required_events} "
                          f"(N_max {N_max}, +{new_events} of {len(c.new_samples)} new samples) ({direction})")
        self.trace_decision(c, outcome="EVENTS", direction=direction, up=up_events, down=down_events,
                            required=required_events, n_max=N_max, new_events=new_events)

        if dir_events >= required_events:
            self.events_cache.clear_events(c.structure["_id"])
            self.log_decision(c, f"SCALE {direction}", f"{dir_events}/{required_events} events")
            return P_scaling

        return 0

    def count_new_events(self, c: ContainerView, P_scaling):
        # A new sample is an event if its own window mean is outside the budget band, on the same side as now
        half_band = c.budget * self.cfg("ALLOWED_ERROR") / 2
        return sum(1 for P in c.new_samples if abs(c.budget - P) >= half_band and (c.budget - P) * P_scaling > 0)

    def get_max_events(self):
        # REACTION_TIME = METER_LAG + (MIN_ENERGY_POINTS - 1) * T + N_max * T (T = POLLING_FREQUENCY), i.e., the
        # seconds skipped after the action, the samples that only fill the first window (the one completing it is
        # already an event) and one sample per event. E.g., 20 s, 1 s of lag and windows of 3 points: 1 + 2 + 17 events
        R, L, M, T = (self.cfg(k) for k in ("REACTION_TIME", "METER_LAG", "MIN_ENERGY_POINTS", "POLLING_FREQUENCY"))
        return max(1, int((R - (M - 1) * T - L) / T + 1e-6))

    # ----------------------------------------------------------------- capping methods
    def print_scaling_info(self, name, P_usage, P_budget, U_alloc, U_alloc_new):
        self.ctx.log_info(f"@{name} POWER {P_usage} -> {P_budget} | CPU {U_alloc} -> {U_alloc_new}")

    @staticmethod
    def cap_scaling(c: ContainerView, U_scaling):
        U_max, U_min = c.structure["resources"]["cpu"]["max"], c.structure["resources"]["cpu"]["min"]
        return max(min(U_scaling, U_max - c.cpu_alloc), - (c.cpu_alloc - U_min))

    def available_host_models(self):
        """Host models of WattWizard, read once (if WattWizard cannot be reached, it is tried again next time)."""
        if not self._host_models:
            try:
                self._host_models = list(self.ctx.wattwizard.get_models_structure("host") or [])
            except Exception as e:
                self.ctx.log_warning(f"Cannot get the list of WattWizard models: {e}")
                return []
        return self._host_models

    def host_models(self):
        """Host models of WattWizard with the prediction method of POWER_MODEL, by core distribution (e.g.,
        polyreg_Group_P_and_L -> Group_P_and_L). With several methods (e.g., polyreg,sgdregressor), Group_PP_LL would
        map to any of them."""
        method = self.cfg("POWER_MODEL").split("_")[0]
        return {topology.normalize_distribution(m[len(method) + 1:]): m for m in self.available_host_models()
                if m.split("_")[0] == method and "iomix" not in m}

    def model_router(self, view: HostView):
        """Routing of the host models: route(host CPUs, host CPU usage) -> (model, description).
        - With POWER_MODEL_ROUTING, the model of the core distribution closest to those CPUs (topology.closest_distribution).
        - Without routing, the General model, or the Single_Core model depending on CPU usage.
        Also returns the topology of the host, None if the CPUs do not matter."""
        method = self.cfg("POWER_MODEL").split("_")[0]
        raw_topology = view.extra.get("cpu_topology")
        models = self.host_models() if self.cfg("POWER_MODEL_ROUTING") and raw_topology else {}
        topo = topology.parse(raw_topology) if models else None

        def route(cpus, U_usage_host):
            default = f"{method}_Single_Core" if U_usage_host < 100 else f"{method}_General"
            if topo is None:
                return default, f"host CPU usage {U_usage_host:.1f}"
            distribution, distance, distances = topology.closest_distribution(topo, cpus, models)
            if distribution is None:
                return default, f"host CPUs {topo.describe(cpus)}, no model of a known core distribution"
            others = ", ".join(f"{d} {v}" for d, v in sorted(distances.items(), key=lambda i: i[1]) if d != distribution)
            return models[distribution], (f"host CPUs {topo.describe(cpus)}, distance {distance} to {distribution}"
                                          + (f" (others: {others})" if others else ""))

        return route, topo

    def select_power_model(self, view: HostView, P_budget_host, U_user_host, U_system_host, amounts_for, other_amounts):
        """Host model and host CPU target meeting the host budget. The host CPU target is the one that meets the host budget
        using the power model of the core distribution that results after scaling to this CPU target.
        Returns (model, target, fields for the trace)."""

        # Get routing function to select the model of the host after the scaling
        route, topo = self.model_router(view)
        core_map = view.host.get("resources", {}).get("cpu", {}).get("core_usage_mapping", {})
        layout_params = None if self.cfg("CPU_LAYOUT") == "scaler" else dict(
            min_socket_share=self.cfg("MIN_SOCKET_SHARE"), min_socket_cpus=self.cfg("MIN_SOCKET_CPUS"))
        after, timing = {}, {"start": time.perf_counter(), "wattwizard": 0.0, "error": None}

        def predict(model):
            # Predict the host CPU target with time measurement
            t0 = time.perf_counter()
            try:
                return self.ctx.wattwizard.get_usage_meeting_budget("host", model, P_budget_host, user_load=U_user_host,
                                                                    system_load=U_system_host)["value"]
            except Exception as e:
                timing["error"] = e
                raise
            finally:
                timing["wattwizard"] += time.perf_counter() - t0

        def model_after(U):
            # Simulate the core distribution of the host after applying the CPU scalings of the containers required to
            # reach target U. The actuator will place them following CPU_LAYOUT (scale-downs first).
            cpus = None
            if topo is not None:
                amounts = {name: a for name, a in {**other_amounts, **amounts_for(U)}.items() if a}
                cpus = topology.host_cpus(topology.simulate_scalings(topo, core_map, amounts, layout_params))
            after[U] = route(cpus, U + U_system_host)
            return after[U][0]

        # Get first power model, using the current core distribution (before scaling)
        first, text = route(topology.host_cpus(core_map) if topo else None, U_user_host + U_system_host)
        self.ctx.log_info(f"@{view.name} POWER MODEL {first}: {text}")

        # Get the final power model and the host CPU target that meets the host budget, with the predictions of each model
        model, U_target, predictions, result = resolve_cpu_target(first, predict, model_after)

        for m, U in predictions.items():
            self.ctx.log_info(f"@{view.name} POWER MODEL {m}: host CPU {U_user_host:.0f} -> {U:.0f} for "
                              f"{P_budget_host:.1f} W | after the scaling: {after[U][1]} -> {after[U][0]}")
        total_ms, wattwizard_ms = 1000 * (time.perf_counter() - timing["start"]), 1000 * timing["wattwizard"]
        cost = f"{len(predictions)} prediction(s) in {total_ms:.1f} ms, WattWizard {wattwizard_ms:.1f} ms"
        if result == "consistent":
            self.ctx.log_info(f"@{view.name} POWER MODEL {model}: model of the host after the scaling ({cost})")
        elif result == "frontier":
            self.ctx.log_info(f"@{view.name} POWER MODEL {model}: the models alternate ({' -> '.join(predictions)}), "
                              f"so the target is the frontier between their distributions: host CPU {U_target:.0f}, "
                              f"the largest one within the budget for the model of its distribution, {after[U_target][1]}"
                              f" ({cost})")
        else:
            self.ctx.log_warning(f"@{view.name} POWER MODEL {model}: the next prediction failed ({timing['error']}), so "
                                 f"its prediction is kept ({cost})")
        if topo is not None:
            self._model_checks[view.name] = (route, model, U_target + U_system_host)
        trace = dict(power_model=model, model_predictions=[[m, round(U, 1)] for m, U in predictions.items()],
                     model_selection=result, model_target=round(U_target, 1), model_selection_ms=round(total_ms, 2),
                     wattwizard_ms=round(wattwizard_ms, 2))
        return model, U_target, trace

    def get_amounts_from_power_model(self, view: HostView, scalings, host_totals, other_amounts):
        """CPU scaling of the containers that use a power model to predict their initial CPU ({container: P_scaling}):
        the host CPU target that meets the host budget, shared across containers in proportion to their power scalings."""
        U_user_host, U_system_host, P_usage_host, P_scaling_host = host_totals
        containers = [view.containers[name] for name in scalings]
        for c in containers:
            self.pb_cache.add(c.structure["_id"], c.budget)

        # Compute desired host power budget based on current scalings
        P_budget_host = P_usage_host + P_scaling_host

        def cpu_scalings(U_target):
            # CPU scaling of each container for a host CPU target, within its CPU limits
            return {c.name: self.cap_scaling(c, (U_target - U_user_host) * scalings[c.name] / P_scaling_host) for c in containers}

        def amounts_for(U_target):
            # If we want to scale up power, avoid scaling down CPU and vice versa
            return {name: int(U) if U * scalings[name] > 0 else 0 for name, U in cpu_scalings(U_target).items()}

        try:
            power_model, U_target, trace = self.select_power_model(view, P_budget_host, U_user_host, U_system_host,
                                                                   amounts_for, other_amounts)
        except Exception as e:
            self.ctx.log_error(f"@{view.name} Error trying to get estimated CPU from power models: {e}")
            return {}

        self.print_scaling_info("host", P_usage_host, P_budget_host, U_user_host, U_target)
        for c in containers:
            U_scaling = cpu_scalings(U_target)[c.name]
            self.trace_decision(c, **trace)
            self.print_scaling_info(c.name, c.usages[ENERGY_USAGE], c.budget, c.cpu_alloc, c.cpu_alloc + U_scaling)
            if U_scaling * scalings[c.name] < 0:
                self.ctx.log_warning(f"@{c.name} MODEL CPU scaling ({U_scaling}) is not coherent with power scaling "
                                     f"({scalings[c.name]}). Setting amount to 0.")
        return amounts_for(U_target)

    def get_amount_from_ppe(self, c: ContainerView):
        U_max, U_min = c.structure["resources"]["cpu"]["max"], c.structure["resources"]["cpu"]["min"]
        error = c.budget - c.usages[ENERGY_USAGE]  # This would be + P_idle in both sides of the subtraction, so it can be omitted
        U_alloc_new = c.cpu_alloc * (1 + (error / (c.budget + self.idle_power)))
        U_alloc_new_cap = max(min(U_alloc_new, U_max), U_min)
        self.print_scaling_info(c.name, c.usages[ENERGY_USAGE], c.budget, c.cpu_alloc, U_alloc_new_cap)
        return int(U_alloc_new_cap - c.cpu_alloc)

    def get_amount_from_ratio(self, c: ContainerView, P_scaling, ratio):
        # U_alloc = U_alloc + k * (P_budget - P_usage)
        U_scaling_cap = self.cap_scaling(c, ratio * P_scaling)
        self.ctx.log_info(f"@{c.name} CPU-power ratio k = {ratio:.2f} shares/W")
        self.print_scaling_info(c.name, c.usages[ENERGY_USAGE], c.budget, c.cpu_alloc, c.cpu_alloc + U_scaling_cap)
        return int(U_scaling_cap)

    def get_tdp_ratio(self, view: HostView):
        # k = (U_max - U_idle) / (P_tdp - P_idle), with U_idle = 0, U_max being the host maximum CPU shares and
        # P_tdp the host maximum power (the host energy 'max' is the TDP of its CPUs)
        U_max_host, P_tdp_host = view.host["resources"]["cpu"]["max"], view.host["resources"]["energy"]["max"]
        if P_tdp_host <= self.cfg("IDLE_POWER"):
            raise ValueError("Host TDP ({0} W) must be higher than idle power ({1} W)".format(P_tdp_host, self.cfg("IDLE_POWER")))
        return U_max_host / (P_tdp_host - self.cfg("IDLE_POWER"))

    # ----------------------------------------------------------------- host control
    @staticmethod
    def usages_are_valid(c: ContainerView):
        # 0 W is a valid power (e.g., the power meter gives no power to a container that uses little CPU), but only
        # once the next point confirms it: a single 0 W point between others is a glitch of the power meter, and with
        # an error of 100 % a single event would scale the container
        if not c.usages:
            return False
        energy = c.usages.get(ENERGY_USAGE, 0)
        return energy > 0 or (energy == 0 and c.energy_zeros >= 2)

    def control_host(self, view: HostView):
        self.events_cache.remove_old_events(self.cfg("EVENT_TIMEOUT"))
        self._model_checks.pop(view.name, None)

        # 1) Power scaling needed by each guarded container (only with samples taken after its last action)
        scalings = {}
        for c in view.guarded():
            if not c.fresh:
                continue
            if not c.ready:
                # Energy points are there (fresh), CPU points after the last action are missing
                self.ctx.log_info(f"@{c.name} WAIT (CPU usage points after the last action: {c.cpu_points}/"
                                  f"{self.cfg('MIN_CPU_POINTS')}, energy points: {c.energy_points})")
                self.trace_decision(c, outcome="WAIT", reason="CPU usage points after the last action")
                continue
            if not self.usages_are_valid(c):
                if c.usages and c.usages.get(ENERGY_USAGE) == 0:
                    self.ctx.log_info(f"@{c.name} WAIT (0 W power point: used once the next point confirms it)")
                    self.trace_decision(c, outcome="WAIT", reason="0 W power point not confirmed yet")
                else:
                    self.ctx.log_warning(f"@{c.name} No valid usage data")
                continue
            scalings[c.name] = self.compute_power_scaling(c)

        to_scale = {name: s for name, s in scalings.items() if s != 0}
        if not to_scale:
            return {}

        # 2) Host totals (all containers with usages, as the model needs the full host load; latest CPU usage)
        with_usages = [c for c in view.containers.values() if c.usages]
        U_user_host = sum(c.usages.get(CPU_USER, 0) for c in with_usages)
        U_system_host = sum(c.usages.get(CPU_KERNEL, 0) for c in with_usages)
        P_usage_host = (view.power or {}).get("global", 0)
        P_scaling_host = sum(scalings.values())
        if view.power:
            self.ctx.log_info(f"Global consumption = {view.power['rapl']} (RAPL) - {view.power['sensor']} (sensor) = {P_usage_host} W")

        # 3) CPU scaling for each container
        amounts, modelled, methods = {}, {}, {}
        for name, P_scaling in to_scale.items():
            c = view.containers[name]
            methods[name] = BUILTIN_POLICIES[self.policy]
            # Containers that apply a power model are processed all together and separately
            if self.policy in MODEL_POLICIES and self.pb_cache.is_new(c.structure["_id"], c.budget):
                methods[name] = "modelling"
                modelled[name] = P_scaling
                continue
            try:
                if methods[name] == "ppe":
                    amounts[name] = self.get_amount_from_ppe(c)
                elif methods[name] == "ev":
                    amounts[name] = self.get_amount_from_ratio(c, P_scaling, self.cfg("EV_RATIO"))
                else:
                    amounts[name] = self.get_amount_from_ratio(c, P_scaling, self.get_tdp_ratio(view))
            except Exception as e:
                self.ctx.log_error(f"@{name} Error computing CPU scaling: {e}")
                amounts[name] = 0

        # Use the proper power model to get a host CPU prediction and distribute proportionally across container scalings
        if modelled:
            host_totals = (U_user_host, U_system_host, P_usage_host, P_scaling_host)
            amounts.update(self.get_amounts_from_power_model(view, modelled, host_totals, amounts))

        for name in to_scale:
            if amounts.get(name, 0) == 0:
                c, cpu = view.containers[name], view.containers[name].structure["resources"]["cpu"]
                self.log_decision(c, "HOLD", f"{methods[name]} computed no CPU change (quota {c.cpu_alloc}, "
                                             f"min {cpu['min']}, max {cpu['max']})")
        return {name: amount for name, amount in amounts.items() if amount != 0}

    def on_applied(self, view: HostView, applied):
        # Check if the model selected to estimate CPU allocation matches the final core distribution after the actuator
        # applied all the scalings
        check = self._model_checks.pop(view.name, None)
        if check is None or not any(applied.values()):
            return
        route, model, U_usage_host = check
        core_map = view.host.get("resources", {}).get("cpu", {}).get("core_usage_mapping", {})
        applied_model, text = route(topology.host_cpus(core_map), U_usage_host)
        for c in view.containers.values():
            if self.last_trace.get(c.name, {}).get("power_model") == model:
                self.trace_decision(c, applied_power_model=applied_model)
        if applied_model != model:
            self.ctx.log_warning(f"@{view.name} POWER MODEL {model} was predicted for the host after the scaling, but "
                                 f"with the CPUs applied it is {applied_model}: {text}")
