"""
Telemetry of the EnergyManager: incremental store of the points read from OpenTSDB.

Every iteration a single query retrieves the last seconds of every series (containers and hosts). Points with new
timestamps are added; points already read are updated if their value has changed (e.g., the CPU usage of a
container is the sum of its processes, which may be sent in different requests) and late points fill their gaps.
Metrics are expected to arrive with the same granularity and points are read as averages of POLLING_FREQUENCY seconds
(OpenTSDB downsampling), thus the POLLING_FREQUENCY is equivalent to the sampling period (T).
"""
import bisect
import time

CPU_USER, CPU_KERNEL, CPU_WAIT, ENERGY = "proc.cpu.user", "proc.cpu.kernel", "proc.cpu.wait", "structure.energy.usage"
RETRIEVED_METRICS = [CPU_USER, CPU_KERNEL, CPU_WAIT, ENERGY]


class Telemetry:

    def __init__(self, opentsdb_handler, horizon=120):
        self.opentsdb_handler = opentsdb_handler
        self.horizon = horizon          # Seconds of points kept in memory
        self.series = {}                # (name, metric) -> [(ts, value)], sorted by ts
        self.query_time = 0.0
        self.last_query = (0, 0)        # (start, end) of the last query

    def poll(self, names, lookback, period=1):
        """Read the last 'lookback' seconds of every series and merge them with the points already read. Each point is
        the average of 'period' seconds, with the timestamp of its first second (multiples of the period); a period is
        only read once its last second has started. Returns the set of (name, metric) with new timestamps (newer than
        the last one read)."""
        t0 = time.time()
        tags = {"host": "|".join(sorted(names))}
        start = int(t0 - lookback)
        # OpenTSDB averages periods that start at multiples of the period, whatever the query asks. The query starts
        # with a period, as a partial one would replace the complete value read before, and ends with the last period
        # whose last second has started (the current second with 1 s periods): each sample is evaluated only once
        self.last_query = (start - start % period, (int(t0) + 1) // period * period - 1)
        query = dict(start=self.last_query[0], end=self.last_query[1], queries=[dict(aggregator="zimsum", metric=m, tags=tags, downsample=f"{period}s-avg") for m in RETRIEVED_METRICS])
        updated = set()
        for entry in self.opentsdb_handler.get_points(query) or []:
            key = (str(entry.get("tags", {}).get("host", "")), entry["metric"])
            points = self.series.setdefault(key, [])
            last_ts = points[-1][0] if points else -1
            for ts, v in sorted((int(ts), float(v)) for ts, v in entry.get("dps", {}).items()):
                if ts > last_ts:
                    points.append((ts, v))
                    last_ts = ts
                    updated.add(key)
                    continue
                # Find the appropriate position for this timestamp, points are ordered by ts
                i = bisect.bisect_left(points, (ts,))
                # If the timestamp already exists in that position, update its value
                if i < len(points) and points[i][0] == ts:
                    points[i] = (ts, v)
                # If the timestamp does not exist, insert it in the proper position (late timestamp)
                else:
                    points.insert(i, (ts, v))
            # Remove oldest points, only keep in memory self.horizon seconds
            first_kept = bisect.bisect_left(points, (t0 - self.horizon,))
            if first_kept:
                del points[:first_kept]
        self.query_time = time.time() - t0
        return updated

    def missing(self, names, updated, now):
        """Series of these names without new points in the last poll: [(name, 'energy'|'cpu', last ts, age s)]"""
        result = []
        for name in names:
            for metric, label in ((ENERGY, "energy"), (CPU_USER, "cpu")):
                if (name, metric) not in updated:
                    last = self.latest_ts(name, metric)
                    result.append((name, label, last, now - last if last is not None else None))
        return result

    def forget(self, name):
        for key in [k for k in self.series if k[0] == name]:
            del self.series[key]

    def points_since(self, name, metric, since):
        return [(ts, v) for ts, v in self.series.get((name, metric), ()) if ts >= since]

    def latest_ts(self, name, metric):
        points = self.series.get((name, metric))
        return points[-1][0] if points else None

    def mean_last(self, name, metric, since, n):
        """Mean of the last n points taken at or after 'since'. Returns (mean, points used, first ts, last ts),
        with mean = None if there are fewer than n points."""
        points = self.points_since(name, metric, since)[-n:]
        if len(points) < n:
            return None, len(points), None, None
        return sum(v for _, v in points) / n, n, points[0][0], points[-1][0]

    def latest_since(self, name, metric, since):
        points = self.points_since(name, metric, since)
        return points[-1] if points else None

    # Compatibility with plugins using the previous API
    def mean_since(self, name, metric, since, fallback_latest=False):
        points = self.points_since(name, metric, since)
        if points:
            return sum(v for _, v in points) / len(points), len(points)
        return None, 0

    def container_usages(self, name, since, n_energy, n_cpu):
        """Returns (usages, info). usages is None until there are n_energy energy points and n_cpu CPU points after
        'since'. CPU usage is user + kernel, added up timestamp by timestamp. CPU wait and pressure are only included
        if there are CPU wait points at the timestamps of the CPU usage points."""
        energy, energy_points, first, last = self.mean_last(name, ENERGY, since, n_energy)
        user = self.points_since(name, CPU_USER, since)[-n_cpu:]
        kernel = dict(self.points_since(name, CPU_KERNEL, since))
        info = {"energy_points": energy_points, "first_ts": first, "last_ts": last,
                "cpu_points": len(user), "cpu_ts": user[-1][0] if user else None}
        if energy is None or len(user) < n_cpu:
            return None, info
        mean_user = sum(v for _, v in user) / n_cpu
        mean_kernel = sum(kernel.get(ts, 0.0) for ts, _ in user) / n_cpu
        usages = {"structure.cpu.usage": mean_user + mean_kernel, "structure.cpu.user": mean_user,
                  "structure.cpu.kernel": mean_kernel, "structure.energy.usage": energy}
        wait = dict(self.points_since(name, CPU_WAIT, since))
        waits = [wait[ts] for ts, _ in user if ts in wait]
        if waits:
            mean_wait = sum(waits) / len(waits)
            demand = mean_user + mean_kernel + mean_wait
            usages["structure.cpu.wait"] = mean_wait
            # CPU pressure = wait / (usage + wait)
            usages["structure.cpu.pressure"] = mean_wait / demand if demand > 0 else 0.0
        return usages, info

    def host_power(self, host, since, n):
        """Host power excluding the power sensor consumption (i.e., RAPL - sensor)."""
        rapl, n_rapl, _, last = self.mean_last("{0}-rapl".format(host), ENERGY, since, n)
        if rapl is None:
            return None, n_rapl
        sensor, _, _, _ = self.mean_last("{0}-sensor".format(host), ENERGY, since, n)
        sensor = sensor or 0.0
        return {"rapl": rapl, "sensor": sensor, "global": rapl - sensor}, n_rapl
