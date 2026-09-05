#!/usr/bin/env python3
"""Build and validate evidence for a bounded WeatherNext 3 probe.

This tool deliberately has no authentication implementation. It prepares the
exact public field inventory and rejects incomplete or over-budget evidence.
It does not execute or meter provider requests; the counters are evidence
supplied by a separately approved transport after requester-billing preflight.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PRODUCT = "weathernext_3_0_0_statistics"
BUCKET = "weathernext3_statistics_spatial"
PREFIX = f"{PRODUCT}/zarr/"
INITIALIZATION = "2026-08-01T00:00:00Z"
LEADS_HOURS = [6, 12, 24]
VALID_TIMES = ["2026-08-01T06:00:00Z", "2026-08-01T12:00:00Z", "2026-08-02T00:00:00Z"]
POINT = {"latitude": 47.5, "longitude": -52.7, "selection": "nearest_native_cell"}
CAPS = {
    "received_bytes": 512 * 1024 * 1024,
    "metadata_bytes": 4 * 1024 * 1024,
    "decoded_working_bytes": 128 * 1024 * 1024,
    "output_bytes": 5 * 1024 * 1024,
    "object_requests": 256,
    "deadline_seconds": 300,
}

STATISTICS = ("mean", "p10", "p25", "p50", "p75", "p90")
BASE_FIELDS = {
    "temperature_2m": ("K", "0p1"),
    "dewpoint_temperature_2m": ("K", "0p1"),
    "wind_speed_10m": ("m/s", "0p1"),
    "wind_speed_100m": ("m/s", "0p1"),
    "u_component_of_wind_10m": ("m/s", "0p1"),
    "v_component_of_wind_10m": ("m/s", "0p1"),
    "u_component_of_wind_100m": ("m/s", "0p1"),
    "v_component_of_wind_100m": ("m/s", "0p1"),
    "surface_solar_radiation_downwards_1hr": ("J/m^2", "0p1"),
    "total_sky_direct_solar_radiation_at_surface_1hr": ("J/m^2", "0p1"),
    "total_precipitation_1hr": ("m", "0p1"),
    "imerg_tp_1hr": ("m", "0p1"),
    "experimental_tp_1hr": ("m", "0p1"),
    "total_cloud_cover": ("fraction_0_to_1", "0p1"),
    "low_cloud_cover": ("fraction_0_to_1", "0p1"),
    "medium_cloud_cover": ("fraction_0_to_1", "0p1"),
    "high_cloud_cover": ("fraction_0_to_1", "0p1"),
    "mean_sea_level_pressure": ("Pa", "0p1"),
    "sea_surface_temperature": ("K", "0p1"),
    "station_head_temperature_2m": ("K", "0p05"),
    "station_head_dewpoint_temperature_2m": ("K", "0p05"),
}
EXPECTED_FIELDS = tuple(f"{base}_{stat}" for base in BASE_FIELDS for stat in STATISTICS)
SELECTED_FIELDS = (
    "total_cloud_cover_mean",
    "low_cloud_cover_mean",
    "medium_cloud_cover_mean",
    "high_cloud_cover_mean",
    "total_cloud_cover_p10",
    "total_cloud_cover_p90",
)
DOCUMENTED_ABSENCES = (
    "fog",
    "visibility",
    "ceiling",
    "cloud_base",
    "cloud_top",
)
FIELD_STATES = {"retrieved", "missing", "unsupported", "deferred"}


def template() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "result": "not_run",
        "blocker": "sample transport has not supplied bounded retrieval evidence",
        "request": {
            "bucket": BUCKET,
            "prefix": PREFIX,
            "requester_billing_identity": None,
            "initialization": INITIALIZATION,
            "lead_hours": LEADS_HOURS,
            "point": POINT,
            "selected_fields": list(SELECTED_FIELDS),
        },
        "caps": CAPS,
        "usage": {key: None for key in CAPS},
        "identity": {
            "product_version": "3.0.0",
            "access_surface": "gcs_statistics_spatial",
            "ensemble_size_documented": 64,
            "member_id": None,
            "terms_class": "historical_cc_by_4_0_candidate_must_be_verified_at_read_time",
        },
        "coordinates": {
            "dimensions": None,
            "selected_native_cell": None,
            "coordinate_direction": None,
            "chunk_or_shard_layout": None,
        },
        "times": {
            "initialization": INITIALIZATION,
            "valid": [],
            "publication": None,
            "retrieval": None,
            "object_updated_is_publication": False,
        },
        "fields": {
            name: {
                "status": "deferred",
                "selected_for_sample": name in SELECTED_FIELDS,
                "statistic": name.rsplit("_", 1)[1],
                "unit": BASE_FIELDS[name.rsplit("_", 1)[0]][0],
                "grid": BASE_FIELDS[name.rsplit("_", 1)[0]][1],
                "dtype": None,
                "fill_value": None,
                "null_count": None,
                "finite_min": None,
                "finite_max": None,
            }
            for name in EXPECTED_FIELDS
        },
        "documented_absences": {
            name: {"status": "unsupported", "observed_in_manifest": False}
            for name in DOCUMENTED_ABSENCES
        },
        "objects": [],
        "decoder": None,
        "notes": [
            "Expected fields come from public documentation and are not live observations.",
            "A successful small sample does not prove full-field implementation readiness.",
        ],
    }


def validate(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    request = manifest.get("request")
    if not isinstance(request, dict):
        return ["request must be an object"]
    expected_request = {
        "bucket": BUCKET,
        "prefix": PREFIX,
        "requester_billing_identity": None,
        "initialization": INITIALIZATION,
        "lead_hours": LEADS_HOURS,
        "point": POINT,
        "selected_fields": list(SELECTED_FIELDS),
    }
    for key, expected in expected_request.items():
        if request.get(key) != expected:
            errors.append(f"request {key} must equal {expected!r}")
    if request.get("requester_billing_identity") is not None:
        errors.append("requester_billing_identity must be null")
    fields = manifest.get("fields", {})
    if not isinstance(fields, dict):
        return errors + ["fields must be an object"]
    if set(fields) != set(EXPECTED_FIELDS):
        missing = sorted(set(EXPECTED_FIELDS) - set(fields))
        extra = sorted(set(fields) - set(EXPECTED_FIELDS))
        errors.append(f"field inventory mismatch; missing={missing}, extra={extra}")
    for name, item in fields.items():
        if not isinstance(item, dict):
            errors.append(f"{name}: field evidence must be an object")
            continue
        state = item.get("status")
        if state not in FIELD_STATES:
            errors.append(f"{name}: invalid status {state!r}")
        if state == "retrieved" and item.get("unit") in {"fraction_0_to_1", "(0 - 1)"}:
            low, high = item.get("finite_min"), item.get("finite_max")
            if low is None or high is None or not (0 <= low <= high <= 1):
                errors.append(f"{name}: retrieved finite range is absent or outside [0,1]")
    usage = manifest.get("usage", {})
    if not isinstance(usage, dict):
        return errors + ["usage must be an object"]
    for key, cap in CAPS.items():
        value = usage.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > cap
        ):
            errors.append(f"usage {key}={value!r} exceeds or does not satisfy cap {cap}")
    if manifest.get("result") == "success":
        for name in SELECTED_FIELDS:
            if fields.get(name, {}).get("status") != "retrieved":
                errors.append(f"success requires selected field {name} to be retrieved")
        if any(usage.get(key) is None for key in CAPS):
            errors.append("success requires every usage counter")
        for name in SELECTED_FIELDS:
            item = fields.get(name)
            if isinstance(item, dict) and (
                not item.get("dtype")
                or isinstance(item.get("null_count"), bool)
                or not isinstance(item.get("null_count"), int)
                or item.get("null_count") < 0
            ):
                errors.append(f"success requires numeric summary metadata for {name}")
        times = manifest.get("times")
        if not isinstance(times, dict) or times.get("initialization") != INITIALIZATION:
            errors.append("success requires the exact initialization time")
        elif times.get("valid") != VALID_TIMES:
            errors.append("success requires the exact valid times for leads 6, 12 and 24")
        elif not times.get("retrieval"):
            errors.append("success requires a retrieval time")
        coordinates = manifest.get("coordinates")
        if not isinstance(coordinates, dict):
            errors.append("success requires coordinate evidence")
        else:
            cell = coordinates.get("selected_native_cell")
            if not isinstance(cell, dict) or not all(
                isinstance(cell.get(key), (int, float)) and not isinstance(cell.get(key), bool)
                for key in ("latitude", "longitude")
            ):
                errors.append("success requires numeric selected native-cell coordinates")
            if not coordinates.get("dimensions") or not coordinates.get("coordinate_direction"):
                errors.append("success requires dimensions and coordinate direction")
            if not coordinates.get("chunk_or_shard_layout"):
                errors.append("success requires chunk or shard layout")
        objects = manifest.get("objects")
        if not isinstance(objects, list) or not objects:
            errors.append("success requires source object identities")
        elif any(
            not isinstance(obj, dict)
            or not obj.get("name")
            or not (obj.get("generation") or obj.get("etag"))
            or isinstance(obj.get("size"), bool)
            or not isinstance(obj.get("size"), int)
            or obj.get("size") < 0
            for obj in objects
        ):
            errors.append("each source object requires name, generation/etag and byte size")
        decoder = manifest.get("decoder")
        if not isinstance(decoder, dict) or not decoder.get("name") or not decoder.get("version"):
            errors.append("success requires decoder name and version")
        if manifest.get("blocker") is not None:
            errors.append("success requires blocker to be null")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("template", "validate"))
    parser.add_argument("path", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "template":
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0
    if args.path is None:
        parser.error("validate requires a manifest path")
    manifest = json.loads(args.path.read_text())
    errors = validate(manifest)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("WeatherNext bounded-probe manifest is internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
