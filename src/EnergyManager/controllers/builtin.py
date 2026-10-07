"""
Built-in power-capping policies of the EnergyManager: EV, TDP, PPE, MB and MO (model-only, MB without PPE).

Same decision logic as the EnergyController (events, skip conditions and CPU-power ratios), but it
works on a HostView and returns the CPU scalings instead of writing requests to CouchDB.
"""
import math

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


class BuiltinController(Controller):

    # REACTION_TIME: maximum time (s) of data, since the last action, until scaling with the smallest errors
    # (N_max events, see get_max_events). METER_LAG, MIN_ENERGY_POINTS and POLLING_FREQUENCY (seconds of each sample)
    # are EnergyManager settings (it passes its defaults)
    # SCALE_UP_CHECK: how to know if a container would use more CPU before scaling it up
    #   boundary: CPU usage is not below the CPU quota minus its boundary (as the EnergyController)
    #   pressure: CPU pressure (share of its CPU demand waiting for a CPU) is at least PRESSURE_THRESHOLD
    # POWER_MODEL_ROUTING: MB uses the host model of WattWizard (with the prediction method of POWER_MODEL) whose core
    # distribution is closest to the CPUs allocated now in the host (topology.closest_distribution). Otherwise (or
    # without topology or models), the General model, and the Single_Core model while the host uses less than one CPU
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
        self.last_trace = {}  # Decision of each container in the current iteration (written to the EnergyManager trace)

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

    def select_power_model(self, view: HostView, U_usage_host):
        """Host model for MB: the one whose core distribution is closest to the CPUs allocated in the host."""
        method = self.cfg("POWER_MODEL").split("_")[0]
        # Without routing (or a model of a known distribution): the General model, or the Single_Core model while the
        # host uses less than one CPU (the same models for any CPU, whatever its topology)
        default = f"{method}_Single_Core" if U_usage_host < 100 else f"{method}_General"
        raw_topology = view.extra.get("cpu_topology")
        if not self.cfg("POWER_MODEL_ROUTING") or not raw_topology:
            return default
        # Models of the same prediction method as POWER_MODEL, by distribution (e.g., polyreg_Group_P_and_L ->
        # Group_P_and_L). With several methods (e.g., polyreg,sgdregressor), Group_PP_LL would map to any of them
        models = {topology.normalize_distribution(m[len(method) + 1:]): m for m in self.available_host_models()
                  if m.split("_")[0] == method and "iomix" not in m}
        topo = topology.parse(raw_topology)
        core_map = view.host.get("resources", {}).get("cpu", {}).get("core_usage_mapping", {})
        cpus = [cpu for cpu, shares in core_map.items() if any(v > 0 for k, v in shares.items() if k != "free")]
        distribution, distance, distances = topology.closest_distribution(topo, cpus, models)
        if distribution is None:
            self.ctx.log_warning(f"@{view.name} No WattWizard model with a known core distribution: using {default}")
            return default
        others = ", ".join(f"{d} {v}" for d, v in sorted(distances.items(), key=lambda i: i[1]) if d != distribution)
        self.ctx.log_info(f"@{view.name} POWER MODEL {models[distribution]}: host CPUs {topo.describe(cpus)}, distance "
                          f"{distance} to {distribution}" + (f" (others: {others})" if others else ""))
        return models[distribution]

    def get_amount_from_power_model(self, c: ContainerView, P_scaling, host_totals, power_model):
        self.pb_cache.add(c.structure["_id"], c.budget)
        U_user_host, U_system_host, P_usage_host, P_scaling_host = host_totals

        # Compute desired host power budget based on current scalings
        P_budget_host = P_usage_host + P_scaling_host
        self.trace_decision(c, power_model=power_model)

        U_scaling_cap = 0
        try:
            result = self.ctx.wattwizard.get_usage_meeting_budget("host", power_model, P_budget_host, user_load=U_user_host, system_load=U_system_host)
            U_scaling_host = result["value"] - U_user_host
            U_scaling_cap = self.cap_scaling(c, U_scaling_host * (P_scaling / P_scaling_host))

            self.print_scaling_info("host", P_usage_host, P_budget_host, U_user_host, result['value'])
            self.print_scaling_info(c.name, c.usages[ENERGY_USAGE], c.budget, c.cpu_alloc, c.cpu_alloc + U_scaling_cap)

            # If we want to scale up power, avoid scaling down CPU and vice versa
            if P_scaling * U_scaling_cap < 0:
                self.ctx.log_warning(f"@{c.name} MODEL CPU scaling ({U_scaling_cap}) is not coherent with power scaling ({P_scaling}). Setting amount to 0.")
                U_scaling_cap = 0
        except Exception as e:
            self.ctx.log_error(f"@{c.name} Error trying to get estimated CPU from power models: {e}")

        return int(U_scaling_cap)

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
        amounts, power_model = {}, None
        for name, P_scaling in to_scale.items():
            c = view.containers[name]
            method = BUILTIN_POLICIES[self.policy]
            if self.policy in MODEL_POLICIES and self.pb_cache.is_new(c.structure["_id"], c.budget):
                method = "modelling"
            try:
                if method == "modelling":
                    power_model = power_model or self.select_power_model(view, U_user_host + U_system_host)
                    amount = self.get_amount_from_power_model(c, P_scaling, (U_user_host, U_system_host, P_usage_host, P_scaling_host), power_model)
                elif method == "ppe":
                    amount = self.get_amount_from_ppe(c)
                elif method == "ev":
                    amount = self.get_amount_from_ratio(c, P_scaling, self.cfg("EV_RATIO"))
                else:
                    amount = self.get_amount_from_ratio(c, P_scaling, self.get_tdp_ratio(view))
            except Exception as e:
                self.ctx.log_error(f"@{name} Error computing CPU scaling: {e}")
                amount = 0
            if amount != 0:
                amounts[name] = amount
            else:
                cpu = c.structure["resources"]["cpu"]
                self.log_decision(c, "HOLD", f"{method} computed no CPU change (quota {c.cpu_alloc}, "
                                             f"min {cpu['min']}, max {cpu['max']})")

        return amounts
