"""Capture all selected RAQDPS/RDAQA WCS fields with exact HTTP receipts.

Run from the experiment root with ``PYTHONPATH=.:api``. Raw bytes remain only
in the chosen output directory; commit only the compact derived receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import xarray
import zarr

from ingest.adapters.eccc_analysis_contracts import PRODUCT_CONTRACTS, fetch_unresolved_product
from ingest.adapters.eccc_geomet_wcs import GeoMetWCSClient, fetch_artifact
from ingest.resources import acquisition_budget

PRODUCTS = ("raqdps_hourly", "raqdps_statistics", "rdaqa_preliminary", "rdaqa_final", "rdaqa_smoke")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cap-bytes", type=int, default=64 << 20)
    args = parser.parse_args()
    root: Path = args.output
    root.mkdir(parents=True, exist_ok=True)
    client = GeoMetWCSClient(scratch_dir=root / "scratch")
    rows: list[dict[str, object]] = []
    try:
        with acquisition_budget(args.cap_bytes) as budget:
            for product in PRODUCTS:
                contract = PRODUCT_CONTRACTS[product]
                first = client.metadata(contract.fields[0].coverage_id)
                valid_time = first.time.default
                reference_time = first.reference_time.default if first.reference_time else None
                result = fetch_unresolved_product(
                    client, product, valid_time=valid_time, reference_time=reference_time,
                    workdir=root / product,
                )
                if result.complete or result.qc_passed is not True:
                    raise RuntimeError(f"{product} did not return the expected structural-only refusal")
                for field, artifact in zip(contract.fields, result.artifacts, strict=True):
                    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
                    try:
                        stored_units = xarray.open_zarr(store, consolidated=False)[field.variable].attrs["units"]
                    finally:
                        store.close()
                    rows.append({
                        "product": product, "coverage_id": field.coverage_id, "variable": field.variable,
                        "valid_time": artifact.provenance["valid_time"], "run_time": artifact.provenance["run_time"],
                        "http_completed_at": artifact.provenance["http_completed_at"],
                        "url": artifact.provenance["source_uri"], "headers": artifact.provenance["http_response_headers"],
                        "raw": artifact.provenance["raw_response"],
                        "artifact": {"path": str(artifact.payload_path), "bytes": artifact.byte_size, "sha256": artifact.provenance["sha256"]},
                        "units_as_published": artifact.provenance["units_as_published"], "stored_units": stored_units,
                        "group_complete": result.complete, "group_qc_passed": result.qc_passed, "group_notes": result.notes,
                    })
    finally:
        client.close()
    receipt = {
        "capture_completed_at": datetime.now(timezone.utc).isoformat(),
        "finite_operation_cap_bytes": args.cap_bytes,
        "received_bytes": budget.used,
        "rows": rows,
    }
    receipt_path = root / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True))
    print(json.dumps({
        "count": len(rows),
        "receipt": str(receipt_path),
        "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "raw_bytes": sum(int(row["raw"]["bytes"]) for row in rows),  # type: ignore[index]
    }, indent=2))


if __name__ == "__main__":
    main()
