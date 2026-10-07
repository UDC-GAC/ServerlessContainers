"""
CPU topology of the hosts for the EnergyManager: core layout of the containers and power model routing.

The NodeRescaler gives the topology of a host (/host/cpu_topology) as {socket: {core id: [CPUs]}}: the first CPU of
a core is its physical core and the rest are its SMT siblings. It is read once per host and used for:

1) Core layout (plan_layout). The Scaler always fills CPUs in the same order (Group_PP_LL: physical cores of every
   socket, then their siblings), so a container with 17 CPUs in a host with 16 cores per socket gets 16 CPUs in one
   socket and 1 alone in the other, whose threads slow down the rest (e.g., FT with 32 threads could not use its CPU
   and was never scaled up). When the CPU allocation of a container changes, the EnergyManager chooses its CPUs with
   the rules of LAYOUT_RULES, in order of priority. Only the layout of that container changes (other containers keep
   their shares); the scaling is only rejected if the host has not enough free shares (checked before, as the Scaler).

2) Power model routing (closest_distribution). The WattWizard models of the host are trained stressing its CPUs in
   the order of a core distribution (Group_PP_LL, Group_1P_2L, Spread_P_and_L... see the timestamps of WattWizard).
   The model used is the one whose distribution, with as many CPUs as those allocated now in the host, has the most
   similar shape: CPUs per socket and SMT siblings used (so the ids of the CPUs and sockets do not matter).
"""
import math
from threading import Lock

# ----------------------------------------------------------------- topology

TOPOLOGIES = {}          # (NodeRescaler IP, port) -> Topologies read from the NodeRescaler
TOPOLOGIES_LOCK = Lock()


def get_host_topology(rescaler_session, rescaler_ip, rescaler_port):
    """Topology of a host from its NodeRescaler, read only once."""
    key = (rescaler_ip, rescaler_port)
    with TOPOLOGIES_LOCK:
        if key not in TOPOLOGIES:
            r = rescaler_session.get("http://{0}:{1}/host/cpu_topology".format(rescaler_ip, rescaler_port),
                                     headers={'Accept': 'application/json'}, timeout=5)
            r.raise_for_status()
            TOPOLOGIES[key] = dict(r.json())
        return TOPOLOGIES[key]


_PARSED = {}             # id(raw topology) -> (raw topology, Topology)


def parse(raw):
    """Topology of a raw topology, built only once: the raw topologies of the hosts are cached (TOPOLOGIES), so the
    same dict comes every time. The raw dict is kept with its Topology, so its id cannot be reused by another dict."""
    entry = _PARSED.get(id(raw))
    if entry is None or entry[0] is not raw:
        entry = _PARSED[id(raw)] = (raw, Topology(raw))
    return entry[1]


class Topology:
    """Sockets, physical cores and CPUs of a host. CPU ids are strings, as in the core map of the host."""

    def __init__(self, raw):
        self.sockets = []       # Socket ids, in numeric order
        self.cores = {}         # Socket -> [core], each core being a tuple of CPU ids (physical CPU first)
        self.socket_of = {}     # CPU -> socket
        self.core_of = {}       # CPU -> core
        self._orders, self._prefix_shapes = {}, {}   # Distribution -> CPU order / shapes of its prefixes
        # raw = {socket0: {core_0: [cpu_0, cpu_1,...], core_1: [cpu_2, cpu_3, ...], ...}, ...}
        for socket in sorted(raw, key=int):
            cores = sorted((tuple(str(cpu) for cpu in sorted(int(c) for c in cpus)) for cpus in raw[socket].values()), key=lambda core: int(core[0]))
            # cores = [(cpu_0, cpu_1, ...), (cpu_2, cpu_3, ...)]
            self.sockets.append(str(socket))
            self.cores[str(socket)] = cores
            for core in cores:
                for cpu in core:
                    self.socket_of[cpu] = str(socket)
                    self.core_of[cpu] = core

    def cpus_per_socket(self, cpus):
        counts = {s: 0 for s in self.sockets}
        for cpu in cpus:
            if cpu in self.socket_of:
                counts[self.socket_of[cpu]] += 1
        return counts

    def siblings_used(self, cpus):
        """SMT siblings among these CPUs: CPUs minus physical cores."""
        cpus = [cpu for cpu in cpus if cpu in self.core_of]
        return len(cpus) - len({self.core_of[cpu] for cpu in cpus})

    def describe(self, cpus):
        """E.g., 'S0:16 S1:1' or 'S0:17 (1 SMT)'."""
        counts = self.cpus_per_socket(cpus)
        smt = self.siblings_used(cpus)
        text = " ".join("S{0}:{1}".format(s, n) for s, n in counts.items() if n) or "none"
        return text + (" ({0} SMT)".format(smt) if smt else "")

    def order(self, name):
        """CPU order of a distribution in this host (distribution_order), computed once."""
        name = normalize_distribution(name)
        if name not in self._orders:
            self._orders[name] = distribution_order(self, name)
        return self._orders[name]

    def prefix_shapes(self, name):
        """Shapes of the first n CPUs of a distribution, for n = 0, 1, ..., computed once: only the CPUs of the host
        change between model selections, never the distributions."""
        name = normalize_distribution(name)
        if name not in self._prefix_shapes:
            order = self.order(name)
            self._prefix_shapes[name] = [shape(self, order[:n]) for n in range(len(order) + 1)]
        return self._prefix_shapes[name]


