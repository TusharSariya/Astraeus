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

from ingest.contract import AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult, MEDIA_ZARR
from ingest.experimental.native_deterministic import DWDIconNativeCandidate, IndexedNativeCandidate
from weather_api.store import LiveStore

UTC = timezone.utc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20): digest.update(chunk)
    return digest.hexdigest()


def retained_candidate(adapter: object, source_dir: Path) -> RunCandidate | None:
    """Resolve an offline candidate only when all upstream evidence is retained."""
    discovery_path = source_dir / "discovery.json"
    if not discovery_path.is_file():
        return None
    discovery = json.loads(discovery_path.read_text())
    run = datetime.fromisoformat(discovery["run_time"])
    if isinstance(adapter, IndexedNativeCandidate):
        index_path = source_dir / f"{adapter.source_id}.index"
        raw_path = source_dir / f"{adapter.source_id}.grib2"
        if not index_path.is_file() or not raw_path.is_file():
            return None
        index = index_path.read_bytes()
        expected = discovery.get("index_sha256")
        if expected and hashlib.sha256(index).hexdigest() != expected:
            raise AssertionError(f"retained index digest mismatch: {adapter.source_id}")
        return RunCandidate(discovery["provider_run_id"], run, discovery["urls"], {"index": index, "retained_raw": True})
    manifest_path = source_dir / "upstream-objects.json"
    if not manifest_path.is_file():
        return None
    for item in json.loads(manifest_path.read_text())["objects"]:
        path = source_dir / item["path"]
        if not path.is_file() or path.stat().st_size != item["compressed_bytes"] or sha256(path) != item["compressed_sha256"]:
            raise AssertionError(f"retained ICON object mismatch: {item['path']}")
    return RunCandidate(discovery["provider_run_id"], run, discovery["urls"], {"cycle": run.strftime("%H"), "stamp": discovery["provider_run_id"], "retained_raw": True})


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("output", type=Path)
    parser.add_argument("--offline", action="store_true", help="require retained upstream bytes and make no provider requests")
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0); window = FetchWindow(now, back_hours=0, forward_hours=0)
    adapters = [IndexedNativeCandidate("ecmwf-ifs-native"), IndexedNativeCandidate("ecmwf-aifs-single-native"),
                DWDIconNativeCandidate(), IndexedNativeCandidate("noaa-nam-parent-native"), IndexedNativeCandidate("noaa-rap-parent-native")]
    summary: dict[str, object] = {"retrieved_at": datetime.now(UTC).isoformat(), "bounds": [45.0, -58.0, 50.5, -46.0],
                                  "operational": False, "sources": []}
    artifacts = []
    for adapter in adapters:
        source_dir = output / adapter.source_id; source_dir.mkdir(exist_ok=True)
        try:
            candidate = retained_candidate(adapter, source_dir)
            replayed = candidate is not None
            if candidate is None:
                if args.offline:
                    raise AdapterUnavailable(f"offline replay evidence is incomplete for {adapter.source_id}")
                candidate = adapter.discover(window)[0]
                (source_dir / "discovery.json").write_text(json.dumps({"provider_run_id": candidate.provider_run_id, "run_time": candidate.run_time.isoformat() if candidate.run_time else None,
                    "urls": candidate.urls, "index_sha256": hashlib.sha256(candidate.detail.get("index", b"")).hexdigest() if isinstance(candidate.detail.get("index"), bytes) else None}, indent=2, sort_keys=True) + "\n")
            result = adapter.fetch(candidate, window, source_dir)
            artifact = result.artifacts[0]; provenance_path = source_dir / "provenance.json"
            artifact.provenance["sha256"] = sha256(artifact.payload_path)
            provenance_path.write_text(json.dumps(artifact.provenance, indent=2, sort_keys=True) + "\n")
            artifacts.append((artifact, result))
            summary["sources"].append({"source_id": adapter.source_id, "status": "artifact-built", "artifact_bytes": artifact.byte_size,
                "artifact_sha256": sha256(artifact.payload_path), "coverage": artifact.provenance["native_grid_coverage"],
                "retrieved_message_count": len(artifact.provenance["message_inventory"]), "replayed_retained_raw": replayed})
        except AdapterUnavailable as error:
            raw = source_dir / f"{adapter.source_id}.grib2"
            summary["sources"].append({"source_id": adapter.source_id, "status": "excluded", "reason": str(error),
                "retained_raw_bytes": raw.stat().st_size if raw.exists() else 0, "retained_raw_sha256": sha256(raw) if raw.exists() else None,
                "replayed_retained_raw": bool(candidate and candidate.detail.get("retained_raw"))})

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
        payload["raw_only_messages"] = [{"upstream": item["short_name"], "pressure_hpa": item["level"],
            "value_or_null": item["raw_point_value"], "units": item["units"], "step_type": item["step_type"],
            "start_step": item["start_step"], "end_step": item["end_step"]}
            for item in artifact.provenance["message_inventory"] if not item.get("canonical")]
        readbacks[result.source_id] = payload; (output / f"{result.source_id}.api.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    summary["api_readback"] = readbacks
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    for artifact, result in artifacts:
        shutil.rmtree(output / result.source_id / ".reader-cache", ignore_errors=True)


if __name__ == "__main__": main()
