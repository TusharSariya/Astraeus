"""Retain and replay the three bounded issue-98 pressure-profile responses."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from ingest.contract import FetchWindow, RunCandidate
from ingest.experimental.openmeteo import MODEL_SOURCES, OPEN_METEO_PROFILE_FIELDS, OPEN_METEO_PROFILE_LEVELS, OpenMeteoAdapter
from weather_api.app import PREFIX, app
from weather_api.store import LiveStore

UTC = timezone.utc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("response_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"captured_at": datetime.now(UTC).isoformat(), "sources": {}}

    for source_id, (model, _producer, _product) in MODEL_SOURCES.items():
        response_path = args.response_dir / f"{source_id}-profile.json"
        body = response_path.read_bytes()
        payload = json.loads(body)
        first = datetime.fromisoformat(payload["hourly"]["time"][0]).replace(tzinfo=UTC)
        window = FetchWindow(first, back_hours=0, forward_hours=0)
        fields = [f"{kind}_{level}hPa" for level in OPEN_METEO_PROFILE_LEVELS[source_id] for kind in OPEN_METEO_PROFILE_FIELDS]
        url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
            "latitude": "47.5615", "longitude": "-52.7126", "models": model,
            "hourly": ",".join(fields), "timezone": "GMT", "elevation": "nan",
            "cell_selection": "nearest", "wind_speed_unit": "ms", "forecast_hours": "1",
        })
        candidate = RunCandidate(
            f"rolling-unknown-{hashlib.sha256(body).hexdigest()[:16]}", None, [url],
            {"payload": payload, "sha256": hashlib.sha256(body).hexdigest(), "model_selector": model, "profile_only": True},
        )
        with tempfile.TemporaryDirectory() as work:
            result = OpenMeteoAdapter(source_id).fetch(candidate, window, Path(work))
            profile = next(item for item in result.artifacts if item.logical_name == "pressure-profile")
            retained_response = args.output_dir / f"{source_id}.response.json"
            retained_artifact = args.output_dir / f"{source_id}.zarr.zip"
            retained_provenance = args.output_dir / f"{source_id}.provenance.json"
            shutil.copy2(response_path, retained_response)
            shutil.copy2(profile.payload_path, retained_artifact)
            retained_provenance.write_text(json.dumps(profile.provenance, indent=2, sort_keys=True) + "\n")

            record = SimpleNamespace(
                revision_id=f"{source_id}-bounded-profile", source_id=source_id,
                logical_name="pressure-profile", media_type=profile.media_type,
                object_key=retained_artifact.name, byte_size=profile.byte_size,
                provenance=profile.provenance, run_time=None, retrieved_at=datetime.now(UTC),
                native_crs="EPSG:4326",
            )

            class S3:
                def head_bucket(self, **_kwargs): return {}
                def download_fileobj(self, _bucket, _key, handle):
                    with retained_artifact.open("rb") as source: shutil.copyfileobj(source, handle)

            class Store:
                s3 = S3()
                config = SimpleNamespace(bucket="retained-profile-proof")
                def current_artifacts(self): return [record]
                def source_activity(self): return {source_id: record.retrieved_at}

            with tempfile.TemporaryDirectory() as cache:
                api_module = sys.modules["weather_api.app"]
                prior_mode, prior_store = os.environ.get("WEATHER_DATA_MODE"), api_module.live_store
                try:
                    os.environ["WEATHER_DATA_MODE"] = "live"
                    api_module.live_store = lambda: LiveStore(Store(), Path(cache))
                    response = TestClient(app).get(f"{PREFIX}/profile", params={
                        "latitude": payload["latitude"], "longitude": payload["longitude"],
                        "valid_time": first.isoformat(),
                    })
                finally:
                    api_module.live_store = prior_store
                    if prior_mode is None: os.environ.pop("WEATHER_DATA_MODE", None)
                    else: os.environ["WEATHER_DATA_MODE"] = prior_mode
            response.raise_for_status()
            api_payload = response.json()
            (args.output_dir / f"{source_id}.profile-api.json").write_text(json.dumps(api_payload, indent=2, sort_keys=True) + "\n")
            summary["sources"][source_id] = {
                "http_status": 200, "response_sha256": hashlib.sha256(body).hexdigest(),
                "artifact_sha256": profile.provenance["sha256"], "artifact_complete": result.complete,
                "api_status": response.status_code, "api_levels": [item["pressure_hpa"] for item in api_payload["levels"]],
                "field_disposition": profile.provenance["field_disposition"],
            }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
