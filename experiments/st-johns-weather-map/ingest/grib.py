"""GRIB2 subsetting and normalization.

Global GRIB files are far larger than the 25 GiB experiment cap allows, so the
``.idx`` sidecar is the primary defence: it lets an adapter request only the
messages it declared, as a handful of HTTP byte ranges, before any decode.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

UTC = timezone.utc

# Canonical output units for this experiment. Accumulations are deliberately
# absent: see ``normalize_precipitation``.
CANONICAL_UNITS = {
    "temperature": "degC",
    "dew_point": "degC",
    "relative_humidity": "percent",
    "wind_speed": "m s-1",
    "wind_u": "m s-1",
    "wind_v": "m s-1",
    "pressure": "hPa",
    "visibility": "m",
}

_KELVIN_NAMES = frozenset({"K", "degK", "kelvin"})
_FRACTION_NAMES = frozenset({"1", "fraction", "(0 - 1)", "0-1"})


class GribError(RuntimeError):
    """GRIB decoding or normalization could not proceed safely."""


@dataclass(frozen=True)
class IdxRecord:
    """One message in a NOAA-style ``.idx`` sidecar."""

    number: int
    offset: int
    run_time: datetime | None
    param: str
    level: str
    forecast: str
    extra: tuple[str, ...] = ()
    length: int | None = None

    @property
    def end(self) -> int | None:
        """Inclusive last byte, or ``None`` for the final open-ended message."""
        return None if self.length is None else self.offset + self.length - 1


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int | None = None

    @property
    def header(self) -> str:
        return f"bytes={self.start}-{'' if self.end is None else self.end}"

    @property
    def length(self) -> int | None:
        return None if self.end is None else self.end - self.start + 1

    def as_tuple(self) -> tuple[int, int | None]:
        return (self.start, self.end)


_DATE = re.compile(r"^d=(\d{10}|\d{12})$")


def _parse_run_time(token: str) -> datetime | None:
    match = _DATE.match(token.strip())
    if not match:
        return None
    digits = match.group(1)
    fmt = "%Y%m%d%H" if len(digits) == 10 else "%Y%m%d%H%M"
    return datetime.strptime(digits, fmt).replace(tzinfo=UTC)


def parse_idx(text: str) -> list[IdxRecord]:
    """Parse ``recordnum:byteoffset:date:param:level:forecasthour:`` lines.

    Message length is the gap to the next offset; the final message is
    open-ended because the sidecar never states the file size.
    """
    parsed: list[tuple[int, int, datetime | None, str, str, str, tuple[str, ...]]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = line.split(":")
        if len(fields) < 6:
            raise GribError(f"malformed idx line: {line!r}")
        try:
            number, offset = int(fields[0]), int(fields[1])
        except ValueError as error:
            raise GribError(f"malformed idx line: {line!r}") from error
        extra = tuple(item for item in fields[6:] if item)
        parsed.append((number, offset, _parse_run_time(fields[2]), fields[3], fields[4], fields[5], extra))

    ordered = sorted(parsed, key=lambda item: item[1])
    records: list[IdxRecord] = []
    for index, item in enumerate(ordered):
        following = ordered[index + 1][1] if index + 1 < len(ordered) else None
        length = None if following is None else following - item[1]
        if length is not None and length <= 0:
            raise GribError("idx offsets must strictly increase")
        records.append(IdxRecord(item[0], item[1], item[2], item[3], item[4], item[5], item[6], length))
    return records


def select_records(
    records: Sequence[IdxRecord],
    *,
    params: Iterable[str],
    levels: Iterable[str] | None = None,
    forecasts: Iterable[str] | None = None,
) -> list[IdxRecord]:
    """Filter to an explicit allowlist. Empty selections are the caller's problem."""
    wanted_params = {item.upper() for item in params}
    wanted_levels = None if levels is None else {item.lower() for item in levels}
    wanted_forecasts = None if forecasts is None else {item.lower() for item in forecasts}
    selected = []
    for record in records:
        if record.param.upper() not in wanted_params:
            continue
        if wanted_levels is not None and record.level.lower() not in wanted_levels:
            continue
        if wanted_forecasts is not None and record.forecast.lower() not in wanted_forecasts:
            continue
        selected.append(record)
    return selected


