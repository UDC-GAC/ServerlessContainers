import time
from cachetools import LRUCache
from threading import Lock
from collections import deque


class EventsCache:

    def __init__(self):
        self._cache = LRUCache(maxsize=128)
        self._lock = Lock()

    def add_event(self, structure_id, direction):
        now = time.time()
        with self._lock:
            entry = self._cache.setdefault(structure_id, {"events": deque(), "counts": {"up": 0, "down": 0}})
            entry["events"].append((now, direction))
            entry["counts"][direction] += 1

    def get_events(self, structure_id, direction):
        return self._cache.get(structure_id, {}).get("counts", {}).get(direction, 0)

    def get_events_info(self, structure_id):
        return f"EVENTS: UP {self.get_events(structure_id, 'up')} | DOWN {self.get_events(structure_id, 'down')}"

    def clear_events(self, structure_id):
        with self._lock:
            entry = self._cache.get(structure_id)
            if entry:
                entry["events"].clear()
                entry["counts"]["up"] = 0
                entry["counts"]["down"] = 0

    def keep_last_n_events(self, structure_id, num_events):
        if num_events < 0:
            raise ValueError("The number of events to keep must be positive: {0}".format(num_events))

        with self._lock:
            entry = self._cache.get(structure_id)
            if not entry:
                return

            while len(entry["events"]) > num_events:
                _, direction = entry["events"].popleft()
                entry["counts"][direction] -= 1

    def remove_old_events(self, timeout):
        cutoff = time.time() - timeout
        with self._lock:
            for entry in self._cache.values():
                while entry["events"] and entry["events"][0][0] < cutoff:
                    _, direction = entry["events"].popleft()
                    entry["counts"][direction] -= 1


class PowerBudgetCache:

    def __init__(self):
        self._cache = LRUCache(maxsize=128)
        self._lock = Lock()

    def add(self, structure_id, pb):
        with self._lock:
            self._cache[structure_id] = pb

    def is_new(self, structure_id, pb):
        return structure_id not in self._cache


class CPUAllocationCache:

    def __init__(self):
        self._cache = LRUCache(maxsize=128)
        self._outdated_count = LRUCache(maxsize=128)
        self._outdated_max = 3
        self._cache_lock,self._outdated_lock = Lock(), Lock()

    def add(self, structure_id, old, new):
        with self._cache_lock:
            self._cache[structure_id] = {"old": old, "new": new}

    def count_outdated(self, structure_id, value):
        with self._outdated_lock:
            self._outdated_count.setdefault(structure_id, {})[value] = self._outdated_count.get(structure_id, {}).get(value, 0) + 1

    def reset_outdated(self, structure_id, value):
        with self._outdated_lock:
            self._outdated_count[structure_id][value] = 0

    def get_old(self, structure_id, read):
        return self._cache.get(structure_id, {}).get("old", read)

    def get_new(self, structure_id, read):
        return self._cache.get(structure_id, {}).get("new", read)

    def get_outdated_count(self, structure_id, value):
        return self._outdated_count.get(structure_id, {}).get(value, 0)