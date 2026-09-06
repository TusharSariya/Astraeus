"""Source-local coalescing cache for selected-timestamp NOAA GFS queries."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping


@dataclass(frozen=True)
class GFSRequestKey:
    """Canonical provider request identity known before payload retrieval."""

    index_url: str
    grib_url: str
    ranges: tuple[tuple[int, int], ...]
    fields: tuple[str, ...]
    bounds: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class GFSQueryEntry:
    key: GFSRequestKey
    run_time: datetime
    valid_time: datetime
    fetched_at: datetime
    content_digest: str
    values: Mapping[str, object]
    provenance: Mapping[str, object]


class GFSQueryService:
    """Cache exact immutable GFS object ranges and coalesce identical misses."""

    def __init__(
        self,
        loader: Callable[[GFSRequestKey], GFSQueryEntry],
        *,
        ttl_seconds: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("GFS cache TTL must be positive")
        self._loader = loader
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[GFSRequestKey, tuple[float, GFSQueryEntry]] = {}
        self._inflight: dict[GFSRequestKey, threading.Event] = {}
        self._failures: dict[GFSRequestKey, BaseException] = {}

    def query(self, key: GFSRequestKey) -> GFSQueryEntry:
        while True:
            with self._lock:
                now = self._clock()
                cached = self._entries.get(key)
                if cached is not None and now < cached[0]:
                    return cached[1]
                event = self._inflight.get(key)
                if event is None:
                    event = threading.Event()
                    self._inflight[key] = event
                    self._failures.pop(key, None)
                    owner = True
                else:
                    owner = False
            if owner:
                try:
                    entry = self._loader(key)
                    if entry.key != key:
                        raise ValueError("GFS loader returned a different provider request identity")
                    with self._lock:
                        self._entries[key] = (self._clock() + self._ttl, entry)
                    return entry
                except BaseException as error:
                    with self._lock:
                        self._entries.pop(key, None)
                        self._failures[key] = error
                    raise
                finally:
                    with self._lock:
                        self._inflight.pop(key, None)
                        event.set()
            event.wait()
            with self._lock:
                failure = self._failures.get(key)
            if failure is not None:
                raise RuntimeError("coalesced GFS provider query failed") from failure
