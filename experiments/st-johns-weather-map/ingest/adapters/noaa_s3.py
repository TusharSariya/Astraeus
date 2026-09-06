"""NOAA GFS S3 adapter with .idx byte-range subsetting.

Fetches global forecast data from the NOAA Open Data S3 bucket (noaa-gfs-bdp-pds).
Uses .idx sidecars to request strictly target variables via HTTP byte ranges
(measured ~8.4 MB of selected messages, ~10.5 MB after gap-merging, per lead
hour vs 450+ MB whole file), keeping well within the per-lead ceiling.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
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
    GFS_RH_PHASE_BASIS,
    RH_PHASE_MIXED_LINEAR_253K_273K,
    ByteRange,
    GribError,
    byte_ranges,
    cap_open_range,
    crop_to_bbox,
    declare_rh_phase,
    declare_time_average,
    normalize_units,
    open_grib,
    parse_idx,
    stack_members,
    strip_message_scalars,
    write_zarr,
)
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, required_leads, validate_run
from ingest.registry import EnsembleDeclaration, get_config, register
from registry import fields as catalogue

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
        # Vertical velocity at the same three levels: omega, d(pressure)/dt,
        # so negative is ascent. It tells the computed-residual
        # interpolation methods WHEN inside an interval the model made or
        # destroyed cloud. Display derivation only, never a reading. Verified
        # in the real .idx (gfs.20260831/00 f006): `VVEL:850 mb` and the same
        # at 700 and 500. GFS also publishes `DZDT` (geometric vertical
        # velocity, m s-1) at every one of these levels; it is deliberately
        # NOT taken - omega is the quantity whose sign follows directly from
        # the pressure coordinate, and mixing the two conventions is how a
        # sign error would get in.
        ("VVEL", "850 mb"),
        ("VVEL", "700 mb"),
        ("VVEL", "500 mb"),
        # Relative humidity and temperature on the same three levels: the
        # profile a humidity-based low-cloud diagnosis reads. Verified in the
        # real .idx (gfs.20260901/06 f003): `RH:850 mb`, `TMP:850 mb` and the
        # same at 700 and 500. Display derivation only, never a reading.
        ("RH", "850 mb"),
        ("RH", "700 mb"),
        ("RH", "500 mb"),
        ("TMP", "850 mb"),
        ("TMP", "700 mb"),
        ("TMP", "500 mb"),
        ("PWAT", "entire atmosphere (considered as a single layer)"),
    }
)

# GFS publishes the cloud fields both instantaneously ("7 hour fcst") and as a
# trailing average ("6-7 hour ave fcst"). Only the instantaneous message (or
# the analysis at f000) is wanted: mixing the two step types in one file makes
# cfgrib refuse the decode, and an average over an unstated convention is not
# the quantity the manifest declares.
_INSTANTANEOUS_FORECAST = re.compile(r"^(anl|\d+ hour fcst)$")

# Ceiling on the byte ranges fetched for one lead hour. It exists to stop a
# careless selector turning into a whole-file pull: one f003 pgrb2.0p25 file
# is 521 MiB.
#
# RE-MEASURED 2026-09-01, and the previous comment here was badly out of date.
# It claimed ~10.5 MB per lead "measured against gfs.20260830/06 f000 and
# f007". Against the live sidecars the selector set BEFORE this change already
# requested 19.1-21.8 MiB per lead - i.e. it had been sitting inside 15% of
# the 25 MiB ceiling, not at 40% of it. Adding the six isobaric RH/TMP
# messages adds ~4.6 MiB and takes the request to:
#
#   gfs.20260901/06  f000 23.73  f001 25.09  f003 25.37  f006 26.32
#                    f012 25.66  f024 26.11   MiB
#   gfs.20260831/18  f003 26.45 MiB
#
# Four of those seven leads exceed 25 MiB, so keeping the old ceiling would
# have failed the whole run closed on most leads - exactly the failure this
# constant was introduced to catch, arriving from the ceiling being stale
# rather than from the selector being careless. The ceiling is therefore
# raised to 40 MiB: ~1.5x the largest measured request, and still ~13x below
# a whole-file pull, so it remains a real guard.
MAX_BYTES_PER_LEAD = 40 * 1024 * 1024

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
    ("w", {"typeOfLevel": "isobaricInhPa"}, (("VVEL", "850 mb"), ("VVEL", "700 mb"), ("VVEL", "500 mb"))),
    # The explicit ``typeOfLevel`` filter is load-bearing on these two, more so
    # than on u/v/w: GFS publishes `t` at 2 m above ground and `r` at 2 m above
    # ground as well, and both are already selected above. Without the filter a
    # single cfgrib open on shortName `t` would try to merge the isobaric
    # messages with the screen-level one on incompatible level coordinates.
    ("r", {"typeOfLevel": "isobaricInhPa"}, (("RH", "850 mb"), ("RH", "700 mb"), ("RH", "500 mb"))),
    ("t", {"typeOfLevel": "isobaricInhPa"}, (("TMP", "850 mb"), ("TMP", "700 mb"), ("TMP", "500 mb"))),
    ("pwat", {}, (("PWAT", "entire atmosphere (considered as a single layer)"),)),
)

# The isobaric shortNames and the canonical prefix their split levels publish
# under; the level suffix comes from the .idx level ("200 mb" -> 200hPa).
# `w` is VVEL, vertical velocity on pressure surfaces (ecCodes paramId 135,
# Pa s-1), not DZDT.
# ``r`` and ``t`` split to `relative_humidity_700hPa` / `temperature_700hPa`,
# which do not collide with the screen-level `relative_humidity_2m` /
# `temperature_2m` those same shortNames' 2 m messages publish under (`2r`,
# `2t` in GFS_VAR_MAP - cfgrib gives the screen fields distinct shortNames).
_ISOBARIC_PREFIXES = {"u": "wind_u", "v": "wind_v", "w": "omega", "r": "relative_humidity", "t": "temperature"}

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
        RequiredField("total_cloud_geometric", "percent", level="column", optional=True),
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
        # Vertical velocity at the steering levels: display-derivation input
        # only (the development residual), so a cycle that omits a level costs
        # that re-timing, never the artifact.
        RequiredField("omega_850hPa", "Pa s-1", level="850 hPa", optional=True),
        RequiredField("omega_700hPa", "Pa s-1", level="700 hPa", optional=True),
        RequiredField("omega_500hPa", "Pa s-1", level="500 hPa", optional=True),
        # Humidity and temperature on the steering levels: the profile a
        # humidity-based low-cloud diagnosis reads. Optional for the same
        # reason the winds are - a level the inventory omits must cost the
        # diagnosis, never the artifact.
        #
        # NOTE for anyone thresholding these: GFS RH below freezing is NOT the
        # same quantity as ECCC RH. Measured 2026-09-01 (see
        # ``ingest.grib.GFS_RH_PHASE_BASIS``), GFS divides by a mixed-phase
        # saturation that ramps linearly from ice at 253.16 K to water at
        # 273.16 K, while HRDPS and RDPS divide by liquid water at every
        # temperature. At -25 degC the same air reads ~24 % higher here.
        RequiredField("relative_humidity_850hPa", "percent", level="850 hPa", optional=True),
        RequiredField("relative_humidity_700hPa", "percent", level="700 hPa", optional=True),
        RequiredField("relative_humidity_500hPa", "percent", level="500 hPa", optional=True),
        RequiredField("temperature_850hPa", "degC", level="850 hPa", optional=True),
        RequiredField("temperature_700hPa", "degC", level="700 hPa", optional=True),
        RequiredField("temperature_500hPa", "degC", level="500 hPa", optional=True),
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
    "tcc": "total_cloud_geometric",
    "lcc": "cloud_low",
    "mcc": "cloud_middle",
    "hcc": "cloud_high",
    "pwat": "precipitable_water",
}


def select_gfs_ranges(idx_text: str, *, merge_gap_bytes: int = 1 << 20) -> tuple[list[ByteRange], set[str]]:
    """Resolve one sidecar to the byte ranges and the .idx params they carry.

    Selection is by exact (parameter, level) pair plus the instantaneous
    forecast filter, so only the declared messages ever qualify. The
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
            # messages, so the request stays ~24-27 MiB per lead (measured
            # 2026-09-01; see MAX_BYTES_PER_LEAD).
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
                                field = strip_message_scalars(selected_level.load())
                                if canonical.startswith("relative_humidity_"):
                                    field = declare_rh_phase(
                                        field,
                                        convention=RH_PHASE_MIXED_LINEAR_253K_273K,
                                        basis=GFS_RH_PHASE_BASIS,
                                    )
                                step_fields[canonical] = field
                            continue
                        canonical = GFS_VAR_MAP.get(lowered)
                        if canonical is None:
                            continue
                        # ``load`` materialises before the finally-unlink below.
                        surface_field = strip_message_scalars(normalized[var_name].load())
                        # The screen humidity needs the same measured phase
                        # stamp as the isobaric levels above: it is the same
                        # mixed-phase saturation, and the catalogue refuses a
                        # humidity that cannot say which one it is.
                        if canonical.startswith("relative_humidity_"):
                            surface_field = declare_rh_phase(
                                surface_field,
                                convention=RH_PHASE_MIXED_LINEAR_253K_273K,
                                basis=GFS_RH_PHASE_BASIS,
                            )
                        step_fields[canonical] = surface_field
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
            # Both artifacts below are GFS's own published cells, so the one
            # declaration covers the surface set and the jet-level winds.
            **manifest.as_manifest_block(),
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


