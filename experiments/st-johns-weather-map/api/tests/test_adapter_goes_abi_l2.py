from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import xarray
from pyproj import CRS, Transformer

from ingest.adapters.goes_abi_l2 import PRODUCTS, crop_product, parse_product_key

BOUNDS = {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}
PROJECTION = {
    "perspective_point_height": 35786023.0,
    "semi_major_axis": 6378137.0,
    "semi_minor_axis": 6356752.31414,
    "longitude_of_projection_origin": -75.0,
    "sweep_angle_axis": "x",
}


def _granule(path: Path, product_id: str, *, bad_units: bool = False, pressure: numpy.ndarray | None = None) -> Path:
    product = PRODUCTS[product_id]
    crs = CRS.from_dict({"proj": "geos", "h": PROJECTION["perspective_point_height"], "lon_0": -75.0, "sweep": "x", "a": PROJECTION["semi_major_axis"], "b": PROJECTION["semi_minor_axis"], "units": "m"})
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    corners_x, corners_y = project.transform([-59, -45, -59, -45], [44, 44, 52, 52])
    height = PROJECTION["perspective_point_height"]
    x = numpy.linspace(min(corners_x) / height, max(corners_x) / height, 12)
    y = numpy.linspace(max(corners_y) / height, min(corners_y) / height, 10)
    pressure = numpy.asarray(pressure if pressure is not None else numpy.linspace(1100.0, 0.1, 101), dtype="float32")
    variables: dict[str, object] = {"goes_imager_projection": xarray.DataArray(numpy.int32(0), attrs=PROJECTION)}
    for index, field in enumerate(product.fields):
        dims = ("y", "x", "pressure") if product_id in {"ABI-L2-LVMPF", "ABI-L2-LVTPF"} else ("y", "x")
        shape = (len(y), len(x), len(pressure)) if len(dims) == 3 else (len(y), len(x))
        value = 0.5 if field.scale != 1.0 else 2.0 + index
        values = numpy.full(shape, value, dtype="float32")
        variables[field.native] = xarray.DataArray(values, dims=dims, attrs={"units": "wrong" if bad_units and index == 0 else field.native_units, "long_name": field.native})
    quality = numpy.zeros((len(y), len(x)), dtype="int8")
    quality[5, 5] = 1
    quality_attrs = {"units": "1", "flag_values": [0, 1], "flag_meanings": "good bad"}
    if product.quality_is_cod_bitfield:
        quality.fill(2)
        quality[5, 5] = 6
        quality_attrs = {
            "units": "1",
            "flag_masks": [1, 1, 2, 2, 4, 4],
            "flag_values": [0, 1, 0, 2, 0, 4],
            "flag_meanings": "day_algorithm_pixel_qf not_day_algorithm_pixel_qf night_algorithm_pixel_qf not_night_algorithm_pixel_qf good_quality_qf degraded_quality_qf",
        }
    variables[product.quality] = xarray.DataArray(quality, dims=("y", "x"), attrs=quality_attrs)
    coords: dict[str, object] = {"x": x, "y": y}
    if product_id in {"ABI-L2-LVMPF", "ABI-L2-LVTPF"}:
        coords["pressure"] = xarray.DataArray(pressure, dims=("pressure",), attrs={"units": "hPa"})
    dataset = xarray.Dataset(variables, coords=coords, attrs={"dataset_name": f"OR_{product_id}-M6_G19_s20262482010207_e20262482019515_c20262482020528.nc", "title": product_id, "platform_ID": "G19", "time_coverage_start": "2026-09-05T20:10:20.7Z", "time_coverage_end": "2026-09-05T20:19:51.5Z", "date_created": "2026-09-05T20:20:52.8Z"})
    dataset.to_netcdf(path)
    return path


