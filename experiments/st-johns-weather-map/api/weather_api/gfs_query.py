"""Source-local coalescing cache for selected-timestamp NOAA GFS queries."""

from __future__ import annotations

import threading
import time
import json
import hashlib
import tempfile
import sys
import zipfile
import re
import xml.etree.ElementTree as ElementTree
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from ingest.adapters.noaa_s3 import (
    GFS_IDX_SELECTORS,
    MAX_IDX_BYTES,
    NOAAS3Adapter,
    cap_open_range,
    gfs_native_lead,
    gfs_native_time_at_or_before,
    select_gfs_ranges,
)
from ingest.contract import RunCandidate
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

from .native_runs import NativeRunInventory, RunUnavailable

GFS_OBJECT_CACHE_TTL_SECONDS = 600.0
GFS_TIMELINE_LISTING_MAX_BYTES = 1024 * 1024
GFS_TIMELINE_LISTING_MAX_KEYS = 1000
GFS_TIMELINE_LISTING_MAX_NODES = 8 * GFS_TIMELINE_LISTING_MAX_KEYS + 64
GFS_CACHE_MAX_ENTRIES = 4
GFS_CACHE_MAX_BYTES = 256 * 1024 * 1024
GFS_DEMAND_WORKSPACE_BYTES = 192 * 1024 * 1024
GFS_DEMAND_LIMITS = ProcessAllocationLimits(
    address_space_bytes=1 * 1024 * 1024 * 1024,
    output_bytes=64 * 1024 * 1024,
    # A 2 MiB sidecar can expand six-fold when control bytes are JSON escaped.
    stdin_bytes=16 * 1024 * 1024,
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

    def query(self, key: GFSRequestKey, *, refresh: bool = False) -> GFSQueryEntry:
        while True:
            with self._lock:
                now = self._clock()
                cached = self._entries.get(key)
                if cached is not None and now < cached[0] and not refresh:
                    self._entries.move_to_end(key)
                    return cached[1]
                if cached is not None and now >= cached[0]:
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
                    future.set_exception(error)
                    raise
                finally:
                    with self._lock:
                        self._inflight.pop(key, None)
            return future.result()

    def cached_valid_times(self) -> tuple[datetime, ...]:
        """Native instants already cached; this method performs no provider I/O."""
        with self._lock:
            current = self._clock()
            return tuple(sorted({entry.valid_time for expiry, entry in self._entries.values() if current < expiry}))

    def cached_entries(self) -> tuple[GFSQueryEntry, ...]:
        """Unexpired normalized entries, without provider or loader I/O."""
        with self._lock:
            current = self._clock()
            return tuple(entry for expiry, entry in self._entries.values() if current < expiry)


def hides_legacy_published_gfs_layer(source_id: str) -> bool:
    """Keep pre-demand GFS artifacts audit-readable without advertising them as live layers."""
    return source_id == "noaa-gfs"


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
        self._timeline_lock = threading.Lock()
        self._indices: OrderedDict[str, tuple[float, str, Mapping[str, object] | None]] = OrderedDict()
        self._timeline: OrderedDict[str, tuple[float, tuple[datetime, ...], Mapping[str, object]]] = OrderedDict()
        self._timeline_inflight: dict[str, Future[tuple[tuple[datetime, ...], Mapping[str, object]]]] = {}
        self._query_lock = threading.Lock()
        self._query_inflight: dict[tuple[datetime, str | None], Future[GFSQueryEntry]] = {}
        self._run_inventory = NativeRunInventory(self._adapter.discover, now=now, clock=clock, ttl=GFS_OBJECT_CACHE_TTL_SECONDS)
        self._prepared: dict[GFSRequestKey, RunCandidate] = {}
        self._bounded_fetch = bounded_fetch
        self._cache = GFSQueryService(self._load, clock=clock)

    def query(self, selected_time: datetime, *, run_id: str | None = None, refresh: bool = False) -> GFSQueryEntry:
        if selected_time.tzinfo is None:
            raise ValueError("GFS selected time must be timezone-aware")
        selection = (selected_time.astimezone(UTC).replace(minute=0, second=0, microsecond=0), run_id)
        with self._query_lock:
            future = self._query_inflight.get(selection)
            owner = future is None
            if owner:
                future = Future()
                self._query_inflight[selection] = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            entry = self._query(selected_time, run_id=run_id, refresh=refresh)
            future.set_result(entry)
            return entry
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._query_lock:
                self._query_inflight.pop(selection, None)

    def _query(self, selected_time: datetime, *, run_id: str | None, refresh: bool) -> GFSQueryEntry:
        candidate = (self._run_inventory.resolve(run_id, refresh=refresh)
                     if run_id is not None else self._discover(refresh=refresh))
        if run_id is not None:
            if candidate.run_time is None:
                raise RunUnavailable("GFS selected run has no producer run time")
            native = gfs_native_time_at_or_before(candidate.run_time, selected_time)
            times, _receipt = self._run_listing(candidate, refresh=refresh)
            if native not in times:
                raise RunUnavailable("GFS selected run has no listed native frame for this time")
        with self._lock:
            if candidate.run_time is None:
                raise ValueError("GFS discovery returned no producer run time")
            native_time = gfs_native_time_at_or_before(candidate.run_time, selected_time)
            lead = gfs_native_lead(candidate.run_time, native_time)
            date_str = str(candidate.detail["date_str"])
            cycle = str(candidate.detail["cycle"])
            stem = f"gfs.t{cycle}z.pgrb2.0p25.f{lead:03d}"
            grib_url = f"{self._adapter._base_url}/gfs.{date_str}/{cycle}/atmos/{stem}"
            idx_url = f"{grib_url}.idx"
            idx_text, idx_receipt = self._index(idx_url, refresh=refresh)
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
                {**candidate.detail, "idx_text_by_lead": {lead: idx_text}, "idx_receipts_by_lead": {lead: idx_receipt}},
            )
            try:
                return self._cache.query(key, refresh=refresh)
            finally:
                self._prepared.pop(key, None)

    def cached_valid_times(self) -> tuple[datetime, ...]:
        return self._cache.cached_valid_times()

    def cached_cloud_availability(self) -> Mapping[str, tuple[datetime, ...]]:
        """Cached native frames by actually present cloud field; no provider I/O."""
        fields = ("total_cloud_geometric", "cloud_low", "cloud_middle", "cloud_high")
        result: dict[str, list[datetime]] = {field: [] for field in fields}
        for entry in self._cache.cached_entries():
            present = set(entry.values.get("surface_fields", ()))
            for field in fields:
                if field in present:
                    result[field].append(entry.valid_time)
        return {field: tuple(sorted(set(times))) for field, times in result.items()}

    def point_fields(self, latitude: float, longitude: float, selected_time: datetime, *, run_id: str | None = None, refresh: bool = False) -> tuple[list[Any], Any, list[str]]:
        """Answer one point through the existing evidence/provenance builder.

        Demand payloads remain memory-resident cache entries.  They are opened
        only for this request and presented to the existing sampler as native
        retrieved artifacts; no ArtifactStore row or current revision is
        invented for the live-query path.
        """
        from .store import LiveStore, live_point_fields  # noqa: PLC0415

        entry = self.query(selected_time, **({"run_id": run_id} if run_id is not None else {}), **({"refresh": True} if refresh else {}))
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
                    provenance.setdefault("run_time", entry.run_time.isoformat())
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

    def profile_levels(self, latitude: float, longitude: float, selected_time: datetime, pressures: tuple[int, ...], *, run_id: str | None = None, refresh: bool = False) -> list[Any]:
        """Answer the existing pressure-level profile from one cached frame."""
        from .store import (  # noqa: PLC0415
            WIND_METHOD,
            LiveStore,
            _derived_evidence_field,
            _registered_wind,
            live_profile_levels,
        )
        from .science import WIND_DIRECTION_UNITS, WIND_SPEED_UNITS  # noqa: PLC0415

        entry = self.query(selected_time, **({"run_id": run_id} if run_id is not None else {}), **({"refresh": True} if refresh else {}))
        by_pressure: dict[int, list[Any]] = {}
        with tempfile.TemporaryDirectory(prefix="gfs-demand-profile-") as directory:
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
                    provenance.setdefault("run_time", entry.run_time.isoformat())
                    artifact = SimpleNamespace(
                        source_id="noaa-gfs",
                        logical_name=logical_name,
                        revision_id=f"demand:{entry.content_digest}:{logical_name}",
                        provenance=provenance,
                        run_time=entry.run_time,
                        retrieved_at=entry.fetched_at,
                        native_crs=provenance.get("native_crs", "EPSG:4326"),
                    )
                    for pressure in pressures:
                        found = sampler._sample_dataset(dataset, artifact, latitude, longitude, entry.valid_time, pressure=pressure)
                        if found:
                            by_pressure.setdefault(pressure, []).extend(found)
                finally:
                    dataset.close()
                    zipped.close()

        class _Samples:
            skipped = sampler.skipped
            unmodelled = sampler.unmodelled

            @staticmethod
            def sample_profile(*_args: object, **_kwargs: object) -> dict[int, list[Any]]:
                return by_pressure

        levels = live_profile_levels(_Samples(), latitude, longitude, entry.valid_time, pressures)
        for level in levels:
            samples = {sample.variable: sample for sample in by_pressure.get(level.pressure_hpa, [])}
            suffix = f"_{level.pressure_hpa}hPa"
            u_name, v_name = f"wind_u{suffix}", f"wind_v{suffix}"
            u, v = samples.get(u_name), samples.get(v_name)
            # Pressure-level components are derivation inputs, not standalone
            # profile readings. The profile exposes the same registered wind
            # representation as its existing fixture and UI contract.
            level.fields = [
                field.model_copy(update={"field": "temperature"}) if field.key == "temperature_pressure"
                else field.model_copy(update={"field": "relative_humidity"}) if field.key == "relative_humidity_pressure"
                else field
                for field in level.fields
                if field.field not in {u_name, v_name}
            ]
            if u is not None and v is not None and u.value is not None and v.value is not None:
                speed, direction = _registered_wind(u.value, v.value)
                for name, derived, units in (
                    ("wind_speed", speed, WIND_SPEED_UNITS),
                    ("wind_direction", direction, WIND_DIRECTION_UNITS),
                ):
                    level.fields.append(
                        _derived_evidence_field(
                            _Samples(),
                            field_name=name,
                            basis=replace(u, variable=name, value=derived.value, units=units),
                            inputs=[(u_name, u), (v_name, v)],
                            method=WIND_METHOD,
                            value=derived.value,
                            derivation=derived.derivation,
                            derivation_version=derived.version,
                            reference=datetime.now(UTC),
                        )
                    )
        return levels

    def cloud_raster(self, selected_time: datetime, *, layer_id: str, bounds: Mapping[str, float], width: int, height: int, crs: str):
        """Render one allowlisted cached native geometric-cloud grid."""
        from . import grids  # noqa: PLC0415
        if layer_id not in {
            "noaa-gfs-demand-total-cloud",
            "noaa-gfs-demand-cloud-low",
            "noaa-gfs-demand-cloud-middle",
            "noaa-gfs-demand-cloud-high",
        }:
            raise ValueError(f"unsupported GFS demand raster: {layer_id}")
        entry = self.query(selected_time)
        try:
            index = tuple(entry.values["logical_names"]).index("surface")
        except ValueError as error:
            raise grids.GridUnavailable("selected GFS response carries no surface grid") from error
        with tempfile.TemporaryDirectory(prefix="gfs-demand-raster-") as directory:
            path = Path(directory) / "surface.zarr.zip"
            path.write_bytes(entry.payloads[index])
            import xarray  # noqa: PLC0415
            import zarr  # noqa: PLC0415
            zipped = zarr.storage.ZipStore(str(path), mode="r")
            dataset = xarray.open_zarr(zipped, consolidated=False)
            artifact = SimpleNamespace(
                source_id="noaa-gfs", logical_name="surface",
                revision_id=f"demand:{entry.content_digest}:surface",
                provenance=entry.provenance["surface"], run_time=entry.run_time,
                retrieved_at=entry.fetched_at, native_crs="EPSG:4326",
            )
            class Store:
                def current(self): return [artifact]
                def open(self, _artifact): return dataset
            try:
                spec = grids.rendered_grid_spec(layer_id)
                assert spec is not None
                return grids.render_grid(Store(), spec, bounds=bounds, width=width, height=height, crs=crs, valid_time=entry.valid_time), entry
            finally:
                dataset.close()
                zipped.close()

    def total_cloud_raster(self, selected_time: datetime, *, bounds: Mapping[str, float], width: int, height: int, crs: str):
        """Compatibility wrapper for the first GFS demand raster."""
        return self.cloud_raster(selected_time, layer_id="noaa-gfs-demand-total-cloud", bounds=bounds, width=width, height=height, crs=crs)

    def native_resolution_seconds(self, selected_time: datetime, end: datetime) -> int:
        """Use the same producer lead boundary as exact GFS acquisition."""
        from ingest.adapters.noaa_s3 import GFS_HOURLY_LEAD_LIMIT
        candidate = self._discover()
        if candidate.run_time is None:
            raise ValueError('GFS run time unavailable')
        return 10800 if end - candidate.run_time > timedelta(hours=GFS_HOURLY_LEAD_LIMIT + 1) else 3600

    def run_inventory(self, *, refresh: bool = False):
        return self._run_inventory.candidates(refresh=refresh)

    def run_times(self, run_id: str, *, refresh: bool = False):
        candidate = self._run_inventory.resolve(run_id, refresh=refresh)
        return self._run_listing(candidate, refresh=refresh)[0]

    def timeline_times(self, reference: datetime, *, refresh: bool = False) -> tuple[tuple[datetime, ...], Mapping[str, object]]:
        """Return actual native frame keys within the current evidence window."""
        if reference.tzinfo is None:
            raise ValueError("reference must be timezone-aware")
        candidate = self._discover(refresh=refresh)
        times, receipt = self._run_listing(candidate, refresh=refresh)
        start, end = reference.astimezone(UTC) - timedelta(hours=24), reference.astimezone(UTC) + timedelta(days=14)
        return tuple(stamp for stamp in times if start <= stamp <= end), receipt

    def _run_listing(self, candidate: RunCandidate, *, refresh: bool = False) -> tuple[tuple[datetime, ...], Mapping[str, object]]:
        run_id = candidate.provider_run_id
        with self._timeline_lock:
            cached = self._timeline.get(run_id)
            if cached is not None and self._clock() < cached[0] and not refresh:
                return cached[1], cached[2]
            future = self._timeline_inflight.get(run_id)
            owner = future is None
            if owner:
                future = Future()
                self._timeline_inflight[run_id] = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            if candidate.run_time is None:
                raise ValueError("GFS candidate has no producer run time")
            date_str, cycle = str(candidate.detail["date_str"]), str(candidate.detail["cycle"])
            prefix = f"gfs.{date_str}/{cycle}/atmos/gfs.t{cycle}z.pgrb2.0p25.f"
            query = urlencode({"list-type": "2", "max-keys": GFS_TIMELINE_LISTING_MAX_KEYS, "prefix": prefix})
            body, receipt = self._adapter._get_client().get_bytes_with_receipt(
                f"{self._adapter._base_url}?{query}", max_bytes=GFS_TIMELINE_LISTING_MAX_BYTES
            )
            upper = body.upper()
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise ValueError("GFS listing declarations are unsupported")
            root = ElementTree.fromstring(body)
            if root.tag.rsplit("}", 1)[-1] != "ListBucketResult":
                raise ValueError("GFS listing has an unexpected root")
            nodes = list(root.iter())
            if len(nodes) > GFS_TIMELINE_LISTING_MAX_NODES:
                raise ValueError("GFS listing exceeds structural node bound")
            contents = [node for node in nodes if node.tag.rsplit("}", 1)[-1] == "Contents"]
            if len(contents) > GFS_TIMELINE_LISTING_MAX_KEYS:
                raise ValueError("GFS listing exceeds key bound")
            truncated = next((node.text for node in nodes if node.tag.rsplit("}", 1)[-1] == "IsTruncated"), "false")
            if str(truncated).lower() != "false":
                raise ValueError("GFS listing was truncated")
            leads: set[int] = set()
            for node in nodes:
                if node.tag.rsplit("}", 1)[-1] != "Key" or not isinstance(node.text, str) or not node.text.startswith(prefix):
                    continue
                match = re.fullmatch(re.escape(prefix) + r"(\d{3})\.idx", node.text)
                if match:
                    lead = int(match.group(1))
                    if lead <= 384 and (lead <= 120 or lead % 3 == 0):
                        leads.add(lead)
            times = tuple(candidate.run_time + timedelta(hours=lead) for lead in sorted(leads))
            result = (times, receipt)
            with self._timeline_lock:
                self._timeline[run_id] = (self._clock() + GFS_OBJECT_CACHE_TTL_SECONDS, times, receipt)
                self._timeline.move_to_end(run_id)
                while len(self._timeline) > 2:
                    self._timeline.popitem(last=False)
            future.set_result(result)
            return result
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._timeline_lock:
                self._timeline_inflight.pop(run_id, None)

    def _discover(self, *, refresh: bool = False) -> RunCandidate:
        candidates = self.run_inventory(refresh=refresh)
        if not candidates:
            raise RunUnavailable("No GFS run is available")
        return candidates[0]

    def _index(self, url: str, *, refresh: bool = False) -> tuple[str, Mapping[str, object] | None]:
        current = self._clock()
        cached = self._indices.get(url)
        if cached is not None and current < cached[0] and not refresh:
            self._indices.move_to_end(url)
            return cached[1], cached[2]
        client = self._adapter._get_client()
        if hasattr(client, "get_bytes_with_receipt"):
            raw, receipt = client.get_bytes_with_receipt(url, max_bytes=MAX_IDX_BYTES)
        else:
            raw, receipt = client.get_bytes(url, max_bytes=MAX_IDX_BYTES), None
        text = raw.decode("utf-8")
        self._indices[url] = (current + GFS_OBJECT_CACHE_TTL_SECONDS, text, receipt)
        while len(self._indices) > GFS_CACHE_MAX_ENTRIES:
            self._indices.popitem(last=False)
        return text, receipt

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
                    "base_url": self._adapter._base_url,
                    "bounds": self._adapter._bounds,
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
                if info.get("provider_run_id") != candidate.provider_run_id:
                    raise ValueError("GFS bounded child returned a different provider run")
                if datetime.fromisoformat(info["run_time"]) != candidate.run_time:
                    raise ValueError("GFS bounded child returned a different producer run time")
                if datetime.fromisoformat(info["valid_time"]) != self._selected_time(key, candidate):
                    raise ValueError("GFS bounded child returned a different native valid time")
                artifacts = info["artifacts"]
                if not artifacts or len(artifacts) > 2:
                    raise ValueError("GFS bounded child returned an invalid artifact set")
                logical_names = [artifact["logical_name"] for artifact in artifacts]
                if len(set(logical_names)) != len(logical_names) or set(logical_names) - {"surface", "upper_air"}:
                    raise ValueError("GFS bounded child returned invalid logical artifact names")
                expected_members = {"result.json", *(f"artifacts/{artifact['name']}" for artifact in artifacts)}
                if set(bundle.namelist()) != expected_members:
                    raise ValueError("GFS bounded child bundle contains unexpected members")
                if sum(member.file_size for member in bundle.infolist()) > GFS_DEMAND_LIMITS.output_bytes:
                    raise ValueError("GFS bounded child bundle expands beyond its output ceiling")
                payloads = tuple(bundle.read(f"artifacts/{artifact['name']}") for artifact in artifacts)
            digest = hashlib.sha256(b"".join(payloads)).hexdigest()
            provenance = {artifact["logical_name"]: artifact["provenance"] for artifact in artifacts}
            surface_fields: tuple[str, ...] = ()
            if "surface" in logical_names:
                surface_payload = payloads[logical_names.index("surface")]
                surface_path = Path(directory) / "validated-surface.zarr.zip"
                surface_path.write_bytes(surface_payload)
                import xarray  # noqa: PLC0415
                import zarr  # noqa: PLC0415
                surface_store = zarr.storage.ZipStore(str(surface_path), mode="r")
                surface_dataset = xarray.open_zarr(surface_store, consolidated=False)
                try:
                    surface_fields = tuple(sorted(str(name) for name in surface_dataset.data_vars))
                finally:
                    surface_dataset.close()
                    surface_store.close()
        return GFSQueryEntry(
            key=key,
            run_time=datetime.fromisoformat(info["run_time"]),
            valid_time=self._selected_time(key, candidate),
            fetched_at=datetime.fromisoformat(info["retrieved_at"]),
            content_digest=digest,
            values={"logical_names": [artifact["logical_name"] for artifact in artifacts], "surface_fields": surface_fields},
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
