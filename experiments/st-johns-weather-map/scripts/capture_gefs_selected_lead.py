"""Run one reviewed GEFS selected-lead capture through the bounded child."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from weather_api.gefs_query import (
    GEFSBoundedLoader,
    GEFSQueryService,
    GEFSRequestKey,
    GEFS_FIELDS,
    GEFS_PRODUCT_SET,
    declared_members,
)

ST_JOHNS_BOUNDS = (("east", -46.0), ("north", 50.5), ("south", 45.0), ("west", -58.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="Canonical YYYYMMDDHH UTC run")
    parser.add_argument("--lead", required=True, type=int)
    parser.add_argument("--workspace", type=Path, default=Path("/work"))
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    run_time = datetime.strptime(args.run, "%Y%m%d%H").replace(tzinfo=UTC)
    key = GEFSRequestKey(
        args.run,
        run_time,
        args.lead,
        GEFS_PRODUCT_SET,
        declared_members(),
        GEFS_FIELDS,
        ST_JOHNS_BOUNDS,
    )
    entry = GEFSQueryService(GEFSBoundedLoader(args.workspace), workspace=args.workspace).query(key)
    result = {
        "run_id": entry.key.run_id,
        "lead": entry.key.lead,
        "valid_time": entry.valid_time.isoformat(),
        "fetched_at": entry.fetched_at.isoformat(),
        "members_declared": len(entry.key.members),
        "members_present": list(entry.members_present),
        "mandatory_failures": dict(entry.mandatory_failures),
        "optional_absences": {key: list(value) for key, value in entry.optional_absences.items()},
        "normalized_bytes": len(entry.payload),
        "normalized_sha256": hashlib.sha256(entry.payload).hexdigest(),
        "cache_backing_bytes": entry.backing_bytes,
        "transport_receipt_count": len(entry.provenance["transport_receipts"]),
    }
    args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