def byte_ranges(selected: Sequence[IdxRecord], *, merge_gap_bytes: int = 0) -> list[ByteRange]:
    """Collapse selected messages into the fewest HTTP ranges.

    Adjacent messages are merged so a contiguous block costs one request; a
    non-final selection never becomes open-ended, which would defeat subsetting.
    """
    ordered = sorted(selected, key=lambda item: item.offset)
    ranges: list[ByteRange] = []
    for record in ordered:
        current = ByteRange(record.offset, record.end)
        if ranges:
            previous = ranges[-1]
            if previous.end is not None and record.offset - previous.end - 1 <= merge_gap_bytes:
                ranges[-1] = ByteRange(previous.start, current.end)
                continue
        ranges.append(current)
    return ranges


def subset_ranges(
    idx_text: str,
    *,
    params: Iterable[str],
    levels: Iterable[str] | None = None,
    forecasts: Iterable[str] | None = None,
    merge_gap_bytes: int = 0,
) -> list[ByteRange]:
    """One-call path from sidecar text to the ranges an adapter should fetch."""
    records = parse_idx(idx_text)
    return byte_ranges(select_records(records, params=params, levels=levels, forecasts=forecasts), merge_gap_bytes=merge_gap_bytes)


def selected_bytes(ranges: Sequence[ByteRange]) -> int | None:
    """Total bytes the ranges will pull, or ``None`` if any is open-ended."""
    total = 0
    for item in ranges:
        if item.length is None:
            return None
        total += item.length
    return total


DEFAULT_TRAILING_MESSAGE_CAP = 16 * 1024 * 1024


def cap_open_range(ranges: Sequence[ByteRange], *, max_trailing_bytes: int = DEFAULT_TRAILING_MESSAGE_CAP) -> list[ByteRange]:
    """Bound a trailing open-ended range so a Range request cannot pull a whole file.

    The sidecar never states the file size, so the last indexed message has no
    end offset. An unbounded ``bytes=N-`` on a 521 MiB GFS file would read the
    remainder into memory, which is exactly what byte-range subsetting exists to
    prevent. A bounded read is safe because the server truncates at EOF: as long
    as the cap exceeds the message, the response is that message and nothing
    else. If the cap is too small the message is short and cfgrib fails loudly,
    which the adapter reports as a decode error rather than a silent gap.
    """
    if max_trailing_bytes <= 0:
        raise GribError("trailing range cap must be positive")
    return [ByteRange(item.start, item.start + max_trailing_bytes - 1) if item.end is None else item for item in ranges]


def open_grib(
    path: Path,
    *,
    filter_by_keys: Mapping[str, Any] | None = None,
    read_keys: Sequence[str] | None = None,
) -> Any:
    """Open GRIB2 through cfgrib. Imported lazily: ecCodes is worker-only.

    ``read_keys`` asks cfgrib to expose additional ecCodes keys as
    ``GRIB_<key>`` variable attributes - used where a field's identity must be
    read from the message's own coded keys rather than from ecCodes' concept
    files (see :func:`declare_wmo_total_cloud`).
    """
    import xarray  # noqa: PLC0415

    backend_kwargs: dict[str, Any] = {"indexpath": ""}
    if filter_by_keys:
        backend_kwargs["filter_by_keys"] = dict(filter_by_keys)
    if read_keys:
        backend_kwargs["read_keys"] = list(read_keys)
    try:
        return xarray.open_dataset(path, engine="cfgrib", backend_kwargs=backend_kwargs)
    except Exception as error:  # cfgrib raises a wide family of decode errors
        raise GribError(f"could not decode {path}: {error}") from error


def _longitude_name(dataset: Any) -> str:
    for name in ("longitude", "lon", "x"):
        if name in dataset.coords:
            return name
    raise GribError("dataset has no recognisable longitude coordinate")


def _latitude_name(dataset: Any) -> str:
    for name in ("latitude", "lat", "y"):
        if name in dataset.coords:
            return name
    raise GribError("dataset has no recognisable latitude coordinate")


def is_curvilinear(dataset: Any, *, lat_name: str | None = None, lon_name: str | None = None) -> bool:
    """True when latitude/longitude are 2-D fields rather than sliceable axes.

    HRDPS and RDPS are published on a rotated lat/lon grid, so cfgrib returns
    ``latitude`` and ``longitude`` as ``(y, x)`` coordinates over anonymous
    dimensions. Nothing on such a dataset can be selected by a lat/lon label.
    """
    lat_name = lat_name or _latitude_name(dataset)
    lon_name = lon_name or _longitude_name(dataset)
    axes = getattr(dataset, "dims", ())
    rectilinear = dataset[lat_name].ndim == 1 and dataset[lon_name].ndim == 1 and lat_name in axes and lon_name in axes
    return not rectilinear


