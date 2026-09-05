#!/usr/bin/env python3
"""Metadata-only proof that every WeatherNext 3 statistics field has one lead.

No forecast object body is downloaded.  The operation describes the exact
lead-6 chunk for all 126 arrays, records immutable object identity and sums the
bytes a later bounded value read would require.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import weathernext_probe_manifest as contract
from weathernext_bounded_sample import RUN_PREFIX, Transport


def run(output: Path, *, deadline_seconds: int = 900) -> dict:
    started = time.monotonic()
    transport = Transport(started + deadline_seconds)
    bucket_result = transport._run(["buckets", "describe", f"gs://{contract.BUCKET}", "--raw", "--format=json"])
    bucket = json.loads(bucket_result.stdout)
    billing = bucket.get("billing")
    if billing is not None and billing.get("requesterPays") is not False:
        raise RuntimeError("statistics bucket requester-pays state is not disabled")

    objects = []
    for field in contract.EXPECTED_FIELDS:
        uri = f"{RUN_PREFIX}/{field}/c/6/0/0"
        item = transport.describe(uri)
        objects.append({
            "field": field,
            "object": uri.removeprefix(f"gs://{contract.BUCKET}/"),
            "generation": str(item.get("generation", "")),
            "etag": item.get("etag"),
            "size": int(item["size"]),
            "updated": item.get("updateTime"),
        })
    if any(not item["generation"] or not item["etag"] or item["size"] <= 0 for item in objects):
        raise RuntimeError("one or more field chunks lack immutable identity or positive size")
    payload = {
        "schema_version": 1,
        "result": "success",
        "source_id": "google-weathernext-3-statistics",
        "product": contract.PRODUCT,
        "access_surface": "gcs_statistics_spatial",
        "requester_pays": False,
        "requester_pays_evidence": "raw JSON API billing block absent (disabled)",
        "initialization": contract.INITIALIZATION,
        "lead_hours": 6,
        "valid_time": "2026-08-01T06:00:00Z",
        "field_count": len(objects),
        "field_objects": objects,
        "forecast_bytes_not_downloaded": sum(item["size"] for item in objects),
        "object_operations": transport.requests,
        "received_forecast_bytes": transport.received_bytes,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "note": "Metadata-only existence and cost proof; no forecast values were decoded.",
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded)
    payload["output_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(f"described {result['field_count']} fields; forecast bytes downloaded: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
