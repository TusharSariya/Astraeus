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


def _run_object_prefix(initialization: str) -> str:
    run = _time(initialization)
    return (
        f"{PRODUCT}/zarr/2026_to_present/"
        f"{run:%Y%m%d_%H}hr_01_preds/predictions.zarr"
    )


def _validate_object_identity(manifest: dict[str, Any], selected: set[str], leads: list[int]) -> None:
    """Validate the acquisition's own identity evidence.

    This proves that the record is structurally self-consistent. It cannot
    cryptographically establish that an arbitrary JSON record came from GCS.
    """
    objects = manifest.get("objects")
    if not isinstance(objects, list) or not objects:
        raise WeatherNextManifestError("source object identity evidence is missing")
    prefix = _run_object_prefix(manifest["times"]["initialization"])
    paths: set[str] = set()
    field_leads: list[tuple[str, int]] = []
    is_box = manifest.get("avalon_box_sample") is not None
    required_ancillary = set()
    if is_box:
        required_ancillary = {f"{prefix}/zarr.json", f"{prefix}/lat_0p1/c/0", f"{prefix}/lon_0p1/c/0",
                              f"{prefix}/lead_time/c/0", f"{prefix}/init_time/c"}
        if "grids" in manifest["avalon_box_sample"]:
            required_ancillary.update({f"{prefix}/lat_0p05/c/0", f"{prefix}/lon_0p05/c/0"})
        else:
            required_ancillary.update(f"{prefix}/datetime/c/{lead - 1}" for lead in leads)
    for item in objects:
        path = item.get("name", item.get("object"))
        if not isinstance(path, str) or not path.startswith(f"{prefix}/") or path in paths:
            raise WeatherNextManifestError("source object path is missing, duplicated or outside the exact run")
        paths.add(path)
        if not isinstance(item.get("generation"), str) or not item["generation"].isdigit():
            raise WeatherNextManifestError(f"{path}: source generation is missing or invalid")
        if not isinstance(item.get("etag"), str) or not item["etag"]:
            raise WeatherNextManifestError(f"{path}: source ETag is missing")
        if not isinstance(item.get("size"), int) or isinstance(item["size"], bool) or item["size"] <= 0:
            raise WeatherNextManifestError(f"{path}: source size is missing or invalid")
        post_read = item.get("post_read_identity_verified")
        pinned_read = item.get("identity_verification_method") == "generation_qualified_read_with_size_check"
        if post_read is False or (post_read is not True and not pinned_read):
            raise WeatherNextManifestError(f"{path}: source identity has no verified read mechanism")

        relative = path.removeprefix(f"{prefix}/")
        matched_field = False
        for field in selected:
            marker = f"{field}/c/"
            if relative.startswith(marker) and relative.endswith("/0/0"):
                try:
                    chunk = int(relative.removeprefix(marker).split("/", 1)[0])
                except ValueError as error:
                    raise WeatherNextManifestError(f"{path}: invalid field chunk identity") from error
                declared = item.get("field", field)
                if declared != field:
                    raise WeatherNextManifestError(f"{path}: source object field identity mismatch")
                # These two recorders deliberately retain their provider path
                # conventions: box chunks use zero-based lead indexes while
                # the point proof names the lead coordinate itself.
                legacy_box = is_box and "grids" not in manifest["avalon_box_sample"]
                matching_lead = next((lead for lead in leads if chunk == (lead - 1 if legacy_box else lead)), None)
                if matching_lead is None:
                    raise WeatherNextManifestError(f"{path}: source object lead identity mismatch")
                field_leads.append((field, matching_lead))
                matched_field = True
                break
        if not matched_field and path not in required_ancillary:
            raise WeatherNextManifestError(f"{path}: source object is not bound to sampled data or required coordinates")

    expected = {(field, lead) for field in selected for lead in leads}
    if set(field_leads) != expected or len(field_leads) != len(expected):
        raise WeatherNextManifestError("source objects do not bind every selected field and lead exactly once")

    if is_box:
        if not required_ancillary <= paths:
            raise WeatherNextManifestError("source metadata or coordinate object identity is missing")


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
    _validate_object_identity(manifest, retrieved, leads)
    valid = manifest.get("times", {}).get("valid", [])
    box = manifest.get("avalon_box_sample")
    if len(leads) != len(valid) or (box is None and any(
            len(item.get("values", [])) != len(leads) for item in samples.values())):
        raise WeatherNextManifestError("lead, valid-time and value cardinalities differ")
    initialization = _time(manifest["times"]["initialization"])
    if any(_time(stamp) != initialization + timedelta(hours=lead) for lead, stamp in zip(leads, valid)):
        raise WeatherNextManifestError("valid time is not initialization plus lead")
    for name, item in samples.items():
        expected_unit = _expected_unit(name)
        if item.get("unit") != expected_unit or fields[name].get("unit") != expected_unit:
            raise WeatherNextManifestError(f"{name}: native unit mismatch")
        if box is None or "grids" not in box:
            if not all(value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and numpy.isfinite(value))
                       for value in item["values"]):
                raise WeatherNextManifestError(f"{name}: non-finite or non-numeric sample value")
            null_count = sum(value is None for value in item["values"])
            if fields[name].get("null_count") != null_count:
                raise WeatherNextManifestError(f"{name}: fill-mask count mismatch")
            if name in CLOUD_FIELDS:
                for value in item["values"]:
                    if value is not None and not 0 <= value <= 1:
                        raise WeatherNextManifestError(f"{name}: invalid cloud fraction")
    if box is not None:
        box_items = box.get("fields", sample_items if "grids" in box else [])
        box_fields = {item["field"]: item for item in box_items}
        if len(box_fields) != len(box_items):
            raise WeatherNextManifestError("duplicate Avalon box field identity")
        if set(box_fields) != retrieved:
            raise WeatherNextManifestError("Avalon box fields and retrieved dispositions differ")
        native_grid_schema = "grids" in box
        grids = box.get("grids")
        if grids is None:
            grids = {"0p1": {"latitudes": box.get("latitudes", []), "longitudes": box.get("longitudes", []),
                              "native_resolution_degrees": 0.1}}
            if not set(box_fields) <= set(CLOUD_FIELDS):
                raise WeatherNextManifestError("legacy Avalon box accepts only supported 0.1-degree cloud statistics")
        if set(grids) != {item.get("grid", "0p1") for item in box_items}:
            raise WeatherNextManifestError("Avalon box native grids and fields differ")
        if "grids" in box and box.get("bounds") != {"west": -58.0, "south": 45.0, "east": -46.0, "north": 50.5}:
            raise WeatherNextManifestError("Avalon box bounds differ from the declared evidence box")
        for grid_name, grid in grids.items():
            expected_resolution = 0.1 if grid_name == "0p1" else 0.05 if grid_name == "0p05" else None
            if expected_resolution is None or grid.get("native_resolution_degrees") != expected_resolution:
                raise WeatherNextManifestError("Avalon box native grid identity is invalid")
            for coordinate_name in ("latitudes", "longitudes"):
                coordinates = grid.get(coordinate_name, [])
                if not coordinates or any(not isinstance(value, (int, float)) or not numpy.isfinite(value) for value in coordinates):
                    raise WeatherNextManifestError(f"Avalon box {coordinate_name} coordinate is invalid")
                differences = numpy.diff(coordinates)
                if not (numpy.all(differences > 0) and numpy.allclose(differences, expected_resolution, atol=5e-5)):
                    raise WeatherNextManifestError(
                        f"Avalon box {coordinate_name} coordinates must be monotonic native {expected_resolution}-degree centres")
            if native_grid_schema:
                expected_shape = (56, 121) if grid_name == "0p1" else (111, 241)
                if (len(grid["latitudes"]), len(grid["longitudes"])) != expected_shape:
                    raise WeatherNextManifestError(f"Avalon box {grid_name} does not contain every native cell")
                if not (numpy.isclose(grid["latitudes"][0], 45.0, atol=5e-5)
                        and numpy.isclose(grid["latitudes"][-1], 50.5, atol=5e-5)
                        and numpy.isclose(grid["longitudes"][0], -58.0, atol=5e-5)
                        and numpy.isclose(grid["longitudes"][-1], -46.0, atol=5e-5)):
                    raise WeatherNextManifestError(f"Avalon box {grid_name} coordinate bounds are incomplete")
        for name, item in box_fields.items():
            grid_name = item.get("grid", "0p1")
            if grid_name != _expected_grid(name):
                raise WeatherNextManifestError(f"{name}: native grid mismatch")
            latitudes = grids[grid_name]["latitudes"]
            longitudes = grids[grid_name]["longitudes"]
            if [lead.get("lead_hours") for lead in item.get("leads", [])] != leads:
                raise WeatherNextManifestError(f"{name}: Avalon box lead identity mismatch")
            null_count = 0
            for lead in item["leads"]:
                values = lead.get("values", [])
                if len(values) != len(latitudes) or any(len(row) != len(longitudes) for row in values):
                    raise WeatherNextManifestError(f"{name}: Avalon box shape mismatch")
                for row in values:
                    for value in row:
                        if value is None:
                            null_count += 1
                        elif not isinstance(value, (int, float)) or isinstance(value, bool) or not numpy.isfinite(value):
                            raise WeatherNextManifestError(f"{name}: non-finite or non-numeric Avalon box value")
                        elif name in CLOUD_FIELDS and not 0 <= value <= 1:
                            raise WeatherNextManifestError(f"{name}: invalid Avalon box cloud fraction")
            if fields[name].get("null_count") != null_count:
                raise WeatherNextManifestError(f"{name}: fill-mask count mismatch")
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
        box_fields = ({item["field"]: item for item in box.get("fields", manifest["sample"]["fields"])}
                      if box else {})
        dispositions = {name: item["status"] for name, item in manifest["fields"].items()}
        groups: dict[str, list[dict[str, Any]]] = {}
        for sample in manifest["sample"]["fields"]:
            groups.setdefault(sample.get("grid", "0p1"), []).append(sample)
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
            if box:
                grid = box.get("grids", {}).get(grid_name)
                latitudes = grid["latitudes"] if grid else box["latitudes"]
                longitudes = grid["longitudes"] if grid else box["longitudes"]
            else:
                latitudes = [samples[0]["latitude"]]
                longitudes = [samples[0]["longitude"]]
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
                "upstream_objects": manifest["objects"], "usage": manifest.get("usage", {}),
                "acquisition_scope": {
                    "kind": "experimental_partial_sample",
                    "spatial_coverage": "avalon_45_50p5n_58_46w_native_grids" if box and "grids" in box
                    else "avalon_16x16_box" if box else "single_native_cell_per_grid",
                    "lead_hours": manifest["sample"]["lead_hours"],
                    "operational_publishable": False,
                },
                "terms": {key: manifest["identity"].get(key) for key in ("terms_class", "terms_url", "terms_reviewed", "terms_sha256")},
                "input_lineage": manifest["identity"].get("input_lineage"),
                "attribution": manifest["identity"].get("attribution"),
            }
            artifacts.append(Artifact(f"weathernext3-statistics-{grid_name}", MEDIA_ZARR, output, provenance))
        return RunResult(self.source_id, candidate.provider_run_id, candidate.run_time,
                         _time(manifest["times"]["retrieval"]), False, False, artifacts, "EPSG:4326",
                         "experimental partial sample; non-publishable until an accepted full-coverage and cadence contract exists; "
                         f"{sum(len(group) for group in groups.values())} retrieved; {sum(v == 'deferred' for v in dispositions.values())} deferred")
