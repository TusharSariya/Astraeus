"""Bounded GOES-19 ABI L2+ acquisition probes for issue #101.

Each adapter instance retrieves one producer product from NOAA's anonymous
public bucket, crops its fixed grid to the evidence box, preserves the native
pixels and quality flags, and stages one non-operational Zarr artifact.  The
modules are intentionally not scheduler-registered: this is experimental
acquisition evidence, not an owner-authorized production promotion.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy
import xarray

from ingest.adapters.goes_abi import GOES_S3_BASE, _hour_prefix, _index_window, parse_bucket_keys, parse_scan_stamp
from ingest.contract import EVIDENCE_BOX_BOUNDS, MEDIA_ZARR, AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, declared_classes, validate_run
from ingest.grib import write_zarr

UTC = timezone.utc
DISCOVERY_HOURS = 6
MAX_GRANULE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class FieldMap:
    native: str
    canonical: str
    units: str
    native_units: str
    scale: float = 1.0
    offset: float = 0.0
    valid: tuple[float, float] | None = None


@dataclass(frozen=True)
class Product:
    product_id: str
    logical_name: str
    fields: tuple[FieldMap, ...]
    quality: str
    cadence_seconds: int
    good_quality_values: tuple[int, ...] = (0,)


PRODUCTS: dict[str, Product] = {
    "ABI-L2-CCLF": Product("ABI-L2-CCLF", "abi_cclf", (
        FieldMap("TCF", "cloud_fraction_total_satellite", "percent", "1", scale=100.0, valid=(0.0, 100.0)),
        *(FieldMap(f"CF{i}", f"cloud_fraction_layer_{i}", "percent", "1", valid=(0.0, 100.0)) for i in range(1, 6)),
        FieldMap("CL", "cloud_layer_flag", "code", "1", valid=(0.0, 127.0)),
    ), "DQF", 3600),
    "ABI-L2-ACTPF": Product("ABI-L2-ACTPF", "abi_actpf", (FieldMap("Phase", "cloud_top_phase", "code", "1", valid=(0.0, 5.0)),), "DQF", 600),
    "ABI-L2-ACHTF": Product("ABI-L2-ACHTF", "abi_achtf", (FieldMap("TEMP", "cloud_top_temperature", "K", "K"),), "DQF", 600),
    "ABI-L2-CODF": Product("ABI-L2-CODF", "abi_codf", (FieldMap("COD", "cloud_optical_depth", "1", "1"),), "DQF", 600, (1, 2)),
    "ABI-L2-COD2KMF": Product("ABI-L2-COD2KMF", "abi_cod2kmf", (FieldMap("COD", "cloud_optical_depth", "1", "1"),), "DQF", 600, (1, 2)),
    "ABI-L2-CPSF": Product("ABI-L2-CPSF", "abi_cpsf", (FieldMap("CPS", "cloud_particle_size", "um", "um"),), "DQF", 600, (1, 2)),
    "ABI-L2-TPWF": Product("ABI-L2-TPWF", "abi_tpwf", (FieldMap("TPW", "precipitable_water", "kg m-2", "mm"),), "DQF_Overall", 600),
    "ABI-L2-LVMPF": Product("ABI-L2-LVMPF", "abi_lvmpf", (FieldMap("LVM", "relative_humidity_pressure", "percent", "percent", valid=(0.0, 100.0)),), "DQF_Overall", 600),
    "ABI-L2-LVTPF": Product("ABI-L2-LVTPF", "abi_lvtpf", (FieldMap("LVT", "temperature_pressure", "degC", "K", offset=-273.15),), "DQF_Overall", 600),
    "ABI-L2-DSIF": Product("ABI-L2-DSIF", "abi_dsif", (
        FieldMap("LI", "lifted_index", "K", "K"), FieldMap("CAPE", "convective_available_potential_energy", "J kg-1", "J kg-1"),
        FieldMap("TT", "total_totals_index", "K", "K"), FieldMap("SI", "showalter_index", "K", "K"), FieldMap("KI", "k_index", "K", "K"),
    ), "DQF_Overall", 600),
    "ABI-L2-SSTF": Product("ABI-L2-SSTF", "abi_sstf", (FieldMap("SST", "sea_surface_skin_temperature", "K", "K"),), "DQF", 3600),
    "ABI-L2-RRQPEF": Product("ABI-L2-RRQPEF", "abi_rrqpef", (FieldMap("RRQPE", "precipitation_rate", "mm h-1", "mm h-1"),), "DQF", 600),
}


def parse_product_key(key: str, product_id: str) -> str | None:
    name = key.rsplit("/", 1)[-1]
    prefix = f"OR_{product_id}-M6_G19_s"
    if not name.startswith(prefix) or not name.endswith(".nc"):
        return None
    stamp = name[len(prefix):].split("_", 1)[0]
    return stamp if len(stamp) == 14 and stamp.isdigit() else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crop_product(path: Path, product: Product, *, bounds: Mapping[str, float]) -> tuple[xarray.Dataset, dict[str, Any]]:
    """Crop one fixed-grid product without interpolating producer values."""
    from pyproj import CRS, Transformer  # noqa: PLC0415

    with xarray.open_dataset(path, engine="netcdf4") as source:
        missing = [item.native for item in product.fields if item.native not in source]
        if missing or product.quality not in source or "goes_imager_projection" not in source:
            raise ValueError(f"{product.product_id} missing required variables {missing or [product.quality, 'goes_imager_projection']}")
        attrs = dict(source["goes_imager_projection"].attrs)
        required_projection = ("perspective_point_height", "longitude_of_projection_origin", "sweep_angle_axis", "semi_major_axis", "semi_minor_axis")
        absent_projection = [name for name in required_projection if name not in attrs]
        if absent_projection:
            raise ValueError(f"{product.product_id} projection missing {absent_projection}")
        height = float(attrs["perspective_point_height"])
        crs = CRS.from_dict({"proj": "geos", "h": height, "lon_0": float(attrs["longitude_of_projection_origin"]), "sweep": str(attrs["sweep_angle_axis"]), "a": float(attrs["semi_major_axis"]), "b": float(attrs["semi_minor_axis"]), "units": "m"})
        to_fixed = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        to_geo = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        edge = numpy.linspace(0.0, 1.0, 65)
        lons = numpy.concatenate((bounds["west"] + edge * (bounds["east"] - bounds["west"]), bounds["west"] + edge * (bounds["east"] - bounds["west"]), numpy.full(65, bounds["west"]), numpy.full(65, bounds["east"])))
        lats = numpy.concatenate((numpy.full(65, bounds["south"]), numpy.full(65, bounds["north"]), bounds["south"] + edge * (bounds["north"] - bounds["south"]), bounds["south"] + edge * (bounds["north"] - bounds["south"])))
        edge_x, edge_y = to_fixed.transform(lons, lats)
        finite = numpy.isfinite(edge_x) & numpy.isfinite(edge_y)
        if not finite.any():
            raise ValueError("evidence box is outside the granule disk")
        x_m = numpy.asarray(source["x"].values, dtype="float64") * height
        y_m = numpy.asarray(source["y"].values, dtype="float64") * height
        xs = _index_window(x_m, numpy.asarray(edge_x)[finite].min(), numpy.asarray(edge_x)[finite].max(), "x")
        ys = _index_window(y_m, numpy.asarray(edge_y)[finite].min(), numpy.asarray(edge_y)[finite].max(), "y")
        subset = source.isel(x=xs, y=ys).load()
        grid_x, grid_y = numpy.meshgrid(x_m[xs], y_m[ys])
        lon2d, lat2d = to_geo.transform(grid_x, grid_y)
        scan_text = source.attrs.get("time_coverage_start")
        if not scan_text:
            raise ValueError("granule missing time_coverage_start")
        scan_start = datetime.fromisoformat(str(scan_text).replace("Z", "+00:00")).astimezone(UTC)
        source_attrs = {name: source.attrs.get(name) for name in ("title", "dataset_name", "platform_ID", "time_coverage_end", "date_created")}

    if source_attrs["platform_ID"] != "G19" or not str(source_attrs["dataset_name"]).startswith(f"OR_{product.product_id}-M6_G19_"):
        raise ValueError(f"granule identity does not match {product.product_id} on G19")

    inside = numpy.isfinite(lat2d) & numpy.isfinite(lon2d) & (lat2d >= bounds["south"]) & (lat2d <= bounds["north"]) & (lon2d >= bounds["west"]) & (lon2d <= bounds["east"])
    variables: dict[str, Any] = {}
    dispositions: list[dict[str, Any]] = []
    quality = subset[product.quality]
    quality_values = numpy.asarray(quality.values, dtype="float32")
    good_quality = numpy.isfinite(quality_values) & numpy.isin(quality_values, product.good_quality_values)
    for item in product.fields:
        native = subset[item.native]
        if str(native.attrs.get("units", "")) != item.native_units:
            raise ValueError(f"{product.product_id} {item.native} units {native.attrs.get('units')!r}, expected {item.native_units!r}")
        values = numpy.asarray(native.values, dtype="float64") * item.scale + item.offset
        spatial_mask = inside[(...,) + (None,) * (values.ndim - 2)]
        quality_mask = good_quality[(...,) + (None,) * (values.ndim - good_quality.ndim)]
        values = numpy.where(spatial_mask & quality_mask, values, numpy.nan)
        if item.valid:
            values = numpy.where((values >= item.valid[0]) & (values <= item.valid[1]), values, numpy.nan)
        dims = tuple("latitude_index" if dim == "y" else "longitude_index" if dim == "x" else dim for dim in native.dims)
        out_attrs = {"units": item.units, "native_name": item.native, "native_units": str(native.attrs.get("units", "unknown")), "long_name": str(native.attrs.get("long_name", item.canonical))}
        if "flag_values" in native.attrs:
            out_attrs.update(flag_values=numpy.asarray(native.attrs["flag_values"]).tolist(), flag_meanings=str(native.attrs.get("flag_meanings", "")))
        variables[item.canonical] = (dims, values.astype("float32"), out_attrs)
        dispositions.append({"native": item.native, "field": item.canonical, "disposition": "retrieved"})
    qdims = tuple("latitude_index" if dim == "y" else "longitude_index" if dim == "x" else dim for dim in quality.dims)
    quality_values = numpy.where(inside[(...,) + (None,) * (quality_values.ndim - 2)], quality_values, numpy.nan)
    variables["quality_flag"] = (qdims, quality_values, {"units": "1", "native_name": product.quality, "flag_values": numpy.asarray(quality.attrs.get("flag_values", [])).tolist(), "flag_meanings": str(quality.attrs.get("flag_meanings", ""))})
    coords: dict[str, Any] = {
        "latitude": (("latitude_index", "longitude_index"), numpy.asarray(lat2d, dtype="float32")),
        "longitude": (("latitude_index", "longitude_index"), numpy.asarray(lon2d, dtype="float32")),
    }
    if "pressure" in subset.coords:
        pressure = numpy.asarray(subset["pressure"].values, dtype="float64")
        pressure_units = str(subset["pressure"].attrs.get("units", ""))
        if pressure_units != "hPa" or pressure.size != 101 or not numpy.isfinite(pressure).all() or len(numpy.unique(pressure)) != 101 or not numpy.all(numpy.diff(pressure) < 0):
            raise ValueError("GOES legacy profile pressure must be 101 unique finite descending hPa levels")
        coords["pressure"] = ("pressure", pressure.astype("float32"), {"units": pressure_units})
    elif any(item.canonical in {"relative_humidity_pressure", "temperature_pressure"} for item in product.fields):
        raise ValueError(f"{product.product_id} carries no pressure coordinate")
    dataset = xarray.Dataset(variables, coords=coords, attrs={"product_id": product.product_id, "scan_start": scan_start.isoformat(), "source_dataset_name": str(source_attrs["dataset_name"])})
    dataset = dataset.expand_dims(valid_time=[numpy.datetime64(scan_start.replace(tzinfo=None), "ns")])
    lat_step = float(numpy.nanmax(numpy.abs(numpy.diff(lat2d, axis=0))))
    lon_step = float(numpy.nanmax(numpy.abs(numpy.diff(lon2d, axis=1))))
    covers_bounds = bool(numpy.nanmin(lat2d) <= bounds["south"] + lat_step and numpy.nanmax(lat2d) >= bounds["north"] - lat_step and numpy.nanmin(lon2d) <= bounds["west"] + lon_step and numpy.nanmax(lon2d) >= bounds["east"] - lon_step)
    pressure_hash = hashlib.sha256(numpy.asarray(dataset.coords["pressure"].values, dtype="float32").tobytes()).hexdigest() if "pressure" in dataset.coords else None
    return dataset, {"scan_start": scan_start, "source_attrs": source_attrs, "coverage_cells": int(inside.sum()), "total_crop_cells": int(inside.size), "covers_bounds": covers_bounds, "field_dispositions": dispositions, "quality_native_name": product.quality, "good_quality_cells": int(good_quality.sum()), "pressure_sha256": pressure_hash}


class GOESABIL2Adapter:
    source_id = "noaa-goes-east"
    adapter_version = "goes-abi-l2-expansion-v1"

    def __init__(self, product_id: str, *, base_url: str = GOES_S3_BASE, bounds: Mapping[str, float] = EVIDENCE_BOX_BOUNDS, client: PoliteClient | None = None) -> None:
        if product_id not in PRODUCTS:
            raise ValueError(f"unsupported GOES ABI product {product_id!r}")
        self.product = PRODUCTS[product_id]
        self._base_url = base_url.rstrip("/")
        self._bounds = dict(bounds)
        self._client = client

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        found: dict[str, str] = {}
        for hours_back in range(DISCOVERY_HOURS):
            moment = window.now - timedelta(hours=hours_back)
            prefix = _hour_prefix(self.product.product_id, moment)
            try:
                listing = self._get_client().get_text(f"{self._base_url}/?list-type=2&max-keys=1000&prefix={prefix}")
            except Exception:
                continue
            for key in parse_bucket_keys(listing):
                stamp = parse_product_key(key, self.product.product_id)
                if stamp:
                    found[stamp] = key
        usable = [stamp for stamp in found if parse_scan_stamp(stamp) <= window.now]
        if not usable:
            raise AdapterUnavailable(f"no {self.product.product_id} granule in the last {DISCOVERY_HOURS} hours")
        stamp = max(usable)
        key = found[stamp]
        return [RunCandidate(f"goes19-{self.product.product_id.lower()}-{stamp}", parse_scan_stamp(stamp), [f"{self._base_url}/{key}"], {"key": key, "scan_stamp": stamp, "product_id": self.product.product_id})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        retrieved_at = datetime.now(UTC)
        key = str(candidate.detail["key"])
        raw = workdir / Path(key).name
        size = self._get_client().download(f"{self._base_url}/{key}", raw, max_bytes=MAX_GRANULE_BYTES)
        digest = _sha256(raw)
        dataset, stats = crop_product(raw, self.product, bounds=self._bounds)
        expected_stamp = str(candidate.detail.get("scan_stamp", ""))
        if expected_stamp and abs((stats["scan_start"] - parse_scan_stamp(expected_stamp)).total_seconds()) > 1.0:
            raise ValueError("granule scan time does not match the discovered object key")
        output = workdir / f"{self.product.logical_name}.zarr.zip"
        write_zarr(dataset, output)
        artifact_digest = _sha256(output)
        manifest = RunManifest(self.source_id, tuple(RequiredField(item.canonical, item.units) for item in self.product.fields), bounds=self._bounds, min_coverage_fraction=0.000001)
        validation = validate_run(manifest, dataset, window=window)
        provenance = {
            "source_id": self.source_id, "producer": "NOAA / NESDIS", "product": stats["source_attrs"]["title"],
            "product_id": self.product.product_id, "source_url": f"{self._base_url}/{key}", "source_bytes": size,
            "source_sha256": digest, "source_dataset_name": stats["source_attrs"]["dataset_name"],
            "provider_run_id": candidate.provider_run_id, "valid_times": [stats["scan_start"].isoformat()],
            "artifact_revision": artifact_digest, "artifact_sha256": artifact_digest, "scan_start": stats["scan_start"].isoformat(),
            "time_coverage_end": stats["source_attrs"]["time_coverage_end"], "date_created": stats["source_attrs"]["date_created"],
            "platform_ID": stats["source_attrs"]["platform_ID"], "bounds": dict(self._bounds),
            "coverage_cells": stats["coverage_cells"], "total_crop_cells": stats["total_crop_cells"], "covers_bounds": stats["covers_bounds"],
            "good_quality_cells": stats["good_quality_cells"],
            "pressure_coordinate_sha256": stats["pressure_sha256"], "validation_flags": list(validation.flags),
            "field_dispositions": stats["field_dispositions"], "quality_native_name": stats["quality_native_name"],
            "readable_quality_values": list(self.product.good_quality_values),
            "geometry": "native ABI fixed-grid pixels cropped to the evidence box; values are not interpolated",
            "operational": False, "adapter_version": self.adapter_version, **declared_classes(["retrieved"], by_variable={item.canonical: "retrieved" for item in self.product.fields}),
        }
        artifact = Artifact(self.product.logical_name, MEDIA_ZARR, output, provenance)
        complete = bool(stats["covers_bounds"] and validation.complete)
        qc_passed = bool(validation.qc_passed)
        return RunResult(self.source_id, candidate.provider_run_id, stats["scan_start"], retrieved_at, complete, qc_passed, [artifact], "ABI fixed grid with EPSG:4326 latitude/longitude coordinates", f"{self.product.product_id}: {len(self.product.fields)} mapped fields; operational false")


__all__: Sequence[str] = ("PRODUCTS", "GOESABIL2Adapter", "crop_product", "parse_product_key")
