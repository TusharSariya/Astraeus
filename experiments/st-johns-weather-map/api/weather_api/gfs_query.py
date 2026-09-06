"""Source-local coalescing cache for selected-timestamp NOAA GFS queries."""

from __future__ import annotations

import threading
import time
import json
import hashlib
import tempfile
import sys
import zipfile
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from ingest.adapters.noaa_s3 import (
    GFS_IDX_SELECTORS,
    MAX_IDX_BYTES,
    NOAAS3Adapter,
    cap_open_range,
    gfs_native_lead,
    gfs_native_time_at_or_before,
    select_gfs_ranges,
)
from ingest.contract import FetchWindow, RunCandidate
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

GFS_OBJECT_CACHE_TTL_SECONDS = 600.0
GFS_CACHE_MAX_ENTRIES = 4
GFS_CACHE_MAX_BYTES = 256 * 1024 * 1024
GFS_DEMAND_LIMITS = ProcessAllocationLimits(
    address_space_bytes=1 * 1024 * 1024 * 1024,
    output_bytes=64 * 1024 * 1024,
    stdin_bytes=2 * 1024 * 1024,
    stdout_bytes=64 * 1024,
    stderr_bytes=256 * 1024,
)
_COORDINATOR: GFSQueryCoordinator | None = None

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


