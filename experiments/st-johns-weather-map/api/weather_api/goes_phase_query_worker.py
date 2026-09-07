"""Kernel-bounded ACTPF crop using the existing native scientific decoder."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Bound native-library thread pools before importing the scientific stack.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy
import xarray

from ingest.adapters.goes_abi import parse_scan_stamp
from ingest.adapters.goes_abi_l2 import MAX_GRANULE_BYTES, PRODUCTS, crop_product, parse_product_key
from ingest.contract import EVIDENCE_BOX_BOUNDS

if __name__ == "__main__":
    output = Path(sys.argv[1])
    key = sys.argv[2]
    body = sys.stdin.buffer.read(MAX_GRANULE_BYTES + 1)
    if len(body) > MAX_GRANULE_BYTES:
        raise ValueError("ACTPF granule exceeds ceiling")
    raw = output.with_name("input.nc")
    try:
        raw.write_bytes(body)
        del body
        with xarray.open_dataset(raw) as source:
            projection = dict(source["goes_imager_projection"].attrs)
        dataset, stats = crop_product(raw, PRODUCTS["ABI-L2-ACTPF"], bounds=EVIDENCE_BOX_BOUNDS)
        stamp = parse_product_key(key, "ABI-L2-ACTPF")
        if stamp is None or stats["source_attrs"]["dataset_name"] != key.rsplit("/", 1)[-1]:
            raise ValueError("ACTPF granule object identity mismatch")
        if abs((stats["scan_start"] - parse_scan_stamp(stamp)).total_seconds()) > 1:
            raise ValueError("ACTPF granule time mismatch")
        phase = dataset["cloud_top_phase"].values
        if numpy.any(numpy.isfinite(phase) & ~numpy.isin(phase, (0, 1, 2, 3, 4, 5))):
            raise ValueError("ACTPF phase is outside the exact native categorical domain")
        if not stats["field_dispositions"][0]["usable_cells"]:
            raise ValueError("ACTPF has no producer-readable phase cells")
        # Native uncertainty categories and DQF stay codes. No clear/fog inference.
        dataset.attrs.update(operational="false", geometry="native fixed-grid crop; no interpolation or parallax correction")
        dataset.attrs["native_projection_json"] = json.dumps(projection, sort_keys=True)
        dataset.attrs["scan_end"] = stats["source_attrs"]["time_coverage_end"]
        dataset.to_netcdf(output, engine="netcdf4")
        metadata = {"product_id": "ABI-L2-ACTPF", "source_dataset_name": stats["source_attrs"]["dataset_name"],
                    "native_projection": projection, "scan_start": stats["scan_start"].isoformat(), "source_attrs": stats["source_attrs"],
                    "field_dispositions": stats["field_dispositions"], "good_quality_cells": stats["good_quality_cells"],
                    "coverage_cells": stats["coverage_cells"], "covers_bounds": stats["covers_bounds"],
                    "units": "code", "quality_native_name": "DQF", "readable_quality_values": [0],
                    "uncertainty": "native Phase categories and DQF; no locally estimated uncertainty"}
        sys.stdout.write(json.dumps(metadata))
    finally:
        raw.unlink(missing_ok=True)
