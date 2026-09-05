#!/usr/bin/env python3
"""Retrieve the exact bounded WeatherNext 3 point sample for issue 76.

The transport deliberately shells out to the already-approved ``astraeus``
gcloud configuration. Every call clears requester-project and impersonation
overrides, names that configuration explicitly, and targets one known object.
It never reads or prints account or credential material.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

import numpy as np
import zarr

import weathernext_probe_manifest as contract


RUN_PREFIX = (
    f"gs://{contract.BUCKET}/{contract.PREFIX}"
    "2026_to_present/20260801_00hr_01_preds/predictions.zarr"
)
METADATA_OBJECT = f"{RUN_PREFIX}/zarr.json"
COORDINATE_OBJECTS = {
    "lat_0p1": "lat_0p1/c/0",
    "lon_0p1": "lon_0p1/c/0",
    "lead_time": "lead_time/c/0",
    "init_time": "init_time/c",
}
DEADLINE_SECONDS = contract.CAPS["deadline_seconds"]
LOCAL_FREE_SPACE_RESERVE = 1024 * 1024 * 1024
AVALON_BOX = {"west": -54.0, "south": 46.5, "east": -52.5, "north": 48.0}


class ProbeError(RuntimeError):
    pass


class Transport:
    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.requests = 0
        self.received_bytes = 0

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[bytes]:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeError("five-minute probe deadline expired")
        if self.requests >= contract.CAPS["object_requests"]:
            raise ProbeError("object-request cap would be exceeded")
        self.requests += 1
        env = os.environ.copy()
        for key in (
            "CLOUDSDK_BILLING_QUOTA_PROJECT",
            "GOOGLE_CLOUD_QUOTA_PROJECT",
            "CLOUDSDK_CORE_PROJECT",
            "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
            "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
            "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
        ):
            env[key] = ""
        command = ["gcloud", "--configuration=astraeus", "storage", *args]
        try:
            result = subprocess.run(
                command,
                env=env,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=remaining,
            )
        except subprocess.CalledProcessError as exc:
            raise ProbeError(
                f"gcloud storage operation failed with exit code {exc.returncode}; stderr redacted"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProbeError("five-minute probe deadline expired") from exc
        return result

    def describe(self, uri: str) -> dict[str, Any]:
        result = self._run(["objects", "describe", uri, "--format=json"])
        return json.loads(result.stdout)

    def download(self, uri: str, destination: Path, expected_size: int) -> None:
        if self.received_bytes + expected_size > contract.CAPS["received_bytes"]:
            raise ProbeError("received-byte cap would be exceeded")
        required_free = (
            LOCAL_FREE_SPACE_RESERVE
            + contract.CAPS["decoded_working_bytes"]
            + contract.CAPS["output_bytes"]
            + expected_size
        )
        available = shutil.disk_usage(destination.parent).free
        if available < required_free:
            raise ProbeError(
                f"local free-space gate failed: {available} available, {required_free} required"
            )
        self._run(["cp", uri, str(destination), "--quiet"])
        actual_size = destination.stat().st_size
        if actual_size != expected_size:
            raise ProbeError(f"size mismatch for {uri}: expected {expected_size}, got {actual_size}")
        self.received_bytes += actual_size
        if self.received_bytes > contract.CAPS["received_bytes"]:
            raise ProbeError("received-byte cap exceeded")


def _node(metadata: dict[str, Any], name: str) -> dict[str, Any]:
    try:
        return metadata["consolidated_metadata"]["metadata"][name]
    except (KeyError, TypeError) as exc:
        raise ProbeError(f"consolidated metadata is missing {name}") from exc


def _decode_array(
    root: Path,
    name: str,
    node: dict[str, Any],
    chunk_path: str,
    selection: Any = None,
) -> np.ndarray:
    array_root = root / name
    array_root.mkdir(parents=True, exist_ok=True)
    (array_root / "zarr.json").write_text(json.dumps(node))
    local_chunk = array_root / chunk_path.removeprefix(f"{name}/")
    if not local_chunk.exists():
        raise ProbeError(f"local chunk is absent: {local_chunk}")
    array = zarr.open_array(array_root, mode="r")
    if selection is None:
        selection = () if array.ndim == 0 else slice(None)
    decoded = np.asarray(array[selection])
    if decoded.nbytes > contract.CAPS["decoded_working_bytes"]:
        raise ProbeError(f"decoded array exceeds working-memory cap: {decoded.nbytes}")
    return decoded


def _object_evidence(uri: str, description: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": uri.removeprefix(f"gs://{contract.BUCKET}/"),
        "generation": str(description.get("generation", "")),
        "etag": description.get("etag"),
        "size": int(description["size"]),
        "updated": description.get("updateTime"),
    }


def verify_object_identities(
    transport: Transport, objects: list[dict[str, Any]], bucket: str
) -> str:
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for item in objects:
        description = transport.describe(f"gs://{bucket}/{item['name']}")
        observed = (
            str(description.get("generation", "")),
            description.get("etag"),
            int(description["size"]),
        )
        expected = (item.get("generation", ""), item.get("etag"), item["size"])
        if observed != expected:
            raise ProbeError(f"source identity changed during read: {item['name']}")
        item["post_read_identity_verified"] = True
        item["post_read_checked_at"] = checked_at
    return checked_at


def write_validated_manifest(manifest: dict[str, Any], output: Path) -> tuple[int, str]:
    manifest["usage"]["output_bytes"] = 0
    for _ in range(4):
        encoded = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        measured = len(encoded.encode())
        if manifest["usage"]["output_bytes"] == measured:
            break
        manifest["usage"]["output_bytes"] = measured
    encoded = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    measured = len(encoded.encode())
    if measured != manifest["usage"]["output_bytes"]:
        raise ProbeError("output-byte accounting did not converge")
    errors = contract.validate(manifest)
    if errors:
        raise ProbeError("manifest validation failed: " + "; ".join(errors))
    if measured > contract.CAPS["output_bytes"]:
        raise ProbeError("output cap exceeded")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    return measured, digest


def run(output: Path) -> None:
    started = time.monotonic()
    transport = Transport(started + DEADLINE_SECONDS)
    manifest = contract.template()
    objects: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="weathernext-bounded-") as raw_dir_name:
        raw_dir = Path(raw_dir_name)
        metadata_description = transport.describe(METADATA_OBJECT)
        metadata_size = int(metadata_description["size"])
        if metadata_size > contract.CAPS["metadata_bytes"]:
            raise ProbeError("consolidated metadata exceeds metadata cap")
        metadata_path = raw_dir / "root-zarr.json"
        transport.download(METADATA_OBJECT, metadata_path, metadata_size)
        metadata = json.loads(metadata_path.read_text())
        objects.append(_object_evidence(METADATA_OBJECT, metadata_description))

        inventory = set(metadata["consolidated_metadata"]["metadata"])
        missing_inventory = set(contract.EXPECTED_FIELDS) - inventory
        if missing_inventory:
            raise ProbeError(f"documented arrays absent from metadata: {sorted(missing_inventory)}")

        coordinate_values: dict[str, np.ndarray] = {}
        for name, relative in COORDINATE_OBJECTS.items():
            uri = f"{RUN_PREFIX}/{relative}"
            description = transport.describe(uri)
            local_chunk = raw_dir / relative
            local_chunk.parent.mkdir(parents=True, exist_ok=True)
            transport.download(uri, local_chunk, int(description["size"]))
            objects.append(_object_evidence(uri, description))
            coordinate_values[name] = _decode_array(raw_dir, name, _node(metadata, name), relative)

        latitudes = coordinate_values["lat_0p1"]
        longitudes = coordinate_values["lon_0p1"]
        lead_hours = coordinate_values["lead_time"]
        init_days = int(coordinate_values["init_time"].item())
        initialization = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(days=init_days)
        if initialization.isoformat().replace("+00:00", "Z") != contract.INITIALIZATION:
            raise ProbeError(f"unexpected initialization: {initialization.isoformat()}")

        latitude_index = int(np.nanargmin(np.abs(latitudes - contract.POINT["latitude"])))
        normalized_longitude = contract.POINT["longitude"] % 360
        longitude_index = int(np.nanargmin(np.abs(longitudes - normalized_longitude)))
        selected_latitude = float(latitudes[latitude_index])
        selected_longitude_native = float(longitudes[longitude_index])
        selected_longitude = ((selected_longitude_native + 180) % 360) - 180
        normalized_lons = ((longitudes + 180) % 360) - 180
        box_latitude_indices = np.flatnonzero(
            (latitudes >= AVALON_BOX["south"]) & (latitudes <= AVALON_BOX["north"])
        )
        box_longitude_indices = np.flatnonzero(
            (normalized_lons >= AVALON_BOX["west"]) & (normalized_lons <= AVALON_BOX["east"])
        )
        if not len(box_latitude_indices) or not len(box_longitude_indices):
            raise ProbeError("Avalon box selects no native cells")

        lead_indices: dict[int, int] = {}
        for lead in contract.LEADS_HOURS:
            matches = np.flatnonzero(lead_hours == lead)
            if len(matches) != 1:
                raise ProbeError(f"lead {lead}h has {len(matches)} coordinate matches")
            lead_indices[lead] = int(matches[0])

        valid_times: list[str] = []
        datetime_node = _node(metadata, "datetime")
        for lead in contract.LEADS_HOURS:
            index = lead_indices[lead]
            relative = f"datetime/c/{index}"
            uri = f"{RUN_PREFIX}/{relative}"
            description = transport.describe(uri)
            local_chunk = raw_dir / relative
            local_chunk.parent.mkdir(parents=True, exist_ok=True)
            transport.download(uri, local_chunk, int(description["size"]))
            objects.append(_object_evidence(uri, description))
            valid_ns = int(_decode_array(raw_dir, "datetime", datetime_node, relative, index).item())
            valid = datetime.fromtimestamp(valid_ns / 1_000_000_000, tz=timezone.utc)
            expected = initialization + timedelta(hours=lead)
            if valid != expected:
                raise ProbeError(f"valid time mismatch at lead {lead}: {valid.isoformat()}")
            valid_times.append(valid.isoformat().replace("+00:00", "Z"))
            shutil.rmtree(raw_dir / "datetime")

        samples: list[dict[str, Any]] = []
        box_samples: list[dict[str, Any]] = []
        max_decoded_bytes = max(array.nbytes for array in coordinate_values.values())
        for field in contract.SELECTED_FIELDS:
            node = _node(metadata, field)
            if node.get("dimension_names") != ["lead_time", "lat_0p1", "lon_0p1"]:
                raise ProbeError(f"unexpected dimensions for {field}")
            if node.get("data_type") != "float32" or node.get("shape") != [360, 1801, 3600]:
                raise ProbeError(f"unexpected shape or dtype for {field}")
            if node.get("chunk_grid", {}).get("configuration", {}).get("chunk_shape") != [1, 1801, 3600]:
                raise ProbeError(f"unexpected chunk shape for {field}")
            if node.get("attributes", {}).get("units") != "(0 - 1)":
                raise ProbeError(f"unexpected units for {field}")

            values: list[float | None] = []
            null_count = 0
            finite_values: list[float] = []
            field_box_values: list[dict[str, Any]] = []
            for lead in contract.LEADS_HOURS:
                index = lead_indices[lead]
                relative = f"{field}/c/{index}/0/0"
                uri = f"{RUN_PREFIX}/{relative}"
                description = transport.describe(uri)
                local_chunk = raw_dir / relative
                local_chunk.parent.mkdir(parents=True, exist_ok=True)
                transport.download(uri, local_chunk, int(description["size"]))
                objects.append(_object_evidence(uri, description))
                grid = _decode_array(raw_dir, field, node, relative, (index, slice(None), slice(None)))
                max_decoded_bytes = max(max_decoded_bytes, grid.nbytes)
                value = float(grid[latitude_index, longitude_index])
                box = grid[np.ix_(box_latitude_indices, box_longitude_indices)]
                box_values = [
                    [float(item) if math.isfinite(float(item)) else None for item in row]
                    for row in box
                ]
                field_box_values.append({"lead_hours": lead, "values": box_values})
                if math.isfinite(value):
                    if not 0 <= value <= 1:
                        raise ProbeError(f"{field} has out-of-range value {value}")
                    finite_values.append(value)
                    values.append(value)
                else:
                    null_count += 1
                    values.append(None)
                shutil.rmtree(raw_dir / field)

            if not finite_values:
                raise ProbeError(f"{field} has no finite values at the selected point")
            manifest["fields"][field].update(
                status="retrieved",
                unit="(0 - 1)",
                dtype="float32",
                fill_value="NaN",
                null_count=null_count,
                finite_min=min(finite_values),
                finite_max=max(finite_values),
            )
            samples.append({"field": field, "unit": "(0 - 1)", "values": values})
            box_samples.append({"field": field, "unit": "(0 - 1)", "leads": field_box_values})

        verify_object_identities(transport, objects, contract.BUCKET)

    retrieval = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest.update(result="success", blocker=None)
    manifest["coordinates"].update(
        dimensions={"lead_time": 360, "lat_0p1": 1801, "lon_0p1": 3600},
        selected_native_cell={
            "latitude": selected_latitude,
            "longitude": selected_longitude,
            "longitude_native": selected_longitude_native,
            "latitude_index": latitude_index,
            "longitude_index": longitude_index,
        },
        coordinate_direction={
            "latitude": "descending" if latitudes[0] > latitudes[-1] else "ascending",
            "longitude": "ascending" if longitudes[0] < longitudes[-1] else "descending",
        },
        chunk_or_shard_layout={"chunk_shape": [1, 1801, 3600], "sharded": False},
    )
    manifest["times"].update(valid=valid_times, retrieval=retrieval)
    manifest["usage"].update(
        received_bytes=transport.received_bytes,
        metadata_bytes=metadata_size,
        decoded_working_bytes=max_decoded_bytes,
        object_requests=transport.requests,
        deadline_seconds=math.ceil(time.monotonic() - started),
    )
    manifest["objects"] = objects
    manifest["decoder"] = {"name": "zarr", "version": zarr.__version__, "numpy": np.__version__}
    manifest["sample"] = {"lead_hours": contract.LEADS_HOURS, "fields": samples}
    manifest["avalon_box_sample"] = {
        "bounds": AVALON_BOX,
        "selection": "all_native_cell_centres_inside_inclusive_bounds",
        "latitudes": [float(latitudes[index]) for index in box_latitude_indices],
        "longitudes": [float(normalized_lons[index]) for index in box_longitude_indices],
        "fields": box_samples,
    }
    manifest["identity"].update(
        terms_url="https://storage.googleapis.com/weathernext-public/terms-of-use.pdf",
        terms_reviewed="2026-09-05",
        terms_sha256="5fe155ace6bb11737f15bc735913c5739d31d27374269a8cbfa5f338c4d40654",
        input_lineage="ECMWF HRES analysis documented by provider",
        attribution="WeatherNext data provided by Google",
    )
    manifest["notes"].extend(
        [
            "All 126 documented statistic arrays were enumerated from consolidated metadata; only six arrays were sampled.",
            "Object-request usage counts explicit Cloud Storage CLI operations; HTTP requests and implicit SDK retries were not wire-instrumented.",
            "Received-byte usage sums downloaded object bodies; describe-response headers and bodies were not wire-instrumented.",
            "Raw chunks were deleted immediately after point extraction and are not retained.",
        ]
    )
    manifest["local_storage"] = {
        "raw_chunks_retained": False,
        "free_space_reserve_bytes": LOCAL_FREE_SPACE_RESERVE,
        "gate_includes_next_chunk_decoded_working_cap_and_output_cap": True,
    }
    output_bytes, digest = write_validated_manifest(manifest, output)
    print(f"wrote {output} ({output_bytes} bytes, sha256 {digest})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify-existing-identities", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_existing_identities:
            started = time.monotonic()
            manifest = json.loads(args.output.read_text())
            transport = Transport(started + DEADLINE_SECONDS)
            transport.requests = int(manifest["usage"]["object_requests"])
            transport.received_bytes = int(manifest["usage"]["received_bytes"])
            verify_object_identities(transport, manifest["objects"], contract.BUCKET)
            manifest["usage"]["object_requests"] = transport.requests
            manifest["usage"]["deadline_seconds"] += math.ceil(time.monotonic() - started)
            output_bytes, digest = write_validated_manifest(manifest, args.output)
            print(f"verified {len(manifest['objects'])} identities; {output_bytes} bytes, sha256 {digest}")
        else:
            run(args.output)
    except ProbeError as exc:
        print(f"WeatherNext bounded sample failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
