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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EXPERIMENT_ROOT.parent.parent
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from ingest.contract import FetchWindow  # noqa: E402
from ingest.space_weather import FeedReceipt  # noqa: E402

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
            "record_count": len(parsed) if isinstance(parsed, list) else len(valid_times),
            "instant_count": len(valid_times),
            "newest_instant": valid_times[-1] if valid_times else None,
            "oldest_instant": valid_times[0] if valid_times else None,
            "platforms": _labels(artifact.payload_path),
            "provider_run_id": result.provider_run_id,
            "complete": result.complete,
            "notes": result.notes,
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
