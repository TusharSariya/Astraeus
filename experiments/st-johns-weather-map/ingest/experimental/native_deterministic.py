"""Unregistered native deterministic acquisition candidates for issue 81.

Nothing in this module is imported by :mod:`ingest.adapters`.  The accepted
specification corpus has governance but no accepted source contract, so these
objects may build review evidence but cannot publish or be scheduled.
"""

from __future__ import annotations

import bz2
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy
import xarray

from ingest.contract import MEDIA_ZARR, AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
from ingest.grib import write_zarr
from ingest.http import PoliteClient

UTC = timezone.utc
EVIDENCE_BOUNDS = {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_MESSAGE_BYTES = 16 * 1024 * 1024
ECMWF_BASE = "https://data.ecmwf.int/forecasts"
RAP_BASE = "https://noaa-rap-pds.s3.amazonaws.com"
NAM_BASE = "https://noaa-nam-pds.s3.amazonaws.com"
DWD_BASE = "https://opendata.dwd.de/weather/nwp/icon/grib"

PRESSURE_LEVELS = (1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50, 10)
AIFS_Q_LEVELS = tuple(level for level in PRESSURE_LEVELS if level != 10)


@dataclass(frozen=True)
class FieldSelection:
    upstream: str
    canonical: str | None
    native_units: str
    level_type: str
    levels: tuple[int, ...] = ()
    disposition: str = "selected"
    note: str = ""


ECMWF_SURFACE = (
    FieldSelection("2t", "temperature_2m", "K", "sfc"),
    FieldSelection("2d", "dew_point_2m", "K", "sfc"),
    FieldSelection("10u", "wind_u_10m", "m s-1", "sfc"),
    FieldSelection("10v", "wind_v_10m", "m s-1", "sfc"),
    FieldSelection("msl", "mean_sea_level_pressure", "Pa", "sfc"),
    FieldSelection("tp", None, "provider-coded", "sfc", note="lead-0 initialization is retained raw; no nonzero accumulation interval is claimed"),
    FieldSelection("tcwv", "precipitable_water", "kg m-2", "sfc"),
    FieldSelection("tcc", "total_cloud_geometric", "(0 - 1)", "sfc"),
)
IFS_PROFILE = tuple(FieldSelection(name, canonical, unit, "pl", PRESSURE_LEVELS) for name, canonical, unit in (
    ("r", "relative_humidity_pressure", "%"), ("q", "specific_humidity_pressure", "kg kg-1"),
    ("t", "temperature_pressure", "K"), ("u", "wind_u_pressure", "m s-1"),
    ("v", "wind_v_pressure", "m s-1"), ("w", "omega_pressure", "Pa s-1"),
    ("gh", "geopotential_height_pressure", "gpm"),
))
AIFS_PROFILE = (FieldSelection("q", "specific_humidity_pressure", "kg kg-1", "pl", AIFS_Q_LEVELS),) + tuple(FieldSelection(name, canonical, unit, "pl", PRESSURE_LEVELS) for name, canonical, unit in (
    ("t", "temperature_pressure", "K"),
    ("u", "wind_u_pressure", "m s-1"), ("v", "wind_v_pressure", "m s-1"),
    ("w", "omega_pressure", "Pa s-1"), ("gh", "geopotential_height_pressure", "gpm"),
))

PRODUCT_INVENTORY: Mapping[str, tuple[FieldSelection, ...]] = {
    "ecmwf-ifs-native": ECMWF_SURFACE + IFS_PROFILE,
    "ecmwf-aifs-single-native": tuple(
        item for item in ECMWF_SURFACE if item.upstream != "tcwv"
    ) + (
        FieldSelection("lcc", "cloud_low", "(0 - 1)", "sfc"),
        FieldSelection("mcc", "cloud_middle", "(0 - 1)", "sfc"),
        FieldSelection("hcc", "cloud_high", "(0 - 1)", "sfc"),
    ) + AIFS_PROFILE + (
        FieldSelection("r", None, "%", "pl", PRESSURE_LEVELS, "catalogued-unavailable", "AIFS Single lead-0 index publishes no relative humidity"),
        FieldSelection("q", None, "kg kg-1", "pl", (10,), "catalogued-unavailable", "AIFS Single lead-0 index publishes no q at 10 hPa"),
        FieldSelection("tcwv", None, "kg m-2", "sfc", (), "catalogued-unavailable", "AIFS Single lead-0 index publishes no TCWV"),
    ),
    "noaa-rap-parent-native": (
        FieldSelection("MASSDEN", None, "unknown", "8 m above ground", (), "raw-only", "ecCodes has no stable name/unit mapping; no aerosol species may be invented"),
        FieldSelection("AOTK", None, "unknown", "entire atmosphere", (), "raw-only", "ecCodes has no stable name/unit mapping; no wavelength may be invented"),
    ),
    "noaa-nam-parent-native": (
        FieldSelection("TCDC", "total_cloud_geometric", "%", "entire atmosphere"),
    ),
    "dwd-icon-global-native": (
        FieldSelection("t_2m", "temperature_2m", "K", "single-level"),
        FieldSelection("td_2m", "dew_point_2m", "K", "single-level"),
        FieldSelection("u_10m", "wind_u_10m", "m s-1", "single-level"),
        FieldSelection("v_10m", "wind_v_10m", "m s-1", "single-level"),
        FieldSelection("pmsl", "mean_sea_level_pressure", "Pa", "single-level"),
        FieldSelection("tot_prec", None, "provider-coded", "single-level", note="lead-0 initialization is retained raw; no nonzero accumulation interval is claimed"),
        FieldSelection("clct", "total_cloud_geometric", "%", "single-level"),
        FieldSelection("clcl", "cloud_low", "%", "single-level"),
        FieldSelection("clcm", "cloud_middle", "%", "single-level"),
        FieldSelection("clch", "cloud_high", "%", "single-level"),
        FieldSelection("relhum", "relative_humidity_pressure", "%", "pressure-level", (850, 700, 500, 300)),
        FieldSelection("qv", None, "kg kg-1", "model-level", (), "catalogued-unavailable", "DWD exposes QV on model levels, not the selected pressure surfaces; no vertical conversion is invented"),
        FieldSelection("t", "temperature_pressure", "K", "pressure-level", (850, 700, 500, 300)),
        FieldSelection("u", "wind_u_pressure", "m s-1", "pressure-level", (850, 700, 500, 300)),
        FieldSelection("v", "wind_v_pressure", "m s-1", "pressure-level", (850, 700, 500, 300)),
        FieldSelection("w", None, "m s-1", "model-level", (), "catalogued-unavailable", "DWD exposes W on model/half levels, not the selected pressure surfaces; no vertical conversion is invented"),
    ),
}


@dataclass(frozen=True)
class Coverage:
    selected_cells: int
    covers_full_box: bool
    native_south: float
    native_west: float
    native_north: float
    native_east: float
    selected_south: float | None
    selected_west: float | None
    selected_north: float | None
    selected_east: float | None
    corner_max_distance_degrees: float


def coverage(latitude: numpy.ndarray, longitude: numpy.ndarray) -> tuple[numpy.ndarray, Coverage]:
    lat = numpy.asarray(latitude, dtype="float64")
    lon = ((numpy.asarray(longitude, dtype="float64") + 180.0) % 360.0) - 180.0
    if lat.shape != lon.shape or not numpy.isfinite(lat).any() or not numpy.isfinite(lon).any():
        raise AdapterUnavailable("native latitude/longitude arrays are absent or mismatched")
    mask = ((lat >= EVIDENCE_BOUNDS["south"]) & (lat <= EVIDENCE_BOUNDS["north"]) &
            (lon >= EVIDENCE_BOUNDS["west"]) & (lon <= EVIDENCE_BOUNDS["east"]))
    selected = int(mask.sum())
    # Test the actual two-dimensional footprint, including the four corners.
    # Rectangular extrema alone falsely imply coverage for projected domains.
    corner_distances = []
    for corner_lat in (EVIDENCE_BOUNDS["south"], EVIDENCE_BOUNDS["north"]):
        scale = math.cos(math.radians(corner_lat))
        for corner_lon in (EVIDENCE_BOUNDS["west"], EVIDENCE_BOUNDS["east"]):
            distance = numpy.hypot(lat - corner_lat, (((lon - corner_lon + 180) % 360) - 180) * scale)
            corner_distances.append(float(numpy.nanmin(distance)))
    corner_max = max(corner_distances)
    full = selected > 0 and corner_max <= 0.4
    return mask, Coverage(selected, full, float(lat.min()), float(lon.min()), float(lat.max()), float(lon.max()),
        float(lat[mask].min()) if selected else None, float(lon[mask].min()) if selected else None,
        float(lat[mask].max()) if selected else None, float(lon[mask].max()) if selected else None, corner_max)


def _json_lines(body: bytes) -> list[dict[str, Any]]:
    if len(body) > MAX_INDEX_BYTES:
        raise AdapterUnavailable("ECMWF index exceeds bounded metadata ceiling")
    try:
        rows = [json.loads(line) for line in body.decode().splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"malformed ECMWF JSON-lines index: {error}") from error
    required = {"date", "time", "type", "stream", "step", "levtype", "param", "_offset", "_length"}
    if not rows or any(not isinstance(row, dict) or not required <= row.keys() for row in rows):
        raise AdapterUnavailable("ECMWF index is empty or omits identity/range keys")
    return rows


def select_ecmwf_records(rows: Sequence[Mapping[str, Any]], inventory: Sequence[FieldSelection]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for field in inventory:
        matches = [dict(row) for row in rows if row["param"] == field.upstream and row["levtype"] == field.level_type and
                   (not field.levels or int(row.get("levelist", -1)) in field.levels)]
        found = {(int(row["levelist"]) if "levelist" in row else None) for row in matches}
        missing = sorted(set(field.levels) - {value for value in found if value is not None})
        disposition = field.disposition if field.disposition != "selected" else ("retrieved" if matches and not missing else "missing")
        dispositions.append({"upstream": field.upstream, "canonical": field.canonical, "native_units": field.native_units,
            "level_type": field.level_type, "selected_levels": list(field.levels), "retrieved_levels": sorted(x for x in found if x is not None),
            "missing_levels": missing, "disposition": disposition, "note": field.note})
        if field.disposition == "selected": selected.extend(matches)
    return selected, dispositions


def select_noaa_records(idx_text: str, inventory: Sequence[FieldSelection]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # NCEP inventories use identifiers such as ``8.1`` for repeated record
    # numbers. Identity is opaque here; byte offsets are the ordering key.
    parsed = []
    for line in idx_text.splitlines():
        fields = line.split(":")
        if len(fields) < 6:
            raise AdapterUnavailable(f"malformed NOAA idx line: {line!r}")
        try: offset = int(fields[1])
        except ValueError as error: raise AdapterUnavailable(f"malformed NOAA idx offset: {line!r}") from error
        parsed.append({"offset": offset, "param": fields[3], "level": fields[4], "forecast": fields[5]})
    parsed.sort(key=lambda item: int(item["offset"]))
    rows = [dict(item, length=(int(parsed[index + 1]["offset"]) - int(item["offset"]) if index + 1 < len(parsed) else None)) for index, item in enumerate(parsed)]
    selected: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for field in inventory:
        matches = [row for row in rows if str(row["param"]).upper() == field.upstream and field.level_type.lower() in str(row["level"]).lower()]
        dispositions.append({"upstream": field.upstream, "canonical": field.canonical, "native_units": field.native_units,
            "level_type": field.level_type, "disposition": field.disposition if matches else "missing", "count": len(matches), "note": field.note})
        for row in matches:
            if row["length"] is None:
                raise AdapterUnavailable(f"unbounded trailing NOAA message: {field.upstream}")
            selected.append({"param": row["param"], "level": row["level"], "forecast": row["forecast"], "_offset": row["offset"], "_length": row["length"]})
    return selected, dispositions


def _message_bytes(client: PoliteClient, url: str, records: Sequence[Mapping[str, Any]], destination: Path) -> tuple[int, str]:
    total = 0
    digest = hashlib.sha256()
    with destination.open("wb") as handle:
        for row in records:
            start, length = int(row["_offset"]), int(row["_length"])
            if length <= 0 or length > MAX_MESSAGE_BYTES:
                raise AdapterUnavailable(f"message length {length} violates the 16 MiB bound")
            payload = client.get_range(url, start, start + length - 1)
            if len(payload) != length:
                raise AdapterUnavailable(f"short HTTP range at {start}: wanted {length}, got {len(payload)}")
            if payload[:4] != b"GRIB" or payload[-4:] != b"7777":
                raise AdapterUnavailable(f"range at {start} is not one complete GRIB message")
            handle.write(payload); digest.update(payload); total += length
    return total, digest.hexdigest()


def _decode_messages(path: Path, canonical: Mapping[str, str | None]) -> tuple[xarray.Dataset, Coverage, list[dict[str, Any]]]:
    import eccodes

    variables: dict[str, list[tuple[int | None, numpy.ndarray, dict[str, Any]]]] = {}
    selected_lat = selected_lon = None
    proof: Coverage | None = None
    message_inventory: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        while gid := eccodes.codes_grib_new_from_file(handle):
            try:
                short = str(eccodes.codes_get(gid, "shortName"))
                level_type = str(eccodes.codes_get(gid, "typeOfLevel"))
                level = int(eccodes.codes_get(gid, "level")) if level_type in {"isobaricInhPa", "isobaricInPa"} else None
                units = str(eccodes.codes_get(gid, "units"))
                values = numpy.asarray(eccodes.codes_get_array(gid, "values"), dtype="float32")
                lat = numpy.asarray(eccodes.codes_get_array(gid, "latitudes"), dtype="float64")
                lon = numpy.asarray(eccodes.codes_get_array(gid, "longitudes"), dtype="float64")
                mask, current = coverage(lat, lon)
                if proof is None: proof = current; selected_lat, selected_lon = lat[mask], ((lon[mask] + 180) % 360) - 180
                elif len(selected_lat) != int(mask.sum()) or not numpy.allclose(selected_lat, lat[mask]):
                    raise AdapterUnavailable("selected messages do not share one native grid")
                name = canonical.get(short.lower())
                chosen_values = values[mask]
                chosen_lat = lat[mask]; chosen_lon = ((lon[mask] + 180) % 360) - 180
                point_distance = numpy.hypot(chosen_lat - 47.5615, (((chosen_lon + 52.7126 + 180) % 360) - 180) * math.cos(math.radians(47.5615)))
                witness_index = int(numpy.nanargmin(point_distance)) if chosen_values.size else None
                message_inventory.append({"short_name": short, "canonical": name, "units": units, "level_type": level_type,
                    "level": level, "grid_type": str(eccodes.codes_get(gid, "gridType")), "selected_cells": int(mask.sum()),
                    "step_type": str(eccodes.codes_get(gid, "stepType")), "start_step": str(eccodes.codes_get(gid, "startStep")),
                    "end_step": str(eccodes.codes_get(gid, "endStep")), "raw_point_value": (float(chosen_values[witness_index]) if witness_index is not None and numpy.isfinite(chosen_values[witness_index]) else None),
                    "raw_point_latitude": (float(chosen_lat[witness_index]) if witness_index is not None else None), "raw_point_longitude": (float(chosen_lon[witness_index]) if witness_index is not None else None)})
                if name is not None: variables.setdefault(name, []).append((level, values[mask], {"units": units, "upstream_short_name": short}))
            finally:
                eccodes.codes_release(gid)
    if proof is None or selected_lat is None or selected_lon is None:
        raise AdapterUnavailable("GRIB bundle contained no messages")
    count = len(selected_lat)
    coords: dict[str, Any] = {"time": [numpy.datetime64("1970-01-01")], "latitude": (("y", "x"), selected_lat.reshape(count, 1)),
                              "longitude": (("y", "x"), selected_lon.reshape(count, 1))}
    data: dict[str, Any] = {}
    pressure_axis = sorted({int(level) for entries in variables.values() for level, *_ in entries if level is not None})
    if pressure_axis: coords["pressure"] = pressure_axis
    for name, entries in variables.items():
        levels = [item[0] for item in entries]
        if all(level is not None for level in levels):
            by_level = {int(level): values for level, values, _attrs in entries if level is not None}
            array = numpy.stack([by_level.get(level, numpy.full(count, numpy.nan, dtype="float32")) for level in pressure_axis]).reshape(1, len(pressure_axis), count, 1)
            data[name] = (("time", "pressure", "y", "x"), array, entries[0][2])
        else:
            data[name] = (("time", "y", "x"), entries[0][1].reshape(1, count, 1), entries[0][2])
    return xarray.Dataset(data, coords=coords), proof, message_inventory


def _product_url(source_id: str, run: datetime, lead: int) -> tuple[str, str]:
    date, cycle = run.strftime("%Y%m%d"), run.strftime("%H")
    if source_id.startswith("ecmwf-"):
        model = "ifs" if source_id == "ecmwf-ifs-native" else "aifs-single"
        name = f"{date}{cycle}0000-{lead}h-oper-fc"
        root = f"{ECMWF_BASE}/{date}/{cycle}z/{model}/0p25/oper/{name}"
        return root + ".grib2", root + ".index"
    if source_id == "noaa-rap-parent-native":
        root = f"{RAP_BASE}/rap.{date}/rap.t{cycle}z.awp130pgrbf{lead:02d}.grib2"
    elif source_id == "noaa-nam-parent-native":
        root = f"{NAM_BASE}/nam.{date}/nam.t{cycle}z.awphys{lead:02d}.tm00.grib2"
    else: raise ValueError(source_id)
    return root, root + ".idx"


@dataclass
class IndexedNativeCandidate:
    source_id: str
    client: PoliteClient | None = None
    adapter_version: str = "native-indexed-evidence-v1"

    def __post_init__(self) -> None:
        if self.source_id not in PRODUCT_INVENTORY: raise ValueError(self.source_id)

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self.client or PoliteClient(); cadence = 1 if "rap" in self.source_id else 6
        ref = window.now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        ref -= timedelta(hours=ref.hour % cadence)
        for age in range(0, 37, cadence):
            run = ref - timedelta(hours=age); data_url, index_url = _product_url(self.source_id, run, 0)
            try: response = client.get(index_url)
            except Exception: continue
            if response.content:
                return [RunCandidate(run.strftime("%Y%m%d%H"), run, [data_url, index_url], {"index": response.content})]
        raise AdapterUnavailable(f"no indexed {self.source_id} run found in bounded 36-hour discovery")

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        body = candidate.detail.get("index")
        if not isinstance(body, bytes): raise AdapterUnavailable("candidate has no retained index bytes")
        inventory = PRODUCT_INVENTORY[self.source_id]
        if self.source_id.startswith("ecmwf-"):
            records, dispositions = select_ecmwf_records(_json_lines(body), inventory)
        else:
            records, dispositions = select_noaa_records(body.decode(), inventory)
        if not records: raise AdapterUnavailable("selected inventory has no retrievable messages")
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / f"{self.source_id}.index").write_bytes(body)
        raw = workdir / f"{self.source_id}.grib2"
        if candidate.detail.get("retained_raw"):
            if not raw.is_file():
                raise AdapterUnavailable(f"retained raw bundle is absent: {raw}")
            byte_size = raw.stat().st_size
            expected_size = sum(int(row["_length"]) for row in records)
            if byte_size != expected_size:
                raise AdapterUnavailable(f"retained raw bundle size mismatch: wanted {expected_size}, got {byte_size}")
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        else:
            byte_size, digest = _message_bytes(self.client or PoliteClient(), candidate.urls[0], records, raw)
        canonical = {field.upstream.lower(): field.canonical for field in inventory if field.canonical is not None}
        if self.source_id == "noaa-nam-parent-native":
            canonical["tcc"] = "total_cloud_geometric"  # NCEP idx TCDC decodes to WMO shortName tcc
        dataset, geometry, messages = _decode_messages(raw, canonical)
        # RAP's parent grid demonstrably misses the evidence box. Preserve the
        # real bytes and geometry in the evidence harness, but refuse an artifact.
        if not geometry.covers_full_box:
            raise AdapterUnavailable(f"regional_exclusion:native parent grid does not cover the full evidence box; bounds={geometry}")
        run = candidate.run_time or datetime.now(UTC); dataset = dataset.assign_coords(time=[numpy.datetime64(run.replace(tzinfo=None))])
        dataset.attrs.update(source_id=self.source_id, operational=False, native_grid=True)
        artifact_path = workdir / f"{self.source_id}.zarr.zip"; write_zarr(dataset, artifact_path)
        provenance = {"source_id": self.source_id, "product_access_path": candidate.urls[0], "index_url": candidate.urls[1],
            "provider_run_id": candidate.provider_run_id, "run_time": run.isoformat(), "lead_hours": 0,
            "valid_time": run.isoformat(), "retrieved_at": datetime.now(UTC).isoformat(), "raw_sha256": digest,
            "raw_bytes": byte_size, "field_disposition": dispositions, "message_inventory": messages,
            "native_grid_coverage": geometry.__dict__, "bounds": EVIDENCE_BOUNDS, "evidence_classes": ["retrieved"],
            "evidence_class_by_variable": {name: "retrieved" for name in dataset.data_vars}, "operational": False}
        artifact = Artifact("native-deterministic", MEDIA_ZARR, artifact_path, provenance)
        complete = not any(item["disposition"] == "missing" for item in dispositions)
        return RunResult(self.source_id, candidate.provider_run_id, run, datetime.now(UTC), complete, True, [artifact],
                         native_crs="native producer grid", notes="unregistered experimental evidence candidate")


def _icon_name(run: datetime, field: FieldSelection, lead: int = 0) -> str:
    stamp = run.strftime("%Y%m%d%H")
    token = field.upstream.upper()
    if field.levels:
        raise ValueError("pressure fields require one explicit level")
    return f"icon_global_icosahedral_single-level_{stamp}_{lead:03d}_{token}.grib2.bz2"


def _decode_icon(bundle: Path, clat_path: Path, clon_path: Path, canonical: Mapping[str, str | None]) -> tuple[xarray.Dataset, Coverage, list[dict[str, Any]]]:
    import eccodes

    def one(path: Path) -> tuple[numpy.ndarray, str, str, int | None, str]:
        with path.open("rb") as handle:
            gid = eccodes.codes_grib_new_from_file(handle)
            if gid is None: raise AdapterUnavailable(f"empty GRIB: {path.name}")
            try:
                values = numpy.asarray(eccodes.codes_get_array(gid, "values"), dtype="float32")
                short = str(eccodes.codes_get(gid, "shortName")); units = str(eccodes.codes_get(gid, "units"))
                kind = str(eccodes.codes_get(gid, "typeOfLevel")); level = int(eccodes.codes_get(gid, "level")) if kind in {"isobaricInhPa", "isobaricInPa"} else None
                return values, short, units, level, kind
            finally: eccodes.codes_release(gid)

    lat, *_ = one(clat_path); lon, *_ = one(clon_path)
    mask, geometry = coverage(lat, lon); count = int(mask.sum())
    chosen_lat, chosen_lon = lat[mask], ((lon[mask] + 180) % 360) - 180
    point_distance = numpy.hypot(chosen_lat - 47.5615, (((chosen_lon + 52.7126 + 180) % 360) - 180) * math.cos(math.radians(47.5615)))
    witness_index = int(numpy.nanargmin(point_distance))
    entries: dict[str, list[tuple[int | None, numpy.ndarray, dict[str, str]]]] = {}; messages = []
    # Each downloaded DWD object is retained as one concatenated decompressed
    # bundle. ecCodes reads the exact message boundaries in sequence.
    with bundle.open("rb") as handle:
        while gid := eccodes.codes_grib_new_from_file(handle):
            try:
                short = str(eccodes.codes_get(gid, "shortName")); units = str(eccodes.codes_get(gid, "units")); kind = str(eccodes.codes_get(gid, "typeOfLevel"))
                level = int(eccodes.codes_get(gid, "level")) if kind in {"isobaricInhPa", "isobaricInPa"} else None
                values = numpy.asarray(eccodes.codes_get_array(gid, "values"), dtype="float32")
                if values.shape != lat.shape: raise AdapterUnavailable("ICON field/grid point counts differ")
                name = canonical.get(short.lower()); selected_values = values[mask]; messages.append({"short_name": short, "canonical": name, "units": units, "level_type": kind, "level": level, "selected_cells": count,
                    "step_type": str(eccodes.codes_get(gid, "stepType")), "start_step": str(eccodes.codes_get(gid, "startStep")), "end_step": str(eccodes.codes_get(gid, "endStep")),
                    "raw_point_value": (float(selected_values[witness_index]) if numpy.isfinite(selected_values[witness_index]) else None),
                    "raw_point_latitude": float(chosen_lat[witness_index]), "raw_point_longitude": float(chosen_lon[witness_index])})
                if name: entries.setdefault(name, []).append((level, values[mask], {"units": units, "upstream_short_name": short}))
            finally: eccodes.codes_release(gid)
    coords: dict[str, Any] = {"time": [numpy.datetime64("1970-01-01")], "latitude": (("y", "x"), lat[mask].reshape(count, 1)), "longitude": (("y", "x"), lon[mask].reshape(count, 1))}
    data = {}
    for name, parts in entries.items():
        if all(level is not None for level, *_ in parts):
            parts.sort(key=lambda item: int(item[0])); coords.setdefault("pressure", [int(item[0]) for item in parts])
            data[name] = (("time", "pressure", "y", "x"), numpy.stack([item[1] for item in parts]).reshape(1, len(parts), count, 1), parts[0][2])
        else: data[name] = (("time", "y", "x"), parts[0][1].reshape(1, count, 1), parts[0][2])
    return xarray.Dataset(data, coords=coords), geometry, messages


@dataclass
class DWDIconNativeCandidate:
    """Native ICON nearest-cell evidence using DWD's own CLAT/CLON messages."""

    source_id: str = "dwd-icon-global-native"
    client: PoliteClient | None = None
    adapter_version: str = "dwd-icon-native-evidence-v1"

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self.client or PoliteClient(); ref = window.now.astimezone(UTC).replace(minute=0, second=0, microsecond=0); ref -= timedelta(hours=ref.hour % 6)
        for age in range(0, 37, 6):
            run = ref - timedelta(hours=age); cycle, stamp = run.strftime("%H"), run.strftime("%Y%m%d%H")
            url = f"{DWD_BASE}/{cycle}/clat/icon_global_icosahedral_time-invariant_{stamp}_CLAT.grib2.bz2"
            try:
                if client.get(url, headers={"Range": "bytes=0-3"}).content.startswith(b"BZh"):
                    return [RunCandidate(stamp, run, [url], {"cycle": cycle, "stamp": stamp})]
            except Exception: continue
        raise AdapterUnavailable("no ICON CLAT inventory found in bounded 36-hour discovery")

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self.client or PoliteClient(); run = candidate.run_time
        if run is None: raise AdapterUnavailable("ICON run identity missing")
        workdir.mkdir(parents=True, exist_ok=True); cycle, stamp = run.strftime("%H"), run.strftime("%Y%m%d%H")
        retrieved = []; digest = hashlib.sha256(); bundle = workdir / f"{self.source_id}.grib2"
        objects = workdir / "upstream-objects"
        objects.mkdir(exist_ok=True)
        coord_paths = {}
        with bundle.open("wb") as output:
            for coordinate in ("clat", "clon"):
                url = f"{DWD_BASE}/{cycle}/{coordinate}/icon_global_icosahedral_time-invariant_{stamp}_{coordinate.upper()}.grib2.bz2"
                packed = objects / f"{coordinate}.grib2.bz2"
                if not candidate.detail.get("retained_raw"):
                    client.download(url, packed, max_bytes=8 * 1024 * 1024)
                if not packed.is_file(): raise AdapterUnavailable(f"retained ICON coordinate is absent: {packed}")
                raw = bz2.decompress(packed.read_bytes()); coord_paths[coordinate] = workdir / f"{coordinate}.grib2"; coord_paths[coordinate].write_bytes(raw); digest.update(packed.read_bytes())
                retrieved.append({"upstream": coordinate, "level": None, "url": url, "path": str(packed.relative_to(workdir)),
                    "compressed_bytes": packed.stat().st_size, "compressed_sha256": hashlib.sha256(packed.read_bytes()).hexdigest(), "coordinate": True})
            for field in PRODUCT_INVENTORY[self.source_id]:
                if field.disposition != "selected": continue
                levels: Iterable[int | None] = field.levels or (None,)
                for level in levels:
                    kind = "pressure-level" if level is not None else "single-level"; suffix = f"_{level}" if level is not None else ""
                    filename = f"icon_global_icosahedral_{kind}_{stamp}_000{suffix}_{field.upstream.upper()}.grib2.bz2"
                    url = f"{DWD_BASE}/{cycle}/{field.upstream}/{filename}"; packed = objects / filename
                    if not candidate.detail.get("retained_raw"):
                        try:
                            client.download(url, packed, max_bytes=8 * 1024 * 1024)
                        except Exception as error:
                            raise AdapterUnavailable(f"ICON selected object unavailable: {url}: {error}") from error
                    if not packed.is_file(): raise AdapterUnavailable(f"retained ICON field is absent: {packed}")
                    compressed = packed.read_bytes(); raw = bz2.decompress(compressed)
                    if not raw.startswith(b"GRIB") or not raw.endswith(b"7777"): raise AdapterUnavailable(f"invalid ICON GRIB object: {filename}")
                    output.write(raw); digest.update(compressed); retrieved.append({"upstream": field.upstream, "level": level, "url": url,
                        "path": str(packed.relative_to(workdir)), "compressed_bytes": len(compressed),
                        "compressed_sha256": hashlib.sha256(compressed).hexdigest(), "coordinate": False})
        (workdir / "upstream-objects.json").write_text(json.dumps({"objects": retrieved}, indent=2, sort_keys=True) + "\n")
        canonical = {
            "2t": "temperature_2m", "2d": "dew_point_2m", "10u": "wind_u_10m", "10v": "wind_v_10m",
            "prmsl": "mean_sea_level_pressure", "tp": None, "clct": "total_cloud_geometric",
            "clcl": "cloud_low", "clcm": "cloud_middle", "clch": "cloud_high", "r": "relative_humidity_pressure",
            "t": "temperature_pressure", "u": "wind_u_pressure", "v": "wind_v_pressure",
        }
        dataset, geometry, messages = _decode_icon(bundle, coord_paths["clat"], coord_paths["clon"], canonical)
        bundle.unlink()
        coord_paths["clat"].unlink()
        coord_paths["clon"].unlink()
        dataset = dataset.assign_coords(time=[numpy.datetime64(run.replace(tzinfo=None))]); dataset.attrs.update(source_id=self.source_id, operational=False, native_grid=True)
        artifact_path = workdir / f"{self.source_id}.zarr.zip"; write_zarr(dataset, artifact_path)
        unavailable = [{"upstream": field.upstream, "canonical": field.canonical, "disposition": field.disposition, "note": field.note} for field in PRODUCT_INVENTORY[self.source_id] if field.disposition != "selected"]
        provenance = {"source_id": self.source_id, "product_access_path": DWD_BASE, "provider_run_id": candidate.provider_run_id, "run_time": run.isoformat(), "lead_hours": 0,
            "valid_time": run.isoformat(), "retrieved_at": datetime.now(UTC).isoformat(), "raw_sha256": digest.hexdigest(), "retrieved_objects": retrieved,
            "field_disposition": unavailable, "message_inventory": messages, "native_grid_coverage": geometry.__dict__, "bounds": EVIDENCE_BOUNDS,
            "evidence_classes": ["retrieved"], "evidence_class_by_variable": {name: "retrieved" for name in dataset.data_vars}, "operational": False}
        artifact = Artifact("native-deterministic", MEDIA_ZARR, artifact_path, provenance)
        return RunResult(self.source_id, candidate.provider_run_id, run, datetime.now(UTC), True, True, [artifact], native_crs="ICON R03B07 native icosahedral", notes="unregistered experimental evidence candidate")