# ----------------------------------------------------------------- core distributions

DISTRIBUTIONS = ("Group_PP_LL", "Group_1P_2L", "Group_P_and_L", "Spread_PP_LL", "Spread_P_and_L", "Group_P", "Spread_P")
SINGLE_CORE, GENERAL = "Single_Core", "General"
ALIASES = {"Group_P&L": "Group_P_and_L", "Spread_P&L": "Spread_P_and_L"}


def normalize_distribution(name):
    return ALIASES.get(name, name)


def _interleave(lists, block):
    """Round robin over the lists taking 'block' items each time, until all of them are used."""
    # E.g., [[0, 1, 2, 3], [16, 17, 18, 19]] with block 2 -> [0, 1, 16, 17, 2, 3, 18, 19]
    result = []
    for i in range(0, max((len(items) for items in lists), default=0), block):
        for items in lists:
            result.extend(items[i:i + block])
    return result


def distribution_order(topo, name):
    """CPUs of the host in the order in which they are stressed to train WattWizard models."""
    name = normalize_distribution(name)
    # Physical cores of each socket (first CPU for a core id)
    phys = [[core[0] for core in topo.cores[s]] for s in topo.sockets] 
    # Logical cores or SMT siblings of each socket (second or next CPUs for a core id)
    siblings = [[cpu for core in topo.cores[s] for cpu in core[1:]] for s in topo.sockets]
    # Pairs of physical core (first CPU) and logical cores (next CPUs for same core id)
    pairs = [[cpu for core in topo.cores[s] for cpu in core] for s in topo.sockets]
    threads = max((len(core) for s in topo.sockets for core in topo.cores[s]), default=1)
    flat = lambda lists: [cpu for items in lists for cpu in items]
    if name == SINGLE_CORE:
        return flat(phys)[:1]
    if name == "Group_P":
        return flat(phys)
    if name == "Group_PP_LL":
        return flat(phys) + flat(siblings)
    if name == "Group_1P_2L":
        return flat(p + l for p, l in zip(phys, siblings))
    if name == "Group_P_and_L":
        return flat(pairs)
    if name == "Spread_P":
        return _interleave(phys, 2)
    if name == "Spread_PP_LL":
        return _interleave(phys, 2) + _interleave(siblings, 2)
    if name == "Spread_P_and_L":
        return _interleave(pairs, threads if threads > 1 else 2)
    raise ValueError("Unknown core distribution '{0}'".format(name))


def shape(topo, cpus):
    """Per socket, most used first: (physical cores used, SMT siblings used). E.g., CPUs 0-15 and 32 (sibling of 0)
    in the 2 x 16-core Xeon -> [(16, 1)]; CPUs 0-15 and 16 -> [(16, 0), (1, 0)]."""
    per_core = {}
    for cpu in cpus:
        if cpu in topo.core_of:
            per_core[topo.core_of[cpu]] = per_core.get(topo.core_of[cpu], 0) + 1
    per_socket = {}
    for core, n in per_core.items():
        cores, siblings = per_socket.get(topo.socket_of[core[0]], (0, 0))
        per_socket[topo.socket_of[core[0]]] = (cores + 1, siblings + n - 1)
    return sorted(per_socket.values(), key=lambda v: (-(v[0] + v[1]), -v[0]))


