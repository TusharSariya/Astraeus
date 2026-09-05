"""Bounded experimental numeric GeoMet WCS acquisition.

This module is deliberately not imported by :mod:`ingest.adapters` and does
not register an adapter.  The existing ``eccc-hrdps`` and ``eccc-rdps``
production identities continue to belong to the Datamart GRIB adapters.  WCS
is a distinct access path whose source contract is still proposed.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlencode

import numpy
import xarray
from PIL import Image

from ingest.adapters.eccc_geomet import (
    ATTRIBUTION,
    GEOMET_BASE_URL,
    LICENCE,
    GeoMetClient,
    LayerCapability,
)
from ingest.contract import AVALON_CORE_BOUNDS, Artifact, MEDIA_ZARR
from ingest.grib import write_zarr
from ingest.http import PoliteClient

UTC = timezone.utc
WCS_VERSION = "2.0.1"
WCS_CAPABILITIES_MAX_BYTES = 2 << 20
DESCRIBE_MAX_BYTES = 64 << 10
MAX_COVERAGE_BYTES = 2 << 20
MAX_FIELDS_PER_OPERATION = 64
MAX_PIXELS_PER_COVERAGE = 200_000
NATIVE_GRID_TOLERANCE = 1e-6

HRDPS_PRESSURE_LEVELS_HPA = (
    50, 100, 150, 175, 200, 225, 250, 275, 300, 350, 400, 450, 500, 550,
    600, 650, 700, 750, 800, 850, 875, 900, 925, 950, 970, 985, 1000, 1015,
)
GLOBAL_PRESSURE_LEVELS_HPA = (10, 20, 30) + HRDPS_PRESSURE_LEVELS_HPA
HEIGHTS_M = (40, 80, 120)
WEONG_PRODUCTS = (
    "AirTemp", "BlowingSnow-Prob", "BlowingSnowPresence", "DewPointTemp",
    "DominantPrecipType", "Drizzle-Prob", "FreezingDrizzle-Prob",
    "FreezingPrecip-Prob", "FreezingPrecipCondAmt", "FreezingRain-Prob",
    "IceFogVisibility", "IcePellets-Prob", "IcePelletsCondAmt",
    "InstantPrecipType", "LandWater-Proportion", "LiquidFogVisibility",
    "LiquidPrecip-Prob", "LiquidPrecipCondAmt", "Orography", "Precip-Prob",
    "PrecipCharacter", "PrecipCondAmt", "Rain-Prob",
    "SecondMostCommonPrecipType", "SkyState", "Snow-Prob",
    "SnowLevelHeight", "SnowSqualls-Prob", "SolidSnowCondAmt",
    "Thunderstorm-Prob", "TotalPrecipIntensityIndex", "WindDir", "WindGust",
    "WindSpeed",
)


class WCSResponseError(RuntimeError):
    """GeoMet answered without a usable numeric coverage."""


@dataclass(frozen=True)
class GridContract:
    source_id: str
    product: str
    prefix: str
    spacing_degrees: float
    width: int
    height: int


GRID_CONTRACTS = {
    "hrdps": GridContract("eccc-hrdps", "HRDPS continental 2.5 km", "HRDPS.CONTINENTAL", 0.0225, 178, 89),
    "rdps": GridContract("eccc-rdps", "RDPS 10 km", "RDPS_10km", 0.090298, 45, 23),
    "gdps": GridContract("eccc-gdps", "GDPS 15 km", "GDPS_15km", 0.15, 27, 14),
    "geml": GridContract("eccc-gdps", "GEML 25 km", "GDPS-GEML_25km", 0.25, 16, 9),
}


def grid_contract_for(coverage_id: str) -> GridContract:
    if coverage_id.startswith("HRDPS"):
        return GRID_CONTRACTS["hrdps"]
    if coverage_id.startswith("RDPS"):
        return GRID_CONTRACTS["rdps"]
    if coverage_id.startswith("GDPS_15km") or coverage_id.startswith("GDPS-WEonG_15km"):
        return GRID_CONTRACTS["gdps"]
    if coverage_id.startswith("GDPS-GEML_25km"):
        return GRID_CONTRACTS["geml"]
    raise WCSResponseError(f"no numeric grid contract for {coverage_id}")


@dataclass(frozen=True)
class CoverageField:
    coverage_id: str
    variable: str
    disposition: str = "experimental-retrievable"


@dataclass(frozen=True)
class CoverageDescription:
    coverage_id: str
    crs: str
    envelope_axis_labels: tuple[str, ...]
    grid_axis_labels: tuple[str, ...]
    longitude_spacing: float
    latitude_spacing: float


def parse_description(path: Path) -> CoverageDescription:
    root = ElementTree.parse(path).getroot()
    coverage = next((node.text or "").strip() for node in root.iter() if node.tag.endswith("CoverageId"))
    envelope = next(node for node in root.iter() if node.tag.endswith("Envelope"))
    grid = next(node for node in root.iter() if node.tag.endswith("RectifiedGrid"))
    grid_axes = next(node for node in grid if node.tag.endswith("axisLabels"))
    vectors = [tuple(float(value) for value in (node.text or "").split())
               for node in grid.iter() if node.tag.endswith("offsetVector")]
    if len(vectors) != 2 or any(len(vector) != 2 for vector in vectors):
        raise WCSResponseError("DescribeCoverage does not carry a two-axis rectified grid")
    return CoverageDescription(
        coverage_id=coverage,
        crs=str(envelope.attrib.get("srsName", "")),
        envelope_axis_labels=tuple(str(envelope.attrib.get("axisLabels", "")).split()),
        grid_axis_labels=tuple((grid_axes.text or "").split()),
        longitude_spacing=max(abs(vector[1]) for vector in vectors),
        latitude_spacing=max(abs(vector[0]) for vector in vectors),
    )


def _height_fields(model: str) -> tuple[CoverageField, ...]:
    if model == "hrdps":
        mappings = (("TT", "temperature"), ("TD", "dew_point"), ("HR", "relative_humidity"),
                    ("HU", "specific_humidity"), ("WSPD", "wind_speed"), ("WD", "wind_direction"))
        return tuple(CoverageField(f"HRDPS.CONTINENTAL_{code}_{height}m", f"{name}_{height}m")
                     for code, name in mappings for height in HEIGHTS_M)
    prefix = GRID_CONTRACTS[model].prefix
    mappings = (("AirTemp", "temperature"), ("SpecificHumidity", "specific_humidity"),
                ("WindSpeed", "wind_speed"), ("WindDir", "wind_direction"))
    return tuple(CoverageField(f"{prefix}_{code}_{height}m", f"{name}_{height}m")
                 for code, name in mappings for height in HEIGHTS_M)


def contract_fields(model: str) -> tuple[CoverageField, ...]:
    """Exact current selected coverage contract, including explicit absences."""
    grid = GRID_CONTRACTS[model]
    if model == "hrdps":
        pressure = tuple(CoverageField(f"{grid.prefix}.PRES_HR.{level}", "relative_humidity_pressure")
                         for level in HRDPS_PRESSURE_LEVELS_HPA)
        diagnostics = (
            CoverageField(f"{grid.prefix}_HPBL", "boundary_layer_height"),
            CoverageField(f"{grid.prefix}_SKINT", "skin_temperature"),
            CoverageField(f"{grid.prefix}_ICEC", "sea_ice_fraction"),
        )
    else:
        pressure = tuple(CoverageField(f"{grid.prefix}_RelativeHumidity_{level}mb", "relative_humidity_pressure")
                         for level in GLOBAL_PRESSURE_LEVELS_HPA)
        diagnostics = (
            CoverageField(f"{grid.prefix}_PlanetaryBoundaryLayerHeight", "boundary_layer_height"),
            CoverageField(f"{grid.prefix}_RadiativeTemp", "radiative_surface_temperature"),
            CoverageField(f"{grid.prefix}_SeaIceFraction", "sea_ice_fraction"),
        )
    weong_prefix = {"hrdps": "HRDPS-WEonG_2.5km", "rdps": "RDPS-WEonG_10km", "gdps": "GDPS-WEonG_15km"}[model]
    weong = tuple(CoverageField(f"{weong_prefix}_{name}", f"weong_{_snake(name)}") for name in WEONG_PRODUCTS)
    astronomy = () if model != "rdps" else (
        CoverageField("RDPS_10km_SeeingIndex", "seeing_class_eccc"),
        CoverageField("RDPS_10km_SkyTransparencyIndex", "transparency_class_eccc"),
    )
    absent = (
        CoverageField(f"{model}:cloud_low", "cloud_low", "not-published"),
        CoverageField(f"{model}:cloud_middle", "cloud_middle", "not-published"),
        CoverageField(f"{model}:cloud_high", "cloud_high", "not-published"),
        CoverageField(f"{model}:cloud_ceiling", "cloud_ceiling", "not-published"),
        CoverageField(f"{model}:precipitable_water", "precipitable_water", "not-published"),
    )
    return _height_fields(model) + pressure + diagnostics + weong + astronomy + absent


def _snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return value.replace("-", "_").lower()


def raw_field(coverage_id: str) -> CoverageField:
    """An unmapped coverage preserved under an explicit raw namespace.

    This is an experimental storage destination, not a canonical field
    meaning.  It allows a bounded acquisition to retain producer bytes and
    metadata while semantic normalization remains deferred.
    """
    return CoverageField(coverage_id, f"raw__{_snake(coverage_id)}")


def parse_coverage_ids(path: Path) -> frozenset[str]:
    root = ElementTree.parse(path).getroot()
    return frozenset((node.text or "").strip() for node in root.iter() if node.tag.endswith("CoverageId"))


def _service_error(head: bytes, content_type: str) -> str | None:
    text = head.decode("utf-8", "replace")
    lowered = content_type.lower()
    if "xml" not in lowered and "html" not in lowered and not text.lstrip().startswith("<"):
        return None
    if not any(token in text for token in ("ExceptionReport", "ServiceException", "<html", "<HTML")):
        return None
    try:
        root = ElementTree.fromstring(text)
        messages = [str(node.text).strip() for node in root.iter() if node.text and str(node.text).strip()]
        return "; ".join(messages[-3:])[:500]
    except ElementTree.ParseError:
        return text[:500]


@dataclass
class GeoMetWCSClient:
    client: PoliteClient | None = None
    base_url: str = GEOMET_BASE_URL.rstrip("/")
    scratch_dir: Path | None = None

    def __post_init__(self) -> None:
        self._owned = None
        self._wms = GeoMetClient(client=self.client, base_url=self.base_url)

    def _http(self) -> PoliteClient:
        if self.client is not None:
            return self.client
        if self._owned is None:
            self._owned = PoliteClient(attempts=2, timeout_seconds=45)
            self._wms.client = self._owned
        return self._owned

    def close(self) -> None:
        self._wms.close()
        if self._owned is not None:
            self._owned.close()
            self._owned = None

    def _url(self, request: str, **params: object) -> str:
        query = {"SERVICE": "WCS", "VERSION": WCS_VERSION, "REQUEST": request, **params}
        return f"{self.base_url}?{urlencode(query, doseq=True)}"

    def inventory(self, destination: Path) -> frozenset[str]:
        self._http().download(self._url("GetCapabilities"), destination, max_bytes=WCS_CAPABILITIES_MAX_BYTES)
        return parse_coverage_ids(destination)

    def metadata(self, coverage_id: str) -> LayerCapability:
        return self._wms.capabilities(coverage_id)

    def description(self, coverage_id: str) -> CoverageDescription:
        base = self.scratch_dir or Path("/tmp")
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"describe-{_snake(coverage_id)}.xml.part"
        try:
            self._http().download(self._url("DescribeCoverage", COVERAGEID=coverage_id), path,
                                  max_bytes=DESCRIBE_MAX_BYTES)
            error = _service_error(path.read_bytes()[:4096], "application/xml")
            if error:
                raise WCSResponseError(f"DescribeCoverage failed: {error}")
            return parse_description(path)
        finally:
            path.unlink(missing_ok=True)

    def fetch(
        self, field: CoverageField, *, valid_time: datetime, reference_time: datetime | None,
        bounds: Mapping[str, float], width: int, height: int, destination: Path,
    ) -> tuple[Path, str]:
        if field.disposition != "experimental-retrievable":
            raise WCSResponseError(f"{field.variable} is {field.disposition}")
        if width <= 0 or height <= 0 or width * height > MAX_PIXELS_PER_COVERAGE:
            raise ValueError("requested WCS grid exceeds the finite pixel bound")
        capability = self.metadata(field.coverage_id)
        description = self.description(field.coverage_id)
        if description.coverage_id != field.coverage_id:
            raise WCSResponseError("DescribeCoverage returned a different coverage identity")
        if not description.crs.endswith("/4326") or description.grid_axis_labels != ("long", "lat"):
            raise WCSResponseError("coverage is not the expected EPSG:4326 long/lat rectified grid")
        expected_grid = grid_contract_for(field.coverage_id)
        if (
            abs(description.longitude_spacing - expected_grid.spacing_degrees) > NATIVE_GRID_TOLERANCE
            or abs(description.latitude_spacing - expected_grid.spacing_degrees) > NATIVE_GRID_TOLERANCE
        ):
            raise WCSResponseError(
                f"coverage spacing {(description.longitude_spacing, description.latitude_spacing)} "
                f"does not match declared {expected_grid.spacing_degrees} degrees"
            )
        advertised_time = capability.time.nearest(valid_time) if capability.time else None
        if advertised_time is None:
            raise WCSResponseError(f"{field.coverage_id} advertises no valid-time dimension")
        advertised_run = None
        if reference_time is not None:
            if capability.reference_time is None:
                raise WCSResponseError(f"{field.coverage_id} advertises no reference-time dimension")
            advertised_run = capability.reference_time.nearest(reference_time)
        params = {
            "COVERAGEID": field.coverage_id,
            "FORMAT": "image/tiff",
            "SUBSET": (f"long({bounds['west']},{bounds['east']})", f"lat({bounds['south']},{bounds['north']})"),
            "SCALESIZE": (f"long({width})", f"lat({height})"),
            "TIME": advertised_time.isoformat().replace("+00:00", "Z"),
            "DIM_REFERENCE_TIME": None if advertised_run is None else advertised_run.isoformat().replace("+00:00", "Z"),
        }
        url = self._url("GetCoverage", **{key: value for key, value in params.items() if value is not None})
        self._http().download(url, destination, max_bytes=MAX_COVERAGE_BYTES)
        head = destination.read_bytes()[:4096]
        with destination.open("rb") as stream:
            signature = stream.read(4)
        if signature not in (b"II*\x00", b"MM\x00*"):
            error = _service_error(head, "application/xml")
            destination.unlink(missing_ok=True)
            raise WCSResponseError(f"GeoMet returned a non-TIFF coverage: {error or head[:120]!r}")
        return destination, url

    def fetch_many(self, fields: Sequence[CoverageField], **kwargs: object) -> list[tuple[Path, str]]:
        """Fetch a bounded list sequentially; no provider concurrency is used."""
        if len(fields) > MAX_FIELDS_PER_OPERATION:
            raise ValueError(f"operation selects {len(fields)} fields; maximum is {MAX_FIELDS_PER_OPERATION}")
        return [self.fetch(field, **kwargs) for field in fields]


def decode_geotiff(path: Path, field: CoverageField, *, valid_time: datetime, expected_bounds: Mapping[str, float], expected_width: int, expected_height: int) -> xarray.Dataset:
    """Decode one numeric float GeoTIFF and validate its requested geometry."""
    with Image.open(path) as image:
        values = numpy.asarray(image, dtype=numpy.float32)
        tags = image.tag_v2
        scale = tuple(float(value) for value in tags.get(33550, ()))
        tie = tuple(float(value) for value in tags.get(33922, ()))
        nodata_raw = tags.get(42113)
    if values.shape != (expected_height, expected_width):
        raise WCSResponseError(f"coverage shape {values.shape} != requested {(expected_height, expected_width)}")
    if len(scale) < 2 or len(tie) < 6 or scale[0] <= 0 or scale[1] <= 0:
        raise WCSResponseError("coverage lacks usable GeoTIFF scale/tie-point metadata")
    west, north = tie[3], tie[4]
    if abs(west - expected_bounds["west"]) > NATIVE_GRID_TOLERANCE or abs(north - expected_bounds["north"]) > NATIVE_GRID_TOLERANCE:
        raise WCSResponseError("coverage tie point does not match the requested subset")
    longitude = west + numpy.arange(expected_width, dtype=numpy.float64) * scale[0]
    latitude = north - numpy.arange(expected_height, dtype=numpy.float64) * scale[1]
    nodata = None
    if nodata_raw is not None:
        try:
            raw = nodata_raw[0] if isinstance(nodata_raw, tuple) else nodata_raw
            nodata = float(str(raw).strip().rstrip("\x00"))
        except ValueError:
            nodata = None
    if nodata is not None:
        values = numpy.where(values == nodata, numpy.nan, values)
    data = values[numpy.newaxis, :, :]
    return xarray.Dataset(
        {field.variable: (("valid_time", "latitude", "longitude"), data)},
        coords={"valid_time": [numpy.datetime64(valid_time.astimezone(UTC).replace(tzinfo=None), "ns")], "latitude": latitude, "longitude": longitude},
    )


def fetch_artifact(
    client: GeoMetWCSClient, field: CoverageField, *, valid_time: datetime,
    reference_time: datetime | None, workdir: Path, model: str = "rdps",
    bounds: Mapping[str, float] = AVALON_CORE_BOUNDS,
) -> Artifact:
    """Fetch, validate, normalize and round-trip one immutable WCS artifact."""
    grid = grid_contract_for(field.coverage_id)
    if GRID_CONTRACTS[model].source_id != grid.source_id:
        raise ValueError(f"{field.coverage_id} does not belong to model {model}")
    workdir.mkdir(parents=True, exist_ok=True)
    tiff = workdir / f"{_snake(field.coverage_id)}.tif"
    tiff, url = client.fetch(field, valid_time=valid_time, reference_time=reference_time,
                             bounds=bounds, width=grid.width, height=grid.height, destination=tiff)
    dataset = decode_geotiff(tiff, field, valid_time=valid_time, expected_bounds=bounds,
                             expected_width=grid.width, expected_height=grid.height)
    capability = client.metadata(field.coverage_id)
    raw_units, units, recognised = capability.units
    if field.variable in {"seeing_class_eccc", "transparency_class_eccc"} and raw_units is None:
        units, raw_units, recognised = "1", "unlabelled class index", True
    dataset[field.variable].attrs.update({"units": units or "unknown", "original_units": raw_units or "unknown"})
    output = write_zarr(dataset, workdir / f"{_snake(field.coverage_id)}.zarr.zip")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    provenance = {
        "adapter_version": "geomet-wcs-experimental-v1",
        "access_path": "GeoMet WCS 2.0.1",
        "coverage_id": field.coverage_id,
        "source_uri": url,
        "valid_time": valid_time.astimezone(UTC).isoformat(),
        "run_time": None if reference_time is None else reference_time.astimezone(UTC).isoformat(),
        "run_identity_status": "requested_unverified" if reference_time is not None else "unknown",
        "native_crs": "EPSG:4326",
        "stored_geometry": "rectilinear_grid",
        "requested_bounds": dict(bounds),
        "requested_shape": [grid.height, grid.width],
        "units_as_published": raw_units,
        "units_recognised": recognised,
        "evidence_classes": ["retrieved"],
        "quality": {"status": "unknown", "flags": ["experimental_source_contract_pending"]},
        "sha256": digest,
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        "operational": False,
    }
    return Artifact(field.variable, MEDIA_ZARR, output, provenance)


def fetch_pressure_profile_artifact(
    client: GeoMetWCSClient, fields: Sequence[CoverageField], levels_hpa: Sequence[int], *,
    valid_time: datetime, reference_time: datetime | None, workdir: Path, model: str,
    bounds: Mapping[str, float] = AVALON_CORE_BOUNDS,
) -> Artifact:
    """Assemble exact per-level WCS coverages on one pressure coordinate."""
    if not fields or len(fields) != len(levels_hpa):
        raise ValueError("pressure fields and levels must be non-empty and have equal length")
    if len(fields) > MAX_FIELDS_PER_OPERATION:
        raise ValueError(f"profile selects {len(fields)} fields; maximum is {MAX_FIELDS_PER_OPERATION}")
    if len(set(levels_hpa)) != len(levels_hpa) or any(level <= 0 for level in levels_hpa):
        raise ValueError("pressure levels must be unique positive hPa values")
    if {field.variable for field in fields} != {"relative_humidity_pressure"}:
        raise ValueError("this profile contract accepts only relative_humidity_pressure coverages")
    grid = grid_contract_for(fields[0].coverage_id)
    if GRID_CONTRACTS[model].source_id != grid.source_id:
        raise ValueError(f"profile does not belong to model {model}")
    if any(grid_contract_for(field.coverage_id) != grid for field in fields):
        raise ValueError("one profile artifact cannot combine different native grids")
    workdir.mkdir(parents=True, exist_ok=True)
    arrays = []
    coverage_ids = []
    raw_units: str | None = None
    units: str | None = None
    recognised = False
    for field, level in zip(fields, levels_hpa):
        tiff = workdir / f"{_snake(field.coverage_id)}.tif"
        client.fetch(field, valid_time=valid_time, reference_time=reference_time, bounds=bounds,
                     width=grid.width, height=grid.height, destination=tiff)
        dataset = decode_geotiff(tiff, field, valid_time=valid_time, expected_bounds=bounds,
                                 expected_width=grid.width, expected_height=grid.height)
        capability = client.metadata(field.coverage_id)
        field_raw, field_units, field_recognised = capability.units
        if coverage_ids and (field_raw, field_units) != (raw_units, units):
            raise WCSResponseError("pressure coverages disagree on published units")
        raw_units, units, recognised = field_raw, field_units, field_recognised
        arrays.append(dataset[field.variable].expand_dims(pressure=[int(level)]))
        coverage_ids.append(field.coverage_id)
    stacked = xarray.concat(arrays, dim="pressure").to_dataset(name="relative_humidity_pressure")
    stacked["relative_humidity_pressure"].attrs.update({
        "units": units or "unknown", "original_units": raw_units or "unknown",
        "pressure_units": "hPa",
    })
    output = write_zarr(stacked, workdir / "relative_humidity_pressure.zarr.zip")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    provenance = {
        "adapter_version": "geomet-wcs-experimental-v1",
        "access_path": "GeoMet WCS 2.0.1",
        "coverage_ids": coverage_ids,
        "pressure_levels_hpa": list(map(int, levels_hpa)),
        "valid_time": valid_time.astimezone(UTC).isoformat(),
        "run_time": None if reference_time is None else reference_time.astimezone(UTC).isoformat(),
        "run_identity_status": "requested_unverified" if reference_time is not None else "unknown",
        "native_crs": "EPSG:4326",
        "stored_geometry": "rectilinear_pressure_grid",
        "requested_bounds": dict(bounds),
        "requested_shape": [grid.height, grid.width],
        "units_as_published": raw_units,
        "units_recognised": recognised,
        "evidence_classes": ["retrieved"],
        "quality": {"status": "unknown", "flags": ["experimental_source_contract_pending"]},
        "sha256": digest,
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        "operational": False,
    }
    return Artifact("relative_humidity_pressure", MEDIA_ZARR, output, provenance)


def audit_inventory(advertised: Iterable[str], model: str) -> list[dict[str, str]]:
    """Return every selected field with retrieved/missing/unsupported status."""
    ids = frozenset(advertised)
    rows = []
    for field in contract_fields(model):
        disposition = field.disposition
        if disposition == "experimental-retrievable":
            disposition = "advertised" if field.coverage_id in ids else "missing"
        rows.append({"coverage_id": field.coverage_id, "variable": field.variable, "disposition": disposition})
    return rows
