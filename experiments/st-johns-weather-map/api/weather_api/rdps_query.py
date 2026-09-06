"""Selected-native-time RDPS query with a finite process-local cache."""
from __future__ import annotations

import hashlib
import json
import tempfile
import sys
import zipfile
from ingest.isolation import ProcessAllocationLimits, run_bounded_process
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Mapping

from ingest.adapters.eccc_datamart import (
    AVALON_CORE_BOUNDS,
    ECCCDataMartAdapter,
    RDPS_DEMAND_VARS,
    HRDPS_FILE_BYTES,
)
from ingest.contract import FetchWindow, RunCandidate

RDPS_POINT_FIELDS = (
    "temperature_2m", "dew_point_2m",
    "wind_speed_10m", "wind_direction_10m", "mean_sea_level_pressure",
    "total_cloud_opacity",
)
def rdps_profile_fields(pressures) -> tuple[str, ...]:
    """Only provider fields the requested profile levels can expose."""
    available = set(RDPS_DEMAND_VARS)
    ordered: list[str] = []
    for pressure in pressures:
        for prefix in ("relative_humidity", "temperature", "geopotential_height", "wind_speed", "wind_direction", "omega"):
            name = f"{prefix}_{int(pressure)}hPa"
            if name in available and name not in ordered:
                ordered.append(name)
    return tuple(ordered)
RDPS_CACHE_TTL_SECONDS = 600.0
RDPS_CACHE_MAX_ENTRIES = 4
RDPS_CACHE_MAX_BYTES = 32 * 1024 * 1024
RDPS_LIMITS = ProcessAllocationLimits(2 * 1024 * 1024 * 1024, 16 * 1024 * 1024, 2 * 1024 * 1024, 64 * 1024, 256 * 1024)
RDPS_SELECTED_RECEIVED_BYTES = len(RDPS_POINT_FIELDS) * HRDPS_FILE_BYTES
RDPS_FAILURE_BACKOFF_SECONDS = 60.0
_COORDINATOR: "RDPSQueryCoordinator | None" = None


@dataclass(frozen=True)
class RDPSRequestKey:
    cycle_url: str
    provider_run_id: str
    lead: int
    fields: tuple[str, ...]
    bounds: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class RDPSQueryEntry:
    key: RDPSRequestKey
    run_time: datetime
    valid_time: datetime
    fetched_at: datetime
    content_digest: str
    payload: bytes
    provenance: Mapping[str, object]

    @property
    def backing_bytes(self) -> int:
        return len(self.payload) + len(json.dumps(self.provenance, sort_keys=True, default=str).encode())


class RDPSQueryService:
    """Coalesce and cache exact provider run/lead/field requests."""

    def __init__(self, loader: Callable[[RDPSRequestKey], RDPSQueryEntry], *,
                 ttl_seconds: float = RDPS_CACHE_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if ttl_seconds <= 0 or ttl_seconds > RDPS_CACHE_TTL_SECONDS:
            raise ValueError("RDPS cache TTL is outside its source-local ceiling")
        self._loader, self._ttl, self._clock = loader, ttl_seconds, clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[RDPSRequestKey, tuple[float, RDPSQueryEntry]] = OrderedDict()
        self._inflight: dict[RDPSRequestKey, Future[RDPSQueryEntry]] = {}
        self._failures: dict[RDPSRequestKey, tuple[float, BaseException]] = {}

    def query(self, key: RDPSRequestKey) -> RDPSQueryEntry:
        with self._lock:
            now = self._clock()
            cached = self._entries.get(key)
            if cached and now < cached[0]:
                self._entries.move_to_end(key)
                return cached[1]
            self._entries.pop(key, None)
            failure = self._failures.get(key)
            if failure and now < failure[0]:
                raise failure[1]
            self._failures.pop(key, None)
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[key] = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            entry = self._loader(key)
            if entry.key != key:
                raise ValueError("RDPS loader returned a different request identity")
            if not 0 < entry.backing_bytes <= RDPS_CACHE_MAX_BYTES:
                raise ValueError("RDPS cache entry exceeds its finite byte ceiling")
            with self._lock:
                self._entries[key] = (self._clock() + self._ttl, entry)
                while len(self._entries) > RDPS_CACHE_MAX_ENTRIES or sum(v.backing_bytes for _, v in self._entries.values()) > RDPS_CACHE_MAX_BYTES:
                    self._entries.popitem(last=False)
            future.set_result(entry)
            return entry
        except BaseException as error:
            with self._lock:
                self._failures[key] = (self._clock() + RDPS_FAILURE_BACKOFF_SECONDS, error)
                while len(self._failures) > RDPS_CACHE_MAX_ENTRIES:
                    self._failures.pop(next(iter(self._failures)))
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)