def _wrap_longitudes(dataset: Any, lon_name: str) -> Any:
    """Shift a 0-360 axis onto -180..180 so a signed-degree bbox can select."""
    longitudes = dataset[lon_name]
    if float(longitudes.max()) <= 180:
        return dataset
    shifted = dataset.assign_coords({lon_name: (((longitudes + 180) % 360) - 180)})
    # A 1-D axis has to be re-sorted or the slice straddles the wrap point. A
    # 2-D grid has no axis to sort and is cropped by index anyway.
    return shifted if is_curvilinear(shifted, lon_name=lon_name) else shifted.sortby(lon_name)


def _crop_rectilinear(dataset: Any, lat_name: str, lon_name: str, bounds: Mapping[str, float]) -> Any:
    latitudes = dataset[lat_name]
    descending = float(latitudes[0]) > float(latitudes[-1]) if latitudes.size > 1 else False
    lat_slice = slice(bounds["north"], bounds["south"]) if descending else slice(bounds["south"], bounds["north"])
    return dataset.sel({lat_name: lat_slice, lon_name: slice(bounds["west"], bounds["east"])})


def _crop_curvilinear(dataset: Any, lat_name: str, lon_name: str, bounds: Mapping[str, float]) -> Any:
    """Crop a 2-D grid by index, because it has no coordinate to slice on.

    The box is resolved to the smallest index window that still contains every
    cell inside it. That window is a superset of the box: a rotated grid cannot
    be trimmed to a lat/lon rectangle without regridding, and regridding would
    invent values. The provider's own cells and their real coordinates survive
    unchanged, so what is published is still only what was retrieved.
    """
    latitudes, longitudes = dataset[lat_name], dataset[lon_name]
    if latitudes.dims != longitudes.dims:
        raise GribError("latitude and longitude span different dimensions; the grid is not a curvilinear pair")
    inside = (
        (latitudes >= bounds["south"])
        & (latitudes <= bounds["north"])
        & (longitudes >= bounds["west"])
        & (longitudes <= bounds["east"])
    )
    indexers: dict[str, slice] = {}
    for axis in latitudes.dims:
        others = [name for name in latitudes.dims if name != axis]
        hits = inside.any(dim=others).values.nonzero()[0] if others else inside.values.nonzero()[0]
        if hits.size == 0:
            return dataset.isel({name: slice(0, 0) for name in latitudes.dims})
        indexers[str(axis)] = slice(int(hits[0]), int(hits[-1]) + 1)
    return dataset.isel(indexers)


def crop_to_bbox(dataset: Any, bounds: Mapping[str, float]) -> Any:
    """Crop to a south/west/north/east box, handling 0-360 longitudes.

    Cropping before any other step is what keeps a global run inside the cap.
    Regular grids are sliced by coordinate label; rotated grids, which carry
    2-D latitude/longitude, are cropped by index instead.
    """
    lon_name, lat_name = _longitude_name(dataset), _latitude_name(dataset)
    dataset = _wrap_longitudes(dataset, lon_name)
    if is_curvilinear(dataset, lat_name=lat_name, lon_name=lon_name):
        cropped = _crop_curvilinear(dataset, lat_name, lon_name, bounds)
    else:
        cropped = _crop_rectilinear(dataset, lat_name, lon_name, bounds)
    if cropped[lat_name].size == 0 or cropped[lon_name].size == 0:
        raise GribError("bbox crop produced an empty grid; the run does not cover the domain")
    return cropped


# Coordinates cfgrib attaches to every message that describe the message rather
# than the grid. They are scalar, so they carry no data, but they are still
# coordinates and xarray will refuse to combine two variables whose values
# disagree.
_MESSAGE_SCALAR_COORDS = ("time", "step", "valid_time", "number")


