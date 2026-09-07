"""Selected-native-time HRDPS query with a finite process-local cache."""
from __future__ import annotations

import hashlib
import json
import tempfile
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
    HRDPS_ADAPTER,
    HRDPS_FILE_BYTES,
    HRDPS_PROFILE_VARS,
    HRDPS_STEERING_VARS,
    HRDPS_OMEGA_VARS,
    HRDPS_THERMO_VARS,
)
from .native_runs import NativeRunInventory, RunUnavailable
from ingest.contract import FetchWindow, RunCandidate

HRDPS_POINT_FIELDS = (
    "temperature_2m", "dew_point_2m", "relative_humidity_2m",
    "wind_u_10m", "wind_v_10m", "mean_sea_level_pressure",
    "total_cloud_opacity",
)
def hrdps_profile_fields(pressures) -> tuple[str, ...]:
    """Only provider fields the requested profile levels can expose."""
    available = set(HRDPS_PROFILE_VARS) | set(HRDPS_STEERING_VARS) | set(HRDPS_OMEGA_VARS) | set(HRDPS_THERMO_VARS)
    ordered: list[str] = []
    for pressure in pressures:
        for prefix in ("relative_humidity", "temperature", "geopotential_height", "wind_u", "wind_v", "omega"):
            name = f"{prefix}_{int(pressure)}hPa"
            if name in available and name not in ordered:
                ordered.append(name)
    return tuple(ordered)
HRDPS_CACHE_TTL_SECONDS = 600.0
HRDPS_CACHE_MAX_ENTRIES = 4
HRDPS_CACHE_MAX_BYTES = 64 * 1024 * 1024
HRDPS_SELECTED_RECEIVED_BYTES = len(HRDPS_POINT_FIELDS) * HRDPS_FILE_BYTES
HRDPS_FAILURE_BACKOFF_SECONDS = 60.0
_COORDINATOR: "HRDPSQueryCoordinator | None" = None


@dataclass(frozen=True)
class HRDPSRequestKey:
    cycle_url: str
    provider_run_id: str
    lead: int
    fields: tuple[str, ...]
    bounds: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class HRDPSQueryEntry:
    key: HRDPSRequestKey
    run_time: datetime
    valid_time: datetime
    fetched_at: datetime
    content_digest: str
    payload: bytes
    provenance: Mapping[str, object]

    @property
    def backing_bytes(self) -> int:
        return len(self.payload) + len(json.dumps(self.provenance, sort_keys=True, default=str).encode())


class HRDPSQueryService:
    """Coalesce and cache exact provider run/lead/field requests."""

    def __init__(self, loader: Callable[[HRDPSRequestKey], HRDPSQueryEntry], *,
                 ttl_seconds: float = HRDPS_CACHE_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if ttl_seconds <= 0 or ttl_seconds > HRDPS_CACHE_TTL_SECONDS:
            raise ValueError("HRDPS cache TTL is outside its source-local ceiling")
        self._loader, self._ttl, self._clock = loader, ttl_seconds, clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[HRDPSRequestKey, tuple[float, HRDPSQueryEntry]] = OrderedDict()
        self._inflight: dict[HRDPSRequestKey, Future[HRDPSQueryEntry]] = {}
        self._failures: dict[HRDPSRequestKey, tuple[float, BaseException]] = {}

    def query(self, key: HRDPSRequestKey, *, refresh: bool = False) -> HRDPSQueryEntry:
        with self._lock:
            now = self._clock()
            cached = self._entries.get(key)
            if not refresh and cached and now < cached[0]:
                self._entries.move_to_end(key)
                return cached[1]
            if cached and now >= cached[0]:
                self._entries.pop(key, None)
            failure = self._failures.get(key)
            if not refresh and failure and now < failure[0]:
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
                raise ValueError("HRDPS loader returned a different request identity")
            if not 0 < entry.backing_bytes <= HRDPS_CACHE_MAX_BYTES:
                raise ValueError("HRDPS cache entry exceeds its finite byte ceiling")
            with self._lock:
                self._entries[key] = (self._clock() + self._ttl, entry)
                while len(self._entries) > HRDPS_CACHE_MAX_ENTRIES or sum(v.backing_bytes for _, v in self._entries.values()) > HRDPS_CACHE_MAX_BYTES:
                    self._entries.popitem(last=False)
            future.set_result(entry)
            return entry
        except BaseException as error:
            with self._lock:
                self._failures[key] = (self._clock() + HRDPS_FAILURE_BACKOFF_SECONDS, error)
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)


