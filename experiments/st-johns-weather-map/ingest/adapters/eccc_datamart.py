"""ECCC Datamart NWP model adapters (HRDPS, RDPS, GDPS).

Walks the Apache autoindex on dd.weather.gc.ca, retrieves single-parameter GRIB2
files for the Avalon domain, decodes with cfgrib/ecCodes, crops to bounds,
normalizes units, and packages into zipped Zarr artifacts.

Two discovery facts, verified live on 2026-08-30, shape this module:

* ``dd.weather.gc.ca/today/model_hrdps/`` is empty and its ``continental/2.5km``
  child is a 404. The working layout is the dated one,
  ``/{YYYYMMDD}/WXO-DD/{model}/{HH}/{FFF}/``. The dated directory rolls at 00Z
  and is empty for the first hours of the UTC day, so discovery tries today and
  then falls back to yesterday. Neither the ``today`` alias nor a single date
  can find a run at 02:30Z.
* The run identity is stamped in the filename
  (``20260829T18Z_MSC_HRDPS_TMP_AGL-2m_...``). Deriving it from ``window.now``
  instead — as this adapter used to — mislabels every run fetched after 00Z from
  the previous day's directory.

WHAT THE LOW-LEVEL PROFILE COSTS (measured, not estimated)
----------------------------------------------------------
``LOW_LEVELS_HPA`` adds 28 single-parameter GRIB2 files per lead hour to each
ECCC model (9 levels x RH/T/height, plus one surface datum). Measured on
2026-09-01 by fetching the 12Z PT003H set for both models and running them
through this adapter's own ``open_grib`` -> ``crop_to_bbox`` ->
``normalize_units`` -> ``write_zarr`` path at ``AVALON_CORE_BOUNDS``:

===========================  ===========  ==========
per lead hour                HRDPS        RDPS
===========================  ===========  ==========
files added                  28           28
bytes downloaded             59 330 113   20 625 348
largest single file          4 326 678    1 133 025
cropped grid                 148 x 149    35 x 36
added zipped-Zarr bytes      1 285 189    150 833
decode + crop wall time      10.1 s       3.3 s
===========================  ===========  ==========

Every file is well under the 10 MiB per-file cap ``fetch`` passes to
``PoliteClient.download``. Over the 25 lead hours a cycle retrieves that is
~1.38 GiB downloaded and ~30.6 MiB of added artifact for HRDPS, ~492 MiB
downloaded and ~3.6 MiB added for RDPS - about 34 MiB per pair of runs against
the 25 GiB retention cap, and ~5.5 minutes of added decode time per HRDPS run
on this machine. The download is the cost, not the storage.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy
import xarray

from ingest.contract import (
    ATLANTIC_CONTEXT_BOUNDS,
    AVALON_CORE_BOUNDS,
    MEDIA_ZARR,
    Adapter,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import (
    ECCC_RH_PHASE_BASIS,
    RH_PHASE_LIQUID_WATER,
    WMO_IDENTITY_READ_KEYS,
    crop_to_bbox,
    declare_rh_phase,
    declare_wmo_total_cloud,
    normalize_units,
    open_grib,
    strip_message_scalars,
    write_zarr,
)
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, required_leads, validate_run
from ingest.registry import register

UTC = timezone.utc
_log = logging.getLogger(__name__)

ECCC_DATAMART_BASE = "https://dd.weather.gc.ca"
DATED_PATH_SEGMENT = "WXO-DD"

# 20260829T18Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2
_FILE_RUN_STAMP = re.compile(r"(?P<date>\d{8})T(?P<hour>\d{2})Z")
_CYCLE_DIR = re.compile(r"^\d{2}/?$")
_LEAD_DIR = re.compile(r"^\d{3}/?$")

# ``total_cloud_opacity`` is published from the message's own WMO keys, not
# from ecCodes' concept files.
#
# The key says opacity because the quantity is opacity-weighted: ECCC GEM's
# total cloud weights each layer by how much light it actually stops, so thin
# cirrus reads near zero. GFS publishes a geometric maximum-random overlap
# fraction under the same English words, which is why they are two catalogue
# keys and not one (registry.fields, family cloud_cover).
#
# MSC publishes it (HRDPS ``TCDC_Sfc``, RDPS ``TotalCloudCover_Sfc``) and the
# files download fine, but the message decodes with ``paramId=0`` and
# ``shortName``, ``name``, ``cfVarName`` and ``units`` all literally
# ``'unknown'``. Verified live on 2026-08-30 against the 12Z PT006H files
# with ecCodes 2.48.0 (the ``eccodeslib`` wheel this worker image now uses;
# the earlier blame on the Debian 2.28.0 package was wrong about the cause):
#
#   centre=cwao, tablesVersion=4, localTablesVersion=1, template 4.0,
#   discipline=0, parameterCategory=6, parameterNumber=1
#   (WMO code table 4.2: "Total cloud cover", %),
#   typeOfFirstFixedSurface=1 (sfc), typeOfSecondFixedSurface=255.
#
# ecCodes' ``grib2/shortName.def`` concept ``tcc`` matches 0/6/1 only with
# ``typeOfSecondFixedSurface=8`` (top of atmosphere, i.e. a whole-column
# quantity); CWAO stamps 255 (missing), and ecCodes ships no
# ``localConcepts/cwao`` that would say otherwise. Setting the second surface
# to 8 on an otherwise identical message makes 2.48.0 name it ``tcc`` /
# ``%``, so the gap is a definitions mismatch, not a library age. The field
# was withheld until the owner decided how to declare its units; the owner's
# decision (2026-08-31) is to publish from the coded WMO 0/6/1 keys - which
# are retrieved facts in the message itself, unlike the 0.0-100.0 value range,
# which is only an inference. ``ingest.grib.declare_wmo_total_cloud`` performs
# exactly that declaration and records its basis in the variable's attrs; a
# message whose coded keys do not match is still refused, never ranged-guessed.

# Steering levels for cloud motion: 850 hPa for low cloud, 700 for mid, 500
# for high. A 10 m wind is not a steering wind - it is friction-slowed and
# veered - so the motion prior needs the isobaric levels, and only these
# three. Verified present in the Datamart listing for both models
# (2026-08-31): HRDPS names them `UGRD_ISBL_0850`, RDPS `WindU_IsbL-0850`.
STEERING_LEVELS_HPA = (850, 700, 500)


def _steering_vars(u_prefix: str, v_prefix: str, token: str) -> dict[str, tuple[str, str]]:
    """`wind_u_850hPa -> (prefix, level token)` for each steering level."""
    entries: dict[str, tuple[str, str]] = {}
    for level in STEERING_LEVELS_HPA:
        entries[f"wind_u_{level}hPa"] = (u_prefix, token.format(level=level))
        entries[f"wind_v_{level}hPa"] = (v_prefix, token.format(level=level))
    return entries


HRDPS_STEERING_VARS = _steering_vars("UGRD", "VGRD", "ISBL_{level:04d}")
RDPS_STEERING_VARS = _steering_vars("WindU", "WindV", "IsbL-{level:04d}")


def _omega_vars(prefix: str, token: str) -> dict[str, tuple[str, str]]:
    """`omega_850hPa -> (prefix, level token)` for each steering level.

    Vertical velocity on pressure surfaces - omega, d(pressure)/dt, so
    negative is ascent. It informs the computed-residual interpolation
    methods, which re-time growth and decay by where the model says air is
    rising or sinking; it never reaches a reading. Verified present in the Datamart
    listing for both models (2026-09-01): HRDPS publishes
    `VVEL_ISBL_0850/0700/0500`, RDPS `VerticalVelocity_IsbL-0850/0700/0500`.
    One HRDPS message was decoded to confirm the identity rather than trust
    the filename: WMO discipline 0, parameterCategory 2, parameterNumber 8 on
    typeOfFirstFixedSurface 100, which ecCodes 2.48.0 names `w`, paramId 135,
    units `Pa s**-1`.
    """
    return {f"omega_{level}hPa": (prefix, token.format(level=level)) for level in STEERING_LEVELS_HPA}


HRDPS_OMEGA_VARS = _omega_vars("VVEL", "ISBL_{level:04d}")
RDPS_OMEGA_VARS = _omega_vars("VerticalVelocity", "IsbL-{level:04d}")


def _thermo_vars(rh_prefix: str, temp_prefix: str, token: str) -> dict[str, tuple[str, str]]:
    """`relative_humidity_850hPa` / `temperature_850hPa` for each steering level.

    Relative humidity and temperature on the same three pressure surfaces the
    winds and omega already use. They feed the humidity-based low-cloud
    diagnosis (`ingest.derive.weong_low_cloud`), which exists because ECCC's
    own WEonG technical note (v2.4.1, 2025-06-23, section 7.9) documents that
    HRDPS's published NT under-reports low cloud and repairs it from the RH
    profile. Display derivation only; never a reading.

    Tokens verified present in the live Datamart listing for both models on
    2026-09-01 (12Z, PT003H): HRDPS publishes `RH_ISBL_0850/0700/0500` and
    `TMP_ISBL_0850/0700/0500`; RDPS publishes
    `RelativeHumidity_IsbL-0850/0700/0500` and `AirTemp_IsbL-0850/0700/0500`.
    Note RDPS names temperature `AirTemp`, not `Temperature`, matching its own
    surface naming.

    Four messages were decoded rather than trusting the filenames (HRDPS and
    RDPS, RH and temperature, 700 hPa, ecCodes 2.48.0). All four carry
    centre=cwao, tablesVersion=4, template 4.0, typeOfFirstFixedSurface=100
    (`pl`), level=700, stepType=instant. RH decodes as discipline 0 /
    parameterCategory 1 / parameterNumber 1 -> shortName `r`, paramId 157,
    units `%`; temperature as 0/0/0 -> shortName `t`, paramId 130, units `K`.
    Unlike `TCDC_Sfc`, none of these decode as `unknown`, so no WMO-key
    declaration is needed - only the unit normalisation the adapter already
    applies.

    What the coded keys do NOT say is which saturation the RH was divided by;
    GRIB2 0/1/1 has no phase key. That was measured instead - see
    ``ingest.grib.ECCC_RH_PHASE_BASIS`` - and both ECCC models turn out to use
    saturation over LIQUID WATER at every temperature, which is what the
    WEonG thresholds below are calibrated against. The convention is stamped
    into each variable's attrs on retrieval.
    """
    entries: dict[str, tuple[str, str]] = {}
    for level in STEERING_LEVELS_HPA:
        entries[f"relative_humidity_{level}hPa"] = (rh_prefix, token.format(level=level))
        entries[f"temperature_{level}hPa"] = (temp_prefix, token.format(level=level))
    return entries


HRDPS_THERMO_VARS = _thermo_vars("RH", "TMP", "ISBL_{level:04d}")
RDPS_THERMO_VARS = _thermo_vars("RelativeHumidity", "AirTemp", "IsbL-{level:04d}")

# The nine lowest isobaric levels both ECCC models publish, ascending in
# height (descending in pressure). Verified present in the live Datamart
# listing for both models on 2026-09-01 (12Z, PT003H): HRDPS publishes
# `RH_ISBL_`, `TMP_ISBL_` and `HGT_ISBL_` at every one of them, RDPS
# `RelativeHumidity_IsbL-`, `AirTemp_IsbL-` and `GeopotentialHeight_IsbL-`.
#
# This is the profile the WEonG low-cloud diagnosis needs and the three
# steering levels cannot give it. ECCC's technote (v2.4.1 sec 7.9) requires a
# saturated layer with a base under 2000 m AGL and a thickness of at least
# 150 m; on 850/700/500 hPa only 850 lies inside that window at all, and one
# level has zero thickness, so the diagnosis can never fire. Nine levels
# between 1015 and 850 hPa span roughly the surface to ~1.5 km AGL over the
# Avalon at 100-200 m spacing, which is where marine stratus and advection
# fog actually sit.
LOW_LEVELS_HPA = (1015, 1000, 985, 970, 950, 925, 900, 875, 850)


def _profile_vars(rh_prefix: str, temp_prefix: str, height_prefix: str, token: str) -> dict[str, tuple[str, str]]:
    """RH, temperature and geopotential height at each of ``LOW_LEVELS_HPA``.

    Follows ``_thermo_vars``' shape, and adds the height that turns a pressure
    profile into the height-AGL profile the WEonG algorithm is written
    against. Display derivation only; never a reading.

    Three messages per model were decoded rather than trusting the filenames
    (950 hPa, 2026-09-01 12Z PT003H, ecCodes 2.48.0). All six carry
    ``typeOfFirstFixedSurface=pl`` (100), ``typeOfSecondFixedSurface=255``,
    ``stepType=instant``, and identical coded identities across the two
    models:

    * relative humidity - discipline 0, parameterCategory 1, parameterNumber 1
      -> shortName ``r``, paramId 157, units ``%``
    * temperature - 0/0/0 -> shortName ``t``, paramId 130, units ``K``
    * geopotential height - 0/3/5 -> shortName ``gh``, paramId 156, units
      ``gpm``

    None decodes as ``unknown``, so no WMO-key declaration is needed here (see
    the ``total_cloud_opacity`` comment above for the one field that does); only the
    unit normalisation the adapter already applies, plus the measured
    saturation-phase stamp on every RH level.

    Geopotential metres are not geometric metres, but below 2 km the two
    differ by under 0.05 %, well inside the 150 m thickness test's own
    level-spacing error. The height is used as a height and the difference is
    stated rather than corrected.
    """
    entries: dict[str, tuple[str, str]] = {}
    for level in LOW_LEVELS_HPA:
        entries[f"relative_humidity_{level}hPa"] = (rh_prefix, token.format(level=level))
        entries[f"temperature_{level}hPa"] = (temp_prefix, token.format(level=level))
        entries[f"geopotential_height_{level}hPa"] = (height_prefix, token.format(level=level))
    return entries


HRDPS_PROFILE_VARS = {
    **_profile_vars("RH", "TMP", "HGT", "ISBL_{level:04d}"),
    # The AGL datum, and the one place the two models genuinely differ.
    #
    # HRDPS publishes `HGT_Sfc` (verified live 2026-09-01). Decoded, that
    # message is NOT a geopotential height in gpm: discipline 0,
    # parameterCategory 3, parameterNumber 5 on typeOfFirstFixedSurface=sfc
    # (1), which ecCodes 2.48.0 names `orog` / "Orography", paramId 228002,
    # units `m`. So it is the model's terrain height in metres - exactly the
    # datum the WEonG algorithm's "AGL" means - and the canonical units below
    # say `m`, not `gpm`, because that is what the message says.
    "surface_height": ("HGT", "Sfc"),
}

RDPS_PROFILE_VARS = {
    **_profile_vars("RelativeHumidity", "AirTemp", "GeopotentialHeight", "IsbL-{level:04d}"),
    # RDPS publishes NO surface geopotential height and no orography: the
    # 2026-09-01 12Z PT003H listing carries 21 `_Sfc_` tokens and none of them
    # is a height (checked by enumeration, not by absence of a guess). It does
    # publish `Pressure_Sfc`, decoded as 0/3/0 on sfc -> shortName `sp`,
    # paramId 134, units `Pa` (left in Pa by `normalize_units`, whose hPa rule
    # keys on the decoded variable name and `sp` does not match it).
    #
    # The derive therefore reconstructs the RDPS AGL datum by interpolating
    # `geopotential_height_*hPa` to `surface_pressure` in log-pressure. That
    # datum is the height of the model's own surface pressure surface, which
    # is the model's terrain height to within the hydrostatic error of the
    # interpolation - see `ingest.derive.weong_layer.surface_height_from_profile`
    # for the bias this carries and which way it points.
    "surface_pressure": ("Pressure", "Sfc"),
}

# HRDPS variable map: canonical -> (GRIB file var prefix, level token)
HRDPS_VARS = {
    "temperature_2m": ("TMP", "AGL-2m"),
    "dew_point_2m": ("DPT", "AGL-2m"),
    "relative_humidity_2m": ("RH", "AGL-2m"),
    "wind_u_10m": ("UGRD", "AGL-10m"),
    "wind_v_10m": ("VGRD", "AGL-10m"),
    "mean_sea_level_pressure": ("PRMSL", "MSL"),
    "total_cloud_opacity": ("TCDC", "Sfc"),
    **HRDPS_STEERING_VARS,
    **HRDPS_OMEGA_VARS,
    **HRDPS_THERMO_VARS,
    **HRDPS_PROFILE_VARS,
}

# RDPS variable map (CamelCase upstream naming)
RDPS_VARS = {
    "temperature_2m": ("AirTemp", "AGL-2m"),
    "dew_point_2m": ("DewPoint", "AGL-2m"),
    "wind_u_10m": ("WindU", "AGL-10m"),
    "wind_v_10m": ("WindV", "AGL-10m"),
    "mean_sea_level_pressure": ("Pressure_MSL", "MSL"),
    "total_cloud_opacity": ("TotalCloudCover", "Sfc"),
    **RDPS_STEERING_VARS,
    **RDPS_OMEGA_VARS,
    **RDPS_THERMO_VARS,
    **RDPS_PROFILE_VARS,
}

# GDPS variable map (CamelCase upstream naming)
GDPS_VARS = {
    "temperature_2m": ("AirTemp", "AGL-2m"),
    "dew_point_2m": ("DewPoint", "AGL-2m"),
    "wind_u_10m": ("WindU", "AGL-10m"),
    "wind_v_10m": ("WindV", "AGL-10m"),
    "mean_sea_level_pressure": ("Pressure_MSL", "MSL"),
}

# Normalized units per canonical variable, as ``ingest.grib.normalize_units``
# leaves them. A declared field arriving in anything else is a QC failure.
CANONICAL_FIELD_UNITS = {
    "temperature_2m": ("degC", "2 m"),
    "dew_point_2m": ("degC", "2 m"),
    "relative_humidity_2m": ("percent", "2 m"),
    "wind_u_10m": ("m s-1", "10 m"),
    "wind_v_10m": ("m s-1", "10 m"),
    "mean_sea_level_pressure": ("hPa", "mean sea level"),
    "total_cloud_opacity": ("percent", "column"),
    **{f"wind_{component}_{level}hPa": ("m s-1", f"{level} hPa")
       for level in STEERING_LEVELS_HPA for component in ("u", "v")},
    **{f"omega_{level}hPa": ("Pa s-1", f"{level} hPa") for level in STEERING_LEVELS_HPA},
    **{f"relative_humidity_{level}hPa": ("percent", f"{level} hPa") for level in STEERING_LEVELS_HPA},
    **{f"temperature_{level}hPa": ("degC", f"{level} hPa") for level in STEERING_LEVELS_HPA},
    **{f"relative_humidity_{level}hPa": ("percent", f"{level} hPa") for level in LOW_LEVELS_HPA},
    **{f"temperature_{level}hPa": ("degC", f"{level} hPa") for level in LOW_LEVELS_HPA},
    # `gpm` is what the message declares (0/3/5, shortName `gh`) and
    # `normalize_units` has no rule for it, so it arrives untouched.
    **{f"geopotential_height_{level}hPa": ("gpm", f"{level} hPa") for level in LOW_LEVELS_HPA},
    # HRDPS only, and `m` rather than `gpm`: the decoded message is orography
    # (paramId 228002, units `m`), not a geopotential height.
    "surface_height": ("m", "surface (model orography)"),
    # RDPS only. Left in Pa: the hPa conversion in `normalize_units` keys on
    # the decoded variable name, and this one decodes as `sp`.
    "surface_pressure": ("Pa", "surface"),
}

#: Variables the run may publish without, because they only inform a display
#: derivation (the cloud-motion steering prior, the development residual's
#: vertical velocity, and the WEonG low-cloud diagnosis' RH/T/height profile
#: with its AGL datum). A level absent from one cycle must never fail the
#: surface artifact the whole map is drawn from; it costs the derived layer,
#: which is then simply not offered.
OPTIONAL_VARIABLES = frozenset(
    [f"wind_{component}_{level}hPa" for level in STEERING_LEVELS_HPA for component in ("u", "v")]
    + [f"omega_{level}hPa" for level in STEERING_LEVELS_HPA]
    + [f"relative_humidity_{level}hPa" for level in STEERING_LEVELS_HPA]
    + [f"temperature_{level}hPa" for level in STEERING_LEVELS_HPA]
    + [f"relative_humidity_{level}hPa" for level in LOW_LEVELS_HPA]
    + [f"temperature_{level}hPa" for level in LOW_LEVELS_HPA]
    + [f"geopotential_height_{level}hPa" for level in LOW_LEVELS_HPA]
    + ["surface_height", "surface_pressure"]
)


def manifest_for(source_id: str, var_map: Mapping[str, tuple[str, str]]) -> RunManifest:
    """Every mapped variable is mandatory: the map is the adapter's own promise.

    Except the steering winds, the vertical velocity and the low-level
    RH/temperature/height profile, which are declared optional: they inform a
    display derivation only, so a level ECCC did not publish this cycle must
    cost the map its motion prior, its development residual or its WEonG
    low-cloud layer, never its evidence.
    """
    fields = []
    for name in var_map:
        units, level = CANONICAL_FIELD_UNITS[name]
        fields.append(RequiredField(name, units, level=level, optional=name in OPTIONAL_VARIABLES))
    return RunManifest(source_id=source_id, fields=tuple(fields))


def _cloud_units_declared(dataset: Any) -> bool:
    """True when every decoded variable's units are declared, one way or another.

    First the WMO-key declaration is attempted (it only touches variables
    ecCodes left ``unknown``); then any variable still without declared units
    means the field must be refused rather than published.
    """
    declare_wmo_total_cloud(dataset)
    for name in dataset.data_vars:
        units = str(dataset[name].attrs.get("units", "")).strip().lower()
        if units in {"", "unknown"}:
            return False
    return bool(dataset.data_vars)


def parse_run_stamp(filename: str) -> datetime | None:
    """Read the run's own ``{YYYYMMDD}T{HH}Z`` stamp out of a Datamart filename."""
    match = _FILE_RUN_STAMP.search(filename)
    if not match:
        return None
    try:
        return datetime.strptime(f"{match.group('date')}{match.group('hour')}", "%Y%m%d%H").replace(tzinfo=UTC)
    except ValueError:
        return None