def strip_message_scalars(array: Any) -> Any:
    """Move a decoded message's scalar coordinates into its attributes.

    cfgrib names the vertical coordinate after the GRIB ``typeOfLevel``, so a
    2 m temperature message carries ``heightAboveGround = 2`` and a 10 m wind
    message carries ``heightAboveGround = 10``. Assembling both into one
    ``Dataset`` merges those coordinates, they disagree, and xarray raises
    ``MergeError`` - which is the correct refusal against the wrong data model.
    The level belongs to the variable, not to the dataset it is filed under.

    So each scalar coordinate is recorded in the variable's attrs and then
    dropped. Nothing is discarded: ``level_type`` and ``level_value`` state the
    level the value was actually read at, which is what a reader needs in order
    to know that a temperature is a screen-level temperature. Coordinates with a
    dimension - latitude and longitude, including the 2-D pair a rotated grid
    produces - are untouched.
    """
    level_type = str(array.attrs.get("GRIB_typeOfLevel", "") or "")
    attrs = dict(array.attrs)
    drop: list[str] = []
    for name, coord in array.coords.items():
        if coord.ndim != 0:
            continue
        key = str(name)
        drop.append(key)
        if key in _MESSAGE_SCALAR_COORDS:
            continue
        # The remaining scalar is the vertical level under its typeOfLevel name.
        attrs.setdefault("level_type", level_type or key)
        attrs.setdefault("level_value", coord.item())
    if not drop:
        return array
    stripped = array.drop_vars(drop)
    stripped.attrs = attrs
    return stripped


#: The ecCodes keys whose values identify a GRIB2 field independently of the
#: library's concept files. Request them via ``open_grib(read_keys=...)``.
WMO_IDENTITY_READ_KEYS: tuple[str, ...] = (
    "discipline",
    "parameterCategory",
    "parameterNumber",
    "typeOfFirstFixedSurface",
    "typeOfSecondFixedSurface",
)

#: WMO GRIB2 code table 4.2, discipline 0 (meteorological), category 6
#: (cloud), number 1: "Total cloud cover", unit %.
_WMO_TOTAL_CLOUD_IDENTITY = {
    "GRIB_discipline": 0,
    "GRIB_parameterCategory": 6,
    "GRIB_parameterNumber": 1,
}

WMO_TOTAL_CLOUD_UNITS_BASIS = (
    "units declared from the message's own coded identity: WMO GRIB2 code table 4.2 "
    "discipline 0, parameterCategory 6, parameterNumber 1 is 'Total cloud cover' in "
    "percent; ecCodes decodes the name and units as 'unknown' because the producer "
    "stamps typeOfSecondFixedSurface=255 where ecCodes' concept files expect 8"
)


def _grib_int(attrs: Mapping[str, Any], key: str) -> int | None:
    value = attrs.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def declare_wmo_total_cloud(dataset: Any) -> bool:
    """Declare an ecCodes-``unknown`` field as total cloud from its own WMO keys.

    CWAO's HRDPS/RDPS total-cloud messages decode with name and units literally
    ``'unknown'`` (their ``typeOfSecondFixedSurface=255`` misses ecCodes'
    ``tcc`` concept, which requires 8). The identity is still in the message:
    the coded keys 0/6/1 are WMO table 4.2's "Total cloud cover", %, and those
    keys are retrieved facts, not a guess from the value range. Owner decision
    2026-08-31: publish from the WMO table keys, disclosing the basis.

    Requires the dataset to have been opened with
    ``read_keys=WMO_IDENTITY_READ_KEYS``. Returns True when exactly this
    declaration was applied to a variable; a field whose units ecCodes *did*
    declare is left untouched.
    """
    declared = False
    for name in list(dataset.data_vars):
        variable = dataset[name]
        attrs = variable.attrs
        units = str(attrs.get("units", "")).strip().lower()
        if units not in {"", "unknown"}:
            continue
        if any(_grib_int(attrs, key) != expected for key, expected in _WMO_TOTAL_CLOUD_IDENTITY.items()):
            continue
        # Surface-based whole-column cover: first fixed surface is ground -
        # coded 1, which ecCodes hands back as its abbreviation 'sfc'
        # (verified live 2026-08-31); the second is what the producer left
        # unstated (255).
        first_surface = str(attrs.get("GRIB_typeOfFirstFixedSurface", "")).strip().lower()
        if first_surface not in {"1", "sfc"}:
            continue
        variable.attrs = {
            **attrs,
            "units": "percent",
            "original_units": str(attrs.get("units", "unknown")),
            "units_basis": WMO_TOTAL_CLOUD_UNITS_BASIS,
            "long_name": "Total cloud cover",
        }
        declared = True
    return declared


