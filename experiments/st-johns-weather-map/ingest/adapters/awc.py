"""Aviation Weather Center (AWC) METAR/SPECI observation adapter.

Fetches JSON observations for CYYT (St. John's Airport) covering the -3h backward
window, parses METAR fields, converts units to canonical standards, and packages
into Zarr point artifacts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy
import xarray

from ingest.contract import (
    MEDIA_ZARR,
    Adapter,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import write_zarr
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, validate_run
from ingest.registry import register

UTC = timezone.utc
CYYT_LAT = 47.6186
CYYT_LON = -52.7519
CYYT_ELEV_M = 140.0
AWC_METAR_URL = "https://aviationweather.gov/api/data/metar?ids=CYYT&format=json&hours=4"
AWC_TAF_URL = "https://aviationweather.gov/api/data/taf?ids=CYYT&format=json"

# A METAR is a human-coded report: pressure, visibility, cloud and a variable
# wind direction are all legitimately absent from a valid observation, so they
# are declared optional. Temperature, dew point and the humidity derived from
# them are what make the report usable evidence at all.
METAR_MANIFEST = RunManifest(
    source_id="awc-metar-speci",
    fields=(
        RequiredField("temperature_2m", "degC", level="2 m"),
        RequiredField("dew_point_2m", "degC", level="2 m"),
        RequiredField("relative_humidity_2m", "percent", level="2 m"),
        RequiredField("mean_sea_level_pressure", "hPa", level="mean sea level", optional=True),
        RequiredField("visibility", "m", optional=True),
        RequiredField("total_cloud", "percent", level="column", optional=True),
        RequiredField("wind_u_10m", "m s-1", level="10 m", optional=True),
        RequiredField("wind_v_10m", "m s-1", level="10 m", optional=True),
        # Per-layer cloud and the present-weather flags are published as
        # retrieved (see ``parse_cloud_layers`` / ``parse_present_weather``).
        # Only the first slot and the fog flag are declared: they pin the units
        # the store must find; slots 2-6 are legitimately absent on most reports.
        RequiredField("cloud_layer_1_cover_code", "code", optional=True),
        RequiredField("cloud_layer_1_base", "m", optional=True),
        RequiredField("weather_fog_code", "flag", optional=True),
    ),
    # One element missing from one report in a rolling four-hour batch is a
    # provider gap; a batch more than a tenth empty is not evidence.
    min_coverage_fraction=0.9,
)

# A TAF carries no temperature at all, so its manifest is a different contract
# rather than a relaxation of the METAR one.
TAF_MANIFEST = RunManifest(
    source_id="awc-taf",
    fields=(
        RequiredField("wind_u_10m", "m s-1", level="10 m"),
        RequiredField("wind_v_10m", "m s-1", level="10 m"),
        RequiredField("visibility", "m"),
        RequiredField("total_cloud", "percent", level="column", optional=True),
        RequiredField("cloud_layer_1_cover_code", "code", optional=True),
        RequiredField("cloud_layer_1_base", "m", optional=True),
        RequiredField("weather_fog_code", "flag", optional=True),
    ),
    min_coverage_fraction=0.9,
)

# --- present weather ------------------------------------------------------
# The METAR/TAF present-weather group (WMO No. 306 FM 15 table 4678; NAV CANADA
# MANOBS) is a sequence of two-letter descriptors and phenomena, optionally
# prefixed by an intensity sign and/or ``VC`` (in the vicinity, not at the
# station). Only the two phenomena that bear on fog evidence are read here;
# nothing else in the group is interpreted.
FOG_PHENOMENON = "FG"
MIST_PHENOMENON = "BR"
_VICINITY_PREFIX = "VC"
_INTENSITY_SIGNS = "+-"


@dataclass(frozen=True)
class PresentWeather:
    """What the present-weather group said about fog and mist, and nothing else.

    ``fog`` is FG at the station (FZFG, MIFG, BCFG, PRFG and intensity-prefixed
    forms included); ``fog_vicinity`` is VCFG, fog observed near but not at
    the station; ``mist`` is BR, which table 4678 defines as a separate
    phenomenon (visibility 1000 m or more) and which is *not* fog. ``raw`` is
    the group as retrieved, or None when the report carried none.
    """

    fog: bool
    fog_vicinity: bool
    mist: bool
    raw: str | None


def parse_present_weather(wx_string: Any) -> PresentWeather:
    """Read fog and mist out of a METAR/TAF present-weather string.

    Tokenised on whitespace; per token the leading intensity sign is dropped,
    a leading ``VC`` is detected and dropped, and the remainder is read as
    consecutive two-letter pairs (WMO No. 306 FM 15 table 4678; NAV CANADA
    MANOBS). A null or empty string is a retrieved absence: every flag False
    and ``raw`` None.
    """
    if wx_string is None:
        return PresentWeather(False, False, False, None)
    text = str(wx_string).strip()
    if not text:
        return PresentWeather(False, False, False, None)
    fog = vicinity = mist = False
    for token in text.upper().split():
        body = token.lstrip(_INTENSITY_SIGNS)
        in_vicinity = body.startswith(_VICINITY_PREFIX)
        if in_vicinity:
            body = body[len(_VICINITY_PREFIX):]
        pairs = {body[index:index + 2] for index in range(0, len(body) - 1, 2)}
        if FOG_PHENOMENON in pairs:
            if in_vicinity:
                vicinity = True
            else:
                fog = True
        if MIST_PHENOMENON in pairs:
            mist = True
    return PresentWeather(fog=fog, fog_vicinity=vicinity, mist=mist, raw=text)


# --- cloud layers ---------------------------------------------------------
# A METAR reports up to several cloud layers, each as a cover code and a base
# in hundreds of feet above ground. They are published here per layer, in
# provider order, as flag-coded integers plus the base in metres. They are
# deliberately NOT bucketed into low/middle/high strata: that is a derived
# classification and is withheld pending an owner decision.
MAX_CLOUD_LAYERS = 6
CLOUD_COVER_FLAGS = {"SKC": 0, "CLR": 1, "NSC": 2, "FEW": 3, "SCT": 4, "BKN": 5, "OVC": 6, "VV": 7, "OVX": 8, "CAVOK": 9}
CLOUD_COVER_FLAG_VALUES = list(CLOUD_COVER_FLAGS.values())
CLOUD_COVER_FLAG_MEANINGS = " ".join(CLOUD_COVER_FLAGS)
FEET_TO_METRES = 0.3048


@dataclass(frozen=True)
class CloudLayer:
    """One reported layer: its cover code flag, the percent that code maps to
    under ``_CLOUD_FRACTION`` (None where the code carries no fraction), and
    the base above ground in metres (None where the report gave none)."""

    code_flag: int
    cover_pct: float | None
    base_m: float | None


def parse_cloud_layers(clouds: list[dict[str, Any]] | None, *, stamp: str = "") -> tuple[list[CloudLayer], list[str]]:
    """Every reported layer in provider order, plus the decode errors met.

    An unknown cover vocabulary is an error, not a guess; more than
    ``MAX_CLOUD_LAYERS`` layers is an error too, reported loudly rather than
    silently dropped (the first six are kept so the report is still readable
    while the run itself is refused). A base that is not a number is an error;
    a base that is absent is simply None.
    """
    layers: list[CloudLayer] = []
    errors: list[str] = []
    if not clouds:
        return layers, errors
    if len(clouds) > MAX_CLOUD_LAYERS:
        errors.append(f"cloud_layers_truncated:{len(clouds)}@{stamp}")
    for entry in clouds[:MAX_CLOUD_LAYERS]:
        code = str(entry.get("cover") or "").strip().upper()
        flag = CLOUD_COVER_FLAGS.get(code)
        if flag is None:
            errors.append(f"cloud_cover_code:{code or 'unset'}@{stamp}")
            continue
        base_raw = entry.get("base")
        base_m: float | None = None
        if base_raw is not None:
            try:
                base_m = round(float(base_raw) * FEET_TO_METRES, 2)
            except (TypeError, ValueError):
                errors.append(f"cloud_base:{base_raw}@{stamp}")
        layers.append(CloudLayer(code_flag=flag, cover_pct=_CLOUD_FRACTION.get(code), base_m=base_m))
    return layers, errors


def _cloud_layer_arrays(n_times: int) -> dict[str, numpy.ndarray]:
    arrays: dict[str, numpy.ndarray] = {}
    for slot in range(1, MAX_CLOUD_LAYERS + 1):
        for suffix in ("cover_code", "cover", "base"):
            arrays[f"cloud_layer_{slot}_{suffix}"] = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
    return arrays


def _fill_cloud_layers(arrays: dict[str, numpy.ndarray], index: int, layers: list[CloudLayer]) -> None:
    for slot, layer in enumerate(layers, start=1):
        arrays[f"cloud_layer_{slot}_cover_code"][index, 0, 0] = float(layer.code_flag)
        if layer.cover_pct is not None:
            arrays[f"cloud_layer_{slot}_cover"][index, 0, 0] = layer.cover_pct
        if layer.base_m is not None:
            arrays[f"cloud_layer_{slot}_base"][index, 0, 0] = layer.base_m


def _cloud_layer_data_vars(arrays: dict[str, numpy.ndarray], report: str) -> dict[str, tuple[Any, ...]]:
    dims = ("valid_time", "latitude", "longitude")
    data_vars: dict[str, tuple[Any, ...]] = {}
    for slot in range(1, MAX_CLOUD_LAYERS + 1):
        data_vars[f"cloud_layer_{slot}_cover_code"] = (
            dims,
            arrays[f"cloud_layer_{slot}_cover_code"],
            {
                "units": "code",
                "original_units": "code",
                "flag_values": CLOUD_COVER_FLAG_VALUES,
                "flag_meanings": CLOUD_COVER_FLAG_MEANINGS,
                "long_name": f"{report} cloud layer {slot} cover code as reported",
            },
        )
        data_vars[f"cloud_layer_{slot}_cover"] = (dims, arrays[f"cloud_layer_{slot}_cover"], {"units": "percent", "original_units": "okta_fraction"})
        data_vars[f"cloud_layer_{slot}_base"] = (dims, arrays[f"cloud_layer_{slot}_base"], {"units": "m", "original_units": "ft", "long_name": "cloud base above ground level"})
    return data_vars


_PRESENT_WEATHER_ATTRS = {"units": "flag", "original_units": "present_weather_group", "flag_values": [0, 1], "flag_meanings": "absent present"}


def _present_weather_data_vars(fog: numpy.ndarray, vicinity: numpy.ndarray, mist: numpy.ndarray) -> dict[str, tuple[Any, ...]]:
    dims = ("valid_time", "latitude", "longitude")
    return {
        "weather_fog_code": (dims, fog, {**_PRESENT_WEATHER_ATTRS, "long_name": "FG in the present-weather group (fog at the station)"}),
        "weather_fog_vicinity_code": (dims, vicinity, {**_PRESENT_WEATHER_ATTRS, "long_name": "VCFG in the present-weather group (fog in the vicinity)"}),
        "weather_mist_code": (dims, mist, {**_PRESENT_WEATHER_ATTRS, "long_name": "BR in the present-weather group (mist, not fog)"}),
    }


def _original_units(dataset: xarray.Dataset) -> dict[str, str]:
    """Per-variable provider units, read from the attrs the dataset declares."""
    return {str(name): str(dataset[name].attrs["original_units"]) for name in dataset.data_vars if "original_units" in dataset[name].attrs}


_CLOUD_FRACTION = {
    "SKC": 0.0,
    "CLR": 0.0,
    "NSC": 0.0,
    "FEW": 25.0,
    "SCT": 50.0,
    "BKN": 75.0,
    "OVC": 100.0,
    "VV": 100.0,
}


def parse_visibility_meters(raw: Any) -> float | None:
    """Parse statute miles (numeric or string fraction) to meters."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) * 1609.344
    text = str(raw).strip().removesuffix("SM").removesuffix("+").strip()
    if not text:
        return None
    try:
        if " " in text:
            parts = text.split(" ")
            miles = sum(parse_visibility_meters(p) or 0.0 for p in parts) / 1609.344
            return miles * 1609.344
        if "/" in text:
            num, denom = text.split("/", 1)
            return (float(num) / float(denom)) * 1609.344
        return float(text) * 1609.344
    except (ValueError, ZeroDivisionError):
        return None


