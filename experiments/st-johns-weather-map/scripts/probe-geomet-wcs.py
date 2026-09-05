#!/usr/bin/env python3
"""Bounded live evidence probe for the experimental GeoMet WCS contract."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ingest.adapters.eccc_geomet_wcs import (
    CoverageField,
    GeoMetWCSClient,
    audit_inventory,
    fetch_artifact,
    fetch_pressure_profile_artifact,
)

UTC = timezone.utc
REPRESENTATIVE = (
    ("hrdps", CoverageField("HRDPS.CONTINENTAL_HR_40m", "relative_humidity_40m")),
    ("hrdps", CoverageField("HRDPS-WEonG_2.5km_SkyState", "weong_sky_state")),
    ("rdps", CoverageField("RDPS_10km_SeeingIndex", "seeing_class_eccc")),
    ("rdps", CoverageField("RDPS_10km_SkyTransparencyIndex", "transparency_class_eccc")),
    ("gdps", CoverageField("GDPS-WEonG_15km_LiquidFogVisibility", "weong_liquid_fog_visibility")),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="geomet-wcs-probe-") as directory:
        scratch = Path(directory)
        client = GeoMetWCSClient(scratch_dir=scratch)
        capabilities = scratch / "capabilities.xml"
        advertised = client.inventory(capabilities)
        rows = {model: audit_inventory(advertised, model) for model in ("hrdps", "rdps", "gdps")}
        selected_by_id = {
            row["coverage_id"]: row["variable"]
            for model_rows in rows.values()
            for row in model_rows
            if row["disposition"] == "advertised"
        }
        family_ids = sorted(
            coverage_id for coverage_id in advertised
            if coverage_id.startswith((
                "HRDPS.CONTINENTAL", "HRDPS-WEonG", "RDPS_10km", "RDPS-WEonG",
                "GDPS_15km", "GDPS-WEonG", "GDPS-GEML",
            ))
        )
        artifacts = []
        for model, field in REPRESENTATIVE:
            capability = client.metadata(field.coverage_id)
            valid = capability.time.end if capability.time else None
            run = capability.reference_time.end if capability.reference_time else None
            if valid is None:
                artifacts.append({"coverage_id": field.coverage_id, "status": "missing-time-dimension"})
                continue
            artifact = fetch_artifact(client, field, valid_time=valid, reference_time=run,
                                      workdir=scratch / model / field.variable, model=model)
            artifacts.append({
                "coverage_id": field.coverage_id,
                "status": "retrieved-artifact-roundtrip",
                "bytes": artifact.byte_size,
                "sha256": artifact.provenance["sha256"],
                "valid_time": artifact.provenance["valid_time"],
                "run_time": artifact.provenance["run_time"],
                "run_identity_status": artifact.provenance["run_identity_status"],
                "operational": artifact.provenance["operational"],
            })
        profile_fields = (
            CoverageField("HRDPS.CONTINENTAL.PRES_HR.850", "relative_humidity_pressure"),
            CoverageField("HRDPS.CONTINENTAL.PRES_HR.700", "relative_humidity_pressure"),
        )
        profile_capability = client.metadata(profile_fields[0].coverage_id)
        profile_valid = profile_capability.time.end
        profile_run = profile_capability.reference_time.end if profile_capability.reference_time else None
        profile = fetch_pressure_profile_artifact(
            client, profile_fields, (850, 700), valid_time=profile_valid,
            reference_time=profile_run, workdir=scratch / "hrdps" / "profile",
            model="hrdps",
        )
        report = {
            "retrieved_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round((datetime.now(UTC) - started).total_seconds(), 3),
            "wcs_coverage_count": len(advertised),
            "prefix_counts": {
                "hrdps": sum(item.startswith("HRDPS.CONTINENTAL") or item.startswith("HRDPS-WEonG") for item in advertised),
                "rdps": sum(item.startswith("RDPS_10km") or item.startswith("RDPS-WEonG") for item in advertised),
                "gdps_15km_and_geml_25km": sum(item.startswith("GDPS_15km") or item.startswith("GDPS-WEonG") or item.startswith("GDPS-GEML") for item in advertised),
            },
            "selected_contract": {
                model: {
                    status: sum(row["disposition"] == status for row in model_rows)
                    for status in ("advertised", "missing", "not-published")
                }
                for model, model_rows in rows.items()
            },
            "selected_fields": rows,
            "full_family_inventory": [
                {
                    "coverage_id": coverage_id,
                    "variable": selected_by_id.get(coverage_id),
                    "disposition": (
                        "advertised-selected-capability" if coverage_id in selected_by_id
                        else "advertised-capability-only-deferred"
                    ),
                    "reason": (
                        "issue-79 selected field; exact canonical mapping is declared"
                        if coverage_id in selected_by_id
                        else "semantic normalization and production admission are not established"
                    ),
                    "destination": (
                        selected_by_id[coverage_id]
                        if coverage_id in selected_by_id
                        else "isolated raw__<coverage_id> artifact only; future source contract"
                    ),
                }
                for coverage_id in family_ids
            ],
            "representative_artifacts": artifacts,
            "representative_profile_artifact": {
                "coverage_ids": profile.provenance["coverage_ids"],
                "pressure_levels_hpa": profile.provenance["pressure_levels_hpa"],
                "status": "retrieved-profile-artifact-roundtrip",
                "bytes": profile.byte_size,
                "sha256": profile.provenance["sha256"],
                "valid_time": profile.provenance["valid_time"],
                "run_time": profile.provenance["run_time"],
                "run_identity_status": profile.provenance["run_identity_status"],
                "operational": profile.provenance["operational"],
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
