#!/usr/bin/env python3
"""Sequentially decode a bounded box from all 126 WeatherNext 3 arrays."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import zarr

import weathernext_probe_manifest as contract
from weathernext_bounded_sample import RUN_PREFIX, _decode_array, _node

RECEIVED_CAP = 4 * 1024**3
REQUEST_CAP = 300
DECODED_CAP = 128 * 1024**2
OUTPUT_CAP = 64 * 1024**2
LOCAL_RESERVATION = 4 * 1024**3
DEADLINE_SECONDS = 30 * 60
LEAD = 6
AVALON_BOX = {"west": -58.0, "south": 45.0, "east": -46.0, "north": 50.5}


class SampleError(RuntimeError):
    pass


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


class Transport:
    def __init__(self, deadline: float):
        self.deadline = deadline
        self.requests = 0
        self.received_bytes = 0

    def run(self, args: list[str]) -> subprocess.CompletedProcess[bytes]:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise SampleError("30-minute sample deadline expired")
        if self.requests >= REQUEST_CAP:
            raise SampleError("object-operation cap would be exceeded")
        self.requests += 1
        env = os.environ.copy()
        for key in ("CLOUDSDK_BILLING_QUOTA_PROJECT", "GOOGLE_CLOUD_QUOTA_PROJECT",
                    "CLOUDSDK_CORE_PROJECT", "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
                    "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"):
            env[key] = ""
        try:
            return subprocess.run(["gcloud", "--configuration=astraeus", "storage", *args], env=env,
                                  check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining)
        except subprocess.CalledProcessError as error:
            raise SampleError(f"gcloud storage operation failed with exit code {error.returncode}; stderr redacted") from error
        except subprocess.TimeoutExpired as error:
            raise SampleError("30-minute sample deadline expired") from error

    def download(self, uri: str, destination: Path, expected_size: int):
        if self.received_bytes + expected_size > RECEIVED_CAP:
            raise SampleError("4 GiB received-byte cap would be exceeded")
        required = LOCAL_RESERVATION + DECODED_CAP + OUTPUT_CAP + expected_size
        if shutil.disk_usage(destination.parent).free < required:
            raise SampleError("physical free-space margin would be violated")
        self.run(["cp", uri, str(destination), "--quiet"])
        actual = destination.stat().st_size
        if actual != expected_size:
            raise SampleError(f"downloaded size mismatch: expected {expected_size}, got {actual}")
        self.received_bytes += actual


def run(plan_path: Path, output: Path) -> dict:
    started = time.monotonic()
    transport = Transport(started + DEADLINE_SECONDS)
    plan = json.loads(plan_path.read_text())
    if plan.get("result") != "success" or plan.get("field_count") != 126 or plan.get("requester_pays") is not False:
        raise SampleError("all-field metadata plan is not a successful non-requester-paid proof")
    planned = {item["field"]: item for item in plan["field_objects"]}
    if set(planned) != set(contract.EXPECTED_FIELDS) or sum(item["size"] for item in planned.values()) > RECEIVED_CAP:
        raise SampleError("all-field plan is incomplete or over the 4 GiB cap")

    with tempfile.TemporaryDirectory(prefix="weathernext-all-fields-") as raw_name:
        raw = Path(raw_name)
        metadata_uri = f"{RUN_PREFIX}/zarr.json"
        metadata_item = json.loads(transport.run(["objects", "describe", metadata_uri, "--format=json"]).stdout)
        metadata_path = raw / "root-zarr.json"
        transport.download(f"{metadata_uri}#{metadata_item['generation']}", metadata_path, int(metadata_item["size"]))
        metadata = json.loads(metadata_path.read_text())
        ancillary_objects = [{
            "object": metadata_uri.removeprefix(f"gs://{contract.BUCKET}/"),
            "generation": str(metadata_item["generation"]), "etag": metadata_item["etag"],
            "size": int(metadata_item["size"]), "updated": metadata_item.get("updateTime"),
            "identity_verification_method": "generation_qualified_read_with_size_check",
        }]

        coordinate_values = {}
        coordinate_objects = {
            "lat_0p1": "lat_0p1/c/0", "lon_0p1": "lon_0p1/c/0",
            "lat_0p05": "lat_0p05/c/0", "lon_0p05": "lon_0p05/c/0",
            "lead_time": "lead_time/c/0", "init_time": "init_time/c",
        }
        for name, relative in coordinate_objects.items():
            uri = f"{RUN_PREFIX}/{relative}"
            item = json.loads(transport.run(["objects", "describe", uri, "--format=json"]).stdout)
            local = raw / relative
            local.parent.mkdir(parents=True, exist_ok=True)
            transport.download(f"{uri}#{item['generation']}", local, int(item["size"]))
            coordinate_values[name] = _decode_array(raw, name, _node(metadata, name), relative)
            ancillary_objects.append({
                "object": uri.removeprefix(f"gs://{contract.BUCKET}/"),
                "generation": str(item["generation"]), "etag": item["etag"],
                "size": int(item["size"]), "updated": item.get("updateTime"),
                "identity_verification_method": "generation_qualified_read_with_size_check",
            })

        lead_values = coordinate_values["lead_time"]
        matches = np.flatnonzero(lead_values == LEAD)
        if len(matches) != 1:
            raise SampleError("lead 6 does not have exactly one coordinate")
        lead_index = int(matches[0])
        init_days = int(coordinate_values["init_time"].item())
        initialization = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(days=init_days)
        if initialization.isoformat().replace("+00:00", "Z") != contract.INITIALIZATION:
            raise SampleError("initialization coordinate mismatch")

        samples = []
        box_grids = {}
        box_indices = {}
        for grid_name in ("0p1", "0p05"):
            latitudes = coordinate_values[f"lat_{grid_name}"]
            longitudes = coordinate_values[f"lon_{grid_name}"]
            normalized_longitudes = ((longitudes + 180) % 360) - 180
            latitude_indices = np.flatnonzero(
                (latitudes >= AVALON_BOX["south"]) & (latitudes <= AVALON_BOX["north"])
            )
            longitude_indices = np.flatnonzero(
                (normalized_longitudes >= AVALON_BOX["west"]) & (normalized_longitudes <= AVALON_BOX["east"])
            )
            if not len(latitude_indices) or not len(longitude_indices):
                raise SampleError(f"Avalon box selects no {grid_name} native cells")
            selected_latitudes = np.asarray(latitudes[latitude_indices], dtype="float64")
            selected_longitudes = np.asarray(normalized_longitudes[longitude_indices], dtype="float64")
            # The normalized output uses ascending geographic coordinates on
            # both native grids, independently of provider storage direction.
            latitude_order = np.argsort(selected_latitudes)
            longitude_order = np.argsort(selected_longitudes)
            box_indices[grid_name] = (latitude_indices[latitude_order], longitude_indices[longitude_order])
            box_grids[grid_name] = {
                "latitudes": selected_latitudes[latitude_order].tolist(),
                "longitudes": selected_longitudes[longitude_order].tolist(),
                "native_resolution_degrees": 0.1 if grid_name == "0p1" else 0.05,
            }
        fields = contract.template()["fields"]
        max_decoded = max(value.nbytes for value in coordinate_values.values())
        for name in contract.EXPECTED_FIELDS:
            node = _node(metadata, name)
            dimensions = node.get("dimension_names")
            if dimensions not in (["lead_time", "lat_0p1", "lon_0p1"], ["lead_time", "lat_0p05", "lon_0p05"]):
                raise SampleError(f"{name}: unexpected dimensions")
            grid_name = dimensions[1].removeprefix("lat_")
            latitudes = coordinate_values[dimensions[1]]
            longitudes = coordinate_values[dimensions[2]]
            if node.get("data_type") != "float32" or node.get("shape") != [len(lead_values), len(latitudes), len(longitudes)]:
                raise SampleError(f"{name}: unexpected native shape or dtype")
            if node.get("chunk_grid", {}).get("configuration", {}).get("chunk_shape") != [1, len(latitudes), len(longitudes)]:
                raise SampleError(f"{name}: unexpected native chunk shape")
            relative = f"{name}/c/{lead_index}/0/0"
            item = planned[name]
            local = raw / relative
            local.parent.mkdir(parents=True, exist_ok=True)
            uri = f"gs://{contract.BUCKET}/{item['object']}#{item['generation']}"
            transport.download(uri, local, int(item["size"]))
            grid = _decode_array(raw, name, node, relative, (lead_index, slice(None), slice(None)))
            max_decoded = max(max_decoded, grid.nbytes)
            if max_decoded > DECODED_CAP:
                raise SampleError("decoded working-array cap exceeded")
            latitude_indices, longitude_indices = box_indices[grid_name]
            selected = grid[np.ix_(latitude_indices, longitude_indices)]
            values = [
                [float(value) if math.isfinite(float(value)) else None for value in row]
                for row in selected
            ]
            finite_values = [value for row in values for value in row if value is not None]
            if name in contract.SELECTED_FIELDS and any(not 0 <= value <= 1 for value in finite_values):
                raise SampleError(f"{name}: cloud fraction outside [0, 1]")
            unit = str(node.get("attributes", {}).get("units", "unknown"))
            if unit != _expected_unit(name):
                raise SampleError(f"{name}: unexpected native unit {unit}")
            fields[name].update(status="retrieved", selected_for_sample=True, grid=grid_name,
                                unit=unit, dtype=str(node.get("data_type")),
                                fill_value=str(node.get("fill_value", "NaN")),
                                null_count=sum(value is None for row in values for value in row),
                                finite_min=min(finite_values) if finite_values else None,
                                finite_max=max(finite_values) if finite_values else None)
            samples.append({"field": name, "unit": unit, "grid": grid_name,
                            "statistic": name.rsplit("_", 1)[1],
                            "leads": [{"lead_hours": LEAD, "values": values}]})
            shutil.rmtree(raw / name)

    manifest = contract.template()
    manifest.update(result="success", blocker=None, fields=fields)
    manifest["request"].update(lead_hours=[LEAD], selected_fields=list(contract.EXPECTED_FIELDS))
    manifest["times"].update(valid=["2026-08-01T06:00:00Z"], retrieval=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    manifest["sample"] = {"lead_hours": [LEAD], "fields": samples}
    manifest["avalon_box_sample"] = {
        "bounds": AVALON_BOX,
        "selection": "all_native_cell_centres_within_inclusive_bounds",
        "grids": box_grids,
    }
    manifest["identity"].update(terms_url="https://storage.googleapis.com/weathernext-public/terms-of-use.pdf",
                                terms_reviewed="2026-09-05", input_lineage="ECMWF HRES analysis documented by provider",
                                attribution="WeatherNext data provided by Google")
    manifest["usage"] = {"received_bytes": transport.received_bytes, "decoded_working_bytes": max_decoded,
                         "object_requests": transport.requests, "deadline_seconds": math.ceil(time.monotonic() - started),
                         "output_bytes": 0}
    # Every body was fetched through its generation-qualified URI and its byte
    # count matched the description captured in the plan. Name that mechanism
    # precisely; this recorder does not perform a later metadata/ETag recheck.
    manifest["objects"] = ancillary_objects + [
        {**item, "identity_verification_method": "generation_qualified_read_with_size_check"}
        for item in plan["field_objects"]
    ]
    manifest["decoder"] = {"name": "zarr", "version": zarr.__version__, "numpy": np.__version__}
    manifest["resource_gate"] = {"received_cap": RECEIVED_CAP, "decoded_cap": DECODED_CAP,
                                 "local_reservation": LOCAL_RESERVATION, "deadline": DEADLINE_SECONDS}
    for _ in range(4):
        encoded = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        manifest["usage"]["output_bytes"] = len(encoded.encode())
    encoded = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if len(encoded.encode()) > OUTPUT_CAP:
        raise SampleError("output cap exceeded")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded)
    return {"sha256": hashlib.sha256(encoded.encode()).hexdigest(), **manifest["usage"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = run(args.plan, args.output)
    print(f"wrote 126-field sample; sha256 {result['sha256']}; bytes {result['received_bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