def shape_distance(a, b):
    # Sockets compared in order (most used first), missing ones as empty: [(16, 1)] vs [(16, 0), (1, 0)] -> 0 + 1 + 1 + 0
    n = max(len(a), len(b))
    a, b = a + [(0, 0)] * (n - len(a)), b + [(0, 0)] * (n - len(b))
    return sum(abs(x[0] - y[0]) + abs(x[1] - y[1]) for x, y in zip(a, b))


def closest_distribution(topo, cpus, available, max_relative_distance=0.25):
    """Distribution among 'available' whose first len(cpus) CPUs have the shape closest to these CPUs.
    Returns (distribution, distance, {distribution: distance}). Single_Core is only used with one CPU; General is
    used if no distribution is closer than max_relative_distance * CPUs; None if nothing can be used."""
    available = {normalize_distribution(d) for d in available}
    n, target = len(cpus), shape(topo, cpus)
    if n <= 1 and SINGLE_CORE in available:
        return SINGLE_CORE, 0, {SINGLE_CORE: 0}
    distances = {}
    for name in DISTRIBUTIONS:
        prefix_shapes = topo.prefix_shapes(name)
        # Distributions trained with fewer CPUs (e.g., only physical cores) cannot represent the host
        if name in available and len(prefix_shapes) > n:
            distances[name] = shape_distance(target, prefix_shapes[n])
    best = min(distances, key=lambda d: (distances[d], DISTRIBUTIONS.index(d))) if distances else None
    if GENERAL in available and (best is None or distances[best] > max_relative_distance * n):
        return GENERAL, distances.get(best), distances
    return best, distances.get(best), distances


# ----------------------------------------------------------------- core layout

# Rules to choose the CPUs of a container, in order of priority. Each rule is a filter: of the layouts left by the
# previous rules, it keeps those with the lowest value of its criterion (rule 5 is a condition, see _apply_rules).
# F = max(MIN_SOCKET_CPUS, MIN_SOCKET_SHARE * CPUs of the container), e.g., 5 of 17 CPUs, 6 of 24. A fragment is a
# socket with fewer than F physical cores of a container that also uses other sockets: e.g., 16 + 1 CPUs, or 16 + 6
# CPUs if the 6 are 3 physical cores and their siblings
LAYOUT_RULES = (
    ("1", "shared", "fewest CPUs shared with other containers"),
    ("2", "foreign", "fewest CPUs on physical cores of other containers"),
    ("3", "fragment", "fewest sockets with fewer than F physical cores"),
    ("4", "smt_excess", "fewest SMT siblings beyond F - 1"),
    ("5", "consolidate", "no more sockets than the fewest possible with physical cores only"),
    ("6a", "remote", "fewest CPUs moved to another socket"),
    ("6b", "sockets", "fewest sockets"),
    ("6c", "smt", "fewest SMT siblings"),
    ("6d", "local", "fewest CPUs moved within a socket"),
    ("6e", "scaler", "closest to the Scaler layout"),
)
# Criteria of each socket, added up for a layout
SOCKET_CRITERIA = ("foreign", "fragment", "smt", "remote", "sockets", "local", "scaler")


def _others(core_map, cpu, name):
    return sum(v for k, v in core_map.get(cpu, {}).items() if k not in ("free", name))


def shared_cpus(core_map, name, cpus):
    """CPUs of these with shares of other containers."""
    return [cpu for cpu in cpus if _others(core_map, cpu, name) > 0]


