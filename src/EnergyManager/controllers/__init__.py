"""
Controller interface of the EnergyManager.

A controller receives, once per iteration and host, a HostView with the state of every container on
that host (budgets, physical CPU allocation, usages measured only after the last applied action) and
returns the CPU scaling (in shares) it wants for each container. Iterations follow the data: a container
should only be evaluated when it is 'fresh' (a new energy point has arrived) and 'ready' (energy and CPU points taken
after its last action). The EnergyManager applies these scalings immediately, so controllers never deal with requests,
CouchDB or the NodeRescaler.

Built-in controllers live in builtin.py. External controllers are loaded by name as "package.module:ClassName"
(e.g., "src.ExternalController.external_controller:ExternalControllerClass").
"""
import importlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ContainerView:
    name: str
    structure: dict                 # CouchDB document (resources.cpu.{min,max}, resources.energy.{min,max}, ...)
    limits: dict                    # CouchDB limits document (may be empty)
    guarded: bool                   # guard and energy guard are set
    cpu_alloc: int                  # Physical CPU allocation (shares)
    cpu_list: List[str]             # Physical cores assigned to the container
    budget: float                   # Power budget (W) currently applied
    usages: Optional[dict]          # {"structure.cpu.usage", "structure.cpu.user", "structure.cpu.kernel", "structure.energy.usage"}
    ready: bool                     # MIN_ENERGY_POINTS energy and MIN_CPU_POINTS CPU points taken after the last action
    last_action: float              # Timestamp of the last CPU scaling applied to this container (0 if none)
    window: float                   # Seconds covered by the energy points used
    fresh: bool = False             # A new energy point has arrived since the last decision on this container
    new_samples: List[float] = field(default_factory=list)  # Energy mean of each new sample since the last decision
                                    # (window of MIN_ENERGY_POINTS ending at it, oldest first): one event each if it shows the error
    energy_ts: Optional[int] = None # Timestamp of the last energy point in the usages
    energy_points: int = 0          # Energy points available after the last action (up to MIN_ENERGY_POINTS)
    energy_zeros: int = 0           # 0 W energy points in a row at the end of the ones taken after the last action
    cpu_points: int = 0             # CPU points available after the last action (up to MIN_CPU_POINTS)
    cpu_ts: Optional[int] = None    # Timestamp of the last CPU point used (None if there is none after the last action)
    ready_at: float = 0.0           # Only points taken from then on are used (its application has started), inf before


@dataclass
class HostView:
    name: str
    now: float
    host: dict                      # In-memory host document (resources.cpu.{max,core_usage_mapping}, ...)
    containers: Dict[str, ContainerView]
    power: Optional[dict]           # {"rapl", "sensor", "global"} (W), measured after the last action on the host
    power_ready: bool
    last_action: float              # Timestamp of the last CPU scaling applied to any container of the host
    rescaler_ip: str = ""
    rescaler_port: str = ""
    extra: dict = field(default_factory=dict)
    ready_at: float = 0.0           # Host points are only used from then on (its applications have started)

    def guarded(self):
        return [c for c in self.containers.values() if c.guarded]


class ControllerContext:
    """Shared handlers given to controllers. The WattWizard handler is created on demand."""

    def __init__(self, opentsdb_handler, couchdb_handler, log_info, log_warning, log_error, wattwizard_factory=None):
        self.opentsdb_handler = opentsdb_handler
        self.couchdb_handler = couchdb_handler
        self.log_info, self.log_warning, self.log_error = log_info, log_warning, log_error
        self._wattwizard_factory = wattwizard_factory
        self._wattwizard = None

    @property
    def wattwizard(self):
        if self._wattwizard is None and self._wattwizard_factory:
            self._wattwizard = self._wattwizard_factory()
        return self._wattwizard


class Controller:
    """Base class for EnergyManager controllers."""

    # Extra configuration keys (and default values) used by this controller
    CONFIG_DEFAULT_VALUES = {}

    def __init__(self, ctx: ControllerContext, name: str):
        self.ctx = ctx
        self.name = name
        self.config = {}

    def configure(self, config: dict):
        """Called after every configuration update with the full service configuration (upper-case keys)."""
        self.config = config

    def cfg(self, key):
        return self.config.get(key, self.CONFIG_DEFAULT_VALUES.get(key))

    def invalid_conf(self):
        return False, ""

    def control_host(self, view: HostView) -> Dict[str, int]:
        """Returns the CPU scaling (shares, positive or negative) for each container of the host."""
        raise NotImplementedError

    def on_applied(self, view: HostView, applied: Dict[str, int]):
        """Called with the scalings finally applied (they can be trimmed by host/container limits)."""
        pass

    def on_budget_changed(self, container_name: str, old_budget: float, new_budget: float):
        pass


def load_controller(spec: str, ctx: ControllerContext) -> Controller:
    """spec is a built-in policy name (see builtin.BUILTIN_POLICIES) or 'package.module:ClassName'."""
    if ":" in spec:
        module_name, class_name = spec.split(":", 1)
        cls = getattr(importlib.import_module(module_name), class_name)
        if not issubclass(cls, Controller):
            raise ValueError("Controller '{0}' does not extend Controller".format(spec))
        return cls(ctx, spec)

    from src.EnergyManager.controllers.builtin import BuiltinController, BUILTIN_POLICIES
    if spec not in BUILTIN_POLICIES:
        raise ValueError("Unknown controller '{0}'. Built-in: {1}".format(spec, sorted(BUILTIN_POLICIES)))
    return BuiltinController(ctx, spec)
