#!/usr/bin/env python3
"""Build bounded, retained issue-81 evidence from anonymous native feeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest.contract import AdapterUnavailable, Artifact, FetchWindow, RunResult, MEDIA_ZARR
from ingest.experimental.native_deterministic import DWDIconNativeCandidate, IndexedNativeCandidate
from weather_api.store import LiveStore

UTC = timezone.utc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20): digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("output", type=Path); args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0); window = FetchWindow(now, back_hours=0, forward_hours=0)
    adapters = [IndexedNativeCandidate("ecmwf-ifs-native"), IndexedNativeCandidate("ecmwf-aifs-single-native"),
                DWDIconNativeCandidate(), IndexedNativeCandidate("noaa-nam-parent-native"), IndexedNativeCandidate("noaa-rap-parent-native")]
    summary: dict[str, object] = {"retrieved_at": datetime.now(UTC).isoformat(), "bounds": [45.0, -58.0, 50.5, -46.0],
                                  "operational": False, "sources": []}
    artifacts = []
    for adapter in adapters:
        source_dir = output / adapter.source_id; source_dir.mkdir(exist_ok=True)
        retained_artifact = source_dir / f"{adapter.source_id}.zarr.zip"; retained_provenance = source_dir / "provenance.json"
        if retained_artifact.exists() and retained_provenance.exists():
            provenance = json.loads(retained_provenance.read_text()); provenance["evidence_classes"] = ["retrieved"]
            provenance["evidence_class_by_variable"] = {item["canonical"]: "retrieved" for item in provenance["message_inventory"] if item.get("canonical")}
            provenance["sha256"] = sha256(retained_artifact)
            retained_provenance.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
            run = datetime.fromisoformat(provenance["run_time"]); artifact = Artifact("native-deterministic", MEDIA_ZARR, retained_artifact, provenance)
            result = RunResult(adapter.source_id, provenance["provider_run_id"], run, datetime.fromisoformat(provenance["retrieved_at"]), True, True, [artifact], native_crs="native producer grid")
            artifacts.append((artifact, result)); summary["sources"].append({"source_id": adapter.source_id, "status": "artifact-built",
                "artifact_bytes": artifact.byte_size, "artifact_sha256": sha256(artifact.payload_path), "coverage": provenance["native_grid_coverage"],
                "retrieved_message_count": len(provenance["message_inventory"]), "replayed_retained": True})
            continue
        try:
            candidate = adapter.discover(window); candidate = candidate[0]
            (source_dir / "discovery.json").write_text(json.dumps({"provider_run_id": candidate.provider_run_id, "run_time": candidate.run_time.isoformat() if candidate.run_time else None,
                "urls": candidate.urls, "index_sha256": hashlib.sha256(candidate.detail.get("index", b"")).hexdigest() if isinstance(candidate.detail.get("index"), bytes) else None}, indent=2, sort_keys=True) + "\n")
            result = adapter.fetch(candidate, window, source_dir)
            artifact = result.artifacts[0]; provenance_path = source_dir / "provenance.json"
            artifact.provenance["sha256"] = sha256(artifact.payload_path)
            provenance_path.write_text(json.dumps(artifact.provenance, indent=2, sort_keys=True) + "\n")
            artifacts.append((artifact, result))
            summary["sources"].append({"source_id": adapter.source_id, "status": "artifact-built", "artifact_bytes": artifact.byte_size,
                "artifact_sha256": sha256(artifact.payload_path), "coverage": artifact.provenance["native_grid_coverage"],
                "retrieved_message_count": len(artifact.provenance["message_inventory"])})
        except AdapterUnavailable as error:
            raw = source_dir / f"{adapter.source_id}.grib2"
            summary["sources"].append({"source_id": adapter.source_id, "status": "excluded", "reason": str(error),
                "retained_raw_bytes": raw.stat().st_size if raw.exists() else 0, "retained_raw_sha256": sha256(raw) if raw.exists() else None})

    api = FastAPI()
    readbacks = {}
    for artifact, result in artifacts:
        path = artifact.payload_path; provenance = artifact.provenance
        class S3:
            def head_bucket(self, **_kwargs): return {}
            def download_fileobj(self, _bucket, _key, handle, source=path):
                with source.open("rb") as stream: shutil.copyfileobj(stream, handle)
        record = SimpleNamespace(revision_id=f"issue-81-bounded-live-proof-{result.source_id}", source_id=result.source_id, logical_name=artifact.logical_name,
            media_type=artifact.media_type, object_key="retained-local-proof", byte_size=artifact.byte_size, sha256=sha256(path),
            provenance=provenance, run_time=result.run_time, retrieved_at=result.retrieved_at, native_crs=result.native_crs)
        class Store:
            s3 = S3(); config = SimpleNamespace(bucket="issue-81-bounded-live-proof")
            def current_artifacts(self, retained=record): return [retained]
        live = LiveStore(Store(), output / result.source_id / ".reader-cache")
        @api.get(f"/evidence/{result.source_id}")
        def endpoint(latitude: float = 47.5615, longitude: float = -52.7126, pressure: int | None = None,
                     source_id=result.source_id, store=live, valid=result.run_time):
            values = store.sample_point(latitude, longitude, valid) if pressure is None else store.sample_profile(latitude, longitude, valid, [pressure]).get(pressure, [])
            return {"source_id": source_id, "operational": False, "values": [{"variable": item.variable, "value": item.value, "units": item.units,
                "level": item.level, "sample_method": item.sample_method, "sampled_latitude": item.sampled_latitude, "sampled_longitude": item.sampled_longitude} for item in values]}
    client = TestClient(api)
    for artifact, result in artifacts:
        surface = client.get(f"/evidence/{result.source_id}"); surface.raise_for_status()
        east = client.get(f"/evidence/{result.source_id}?latitude=47.5&longitude=-46"); east.raise_for_status()
        levels = sorted({int(item["level"]) for item in artifact.provenance["message_inventory"] if item.get("canonical") and item.get("level") is not None})
        profiles = {}
        for level in levels:
            profile = client.get(f"/evidence/{result.source_id}?pressure={level}"); profile.raise_for_status(); profiles[str(level)] = profile.json()
        payload = {"surface": surface.json(), "profiles_hpa": profiles, "east_edge": east.json()}
        compared = []
        for message in artifact.provenance["message_inventory"]:
            canonical = message.get("canonical")
            if not canonical: continue
            level = message.get("level"); response_values = (profiles.get(str(level), {}).get("values", []) if level is not None else
                (next(iter(profiles.values()))["values"] if profiles else surface.json()["values"]))
            actual = next((item for item in response_values if item["variable"] == canonical), None)
            if actual is None: raise AssertionError(f"HTTP readback omitted {result.source_id} {canonical} {level}")
            expected = message["raw_point_value"]
            equal = (actual["value"] is None and expected is None) or (actual["value"] is not None and expected is not None and math.isclose(actual["value"], expected, rel_tol=0, abs_tol=1e-6))
            if not equal or actual["units"] != message["units"]: raise AssertionError(f"HTTP/raw mismatch {result.source_id} {canonical} {level}")
            compared.append({"variable": canonical, "pressure_hpa": level, "value_or_null_matches": True, "units_match": True,
                "cell_matches": math.isclose(actual["sampled_latitude"], message["raw_point_latitude"], abs_tol=1e-6) and math.isclose(actual["sampled_longitude"], message["raw_point_longitude"], abs_tol=1e-6)})
        if not all(item["cell_matches"] for item in compared): raise AssertionError(f"HTTP/raw cell mismatch: {result.source_id}")
        payload["raw_artifact_http_comparison"] = compared
        readbacks[result.source_id] = payload; (output / f"{result.source_id}.api.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    summary["api_readback"] = readbacks
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__": main()