# ---------------------------------------------------------------------------
# GEFS: the fourth access shape - one file per member, byte ranges per member
# ---------------------------------------------------------------------------
#
# The same .idx-and-Range mechanism as GFS above, repeated across 31 member
# files: `gec00` (the control) and `gep01`..`gep30`, each with its own sidecar.
# GEFS cannot subset server side, so a range buys a whole global record and the
# evidence box is cut locally, exactly as for GFS - which is why the storage
# scope is `family_fields_only` and only the seven catalogue-family fields are
# ever requested. Every other record the sidecar advertises is recorded as
# available-not-stored rather than silently dropped.

NOAA_GEFS_S3_BASE = "https://noaa-gefs-pds.s3.amazonaws.com"

#: The three product sets GEFS publishes, and only these three. The family
#: fields all live in `pgrb2ap5`, the 0.5 degree primary set.
GEFS_PRIMARY_SET = "pgrb2ap5"

#: ``TCDC:entire atmosphere`` is a time average at every lead in every GEFS
#: product set - `0-3 hour ave fcst` at f003, `18-24` at f024 - confirmed at
#: the GRIB2 level, not only from the label. So it is stored under the
#: six-hour-mean key and never under the instantaneous one, and the window is
#: read from the producer's own record.
GEFS_AVERAGED_CLOUD_PARAM = ("TCDC", "entire atmosphere")


