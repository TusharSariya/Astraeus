"""Unit tests for the GOES-19 ABI cloud-mask adapter.

Fixtures are tiny synthetic NetCDF granules built with the real geostationary
projection metadata, so geometry, cropping, parallax and regridding are
exercised without a 25 MB checked-in file. Real-granule decode is proven by
live smoke, not here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy
import pytest
import xarray

from ingest.adapters.goes_abi import (
    ACHAF_PREFIX,
    ACMF_PREFIX,
    GOESCloudMaskAdapter,
    INVALID_CLASS,
    parse_bucket_keys,
    parse_scan_stamp,
    process_granules,
    viewing_geometry,
)
from ingest.contract import AdapterUnavailable, FetchWindow

UTC = timezone.utc

SUB_LON = -75.0
PERSPECTIVE_H = 35786023.0
SEMI_MAJOR = 6378137.0
SEMI_MINOR = 6356752.31414

TEST_BOUNDS = {"south": 46.0, "west": -54.0, "north": 49.0, "east": -51.0}
CLOUD_BOX = {"south": 47.2, "west": -52.9, "north": 47.8, "east": -52.1}
DQF_BOX = {"south": 46.2, "west": -53.8, "north": 46.5, "east": -53.3}

PROJ_ATTRS = {
    "longitude_of_projection_origin": SUB_LON,
    "perspective_point_height": PERSPECTIVE_H,
    "semi_major_axis": SEMI_MAJOR,
    "semi_minor_axis": SEMI_MINOR,
    "sweep_angle_axis": "x",
}


def _fixed_grid_axes(pad_deg: float = 0.7, step_m: float = 2000.0):
    from pyproj import CRS, Transformer

    crs = CRS.from_dict(
        {"proj": "geos", "h": PERSPECTIVE_H, "lon_0": SUB_LON, "sweep": "x",
         "a": SEMI_MAJOR, "b": SEMI_MINOR, "units": "m"}
    )
    to_fixed = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    lons = numpy.linspace(TEST_BOUNDS["west"] - pad_deg, TEST_BOUNDS["east"] + pad_deg, 41)
    lats = numpy.linspace(TEST_BOUNDS["south"] - pad_deg, TEST_BOUNDS["north"] + pad_deg, 41)
    grid_lon, grid_lat = numpy.meshgrid(lons, lats)
    gx, gy = to_fixed.transform(grid_lon, grid_lat)
    x = numpy.arange(numpy.nanmin(gx), numpy.nanmax(gx) + step_m, step_m)
    y = numpy.arange(numpy.nanmax(gy), numpy.nanmin(gy) - step_m, -step_m)
    to_geo = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    mesh_x, mesh_y = numpy.meshgrid(x, y)
    lon2d, lat2d = to_geo.transform(mesh_x, mesh_y)
    return x / PERSPECTIVE_H, y / PERSPECTIVE_H, lon2d, lat2d


def _in_box(lat2d, lon2d, box):
    return (
        (lat2d >= box["south"]) & (lat2d <= box["north"])
        & (lon2d >= box["west"]) & (lon2d <= box["east"])
    )


def _write_acmf(path: Path, *, with_dqf_box: bool = True) -> None:
    x_rad, y_rad, lon2d, lat2d = _fixed_grid_axes()
    acm = numpy.zeros(lat2d.shape, dtype="int8")
    prob = numpy.full(lat2d.shape, 0.05, dtype="float32")
    dqf = numpy.zeros(lat2d.shape, dtype="int8")
    cloudy = _in_box(lat2d, lon2d, CLOUD_BOX)
    acm[cloudy] = 3
    prob[cloudy] = 0.95
    if with_dqf_box:
        dqf[_in_box(lat2d, lon2d, DQF_BOX)] = 1
    ds = xarray.Dataset(
        {
            "ACM": (("y", "x"), acm),
            "Cloud_Probabilities": (("y", "x"), prob),
            "DQF": (("y", "x"), dqf),
            "goes_imager_projection": xarray.DataArray(numpy.int32(0), attrs=dict(PROJ_ATTRS)),
        },
        coords={"x": x_rad, "y": y_rad},
        attrs={
            "time_coverage_start": "2026-08-30T12:00:21.5Z",
            "time_coverage_end": "2026-08-30T12:09:52.4Z",
            "platform_ID": "G19",
        },
    )
    ds.to_netcdf(path)


def _write_achaf(path: Path, *, height_m: float = 10000.0) -> None:
    x_rad, y_rad, lon2d, lat2d = _fixed_grid_axes()
    stride = 3
    lon_c = lon2d[::stride, ::stride]
    lat_c = lat2d[::stride, ::stride]
    ht = numpy.full(lat_c.shape, numpy.nan, dtype="float32")
    ht[_in_box(lat_c, lon_c, CLOUD_BOX)] = height_m
    ds = xarray.Dataset(
        {
            "HT": (("y", "x"), ht),
            "goes_imager_projection": xarray.DataArray(numpy.int32(0), attrs=dict(PROJ_ATTRS)),
        },
        coords={"x": x_rad[::stride], "y": y_rad[::stride]},
        attrs={"time_coverage_start": "2026-08-30T12:00:21.5Z"},
    )
    ds.to_netcdf(path)


# ---------- key / stamp / listing parsing ----------

def test_parse_scan_stamp():
    stamp = "20262421200215"
    parsed = parse_scan_stamp(stamp)
    assert parsed == datetime(2026, 8, 30, 12, 0, 21, 500000, tzinfo=UTC)
    with pytest.raises(ValueError):
        parse_scan_stamp("nonsense")


def test_parse_bucket_keys():
    xml = (
        '<?xml version="1.0"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<Contents><Key>a/b.nc</Key></Contents><Contents><Key>c/d.nc</Key></Contents>"
        "</ListBucketResult>"
    )
    assert parse_bucket_keys(xml) == ["a/b.nc", "c/d.nc"]


# ---------- discovery ----------

def _acmf_key(day: int, hour: int, stamp: str) -> str:
    return f"{ACMF_PREFIX}/2026/{day:03d}/{hour:02d}/OR_ABI-L2-ACMF-M6_G19_s{stamp}_e{stamp}_c{stamp}.nc"


def _achaf_key(day: int, hour: int, stamp: str) -> str:
    return f"{ACHAF_PREFIX}/2026/{day:03d}/{hour:02d}/OR_ABI-L2-ACHAF-M6_G19_s{stamp}_e{stamp}_c{stamp}.nc"


def _listing_xml(keys):
    body = "".join(f"<Contents><Key>{key}</Key></Contents>" for key in keys)
    return (
        '<?xml version="1.0"?>'
        f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">{body}</ListBucketResult>'
    )


class FakeListingClient:
    """Answers ?list-type=2 requests from a prefix -> keys map."""

    def __init__(self, listings: dict[str, list[str]]):
        self._listings = listings
        self.requested: list[str] = []

    def get_text(self, url: str) -> str:
        self.requested.append(url)
        prefix = url.split("prefix=", 1)[1]
        return _listing_xml(self._listings.get(prefix, []))


def test_discover_pairs_achaf_and_survives_empty_newest_hour():
    # 12:30 UTC: the 12h prefix is still empty (granule latency); 11h has scans.
    window = FetchWindow(now=datetime(2026, 8, 30, 12, 30, tzinfo=UTC))
    stamp_new, stamp_old = "20262421150215", "20262421140215"
    listings = {
        f"{ACMF_PREFIX}/2026/242/11/": [_acmf_key(242, 11, stamp_old), _acmf_key(242, 11, stamp_new)],
        f"{ACHAF_PREFIX}/2026/242/11/": [_achaf_key(242, 11, stamp_new)],
    }
    adapter = GOESCloudMaskAdapter(client=FakeListingClient(listings))
    candidates = adapter.discover(window)
    assert [c.detail["scan_stamp"] for c in candidates] == [stamp_new, stamp_old]
    assert candidates[0].detail["achaf_key"] == _achaf_key(242, 11, stamp_new)
    assert candidates[1].detail["achaf_key"] is None
    assert candidates[0].run_time == parse_scan_stamp(stamp_new)


def test_discover_empty_listing_is_unavailable_not_fabricated():
    window = FetchWindow(now=datetime(2026, 8, 30, 12, 30, tzinfo=UTC))
    adapter = GOESCloudMaskAdapter(client=FakeListingClient({}))
    with pytest.raises(AdapterUnavailable):
        adapter.discover(window)


# ---------- processing ----------

@pytest.fixture(scope="module")
def granules(tmp_path_factory):
    root = tmp_path_factory.mktemp("goes")
    acmf = root / "acmf.nc"
    achaf = root / "achaf.nc"
    _write_acmf(acmf)
    _write_achaf(achaf)
    return acmf, achaf


def test_process_regrids_classes_and_preserves_dqf(granules):
    acmf, achaf = granules
    dataset, stats = process_granules(acmf, achaf, bounds=TEST_BOUNDS)
    classes = dataset["cloud_class"].isel(valid_time=0).values
    lats = dataset["latitude"].values
    lons = dataset["longitude"].values
    lat2d, lon2d = numpy.meshgrid(lats, lons, indexing="ij")

    # Quality-flagged pixels are the invalid class, never clear. The box is
    # shrunk by ~one target cell: an edge cell may legitimately take its
    # nearest source pixel from just outside the flagged region.
    dqf_interior = _in_box(lat2d, lon2d, {"south": 46.27, "west": -53.72, "north": 46.43, "east": -53.38})
    assert dqf_interior.any()
    assert (classes[dqf_interior] == INVALID_CLASS).all()

    # The cloudy box regrids as cloudy (interior, away from parallax-shifted edges).
    interior = _in_box(lat2d, lon2d, {"south": 47.35, "west": -52.7, "north": 47.6, "east": -52.4})
    assert (classes[interior] == 3).mean() > 0.9

    # Elsewhere is clear, not invalid: a gap is never manufactured.
    clear_region = _in_box(lat2d, lon2d, {"south": 48.3, "west": -53.8, "north": 48.8, "east": -53.0})
    assert (classes[clear_region] == 0).all()

    # Instrument coverage of the box is complete; the slightly lower populated
    # fraction is the honest occlusion hole a corrected cloud leaves behind.
    assert stats["coverage_fraction"] > 0.99
    assert stats["populated_fraction"] > 0.95
    assert stats["probability_in_range"] and stats["classes_in_range"]


def test_target_cell_is_never_finer_than_native(granules):
    acmf, achaf = granules
    _, stats = process_granules(acmf, achaf, bounds=TEST_BOUNDS)
    native_dlat, native_dlon = stats["native_footprint_deg"]
    target_dlat, target_dlon = stats["target_cell_deg"]
    assert target_dlat >= native_dlat
    assert target_dlon >= native_dlon


def test_scan_time_comes_from_time_coverage_attrs(granules):
    acmf, achaf = granules
    dataset, stats = process_granules(acmf, achaf, bounds=TEST_BOUNDS)
    assert stats["scan_start"] == datetime(2026, 8, 30, 12, 0, 21, 500000, tzinfo=UTC)
    assert dataset["valid_time"].values[0] == numpy.datetime64("2026-08-30T12:00:21.500000000")


def test_parallax_moves_cloud_toward_subsatellite_point(granules):
    acmf, achaf = granules

    def _cloud_centroid(dataset):
        classes = dataset["cloud_class"].isel(valid_time=0).values
        lat2d, lon2d = numpy.meshgrid(
            dataset["latitude"].values, dataset["longitude"].values, indexing="ij"
        )
        cloudy = classes == 3
        return float(lat2d[cloudy].mean()), float(lon2d[cloudy].mean())

    with_height, _ = process_granules(acmf, achaf, bounds=TEST_BOUNDS)
    without_height, _ = process_granules(acmf, None, bounds=TEST_BOUNDS)
    lat_corr, lon_corr = _cloud_centroid(with_height)
    lat_raw, lon_raw = _cloud_centroid(without_height)

    # The sub-satellite point (0N, 75W) lies to the southwest, so a corrected
    # 10 km cloud moves south and west by roughly h*tan(vza) ~ 16 km.
    assert lat_corr < lat_raw
    assert lon_corr < lon_raw
    shift_deg = numpy.hypot(lat_corr - lat_raw, (lon_corr - lon_raw) * numpy.cos(numpy.radians(lat_raw)))
    assert 0.05 < shift_deg < 0.35


def test_no_height_flags_uncorrected_but_still_renders(granules):
    acmf, _ = granules
    dataset, stats = process_granules(acmf, None, bounds=TEST_BOUNDS)
    classes = dataset["cloud_class"].isel(valid_time=0).values
    uncorr = dataset["parallax_uncorrected"].isel(valid_time=0).values
    cloudy = classes == 3
    assert cloudy.any()
    assert (uncorr[cloudy] == 1).all()
    assert (uncorr[~cloudy] == 0).all()
    assert stats["uncorrected_cells"] == int(cloudy.sum())
    assert not stats["achaf_used"]


def test_missing_projection_attrs_are_refused(tmp_path):
    path = tmp_path / "bare.nc"
    ds = xarray.Dataset(
        {"ACM": (("y", "x"), numpy.zeros((4, 4), dtype="int8"))},
        coords={"x": numpy.linspace(-0.02, 0.02, 4), "y": numpy.linspace(0.12, 0.10, 4)},
    )
    ds.to_netcdf(path)
    with pytest.raises(ValueError, match="goes_imager_projection"):
        process_granules(path, None, bounds=TEST_BOUNDS)


def test_viewing_zenith_matches_st_johns_geometry():
    vza, bearing = viewing_geometry(
        numpy.array([47.5615]), numpy.array([-52.7126]), SUB_LON, PERSPECTIVE_H + SEMI_MAJOR
    )
    assert 55.0 < numpy.degrees(vza[0]) < 62.0
    # Bearing toward the sub-satellite point is southwesterly.
    deg = numpy.degrees(bearing[0]) % 360.0
    assert 180.0 < deg < 270.0


# ---------- fetch ----------

class FakeFetchClient(FakeListingClient):
    def __init__(self, listings, files: dict[str, Path]):
        super().__init__(listings)
        self._files = files

    def download(self, url: str, destination: Path, *, max_bytes: int, **_kw) -> int:
        key = url.split(".amazonaws.com/", 1)[-1]
        source = self._files.get(key)
        if source is None:
            raise RuntimeError(f"no fixture for {key}")
        payload = source.read_bytes()
        assert len(payload) <= max_bytes
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return len(payload)


def test_fetch_publishes_one_zarr_artifact(granules, tmp_path):
    acmf, achaf = granules
    stamp = "20262421150215"
    acmf_key = _acmf_key(242, 11, stamp)
    achaf_key = _achaf_key(242, 11, stamp)
    client = FakeFetchClient({}, {acmf_key: acmf, achaf_key: achaf})
    adapter = GOESCloudMaskAdapter(bounds=TEST_BOUNDS, client=client)
    window = FetchWindow(now=datetime(2026, 8, 30, 12, 30, tzinfo=UTC))
    candidate_detail = {"acmf_key": acmf_key, "achaf_key": achaf_key, "scan_stamp": stamp}
    from ingest.contract import RunCandidate

    result = adapter.fetch(
        RunCandidate(provider_run_id=f"goes19-acmf-{stamp}", run_time=parse_scan_stamp(stamp),
                     urls=[], detail=candidate_detail),
        window,
        tmp_path,
    )
    assert result.complete and result.qc_passed
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.media_type == "application/zarr+zip"
    assert artifact.logical_name == "cloud_mask"
    assert artifact.provenance["cloud_top_height_maturity"] == "NOAA Provisional"
    # The scan time in the result is the granule's own, not the key stamp.
    assert result.run_time == datetime(2026, 8, 30, 12, 0, 21, 500000, tzinfo=UTC)

    import zarr

    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    reopened = xarray.open_zarr(store, consolidated=False)
    assert set(reopened.data_vars) == {"cloud_class", "cloud_probability", "parallax_uncorrected"}
    assert "parallax_disclosure" in reopened.attrs


# ---------- live smoke ----------

import os  # noqa: E402


@pytest.mark.live_smoke
@pytest.mark.skipif(os.environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to hit the noaa-goes19 bucket")
def test_live_goes19_acmf_scan_regrids_end_to_end(tmp_path):
    """One polite pull of the newest real ACMF (+ACHAF) Full Disk granule.

    This is the only place real-granule decode is proven: the fixtures above
    are synthetic, so scale/offset/_FillValue handling of Cloud_Probabilities,
    the real fixed-grid geometry and the ACHAF pairing are all asserted here.
    """
    from datetime import datetime as _dt

    from ingest.http import PoliteClient

    adapter = GOESCloudMaskAdapter(client=PoliteClient())
    window = FetchWindow(now=_dt.now(UTC))
    candidates = adapter.discover(window)
    assert candidates, "the bucket listed no ACMF granule in the last four hours"
    newest = candidates[0]
    age = (window.now - newest.run_time).total_seconds()
    assert age < 3600, f"newest scan is {age:.0f} s old; the 10-minute feed should be far fresher"

    result = adapter.fetch(newest, window, tmp_path)
    assert result.complete, result.notes
    assert result.qc_passed, result.notes
    provenance = result.artifacts[0].provenance
    print("scan", provenance["scan_start"], "populated", provenance["populated_fraction"],
          "invalid", provenance["invalid_fraction"], "cloudy", provenance["cloudy_cells"],
          "uncorrected", provenance["parallax_uncorrected_cells"])

    import zarr

    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    dataset = xarray.open_zarr(store, consolidated=False)
    prob = dataset["cloud_probability"].values
    finite = prob[numpy.isfinite(prob)]
    assert finite.size, "no finite cloud probabilities decoded"
    assert float(finite.min()) >= 0.0 and float(finite.max()) <= 1.0, "Cloud_Probabilities decode is off-scale"
    classes = numpy.unique(dataset["cloud_class"].values)
    assert set(classes.tolist()) <= {0, 1, 2, 3, 255}