#: How many files of one lead hour are downloaded at once. Bounded, and
#: settable per deployment through ``WEATHER_DATAMART_PARALLEL``; the polite
#: client's per-host interval (``WEATHER_HTTP_MIN_HOST_INTERVAL``) still
#: applies across the pool, so this never exceeds the provider's request
#: rate ceiling, it only stops one slow response from stalling the others.
DEFAULT_DOWNLOAD_PARALLELISM = 6


def download_parallelism(default: int = DEFAULT_DOWNLOAD_PARALLELISM) -> int:
    """``WEATHER_DATAMART_PARALLEL`` as a positive int, else ``default``."""
    import os  # noqa: PLC0415

    raw = os.environ.get("WEATHER_DATAMART_PARALLEL", "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default

class ECCCDataMartAdapter:
    """Ingests GRIB2 datasets from ECCC Datamart dated directory trees."""

    def __init__(
        self,
        *,
        source_id: str,
        model_subpath: str,
        grid_token: str,
        var_map: Mapping[str, tuple[str, str]],
        bounds: Mapping[str, float] = AVALON_CORE_BOUNDS,
        adapter_version: str = "eccc-datamart-v1",
        client: PoliteClient | None = None,
        base_url: str = ECCC_DATAMART_BASE,
        fallback_days: int = 1,
        datamart_fallback_path: str | None = None,
    ) -> None:
        self.source_id = source_id
        self.model_subpath = model_subpath
        self.grid_token = grid_token
        self.var_map = dict(var_map)
        self.bounds = dict(bounds)
        self.adapter_version = adapter_version
        self.manifest = manifest_for(source_id, self.var_map)
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._fallback_days = max(0, fallback_days)
        self._declared_fallback = datamart_fallback_path

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def model_root(self, date_str: str) -> str:
        return f"{self._base_url}/{date_str}/{DATED_PATH_SEGMENT}/{self.model_subpath}/"

    # --- the declared dated WXO-DD fallback ------------------------------
    def declared_fallback_path(self) -> str | None:
        """The dated WXO-DD path this source's registry record declares.

        Read from the record, not inferred: a path nobody declared is never
        tried, because guessing a directory on a producer's tree is how a
        fetch ends up naming a run it did not actually retrieve.
        """
        if self._declared_fallback is not None:
            return self._declared_fallback or None
        try:
            from ingest.registry import get_config  # noqa: PLC0415

            return get_config(self.source_id).datamart_fallback_path
        except Exception:  # a record that cannot be read declares nothing
            return None

    def fallback_root(self, date_str: str, template: str | None = None) -> str | None:
        """``template`` with ``{YYYYMMDD}`` filled in, cut back to its root.

        The declared path is a full ``{YYYYMMDD}/WXO-DD/<model>/{HH}/{FFF}/``
        template - the same shape the adapter already walks - so discovery
        fills the date and stops where the cycle and lead placeholders begin;
        ``fetch`` walks on from there exactly as it does under the primary.
        """
        declared = template if template is not None else self.declared_fallback_path()
        if not declared:
            return None
        filled = declared.replace("{YYYYMMDD}", date_str)
        root = filled.split("{", 1)[0]
        return root if root.endswith("/") else f"{root}/"

    # --- discovery -------------------------------------------------------
    def _candidates_for_date(self, client: PoliteClient, date_str: str) -> list[RunCandidate]:
        return self._candidates_under_root(client, self.model_root(date_str), date_str)

    def _candidates_under_root(self, client: PoliteClient, root_url: str, date_str: str) -> list[RunCandidate]:
        try:
            entries = client.list_directory(root_url)
        except Exception as error:
            _log.info("%s: no listing at %s (%s)", self.source_id, root_url, error)
            return []

        cycles = sorted({entry.rstrip("/") for entry in entries if _CYCLE_DIR.match(entry)}, reverse=True)
        candidates: list[RunCandidate] = []
        for cycle in cycles:
            cycle_url = f"{root_url}{cycle}/"
            try:
                hour_entries = client.list_directory(cycle_url)
            except Exception:
                continue
            hours = sorted({entry.rstrip("/") for entry in hour_entries if _LEAD_DIR.match(entry)})
            if "000" not in hours:
                continue

            analysis_url = f"{cycle_url}000/"
            try:
                files = client.list_directory(analysis_url, suffixes=(".grib2",))
            except Exception:
                continue
            stamps = {parse_run_stamp(name) for name in files}
            stamps.discard(None)
            if len(stamps) != 1:
                # No stamp, or a directory mixing runs: the run cannot be named
                # honestly, and a mislabelled run is worse than a missing one.
                _log.warning("%s: %s carries %d distinct run stamps", self.source_id, analysis_url, len(stamps))
                continue
            run_dt = stamps.pop()

            candidates.append(
                RunCandidate(
                    provider_run_id=run_dt.strftime("%Y%m%d%H"),
                    run_time=run_dt,
                    urls=[cycle_url],
                    detail={
                        "cycle": cycle,
                        "date_str": date_str,
                        "cycle_url": cycle_url,
                        "available_hours": hours,
                        "run_stamp": run_dt.strftime("%Y%m%dT%HZ"),
                        # Which of the record's paths actually answered. It
                        # travels onto the artifact so a served value can say
                        # where it came from rather than where it usually does.
                        "datamart_path": root_url,
                    },
                )
            )
        return candidates

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        """The primary path, then the record's declared dated fallback.

        The fallback is tried only where the record declares one; a source
        that declares none reports its primary path alone and no alternative
        is inferred from it. Whichever path answered is recorded on the
        candidate and travels to ``RunResult.notes`` and every artifact's
        provenance, so "which path answered" is a retrieved fact rather than
        an assumption about the usual layout.
        """
        client = self._get_client()
        dates = [
            (window.now - timedelta(days=day_offset)).strftime("%Y%m%d")
            for day_offset in range(self._fallback_days + 1)
        ]
        primary = f"{self._base_url}/{{{','.join(dates)}}}/{DATED_PATH_SEGMENT}/{self.model_subpath}/"
        for date_str in dates:
            candidates = self._candidates_under_root(client, self.model_root(date_str), date_str)
            if candidates:
                return candidates

        declared = self.declared_fallback_path()
        if not declared:
            raise AdapterUnavailable(
                f"{self.source_id}: no populated run cycle under {primary}; "
                "the record declares no fallback path, and none is inferred"
            )
        for date_str in dates:
            root_url = self.fallback_root(date_str, declared)
            if not root_url or root_url == self.model_root(date_str):
                # The declared fallback resolves to the path just tried; asking
                # the same directory twice would not make it answer.
                continue
            candidates = self._candidates_under_root(client, root_url, date_str)
            if candidates:
                _log.info("%s: the declared fallback path answered: %s", self.source_id, root_url)
                return candidates
        raise AdapterUnavailable(
            f"{self.source_id}: no populated run cycle under the primary path {primary} "
            f"or the declared fallback path {declared}"
        )

    # --- retrieval -------------------------------------------------------
    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._get_client()
        cycle_url = candidate.detail.get("cycle_url", "")
        available_hours = candidate.detail.get("available_hours", [])
        if not cycle_url:
            raise AdapterUnavailable(f"{self.source_id}: candidate carries no cycle URL")
        run_time = candidate.run_time
        if run_time is None:
            raise AdapterUnavailable(f"{self.source_id}: candidate has no run time derived from its filenames")

        target_hours = [f"{hour:03d}" for hour in range(25) if f"{hour:03d}" in available_hours]
        if not target_hours:
            raise AdapterUnavailable(f"No target forecast hours available for {candidate.provider_run_id}")

        hourly_datasets: list[xarray.Dataset] = []
        decode_errors: list[str] = []
        retrieved_at = datetime.now(UTC)

        for hour_str in target_hours:
            valid_time = run_time + timedelta(hours=int(hour_str))
            if not window.covers(valid_time):
                continue

            hour_dir_url = f"{cycle_url}{hour_str}/"
            try:
                file_list = client.list_directory(hour_dir_url, suffixes=(".grib2",))
            except Exception as error:
                decode_errors.append(f"listing:{hour_dir_url}")
                _log.warning("Could not list %s: %s", hour_dir_url, error)
                continue

            var_datasets: dict[str, xarray.DataArray] = {}
            # Resolve every file for this lead first, sequentially and with
            # the run-stamp check per file, so the download pool below only
            # ever sees files already judged to belong to this run.
            planned: list[tuple[str, str, str, Path]] = []
            for canonical_name, (eccc_var, level) in self.var_map.items():
                match_file = None
                for fname in file_list:
                    if f"_{eccc_var}_" in fname and (f"_{level}_" in fname or f"_{level}." in fname or level in fname):
                        match_file = fname
                        break
                if not match_file:
                    decode_errors.append(f"absent:{canonical_name}@{hour_str}")
                    continue

                stamp = parse_run_stamp(match_file)
                if stamp is not None and stamp != run_time:
                    # The directory rolled under us mid-fetch; mixing two runs
                    # into one artifact would be an invented forecast.
                    decode_errors.append(f"run_stamp_mismatch:{match_file}")
                    continue
                planned.append((canonical_name, match_file, f"{hour_dir_url}{match_file}", workdir / f"{canonical_name}_{hour_str}.grib2"))

            # The downloads run in a bounded pool; the decode stays
            # sequential below. Fetching is latency-bound (about 48 files of
            # 1-4 MB per lead, ~1,200 per run once the low-level profile is
            # requested) and the polite client's per-host interval is the
            # real ceiling, so the pool buys nothing past that interval's
            # reciprocal. Each file keeps its own byte cap and its own
            # failure: one bad download is one `download:` error, never a
            # lost lead. `PoliteClient` is safe to share across threads (one
            # httpx.Client, one locked limiter).
            fetched: dict[str, Path] = {}
            if planned:
                with ThreadPoolExecutor(max_workers=max(1, min(download_parallelism(), len(planned)))) as pool:
                    futures = {
                        pool.submit(client.download, file_url, local_grib, max_bytes=10 * 1024 * 1024): (canonical_name, match_file, file_url, local_grib)
                        for canonical_name, match_file, file_url, local_grib in planned
                    }
                    for future in as_completed(futures):
                        canonical_name, match_file, file_url, local_grib = futures[future]
                        try:
                            future.result()
                        except Exception as error:
                            decode_errors.append(f"download:{match_file}")
                            _log.warning("Failed to download %s: %s", file_url, error)
                            local_grib.unlink(missing_ok=True)
                            continue
                        fetched[canonical_name] = local_grib

            for canonical_name, match_file, file_url, local_grib in planned:
                if canonical_name not in fetched:
                    continue
                try:
                    # The cloud field's identity must be read from the message's own
                    # WMO keys (see the map comment above), so those keys are
                    # requested for it and the declaration is applied - or the
                    # field is refused, never published with unknown units.
                    opened = (
                        open_grib(local_grib, read_keys=WMO_IDENTITY_READ_KEYS)
                        if canonical_name == "total_cloud_opacity"
                        else open_grib(local_grib)
                    )
                    decoded = crop_to_bbox(opened, self.bounds)
                    if canonical_name == "total_cloud_opacity" and not _cloud_units_declared(decoded):
                        decode_errors.append(f"undeclared_units:{match_file}")
                        continue
                    decoded = normalize_units(decoded)
                    data_var_names = list(decoded.data_vars)
                    if not data_var_names:
                        decode_errors.append(f"no_variable:{match_file}")
                        continue
                    # Each field arrives as its own single-message GRIB, so it
                    # carries its own scalar level coordinate (2 m for screen
                    # temperature, 10 m for wind). Those must move into attrs
                    # before the fields are filed into one Dataset below, or the
                    # merge fails on the disagreement.
                    #
                    # ``load`` is what makes the ``unlink`` below safe. cfgrib
                    # reads on demand, so everything up to here is a promise
                    # against a file this loop deletes as soon as it moves to
                    # the next field; without materialising now, the values are
                    # only fetched at write_zarr time and every run dies with
                    # FileNotFoundError. The crop already bounded this to the
                    # Avalon window, so what is held is one small field.
                    field = strip_message_scalars(decoded[data_var_names[0]].load())
                    if canonical_name.startswith("relative_humidity_"):
                        # GRIB2 0/1/1 codes no saturation-phase key, so the
                        # convention cannot be read off the message; it was
                        # measured against the model's own SPFH instead and is
                        # recorded here so a threshold scheme can see what it
                        # is thresholding. Both ECCC models: liquid water.
                        field = declare_rh_phase(
                            field,
                            convention=RH_PHASE_LIQUID_WATER,
                            basis=ECCC_RH_PHASE_BASIS,
                        )
                    var_datasets[canonical_name] = field
                except Exception as error:
                    decode_errors.append(f"decode:{match_file}")
                    _log.warning("Failed to decode %s: %s", file_url, error)
                finally:
                    local_grib.unlink(missing_ok=True)

            if not var_datasets:
                decode_errors.append(f"empty_step:{hour_str}")
                continue

            step = xarray.Dataset(var_datasets).expand_dims(
                valid_time=[numpy.datetime64(valid_time.replace(tzinfo=None), "ns")]
            )
            hourly_datasets.append(step)

        if not hourly_datasets:
            raise AdapterUnavailable(f"No GRIB2 fields could be fetched or cropped for {self.source_id}")

        combined = xarray.concat(hourly_datasets, dim="valid_time")
        manifest = RunManifest(
            source_id=self.manifest.source_id,
            fields=self.manifest.fields,
            required_valid_times=required_leads(window, run_time, max_lead_hours=int(target_hours[-1])),
            min_coverage_fraction=self.manifest.min_coverage_fraction,
            bounds=self.bounds,
        )
        validation = validate_run(manifest, combined, window=window, decode_errors=decode_errors)

        zarr_path = workdir / f"{self.source_id}.zarr.zip"
        write_zarr(combined, zarr_path)

        provenance = {
            "source_id": self.source_id,
            "producer": "Environment and Climate Change Canada",
            "product": self.source_id.upper(),
            "native_resolution": self.grid_token,
            "native_crs": "EPSG:4326",
            "adapter_version": self.adapter_version,
            "provider_run_stamp": candidate.detail.get("run_stamp", ""),
            # Which declared path answered for this run: the primary, or the
            # record's dated WXO-DD fallback.
            "datamart_path": str(candidate.detail.get("datamart_path", "")),
            "quality": validation.as_quality(),
            "coverage": validation.as_coverage(),
            # Model fields decoded from the producer's own GRIB, unmodified.
            **manifest.as_manifest_block(),
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
            run_time=run_time,
            retrieved_at=retrieved_at,
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes=(
                f"Ingested {len(hourly_datasets)} forecast lead steps for {self.source_id} "
                f"from {provenance['datamart_path'] or 'an unrecorded Datamart path'}; {validation.detail}"
            ),
        )


HRDPS_ADAPTER = register(
    ECCCDataMartAdapter(
        source_id="eccc-hrdps",
        model_subpath="model_hrdps/continental/2.5km",
        grid_token="RLatLon0.0225",
        var_map=HRDPS_VARS,
        bounds=AVALON_CORE_BOUNDS,
        adapter_version="hrdps-v2",
    )
)

RDPS_ADAPTER = register(
    ECCCDataMartAdapter(
        source_id="eccc-rdps",
        model_subpath="model_rdps/10km",
        grid_token="RLatLon0.09",
        var_map=RDPS_VARS,
        bounds=AVALON_CORE_BOUNDS,
        adapter_version="rdps-v2",
    )
)

# GDPS is published at 10 km, not 15 km: ``today/model_gdps/15km/`` is a 404 and
# ``10km/`` is a 200, verified 2026-08-30.
GDPS_ADAPTER = register(
    ECCCDataMartAdapter(
        source_id="eccc-gdps",
        model_subpath="model_gdps/10km",
        # Directory resolution only; the exact RLatLon grid token in the
        # filenames was not verified, so it is not asserted here.
        grid_token="10km",
        var_map=GDPS_VARS,
        bounds=ATLANTIC_CONTEXT_BOUNDS,
        adapter_version="gdps-v2",
    )
)