def _gefs_upstream_names(source_id: str = "noaa-gefs") -> dict[tuple[str, str], str]:
    """``(param, level) -> the catalogue's own upstream name`` for stored fields.

    The catalogue names GEFS records as ``PARAM:level``, with the averaged cloud
    carrying its window in the name (``TCDC:entire atmosphere (n-n+6 hour ave
    fcst)``). This maps a sidecar's own two tokens onto those names so the
    storage scope is applied against the catalogue's vocabulary rather than
    against a string this adapter invented.
    """
    names: dict[tuple[str, str], str] = {}
    for item in catalogue.source_mapping(source_id):
        if item.storage != "stored" or not item.upstream:
            continue
        param, _, level = item.upstream.partition(":")
        # Strip a parenthesised window qualifier: the sidecar states the window
        # in its forecast-hour token, not in the record's level.
        level = level.split(" (")[0].strip()
        names[(param.strip().upper(), level.lower())] = item.upstream
    return names


def _gefs_keys_by_upstream(source_id: str = "noaa-gefs") -> dict[str, str]:
    return {
        item.upstream: item.key
        for item in catalogue.source_mapping(source_id)
        if item.storage == "stored" and item.upstream
    }


@dataclass(frozen=True)
class GEFSSelection:
    """What one member's sidecar offered and what of it is wanted."""

    #: ``(byte range, catalogue upstream name, the record's forecast label)``.
    wanted: tuple[tuple[ByteRange, str, str], ...]
    #: Every record the sidecar advertised, as ``PARAM:level``, deduplicated.
    published: tuple[str, ...]


