"""NOAA GFS S3 adapter with .idx byte-range subsetting.

Fetches global forecast data from the NOAA Open Data S3 bucket (noaa-gfs-bdp-pds).
Uses .idx sidecars to request strictly target variables via HTTP byte ranges
(measured ~8.4 MB of selected messages, ~10.5 MB after gap-merging, per lead
hour vs 450+ MB whole file), keeping well within the per-lead ceiling.
"""

from __future__ import annotations

import logging
import re
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
    ByteRange,
    byte_ranges,
    cap_open_range,
    crop_to_bbox,
    normalize_units,
    open_grib,
    parse_idx,
    strip_message_scalars,
    write_zarr,
)
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, required_leads, validate_run
from ingest.registry import register

UTC = timezone.utc
_log = logging.getLogger(__name__)

NOAA_GFS_S3_BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"

# The newest cycle available when the worker runs can be up to ~10 hours old
# (6-hourly cycles plus publication latency), and the evidence window reaches
# 24 hours forward, so covering it needs leads out to run_time + ~34 h. 36 is
# the bound; the window filter below still skips any lead outside it.
MAX_LEAD_HOURS = 36

# GFS 0.25 deg publishes hourly out to f120 and three-hourly to f384. A lead
# past that does not exist, so asking for one is an adapter bug: it must be an
# explicit unavailability rather than a quietly short run.
GFS_HOURLY_LEAD_LIMIT = 120
GFS_PRODUCT_LEAD_LIMIT = 384

# The exact (parameter, level) pairs this adapter reads, matched against the
# .idx sidecar. Selecting on the parameter name alone is how this adapter
# previously fetched most of the file by accident: GFS pgrb2 publishes TMP,
# RH, UGRD, VGRD and TCDC at *every* isobaric level (TMP:500 mb, TCDC:850 mb,
# ...), so a param-only match selected hundreds of messages which the
# gap-merge then coalesced into near-whole-file spans, tripping the 25 MB
# per-lead ceiling on every lead and failing the whole run closed.
#
# APCP is deliberately not selected: its normalized unit and accumulation
# interval semantics are not yet pinned for GFS (see GFS_MANIFEST), so
# retrieving it would only stage bytes nothing may publish.
GFS_IDX_SELECTORS: frozenset[tuple[str, str]] = frozenset(
    {
        ("PRMSL", "mean sea level"),
        ("TMP", "2 m above ground"),
        ("DPT", "2 m above ground"),
        ("RH", "2 m above ground"),
        ("UGRD", "10 m above ground"),
        ("VGRD", "10 m above ground"),
        ("VIS", "surface"),
        ("TCDC", "entire atmosphere"),
        ("LCDC", "low cloud layer"),
        ("MCDC", "middle cloud layer"),
        ("HCDC", "high cloud layer"),
        # Upper-air seeing/transparency ingredients: jet-level winds and
        # column moisture. Exact-pair matching keeps every other isobaric
        # level out, exactly as for the surface set above.
        ("UGRD", "200 mb"),
        ("VGRD", "200 mb"),
        ("UGRD", "300 mb"),
        ("VGRD", "300 mb"),
        # Cloud steering levels: 850 hPa steers low cloud, 700 mid, 500 high.
        # They inform the display-time motion prior only, never a reading.
        ("UGRD", "850 mb"),
        ("VGRD", "850 mb"),
        ("UGRD", "700 mb"),
        ("VGRD", "700 mb"),
        ("UGRD", "500 mb"),
        ("VGRD", "500 mb"),
        ("PWAT", "entire atmosphere (considered as a single layer)"),
    }
)

# GFS publishes the cloud fields both instantaneously ("7 hour fcst") and as a
# trailing average ("6-7 hour ave fcst"). Only the instantaneous message (or
# the analysis at f000) is wanted: mixing the two step types in one file makes
# cfgrib refuse the decode, and an average over an unstated convention is not
# the quantity the manifest declares.
_INSTANTANEOUS_FORECAST = re.compile(r"^(anl|\d+ hour fcst)$")

# Ceiling on the byte ranges fetched for one lead hour. Selected messages
# measure ~8.4 MB and the 1 MiB gap-merge brings the request to ~10.5 MB
# (measured against gfs.20260830/06 f000 and f007), so 25 MB is ample
# headroom without ever permitting a whole-file pull.
MAX_BYTES_PER_LEAD = 25 * 1024 * 1024