def parse_cloud_cover_percent(cover: str | None, clouds: list[dict[str, Any]] | None) -> float | None:
    if cover and cover.upper() in _CLOUD_FRACTION:
        return _CLOUD_FRACTION[cover.upper()]
    if clouds:
        fractions = [_CLOUD_FRACTION.get(str(c.get("cover", "")).upper()) for c in clouds if c.get("cover")]
        valid = [f for f in fractions if f is not None]
        if valid:
            return max(valid)
    return None


def parse_wind_components(wspd_kt: float | None, wdir_deg: Any) -> tuple[float | None, float | None]:
    """Convert wind speed (kt) and direction (deg) to u, v components in m/s."""
    if wspd_kt is None:
        return None, None
    speed_ms = float(wspd_kt) * 0.514444
    try:
        deg = float(wdir_deg)
    except (TypeError, ValueError):
        # Variable or missing direction
        return None, None
    rad = math.radians(deg)
    # Meteorological convention: direction is where wind comes from
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return round(u, 2), round(v, 2)


def parse_pressure_hpa(slp: Any, altim: Any) -> float | None:
    if slp is not None:
        try:
            return round(float(slp), 1)
        except (TypeError, ValueError):
            pass
    if altim is not None:
        try:
            val = float(altim)
            if val < 200.0:  # inHg
                return round(val * 33.8639, 1)
            return round(val, 1)
        except (TypeError, ValueError):
            pass
    return None