# --- relative humidity: which saturation the producer divided by ------------
#
# GRIB2 discipline 0 / parameterCategory 1 / parameterNumber 1 is "Relative
# humidity, %" and says NOTHING about the phase of the saturation vapour
# pressure in the denominator. There is no coded key for it, so the identity
# CANNOT be read out of the message the way ``declare_wmo_total_cloud`` reads
# total cloud - it has to be measured. It matters enormously: at -20 degC
# e_s,water / e_s,ice ~ 1.21, so the same air reads RH 0.85 on one convention
# and ~1.03 on the other, which is the difference between clear and overcast
# under any threshold scheme.
#
# Measured here on 2026-09-01, 12Z PT003H (ECCC) and gfs.20260901/06 f003
# (NOAA), by reconstructing vapour pressure from the model's OWN specific
# humidity on the same level and dividing by Buck (1981) saturation over
# water and over ice:
#
#   HRDPS  RH_ISBL_0500                 -25..-28 degC  bias vs water +0.08 %,
#                                                      vs ice       +19.09 %
#   RDPS   RelativeHumidity_IsbL-0500   -25..-34 degC  bias vs water -0.02 %,
#                                                      vs ice       +20.17 %
#   GFS    RH:500 mb                    -25..-50 degC  bias vs water -24.48 %,
#                                                      vs ice        -0.21 %
#
# So the two ECCC models divide by saturation over LIQUID WATER at every
# temperature, and GFS does not. Resolving GFS's blend weight per 5 degC bin
# at 850 and 700 mb (solving e_s,pub = a*e_s,water + (1-a)*e_s,ice) gives
# a = 1.00 at T >= 0 degC, 0.00 at T <= -20 degC, and 0.12 / 0.37 / 0.62 /
# 0.80 at the midpoints of [-20,-15), [-15,-10), [-10,-5), [-5,0) - i.e. a
# linear ramp in temperature between 253.16 K and 273.16 K, which is NCEP's
# standard mixed-phase saturation function.
#
# Consequence for anything thresholding RH: a threshold calibrated on ECCC RH
# is NOT transferable to GFS RH below freezing, where GFS reads up to ~24 %
# higher for identical air.
RH_PHASE_LIQUID_WATER = "liquid_water"
RH_PHASE_MIXED_LINEAR_253K_273K = "mixed_linear_253K_273K"

ECCC_RH_PHASE_BASIS = (
    "measured, not coded: GRIB2 0/1/1 carries no phase key, so the convention was "
    "determined on 2026-09-01 by reconstructing vapour pressure from the model's own "
    "SPFH on the same isobaric level and comparing against Buck (1981) saturation over "
    "water and over ice at -25 degC and below. HRDPS 500 hPa matched water to 0.08 % "
    "and missed ice by 19.1 %; RDPS 500 hPa matched water to 0.13 % and missed ice by "
    "20.2 %. Both models divide by saturation over liquid water at all temperatures."
)

GFS_RH_PHASE_BASIS = (
    "measured, not coded: GRIB2 0/1/1 carries no phase key, so the convention was "
    "determined on 2026-09-01 from gfs.20260901/06 f003 by reconstructing vapour "
    "pressure from the message's own SPFH on the same level. At 500 mb below -25 degC "
    "the published RH matches saturation over ice to 0.24 % and misses water by 24.5 %. "
    "Solving the blend weight per temperature bin at 850 and 700 mb gives a linear ramp "
    "in temperature from all-ice at 253.16 K to all-water at 273.16 K. A threshold "
    "calibrated on ECCC's liquid-water RH is not transferable to this field below 0 degC."
)


def declare_rh_phase(variable: Any, *, convention: str, basis: str) -> Any:
    """Stamp the measured saturation-phase convention onto a humidity variable.

    Unlike ``declare_wmo_total_cloud`` - which reads a declaration out of the
    message's own coded keys - this records a MEASURED fact, because GRIB2
    codes no key for it. The basis string travels with the data so a reader
    can see how the claim was established rather than trusting the name.
    """
    variable.attrs = {
        **variable.attrs,
        "rh_phase_convention": convention,
        "rh_phase_basis": basis,
    }
    return variable


