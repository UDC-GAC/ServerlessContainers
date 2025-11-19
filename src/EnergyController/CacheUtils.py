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
            self._cache.setdefault(structure_id, {}).setdefault(direction, deque()).append(now)

    def get_events(self, structure_id, direction):
        return len(self._cache.get(structure_id, {}).get(direction, deque()))

    def get_events_info(self, structure_id):
        return f"EVENTS: UP {self.get_events(structure_id, 'up')} | DOWN {self.get_events(structure_id, 'down')}"

    def clear_events(self, structure_id):
        with self._lock:
            events = self._cache.get(structure_id)
            if events:
                for dq in events.values():
                    dq.clear()

    def remove_old_events(self, timeout):
        cutoff = time.time() - timeout
        with self._lock:
            for events in self._cache.values():
                for direction, dq in events.items():
                    while dq and dq[0] < cutoff:
                        dq.popleft()


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
        self._lock = Lock()

    def add(self, structure_id, old, new):
        with self._lock:
            self._cache[structure_id] = {"old": old, "new": new}

    def get_old(self, structure_id, read):
        return self._cache.get(structure_id, {}).get("old", read)

    def get_new(self, structure_id, read):
        return self._cache.get(structure_id, {}).get("new", read)