def select_gefs_member_records(idx_text: str, *, source_id: str = "noaa-gefs") -> GEFSSelection:
    """Restrict one member's sidecar to the catalogue-family fields.

    Selection is by exact ``(param, level)`` pair, as for GFS: matching a
    parameter alone would pull TCDC at every isobaric level and turn a
    seven-record request into most of the file. Everything the sidecar
    advertises is still reported, because the ``family_fields_only`` scope has
    to name what it left behind.
    """
    upstream_by_pair = _gefs_upstream_names(source_id)
    wanted: list[tuple[ByteRange, str, str]] = []
    published: list[str] = []
    records = parse_idx(idx_text)
    for position, record in enumerate(records):
        pair = (record.param.upper(), record.level.lower())
        name = f"{record.param.upper()}:{record.level.lower()}"
        if name not in published:
            published.append(name)
        upstream = upstream_by_pair.get(pair)
        if upstream is None:
            continue
        ranges = byte_ranges([record], merge_gap_bytes=0)
        if not ranges:
            continue
        wanted.append((ranges[0], upstream, record.forecast.strip()))
    return GEFSSelection(wanted=tuple(wanted), published=tuple(published))


def gefs_member_identifiers(declaration: "EnsembleDeclaration") -> tuple[str, ...]:
    """``gec00`` then ``gep01``..``gep30`` - NOAA's own member file names.

    Built from the declared count and the declared control identifier, never
    from a literal 31: the count is a registry fact and an adapter that restated
    it could disagree with the record completeness is judged against.
    """
    if declaration.member_count is None:
        raise ValueError(
            "noaa-gefs: the registry declares no member count, so the member set cannot be "
            "enumerated and no member file is addressed"
        )
    control = None if declaration.control is None else declaration.control.identifier
    perturbed = declaration.member_count - (1 if control else 0)
    return ((control,) if control else ()) + tuple(f"gep{index:02d}" for index in range(1, perturbed + 1))


def _gefs_refusing_reader(path: Path, *, upstream: str, member: str, bounds: Mapping[str, float]) -> Any:
    """Decode one member's record, cropping the global field to the box locally."""
    from ingest.grib import open_grib  # noqa: PLC0415

    param = upstream.split(":", 1)[0].lower()
    decoded = open_grib(path, filter_by_keys={"shortName": param})
    normalized = normalize_units(crop_to_bbox(decoded, bounds))
    names = [str(name) for name in normalized.data_vars]
    if not names:
        raise ValueError(f"no data variable decoded for {upstream} of member {member}")
    return strip_message_scalars(normalized[names[0]].load())


#: The one field a GEFS run is not worth publishing without. The averaged cloud
#: is optional on purpose: a lead whose record states no window is not stored,
#: and that must cost the field rather than the run.
_GEFS_MANDATORY_KEY = "temperature_2m"

#: Ceiling on one member's one-record range. The largest family record measured
#: is ``RH:850 mb`` at 247 106 bytes and the averaged cloud at 174 309
#: (2026-09-02); 4 MiB is far above either and far below the 15 MB member file.
MAX_GEFS_MEMBER_BYTES = 4 * 1024 * 1024


