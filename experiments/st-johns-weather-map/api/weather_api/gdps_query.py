"""Selected-native-time GDPS query with a finite process-local cache."""
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
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Mapping

from ingest.adapters.eccc_datamart import (
    AVALON_CORE_BOUNDS,
    ECCCDataMartAdapter,
    GDPS_DEMAND_VARS,
)
from .native_runs import NativeRunInventory, RunUnavailable
from ingest.contract import FetchWindow, RunCandidate
from .models import GDPSAcquisition, GDPSDemandRequest, GDPSDemandUnavailable

GDPS_POINT_FIELDS = (
    "temperature_2m",
    "dew_point_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "mean_sea_level_pressure",
)
def gdps_profile_fields(pressures) -> tuple[str, ...]:
    """Only provider fields the requested profile levels can expose."""
    available = set(GDPS_DEMAND_VARS)
    ordered: list[str] = []
    for pressure in pressures:
        for prefix in ("relative_humidity", "temperature", "geopotential_height", "wind_speed", "wind_direction", "omega"):
            name = f"{prefix}_{int(pressure)}hPa"
            if name in available and name not in ordered:
                ordered.append(name)
    return tuple(ordered)
GDPS_CACHE_TTL_SECONDS = 600.0
GDPS_CACHE_MAX_ENTRIES = 4
GDPS_CACHE_MAX_BYTES = 32 * 1024 * 1024
GDPS_LIMITS = ProcessAllocationLimits(2 * 1024 * 1024 * 1024, 16 * 1024 * 1024, 2 * 1024 * 1024, 64 * 1024, 256 * 1024)
GDPS_FAILURE_BACKOFF_SECONDS = 60.0
_COORDINATOR: "GDPSQueryCoordinator | None" = None


@dataclass(frozen=True)
class GDPSRequestKey:
    cycle_url: str
    provider_run_id: str
    lead: int
    fields: tuple[str, ...]
    bounds: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class GDPSQueryEntry:
    key: GDPSRequestKey
    run_time: datetime
    valid_time: datetime
    fetched_at: datetime
    content_digest: str
    payload: bytes
    provenance: Mapping[str, object]
    acquisition: GDPSAcquisition | None = None

    @property
    def backing_bytes(self) -> int:
        return (len(self.payload) + len(json.dumps(self.provenance, sort_keys=True, default=str).encode())
                + (len(self.acquisition.model_dump_json().encode()) if self.acquisition else 0))


class GDPSQueryUnavailable(RuntimeError):
    """Unavailable outcome with bounded identity, never cached native values."""

    def __init__(self, outcome: GDPSDemandUnavailable):
        super().__init__(f"GDPS {outcome.reason}: {outcome.error_type}")
        self.outcome = outcome


