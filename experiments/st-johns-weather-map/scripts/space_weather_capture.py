#!/usr/bin/env python3
"""Capture one live space-weather feed once and write only its receipt.

Completion evidence for the space-weather sources is a live capture plus a
receipt: URL, request parameters, byte count, SHA-256, capture instant, the
provider's ``Last-Modified``, the artifact's byte size and SHA-256, the
record count, the newest instant and the platform labels seen. The payload
itself is never evidence and never leaves the temporary directory this
script creates and deletes.

Usage (from ``experiments/st-johns-weather-map/api``)::

    PYTHONPATH=.. uv run python ../scripts/space_weather_capture.py noaa-goes-xray
    PYTHONPATH=.. uv run python ../scripts/space_weather_capture.py --all

``--sample N`` prints N parsed records to stdout so a fixture can be
hand-trimmed from real values in the operator's own session. Nothing it
prints is written to the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EXPERIMENT_ROOT.parent.parent
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from ingest.contract import FetchWindow  # noqa: E402
from ingest.space_weather import FeedReceipt  # noqa: E402
from ingest.store import CurrentArtifact  # noqa: E402

UTC = timezone.utc
RECEIPT_DIR = REPO_ROOT / "docs" / "research" / "wayfinder" / "space-weather-receipts"

#: Adapter modules whose registered adapters this script can run. The
#: products module is agent B's; the other two are accepted when they exist
#: so one command covers every space-weather source in the experiment.
ADAPTER_MODULES = ("ingest.adapters.swpc_products", "ingest.adapters.swpc", "ingest.adapters.gfz")


def load_adapters() -> dict[str, Any]:
    import importlib

    from ingest.registry import registered_adapters

    for name in ADAPTER_MODULES:
        try:
            importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    return registered_adapters()


def _digest(path: Path) -> tuple[int, str]:
    body = path.read_bytes()
    return len(body), hashlib.sha256(body).hexdigest()


def _labels(dataset_path: Path) -> dict[str, list[str]]:
    """The platform labels the written artifact actually carries."""
    import xarray
    import zarr

    with zarr.storage.ZipStore(str(dataset_path), mode="r") as store:
        dataset = xarray.open_zarr(store, consolidated=False)
        return {
            str(name): [str(value) for value in dataset[name].values]
            for name in dataset.dims
            if name != "valid_time" and name in dataset.coords
        }


def capture(source_id: str, adapter: Any, *, sample: int) -> dict[str, Any]:
    window = FetchWindow(now=datetime.now(UTC))
    workdir = Path(tempfile.mkdtemp(prefix=f"capture-{source_id}-"))
    try:
        candidates = adapter.discover(window)
        candidate = candidates[0]
        receipt = candidate.detail.get("receipt")
        parsed = candidate.detail.get("records")
        if sample and isinstance(parsed, list):
            print(f"--- {source_id}: {sample} sample record(s) ---")
            print(json.dumps(parsed[-sample:], indent=1)[:8000])
        if sample and isinstance(candidate.detail.get("payload"), dict):
            print(f"--- {source_id}: payload object ---")
            print(json.dumps(candidate.detail["payload"], indent=1)[:8000])
        result = adapter.fetch(candidate, window, workdir)
        artifact = result.artifacts[0]
        byte_size, artifact_sha = _digest(artifact.payload_path)
        revision_id = f"capture-{source_id}-{artifact_sha[:16]}"
        published = CurrentArtifact(
            source_id=source_id,
            logical_name=artifact.logical_name,
            revision_id=revision_id,
            object_key=f"capture/{source_id}/{artifact.logical_name}",
            media_type=artifact.media_type,
            byte_size=byte_size,
            provenance=dict(artifact.provenance),
            published_at=result.retrieved_at,
            run_time=result.run_time,
            retrieved_at=result.retrieved_at,
            provider_run_id=result.provider_run_id,
            native_crs=result.native_crs,
        )

        # Exercise the HTTP route over the production LiveStore reader with a
        # local test backing store. The artifact digest above independently
        # pins the bytes; only the compact comparison summary survives.
        from fastapi.testclient import TestClient
        import importlib
        api_module = importlib.import_module("weather_api.app")
        from weather_api.store import LiveStore

        class CaptureStore(LiveStore):
            def __init__(self) -> None:
                super().__init__(artifact_store=None, cache_dir=workdir)

            def current(self):
                return [published]

            def _local_copy(self, _artifact):
                return artifact.payload_path

            def assert_object_store_reachable(self) -> None:
                pass

        old_mode = os.environ.get("WEATHER_DATA_MODE")
        old_store = api_module.live_store
        try:
            os.environ["WEATHER_DATA_MODE"] = "live"
            api_module.live_store = lambda: CaptureStore()
            capture_store = CaptureStore()
            stored_series = capture_store.read_series(source_id, artifact.logical_name)
            assert stored_series is not None
            response = TestClient(api_module.app).get(f"{api_module.PREFIX}/space-weather/products")
        finally:
            api_module.live_store = old_store
            if old_mode is None:
                os.environ.pop("WEATHER_DATA_MODE", None)
            else:
                os.environ["WEATHER_DATA_MODE"] = old_mode
        response.raise_for_status()
        body = response.json()
        matched = next(
            item for item in body["products"]
            if item["source_id"] == source_id and item["logical_name"] == artifact.logical_name
        )
        expected_latest = {}
        for served_name, variable in stored_series.variables.items():
            name, _, label = served_name.partition("@")
            value = None
            stamp = None
            for index in range(len(variable.values) - 1, -1, -1):
                if variable.values[index] is not None:
                    value = variable.values[index]
                    stamp = stored_series.times[index]
                    break
            expected_latest[(name, label or None)] = (variable.units, value, stamp)
        received_latest = {
            (item["variable"], item["label"]): (
                item["units"],
                item["value"],
                datetime.fromisoformat(item["time"].replace("Z", "+00:00")) if item["time"] else None,
            )
            for item in matched["latest"]
        }
        if received_latest != expected_latest:
            raise AssertionError(f"API latest-value readback differs from artifact for {source_id}")
        if matched["revision_id"] != revision_id or matched["provider_run_id"] != result.provider_run_id:
            raise AssertionError(f"API artifact identity differs from capture for {source_id}")
        if body["data_mode"] != "live" or body["operational"] is not False:
            raise AssertionError(f"API mode/operational declaration differs for {source_id}")
        valid_times = candidate.detail.get("valid_times") or []
        record = {
            "source_id": source_id,
            "adapter_version": getattr(adapter, "adapter_version", None),
            "logical_name": artifact.logical_name,
            "url": receipt.url if isinstance(receipt, FeedReceipt) else None,
            "request_parameters": (receipt.request_parameters if isinstance(receipt, FeedReceipt) else None) or {},
            "byte_count": receipt.byte_count if isinstance(receipt, FeedReceipt) else None,
            "sha256": receipt.sha256 if isinstance(receipt, FeedReceipt) else None,
            "captured_at": receipt.captured_at if isinstance(receipt, FeedReceipt) else None,
            "last_modified": (receipt.last_modified if isinstance(receipt, FeedReceipt) else None),
            "artifact_byte_size": byte_size,
            "artifact_sha256": artifact_sha,
            "artifact_revision": revision_id,
            "record_count": len(parsed) if isinstance(parsed, list) else len(valid_times),
            "instant_count": len(valid_times),
            "newest_instant": valid_times[-1] if valid_times else None,
            "oldest_instant": valid_times[0] if valid_times else None,
            "platforms": _labels(artifact.payload_path),
            "provider_run_id": result.provider_run_id,
            "complete": result.complete,
            "notes": result.notes,
            "api_readback": {
                "route": f"{api_module.PREFIX}/space-weather/products",
                "http_status": response.status_code,
                "data_mode": body["data_mode"],
                "operational": body["operational"],
                "source_id": matched["source_id"],
                "logical_name": matched["logical_name"],
                "revision_id": matched["revision_id"],
                "provider_run_id": matched["provider_run_id"],
                "record_count": matched["record_count"],
                "newest_instant": matched["newest_instant"],
                "measurement_scope": matched["measurement_scope"],
                "evidence_classes": matched["evidence_classes"],
                "quality_status": matched["quality"]["status"],
                "structural_validation_status": matched["structural_validation"]["status"],
                "missing_required_fields": matched["coverage"].get("missing_required_fields", []),
                "latest_fields_verified": len(expected_latest),
                "latest_value_unit_time_match": True,
                "artifact_sha256_verified_before_readback": True,
            },
        }
        return record
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_ids", nargs="*", help="registry source ids to capture")
    parser.add_argument("--all", action="store_true", help="capture every registered space-weather adapter")
    parser.add_argument("--sample", type=int, default=0, help="print N parsed records to stdout (never written to the repo)")
    parser.add_argument("--receipt-dir", type=Path, default=RECEIPT_DIR)
    args = parser.parse_args(argv)

    adapters = load_adapters()
    wanted = list(args.source_ids) or (sorted(adapters) if args.all else [])
    if not wanted:
        parser.error("name at least one source id, or pass --all")
    missing = [source_id for source_id in wanted if source_id not in adapters]
    if missing:
        parser.error(f"no registered adapter for {missing}")

    args.receipt_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for source_id in wanted:
        try:
            record = capture(source_id, adapters[source_id], sample=args.sample)
        except Exception as error:  # a capture that fails is reported, not hidden
            failures += 1
            print(f"{source_id}: FAILED: {type(error).__name__}: {error}")
            continue
        destination = args.receipt_dir / f"{source_id}.json"
        destination.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps(record, indent=2, sort_keys=True))
        print(f"-> {destination}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
