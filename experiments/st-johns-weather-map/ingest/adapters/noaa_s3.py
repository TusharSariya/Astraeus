"""NOAA GFS S3 adapter with .idx byte-range subsetting.

Fetches global forecast data from the NOAA Open Data S3 bucket (noaa-gfs-bdp-pds).
Uses .idx sidecars to request strictly target variables via HTTP byte ranges (~1.7 MB
per lead hour vs 521 MB whole file), keeping well within the 25 GiB cap.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy
import xarray

from ingest.contract import (
    ATLANTIC_CONTEXT_BOUNDS,
    MEDIA_ZARR,
    Adapter,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import (
    cap_open_range,
    crop_to_bbox,
    normalize_units,
    open_grib,
    subset_ranges,
    write_zarr,
)
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, required_leads, validate_run
from ingest.registry import register

UTC = timezone.utc
_log = logging.getLogger(__name__)

NOAA_GFS_S3_BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
MAX_LEAD_HOURS = 24

# GFS 0.25 deg publishes hourly out to f120 and three-hourly to f384. A lead
# past that does not exist, so asking for one is an adapter bug: it must be an
# explicit unavailability rather than a quietly short run.
GFS_HOURLY_LEAD_LIMIT = 120
GFS_PRODUCT_LEAD_LIMIT = 384

GFS_PARAMS = ["PRMSL", "TMP", "DPT", "RH", "UGRD", "VGRD", "APCP", "VIS", "TCDC"]

# Only the fields this experiment actually reads off the GFS surface subset.
# ``vis``, ``tcc`` and ``r2`` are declared optional because their presence in a
# given cycle depends on the product inventory rather than on retrieval
# succeeding. Precipitation accumulation is deliberately not declared: its
# normalized unit and interval semantics are not yet pinned for GFS, and
# declaring a unit we have not verified would turn a guess into a QC verdict.
GFS_MANIFEST = RunManifest(
    source_id="noaa-gfs",
    fields=(
        RequiredField("temperature_2m", "degC", level="2 m"),
        RequiredField("dew_point_2m", "degC", level="2 m"),
        RequiredField("wind_u_10m", "m s-1", level="10 m"),
        RequiredField("wind_v_10m", "m s-1", level="10 m"),
        RequiredField("mean_sea_level_pressure", "hPa", level="mean sea level"),
        RequiredField("relative_humidity_2m", "percent", level="2 m", optional=True),
        RequiredField("visibility", "m", optional=True),
        RequiredField("total_cloud", "percent", level="column", optional=True),
    ),
)

# Map cfgrib/grib variable short names -> canonical experiment variable names
GFS_VAR_MAP = {
    "t2m": "temperature_2m",
    "d2m": "dew_point_2m",
    "r2": "relative_humidity_2m",
    "u10": "wind_u_10m",
    "v10": "wind_v_10m",
    "prmsl": "mean_sea_level_pressure",
    "vis": "visibility",
    "tcc": "total_cloud",
    "tp": "precipitation_accumulation",
    "apcp": "precipitation_accumulation",
}


class NOAAS3Adapter:
    """Ingests NOAA GFS forecasts with byte-range subsetting."""

    source_id = "noaa-gfs"
    adapter_version = "noaa-gfs-v1"

    def __init__(
        self,
        *,
        base_url: str = NOAA_GFS_S3_BASE,
        bounds: Mapping[str, float] = ATLANTIC_CONTEXT_BOUNDS,
        client: PoliteClient | None = None,
        max_lead_hours: int = MAX_LEAD_HOURS,
        product_lead_limit: int = GFS_HOURLY_LEAD_LIMIT,
    ) -> None:
        self._base_url = base_url
        self._bounds = dict(bounds)
        self._client = client
        self._max_lead_hours = max_lead_hours
        self._product_lead_limit = product_lead_limit

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        candidates: list[RunCandidate] = []

        # Check candidate runs from newest to oldest in window
        ref_dt = window.now
        for day_offset in range(2):
            check_date = ref_dt - timedelta(days=day_offset)
            date_str = check_date.strftime("%Y%m%d")
            for cycle_hour in (18, 12, 6, 0):
                cycle_str = f"{cycle_hour:02d}"
                run_dt = datetime.strptime(f"{date_str}{cycle_str}", "%Y%m%d%H").replace(tzinfo=UTC)
                if run_dt > ref_dt:
                    continue

                idx_url = f"{self._base_url}/gfs.{date_str}/{cycle_str}/atmos/gfs.t{cycle_str}z.pgrb2.0p25.f000.idx"
                try:
                    resp = client.get(idx_url)
                    if resp.status_code == 200 and resp.text.strip():
                        candidates.append(
                            RunCandidate(
                                provider_run_id=f"gfs-{date_str}{cycle_str}",
                                run_time=run_dt,
                                urls=[idx_url],
                                detail={
                                    "date_str": date_str,
                                    "cycle": cycle_str,
                                    "run_dt": run_dt,
                                },
                            )
                        )
                        # We only need the latest candidate or up to 2
                        if len(candidates) >= 2:
                            return candidates
                except Exception:
                    continue

        if not candidates:
            raise AdapterUnavailable("No recent NOAA GFS runs found on AWS S3")
        return candidates

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._get_client()
        date_str = candidate.detail.get("date_str")
        cycle_str = candidate.detail.get("cycle")
        run_dt = candidate.run_time or window.now
        retrieved_at = datetime.now(UTC)

        if not date_str or not cycle_str:
            date_str = run_dt.strftime("%Y%m%d")
            cycle_str = run_dt.strftime("%H")

        # The last lead the window needs from this run. A run old enough that
        # the window reaches past the product's published range cannot cover it,
        # and returning a short run silently would look like a complete one.
        needed_lead = int((window.end - run_dt).total_seconds() // 3600)
        if needed_lead > self._product_lead_limit:
            raise AdapterUnavailable(
                f"{self.source_id}: window needs lead +{needed_lead} h from run {candidate.provider_run_id}, "
                f"beyond the product limit of +{self._product_lead_limit} h"
            )

        hourly_datasets: list[xarray.Dataset] = []
        decode_errors: list[str] = []

        for lead_h in range(self._max_lead_hours + 1):
            valid_time = run_dt + timedelta(hours=lead_h)
            if not window.covers(valid_time):
                continue

            lead_str = f"{lead_h:03d}"
            base_filename = f"gfs.t{cycle_str}z.pgrb2.0p25.f{lead_str}"
            grib_url = f"{self._base_url}/gfs.{date_str}/{cycle_str}/atmos/{base_filename}"
            idx_url = f"{grib_url}.idx"

            try:
                idx_text = client.get_text(idx_url)
            except Exception as error:
                decode_errors.append(f"idx:{idx_url}")
                _log.warning("Missing GFS idx sidecar at %s: %s", idx_url, error)
                continue

            # Byte-range subsetting is mandatory here: one f003 file is 521 MiB.
            ranges = cap_open_range(
                subset_ranges(
                    idx_text,
                    params=GFS_PARAMS,
                    merge_gap_bytes=1 << 20,  # merge gaps <= 1 MiB
                )
            )
            if not ranges:
                decode_errors.append(f"no_selected_messages:{idx_url}")
                continue

            local_grib = workdir / f"{base_filename}.subset.grib2"
            try:
                client.download_ranges(
                    grib_url,
                    local_grib,
                    [r.as_tuple() for r in ranges],
                    max_bytes=25 * 1024 * 1024,  # max 25 MB per lead hour
                )
                ds = open_grib(local_grib)
                cropped = crop_to_bbox(ds, self._bounds)
                normalized = normalize_units(cropped)

                # Rename variables to canonical
                rename_dict: dict[str, str] = {}
                for var_name in normalized.data_vars:
                    canonical = GFS_VAR_MAP.get(str(var_name).lower())
                    if canonical:
                        rename_dict[str(var_name)] = canonical

                if rename_dict:
                    normalized = normalized.rename(rename_dict)

                step_ds = normalized.expand_dims(valid_time=[numpy.datetime64(valid_time.replace(tzinfo=None), "ns")])
                hourly_datasets.append(step_ds)
            except Exception as error:
                decode_errors.append(f"decode:{base_filename}")
                _log.warning("Failed processing GFS subset %s: %s", grib_url, error)
            finally:
                local_grib.unlink(missing_ok=True)

        if not hourly_datasets:
            raise AdapterUnavailable(f"No GFS lead hours successfully retrieved for {candidate.provider_run_id}")

        combined = xarray.concat(hourly_datasets, dim="valid_time")
        manifest = RunManifest(
            source_id=GFS_MANIFEST.source_id,
            fields=GFS_MANIFEST.fields,
            required_valid_times=required_leads(window, run_dt, max_lead_hours=self._max_lead_hours),
            bounds=self._bounds,
        )
        validation = validate_run(manifest, combined, window=window, decode_errors=decode_errors)

        zarr_path = workdir / "noaa_gfs.zarr.zip"
        write_zarr(combined, zarr_path)

        provenance = {
            "source_id": self.source_id,
            "producer": "NOAA / NCEP",
            "product": "Global Forecast System (GFS 0.25 deg)",
            "native_resolution": "0.25 deg (~25 km)",
            "native_crs": "EPSG:4326",
            "adapter_version": self.adapter_version,
            "quality": validation.as_quality(),
            "coverage": validation.as_coverage(),
        }

        artifact = Artifact(
            logical_name="surface",
            media_type=MEDIA_ZARR,
            payload_path=zarr_path,
            provenance=provenance,
        )

        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=run_dt,
            retrieved_at=retrieved_at,
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes=f"Retrieved {len(hourly_datasets)} GFS lead steps via .idx byte ranges; {validation.detail}",
        )


GFS_ADAPTER = register(NOAAS3Adapter())