class RDPSQueryCoordinator:
    def __init__(self, adapter: ECCCDataMartAdapter | None = None, *,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC),
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._adapter = adapter or ECCCDataMartAdapter(source_id="eccc-rdps", model_subpath="model_rdps/10km", grid_token="RLatLon0.09", var_map=RDPS_DEMAND_VARS, bounds=AVALON_CORE_BOUNDS, adapter_version="rdps-demand-v1")
        self._now, self._clock = now, clock
        self._candidate: tuple[float, RunCandidate] | None = None
        self._prepared: dict[RDPSRequestKey, RunCandidate] = {}
        self._lock = threading.Lock()
        self._cache = RDPSQueryService(self._load, clock=clock)

    def query(self, selected_time: datetime, *, fields: tuple[str, ...] = RDPS_POINT_FIELDS) -> RDPSQueryEntry:
        if selected_time.tzinfo is None:
            raise ValueError("RDPS selected time must include an offset")
        fields = tuple(sorted(set(fields)))
        if not fields or set(fields) - set(self._adapter.var_map):
            raise ValueError("RDPS unsupported field set")
        requested_time = selected_time.astimezone(UTC)
        selected_time = requested_time.replace(minute=0, second=0, microsecond=0)
        if requested_time - selected_time >= timedelta(hours=1):  # defensive; floor is always under one hour
            raise ValueError("RDPS latest native time is too old for the selection")
        # This gate precedes even bounded directory discovery: listings are
        # provider payload too, so an unsupported runtime never opens one.
        self._adapter.demand_operation_bounds(len(fields))
        with self._lock:
            candidate = self._discover(selected_time)
            assert candidate.run_time is not None
            seconds = (selected_time - candidate.run_time).total_seconds()
            if seconds < 0 or seconds % 3600:
                raise ValueError("RDPS has no exact native hourly time for the selection")
            lead = int(seconds // 3600)
            available = {int(value) for value in candidate.detail.get("available_hours", ())}
            if lead not in available or not 0 <= lead < 85:
                raise ValueError("RDPS has no exact native lead for the selection")
            key = RDPSRequestKey(str(candidate.detail["cycle_url"]), candidate.provider_run_id,
                                  lead, tuple(fields), tuple(sorted(self._adapter.bounds.items())))
            self._prepared[key] = candidate
            try:
                return self._cache.query(key)
            finally:
                self._prepared.pop(key, None)

    def timeline_times(self, selected_time: datetime) -> tuple[datetime, ...]:
        """Return the bounded native times advertised by the latest eligible run.

        This is directory discovery only.  It does not fetch GRIB payloads or
        populate the selected-field cache; individual point/profile requests
        still fetch only their requested native lead and fields.
        """
        if selected_time.tzinfo is None:
            raise ValueError("RDPS selected time must include an offset")
        selected_hour = selected_time.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        self._adapter.demand_operation_bounds(1)
        with self._lock:
            candidate = self._discover(selected_hour)
        assert candidate.run_time is not None
        return tuple(
            candidate.run_time + timedelta(hours=int(lead))
            for lead in candidate.detail.get("available_hours", ())
            if 0 <= int(lead) < 85
        )

    def point_fields(self, latitude: float, longitude: float, selected_time: datetime):
        from .store import live_point_fields
        entry = self.query(selected_time, fields=RDPS_POINT_FIELDS)
        samples, sampler = self._samples(entry, latitude, longitude)
        class Samples:
            skipped, unmodelled = sampler.skipped, sampler.unmodelled
            @staticmethod
            def sample_point(*_args, **_kwargs): return samples
        return live_point_fields(Samples(), latitude, longitude, entry.valid_time)

    def profile_levels(self, latitude: float, longitude: float, selected_time: datetime, pressures):
        from .store import live_profile_levels
        fields = rdps_profile_fields(pressures)
        if not fields:
            raise ValueError("RDPS has no declared profile field at the requested pressures")
        entry = self.query(selected_time, fields=fields)
        by_pressure = {}
        sampler = None
        for pressure in pressures:
            by_pressure[pressure], sampler = self._samples(entry, latitude, longitude, pressure=pressure)
        assert sampler is not None
        class Samples:
            skipped, unmodelled = sampler.skipped, sampler.unmodelled
            @staticmethod
            def sample_profile(*_args, **_kwargs): return by_pressure
        levels = live_profile_levels(Samples(), latitude, longitude, entry.valid_time, pressures)
        return levels, entry.valid_time

    @staticmethod
    def _samples(entry: RDPSQueryEntry, latitude: float, longitude: float, *, pressure: int | None = None):
        from .store import LiveStore
        with tempfile.TemporaryDirectory(prefix="rdps-demand-read-") as directory:
            path = Path(directory) / "surface.zarr.zip"
            path.write_bytes(entry.payload)
            import xarray
            import zarr
            zipped = zarr.storage.ZipStore(str(path), mode="r")
            dataset = xarray.open_zarr(zipped, consolidated=False)
            sampler = LiveStore.__new__(LiveStore)
            sampler.skipped, sampler.unmodelled = [], []
            try:
                artifact = SimpleNamespace(source_id="eccc-rdps", logical_name="surface",
                    revision_id=f"demand:{entry.content_digest}", provenance=dict(entry.provenance),
                    run_time=entry.run_time, retrieved_at=entry.fetched_at,
                    native_crs=str(entry.provenance.get("native_crs", "EPSG:4326")))
                samples = sampler._sample_dataset(dataset, artifact, latitude, longitude, entry.valid_time, pressure=pressure)
            finally:
                dataset.close(); zipped.close()
        return samples, sampler

    def _discover(self, selected_time: datetime) -> RunCandidate:
        now = self._clock()
        if self._candidate and now < self._candidate[0]:
            candidate = self._candidate[1]
            if candidate.run_time and candidate.run_time <= selected_time:
                lead = (selected_time - candidate.run_time).total_seconds() / 3600
                if lead.is_integer() and int(lead) in {int(v) for v in candidate.detail.get("available_hours", ())}:
                    return candidate
        candidates = self._adapter.discover(FetchWindow(now=min(selected_time, self._now()), back_hours=24, forward_hours=0))
        eligible = [c for c in candidates if c.run_time and c.run_time <= selected_time and
                    (selected_time - c.run_time).total_seconds() % 3600 == 0 and
                    int((selected_time - c.run_time).total_seconds() // 3600) in {int(v) for v in c.detail.get("available_hours", ())}]
        if not eligible:
            raise ValueError("RDPS provider exposes no run with the selected native time")
        candidate = max(eligible, key=lambda c: c.run_time)
        self._candidate = (now + RDPS_CACHE_TTL_SECONDS, candidate)
        return candidate

    def _load(self, key: RDPSRequestKey) -> RDPSQueryEntry:
        candidate = self._prepared[key]
        assert candidate.run_time is not None
        selected = candidate.run_time + timedelta(hours=key.lead)
        with tempfile.TemporaryDirectory(prefix="rdps-demand-") as directory:
            output = Path(directory) / "result.zip"
            request = {"run_time": candidate.run_time.isoformat(), "selected_time": selected.isoformat(),
                       "provider_run_id": candidate.provider_run_id, "detail": candidate.detail,
                       "fields": key.fields, "bounds": dict(key.bounds), "base_url": self._adapter._base_url}
            run_bounded_process(command=[sys.executable, "-m", "weather_api.rdps_query_worker", "{output}"],
                                stdin=json.dumps(request).encode(), destination=output,
                                limits=RDPS_LIMITS, timeout_seconds=180)
            with zipfile.ZipFile(output) as bundle:
                if set(bundle.namelist()) != {"result.json", "surface.zarr.zip"} or len(bundle.infolist()) != 2:
                    raise ValueError("RDPS child returned unexpected bundle members")
                if sum(info.file_size for info in bundle.infolist()) > RDPS_LIMITS.output_bytes:
                    raise ValueError("RDPS child bundle expands beyond output ceiling")
                info = json.loads(bundle.read("result.json"))
                if (info["source_id"] != "eccc-rdps" or not info["complete"] or not info["qc_passed"]
                    or info["provider_run_id"] != candidate.provider_run_id
                    or datetime.fromisoformat(info["run_time"]) != candidate.run_time
                    or datetime.fromisoformat(info["valid_time"]) != selected):
                    raise ValueError("RDPS child returned invalid identity or QC")
                payload = bundle.read("surface.zarr.zip")
            return RDPSQueryEntry(key, candidate.run_time, selected, datetime.fromisoformat(info["retrieved_at"]),
                                  hashlib.sha256(payload).hexdigest(), payload, info["provenance"])



def rdps_query_coordinator() -> RDPSQueryCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = RDPSQueryCoordinator()
    return _COORDINATOR