class GFSQueryCoordinator:
    """Resolve one selection and load one exact GFS object-range request."""

    def __init__(
        self,
        adapter: NOAAS3Adapter | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime],
        bounded_fetch: Callable[[GFSRequestKey, RunCandidate, datetime], GFSQueryEntry] | None = None,
    ) -> None:
        self._adapter = adapter or NOAAS3Adapter()
        self._clock = clock
        self._now = now
        self._lock = threading.Lock()
        self._candidate: tuple[float, RunCandidate] | None = None
        self._indices: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._prepared: dict[GFSRequestKey, RunCandidate] = {}
        self._bounded_fetch = bounded_fetch
        self._cache = GFSQueryService(self._load, clock=clock)

    def query(self, selected_time: datetime) -> GFSQueryEntry:
        with self._lock:
            candidate = self._discover()
            if candidate.run_time is None:
                raise ValueError("GFS discovery returned no producer run time")
            native_time = gfs_native_time_at_or_before(candidate.run_time, selected_time)
            lead = gfs_native_lead(candidate.run_time, native_time)
            date_str = str(candidate.detail["date_str"])
            cycle = str(candidate.detail["cycle"])
            stem = f"gfs.t{cycle}z.pgrb2.0p25.f{lead:03d}"
            grib_url = f"{self._adapter._base_url}/gfs.{date_str}/{cycle}/atmos/{stem}"
            idx_url = f"{grib_url}.idx"
            idx_text = self._index(idx_url)
            ranges, _present = select_gfs_ranges(idx_text)
            ranges = cap_open_range(ranges)
            key = GFSRequestKey(
                index_url=idx_url,
                grib_url=grib_url,
                ranges=tuple((item.start, int(item.end)) for item in ranges if item.end is not None),
                fields=tuple(f"{parameter}:{level}" for parameter, level in sorted(GFS_IDX_SELECTORS)),
                bounds=tuple(sorted((str(name), float(value)) for name, value in self._adapter._bounds.items())),
            )
            self._prepared[key] = RunCandidate(
                candidate.provider_run_id,
                candidate.run_time,
                list(candidate.urls),
                {**candidate.detail, "idx_text_by_lead": {lead: idx_text}},
            )
            try:
                return self._cache.query(key)
            finally:
                self._prepared.pop(key, None)

    def point_fields(self, latitude: float, longitude: float, selected_time: datetime) -> tuple[list[Any], Any, list[str]]:
        """Answer one point through the existing evidence/provenance builder.

        Demand payloads remain memory-resident cache entries.  They are opened
        only for this request and presented to the existing sampler as native
        retrieved artifacts; no ArtifactStore row or current revision is
        invented for the live-query path.
        """
        from .store import LiveStore, live_point_fields  # noqa: PLC0415

        entry = self.query(selected_time)
        samples = []
        with tempfile.TemporaryDirectory(prefix="gfs-demand-read-") as directory:
            sampler = LiveStore.__new__(LiveStore)
            sampler.skipped = []
            sampler.unmodelled = []
            for index, logical_name in enumerate(entry.values["logical_names"]):
                path = Path(directory) / f"{logical_name}.zarr.zip"
                path.write_bytes(entry.payloads[index])
                import xarray  # noqa: PLC0415
                import zarr  # noqa: PLC0415

                zipped = zarr.storage.ZipStore(str(path), mode="r")
                dataset = xarray.open_zarr(zipped, consolidated=False)
                try:
                    provenance = dict(entry.provenance[logical_name])
                    artifact = SimpleNamespace(
                        source_id="noaa-gfs",
                        logical_name=logical_name,
                        revision_id=f"demand:{entry.content_digest}:{logical_name}",
                        provenance=provenance,
                        run_time=entry.run_time,
                        retrieved_at=entry.fetched_at,
                        native_crs=provenance.get("native_crs", "EPSG:4326"),
                    )
                    samples.extend(
                        sampler._sample_dataset(dataset, artifact, latitude, longitude, entry.valid_time)
                    )
                finally:
                    dataset.close()
                    zipped.close()

        class _Samples:
            skipped = sampler.skipped
            unmodelled = sampler.unmodelled

            @staticmethod
            def sample_point(*_args: object, **_kwargs: object) -> list[Any]:
                return samples

        return live_point_fields(_Samples(), latitude, longitude, entry.valid_time)

    def _discover(self) -> RunCandidate:
        current = self._clock()
        if self._candidate is not None and current < self._candidate[0]:
            return self._candidate[1]
        candidate = self._adapter.discover(FetchWindow(now=self._now()))[0]
        self._candidate = (current + GFS_OBJECT_CACHE_TTL_SECONDS, candidate)
        return candidate

    def _index(self, url: str) -> str:
        current = self._clock()
        cached = self._indices.get(url)
        if cached is not None and current < cached[0]:
            self._indices.move_to_end(url)
            return cached[1]
        text = self._adapter._get_client().get_bytes(url, max_bytes=MAX_IDX_BYTES).decode("utf-8")
        self._indices[url] = (current + GFS_OBJECT_CACHE_TTL_SECONDS, text)
        while len(self._indices) > GFS_CACHE_MAX_ENTRIES:
            self._indices.popitem(last=False)
        return text

    def _load(self, key: GFSRequestKey) -> GFSQueryEntry:
        candidate = self._prepared[key]
        if self._bounded_fetch is not None:
            return self._bounded_fetch(key, candidate, self._selected_time(key, candidate))
        with tempfile.TemporaryDirectory(prefix="gfs-demand-") as directory:
            bundle_path = Path(directory) / "gfs-demand-result.zip"
            request = json.dumps(
                {
                    "provider_run_id": candidate.provider_run_id,
                    "run_time": candidate.run_time.isoformat() if candidate.run_time else None,
                    "selected_time": self._selected_time(key, candidate).isoformat(),
                    "urls": candidate.urls,
                    "detail": candidate.detail,
                },
                default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
                sort_keys=True,
            ).encode()
            run_bounded_process(
                command=[sys.executable, "-m", "weather_api.gfs_query_worker", "{output}"],
                stdin=request,
                destination=bundle_path,
                limits=GFS_DEMAND_LIMITS,
                timeout_seconds=180,
            )
            with zipfile.ZipFile(bundle_path) as bundle:
                info = json.loads(bundle.read("result.json"))
                if info.get("source_id") != "noaa-gfs" or not info.get("complete") or not info.get("qc_passed"):
                    raise ValueError("GFS bounded child returned an incomplete or failed-QC selection")
                artifacts = info["artifacts"]
                if not artifacts or len(artifacts) > 2:
                    raise ValueError("GFS bounded child returned an invalid artifact set")
                payloads = tuple(bundle.read(f"artifacts/{artifact['name']}") for artifact in artifacts)
            digest = hashlib.sha256(b"".join(payloads)).hexdigest()
            provenance = {artifact["logical_name"]: artifact["provenance"] for artifact in artifacts}
        return GFSQueryEntry(
            key=key,
            run_time=datetime.fromisoformat(info["run_time"]),
            valid_time=self._selected_time(key, candidate),
            fetched_at=datetime.fromisoformat(info["retrieved_at"]),
            content_digest=digest,
            values={"logical_names": [artifact["logical_name"] for artifact in artifacts]},
            provenance=provenance,
            payloads=payloads,
        )

    @staticmethod
    def _selected_time(key: GFSRequestKey, candidate: RunCandidate) -> datetime:
        lead = int(key.grib_url.rsplit(".f", 1)[1])
        assert candidate.run_time is not None
        return candidate.run_time + timedelta(hours=lead)


def gfs_query_coordinator() -> GFSQueryCoordinator:
    """Process-local demand cache used by the public point route."""
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = GFSQueryCoordinator(now=lambda: datetime.now(UTC))
    return _COORDINATOR