# GRIB shortNames decoded from the subset file, one cfgrib open per
# (shortName, extra cfgrib filter) so a single heterogeneous file (meanSea +
# heightAboveGround 2 m and 10 m + surface + cloud layers + isobaric jet
# levels + column water) never has to merge as one dataset. Each spec names
# the .idx (parameter, level) pairs that justify the open, used to skip
# messages the inventory did not carry - per level, so a missing 300 mb
# message is that level's absence, not the shortName's.
#
# The isobaric u/v open with an explicit typeOfLevel filter (the subset file
# only holds selected messages today, but the filter keeps a future selector
# widening from silently merging foreign levels) and are split by level into
# flat suffixed variables: /point sampling skips pressure-dim datasets when
# no pressure is requested, and these fields must reach /point.
GFS_DECODE_SPECS: tuple[tuple[str, dict[str, object], tuple[tuple[str, str], ...]], ...] = (
    ("prmsl", {}, (("PRMSL", "mean sea level"),)),
    ("2t", {}, (("TMP", "2 m above ground"),)),
    ("2d", {}, (("DPT", "2 m above ground"),)),
    ("2r", {}, (("RH", "2 m above ground"),)),
    ("10u", {}, (("UGRD", "10 m above ground"),)),
    ("10v", {}, (("VGRD", "10 m above ground"),)),
    ("vis", {}, (("VIS", "surface"),)),
    ("tcc", {}, (("TCDC", "entire atmosphere"),)),
    ("lcc", {}, (("LCDC", "low cloud layer"),)),
    ("mcc", {}, (("MCDC", "middle cloud layer"),)),
    ("hcc", {}, (("HCDC", "high cloud layer"),)),
    ("u", {"typeOfLevel": "isobaricInhPa"}, (("UGRD", "200 mb"), ("UGRD", "300 mb"), ("UGRD", "850 mb"), ("UGRD", "700 mb"), ("UGRD", "500 mb"))),
    ("v", {"typeOfLevel": "isobaricInhPa"}, (("VGRD", "200 mb"), ("VGRD", "300 mb"), ("VGRD", "850 mb"), ("VGRD", "700 mb"), ("VGRD", "500 mb"))),
    ("pwat", {}, (("PWAT", "entire atmosphere (considered as a single layer)"),)),
)

# The isobaric wind shortNames and the canonical prefix their split levels
# publish under; the level suffix comes from the .idx level ("200 mb" ->
# 200hPa).
_ISOBARIC_PREFIXES = {"u": "wind_u", "v": "wind_v"}

# Variables that belong to the upper_air artifact rather than surface.
UPPER_AIR_VARIABLES = ("wind_u_200hPa", "wind_v_200hPa", "wind_u_300hPa", "wind_v_300hPa")

# Only the fields this experiment actually reads off the GFS surface subset.
# ``vis``, ``tcc``, ``r2`` and the provider-declared cloud strata are declared
# optional because their presence in a given cycle depends on the product
# inventory rather than on retrieval succeeding. The strata (LCDC/MCDC/HCDC at
# the provider's low/middle/high cloud layers) are retrieved provider fields,
# not derivations. Precipitation accumulation is deliberately not declared:
# its normalized unit and interval semantics are not yet pinned for GFS, and
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
        RequiredField("cloud_low", "percent", level="low cloud layer", optional=True),
        RequiredField("cloud_middle", "percent", level="middle cloud layer", optional=True),
        RequiredField("cloud_high", "percent", level="high cloud layer", optional=True),
        # Upper-air seeing/transparency ingredients. Optional for the same
        # reason as the strata: presence depends on the product inventory for
        # a given lead, and inventory absence must degrade the run rather
        # than fabricate a value.
        RequiredField("wind_u_200hPa", "m s-1", level="200 hPa", optional=True),
        RequiredField("wind_v_200hPa", "m s-1", level="200 hPa", optional=True),
        RequiredField("wind_u_300hPa", "m s-1", level="300 hPa", optional=True),
        RequiredField("wind_v_300hPa", "m s-1", level="300 hPa", optional=True),
        # Cloud steering winds: display-derivation input only, so a cycle
        # that omits a level costs the motion prior, never the artifact.
        RequiredField("wind_u_850hPa", "m s-1", level="850 hPa", optional=True),
        RequiredField("wind_v_850hPa", "m s-1", level="850 hPa", optional=True),
        RequiredField("wind_u_700hPa", "m s-1", level="700 hPa", optional=True),
        RequiredField("wind_v_700hPa", "m s-1", level="700 hPa", optional=True),
        RequiredField("wind_u_500hPa", "m s-1", level="500 hPa", optional=True),
        RequiredField("wind_v_500hPa", "m s-1", level="500 hPa", optional=True),
        RequiredField("precipitable_water", "kg m-2", level="column", optional=True),
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
    "lcc": "cloud_low",
    "mcc": "cloud_middle",
    "hcc": "cloud_high",
    "pwat": "precipitable_water",
}