def normalize_units(dataset: Any) -> Any:
    """Convert to project units, leaving anything unrecognised untouched.

    Silent passthrough is deliberate: inventing a conversion is worse than
    surfacing the provider's own units in provenance.
    """
    result = dataset
    for name in list(result.data_vars):
        variable = result[name]
        units = str(variable.attrs.get("units", "")).strip()
        if units in _KELVIN_NAMES:
            converted = variable - 273.15
            converted.attrs = {**variable.attrs, "units": "degC", "original_units": units}
            result[name] = converted
        elif units in _FRACTION_NAMES and name.lower().startswith(("r", "tcc", "lcc", "hcc", "mcc")):
            converted = variable * 100.0
            converted.attrs = {**variable.attrs, "units": "percent", "original_units": units}
            result[name] = converted
        elif units == "Pa" and any(k in name.lower() for k in ("pres", "prmsl", "msl", "slp", "pressure")):
            converted = variable / 100.0
            converted.attrs = {**variable.attrs, "units": "hPa", "original_units": units}
            result[name] = converted
        elif units in {"%", "percent"}:
            # ``original_units`` may already record how these units were
            # declared (see ``declare_wmo_total_cloud``); keep that record.
            variable.attrs = {
                **variable.attrs,
                "units": "percent",
                "original_units": variable.attrs.get("original_units", units),
            }
        elif units in {"m/s", "m s**-1", "m s-1"}:
            variable.attrs = {**variable.attrs, "units": "m s-1", "original_units": units}
        elif units in {"Pa s**-1", "Pa/s", "Pa s-1"}:
            # Omega, d(pressure)/dt: negative is ascent. Spelled three ways by
            # ecCodes, cfgrib and wgrib2 for the same WMO 0/2/8 quantity, so
            # the spelling is canonicalised while the value is untouched.
            variable.attrs = {**variable.attrs, "units": "Pa s-1", "original_units": units}
        elif units in {"kg m**-2", "kg/m^2", "kg m-2"}:
            variable.attrs = {**variable.attrs, "units": "kg m-2", "original_units": units}
    return result


def normalize_precipitation(dataset: Any, name: str, *, interval_hours: float) -> Any:
    """Tag an accumulation with its interval; never divide it into a rate.

    ``api.weather_api.science.precipitation_interval_hours`` states the rule:
    an accumulation over an interval is a different quantity from a rate, and
    converting between them silently invents information.
    """
    if interval_hours <= 0:
        raise GribError("precipitation accumulation interval must be positive")
    if name not in dataset.data_vars:
        raise GribError(f"{name} is not present in the dataset")
    variable = dataset[name]
    units = str(variable.attrs.get("units", "")).strip()
    variable.attrs = {
        **variable.attrs,
        "units": units or "kg m-2",
        "original_units": units,
        "cell_methods": "time: sum",
        "accumulation_interval_hours": float(interval_hours),
        "semantics": "accumulation over the stated interval; not a rate",
    }
    return dataset


def write_zarr(dataset: Any, destination: Path) -> Path:
    """Write a bbox-cropped dataset as a single zipped Zarr artifact.

    Zarr is written to a temporary directory store first and only then zipped.
    Writing straight into a ``ZipStore`` makes zarr append rather than replace
    entries, which emitted ``UserWarning: Duplicate name: 'x/zarr.json'`` and
    left two copies of every metadata document in the archive. The zip is built
    with sorted entries and no compression so the same dataset always produces
    the same bytes, which is what makes the SHA-256 in ``artifact_revisions``
    mean something.

    One file per revision keeps the immutable-object upload and the SHA-256 in
    ``artifact_revisions`` honest.
    """
    import xarray  # noqa: PLC0415
    import zarr  # noqa: PLC0415

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    expected_vars = set(map(str, dataset.data_vars))
    expected_coords = set(map(str, dataset.coords))

    scratch = Path(tempfile.mkdtemp(prefix="zarr-", dir=str(destination.parent)))
    try:
        directory = scratch / "store.zarr"
        dataset.to_zarr(zarr.storage.LocalStore(str(directory)), mode="w", consolidated=False)

        entries = sorted(path for path in directory.rglob("*") if path.is_file())
        with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_STORED) as archive:
            for path in entries:
                info = zipfile.ZipInfo(str(path.relative_to(directory).as_posix()), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    # Round-trip before the caller can hash and upload it: an artifact that does
    # not reopen is worse than no artifact, because it publishes as evidence.
    store = zarr.storage.ZipStore(str(destination), mode="r")
    try:
        reopened = xarray.open_zarr(store, consolidated=False)
        missing = (expected_vars - set(map(str, reopened.data_vars))) | (expected_coords - set(map(str, reopened.coords)))
        if missing:
            raise GribError(f"zarr round-trip lost {', '.join(sorted(missing))} from {destination.name}")
    finally:
        store.close()
    return destination