def scaler_layout(topo, core_map, name, target):
    """Layout {cpu: shares} that the Scaler would give (ContainerRequest.apply_cpu_request with Group_PP_LL)."""
    order = [cpu for cpu in topo.order("Group_PP_LL") if cpu in core_map]
    layout = {cpu: m.get(name, 0) for cpu, m in core_map.items() if m.get(name, 0) > 0}
    amount = target - sum(layout.values())
    if amount > 0:
        free = {cpu: core_map[cpu].get("free", 0) for cpu in order}
        used = [cpu for cpu in order if layout.get(cpu, 0) > 0]
        completely_free = [cpu for cpu in order if cpu not in used and free[cpu] == 100]
        partially_free = [cpu for cpu in order if cpu not in used and 0 < free[cpu] < 100]
        for cpu in used + completely_free + partially_free:
            take = min(free[cpu], amount)
            if take > 0:
                layout[cpu] = layout.get(cpu, 0) + take
                amount -= take
            if amount <= 0:
                break
    elif amount < 0:
        to_free = -amount
        # Least used CPUs first and, among equals, the last ones of the order (siblings, then socket 1...)
        used = [cpu for cpu in reversed(order) if layout.get(cpu, 0) > 0]
        for cpu in sorted(used, key=lambda c: layout[c]):
            take = min(layout[cpu], to_free)
            layout[cpu] -= take
            to_free -= take
            if to_free <= 0:
                break
    return {cpu: v for cpu, v in layout.items() if v > 0}


def _socket_preferences(topo, socket, current, usable, foreign_core):
    """Usable CPUs of a socket in order of preference: taking the first k of them gives the best k CPUs of the
    socket for the container."""
    primaries, secondaries = [], []
    for core in topo.cores[socket]:
        # CPUs of the container in this core, fullest first: e.g., core (0, 32) with {0: 40, 32: 100} -> [32, 0]
        mine = sorted((cpu for cpu in core if cpu in usable and cpu in current), key=lambda c: -current[c])
        if mine:
            primaries.append(mine[0])
            secondaries.extend(mine[1:])
    # 1) One CPU of each physical core of the container (the fullest ones first, so scale-downs free the others)
    primaries.sort(key=lambda c: -current[c])
    secondaries.sort(key=lambda c: -current[c])
    # 2) Physical cores without CPUs of this or other containers
    idle = [core[0] for core in topo.cores[socket]
            if all(cpu in usable and cpu not in current and not foreign_core[cpu] for cpu in core)]
    # 3) SMT siblings already used by the container, 4) new siblings of its physical cores (the ones above)
    listed = set(primaries) | set(idle) | set(secondaries)
    own_siblings = [cpu for first in primaries + idle for cpu in topo.core_of[first]
                    if cpu in usable and cpu not in listed]
    listed |= set(own_siblings)
    # 5) CPUs whose physical core runs another container
    rest = [cpu for core in topo.cores[socket] for cpu in core if cpu in usable and cpu not in listed]

    # Order of preference:
    #   1) Physical cores already used by the container
    #   2) Physical cores that are completely free
    #   3) Logical cores already used by the container
    #   4) Logical cores belonging to physical cores already used by the container
    #   5) Cores used by other containers
    return primaries + idle + secondaries + own_siblings + rest