class AWCMetarAdapter:
    """Ingests AWC METAR/SPECI point observations for CYYT."""

    source_id = "awc-metar-speci"
    adapter_version = "awc-metar-v2"

    def __init__(self, client: PoliteClient | None = None, url: str = AWC_METAR_URL) -> None:
        self._client = client
        self._url = url

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        try:
            response = client.get(self._url)
            data = response.json()
        except Exception as error:
            raise AdapterUnavailable(f"AWC METAR endpoint unavailable: {error}") from error
        if not isinstance(data, list) or not data:
            raise AdapterUnavailable("AWC METAR returned empty record list")

        # Sort newest-first by obsTime
        def record_time(rec: dict[str, Any]) -> int:
            obs = rec.get("obsTime")
            if isinstance(obs, (int, float)):
                return int(obs)
            return 0

        sorted_records = sorted(data, key=record_time, reverse=True)
        newest = sorted_records[0]
        obs_time = newest.get("obsTime")
        run_dt = datetime.fromtimestamp(obs_time, tz=UTC) if obs_time else window.now
        run_id = f"cyyt-metar-{int(obs_time)}" if obs_time else f"cyyt-metar-{int(window.now.timestamp())}"

        return [
            RunCandidate(
                provider_run_id=run_id,
                run_time=run_dt,
                urls=[self._url],
                detail={"records": sorted_records},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        records = candidate.detail.get("records", [])
        if not records:
            client = self._get_client()
            try:
                records = client.get(self._url).json()
            except Exception as error:
                raise AdapterUnavailable(f"Failed to fetch AWC METAR: {error}") from error

        # Filter to records falling within fetch window
        valid_records: list[tuple[datetime, dict[str, Any]]] = []
        for rec in records:
            obs = rec.get("obsTime")
            if not obs:
                continue
            dt = datetime.fromtimestamp(int(obs), tz=UTC)
            if window.covers(dt):
                valid_records.append((dt, rec))

        if not valid_records:
            raise AdapterUnavailable(f"No CYYT METAR records within window {window.start}..{window.end}")

        # Sort chronologically for time series dataset
        valid_records.sort(key=lambda item: item[0])
        times = [item[0] for item in valid_records]
        n_times = len(times)

        stamps = numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times])
        latitudes = numpy.array([CYYT_LAT], dtype="float64")
        longitudes = numpy.array([CYYT_LON], dtype="float64")

        # Arrays shaped (time, lat, lon)
        temp_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        dewp_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        rh_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        pres_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        vis_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        cloud_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        wind_u_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        wind_v_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        layer_arrays = _cloud_layer_arrays(n_times)
        # 0 is a retrieved absence (the group was read and carried no FG/BR),
        # which is why these start at 0 rather than NaN.
        fog_arr = numpy.zeros((n_times, 1, 1), dtype="float64")
        fog_vicinity_arr = numpy.zeros((n_times, 1, 1), dtype="float64")
        mist_arr = numpy.zeros((n_times, 1, 1), dtype="float64")
        present_weather_strings: list[str] = []

        from ingest.meteorology import resolve_relative_humidity  # noqa: PLC0415

        decode_errors: list[str] = []
        for i, (_dt, rec) in enumerate(valid_records):
            stamp = times[i].strftime("%Y-%m-%dT%H:%M:%SZ")
            layers, layer_errors = parse_cloud_layers(rec.get("clouds"), stamp=stamp)
            decode_errors.extend(layer_errors)
            _fill_cloud_layers(layer_arrays, i, layers)
            weather = parse_present_weather(rec.get("wxString"))
            fog_arr[i, 0, 0] = 1.0 if weather.fog else 0.0
            fog_vicinity_arr[i, 0, 0] = 1.0 if weather.fog_vicinity else 0.0
            mist_arr[i, 0, 0] = 1.0 if weather.mist else 0.0
            present_weather_strings.append(weather.raw or "")
            t = rec.get("temp")
            d = rec.get("dewp")
            if t is not None:
                try:
                    temp_arr[i, 0, 0] = float(t)
                except (ValueError, TypeError):
                    decode_errors.append(f"temp@{stamp}")
            if d is not None:
                try:
                    dewp_arr[i, 0, 0] = float(d)
                except (ValueError, TypeError):
                    decode_errors.append(f"dewp@{stamp}")

            t_val = temp_arr[i, 0, 0]
            d_val = dewp_arr[i, 0, 0]
            if not numpy.isnan(t_val) and not numpy.isnan(d_val):
                rh_calc, _, _ = resolve_relative_humidity(None, float(t_val), float(d_val))
                if rh_calc is not None:
                    rh_arr[i, 0, 0] = rh_calc

            p = parse_pressure_hpa(rec.get("slp"), rec.get("altim"))
            if p is not None:
                pres_arr[i, 0, 0] = p

            vis = parse_visibility_meters(rec.get("visib"))
            if vis is not None:
                vis_arr[i, 0, 0] = vis

            c = parse_cloud_cover_percent(rec.get("cover"), rec.get("clouds"))
            if c is not None:
                cloud_arr[i, 0, 0] = c

            u, v = parse_wind_components(rec.get("wspd"), rec.get("wdir"))
            if u is not None and v is not None:
                wind_u_arr[i, 0, 0] = u
                wind_v_arr[i, 0, 0] = v

        dataset = xarray.Dataset(
            {
                "temperature_2m": (("valid_time", "latitude", "longitude"), temp_arr, {"units": "degC", "original_units": "degC"}),
                "dew_point_2m": (("valid_time", "latitude", "longitude"), dewp_arr, {"units": "degC", "original_units": "degC"}),
                "relative_humidity_2m": (("valid_time", "latitude", "longitude"), rh_arr, {"units": "percent", "original_units": "derived"}),
                "mean_sea_level_pressure": (("valid_time", "latitude", "longitude"), pres_arr, {"units": "hPa", "original_units": "hPa"}),
                "visibility": (("valid_time", "latitude", "longitude"), vis_arr, {"units": "m", "original_units": "SM"}),
                "total_cloud": (("valid_time", "latitude", "longitude"), cloud_arr, {"units": "percent", "original_units": "okta_fraction"}),
                "wind_u_10m": (("valid_time", "latitude", "longitude"), wind_u_arr, {"units": "m s-1", "original_units": "kt"}),
                "wind_v_10m": (("valid_time", "latitude", "longitude"), wind_v_arr, {"units": "m s-1", "original_units": "kt"}),
                **_cloud_layer_data_vars(layer_arrays, "METAR"),
                **_present_weather_data_vars(fog_arr, fog_vicinity_arr, mist_arr),
            },
            coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
            attrs={
                "station_id": "CYYT",
                "elevation_m": CYYT_ELEV_M,
                "source": "AWC METAR",
                # The present-weather group verbatim per step ("" where the
                # report carried none), so the flags above can be audited.
                "present_weather_strings": present_weather_strings,
            },
        )

        validation = validate_run(METAR_MANIFEST, dataset, window=window, decode_errors=decode_errors)

        zarr_path = workdir / "cyyt_metar.zarr.zip"
        write_zarr(dataset, zarr_path)

        now_utc = datetime.now(UTC)
        newest_time = times[-1]
        provenance = {
            "source_id": self.source_id,
            "producer": "Aviation Weather Center / NAV CANADA",
            "product": "CYYT METAR/SPECI",
            "native_resolution": "point observation",
            "native_crs": "EPSG:4326",
            "adapter_version": self.adapter_version,
            "quality": validation.as_quality(),
            "coverage": validation.as_coverage(),
            "station_id": "CYYT",
            "original_units": _original_units(dataset),
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
            run_time=newest_time,
            retrieved_at=now_utc,
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes=f"Parsed {len(valid_records)} CYYT METAR/SPECI observation steps; {validation.detail}",
        )