class NOAAGEFSEnsembleAdapter:
    """GEFS members: one file per member, byte ranges from each member's .idx."""

    source_id = "noaa-gefs"
    adapter_version = "noaa-gefs-ensemble-v1"

    def __init__(
        self,
        *,
        base_url: str = NOAA_GEFS_S3_BASE,
        bounds: Mapping[str, float] = ATLANTIC_CONTEXT_BOUNDS,
        client: PoliteClient | None = None,
        reader: Any = _gefs_refusing_reader,
        product_set: str = GEFS_PRIMARY_SET,
    ) -> None:
        self._base_url = base_url
        self._bounds = dict(bounds)
        self._client = client
        self._reader = reader
        self._product_set = product_set

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def declaration(self) -> "EnsembleDeclaration":
        declaration = get_config(self.source_id).ensemble
        if declaration is None:
            raise AdapterUnavailable(
                f"{self.source_id}: the registry record declares no ensemble block, so the member "
                "count, control rule and storage scope are unstated and nothing is retrieved"
            )
        return declaration

    def manifest(self) -> RunManifest:
        declaration = self.declaration()
        control = declaration.control
        return RunManifest(
            source_id=self.source_id,
            fields=tuple(
                RequiredField(
                    key,
                    catalogue.resolve(key).field.units or "",
                    optional=key != _GEFS_MANDATORY_KEY,
                )
                for key in _gefs_keys_by_upstream(self.source_id).values()
            ),
            member_count=declaration.member_count,
            control=None if control is None else control.identifier,
            storage_scope=declaration.storage_scope,
        )

    def _gate(self) -> "EnsembleDeclaration":
        declaration = self.declaration()
        if not declaration.schedulable:
            raise AdapterUnavailable(
                f"{self.source_id}: the registry declares {declaration.family} not schedulable. "
                f"{declaration.schedulable_reason}"
            )
        return declaration

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        self._gate()
        raise AdapterUnavailable(
            f"{self.source_id}: nothing is scheduled for GEFS by this change; the member run "
            "discovery lands with the owner's acceptance of the upstream cost"
        )

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        self._gate()
        return self.assemble(candidate, window, workdir)

    def member_url(self, candidate: RunCandidate, member: str) -> str:
        date_str = str(candidate.detail.get("date_str", ""))
        cycle = str(candidate.detail.get("cycle", ""))
        lead = int(candidate.detail.get("lead_hours", 0))
        return (
            f"{self._base_url}/gefs.{date_str}/{cycle}/atmos/{self._product_set}/"
            f"{member}.t{cycle}z.{self._product_set}.f{lead:03d}"
        )

    def assemble(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        declaration = self.declaration()
        members = gefs_member_identifiers(declaration)
        control = None if declaration.control is None else declaration.control.identifier
        keys_by_upstream = _gefs_keys_by_upstream(self.source_id)
        client = self._get_client()
        retrieved_at = datetime.now(UTC)

        fields: dict[str, dict[str, Any]] = {}
        published_names: list[str] = []
        retrieved_names: list[str] = []
        decode_errors: list[str] = []
        unstorable: list[str] = []

        for member in members:
            grib_url = self.member_url(candidate, member)
            try:
                idx_text = client.get_text(f"{grib_url}.idx")
            except Exception as error:
                decode_errors.append(f"idx:{member}")
                _log.warning("GEFS member %s sidecar unavailable: %s", member, error)
                continue

            selection = select_gefs_member_records(idx_text, source_id=self.source_id)
            for name in selection.published:
                if name not in published_names:
                    published_names.append(name)

            for byte_range, upstream, label in selection.wanted:
                local = workdir / f"{member}.{upstream.replace(':', '_').replace(' ', '_')}.grib2"
                try:
                    client.download_ranges(
                        grib_url, local, [byte_range.as_tuple()], max_bytes=MAX_GEFS_MEMBER_BYTES
                    )
                    field = self._reader(local, upstream=upstream, member=member, bounds=self._bounds)
                except Exception as error:
                    decode_errors.append(f"member:{member}:{upstream}")
                    _log.warning("GEFS member %s record %s failed: %s", member, upstream, error)
                    continue
                finally:
                    local.unlink(missing_ok=True)

                if keys_by_upstream.get(upstream) == "relative_humidity_2m":
                    # GEFS divides by a mixed-phase saturation ramping from ice
                    # at 253.16 K, so at -25 degC it reads about 24 % higher
                    # than the liquid-basis ECCC humidity. An unstamped humidity
                    # is a QC failure, not a gap: a threshold calibrated on one
                    # convention is not valid on the other.
                    field = declare_rh_phase(
                        field,
                        convention=RH_PHASE_MIXED_LINEAR_253K_273K,
                        basis=GFS_RH_PHASE_BASIS,
                    )

                if keys_by_upstream.get(upstream) == "total_cloud_mean_6h":
                    # The window is the producer's own record label, never the
                    # lead. A record whose label states no window is not a mean
                    # anyone can weigh, so it is not stored at all.
                    try:
                        field = declare_time_average(field, window_label=label)
                    except GribError as error:
                        unstorable.append(f"{member}:{upstream}:{label}")
                        _log.warning("GEFS averaged cloud not stored for %s: %s", member, error)
                        continue

                fields.setdefault(member, {})[upstream] = field
                if upstream not in retrieved_names:
                    retrieved_names.append(upstream)

        if not fields:
            raise AdapterUnavailable(
                f"{self.source_id}: no member decoded for {candidate.provider_run_id}; an ensemble "
                "artifact with no members is an absent ensemble, not a thin one"
            )

        stacked: dict[str, Any] = {}
        for upstream, key in keys_by_upstream.items():
            by_member = {
                member: by_name[upstream]
                for member, by_name in sorted(fields.items())
                if upstream in by_name
            }
            if by_member:
                stacked[key] = stack_members(by_member, control=control)

        dataset = xarray.Dataset(stacked)
        manifest = self.manifest()
        validation = validate_run(
            manifest,
            dataset,
            window=window,
            decode_errors=decode_errors,
            upstream_fields=published_names,
            retrieved_fields=retrieved_names,
            declared_members=members,
            control_retrieval=_gefs_control_retrieval(declaration),
        )

        provenance = {
            "source_id": self.source_id,
            "producer": "NOAA / NCEP",
            "product": f"Global Ensemble Forecast System ({self._product_set})",
            "family": declaration.family,
            "adapter_version": self.adapter_version,
            "subsetting": declaration.subsetting,
            "bounds": dict(self._bounds),
            "unstorable_fields": unstorable,
            "quality": validation.as_quality(),
            "coverage": validation.as_coverage(),
            "members": validation.as_members(),
            "storage_scope": validation.as_storage_scope(),
            **manifest.as_manifest_block(),
        }

        payload_path = workdir / "noaa_gefs_members.zarr.zip"
        write_zarr(dataset, payload_path)
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time,
            retrieved_at=retrieved_at,
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[
                Artifact(
                    logical_name="members",
                    media_type=MEDIA_ZARR,
                    payload_path=payload_path,
                    provenance=provenance,
                )
            ],
            native_crs="EPSG:4326",
            notes=f"GEFS members via per-member .idx byte ranges; {validation.detail}",
        )


def _gefs_control_retrieval(declaration: "EnsembleDeclaration") -> str | None:
    """``separate_file``: GEFS' control is its own S3 object, ``gec00``.

    Deliberately not read off ``control.separate_retrieval``, which the registry
    declares **false** for GEFS. The two record different things and only one of
    them is the access shape ``validate_run`` asks for. The registry's flag says
    the control needs no retrieval step the perturbed members do not - true,
    because every GEFS member is already its own file. ``control_retrieval``
    says which file the control was in, and for GEFS that is emphatically not
    the members' file: the declaration's own rule says ``gec00`` sits beside
    ``gep01`` through ``gep30`` as a separate object. Mapping the flag straight
    onto ``same_file`` would have written into provenance that the control rode
    in the member file, which is false for this family.

    ``None`` where no control identifier is declared, which is what nulls the
    field for a family whose control was never located.
    """
    control = declaration.control
    if control is None or control.identifier is None:
        return None
    return "separate_file"


GEFS_ENSEMBLE_ADAPTER = register(NOAAGEFSEnsembleAdapter())