class GDPSQueryService:
    """Coalesce and cache exact provider run/lead/field requests."""

    def __init__(self, loader: Callable[[GDPSRequestKey], GDPSQueryEntry], *,
                 ttl_seconds: float = GDPS_CACHE_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        if ttl_seconds <= 0 or ttl_seconds > GDPS_CACHE_TTL_SECONDS:
            raise ValueError("GDPS cache TTL is outside its source-local ceiling")
        self._loader, self._ttl, self._clock, self._now = loader, ttl_seconds, clock, now
        self._lock = threading.Lock()
        self._entries: OrderedDict[GDPSRequestKey, tuple[float, GDPSQueryEntry]] = OrderedDict()
        self._inflight: dict[GDPSRequestKey, Future[GDPSQueryEntry]] = {}
        self._failures: dict[GDPSRequestKey, tuple[float, GDPSDemandUnavailable]] = {}
        self._expired: OrderedDict[GDPSRequestKey, tuple[float, GDPSAcquisition]] = OrderedDict()

    def _prune_locked(self, now: float) -> None:
        # Sweep expired values on every lookup, retaining only bounded
        # identity for one further TTL. Neither bookkeeping map owns an
        # exception traceback, which could otherwise keep ZIP locals alive.
        for old_key, (deadline, old_entry) in list(self._entries.items()):
            if now >= deadline:
                del self._entries[old_key]
                if old_entry.acquisition is not None and now < deadline + self._ttl:
                    self._expired[old_key] = (deadline + self._ttl, old_entry.acquisition)
        for old_key, (deadline, _) in list(self._expired.items()):
            if now >= deadline:
                del self._expired[old_key]
        while len(self._expired) > GDPS_CACHE_MAX_ENTRIES:
            self._expired.popitem(last=False)
        for old_key, (deadline, _) in list(self._failures.items()):
            if now >= deadline:
                del self._failures[old_key]

    def expired_acquisition(self, key: GDPSRequestKey) -> GDPSAcquisition | None:
        """Disclose identity even when directory refresh fails before loading."""
        with self._lock:
            self._prune_locked(self._clock())
            expired = self._expired.get(key)
            return expired[1] if expired else None

    def query(self, key: GDPSRequestKey) -> GDPSQueryEntry:
        with self._lock:
            now = self._clock()
            self._prune_locked(now)
            cached = self._entries.get(key)
            if cached and now < cached[0]:
                self._entries.move_to_end(key)
                return cached[1]
            self._entries.pop(key, None)
            failure = self._failures.get(key)
            if failure and now < failure[0]:
                raise GDPSQueryUnavailable(failure[1])
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
                raise ValueError("GDPS loader returned a different request identity")
            if not 0 < entry.backing_bytes <= GDPS_CACHE_MAX_BYTES:
                raise ValueError("GDPS cache entry exceeds its finite byte ceiling")
            cached_at = self._now()
            acquisition = GDPSAcquisition(
                request=GDPSDemandRequest(cycle_url=key.cycle_url, provider_run_id=key.provider_run_id,
                    lead=key.lead, fields=key.fields, bounds=dict(key.bounds)),
                run_time=entry.run_time, valid_time=entry.valid_time, retrieval_time=entry.fetched_at,
                normalized_sha256=entry.content_digest,
                transport_receipts=entry.provenance.get("transport_receipts", ()),
                cached_at=cached_at, expires_at=cached_at + timedelta(seconds=self._ttl),
            )
            entry = replace(entry, acquisition=acquisition)
            if entry.backing_bytes > GDPS_CACHE_MAX_BYTES:
                raise ValueError("GDPS cache entry exceeds its finite byte ceiling")
            with self._lock:
                self._expired.pop(key, None)
                self._entries[key] = (self._clock() + self._ttl, entry)
                while len(self._entries) > GDPS_CACHE_MAX_ENTRIES or sum(v.backing_bytes for _, v in self._entries.values()) > GDPS_CACHE_MAX_BYTES:
                    self._entries.popitem(last=False)
            future.set_result(entry)
            return entry
        except BaseException as error:
            with self._lock:
                expired = self._expired.get(key)
                if expired and self._clock() >= expired[0]:
                    self._expired.pop(key, None)
                    expired = None
                outcome = GDPSDemandUnavailable(
                    reason="refresh_failed" if expired else "query_failed",
                    error_type=type(error).__name__,
                    expired_acquisition=expired[1] if expired else None,
                )
                # Do not let failure backoff extend expired metadata retention.
                deadline = self._clock() + GDPS_FAILURE_BACKOFF_SECONDS
                if expired:
                    deadline = min(deadline, expired[0])
                self._failures[key] = (deadline, outcome)
                while len(self._failures) > GDPS_CACHE_MAX_ENTRIES:
                    self._failures.pop(next(iter(self._failures)))
            unavailable = GDPSQueryUnavailable(outcome)
            future.set_exception(unavailable)
            raise unavailable from error
        finally:
            with self._lock:
                self._inflight.pop(key, None)


class GDPSQueryCoordinator:
    def __init__(self, adapter: ECCCDataMartAdapter | None = None, *,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC),
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._adapter = adapter or ECCCDataMartAdapter(source_id="eccc-gdps", model_subpath="model_gdps/15km", grid_token="LatLon0.15", var_map=GDPS_DEMAND_VARS, bounds=AVALON_CORE_BOUNDS, adapter_version="gdps-demand-v1")
        self._now, self._clock = now, clock
        self._candidate: tuple[float, RunCandidate] | None = None
        self._run_inventory = NativeRunInventory(lambda window: self._adapter.discover(window), now=now, clock=clock, ttl=GDPS_CACHE_TTL_SECONDS)
        self._prepared: dict[GDPSRequestKey, RunCandidate] = {}
        self._lock = threading.Lock()
        self._cache = GDPSQueryService(self._load, clock=clock, now=now)

    def query(self, selected_time: datetime, *, fields: tuple[str, ...] = GDPS_POINT_FIELDS, run_id: str | None = None) -> GDPSQueryEntry:
        if selected_time.tzinfo is None:
            raise ValueError("GDPS selected time must include an offset")
        fields = tuple(sorted(set(fields)))
        if not fields or set(fields) - set(self._adapter.var_map):
            raise ValueError("GDPS unsupported field set")
        requested_time = selected_time.astimezone(UTC)
        selected_time = requested_time.replace(minute=0, second=0, microsecond=0)
        if requested_time - selected_time >= timedelta(hours=1):  # defensive; floor is always under one hour
            raise ValueError("GDPS latest native time is too old for the selection")
        # This gate precedes even bounded directory discovery: listings are
        # provider payload too, so an unsupported runtime never opens one.
        self._adapter.demand_operation_bounds(len(fields))
        with self._lock:
            try:
                candidate = self._run_inventory.resolve(run_id) if run_id is not None else self._discover(selected_time)
            except RunUnavailable:
                raise
            except Exception as error:
                # An expired directory candidate is identity evidence only;
                # it must never authorize a fetch or a cached-value fallback.
                expired = None
                if run_id is None and self._candidate is not None:
                    prior = self._candidate[1]
                    if prior.run_time is not None:
                        lead = int((selected_time - prior.run_time).total_seconds() // 3600)
                        prior_key = GDPSRequestKey(str(prior.detail["cycle_url"]), prior.provider_run_id,
                            lead, fields, tuple(sorted(self._adapter.bounds.items())))
                        expired = self._cache.expired_acquisition(prior_key)
                raise GDPSQueryUnavailable(GDPSDemandUnavailable(
                    reason="refresh_failed" if expired else "query_failed",
                    error_type=type(error).__name__, expired_acquisition=expired,
                )) from error
            assert candidate.run_time is not None
            seconds = (selected_time - candidate.run_time).total_seconds()
            if seconds < 0 or seconds % 3600:
                raise ValueError("GDPS has no exact native hourly time for the selection")
            lead = int(seconds // 3600)
            available = {int(value) for value in candidate.detail.get("available_hours", ())}
            if lead not in available or not 0 <= lead < 241:
                raise ValueError("GDPS has no exact native lead for the selection")
            key = GDPSRequestKey(str(candidate.detail["cycle_url"]), candidate.provider_run_id,
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
            raise ValueError("GDPS selected time must include an offset")
        selected_hour = selected_time.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        self._adapter.demand_operation_bounds(1)
        with self._lock:
            candidate = self._discover(selected_hour)
        assert candidate.run_time is not None
        return tuple(
            candidate.run_time + timedelta(hours=int(lead))
            for lead in candidate.detail.get("available_hours", ())
            if 0 <= int(lead) < 241
        )

    def run_inventory(self):
        self._adapter.demand_operation_bounds(1)
        return self._run_inventory.candidates()

    def run_times(self, run_id: str):
        self._adapter.demand_operation_bounds(1)
        candidate = self._run_inventory.resolve(run_id)
        return tuple(candidate.run_time + timedelta(hours=int(lead)) for lead in candidate.detail.get("available_hours", ()) if 0 <= int(lead) < 241)

    def point_fields(self, latitude: float, longitude: float, selected_time: datetime, *, run_id: str | None = None):
        from .store import live_point_fields
        entry = self.query(selected_time, fields=GDPS_POINT_FIELDS, **({"run_id": run_id} if run_id is not None else {}))
        samples, sampler = self._samples(entry, latitude, longitude)
        class Samples:
            skipped, unmodelled = sampler.skipped, sampler.unmodelled
            @staticmethod
            def sample_point(*_args, **_kwargs): return samples
        return live_point_fields(Samples(), latitude, longitude, entry.valid_time)

    def profile_levels(self, latitude: float, longitude: float, selected_time: datetime, pressures):
        from .store import live_profile_levels
        fields = gdps_profile_fields(pressures)
        if not fields:
            raise ValueError("GDPS has no declared profile field at the requested pressures")
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
    def _samples(entry: GDPSQueryEntry, latitude: float, longitude: float, *, pressure: int | None = None):
        from .store import LiveStore
        with tempfile.TemporaryDirectory(prefix="gdps-demand-read-") as directory:
            path = Path(directory) / "surface.zarr.zip"
            path.write_bytes(entry.payload)
            import xarray
            import zarr
            zipped = zarr.storage.ZipStore(str(path), mode="r")
            dataset = xarray.open_zarr(zipped, consolidated=False)
            sampler = LiveStore.__new__(LiveStore)
            sampler.skipped, sampler.unmodelled = [], []
            try:
                artifact = SimpleNamespace(source_id="eccc-gdps", logical_name="surface",
                    revision_id=f"demand:{entry.content_digest}", provenance={**entry.provenance,
                        "demand_acquisition": entry.acquisition},
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
            raise ValueError("GDPS provider exposes no run with the selected native time")
        candidate = max(eligible, key=lambda c: c.run_time)
        self._candidate = (now + GDPS_CACHE_TTL_SECONDS, candidate)
        return candidate

    def _load(self, key: GDPSRequestKey) -> GDPSQueryEntry:
        candidate = self._prepared[key]
        assert candidate.run_time is not None
        selected = candidate.run_time + timedelta(hours=key.lead)
        with tempfile.TemporaryDirectory(prefix="gdps-demand-") as directory:
            output = Path(directory) / "result.zip"
            request = {"run_time": candidate.run_time.isoformat(), "selected_time": selected.isoformat(),
                       "provider_run_id": candidate.provider_run_id, "detail": candidate.detail,
                       "fields": key.fields, "bounds": dict(key.bounds), "base_url": self._adapter._base_url}
            run_bounded_process(command=[sys.executable, "-m", "weather_api.gdps_query_worker", "{output}"],
                                stdin=json.dumps(request).encode(), destination=output,
                                limits=GDPS_LIMITS, timeout_seconds=180)
            with zipfile.ZipFile(output) as bundle:
                if set(bundle.namelist()) != {"result.json", "surface.zarr.zip"} or len(bundle.infolist()) != 2:
                    raise ValueError("GDPS child returned unexpected bundle members")
                if sum(info.file_size for info in bundle.infolist()) > GDPS_LIMITS.output_bytes:
                    raise ValueError("GDPS child bundle expands beyond output ceiling")
                info = json.loads(bundle.read("result.json"))
                if (info["source_id"] != "eccc-gdps" or not info["complete"] or not info["qc_passed"]
                    or info["provider_run_id"] != candidate.provider_run_id
                    or datetime.fromisoformat(info["run_time"]) != candidate.run_time
                    or datetime.fromisoformat(info["valid_time"]) != selected):
                    raise ValueError("GDPS child returned invalid identity or QC")
                payload = bundle.read("surface.zarr.zip")
            return GDPSQueryEntry(key, candidate.run_time, selected, datetime.fromisoformat(info["retrieved_at"]),
                                  hashlib.sha256(payload).hexdigest(), payload, info["provenance"])



def gdps_query_coordinator() -> GDPSQueryCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = GDPSQueryCoordinator()
    return _COORDINATOR