def plan_layout(topo, core_map, name, target, min_socket_share=0.25, min_socket_cpus=2, scaler=None, trace=None):
    """New layout {cpu: shares} of container 'name' holding 'target' shares (or all the shares it can get, if they
    are fewer), following LAYOUT_RULES. 'scaler' is the Scaler layout for the same target (only used to break ties),
    computed here if not given. If 'trace' is a list, the steps of the rules are added to it (see explain_layout)."""
    n_cpus = math.ceil(target / 100) if target > 0 else 0    # E.g., 1650 shares -> 17 CPUs (16 x 100 + 1 x 50)
    if n_cpus == 0:
        return {}
    current = {cpu: m.get(name, 0) for cpu, m in core_map.items() if m.get(name, 0) > 0 and cpu in topo.socket_of}
    others = {cpu: _others(core_map, cpu, name) for cpu in topo.socket_of}   # Shares of other containers in each CPU
    # CPUs that the container can take entirely without touching other containers
    usable = {cpu for cpu in topo.socket_of
              if cpu in core_map and others[cpu] == 0
              and core_map[cpu].get("free", 0) + core_map[cpu].get(name, 0) >= 100}
    # Rule 1: with not enough CPUs free of other containers, the fewest CPUs shared with them
    if len(usable) < n_cpus:
        if trace is not None:
            trace.append(("1", "{0} CPUs free of other containers for {1} CPUs".format(len(usable), n_cpus)))
        return _shared_layout(topo, core_map, name, target, current, usable)
    # CPUs whose physical core has another CPU with shares of other containers (SMT shared with them)
    foreign_core = {cpu: any(others[sibling] > 0 for sibling in topo.core_of[cpu] if sibling != cpu)
                    for cpu in topo.socket_of}
    min_cpus = min_socket_size(n_cpus, min_socket_share, min_socket_cpus)   # F
    base = topo.cpus_per_socket(scaler if scaler is not None else scaler_layout(topo, core_map, name, target))

    # Criteria of taking the first k preferred CPUs of each socket, for k = 0, 1, ...: the best k CPUs of a socket are
    # always the first k of its preference order, so only the number of CPUs per socket has to be chosen
    prefs, criteria = {}, {}
    for s in topo.sockets:
        prefs[s] = _socket_preferences(topo, s, current, usable, foreign_core)
        cur = sum(1 for cpu in current if topo.socket_of[cpu] == s)     # CPUs of the container in this socket now
        criteria[s], cores_taken, smt, foreign, added = [], set(), 0, 0, 0
        for k in range(min(len(prefs[s]), n_cpus) + 1):
            if k > 0:
                # Counters of the first k CPUs, updated with the k-th one
                cpu = prefs[s][k - 1]
                smt += topo.core_of[cpu] in cores_taken     # +1 if this CPU is a sibling of a core used by this container
                cores_taken.add(topo.core_of[cpu])
                foreign += foreign_core[cpu]                # +1 if this CPU is a sibling of a core used by other container
                added += cpu not in current                 # +1 if this is a CPU that the container does not have yet

            # cur = CPUs previously used in socket, k = Number of CPUs we want, added = new CPUs added
            # e.g., S0 = 1-6 -> cur = 6, if k = 5 (we want 5 CPUs in this socket) and added = 2 (2 new CPUs are selected) -> dropped = 6 - (5 - 2) = 3
            #       Then, 3 original CPUs are kept in the socket, 2 news are added, and 3 of the original cores are dropped
            dropped = cur - (k - added)                     # CPUs of the container in this socket left out

            # CPUs moved within the socket
            # e.g., we add 3 new CPUs in socket (added=3) and we drop 2 CPUs (dropped=2), then 2 of them have been moved locally
            local = min(added, dropped)

            # CPUs moved across sockets, two cases
            # - added > dropped -> remote > 0: We add 3 CPUs and 2 were dropped, which means that the extra added CPU was taken from another socket
            # - dropped > added -> remote = 0: We add 2 CPUs and 3 were dropped, which means the extra dropped CPU was moved to another socket (the other socket will have remote=1)
            # (CPUs added to grow also count here, but they count the same in every layout)
            remote = added - local

            criteria[s].append({
                "foreign": foreign,                             # Cost of using a sibling of  core used by another container

                "fragment": int(0 < k < n_cpus and k - smt < min_cpus), # Accounts if the number of physical cores (k-smt) allocated to this socket is lower than min_cpus (per socket) and if more sockets are used (k < n_cpus), this implies fragmentation
                "remote": remote,                               # Number of cores that will be taken from another socket
                "sockets": int(k > 0),                          # Accounts that this socket is used
                "smt": smt,                                     # Number of sibling of an already used core
                "local": local,                                 # Number of cores moved within this socket
                "scaler": abs(k - base[s]),                     # Break tie with the one more similar to Scaler layout
            })

    # Rules 2-6 on every way of taking n_cpus CPUs from the sockets
    counts = _apply_rules(_candidates(topo, criteria, n_cpus, min_cpus), trace)["counts"]   # E.g., {"0": 17, "1": 0}

    # Full CPUs, except one with the rest of the shares: the chosen CPU with the fewest current shares (a new one if
    # any), so that CPUs already used keep their shares
    ordered = [cpu for s in sorted(topo.sockets, key=lambda s: -counts[s]) for cpu in prefs[s][:counts[s]]]
    layout = {cpu: 100 for cpu in ordered}
    partial = min(reversed(ordered), key=lambda cpu: current.get(cpu, 0))
    layout[partial] = target - 100 * (n_cpus - 1)         # E.g., 1650 shares -> 50 in the new CPU
    return layout


