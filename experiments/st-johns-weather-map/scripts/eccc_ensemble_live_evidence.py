#!/usr/bin/env python3
"""Capture bounded ECCC ensemble sources, or replay them entirely offline.

This is an experiment-only evidence harness. It does not register, schedule,
publish, or promote either source. Every HTTP body is streamed under a hard
ceiling and retained beside a receipt before artifact construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "api"))

import numpy
import xarray
import zarr
from fastapi import FastAPI
from fastapi.testclient import TestClient
from weather_api import store as api_store
from weather_api.app import app
from weather_api.store import LiveStore

from ingest.adapters.eccc_geomet import GEOMET_BASE_URL
from ingest.adapters.eccc_geomet_ensemble import (
    MAX_WCS_TIFF_BYTES,
    ECCCREPSEnsembleAdapter,
    coverage_id,
    coverage_url,
    declaration_for,
    decode_reps_geotiff,
    member_identifiers,
    stored_member_coverages,
)
from ingest.adapters.eccc_geomet_reductions import (
    GEPS_SCALESIZE,
    SELECTED_REDUCTIONS,
    fetch_geps_reductions,
)
from ingest.contract import FetchWindow, RunCandidate
from ingest.http import PoliteClient
from ingest.store import CurrentArtifact

RUN_TIME = datetime(2026, 9, 5, 12, tzinfo=UTC)
REPS_VALID_TIME = datetime(2026, 9, 5, 18, tzinfo=UTC)
GEPS_RUN_TIME = datetime(2026, 9, 5, 0, tzinfo=UTC)
GEPS_VALID_TIME = datetime(2026, 9, 5, 12, tzinfo=UTC)
SELECTED_REPS = ("total_cloud_opacity", "wind_speed_10m")
CAPABILITIES_URL = (
    f"{GEOMET_BASE_URL}?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCapabilities"
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_name(coverage: str) -> str:
    return coverage.replace("/", "_") + ".tif"


class RetainedClient:
    def __init__(self, raw: Path, receipt: dict[str, object]) -> None:
        self.raw = raw
        self.by_url = {str(row["source_uri"]): row for row in receipt["responses"]}
        self.retrieved_at = datetime.fromisoformat(str(receipt["captured_at"]))

    def get_bytes(self, url: str, *, max_bytes: int):
        row = self.by_url.get(url)
        if row is None:
            raise FileNotFoundError(f"offline receipt has no response for {url}")
        path = self.raw / str(row["path"])
        payload = path.read_bytes()
        if len(payload) > max_bytes:
            raise ValueError(f"retained {path} exceeds the replay ceiling")
        if len(payload) != row["bytes"] or _sha(payload) != row["sha256"]:
            raise ValueError(f"retained response identity mismatch: {path}")
        headers = dict(row.get("response_headers", {}))
        headers["x-astraeus-original-retrieved-at"] = str(row["retrieved_at"])
        return payload, headers


def capture(output: Path) -> None:
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    responses: list[dict[str, object]] = []
    with PoliteClient(attempts=2, timeout_seconds=45) as client:
        capabilities, headers = client.get_bytes(
            CAPABILITIES_URL, max_bytes=4 * 1024 * 1024
        )
        (raw / "wcs-capabilities.xml").write_bytes(capabilities)
        responses.append(
            _row(
                "inventory",
                CAPABILITIES_URL,
                "wcs-capabilities.xml",
                capabilities,
                headers,
            )
        )
        templates = dict(stored_member_coverages("eccc-reps"))
        for key in SELECTED_REPS:
            for member in member_identifiers(declaration_for("eccc-reps")):
                coverage = coverage_id(templates[key], member)
                url = coverage_url(
                    coverage, valid_time=REPS_VALID_TIME, reference_time=RUN_TIME
                )
                payload, response_headers = client.get_bytes(
                    url, max_bytes=MAX_WCS_TIFF_BYTES
                )
                name = _safe_name(coverage)
                (raw / name).write_bytes(payload)
                responses.append(
                    _row("reps", url, name, payload, response_headers, coverage)
                )
        for reduction in SELECTED_REDUCTIONS:
            url = coverage_url(
                reduction.coverage_id,
                scalesize=GEPS_SCALESIZE,
                valid_time=GEPS_VALID_TIME,
                reference_time=GEPS_RUN_TIME,
            )
            payload, response_headers = client.get_bytes(
                url, max_bytes=MAX_WCS_TIFF_BYTES
            )
            name = _safe_name(reduction.coverage_id)
            (raw / name).write_bytes(payload)
            responses.append(
                _row(
                    "geps", url, name, payload, response_headers, reduction.coverage_id
                )
            )
    receipt = {
        "classification": "test-only retained-source evidence; operational=false",
        "captured_at": datetime.now(UTC).isoformat(),
        "request_count": len(responses),
        "hard_decoded_response_ceiling_bytes": MAX_WCS_TIFF_BYTES,
        "byte_measurement": "decoded HTTP response body bytes retained on disk; not compressed wire bytes",
        "responses": responses,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    _write_accounting(output, capabilities)
    build = output / ".capture-build"
    result = replay(output, build, compare_baseline=False)
    artifacts = output / "artifacts"
    artifacts.mkdir(exist_ok=True)
    for name in ("eccc_reps_members.zarr.zip", "eccc_geps_reductions.zarr.zip"):
        shutil.move(str(build / name), artifacts / name)
    shutil.rmtree(build)
    manifest = {
        "captured_at": receipt["captured_at"],
        "artifacts": {
            name: {
                "bytes": (artifacts / name).stat().st_size,
                "sha256": _sha((artifacts / name).read_bytes()),
            }
            for name in ("eccc_reps_members.zarr.zip", "eccc_geps_reductions.zarr.zip")
        },
        "capture_validation": result,
    }
    (output / "artifact-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )


def _row(kind, url, path, payload, headers, coverage_id=None):
    return {
        "kind": kind,
        "coverage_id": coverage_id,
        "source_uri": url,
        "path": path,
        "decoded_body_bytes": len(payload),
        "bytes": len(payload),
        "sha256": _sha(payload),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "response_headers": {
            key.lower(): value
            for key, value in headers.items()
            if key.lower()
            in {"content-length", "content-type", "date", "etag", "last-modified"}
        },
    }


def _write_accounting(output: Path, capabilities: bytes) -> None:
    root = ET.fromstring(capabilities)
    coverage_ids = [
        element.text
        for element in root.iter()
        if element.tag.endswith("CoverageId") and element.text
    ]
    selected_reps = {
        coverage_id(dict(stored_member_coverages("eccc-reps"))[key], member)
        for key in SELECTED_REPS
        for member in member_identifiers(declaration_for("eccc-reps"))
    }
    selected_geps = {item.coverage_id for item in SELECTED_REDUCTIONS}
    rows = []
    for coverage in coverage_ids:
        if coverage.startswith("REPS."):
            disposition = (
                "selected" if coverage in selected_reps else "deferred_issue_147"
            )
            rows.append(
                {"family": "REPS", "coverage_id": coverage, "disposition": disposition}
            )
        elif coverage.startswith("GEPS."):
            disposition = (
                "selected_producer_reduction"
                if coverage in selected_geps
                else "deferred_issue_148"
            )
            rows.append(
                {"family": "GEPS", "coverage_id": coverage, "disposition": disposition}
            )
    assert sum(row["family"] == "REPS" for row in rows) == 1239
    assert sum(row["family"] == "GEPS" for row in rows) == 532
    assert sum(row["disposition"] == "selected" for row in rows) == 42
    assert sum(row["disposition"] == "selected_producer_reduction" for row in rows) == 5
    document = {
        "source": "raw/wcs-capabilities.xml",
        "rule": "exact selected coverage IDs are selected; other REPS IDs are deferred to issue 147 and other GEPS IDs to issue 148",
        "whole_family_complete": False,
        "rows": rows,
    }
    (output / "inventory-accounting.json").write_text(
        json.dumps(document, indent=2) + "\n"
    )


def replay(
    source: Path, replay_dir: Path, *, compare_baseline: bool = True
) -> dict[str, object]:
    receipt = json.loads((source / "receipt.json").read_text())
    _verify_receipt(source, receipt)
    client = RetainedClient(source / "raw", receipt)
    if replay_dir.exists() and any(replay_dir.iterdir()):
        raise ValueError(f"replay output must be empty: {replay_dir}")
    replay_dir.mkdir(parents=True, exist_ok=True)
    reps = ECCCREPSEnsembleAdapter(client=client).assemble(
        RunCandidate(
            "reps-20260905T12Z-f006",
            RUN_TIME,
            detail={"valid_time": REPS_VALID_TIME},
        ),
        FetchWindow(now=REPS_VALID_TIME),
        replay_dir,
        selected_keys=SELECTED_REPS,
    )
    geps = fetch_geps_reductions(
        valid_time=GEPS_VALID_TIME,
        reference_time=GEPS_RUN_TIME,
        workdir=replay_dir,
        client=client,
    )
    reps_ds = _open(reps.artifacts[0].payload_path)
    geps_ds = _open(geps.payload_path)
    _assert_identity(reps_ds, "eccc-reps", RUN_TIME, REPS_VALID_TIME)
    _assert_identity(geps_ds, "eccc-geps", GEPS_RUN_TIME, GEPS_VALID_TIME)
    assert reps_ds.sizes == {
        "member": 21,
        "valid_time": 1,
        "latitude": 61,
        "longitude": 133,
    }
    assert "member" not in geps_ds.dims and geps_ds.sizes["valid_time"] == 1
    _assert_raw_numeric_parity(source, receipt, reps_ds, geps_ds)
    hashes = {
        "eccc_reps_members.zarr.zip": _sha(reps.artifacts[0].payload_path.read_bytes()),
        "eccc_geps_reductions.zarr.zip": _sha(geps.payload_path.read_bytes()),
    }
    parity = None
    if compare_baseline:
        baseline = _verify_baseline(source)
        parity = all(
            hashes[name] == baseline[name]["sha256"]
            and (replay_dir / name).stat().st_size == baseline[name]["bytes"]
            for name in hashes
        )
        if not parity:
            raise AssertionError(
                "rebuilt artifact bytes do not match the retained baseline"
            )
    numeric_proof = _numeric_proof(reps_ds, geps_ds)
    _http_readback(replay_dir, reps, geps, reps_ds, geps_ds, client.retrieved_at)
    report = {
        "offline_replay_at": datetime.now(UTC).isoformat(),
        "original_capture_retrieved_at": receipt["captured_at"],
        "artifact_sha256": hashes,
        "retained_baseline_parity": parity,
        "numeric_null_proof": numeric_proof,
        "reps_complete": reps.complete,
        "reps_quality": reps.artifacts[0].provenance["quality"],
        "field_accounting": {
            "reps": reps.artifacts[0].provenance["field_accounting"],
            "geps": geps.provenance["field_accounting"],
        },
        "core_reader_and_test_http_readback": "passed",
    }
    (replay_dir / "offline-replay.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _verify_baseline(source: Path) -> dict[str, dict[str, object]]:
    baseline = json.loads((source / "artifact-manifest.json").read_text())["artifacts"]
    for name, expected in baseline.items():
        path = source / "artifacts" / name
        payload = path.read_bytes()
        if len(payload) != expected["bytes"] or _sha(payload) != expected["sha256"]:
            raise ValueError(f"retained baseline identity mismatch: {name}")
    return baseline


def _numeric_proof(reps_ds, geps_ds):
    proof = {}
    for family, dataset in (("reps", reps_ds), ("geps", geps_ds)):
        proof[family] = {}
        for variable in dataset.data_vars:
            values = numpy.asarray(dataset[variable].values)
            proof[family][str(variable)] = {
                "numeric": int(numpy.count_nonzero(numpy.isfinite(values))),
                "null": int(numpy.count_nonzero(numpy.isnan(values))),
            }
    assert all(row["numeric"] > 0 for family in proof.values() for row in family.values())
    return proof


def _verify_receipt(source: Path, receipt: dict[str, object]) -> None:
    responses = receipt.get("responses")
    if not isinstance(responses, list) or len(responses) != receipt.get(
        "request_count"
    ):
        raise ValueError("receipt response count is inconsistent")
    paths: set[str] = set()
    for row in responses:
        path_name = str(row["path"])
        if path_name in paths:
            raise ValueError(f"duplicate retained response path: {path_name}")
        paths.add(path_name)
        payload = (source / "raw" / path_name).read_bytes()
        if len(payload) != row["bytes"] or _sha(payload) != row["sha256"]:
            raise ValueError(f"receipt identity mismatch: {path_name}")
    if "wcs-capabilities.xml" not in paths:
        raise ValueError("receipt omits the retained WCS capability inventory")


def _open(path: Path):
    return xarray.open_zarr(
        zarr.storage.ZipStore(str(path), mode="r"), consolidated=False
    )


def _assert_identity(dataset, source_id, run_time, valid_time):
    assert dataset.attrs["source_id"] == source_id
    assert dataset.attrs["run_time"] == run_time.isoformat()
    assert dataset.attrs["valid_time"] == valid_time.isoformat()
    actual = dataset.valid_time.values.astype("datetime64[ns]")
    expected = __import__("numpy").datetime64(valid_time.replace(tzinfo=None), "ns")
    assert actual.shape == (1,) and bool((actual == expected).all())


def _assert_raw_numeric_parity(source, receipt, reps_ds, geps_ds):
    templates = dict(stored_member_coverages("eccc-reps"))
    reps_lookup = {
        coverage_id(template, member): (key, member)
        for key, template in templates.items()
        if key in SELECTED_REPS
        for member in member_identifiers(declaration_for("eccc-reps"))
    }
    geps_lookup = {item.coverage_id: item.variable for item in SELECTED_REDUCTIONS}
    checked = 0
    for row in receipt["responses"]:
        coverage = row.get("coverage_id")
        if not coverage:
            continue
        payload = (source / "raw" / row["path"]).read_bytes()
        if coverage in reps_lookup:
            key, member = reps_lookup[coverage]
            raw = decode_reps_geotiff(
                payload,
                coverage=coverage,
                variable=key,
                valid_time=REPS_VALID_TIME,
                bounds={"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0},
            )
            stored = reps_ds[key].sel(member=member)
        else:
            variable = geps_lookup[coverage]
            raw = decode_reps_geotiff(
                payload,
                coverage=coverage,
                variable=variable,
                valid_time=GEPS_VALID_TIME,
                bounds={"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0},
                width=24,
                height=11,
            )
            stored = geps_ds[variable]
        assert numpy.array_equal(raw.values, stored.values, equal_nan=True)
        checked += 1
    assert checked == 47


def _http_readback(cache_dir, reps, geps, reps_ds, geps_ds, retrieved_at):
    currents = [
        CurrentArtifact(
            source_id="eccc-reps",
            logical_name="members",
            revision_id="offline-reps",
            object_key=str(reps.artifacts[0].payload_path),
            media_type="application/zarr+zip",
            byte_size=reps.artifacts[0].payload_path.stat().st_size,
            provenance=reps.artifacts[0].provenance,
            published_at=REPS_VALID_TIME,
            run_time=RUN_TIME,
            retrieved_at=retrieved_at,
            provider_run_id=reps.provider_run_id,
            native_crs="EPSG:4326",
        ),
        CurrentArtifact(
            source_id="eccc-geps",
            logical_name="reductions",
            revision_id="offline-geps",
            object_key=str(geps.payload_path),
            media_type="application/zarr+zip",
            byte_size=geps.payload_path.stat().st_size,
            provenance=geps.provenance,
            published_at=GEPS_VALID_TIME,
            run_time=GEPS_RUN_TIME,
            retrieved_at=retrieved_at,
            provider_run_id="geps-20260905T00Z-f012",
            native_crs="EPSG:4326",
        ),
    ]

    class Harness(LiveStore):
        def __init__(self):
            super().__init__(artifact_store=None, cache_dir=cache_dir)

        def current(self):
            return currents

        def open(self, artifact):
            return reps_ds if artifact.source_id == "eccc-reps" else geps_ds

        def assert_object_store_reachable(self):
            return None

    harness = Harness()
    original_manifest = api_store.artifact_manifest
    original_live_store = sys.modules["weather_api.app"].live_store
    original_mode = __import__("os").environ.get("WEATHER_DATA_MODE")
    original_wind_mapping = api_store.FIELD_BY_VARIABLE.get("wind_speed_10m")
    original_geps_mappings = {
        item.variable: api_store.FIELD_BY_VARIABLE.get(item.variable)
        for item in SELECTED_REDUCTIONS
    }
    try:
        api_store.artifact_manifest = lambda artifact: SimpleNamespace(
            class_for=lambda name: "retrieved", evidence_classes=("retrieved",)
        )
        api_store.FIELD_BY_VARIABLE["wind_speed_10m"] = "wind_speed_10m"
        api_store.FIELD_BY_VARIABLE.update(
            {item.variable: item.variable for item in SELECTED_REDUCTIONS}
        )
        sys.modules["weather_api.app"].live_store = lambda: harness
        __import__("os").environ["WEATHER_DATA_MODE"] = "live"
        response = TestClient(app).get(
            "/api/experiments/weather/v0/point",
            params={
                "latitude": 47.56,
                "longitude": -52.71,
                "valid_time": REPS_VALID_TIME.isoformat(),
                "member": "01",
            },
        )
        assert response.status_code == 200 and response.json()["operational"] is False
        reps_fields = {
            item["field"]: item
            for item in response.json()["fields"]
            if item["provenance"]["source_id"] == "eccc-reps"
        }
        expected_reps = reps_ds.sel(member="01").sel(
            valid_time=numpy.datetime64(REPS_VALID_TIME.replace(tzinfo=None), "ns"),
            latitude=47.56,
            longitude=-52.71,
            method="nearest",
        )
        assert set(reps_fields) == set(SELECTED_REPS)
        for variable in SELECTED_REPS:
            expected = float(expected_reps[variable])
            assert abs(float(reps_fields[variable]["value"]) - expected) <= 1e-6 * max(
                1.0, abs(expected)
            )
        wrong_member = harness.sample_point(
            47.56, -52.71, REPS_VALID_TIME, member="99"
        )
        assert not any(sample.source_id == "eccc-reps" for sample in wrong_member)
        geps_harness = FastAPI()

        @geps_harness.get("/test-only/geps")
        def geps_point(
            latitude: float,
            longitude: float,
            valid_time: datetime,
            member: str | None = None,
        ):
            if member is not None:
                return {"fields": []}
            samples = harness._sample_dataset(
                harness.open(currents[1]),
                currents[1],
                latitude,
                longitude,
                valid_time,
                manifest=SimpleNamespace(
                    class_for=lambda name: "retrieved",
                    evidence_classes=("retrieved",),
                ),
            )
            return {
                "operational": False,
                "fields": [
                    {
                        "field": sample.variable,
                        "value": sample.value,
                        "source_id": sample.source_id,
                    }
                    for sample in samples
                ],
            }

        geps_response = TestClient(geps_harness).get(
            "/test-only/geps",
            params={
                "latitude": 47.56,
                "longitude": -52.71,
                "valid_time": GEPS_VALID_TIME.isoformat(),
            },
        )
        assert geps_response.status_code == 200
        geps_fields = {
            item["field"]: item
            for item in geps_response.json()["fields"]
            if item["source_id"] == "eccc-geps"
        }
        expected_geps = geps_ds.sel(
            valid_time=numpy.datetime64(GEPS_VALID_TIME.replace(tzinfo=None), "ns"),
            latitude=47.56,
            longitude=-52.71,
            method="nearest",
        )
        assert set(geps_fields) == {item.variable for item in SELECTED_REDUCTIONS}
        for variable in geps_fields:
            expected = float(expected_geps[variable])
            assert abs(float(geps_fields[variable]["value"]) - expected) <= 1e-6 * max(
                1.0, abs(expected)
            )
        wrong_time = TestClient(geps_harness).get(
            "/test-only/geps",
            params={
                "latitude": 47.56,
                "longitude": -52.71,
                "valid_time": "2026-09-05T15:00:00Z",
            },
        )
        assert wrong_time.json()["fields"] == []
        wrong_geps_member = TestClient(geps_harness).get(
            "/test-only/geps",
            params={
                "latitude": 47.56,
                "longitude": -52.71,
                "valid_time": GEPS_VALID_TIME.isoformat(),
                "member": "01",
            },
        )
        assert wrong_geps_member.json()["fields"] == []
    finally:
        api_store.artifact_manifest = original_manifest
        if original_wind_mapping is None:
            api_store.FIELD_BY_VARIABLE.pop("wind_speed_10m", None)
        else:
            api_store.FIELD_BY_VARIABLE["wind_speed_10m"] = original_wind_mapping
        for variable, mapping in original_geps_mappings.items():
            if mapping is None:
                api_store.FIELD_BY_VARIABLE.pop(variable, None)
            else:
                api_store.FIELD_BY_VARIABLE[variable] = mapping
        sys.modules["weather_api.app"].live_store = original_live_store
        if original_mode is None:
            __import__("os").environ.pop("WEATHER_DATA_MODE", None)
        else:
            __import__("os").environ["WEATHER_DATA_MODE"] = original_mode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--offline", type=Path, metavar="RETAINED_SOURCE")
    parser.add_argument("--replay-output", type=Path)
    args = parser.parse_args()
    if args.offline is not None:
        if args.replay_output is None:
            parser.error("--offline requires --replay-output")
        source = args.offline.resolve()
        destination = args.replay_output.resolve()
        if source == destination or source in destination.parents:
            parser.error(
                "replay output must be outside the immutable retained-source directory"
            )
        destination.mkdir(parents=True, exist_ok=True)
        replay(source, destination)
    else:
        if args.output is None:
            parser.error("capture requires --output")
        if args.output.exists() and any(args.output.iterdir()):
            parser.error("capture output must be empty")
        args.output.mkdir(parents=True, exist_ok=True)
        capture(args.output)


if __name__ == "__main__":
    main()