def select_gfs_ranges(idx_text: str, *, merge_gap_bytes: int = 1 << 20) -> tuple[list[ByteRange], set[str]]:
    """Resolve one sidecar to the byte ranges and the .idx params they carry.

    Selection is by exact (parameter, level) pair plus the instantaneous
    forecast filter, so only the sixteen declared messages ever qualify. The
    returned (parameter, level) pair set lets the decode loop distinguish
    "the inventory did not publish this optional message" from "we fetched it
    and could not read it" - per level, because UGRD at 10 m and UGRD at
    200 mb are different messages with different fates.
    """
    selected = [
        record
        for record in parse_idx(idx_text)
        if (record.param.upper(), record.level.lower()) in GFS_IDX_SELECTORS
        and _INSTANTANEOUS_FORECAST.match(record.forecast.strip().lower())
    ]
    pairs = {(record.param.upper(), record.level.lower()) for record in selected}
    return byte_ranges(selected, merge_gap_bytes=merge_gap_bytes), pairs


def _select_isobaric_level(array: "xarray.DataArray", level_hpa: int) -> "xarray.DataArray":
    """The single requested pressure level from a decoded isobaric message.

    Handles both shapes cfgrib produces: a real ``isobaricInhPa`` dimension
    when two levels decode together, and a scalar coordinate when only one
    did. A level that is not actually present raises rather than guessing.
    """
    for name in ("isobaricInhPa", "pressure", "level"):
        if name in array.dims:
            return array.sel({name: level_hpa})
        if name in array.coords:
            actual = float(array.coords[name].values)
            if actual != float(level_hpa):
                raise ValueError(f"decoded level {actual} hPa is not the requested {level_hpa} hPa")
            return array
    raise ValueError("no pressure coordinate on decoded isobaric message")


