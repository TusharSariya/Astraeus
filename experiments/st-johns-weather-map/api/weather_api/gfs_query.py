"""Source-local coalescing cache for selected-timestamp NOAA GFS queries."""

from __future__ import annotations

import threading
import time
import json
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping

GFS_OBJECT_CACHE_TTL_SECONDS = 600.0
GFS_CACHE_MAX_ENTRIES = 4
GFS_CACHE_MAX_BYTES = 256 * 1024 * 1024

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
    payloads: tuple[bytes, ...] = ()

    def __post_init__(self) -> None:
        if any(value.tzinfo is None for value in (self.run_time, self.valid_time, self.fetched_at)):
            raise ValueError("GFS cache entry times must be timezone-aware")
        if len(self.content_digest) != 64 or any(char not in "0123456789abcdef" for char in self.content_digest):
            raise ValueError("GFS content digest must be lowercase SHA-256")

    @property
    def backing_bytes(self) -> int:
        metadata = json.dumps(
            {"values": self.values, "provenance": self.provenance},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return len(metadata) + sum(len(payload) for payload in self.payloads)


class GFSQueryService:
    """Cache exact immutable GFS object ranges and coalesce identical misses."""

    def __init__(
        self,
        loader: Callable[[GFSRequestKey], GFSQueryEntry],
        *,
        ttl_seconds: float = GFS_OBJECT_CACHE_TTL_SECONDS,
        max_entries: int = GFS_CACHE_MAX_ENTRIES,
        max_bytes: int = GFS_CACHE_MAX_BYTES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or max_entries <= 0 or max_bytes <= 0:
            raise ValueError("GFS cache TTL, entry count and byte ceiling must be positive")
        if max_entries > GFS_CACHE_MAX_ENTRIES or max_bytes > GFS_CACHE_MAX_BYTES:
            raise ValueError("GFS cache configuration exceeds its source-local ceiling")
        self._loader = loader
        self._ttl = ttl_seconds
        self._clock = clock
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._lock = threading.Lock()
        self._entries: OrderedDict[GFSRequestKey, tuple[float, GFSQueryEntry]] = OrderedDict()
        self._inflight: dict[GFSRequestKey, Future[GFSQueryEntry]] = {}

    def query(self, key: GFSRequestKey) -> GFSQueryEntry:
        while True:
            with self._lock:
                now = self._clock()
                cached = self._entries.get(key)
                if cached is not None and now < cached[0]:
                    self._entries.move_to_end(key)
                    return cached[1]
                if cached is not None:
                    self._entries.pop(key)
                future = self._inflight.get(key)
                if future is None:
                    future = Future()
                    self._inflight[key] = future
                    owner = True
                else:
                    owner = False
            if owner:
                try:
                    entry = self._loader(key)
                    if entry.key != key:
                        raise ValueError("GFS loader returned a different provider request identity")
                    if entry.backing_bytes <= 0 or entry.backing_bytes > self._max_bytes:
                        raise ValueError("GFS normalized cache entry exceeds its finite byte ceiling")
                    with self._lock:
                        self._entries[key] = (self._clock() + self._ttl, entry)
                        self._entries.move_to_end(key)
                        while (
                            len(self._entries) > self._max_entries
                            or sum(item.backing_bytes for _, item in self._entries.values()) > self._max_bytes
                        ):
                            self._entries.popitem(last=False)
                    future.set_result(entry)
                    return entry
                except BaseException as error:
                    with self._lock:
                        self._entries.pop(key, None)
                    future.set_exception(error)
                    raise
                finally:
                    with self._lock:
                        self._inflight.pop(key, None)
            return future.result()
