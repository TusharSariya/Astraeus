"""Bounded isolated reader for the NL St. John's provisional air-quality CSV."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy
import xarray

from ingest.contract import MEDIA_ZARR, AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
from ingest.grib import write_zarr
from ingest.http import PoliteClient

UTC = timezone.utc
LOCAL = ZoneInfo("America/St_Johns")
SOURCE_ID = "nl-air-quality-csv"
CSV_URL = "https://www.mae.gov.nl.ca/wrmd/pp_adrs/Data/StJohns_Line.csv"
SOURCE_PAGE = "https://www.mae.gov.nl.ca/wrmd/pp_adrs/template_airmon.asp?station=stjohns"
MAX_CSV_BYTES = 1024 * 1024
EXPECTED_COLUMNS = (
    "STAT_NUM", "DATE_TIME", "PM2_5_RUN_AVG", "PM10_RUN_AVG", "NO", "NO2", "NOX", "O3", "SO2", "CO",
)
SELECTED_FIELDS = {
    "PM2_5_RUN_AVG": ("pm2_5_surface_24h_mean", "kg m-3", "ug m-3", 1e-9),
    "O3": ("ozone_surface_mole_fraction", "nmol mol-1", "ppb", 1.0),
}
DEFERRED_FIELDS = {
    "PM10_RUN_AVG": "outside issue 118 selected PM2.5/ozone scope",
    "NO": "outside issue 118 selected PM2.5/ozone scope",
    "NO2": "outside issue 118 selected PM2.5/ozone scope",
    "NOX": "outside issue 118 selected PM2.5/ozone scope",
    "SO2": "outside issue 118 selected PM2.5/ozone scope",
    "CO": "outside issue 118 selected PM2.5/ozone scope",
}


def _parse(body: bytes, window: FetchWindow) -> list[dict[str, object]]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise AdapterUnavailable(f"NL air-quality CSV is not UTF-8: {error}") from error
    lines = text.splitlines()
    if not lines or "PROVISIONAL" not in lines[0] or "quality control" not in lines[0]:
        raise AdapterUnavailable("NL air-quality CSV lacks its provisional quality warning")
    reader = csv.DictReader(io.StringIO("\n".join(lines[1:])))
    if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
        raise AdapterUnavailable("NL air-quality CSV columns changed; refusing schema drift")
    rows: list[dict[str, object]] = []
    for position, row in enumerate(reader, start=3):
        if row["STAT_NUM"] != "StJohns":
            raise AdapterUnavailable(f"NL air-quality CSV row {position} has a foreign station")
        try:
            wall = datetime.strptime(row["DATE_TIME"] or "", "%m/%d/%Y %I:%M:%S %p")
        except ValueError as error:
            raise AdapterUnavailable(f"NL air-quality CSV row {position} has an invalid local timestamp") from error
        candidates = []
        for fold in (0, 1):
            aware = wall.replace(tzinfo=LOCAL, fold=fold)
            if aware.astimezone(UTC).astimezone(LOCAL).replace(tzinfo=None) == wall:
                candidates.append(aware)
        offsets = {item.utcoffset() for item in candidates}
        if not candidates:
            raise AdapterUnavailable(f"NL air-quality CSV row {position} has a nonexistent local timestamp")
        if len(offsets) != 1:
            raise AdapterUnavailable(f"NL air-quality CSV row {position} has an ambiguous local timestamp without an offset")
        local = candidates[0]
        instant = local.astimezone(UTC)
        if not window.covers(instant):
            continue
        values: dict[str, float | None] = {}
        for upstream in SELECTED_FIELDS:
            raw = (row[upstream] or "").strip()
            if not raw:
                values[upstream] = None
                continue
            try:
                value = float(raw)
            except ValueError as error:
                raise AdapterUnavailable(f"NL air-quality CSV row {position} has invalid {upstream}") from error
            if not math.isfinite(value) or value < 0:
                raise AdapterUnavailable(f"NL air-quality CSV row {position} has out-of-range {upstream}")
            values[upstream] = value
        rows.append({"time": instant, "local_time": local.isoformat(), "values": values})
    rows.sort(key=lambda item: item["time"])
    if not rows:
        raise AdapterUnavailable("NL air-quality CSV has no rows in the requested evidence window")
    times = [item["time"] for item in rows]
    if len(set(times)) != len(times):
        raise AdapterUnavailable("NL air-quality CSV repeats an observation timestamp")
    return rows


class NLAirQualityAdapter:
    source_id = SOURCE_ID
    adapter_version = "nl-air-quality-csv-v1"

    def __init__(self, client: PoliteClient | None = None, endpoint: str = CSV_URL) -> None:
        self.client = client or PoliteClient()
        self.endpoint = endpoint

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        with tempfile.TemporaryDirectory(prefix="nl-air-quality-") as directory:
            path = Path(directory) / "StJohns_Line.csv"
            try:
                self.client.download(self.endpoint, path, max_bytes=MAX_CSV_BYTES)
            except Exception as error:
                raise AdapterUnavailable(f"NL air-quality CSV request failed: {error}") from error
            body = path.read_bytes()
        captured_at = datetime.now(UTC)
        rows = _parse(body, window)
        newest = rows[-1]["time"]
        assert isinstance(newest, datetime)
        digest = hashlib.sha256(body).hexdigest()
        return [RunCandidate(
            provider_run_id=f"stjohns-provisional-{newest.strftime('%Y%m%d%H%M')}-{digest[:12]}",
            run_time=None,
            urls=[self.endpoint],
            detail={"rows": rows, "sha256": digest, "byte_count": len(body), "captured_at": captured_at},
        )]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        rows = candidate.detail.get("rows")
        if not isinstance(rows, list) or not rows:
            raise AdapterUnavailable("NL air-quality candidate carries no observations")
        rows = [item for item in rows if window.covers(item["time"])]
        if not rows:
            raise AdapterUnavailable("NL air-quality candidate has no observations in the current fetch window")
        times = [item["time"] for item in rows]
        arrays: dict[str, object] = {}
        missing: dict[str, int] = {}
        for upstream, (canonical, units, original_units, scale) in SELECTED_FIELDS.items():
            values = numpy.asarray([
                numpy.nan if item["values"][upstream] is None else float(item["values"][upstream]) * scale
                for item in rows
            ], dtype="float64")[:, None, None]
            missing[canonical] = int(numpy.isnan(values).sum())
            attrs = {"units": units, "original_units": original_units, "quality_control": "provisional_unvalidated"}
            if upstream == "PM2_5_RUN_AVG":
                attrs.update(reporting_interval="trailing_24_hours", reporting_interval_hours=24)
            arrays[canonical] = (("valid_time", "latitude", "longitude"), values, attrs)
        dataset = xarray.Dataset(
            arrays,
            coords={"valid_time": numpy.asarray([numpy.datetime64(item.replace(tzinfo=None), "ns") for item in times]), "latitude": [47.56038], "longitude": [-52.71147]},
            attrs={"source_id": SOURCE_ID, "station_id": "010102", "station_name": "StJohns", "operational": False},
        )
        path = workdir / "air_quality.zarr.zip"
        write_zarr(dataset, path)
        retrieved_at = candidate.detail.get("captured_at")
        if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None:
            raise AdapterUnavailable("NL air-quality candidate lacks its UTC capture time")
        retrieved_at = retrieved_at.astimezone(UTC)
        completeness = all(count == 0 for count in missing.values())
        provenance = {
            "source_id": SOURCE_ID,
            "producer": "Government of Newfoundland and Labrador",
            "product": "St. John's NAPS Station 010102 near-real-time line data",
            "adapter_version": self.adapter_version,
            "evidence_classes": ["uncalibrated_observation"],
            "evidence_class_by_variable": {value[0]: "uncalibrated_observation" for value in SELECTED_FIELDS.values()},
            "operational": False,
            "quality": {"status": "unknown", "flags": ["provisional", "not_quality_controlled"]},
            "coverage": {"status": "complete" if completeness else "partial", "fraction": 1.0 if completeness else None},
            "station": {"id": "010102", "name": "StJohns", "latitude": 47.56038, "longitude": -52.71147, "elevation_m": 6.71},
            "native_resolution": "St. John's NAPS Station 010102 point observation",
            "source_page": SOURCE_PAGE,
            "request": {"url": self.endpoint, "parameters": {}, "byte_count": candidate.detail.get("byte_count"), "sha256": candidate.detail.get("sha256")},
            "time": {"provider_timezone": "America/St_Johns", "local_times": [item["local_time"] for item in rows], "valid_times_utc": [item.isoformat().replace("+00:00", "Z") for item in times]},
            "valid_times": [item.isoformat().replace("+00:00", "Z") for item in times],
            "field_disposition": {
                "STAT_NUM": "station identity metadata",
                "DATE_TIME": "valid time in America/St_Johns, converted to UTC",
                "PM2_5_RUN_AVG": "retrieved as pm2_5_surface_24h_mean; ug m-3 normalized to kg m-3",
                "O3": "retrieved as ozone_surface_mole_fraction; ppb retained as nmol mol-1",
                **{key: f"deferred: {reason}" for key, reason in DEFERRED_FIELDS.items()},
            },
            "licence": "Copyright Government of Newfoundland and Labrador, all rights reserved",
            "redistribution": False,
            "provisional_warning": "PROVISIONAL; has not undergone quality control checks and may be subject to significant change",
            "missing_counts": missing,
            "original_units_by_variable": {value[0]: value[2] for value in SELECTED_FIELDS.values()},
        }
        provenance["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        provenance["byte_size"] = path.stat().st_size
        return RunResult(SOURCE_ID, candidate.provider_run_id, None, retrieved_at, completeness, True, [Artifact("air_quality", MEDIA_ZARR, path, provenance)], "EPSG:4326", "isolated provisional station observations; operational false")
