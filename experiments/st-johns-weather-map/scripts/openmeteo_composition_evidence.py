"""Capture bounded issue-100 provider/artifact/API evidence outside Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from ingest.contract import FetchWindow
from ingest.experimental.openmeteo import COMPOSITION_FIELDS, RADIATION_FIELDS, OpenMeteoCompositionAdapter
from ingest.http import PoliteClient
from weather_api.app import PREFIX, app
from weather_api.store import LiveStore

UTC = timezone.utc


class RecordingClient:
    def __init__(self) -> None:
        self.client = PoliteClient(attempts=1)
        self.responses: list[tuple[str, bytes, str | None, datetime]] = []

    def get(self, url: str):
        response = self.client.get(url)
        self.responses.append((url, response.content, response.headers.get("content-type"), datetime.now(UTC)))
        return response

    def download(self, url: str, destination: Path, *, max_bytes: int):
        size = self.client.download(url, destination, max_bytes=max_bytes)
        body = destination.read_bytes()
        self.responses.append((url, body, "application/json", datetime.now(UTC)))
        return size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC)
    sources: dict[str, object] = {}
    for source_id in ("openmeteo-cams-aod", "openmeteo-air-quality-particulates", "openmeteo-lsa-saf-radiation"):
        window = (FetchWindow(captured_at, back_hours=24, forward_hours=0) if source_id.endswith("radiation")
                  else FetchWindow(captured_at.replace(minute=0, second=0, microsecond=0), back_hours=0, forward_hours=23))
        recorder = RecordingClient()
        adapter = OpenMeteoCompositionAdapter(source_id, client=recorder)
        candidate = adapter.discover(window)[0]
        with tempfile.TemporaryDirectory() as work:
            result = adapter.fetch(candidate, window, Path(work))
            artifact = result.artifacts[0]
            artifact_path = args.output_dir / f"{source_id}.zarr.zip"
            shutil.copy2(artifact.payload_path, artifact_path)
            response_receipts = []
            for index, (url, body, content_type, retrieved_at) in enumerate(recorder.responses):
                response_path = args.output_dir / f"{source_id}.response-{index}.json"
                response_path.write_bytes(body)
                response_receipts.append({
                    "url": urlsplit(url)._replace(query="").geturl(), "parameters": parse_qs(urlsplit(url).query),
                    "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "content_type": content_type,
                    "retrieved_at": retrieved_at.isoformat(),
                })
            record = SimpleNamespace(
                revision_id=f"{source_id}-{artifact.provenance['sha256'][:16]}", source_id=source_id,
                logical_name=artifact.logical_name, media_type=artifact.media_type, object_key=artifact_path.name,
                byte_size=artifact.byte_size, provenance=artifact.provenance, run_time=result.run_time,
                retrieved_at=result.retrieved_at, native_crs=result.native_crs,
            )

            class S3:
                def head_bucket(self, **_kwargs): return {}
                def download_fileobj(self, _bucket, _key, handle):
                    with artifact_path.open("rb") as source: shutil.copyfileobj(source, handle)

            class Store:
                s3 = S3(); config = SimpleNamespace(bucket="issue-100-live-proof")
                def current_artifacts(self): return [record]
                def source_activity(self): return {source_id: record.retrieved_at}

            payload = candidate.detail["payload"]
            required_upstream = (tuple(RADIATION_FIELDS) if source_id.endswith("radiation") else
                                 (("aerosol_optical_depth",) if source_id.endswith("aod") else tuple(COMPOSITION_FIELDS)))
            choices = [datetime.fromisoformat(stamp).replace(tzinfo=UTC) for stamp in payload["hourly"]["time"]]
            readable_time = next(stamp for index, stamp in reversed(list(enumerate(choices)))
                                 if window.covers(stamp) and all(payload["hourly"][name][index] is not None for name in required_upstream))
            first_time = readable_time.isoformat()
            api_module = sys.modules["weather_api.app"]
            product = {"openmeteo-cams-aod": "ISSUE100-AOD", "openmeteo-air-quality-particulates": "ISSUE100-AQ",
                       "openmeteo-lsa-saf-radiation": "ISSUE100-RADIATION"}[source_id]
            prior_mode, prior_store = os.environ.get("WEATHER_DATA_MODE"), api_module.live_store
            api_module.PRODUCT_SOURCE_IDS[product] = source_id
            try:
                os.environ["WEATHER_DATA_MODE"] = "live"
                with tempfile.TemporaryDirectory() as cache:
                    api_module.live_store = lambda: LiveStore(Store(), Path(cache))
                    response = TestClient(app).get(f"{PREFIX}/point", params={"product": product, "valid_time": first_time,
                                                                              "latitude": "47.5615", "longitude": "-52.7126"})
            finally:
                api_module.live_store = prior_store; api_module.PRODUCT_SOURCE_IDS.pop(product, None)
                if prior_mode is None: os.environ.pop("WEATHER_DATA_MODE", None)
                else: os.environ["WEATHER_DATA_MODE"] = prior_mode
            response.raise_for_status()
            api_payload = response.json()
            (args.output_dir / f"{source_id}.point-api.json").write_text(json.dumps(api_payload, indent=2, sort_keys=True) + "\n")
            own_fields = [item for item in api_payload["fields"] if item["provenance"]["source_id"] == source_id]
            expected_fields = ({"aerosol_optical_depth": COMPOSITION_FIELDS["aerosol_optical_depth"]} if source_id.endswith("aod")
                               else (RADIATION_FIELDS if source_id.endswith("radiation") else COMPOSITION_FIELDS))
            provider_index = [datetime.fromisoformat(stamp).replace(tzinfo=UTC) for stamp in payload["hourly"]["time"]].index(readable_time)
            actual = {item["field"]: item for item in own_fields}
            if set(actual) != {details[0] for details in expected_fields.values()}:
                raise AssertionError(f"{source_id}: API field inventory differs from selected provider fields")
            comparisons = 0
            for upstream_name, details in expected_fields.items():
                canonical, normalized_units = details[0], details[1]
                scale = details[3] if len(details) == 4 else 1.0
                field = actual[canonical]; expected = payload["hourly"][upstream_name][provider_index]
                if expected is None or field["value"] is None or abs(field["value"] - expected * scale) > max(1e-12, abs(expected * scale) * 1e-9):
                    raise AssertionError(f"{source_id}/{canonical}: API value differs from retained provider response")
                provenance = field["provenance"]
                assert provenance["normalized_units"] == normalized_units
                assert datetime.fromisoformat(provenance["valid_time"].replace("Z", "+00:00")) == readable_time
                assert provenance["source_id"] == source_id and provenance["artifact_revision"] == record.revision_id
                comparisons += 1
            sources[source_id] = {
                "receipts": response_receipts, "capture_time": result.retrieved_at.isoformat(),
                "artifact_revision": record.revision_id, "artifact_bytes": artifact.byte_size,
                "artifact_sha256": artifact.provenance["sha256"], "complete": result.complete,
                "qc_passed": result.qc_passed, "run_time": result.run_time.isoformat() if result.run_time else None,
                "field_disposition": artifact.provenance["field_disposition"],
                "api_status": response.status_code, "api_operational": api_payload["operational"],
                "api_data_mode": api_payload["data_mode"], "api_source_field_count": len(own_fields),
                "api_provider_value_unit_time_source_revision_comparisons": comparisons,
                "api_values": {item["field"]: item["value"] for item in own_fields},
            }
    summary = {"captured_at": captured_at.isoformat(), "provider_request_count": sum(len(v["receipts"]) for v in sources.values()), "sources": sources}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