def _candidates(topo, criteria, n_cpus, min_cpus):
    """Every way of taking n_cpus CPUs from the sockets (the first k preferred CPUs of each one), with its criteria:
    those of its sockets added up, plus the SMT siblings beyond F - 1. They are n_cpus + 1 at most with 2 sockets."""
    def splits(i, left):
        # CPUs of sockets i, i + 1, ... adding up to 'left': e.g., 2 sockets and 17 CPUs -> [0, 17], [1, 16], ..., [17, 0]
        if i == len(topo.sockets) - 1:
            if left < len(criteria[topo.sockets[i]]):
                yield [left]
            return
        for k in range(min(left, len(criteria[topo.sockets[i]]) - 1) + 1):
            for rest in splits(i + 1, left - k):
                yield [k] + rest

    candidates = []
    for counts in splits(0, n_cpus):
        c = {name: sum(criteria[s][k][name] for s, k in zip(topo.sockets, counts)) for name in SOCKET_CRITERIA}
        c["smt_excess"] = max(0, c["smt"] - (min_cpus - 1))      # E.g., F = 6 and 7 siblings -> 2
        c["counts"] = dict(zip(topo.sockets, counts))
        candidates.append(c)
    return candidates


def _apply_rules(candidates, trace=None):
    """Rules 2-6, one after the other: each one keeps the candidates with the lowest value of its criterion, except
    rule 5, which keeps those using no more sockets than the candidate with physical cores only (no SMT siblings) that
    uses the fewest, if there is any. The first candidate left is chosen."""
    for rule, criterion, _ in LAYOUT_RULES[1:]:
        if criterion == "consolidate":
            physical = [c["sockets"] for c in candidates if c["smt"] == 0]
            kept = [c for c in candidates if not physical or c["sockets"] <= min(physical)]
        else:
            lowest = min(c[criterion] for c in candidates)
            kept = [c for c in candidates if c[criterion] == lowest]
        if trace is not None:
            kept_ids = {id(c) for c in kept}
            trace.append((rule, kept, [c for c in candidates if id(c) not in kept_ids]))
        candidates = kept
    return candidates[0]


def _shared_layout(topo, core_map, name, target, current, usable):
    """Rule 1, when there are not enough CPUs free of other containers: all of them are taken, and the rest of the
    shares in the fewest CPUs shared with other containers, those with the most free shares first (among equals,
    CPUs the container already has, then those of the socket where it has more CPUs). If they are not enough, the
    layout has fewer shares than the target (as the Scaler, which gives the container the shares it can)."""
    layout = {cpu: 100 for cpu in usable}
    remaining = target - 100 * len(usable)
    in_socket = topo.cpus_per_socket(set(usable) | set(current))
    capacity = {cpu: core_map[cpu].get("free", 0) + core_map[cpu].get(name, 0)     # Shares it can have in the CPU
                for cpu in topo.socket_of if cpu in core_map and cpu not in usable}
    for cpu in sorted(capacity, key=lambda c: (-capacity[c], c not in current, -in_socket[topo.socket_of[c]], int(c))):
        if remaining <= 0:
            break
        if capacity[cpu] > 0:
            layout[cpu] = min(capacity[cpu], remaining)     # E.g., 50 free shares and 80 remaining -> 50
            remaining -= layout[cpu]
    return layout


def min_socket_size(n_cpus, min_socket_share=0.25, min_socket_cpus=2):
    """F: minimum physical cores of a container in each socket it uses, if it uses more than one."""
    # E.g., 17 CPUs -> max(2, ceil(4.25)) = 5; 1 CPU -> 1
    return min(n_cpus, max(min_socket_cpus, math.ceil(min_socket_share * n_cpus)))


def layout_fragments(topo, cpus, min_socket_share=0.25, min_socket_cpus=2):
    """Sockets with fewer physical cores of the container than F, if it uses more than one socket."""
    counts = topo.cpus_per_socket(cpus)
    min_cpus = min_socket_size(sum(counts.values()), min_socket_share, min_socket_cpus)
    cores = {s: len({topo.core_of[cpu] for cpu in cpus if topo.socket_of.get(cpu) == s}) for s in topo.sockets}
    used = [s for s, n in counts.items() if n]
    return [s for s in used if len(used) > 1 and cores[s] < min_cpus]


# ----------------------------------------------------------------- explanation

