"""Audit-only retention of exact GEFS selected bytes for bounded source proof."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from ingest.adapters.noaa_s3 import MAX_GEFS_MEMBER_BYTES
from weather_api.gefs_query import GEFS_IDX_BYTES, GEFS_MEMBER_COUNT, GEFS_FIELDS

IDX_CAPTURE_LIMIT = GEFS_MEMBER_COUNT * GEFS_IDX_BYTES
RANGE_CAPTURE_LIMIT = GEFS_MEMBER_COUNT * len(GEFS_FIELDS) * MAX_GEFS_MEMBER_BYTES


class GEFSAuditClient:
    """Tee completed bounded bodies into a fresh, finite evidence directory."""

    def __init__(self, delegate: object, evidence_dir: Path) -> None:
        self.delegate = delegate
        self.root = evidence_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if any(self.root.iterdir()):
            raise RuntimeError("GEFS audit evidence directory must be empty")
        required = IDX_CAPTURE_LIMIT + RANGE_CAPTURE_LIMIT
        if shutil.disk_usage(self.root).free < required:
            raise RuntimeError("GEFS audit evidence filesystem lacks the complete capture allowance")
        self.receipts = self.root / "receipts.jsonl"
        self.idx_bytes = 0
        self.range_bytes = 0
        self.sequence = 0
        self.idx_count = 0
        self.range_count = 0

    def _retain(self, kind: str, body: bytes, receipt: dict[str, object]) -> None:
        ceiling = IDX_CAPTURE_LIMIT if kind == "index" else RANGE_CAPTURE_LIMIT
        used = self.idx_bytes if kind == "index" else self.range_bytes
        if used + len(body) > ceiling:
            raise RuntimeError(f"GEFS {kind} audit capture exceeded aggregate ceiling")
        count = self.idx_count if kind == "index" else self.range_count
        maximum = GEFS_MEMBER_COUNT if kind == "index" else GEFS_MEMBER_COUNT * len(GEFS_FIELDS)
        if count >= maximum:
            raise RuntimeError(f"GEFS {kind} audit capture exceeded request-count ceiling")
        digest = hashlib.sha256(body).hexdigest()
        if receipt.get("byte_size") != len(body) or receipt.get("sha256") != digest:
            raise RuntimeError("GEFS audit body does not match completed transport receipt")
        self.sequence += 1
        name = f"{self.sequence:03d}-{kind}-{digest}.bin"
        path = self.root / name
        with path.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        record = {"kind": kind, "body_file": name, **receipt}
        with self.receipts.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if kind == "index":
            self.idx_bytes += len(body)
            self.idx_count += 1
        else:
            self.range_bytes += len(body)
            self.range_count += 1

    def get_bytes_with_receipt(self, url: str, *, max_bytes: int):
        body, receipt = self.delegate.get_bytes_with_receipt(url, max_bytes=max_bytes)
        self._retain("index", body, receipt)
        return body, receipt

    def download_ranges_with_receipts(self, url: str, destination: Path, ranges, *, max_bytes: int):
        requested = list(ranges)
        written, receipts = self.delegate.download_ranges_with_receipts(
            url, destination, requested, max_bytes=max_bytes
        )
        payload = destination.read_bytes()
        if written != len(payload) or len(receipts) != len(requested):
            raise RuntimeError("GEFS audit range output does not match request receipts")
        offset = 0
        for receipt, requested_range in zip(receipts, requested, strict=True):
            size = int(receipt["byte_size"])
            body = payload[offset : offset + size]
            if len(body) != size:
                raise RuntimeError("GEFS audit range body is truncated")
            self._retain("range", body, {**receipt, "requested_range": list(requested_range)})
            offset += size
        if offset != len(payload):
            raise RuntimeError("GEFS audit range bodies do not cover destination")
        return written, receipts