class NOAAS3Adapter:
    """Ingests NOAA GFS forecasts with byte-range subsetting."""

    source_id = "noaa-gfs"
    adapter_version = "noaa-gfs-v2"

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
            # ``select_gfs_ranges`` picks exactly the declared (param, level)
            # messages, so the request stays ~10.5 MB per lead.
            ranges, present_pairs = select_gfs_ranges(idx_text)
            ranges = cap_open_range(ranges)
            if not ranges:
                decode_errors.append(f"no_selected_messages:{idx_url}")
                continue

            local_grib = workdir / f"{base_filename}.subset.grib2"
            try:
                fetched_bytes = client.download_ranges(
                    grib_url,
                    local_grib,
                    [r.as_tuple() for r in ranges],
                    max_bytes=MAX_BYTES_PER_LEAD,
                )
                _log.info("GFS %s: fetched %d bytes across %d ranges", base_filename, fetched_bytes, len(ranges))
            except Exception as error:
                decode_errors.append(f"download:{base_filename}")
                _log.warning("Failed fetching GFS subset %s: %s", grib_url, error)
                local_grib.unlink(missing_ok=True)
                continue

            # The subset mixes GRIB messages on incompatible level types
            # (mean sea level, 2 m, 10 m, surface, three cloud layers, whole
            # column). One cfgrib open over all of them either refuses the
            # build outright or merges disagreeing scalar level coordinates
            # (heightAboveGround = 2 vs 10) into a MergeError. So each
            # shortName is opened on its own, its scalar message coordinates
            # are moved into attrs (strip_message_scalars), and the fields are
            # then assembled into one flat step dataset.
            step_fields: dict[str, xarray.DataArray] = {}
            for short_name, extra_filter, idx_pairs in GFS_DECODE_SPECS:
                wanted_pairs = [pair for pair in idx_pairs if pair in present_pairs]
                if not wanted_pairs:
                    # The inventory did not publish this message for this lead;
                    # manifest optionality decides what that means for the run.
                    continue
                try:
                    filter_by_keys: dict[str, Any] = {"shortName": short_name, **extra_filter}
                    decoded = open_grib(local_grib, filter_by_keys=filter_by_keys)
                    normalized = normalize_units(crop_to_bbox(decoded, self._bounds))
                    data_var_names = list(normalized.data_vars)
                    if not data_var_names:
                        raise ValueError(f"no data variable decoded for shortName {short_name}")
                    for var_name in data_var_names:
                        lowered = str(var_name).lower()
                        if lowered in _ISOBARIC_PREFIXES:
                            # Split the isobaric dimension by level into flat
                            # suffixed variables; a level the inventory did
                            # not carry stays absent for this lead.
                            for level_hpa in sorted({int(level.split()[0]) for _, level in wanted_pairs}):
                                canonical = f"{_ISOBARIC_PREFIXES[lowered]}_{level_hpa}hPa"
                                try:
                                    selected_level = _select_isobaric_level(normalized[var_name], level_hpa)
                                except Exception as error:
                                    decode_errors.append(f"decode:{base_filename}:{short_name}:{level_hpa}hPa")
                                    _log.warning(
                                        "Failed selecting GFS %s %s at %d hPa: %s",
                                        base_filename, short_name, level_hpa, error,
                                    )
                                    continue
                                # ``load`` materialises before the finally-unlink below.
                                step_fields[canonical] = strip_message_scalars(selected_level.load())
                            continue
                        canonical = GFS_VAR_MAP.get(lowered)
                        if canonical is None:
                            continue
                        # ``load`` materialises before the finally-unlink below.
                        step_fields[canonical] = strip_message_scalars(normalized[var_name].load())
                except Exception as error:
                    decode_errors.append(f"decode:{base_filename}:{short_name}")
                    _log.warning("Failed decoding GFS %s message %s: %s", base_filename, short_name, error)

            local_grib.unlink(missing_ok=True)

            if not step_fields:
                decode_errors.append(f"empty_step:{base_filename}")
                continue

            step_ds = xarray.Dataset(step_fields).expand_dims(
                valid_time=[numpy.datetime64(valid_time.replace(tzinfo=None), "ns")]
            )
            hourly_datasets.append(step_ds)

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

        # The run is validated as one dataset, then written as two artifacts:
        # the surface set (which includes the column total precipitable
        # water) and the jet-level winds as ``upper_air``. The upper_air
        # artifact simply does not exist when no isobaric message decoded -
        # absence over an empty shell.
        surface_names = [str(name) for name in combined.data_vars if str(name) not in UPPER_AIR_VARIABLES]
        upper_names = [str(name) for name in combined.data_vars if str(name) in UPPER_AIR_VARIABLES]

        artifacts: list[Artifact] = []
        zarr_path = workdir / "noaa_gfs.zarr.zip"
        write_zarr(combined[surface_names], zarr_path)
        artifacts.append(
            Artifact(
                logical_name="surface",
                media_type=MEDIA_ZARR,
                payload_path=zarr_path,
                provenance=provenance,
            )
        )
        if upper_names:
            upper_path = workdir / "noaa_gfs_upper_air.zarr.zip"
            write_zarr(combined[upper_names], upper_path)
            artifacts.append(
                Artifact(
                    logical_name="upper_air",
                    media_type=MEDIA_ZARR,
                    payload_path=upper_path,
                    provenance={**provenance, "vertical_levels": "200/300 hPa isobaric"},
                )
            )

        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=run_dt,
            retrieved_at=retrieved_at,
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=artifacts,
            native_crs="EPSG:4326",
            notes=f"Retrieved {len(hourly_datasets)} GFS lead steps via .idx byte ranges; {validation.detail}",
        )


GFS_ADAPTER = register(NOAAS3Adapter())
