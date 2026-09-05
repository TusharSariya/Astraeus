#!/usr/bin/env python3
"""Bounded live evidence for issue 98's four unregistered point adapters.

Exactly four anonymous requests are made. The retained bundle contains the
small raw JSON responses, immutable Zarr artifacts, provenance, checksums and
per-field coverage. No production registry or publication state is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest.contract import FetchWindow
from ingest.experimental.openmeteo import BrightSkyMosmix71801Adapter, OpenMeteoAdapter
from weather_api.store import LiveStore

UTC = timezone.utc


class Client:
    def get(self, url: str):
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        return response


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    window = FetchWindow(now, back_hours=0, forward_hours=2)
    adapters = [
        OpenMeteoAdapter("openmeteo-jma-gsm", client=Client()),
        OpenMeteoAdapter("openmeteo-arpege", client=Client()),
        OpenMeteoAdapter("openmeteo-ukmo-global", client=Client()),
        BrightSkyMosmix71801Adapter(client=Client()),
    ]
    summary = {"retrieved_at": datetime.now(UTC).isoformat(), "request_count": 4, "window": [window.start.isoformat(), window.end.isoformat()], "sources": []}
    for adapter in adapters:
        candidate = adapter.discover(window)[0]
        raw = output / f"{adapter.source_id}.response.json"
        raw.write_text(json.dumps(candidate.detail["payload"], indent=2, sort_keys=True) + "\n")
        result = adapter.fetch(candidate, window, output)
        artifact = result.artifacts[0]
        provenance = output / f"{adapter.source_id}.provenance.json"
        provenance.write_text(json.dumps(artifact.provenance, indent=2, sort_keys=True) + "\n")
        summary["sources"].append({
            "source_id": adapter.source_id, "complete": result.complete, "qc_passed": result.qc_passed,
            "response_sha256": sha256(raw), "artifact_sha256": sha256(artifact.payload_path),
            "artifact_bytes": artifact.byte_size, "field_disposition": artifact.provenance["field_disposition"],
        })

    # Exercise the production artifact reader over one live-produced artifact.
    artifact_path = output / "openmeteo-jma-gsm.zarr.zip"
    provenance = json.loads((output / "openmeteo-jma-gsm.provenance.json").read_text())
    class S3:
        def head_bucket(self, **_kwargs): return {}
        def download_fileobj(self, _bucket, _key, handle):
            with artifact_path.open("rb") as source: shutil.copyfileobj(source, handle)
    record = SimpleNamespace(revision_id="bounded-live-proof", source_id="openmeteo-jma-gsm", logical_name="surface",
        media_type="application/zarr+zip", object_key="local-proof", byte_size=artifact_path.stat().st_size,
        provenance=provenance, run_time=None, retrieved_at=datetime.now(UTC), native_crs="EPSG:4326")
    class Store:
        s3 = S3(); config = SimpleNamespace(bucket="bounded-live-proof")
        def current_artifacts(self): return [record]
    sample = LiveStore(Store(), output / ".reader-cache").sample_point(47.5615, -52.7126, now)
    summary["numeric_reader_proof"] = [{"variable": item.variable, "value": item.value, "units": item.units} for item in sample]
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
