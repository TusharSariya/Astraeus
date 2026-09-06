#!/usr/bin/env python3
"""Replay issue 98's retained live artifacts through LiveStore and /point.

This makes no provider requests. Each route downloads the exact retained Zarr
bytes through the production reader's checksum gate, then compares every
selected artifact field (including null masks) with the HTTP response.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy
import xarray
import zarr
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import weather_api.store as store_module
from weather_api.app import PREFIX, app
from weather_api.storage import ArtifactRevision, FixtureArtifactStore
from weather_api.store import LiveStore

api_module = importlib.import_module("weather_api.app")


HTTP_FIELD = {
    **store_module.FIELD_BY_VARIABLE,
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "wind_gust_10m": "wind_gust",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value: object) -> float | str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None if value is None else str(value)
    return None if numpy.isnan(number) else number


def replay(bundle: Path) -> dict[str, object]:
    summary_path = bundle / "summary.json"
    summary = json.loads(summary_path.read_text())
    valid_time = datetime.fromisoformat(summary["window"][0])
    products = {
        "openmeteo-jma-gsm": "JMA-GSM-RETAINED",
        "openmeteo-arpege": "ARPEGE-RETAINED",
        "openmeteo-ukmo-global": "UKMO-GLOBAL-RETAINED",
        "brightsky-dwd-mosmix-71801": "MOSMIX-71801-RETAINED",
    }
    source_results: dict[str, object] = {}
    original_live_store = api_module.live_store
    original_products = dict(api_module.PRODUCT_SOURCE_IDS)
    original_fields = dict(store_module.FIELD_BY_VARIABLE)
    original_mode = os.environ.get("WEATHER_DATA_MODE")
    cache = tempfile.TemporaryDirectory(prefix="openmeteo-retained-http-")
    try:
        os.environ["WEATHER_DATA_MODE"] = "live"
        store_module.FIELD_BY_VARIABLE.update({
            "wind_speed_10m": "wind_speed",
            "wind_direction_10m": "wind_direction",
            "wind_gust_10m": "wind_gust",
        })
        api_module.PRODUCT_SOURCE_IDS.update({product: source for source, product in products.items()})
        for source in summary["sources"]:
            source_id = source["source_id"]
            artifact_path = bundle / f"{source_id}.zarr.zip"
            provenance = json.loads((bundle / f"{source_id}.provenance.json").read_text())
            expected_digest = source["artifact_sha256"]
            if digest(artifact_path) != expected_digest or provenance["sha256"] != expected_digest:
                raise AssertionError(f"{source_id}: retained checksum disagrees with summary or provenance")

            with xarray.open_zarr(zarr.storage.ZipStore(artifact_path, mode="r"), consolidated=False) as dataset:
                point = dataset.sel(valid_time=numpy.datetime64(valid_time.replace(tzinfo=None), "ns"))
                latitude = float(point.latitude.values.item())
                longitude = float(point.longitude.values.item())
                expected = {HTTP_FIELD[str(name)]: scalar(point[name].values.item()) for name in point.data_vars}

            class S3:
                def head_bucket(self, **_kwargs): return {}
                def download_fileobj(self, _bucket, _key, handle):
                    with artifact_path.open("rb") as retained: shutil.copyfileobj(retained, handle)

            record = SimpleNamespace(
                revision_id=f"retained-{source_id}", source_id=source_id,
                logical_name="surface", media_type="application/zarr+zip",
                object_key=artifact_path.name, byte_size=artifact_path.stat().st_size,
                provenance=provenance, run_time=None,
                retrieved_at=datetime.fromisoformat(summary["retrieved_at"]), native_crs="EPSG:4326",
            )

            class ArtifactStore:
                s3 = S3()
                config = SimpleNamespace(bucket="retained-live-proof")
                def current_artifacts(self): return [record]
                def source_activity(self): return {source_id: record.retrieved_at}

            live = LiveStore(ArtifactStore(), Path(cache.name) / source_id)
            api_module.live_store = lambda: live
            response = TestClient(app).get(
                f"{PREFIX}/point",
                params={"product": products[source_id], "latitude": latitude,
                        "longitude": longitude, "valid_time": valid_time.isoformat()},
            )
            if response.status_code != 200:
                raise AssertionError(f"{source_id}: HTTP {response.status_code}: {response.text}")
            payload = response.json()
            response_fields = {
                field["field"]: field["value"]
                for field in payload["fields"]
                if field["provenance"]["source_id"] == source_id
            }
            missing = sorted(set(expected) - set(response_fields))
            if missing:
                raise AssertionError(f"{source_id}: HTTP response omitted selected fields {missing}")
            actual = {name: response_fields[name] for name in expected}
            if actual != expected:
                raise AssertionError(f"{source_id}: HTTP fields differ: expected {expected!r}, got {actual!r}")
            source_results[source_id] = {
                "route": f"{PREFIX}/point?product={products[source_id]}",
                "artifact_sha256_verified": expected_digest,
                "complete": source["complete"], "qc_passed": source["qc_passed"],
                "fields": actual,
                "null_fields": sorted(name for name, value in actual.items() if value is None),
            }
    finally:
        api_module.live_store = original_live_store
        api_module.PRODUCT_SOURCE_IDS.clear(); api_module.PRODUCT_SOURCE_IDS.update(original_products)
        store_module.FIELD_BY_VARIABLE.clear(); store_module.FIELD_BY_VARIABLE.update(original_fields)
        if original_mode is None: os.environ.pop("WEATHER_DATA_MODE", None)
        else: os.environ["WEATHER_DATA_MODE"] = original_mode
        cache.cleanup()

    mosmix = next(item for item in summary["sources"] if item["source_id"] == "brightsky-dwd-mosmix-71801")
    publication = FixtureArtifactStore()
    prior = ArtifactRevision("prior-visible", 100, True, True)
    publication.stage("mosmix", prior); publication.publish("mosmix")
    publication.stage("mosmix", ArtifactRevision("retained-all-null-gust", mosmix["artifact_bytes"], mosmix["complete"], mosmix["qc_passed"]))
    try:
        publication.publish("mosmix")
    except ValueError as error:
        publication_gate = {"blocked": True, "reason": str(error), "visible_revision": publication.visible["mosmix"].revision}
    else:
        raise AssertionError("incomplete retained MOSMIX artifact unexpectedly published")

    proof = {
        "provider_request_count": 0, "valid_time": valid_time.isoformat(),
        "publication_gate": publication_gate, "sources": source_results,
    }
    summary["retained_http_readback"] = proof
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return proof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    proof = replay(parser.parse_args().bundle.resolve())
    print(json.dumps(proof, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