METAR_ADAPTER = register(AWCMetarAdapter())


class AWCTafAdapter:
    """Ingests AWC TAF terminal aerodrome forecasts for CYYT."""

    source_id = "awc-taf"
    adapter_version = "awc-taf-v2"

    def __init__(self, client: PoliteClient | None = None, url: str = AWC_TAF_URL) -> None:
        self._client = client
        self._url = url

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        try:
            response = client.get(self._url)
            data = response.json()
        except Exception as error:
            raise AdapterUnavailable(f"AWC TAF endpoint unavailable: {error}") from error
        if not isinstance(data, list) or not data:
            raise AdapterUnavailable("AWC TAF returned empty record list")

        taf = data[0]
        issue_time_str = taf.get("issueTime", "")
        valid_from = taf.get("validTimeFrom")
        run_dt = datetime.fromtimestamp(int(valid_from), tz=UTC) if valid_from else window.now
        run_id = f"cyyt-taf-{int(valid_from) if valid_from else int(window.now.timestamp())}"

        return [
            RunCandidate(
                provider_run_id=run_id,
                run_time=run_dt,
                urls=[self._url],
                detail={"taf": taf, "issue_time": issue_time_str},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        taf = candidate.detail.get("taf", {})
        if not taf:
            client = self._get_client()
            try:
                data = client.get(self._url).json()
                taf = data[0] if data else {}
            except Exception as error:
                raise AdapterUnavailable(f"Failed to fetch AWC TAF: {error}") from error

        fcsts = taf.get("fcsts", [])
        if not fcsts:
            raise AdapterUnavailable("TAF contains no forecast periods")

        valid_fcsts: list[tuple[datetime, dict[str, Any]]] = []
        for period in fcsts:
            t_from = period.get("timeFrom")
            if not t_from:
                continue
            dt = datetime.fromtimestamp(int(t_from), tz=UTC)
            if window.covers(dt):
                valid_fcsts.append((dt, period))

        if not valid_fcsts:
            raise AdapterUnavailable(f"No TAF periods within window {window.start}..{window.end}")

        valid_fcsts.sort(key=lambda item: item[0])
        times = [item[0] for item in valid_fcsts]
        n_times = len(times)

        stamps = numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times])
        latitudes = numpy.array([CYYT_LAT], dtype="float64")
        longitudes = numpy.array([CYYT_LON], dtype="float64")

        vis_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        cloud_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        wind_u_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        wind_v_arr = numpy.full((n_times, 1, 1), numpy.nan, dtype="float64")
        layer_arrays = _cloud_layer_arrays(n_times)
        fog_arr = numpy.zeros((n_times, 1, 1), dtype="float64")
        fog_vicinity_arr = numpy.zeros((n_times, 1, 1), dtype="float64")
        mist_arr = numpy.zeros((n_times, 1, 1), dtype="float64")
        present_weather_strings: list[str] = []
        decode_errors: list[str] = []

        for i, (_dt, period) in enumerate(valid_fcsts):
            stamp = times[i].strftime("%Y-%m-%dT%H:%M:%SZ")
            vis = parse_visibility_meters(period.get("visib"))
            if vis is not None:
                vis_arr[i, 0, 0] = vis

            c = parse_cloud_cover_percent(None, period.get("clouds"))
            if c is not None:
                cloud_arr[i, 0, 0] = c

            layers, layer_errors = parse_cloud_layers(period.get("clouds"), stamp=stamp)
            decode_errors.extend(layer_errors)
            _fill_cloud_layers(layer_arrays, i, layers)
            weather = parse_present_weather(period.get("wxString"))
            fog_arr[i, 0, 0] = 1.0 if weather.fog else 0.0
            fog_vicinity_arr[i, 0, 0] = 1.0 if weather.fog_vicinity else 0.0
            mist_arr[i, 0, 0] = 1.0 if weather.mist else 0.0
            present_weather_strings.append(weather.raw or "")

            u, v = parse_wind_components(period.get("wspd"), period.get("wdir"))
            if u is not None and v is not None:
                wind_u_arr[i, 0, 0] = u
                wind_v_arr[i, 0, 0] = v

        dataset = xarray.Dataset(
            {
                "visibility": (("valid_time", "latitude", "longitude"), vis_arr, {"units": "m", "original_units": "SM"}),
                "total_cloud": (("valid_time", "latitude", "longitude"), cloud_arr, {"units": "percent", "original_units": "okta_fraction"}),
                "wind_u_10m": (("valid_time", "latitude", "longitude"), wind_u_arr, {"units": "m s-1", "original_units": "kt"}),
                "wind_v_10m": (("valid_time", "latitude", "longitude"), wind_v_arr, {"units": "m s-1", "original_units": "kt"}),
                **_cloud_layer_data_vars(layer_arrays, "TAF"),
                **_present_weather_data_vars(fog_arr, fog_vicinity_arr, mist_arr),
            },
            coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
            attrs={
                "station_id": "CYYT",
                "elevation_m": CYYT_ELEV_M,
                "source": "AWC TAF",
                "raw_taf": taf.get("rawTAF", ""),
                "present_weather_strings": present_weather_strings,
            },
        )

        validation = validate_run(TAF_MANIFEST, dataset, window=window, decode_errors=decode_errors)

        zarr_path = workdir / "cyyt_taf.zarr.zip"
        write_zarr(dataset, zarr_path)

        provenance = {
            "source_id": self.source_id,
            "producer": "Aviation Weather Center / NAV CANADA",
            "product": "CYYT TAF (Terminal Aerodrome Forecast)",
            "native_resolution": "point aerodrome forecast",
            "native_crs": "EPSG:4326",
            "adapter_version": self.adapter_version,
            "quality": validation.as_quality(),
            "coverage": validation.as_coverage(),
            "station_id": "CYYT",
            "original_units": _original_units(dataset),
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
            run_time=candidate.run_time,
            retrieved_at=datetime.now(UTC),
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes=f"Parsed {len(valid_fcsts)} CYYT TAF forecast steps; {validation.detail}",
        )


TAF_ADAPTER = register(AWCTafAdapter())
