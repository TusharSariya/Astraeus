"""Experimental WeatherNext 3 statistics adapter.

This module is deliberately not registered.  The source contract is draft and
the Google real-time terms have not been approved for product use.  It turns a
validated, bounded acquisition manifest into the same immutable Zarr artifact
shape the Astraeus API reads, without inventing ensemble members.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy
import xarray

from ingest.contract import MEDIA_ZARR, AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
from ingest.grib import write_zarr

UTC = timezone.utc
SOURCE_ID = "google-weathernext-3-statistics"
PRODUCT = "weathernext_3_0_0_statistics"
ACCESS_SURFACE = "gcs_statistics_spatial"
STATISTICS = ("mean", "p10", "p25", "p50", "p75", "p90")
BASE_FIELDS = (
    "temperature_2m", "dewpoint_temperature_2m", "wind_speed_10m",
    "wind_speed_100m", "u_component_of_wind_10m", "v_component_of_wind_10m",
    "u_component_of_wind_100m", "v_component_of_wind_100m",
    "surface_solar_radiation_downwards_1hr",
    "total_sky_direct_solar_radiation_at_surface_1hr", "total_precipitation_1hr",
    "imerg_tp_1hr", "experimental_tp_1hr", "total_cloud_cover",
    "low_cloud_cover", "medium_cloud_cover", "high_cloud_cover",
    "mean_sea_level_pressure", "sea_surface_temperature",
    "station_head_temperature_2m", "station_head_dewpoint_temperature_2m",
)
EXPECTED_FIELDS = tuple(f"{base}_{stat}" for base in BASE_FIELDS for stat in STATISTICS)
CLOUD_FIELDS = tuple(
    f"{base}_{stat}"
    for base in ("total_cloud_cover", "low_cloud_cover", "medium_cloud_cover", "high_cloud_cover")
    for stat in STATISTICS
)


class WeatherNextManifestError(ValueError):
    """The bounded acquisition evidence is incomplete or self-contradictory."""


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise WeatherNextManifestError("timestamp must carry an explicit UTC offset")
    return parsed.astimezone(UTC)


def _expected_grid(name: str) -> str:
    return "0p05" if name.startswith("station_head_") else "0p1"


def _expected_unit(name: str) -> str:
    base = name.rsplit("_", 1)[0]
    if "cloud_cover" in base:
        return "(0 - 1)"
    if base in {"temperature_2m", "dewpoint_temperature_2m", "sea_surface_temperature",
                "station_head_temperature_2m", "station_head_dewpoint_temperature_2m"}:
        return "K"
    if "wind" in base:
        return "m s**-1"
    if "radiation" in base:
        return "J m**-2"
    if base == "mean_sea_level_pressure":
        return "Pa"
    return "m"


def validate_acquisition(manifest: dict[str, Any]) -> None:
    identity = manifest.get("identity", {})
    if identity.get("product_version") != "3.0.0" or identity.get("access_surface") != ACCESS_SURFACE:
        raise WeatherNextManifestError("wrong product version or access surface; WN2 must remain distinct")
    if identity.get("member_id") is not None:
        raise WeatherNextManifestError("statistics are provider reductions, not ensemble members")
    request = manifest.get("request", {})
    if request.get("bucket") != "weathernext3_statistics_spatial" or request.get("prefix") != f"{PRODUCT}/zarr/":
        raise WeatherNextManifestError("wrong WeatherNext bucket or product prefix")
    if request.get("requester_billing_identity") is not None:
        raise WeatherNextManifestError("requester billing identity must be absent")
    if request.get("initialization") != manifest.get("times", {}).get("initialization"):
        raise WeatherNextManifestError("request and time initialization identities differ")
    fields = manifest.get("fields", {})
    if set(fields) != set(EXPECTED_FIELDS):
        raise WeatherNextManifestError("field inventory must contain exactly all 126 documented arrays")
    for name, item in fields.items():
        if item.get("status") not in {"retrieved", "missing", "unsupported", "deferred"}:
            raise WeatherNextManifestError(f"{name}: invalid field disposition")
        if item.get("statistic") != name.rsplit("_", 1)[1]:
            raise WeatherNextManifestError(f"{name}: statistic identity mismatch")
    if manifest.get("result") != "success":
        raise AdapterUnavailable(str(manifest.get("blocker") or "WeatherNext acquisition unavailable"))
    sample_items = manifest.get("sample", {}).get("fields", [])
    samples = {item["field"]: item for item in sample_items}
    if len(samples) != len(sample_items):
        raise WeatherNextManifestError("duplicate sample field identity")
    retrieved = {name for name, item in fields.items() if item["status"] == "retrieved"}
    selected = request.get("selected_fields")
    if not isinstance(selected, list) or not selected or len(selected) != len(set(selected)) or not set(selected) <= set(EXPECTED_FIELDS):
        raise WeatherNextManifestError("selected field set must be non-empty, unique and documented")
    if retrieved != set(selected):
        raise WeatherNextManifestError("selected fields and retrieved dispositions differ")
    if set(samples) != retrieved:
        raise WeatherNextManifestError("retrieved dispositions and sample payload differ")
    leads = manifest.get("sample", {}).get("lead_hours", [])
    if leads != request.get("lead_hours") or not leads or len(leads) != len(set(leads)):
        raise WeatherNextManifestError("request and sample leads must be equal, non-empty and unique")
    valid = manifest.get("times", {}).get("valid", [])
    if len(leads) != len(valid) or any(len(item.get("values", [])) != len(leads) for item in samples.values()):
        raise WeatherNextManifestError("lead, valid-time and value cardinalities differ")
    initialization = _time(manifest["times"]["initialization"])
    if any(_time(stamp) != initialization + timedelta(hours=lead) for lead, stamp in zip(leads, valid)):
        raise WeatherNextManifestError("valid time is not initialization plus lead")
    for name, item in samples.items():
        expected_unit = _expected_unit(name)
        if item.get("unit") != expected_unit or fields[name].get("unit") != expected_unit:
            raise WeatherNextManifestError(f"{name}: native unit mismatch")
        if not all(value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and numpy.isfinite(value))
                   for value in item["values"]):
            raise WeatherNextManifestError(f"{name}: non-finite or non-numeric sample value")
        null_count = sum(value is None for value in item["values"])
        if fields[name].get("null_count") != null_count:
            raise WeatherNextManifestError(f"{name}: fill-mask count mismatch")
        if name in CLOUD_FIELDS:
            for value in item["values"]:
                if value is not None and (not numpy.isfinite(value) or not 0 <= value <= 1):
                    raise WeatherNextManifestError(f"{name}: invalid cloud fraction")
    box = manifest.get("avalon_box_sample")
    if box is not None:
        box_items = box.get("fields", [])
        box_fields = {item["field"]: item for item in box_items}
        if len(box_fields) != len(box_items):
            raise WeatherNextManifestError("duplicate Avalon box field identity")
        if set(box_fields) != retrieved:
            raise WeatherNextManifestError("Avalon box fields and retrieved dispositions differ")
        if not set(box_fields) <= set(CLOUD_FIELDS):
            raise WeatherNextManifestError("Avalon box experiment accepts only supported 0.1-degree cloud statistics")
        latitudes, longitudes = box.get("latitudes", []), box.get("longitudes", [])
        if not latitudes or not longitudes:
            raise WeatherNextManifestError("Avalon box has no native cells")
        for name, coordinates in (("latitude", latitudes), ("longitude", longitudes)):
            if any(not isinstance(value, (int, float)) or not numpy.isfinite(value) for value in coordinates):
                raise WeatherNextManifestError(f"Avalon box {name} coordinate is invalid")
            differences = numpy.diff(coordinates)
            if not (numpy.all(differences > 0) and numpy.allclose(differences, 0.1, atol=5e-5)):
                raise WeatherNextManifestError(f"Avalon box {name} coordinates must be monotonic native 0.1-degree centres")
        for name, item in box_fields.items():
            if [lead.get("lead_hours") for lead in item.get("leads", [])] != leads:
                raise WeatherNextManifestError(f"{name}: Avalon box lead identity mismatch")
            for lead in item["leads"]:
                values = lead.get("values", [])
                if len(values) != len(latitudes) or any(len(row) != len(longitudes) for row in values):
                    raise WeatherNextManifestError(f"{name}: Avalon box shape mismatch")
                if any(value is not None and (not numpy.isfinite(value) or not 0 <= value <= 1)
                       for row in values for value in row):
                    raise WeatherNextManifestError(f"{name}: invalid Avalon box cloud fraction")
    else:
        coordinates_by_grid: dict[str, tuple[float, float]] = {}
        for name, item in samples.items():
            grid = item.get("grid")
            if grid != _expected_grid(name):
                raise WeatherNextManifestError(f"{name}: native grid mismatch")
            coordinate = (item.get("latitude"), item.get("longitude"))
            if not all(isinstance(value, (int, float)) and numpy.isfinite(value) for value in coordinate):
                raise WeatherNextManifestError(f"{name}: point coordinate missing or invalid")
            previous = coordinates_by_grid.setdefault(grid, coordinate)
            if coordinate != previous:
                raise WeatherNextManifestError(f"{name}: point coordinate differs within native grid")


class WeatherNext3StatisticsAdapter:
    source_id = SOURCE_ID
    adapter_version = "weathernext3-statistics-experimental-v1"

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = Path(manifest_path)

    def _load(self) -> dict[str, Any]:
        try:
            manifest = json.loads(self.manifest_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise AdapterUnavailable("WeatherNext bounded manifest unavailable") from error
        validate_acquisition(manifest)
        return manifest

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        manifest = self._load()
        run_time = _time(manifest["times"]["initialization"])
        valid_times = tuple(_time(item) for item in manifest["times"]["valid"])
        if not any(window.covers(item) for item in valid_times):
            raise AdapterUnavailable("bounded WeatherNext artifact has no valid time in the requested window")
        return [RunCandidate(provider_run_id=run_time.strftime("%Y%m%d%H"), run_time=run_time,
                             urls=[f"gs://{manifest['request']['bucket']}/{manifest['request']['prefix']}"],
                             detail={"manifest": manifest})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        manifest = candidate.detail.get("manifest") or self._load()
        validate_acquisition(manifest)
        expected_run = _time(manifest["times"]["initialization"])
        expected_url = f"gs://{manifest['request']['bucket']}/{manifest['request']['prefix']}"
        if candidate.provider_run_id != expected_run.strftime("%Y%m%d%H") or candidate.run_time != expected_run or candidate.urls != [expected_url]:
            raise WeatherNextManifestError("candidate and manifest source identity differ")
        valid = [_time(item) for item in manifest["times"]["valid"]]
        if not any(window.covers(item) for item in valid):
            raise AdapterUnavailable("bounded WeatherNext artifact has no valid time in the requested window")
        box = manifest.get("avalon_box_sample")
        box_fields = {item["field"]: item for item in box.get("fields", [])} if box else {}
        dispositions = {name: item["status"] for name, item in manifest["fields"].items()}
        groups: dict[str, list[dict[str, Any]]] = {}
        for sample in manifest["sample"]["fields"]:
            groups.setdefault("0p1" if box else sample.get("grid", "0p1"), []).append(sample)
        artifacts = []
        for grid_name, samples in sorted(groups.items()):
            data_vars: dict[str, Any] = {}
            for sample in samples:
                if sample["field"] in box_fields:
                    values = numpy.asarray([
                        [[numpy.nan if value is None else value for value in row] for row in lead["values"]]
                        for lead in box_fields[sample["field"]]["leads"]
                    ], dtype="float32")
                else:
                    values = numpy.asarray([numpy.nan if value is None else value for value in sample["values"]], dtype="float32")[:, None, None]
                data_vars[sample["field"]] = (("valid_time", "latitude", "longitude"), values, {
                    "units": sample["unit"], "original_units": sample["unit"],
                    "provider_variable": sample["field"].rsplit("_", 1)[0],
                    "provider_statistic": sample["field"].rsplit("_", 1)[1],
                    "ensemble_member": "none-provider-statistic",
                    **({"cell_methods": "time: sum", "accumulation_interval_hours": 1.0,
                        "period_semantics": "preceding hour ending at valid_time"}
                       if sample["field"].rsplit("_", 1)[0].endswith("_1hr") else {}),
                })
            latitudes = box["latitudes"] if box else [samples[0]["latitude"]]
            longitudes = box["longitudes"] if box else [samples[0]["longitude"]]
            dataset = xarray.Dataset(data_vars, coords={
                "valid_time": numpy.asarray([numpy.datetime64(item.replace(tzinfo=None), "ns") for item in valid]),
                "latitude": latitudes, "longitude": longitudes,
            }, attrs={"source_product": PRODUCT, "source_product_version": "3.0.0", "native_grid": grid_name})
            output = workdir / f"weathernext3-statistics-{grid_name}.zarr.zip"
            write_zarr(dataset, output)
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            null_fields = sorted(name for name in data_vars if manifest["fields"][name].get("null_count", 0) > 0)
            provenance = {
                "source_id": self.source_id, "producer": "Google DeepMind", "product": PRODUCT,
                "product_version": "3.0.0", "access_surface": ACCESS_SURFACE,
                "adapter_version": self.adapter_version, "native_crs": "EPSG:4326",
                "native_resolution": "0.1 degree" if grid_name == "0p1" else "0.05 degree station-head grid",
                "evidence_classes": ["retrieved"],
                "evidence_class_by_variable": {name: "retrieved" for name in data_vars},
                "quality": {"status": "passed", "flags": [f"provider_nodata:{name}" for name in null_fields]},
                "coverage": {"status": "partial" if null_fields else "complete",
                    "usable_fields": len(data_vars) - len(null_fields), "acquired_fields": len(data_vars)},
                "sha256": digest,
                "field_dispositions": dispositions, "ensemble": {"documented_size": 64, "member_id": None,
                    "representation": "provider-computed-statistic"},
                "run": {"initialization": manifest["times"]["initialization"], "valid_times": manifest["times"]["valid"],
                    "publication_time": manifest["times"]["publication"], "object_updated_is_publication": False},
                "accumulation_periods": [
                    {"valid_time": item.isoformat().replace("+00:00", "Z"),
                     "period_start": (item - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                     "period_end": item.isoformat().replace("+00:00", "Z")}
                    for item in valid
                ],
                "upstream_objects": manifest.get("objects", []), "usage": manifest.get("usage", {}),
                "terms": {key: manifest["identity"].get(key) for key in ("terms_class", "terms_url", "terms_reviewed", "terms_sha256")},
                "input_lineage": manifest["identity"].get("input_lineage"),
                "attribution": manifest["identity"].get("attribution"),
            }
            artifacts.append(Artifact(f"weathernext3-statistics-{grid_name}", MEDIA_ZARR, output, provenance))
        return RunResult(self.source_id, candidate.provider_run_id, candidate.run_time,
                         _time(manifest["times"]["retrieval"]), True, True, artifacts, "EPSG:4326",
                         f"{sum(len(group) for group in groups.values())} retrieved; {sum(v == 'deferred' for v in dispositions.values())} deferred")