class HRDPSQueryCoordinator:
    def __init__(self, adapter: ECCCDataMartAdapter | None = None, *,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC),
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._adapter = adapter or HRDPS_ADAPTER
        self._now, self._clock = now, clock
        self._candidate: tuple[float, RunCandidate] | None = None
        self._run_inventory = NativeRunInventory(lambda window: self._adapter.discover(window), now=now, clock=clock, ttl=HRDPS_CACHE_TTL_SECONDS)
        self._prepared: dict[HRDPSRequestKey, RunCandidate] = {}
        self._lock = threading.Lock()
        self._cache = HRDPSQueryService(self._load, clock=clock)
        self._refresh_lock = threading.Lock()
        self._refreshes: dict[tuple, Future] = {}

    def query(self, selected_time: datetime, *, fields: tuple[str, ...] = HRDPS_POINT_FIELDS,
              run_id: str | None = None, refresh: bool = False) -> HRDPSQueryEntry:
        if not refresh:
            return self._query(selected_time, fields=fields, run_id=run_id)
        # Coalesce the complete refresh before the coordinator's existing
        # acquisition lock, including discovery and the native payload read.
        request = (selected_time, tuple(fields), run_id)
        with self._refresh_lock:
            future = self._refreshes.get(request)
            owner = future is None
            if owner:
                if len(self._refreshes) >= HRDPS_CACHE_MAX_ENTRIES:
                    raise ValueError("HRDPS concurrent refresh bound reached")
                future = Future()
                self._refreshes[request] = future
        if not owner:
            return future.result()
        try:
            entry = self._query(selected_time, fields=fields, run_id=run_id, refresh=True)
            future.set_result(entry)
            return entry
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._refresh_lock:
                self._refreshes.pop(request, None)

    def _query(self, selected_time: datetime, *, fields: tuple[str, ...] = HRDPS_POINT_FIELDS,
               run_id: str | None = None, refresh: bool = False) -> HRDPSQueryEntry:
        if selected_time.tzinfo is None:
            raise ValueError("HRDPS selected time must include an offset")
        requested_time = selected_time.astimezone(UTC)
        selected_time = requested_time.replace(minute=0, second=0, microsecond=0)
        if requested_time - selected_time >= timedelta(hours=1):  # defensive; floor is always under one hour
            raise ValueError("HRDPS latest native time is too old for the selection")
        # This gate precedes even bounded directory discovery: listings are
        # provider payload too, so an unsupported runtime never opens one.
        self._adapter.demand_operation_bounds(len(fields))
        with self._lock:
            candidate = self._run_inventory.resolve(run_id, refresh=refresh) if run_id is not None else self._discover(selected_time, refresh=refresh)
            assert candidate.run_time is not None
            seconds = (selected_time - candidate.run_time).total_seconds()
            if seconds < 0 or seconds % 3600:
                raise ValueError("HRDPS has no exact native hourly time for the selection")
            lead = int(seconds // 3600)
            available = {int(value) for value in candidate.detail.get("available_hours", ())}
            if lead not in available or not 0 <= lead < 25:
                raise ValueError("HRDPS has no exact native lead for the selection")
            key = HRDPSRequestKey(str(candidate.detail["cycle_url"]), candidate.provider_run_id,
                                  lead, tuple(fields), tuple(sorted(AVALON_CORE_BOUNDS.items())))
            self._prepared[key] = candidate
            try:
                return self._cache.query(key, refresh=refresh)
            finally:
                self._prepared.pop(key, None)

    def timeline_times(self, selected_time: datetime) -> tuple[datetime, ...]:
        """Return the bounded native times advertised by the latest eligible run.

        This is directory discovery only.  It does not fetch GRIB payloads or
        populate the selected-field cache; individual point/profile requests
        still fetch only their requested native lead and fields.
        """
        if selected_time.tzinfo is None:
            raise ValueError("HRDPS selected time must include an offset")
        selected_hour = selected_time.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        self._adapter.demand_operation_bounds(1)
        with self._lock:
            candidate = self._discover(selected_hour)
        assert candidate.run_time is not None
        return tuple(
            candidate.run_time + timedelta(hours=int(lead))
            for lead in candidate.detail.get("available_hours", ())
            if 0 <= int(lead) < 25
        )

    def run_inventory(self):
        self._adapter.demand_operation_bounds(1)
        return self._run_inventory.candidates()

    def run_times(self, run_id: str):
        self._adapter.demand_operation_bounds(1)
        candidate = self._run_inventory.resolve(run_id)
        return tuple(candidate.run_time + timedelta(hours=int(lead)) for lead in candidate.detail.get("available_hours", ()) if 0 <= int(lead) < 25)

    def point_fields(self, latitude: float, longitude: float, selected_time: datetime, *, run_id: str | None = None, refresh: bool = False):
        from .store import LiveStore, live_point_fields
        entry = self.query(selected_time, fields=HRDPS_POINT_FIELDS, **({"run_id": run_id} if run_id is not None else {}), **({"refresh": True} if refresh else {}))
        samples, sampler = self._samples(entry, latitude, longitude)
        class Samples:
            skipped, unmodelled = sampler.skipped, sampler.unmodelled
            @staticmethod
            def sample_point(*_args, **_kwargs): return samples
        return live_point_fields(Samples(), latitude, longitude, entry.valid_time)

    def profile_levels(self, latitude: float, longitude: float, selected_time: datetime, pressures):
        from .store import live_profile_levels
        fields = hrdps_profile_fields(pressures)
        if not fields:
            raise ValueError("HRDPS has no declared profile field at the requested pressures")
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
        return live_profile_levels(Samples(), latitude, longitude, entry.valid_time, pressures), entry.valid_time

    @staticmethod
    def _samples(entry: HRDPSQueryEntry, latitude: float, longitude: float, *, pressure: int | None = None):
        from .store import LiveStore
        with tempfile.TemporaryDirectory(prefix="hrdps-demand-read-") as directory:
            path = Path(directory) / "surface.zarr.zip"
            path.write_bytes(entry.payload)
            import xarray
            import zarr
            zipped = zarr.storage.ZipStore(str(path), mode="r")
            dataset = xarray.open_zarr(zipped, consolidated=False)
            sampler = LiveStore.__new__(LiveStore)
            sampler.skipped, sampler.unmodelled = [], []
            try:
                artifact = SimpleNamespace(source_id="eccc-hrdps", logical_name="surface",
                    revision_id=f"demand:{entry.content_digest}", provenance=dict(entry.provenance),
                    run_time=entry.run_time, retrieved_at=entry.fetched_at,
                    native_crs=str(entry.provenance.get("native_crs", "EPSG:4326")))
                samples = sampler._sample_dataset(dataset, artifact, latitude, longitude, entry.valid_time, pressure=pressure)
            finally:
                dataset.close(); zipped.close()
        return samples, sampler

    def _discover(self, selected_time: datetime, *, refresh: bool = False) -> RunCandidate:
        now = self._clock()
        if not refresh and self._candidate and now < self._candidate[0]:
            candidate = self._candidate[1]
            if candidate.run_time and candidate.run_time <= selected_time:
                lead = (selected_time - candidate.run_time).total_seconds() / 3600
                if lead.is_integer() and int(lead) in {int(v) for v in candidate.detail.get("available_hours", ())}:
                    return candidate
        candidates = self._adapter.discover(FetchWindow(now=selected_time, back_hours=24, forward_hours=0))
        eligible = [c for c in candidates if c.run_time and c.run_time <= selected_time and
                    (selected_time - c.run_time).total_seconds() % 3600 == 0 and
                    int((selected_time - c.run_time).total_seconds() // 3600) in {int(v) for v in c.detail.get("available_hours", ())}]
        if not eligible:
            raise ValueError("HRDPS provider exposes no run with the selected native time")
        candidate = max(eligible, key=lambda c: c.run_time)
        self._candidate = (self._clock() + HRDPS_CACHE_TTL_SECONDS, candidate)
        return candidate

    def _load(self, key: HRDPSRequestKey) -> HRDPSQueryEntry:
        candidate = self._prepared[key]
        assert candidate.run_time is not None
        selected = candidate.run_time + timedelta(hours=key.lead)
        # The full-run measurement is deliberately reused as a conservative
        # pre-payload platform gate until a smaller selected-field envelope is
        # independently measured. Different keys are serialised by the
        # coordinator lock, while cached ZIPs count against the finite cache.
        with tempfile.TemporaryDirectory(prefix="hrdps-demand-") as directory:
            result = self._adapter.fetch_selected(candidate, selected, Path(directory), fields=key.fields)
            artifact = result.artifacts[0]
            payload = artifact.payload_path.read_bytes()
        return HRDPSQueryEntry(key, result.run_time, selected, result.retrieved_at,
                               hashlib.sha256(payload).hexdigest(), payload, artifact.provenance)


def hrdps_query_coordinator() -> HRDPSQueryCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = HRDPSQueryCoordinator()
    return _COORDINATOR
