#!/usr/bin/env python3
"""Run the bounded live issue-118 capture and print its review receipt."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ingest.contract import FetchWindow
from ingest.experimental.nl_air_quality import NLAirQualityAdapter
from weather_api.app import PREFIX, PRODUCT_SOURCE_IDS, app
from weather_api.store import LiveStore

UTC = timezone.utc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--provider-file", type=Path, help="Retained result of the documented bounded curl capture")
    parser.add_argument("--captured-at", help="UTC HTTP completion time for --provider-file")
    args = parser.parse_args()
    if bool(args.provider_file) != bool(args.captured_at):
        parser.error("--provider-file and --captured-at must be supplied together")
    args.scratch.mkdir(parents=True, exist_ok=True)
    os.environ["WEATHER_DATA_MODE"] = "live"
    captured = datetime.now(UTC)
    window = FetchWindow(captured, back_hours=24, forward_hours=0)
    if args.provider_file:
        class FileClient:
            def download(self, _url, path, *, max_bytes):
                body = args.provider_file.read_bytes()
                if len(body) > max_bytes:
                    raise ValueError(f"retained response exceeds {max_bytes} bytes")
                path.write_bytes(body)
        adapter = NLAirQualityAdapter(client=FileClient())
    else:
        adapter = NLAirQualityAdapter()
    candidate = adapter.discover(window)[0]
    if args.captured_at:
        replay_capture = datetime.fromisoformat(args.captured_at.replace("Z", "+00:00"))
        if replay_capture.tzinfo is None:
            parser.error("--captured-at must include a UTC offset")
        candidate.detail["captured_at"] = replay_capture.astimezone(UTC)
    result = adapter.fetch(candidate, window, args.scratch)
    artifact = result.artifacts[0]

    class S3:
        def head_bucket(self, **_kwargs): return {}
        def download_fileobj(self, _bucket, _key, handle):
            with artifact.payload_path.open("rb") as source:
                shutil.copyfileobj(source, handle)

    record = SimpleNamespace(
        revision_id=artifact.provenance["sha256"][:24], source_id=adapter.source_id,
        logical_name="air_quality", media_type=artifact.media_type, object_key="scratch/nl-aq.zip",
        byte_size=artifact.byte_size, provenance=artifact.provenance, run_time=None,
        retrieved_at=result.retrieved_at, provider_run_id=result.provider_run_id, native_crs=result.native_crs,
    )

    class Store:
        s3 = S3()
        config = SimpleNamespace(bucket="scratch")
        def current_artifacts(self): return [record]
        def source_activity(self): return {record.source_id: record.retrieved_at}

    store = LiveStore(Store(), args.scratch / "cache")
    sys.modules["weather_api.app"].live_store = lambda: store
    PRODUCT_SOURCE_IDS["NL-AQ-LIVE-PROOF"] = adapter.source_id
    last_valid = artifact.provenance["valid_times"][-1]
    response = TestClient(app).get(f"{PREFIX}/point", params={"product": "NL-AQ-LIVE-PROOF", "valid_time": last_valid})
    response.raise_for_status()
    body = response.json()
    wanted = {"pm2_5_surface_24h_mean", "ozone_surface_mole_fraction"}
    fields = {item["field"]: item for item in body["fields"] if item["field"] in wanted}
    if set(fields) != wanted or body["data_mode"] != "live" or body["operational"] is not False:
        raise SystemExit("HTTP readback did not return both live non-operational fields")
    print(json.dumps({
        "capture_time_utc": result.retrieved_at.isoformat(),
        "request_url": candidate.urls[0], "request_parameters": {},
        "provider_bytes": candidate.detail["byte_count"], "provider_sha256": candidate.detail["sha256"],
        "provider_run_id": result.provider_run_id, "selected_rows": len(artifact.provenance["valid_times"]),
        "first_valid_utc": artifact.provenance["valid_times"][0], "last_valid_utc": last_valid,
        "artifact_revision": record.revision_id, "artifact_bytes": artifact.byte_size,
        "artifact_sha256": artifact.provenance["sha256"], "http_status": response.status_code,
        "api_data_mode": body["data_mode"], "api_operational": body["operational"],
        "api_fields": {name: {"value": item["value"], "provenance": item["provenance"]} for name, item in fields.items()},
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
