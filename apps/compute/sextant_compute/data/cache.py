"""Cache backends for DataService's whole-request cache.

Values are JSON-compatible (DataService encodes frames before storing), so every
backend can be remote. Two backends:

- ``RuntimeCache``: Vercel's Runtime Cache (per region, survives deploys, LRU,
  2 MB per item). Used when running on Vercel.
- ``InMemoryCache``: per-process dict with TTL and a size bound. Used locally,
  in tests, and as the fallback.

Runtime Cache entries survive deployments, so every key carries
``CACHE_VERSION`` and the adapter's ``version``: bump one when the cached shape
or the data it represents changes.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any, Protocol

CACHE_VERSION = 1


class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None:
        """The stored JSON value, or None on a miss or expiry."""
        ...

    def set(self, key: str, value: Any, *, ttl: int, tags: Sequence[str] = ()) -> None: ...

    def expire_tag(self, tag: str) -> None:
        """Drop every entry carrying ``tag`` (e.g. ``user:<id>`` on account deletion)."""
        ...


class InMemoryCache:
    def __init__(self, *, max_entries: int = 512, clock: Callable[[], float] = time.monotonic) -> None:
        self._entries: OrderedDict[str, tuple[float, Any, frozenset[str]]] = OrderedDict()
        self._max = max_entries
        self._clock = clock

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires, value, _tags = entry
        if self._clock() >= expires:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: Any, *, ttl: int, tags: Sequence[str] = ()) -> None:
        self._entries[key] = (self._clock() + ttl, value, frozenset(tags))
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def expire_tag(self, tag: str) -> None:
        for key in [k for k, (_, _, tags) in self._entries.items() if tag in tags]:
            del self._entries[key]

    def __len__(self) -> int:
        now = self._clock()
        return sum(1 for expires, _, _ in self._entries.values() if now < expires)


class RuntimeCache:
    """Vercel Runtime Cache via the ``vercel-cache`` package. Failures degrade to misses."""

    def __init__(self, namespace: str = "sextant") -> None:
        from vercel.cache import RuntimeCache as VercelRuntimeCache

        self._cache = VercelRuntimeCache(namespace=namespace)

    def get(self, key: str) -> Any | None:
        try:
            return self._cache.get(key)
        except Exception:  # a cache outage must never fail the request
            return None

    def set(self, key: str, value: Any, *, ttl: int, tags: Sequence[str] = ()) -> None:
        try:
            self._cache.set(key, value, {"ttl": ttl, "tags": list(tags)})
        except Exception:
            pass

    def expire_tag(self, tag: str) -> None:
        self._cache.expire_tag(tag)


def default_shared_cache() -> CacheBackend:
    """Vercel's Runtime Cache on Vercel, otherwise a per-process in-memory cache."""
    if os.environ.get("VERCEL"):
        return RuntimeCache()
    return InMemoryCache()