@pytest.mark.parametrize("product_id", sorted(PRODUCTS))
def test_every_selected_gridded_product_maps_native_fields(product_id: str, tmp_path: Path):
    product = PRODUCTS[product_id]
    dataset, stats = crop_product(_granule(tmp_path / "sample.nc", product_id), product, bounds=BOUNDS)
    assert stats["covers_bounds"]
    assert stats["coverage_cells"] > 0
    assert {field.canonical for field in product.fields} <= set(dataset.data_vars)
    assert dataset["quality_flag"].attrs["flag_meanings"]
    for field in product.fields:
        assert dataset[field.canonical].attrs["units"] == field.units
        assert numpy.isfinite(dataset[field.canonical]).any()


def test_bad_quality_pixel_is_preserved_as_flag_but_not_readable_value(tmp_path: Path):
    product = PRODUCTS["ABI-L2-ACHTF"]
    dataset, _ = crop_product(_granule(tmp_path / "sample.nc", product.product_id), product, bounds=BOUNDS)
    bad = dataset["quality_flag"].values == 1
    assert bad.any()
    assert numpy.isnan(dataset["cloud_top_temperature"].values[bad]).all()


def test_cod_quality_is_decoded_from_declared_bits(tmp_path: Path):
    product = PRODUCTS["ABI-L2-CODF"]
    dataset, stats = crop_product(_granule(tmp_path / "cod.nc", product.product_id), product, bounds=BOUNDS)
    assert stats["good_quality_cells"] > 0
    degraded = dataset["quality_flag"].values == 6
    assert degraded.any()
    assert numpy.isnan(dataset["cloud_optical_depth"].values[degraded]).all()
    assert dataset["quality_flag"].attrs["flag_masks"] == [1, 1, 2, 2, 4, 4]


def test_cod_quality_refuses_an_undeclared_bit_layout(tmp_path: Path):
    product = PRODUCTS["ABI-L2-CODF"]
    path = _granule(tmp_path / "cod.nc", product.product_id)
    with xarray.open_dataset(path) as opened:
        changed = opened.load()
    changed["DQF"].attrs.pop("flag_masks")
    changed.to_netcdf(path, mode="w")
    with pytest.raises(ValueError, match="does not declare"):
        crop_product(path, product, bounds=BOUNDS)


def test_native_unit_and_identity_mismatches_fail_closed(tmp_path: Path):
    product = PRODUCTS["ABI-L2-TPWF"]
    with pytest.raises(ValueError, match="units"):
        crop_product(_granule(tmp_path / "bad.nc", product.product_id, bad_units=True), product, bounds=BOUNDS)
    path = _granule(tmp_path / "identity.nc", product.product_id)
    with xarray.open_dataset(path) as opened:
        changed = opened.load()
    changed.attrs["platform_ID"] = "G18"
    changed.to_netcdf(path, mode="w")
    with pytest.raises(ValueError, match="identity"):
        crop_product(path, product, bounds=BOUNDS)


@pytest.mark.parametrize(
    "pressure",
    [numpy.array([1000.0, 850.0]), numpy.linspace(0.1, 1100.0, 101), numpy.full(101, 500.0)],
)
def test_profile_pressure_coordinate_must_match_producer_shape(pressure: numpy.ndarray, tmp_path: Path):
    product = PRODUCTS["ABI-L2-LVMPF"]
    with pytest.raises(ValueError, match="101 unique finite descending hPa"):
        crop_product(_granule(tmp_path / "bad-pressure.nc", product.product_id, pressure=pressure), product, bounds=BOUNDS)


def test_product_key_parser_refuses_other_products_and_platforms():
    key = "ABI-L2-CCLF/2026/248/20/OR_ABI-L2-CCLF-M6_G19_s20262482000207_e20262482009515_c20262482018094.nc"
    assert parse_product_key(key, "ABI-L2-CCLF") == "20262482000207"
    assert parse_product_key(key, "ABI-L2-ACTPF") is None
    assert parse_product_key(key.replace("G19", "G18"), "ABI-L2-CCLF") is None
