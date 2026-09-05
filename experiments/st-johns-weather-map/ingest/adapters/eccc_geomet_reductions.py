"""Bounded experimental acquisition of ECCC GEPS producer reductions.

GeoMet publishes no ``GEPS.MEM`` coverages.  This module therefore preserves
each issued mean, standard deviation, percentile, or threshold probability as
a separate retrieved variable.  It never constructs members or recomputes a
statistic.  It is intentionally not registered or scheduled.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import xarray

from ingest.adapters.eccc_geomet import ATTRIBUTION, GEOMET_BASE_URL, LICENCE
from ingest.adapters.eccc_geomet_ensemble import (
    REPS_EVIDENCE_BOX,
    coverage_url,
    decode_reps_geotiff,
)
from ingest.contract import MEDIA_ZARR, Artifact
from ingest.grib import write_zarr
from ingest.http import PoliteClient

GEPS_WIDTH = 24
GEPS_HEIGHT = 11
GEPS_SCALESIZE = "long(24),lat(11)"


class GEPSReductionError(RuntimeError):
    """A selected producer reduction was absent, malformed, or inconsistent."""


@dataclass(frozen=True)
class GEPSReduction:
    coverage_id: str
    variable: str
    field: str
    statistic: str
    units: str
    quantile: float | None = None
    threshold: str | None = None


SELECTED_REDUCTIONS = (
    GEPSReduction("GEPS.DIAG.3_TT.ERMEAN", "temperature_2m__mean", "temperature_2m", "mean", "degC"),
    GEPSReduction("GEPS.DIAG.3_TT.ERSSTD", "temperature_2m__spread", "temperature_2m", "standard_deviation", "degC"),
    GEPSReduction("GEPS.DIAG.3_TT.ERC50", "temperature_2m__p50", "temperature_2m", "percentile", "degC", quantile=0.5),
    GEPSReduction("GEPS.DIAG.3_NT.ERC50", "total_cloud_opacity__p50", "total_cloud_opacity", "percentile", "percent", quantile=0.5),
    GEPSReduction("GEPS.DIAG.12_GUST-15MS.PROB", "raw__gust_over_15ms_probability", "raw_gust_threshold", "threshold_probability", "percent", threshold="gust > 15 m s-1"),
)


def fetch_geps_reductions(
    *, valid_time: datetime, reference_time: datetime, workdir: Path,
    reductions: Sequence[GEPSReduction] = SELECTED_REDUCTIONS,
    bounds: Mapping[str, float] = REPS_EVIDENCE_BOX,
    client: PoliteClient | None = None,
) -> Artifact:
    """Retrieve selected issued reductions into one immutable numeric artifact."""
    if not reductions:
        raise ValueError("at least one GEPS reduction must be selected")
    workdir.mkdir(parents=True, exist_ok=True)
    http = client or PoliteClient(attempts=2, timeout_seconds=45)
    owned = client is None
    arrays: dict[str, xarray.DataArray] = {}
    receipts: list[dict[str, object]] = []
    try:
        for reduction in reductions:
            url = coverage_url(
                reduction.coverage_id, bounds, base_url=GEOMET_BASE_URL,
                scalesize=GEPS_SCALESIZE, valid_time=valid_time,
                reference_time=reference_time,
            )
            response = http.get(url)
            payload = response.content
            try:
                array = decode_reps_geotiff(
                    payload, coverage=reduction.coverage_id, variable=reduction.variable,
                    valid_time=valid_time, bounds=bounds, width=GEPS_WIDTH, height=GEPS_HEIGHT,
                )
            except Exception as error:
                raise GEPSReductionError(
                    f"{reduction.coverage_id}: selected reduction did not decode: {error}"
                ) from error
            array.attrs.update({
                "units": reduction.units,
                "field": reduction.field,
                "provider_statistic": reduction.statistic,
                "quantile": reduction.quantile,
                "threshold": reduction.threshold,
                "computed_here": False,
            })
            arrays[reduction.variable] = array
            receipts.append({
                "coverage_id": reduction.coverage_id,
                "variable": reduction.variable,
                "field": reduction.field,
                "provider_statistic": reduction.statistic,
                "quantile": reduction.quantile,
                "threshold": reduction.threshold,
                "source_uri": url,
                "bytes": len(payload),
            })
    finally:
        if owned:
            http.close()
    dataset = xarray.Dataset(arrays)
    dataset.attrs.update({
        "source_grid_crs": "EPSG:4326",
        "source_grid_axis_spacing_degrees": 0.5,
        "stored_crs": "EPSG:4326",
        "resampling": "server_resampled_method_unknown",
        "operational": False,
    })
    output = write_zarr(dataset, workdir / "eccc_geps_reductions.zarr.zip")
    provenance = {
        "adapter_version": "eccc-geps-reductions-experimental-v1",
        "source_id": "eccc-geps",
        "producer": "Environment and Climate Change Canada",
        "product": "Global Ensemble Prediction System producer reductions",
        "access_path": "GeoMet WCS 2.0.1",
        "run_time": reference_time.astimezone(UTC).isoformat(),
        "valid_time": valid_time.astimezone(UTC).isoformat(),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "requested_bounds": dict(bounds),
        "requested_output_shape": [GEPS_HEIGHT, GEPS_WIDTH],
        "stored_crs": "EPSG:4326",
        "resampling": "server_resampled_method_unknown",
        "reductions": receipts,
        "member_count": None,
        "members_published": False,
        "computed_here": False,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        "quality": {"status": "unknown", "flags": ["experimental_source_contract_pending"]},
        "operational": False,
    }
    return Artifact("geps_reductions", MEDIA_ZARR, output, provenance)
