#!/usr/bin/env python3
"""Bounded live evidence probe for the experimental GeoMet WCS contract."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from ingest.adapters.eccc_geomet_wcs import (
    CoverageField,
    GeoMetWCSClient,
    audit_inventory,
    contract_fields,
    fetch_artifact,
    fetch_pressure_profile_artifact,
)

UTC = timezone.utc
MAX_TOTAL_BYTES = 2 << 30
MAX_ELAPSED_SECONDS = 45 * 60
EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = EXPERIMENT_ROOT / "docs"


def _artifact_reference(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(DOCS_ROOT))
    except ValueError:
        return str(path.resolve())
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
    parser.add_argument("--all-selected", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
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
        selected_acquisitions = []
        total_transfer_bytes = 0
        if args.all_selected:
            for model in ("hrdps", "rdps", "gdps"):
                for field in contract_fields(model):
                    if field.coverage_id not in advertised:
                        continue
                    if (datetime.now(UTC) - started).total_seconds() > MAX_ELAPSED_SECONDS:
                        selected_acquisitions.append({"coverage_id": field.coverage_id, "status": "not-attempted-time-cap"})
                        continue
                    if total_transfer_bytes >= MAX_TOTAL_BYTES:
                        selected_acquisitions.append({"coverage_id": field.coverage_id, "status": "not-attempted-byte-cap"})
                        continue
                    row_started = time.monotonic()
                    try:
                        capability = client.metadata(field.coverage_id)
                        valid = capability.time.end if capability.time else None
                        run = capability.reference_time.end if capability.reference_time else None
                        if valid is None:
                            raise RuntimeError("missing-time-dimension")
                        row_dir = scratch / "selected" / model / field.coverage_id.replace("/", "_")
                        artifact = fetch_artifact(client, field, valid_time=valid, reference_time=run,
                                                  workdir=row_dir, model=model)
                        tiff_bytes = next(row_dir.glob("*.tif")).stat().st_size
                        total_transfer_bytes += tiff_bytes
                        import numpy
                        import xarray
                        import zarr
                        store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
                        dataset = xarray.open_zarr(store, consolidated=False)
                        values = numpy.asarray(dataset[field.variable].values)
                        finite = values[numpy.isfinite(values)]
                        selected_acquisitions.append({
                            "coverage_id": field.coverage_id,
                            "variable": field.variable,
                            "status": "retrieved-artifact-roundtrip",
                            "transfer_bytes": tiff_bytes,
                            "artifact_bytes": artifact.byte_size,
                            "sha256": artifact.provenance["sha256"],
                            "valid_time": artifact.provenance["valid_time"],
                            "run_time": artifact.provenance["run_time"],
                            "sampling_geometry": artifact.provenance["sampling_geometry"],
                            "sampling_resolution_degrees": artifact.provenance["sampling_resolution_degrees"],
                            "requested_shape": artifact.provenance["requested_shape"],
                            "resampling": artifact.provenance["resampling"],
                            "units_as_published": artifact.provenance["units_as_published"],
                            "units_recognised": artifact.provenance["units_recognised"],
                            "finite_cells": int(finite.size),
                            "nodata_cells": int(values.size - finite.size),
                            "minimum": None if not finite.size else float(finite.min()),
                            "maximum": None if not finite.size else float(finite.max()),
                            "elapsed_seconds": round(time.monotonic() - row_started, 3),
                        })
                    except Exception as error:
                        selected_acquisitions.append({
                            "coverage_id": field.coverage_id,
                            "variable": field.variable,
                            "status": "failed",
                            "error_type": type(error).__name__,
                            "error": str(error)[:500],
                            "elapsed_seconds": round(time.monotonic() - row_started, 3),
                        })
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
            retained = None
            if args.artifact_dir:
                args.artifact_dir.mkdir(parents=True, exist_ok=True)
                retained_path = args.artifact_dir / artifact.payload_path.name
                shutil.copy2(artifact.payload_path, retained_path)
                retained = _artifact_reference(retained_path)
            artifacts.append({
                "coverage_id": field.coverage_id,
                "status": "retrieved-artifact-roundtrip",
                "bytes": artifact.byte_size,
                "sha256": artifact.provenance["sha256"],
                "valid_time": artifact.provenance["valid_time"],
                "run_time": artifact.provenance["run_time"],
                "run_identity_status": artifact.provenance["run_identity_status"],
                "operational": artifact.provenance["operational"],
                "retained_artifact": retained,
                "sampling_geometry": artifact.provenance["sampling_geometry"],
                "sampling_resolution_degrees": artifact.provenance["sampling_resolution_degrees"],
                "resampling": artifact.provenance["resampling"],
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
        retained_profile = None
        if args.artifact_dir:
            args.artifact_dir.mkdir(parents=True, exist_ok=True)
            retained_profile_path = args.artifact_dir / "hrdps_relative_humidity_850_700hpa.zarr.zip"
            shutil.copy2(profile.payload_path, retained_profile_path)
            retained_profile = _artifact_reference(retained_profile_path)
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
            "selected_acquisition": {
                "requested": args.all_selected,
                "scope": "one latest advertised valid time per each of 245 selected coverages over the exact small Avalon API bbox",
                "bounds": {"west": -55.0, "south": 46.5, "east": -51.0, "north": 48.5},
                "total_transfer_bytes": total_transfer_bytes,
                "byte_cap": MAX_TOTAL_BYTES,
                "elapsed_cap_seconds": MAX_ELAPSED_SECONDS,
                "results": selected_acquisitions,
            },
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
                "retained_artifact": retained_profile,
                "sampling_geometry": profile.provenance["sampling_geometry"],
                "sampling_resolution_degrees": profile.provenance["sampling_resolution_degrees"],
                "resampling": profile.provenance["resampling"],
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