def _describe_counts(candidates):
    """Candidate layouts as text, consecutive ones with 2 sockets as ranges: e.g., 'S0:12..5 S1:5..12'."""
    counts = sorted((tuple(c["counts"].items()) for c in candidates), key=lambda c: [-k for _, k in c])
    if len(counts[0]) != 2:
        return ", ".join(" ".join("S{0}:{1}".format(s, k) for s, k in c) for c in counts)
    runs = []
    for c in counts:
        if runs and runs[-1][-1][0][1] - c[0][1] == 1 and len(runs[-1]) and (runs[-1][-1][1][1] + 1 == c[1][1]):
            runs[-1].append(c)
        else:
            runs.append([c])
    texts = []
    for run in runs:
        (s0, a), (s1, b) = run[0]
        (_, c), (_, d) = run[-1]
        texts.append("S{0}:{1} S{2}:{3}".format(s0, a, s1, b) if len(run) == 1 else
                     "S{0}:{1}..{2} S{3}:{4}..{5}".format(s0, a, c, s1, b, d))
    return ", ".join(texts)


def deciding_rules(trace):
    """Rules that discarded candidates, i.e., those that decided the layout: e.g., ['3', '5', '6a']."""
    return [step[0] for step in trace if step[0] == "1" or step[2]]


def explain_layout(topo, core_map, name, target, min_socket_share=0.25, min_socket_cpus=2):
    """How plan_layout chooses the CPUs of a container, rule by rule, as text."""
    trace = []
    layout = plan_layout(topo, core_map, name, target, min_socket_share, min_socket_cpus, trace=trace)
    current = [cpu for cpu, m in core_map.items() if m.get(name, 0) > 0]
    n_cpus = math.ceil(target / 100)
    lines = ["{0}: {1} -> {2} CPUs (F = {3})".format(name, topo.describe(current), n_cpus,
                                                    min_socket_size(n_cpus, min_socket_share, min_socket_cpus))]
    rules = {rule: (criterion, text) for rule, criterion, text in LAYOUT_RULES}
    for step in trace:
        rule = step[0]
        if rule == "1":
            lines.append("  Rule 1 ({0}): {1}".format(rules[rule][1], step[1]))
            continue
        kept, discarded = step[1], step[2]
        if rule == "2":
            lines.append("  Candidates: {0}".format(_describe_counts(kept + discarded)))
        if not discarded:
            continue
        criterion = "sockets" if rules[rule][0] == "consolidate" else rules[rule][0]
        value = lambda cs: "..".join(str(v) for v in sorted({c[criterion] for c in cs})[::max(1, len({c[criterion] for c in cs}) - 1)])
        lines.append("  Rule {0} ({1}): discards {2} ({3} {4}), keeps {5} ({3} {6})".format(
            rule, rules[rule][1], _describe_counts(discarded), criterion, value(discarded),
            _describe_counts(kept), value(kept)))
    lines.append("  -> {0}".format(topo.describe(layout)))
    return "\n".join(lines)


if __name__ == "__main__":
    # Example on a server with 2x Intel Xeon Silver 4216 (CPUs i and i + 32 in the same core)
    raw = {"0": {str(i): [i, i + 32] for i in range(16)}, "1": {str(i - 16): [i, i + 32] for i in range(16, 32)}}
    topo = Topology(raw)

    def host(**containers):
        core_map = {str(c): {"free": 100} for c in range(64)}
        for container, cpus in containers.items():
            for cpu in cpus:
                core_map[str(cpu)] = {container: 100, "free": 0}
        return core_map

    phys0, phys1, sib0, sib1 = list(range(16)), list(range(16, 32)), list(range(32, 48)), list(range(48, 64))
    examples = [
        ("Grow 16 -> 17", host(c1=phys0), 1700),
        ("Grow 21 -> 22", host(c1=phys0 + sib0[:5]), 2200),
        ("Shrink 22 -> 21", host(c1=phys0 + phys1[:6]), 2100),
        ("Shrink 17 -> 16", host(c1=phys0[:12] + phys1[:5]), 1600),
        ("Grow 21 -> 22, c2 on the physical cores of socket 1", host(c1=phys0 + sib0[:5], c2=phys1), 2200),
        ("Grow 21 -> 22, c2 on 13 physical cores of socket 1", host(c1=phys0 + sib0[:5], c2=phys1[:13]), 2200),
    ]
    for title, core_map, target in examples:
        print("== " + title)
        print(explain_layout(topo, core_map, "c1", target))
