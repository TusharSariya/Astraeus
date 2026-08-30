"""Cloud-strata rasters rendered by this experiment from its own stored grids.

No provider publishes low/middle/high cloud rasters for this region, so the
API draws them from the ingested NOAA GFS artifact. What is under test is the
honesty of that rendering:

* every pixel is the stored value of the native 0.25 degree cell containing
  it - nearest-neighbor, block-uniform, never interpolated or smoothed;
* the offered times are exactly the ingested valid times, and an instant with
  no stored frame within tolerance is a 422, never a silently reused frame;
* positioning is exact in both EPSG:4326 and EPSG:3857;
* the colormap is disclosed and served as a legend; provenance rides the
  response headers; ``operational`` stays false.

The store is stubbed with a synthetic grid whose values are chosen so a single
interpolated pixel would be visible as a wrong byte.
"""

from __future__ import annotations

import math
import struct
import sys as _sys
import zlib
from datetime import datetime, timedelta, timezone

import numpy
import pytest
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from ingest.store import CurrentArtifact
from weather_api import grids
from weather_api.app import PREFIX, app
from weather_api.fixtures import now

UTC = timezone.utc
api_module = _sys.modules["weather_api.app"]
client = TestClient(app)

# --- the synthetic grid ---------------------------------------------------

#: Cell centres, GFS-style: latitude descending, longitude ascending, 0.25 deg.
LATS = numpy.array([48.0, 47.75, 47.5])
LONS = numpy.array([-53.0, -52.75, -52.5])

#: Distinct per-cell percentages. Any interpolation would manufacture a value
#: outside this set and show up as a wrong alpha byte.
FRAME0 = numpy.array([
    [0.0, 25.0, 50.0],
    [75.0, 100.0, 12.0],
    [numpy.nan, 60.0, 88.0],
])
FRAME1 = numpy.clip(FRAME0 + 5.0, 0, 100)

#: The exact bounds of the 3x3 cell block: centres +/- half a 0.25 deg step.
CELL_BOUNDS = {"south": 47.375, "west": -53.125, "north": 48.125, "east": -52.375}


def frame_times() -> list[datetime]:
    base = now().replace(minute=0, second=0, microsecond=0)
    return [base, base + timedelta(hours=1)]


def grid_dataset(variables: tuple[str, ...] = ("cloud_low", "cloud_middle", "cloud_high")) -> xarray.Dataset:
    stamps = [numpy.datetime64(stamp.replace(tzinfo=None), "ns") for stamp in frame_times()]
    data = numpy.stack([FRAME0, FRAME1])
    return xarray.Dataset(
        {name: (("valid_time", "latitude", "longitude"), data.copy(), {"units": "percent"}) for name in variables},
        coords={"valid_time": stamps, "latitude": LATS, "longitude": LONS},
    )


def gfs_artifact() -> CurrentArtifact:
    stamp = now()
    return CurrentArtifact(
        source_id="noaa-gfs",
        logical_name="surface",
        revision_id="revision-noaa-gfs-surface",
        object_key="artifacts/noaa-gfs/surface",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={"product": "Global Forecast System (GFS 0.25 deg)"},
        published_at=stamp,
        run_time=stamp - timedelta(hours=6),
        retrieved_at=stamp,
        provider_run_id="gfs-2026083012",
        native_crs="EPSG:4326",
    )


class GridStore:
    """A reachable live store publishing exactly one GFS grid artifact."""

    skipped: list = []

    def __init__(self, dataset: xarray.Dataset | None, artifact: CurrentArtifact | None = None) -> None:
        self._dataset = dataset
        self._artifact = artifact if artifact is not None else gfs_artifact()

    def current(self):
        return [self._artifact] if self._artifact is not None else []

    def open(self, artifact):
        if self._dataset is None:
            raise RuntimeError("unreadable artifact")
        return self._dataset

    def published_layer_times(self):
        return {}

    def published_products(self):
        return {}

    def sample_point(self, *args, **kwargs):
        return []

    def source_activity(self):
        return {}


def use_store(monkeypatch, data_mode, store) -> None:
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: store)
    monkeypatch.setattr(api_module, "_proxied_forecast_layers", lambda: ([], []))


# --- PNG round-trip helper ------------------------------------------------

def decode_png(payload: bytes) -> numpy.ndarray:
    """Decode the filter-0 RGBA PNGs :func:`grids.encode_png` writes."""
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    offset, width, height, idat = 8, None, None, b""
    while offset < len(payload):
        (length,) = struct.unpack(">I", payload[offset:offset + 4])
        kind = payload[offset + 4:offset + 8]
        body = payload[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", body[:10])
            assert (depth, colour) == (8, 6), "RGBA8 expected"
        elif kind == b"IDAT":
            idat += body
        offset += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 4 + 1
    rows = []
    for row in range(height):
        line = raw[row * stride:(row + 1) * stride]
        assert line[0] == 0, "filter type 0 expected"
        rows.append(numpy.frombuffer(line[1:], dtype="uint8").reshape(width, 4))
    return numpy.stack(rows)


def alpha_for(percent: float) -> int:
    return int(round(percent * 2.55))


# --- rasterize: nearest-neighbor exactness --------------------------------

def test_each_pixel_is_the_stored_value_of_its_cell_and_nothing_between():
    """6x6 pixels over 3x3 cells: every 2x2 block is uniform at the stored
    value's alpha, so no pixel can have been interpolated between cells."""
    rgba = grids.rasterize(FRAME0, LATS, LONS, bounds=CELL_BOUNDS, width=6, height=6, crs="EPSG:4326")
    assert rgba.shape == (6, 6, 4)
    for row_cell in range(3):
        for col_cell in range(3):
            block = rgba[row_cell * 2:(row_cell + 1) * 2, col_cell * 2:(col_cell + 1) * 2]
            stored = FRAME0[row_cell, col_cell]
            expected = 0 if not numpy.isfinite(stored) else alpha_for(stored)
            assert (block[..., 3] == expected).all(), (row_cell, col_cell)
    # White hue everywhere; the value lives in alpha alone.
    assert (rgba[..., 0:3] == 255).all()


def test_zero_percent_and_missing_cells_are_both_transparent_but_stored_zero_is_still_stored():
    rgba = grids.rasterize(FRAME0, LATS, LONS, bounds=CELL_BOUNDS, width=3, height=3, crs="EPSG:4326")
    assert rgba[0, 0, 3] == 0  # stored 0 percent
    assert rgba[2, 0, 3] == 0  # NaN: no stored value
    assert rgba[1, 1, 3] == 255  # stored 100 percent


def test_pixels_outside_the_grid_edge_are_transparent_never_extrapolated():
    wide = {"south": 46.0, "west": -55.0, "north": 49.0, "east": -51.0}
    rgba = grids.rasterize(FRAME0, LATS, LONS, bounds=wide, width=40, height=30, crs="EPSG:4326")
    # Corner pixels are far outside the 0.75 deg cell block: nothing there.
    assert rgba[0, 0, 3] == 0 and rgba[-1, -1, 3] == 0
    # But the cells themselves are still painted somewhere in the middle.
    assert (rgba[..., 3] == 255).any()


def test_a_cell_boundary_splits_pixels_between_the_adjacent_cells_exactly():
    """Four columns over two cells: the first two columns take the west cell's
    value and the last two the east cell's - the boundary is a boundary."""
    two = numpy.array([[10.0, 90.0]])
    rgba = grids.rasterize(
        two, numpy.array([47.75, 47.5]), numpy.array([-53.0, -52.75]),
        bounds={"south": 47.625, "west": -53.125, "north": 47.875, "east": -52.625},
        width=4, height=1, crs="EPSG:4326",
    )
    assert list(rgba[0, :, 3]) == [alpha_for(10)] * 2 + [alpha_for(90)] * 2


def test_epsg_3857_rows_are_uniform_in_mercator_not_latitude():
    """Two tall cells rendered in EPSG:3857: the row where the value changes is
    the mercator position of the cell edge, computed independently here, and it
    differs by many rows from the linear-latitude midpoint."""
    lats = numpy.array([40.0, 20.0])  # cell edge at 30.0
    lons = numpy.array([-53.0, -52.75])
    field = numpy.array([[80.0, 80.0], [20.0, 20.0]])
    bounds = {"south": 10.0, "west": -53.125, "north": 50.0, "east": -52.625}
    height = 200
    rgba = grids.rasterize(field, lats, lons, bounds=bounds, width=1, height=height, crs="EPSG:3857")

    def mercator_y(latitude: float) -> float:
        return math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))

    fraction = (mercator_y(50.0) - mercator_y(30.0)) / (mercator_y(50.0) - mercator_y(10.0))
    expected_row = fraction * height
    change = next(row for row in range(height) if rgba[row, 0, 3] == alpha_for(20))
    assert abs(change - expected_row) <= 1
    # The linear-latitude midpoint (row 100) would be wrong by many rows.
    assert abs(change - height / 2) > 5
    # And in EPSG:4326 the change row IS the linear midpoint.
    linear = grids.rasterize(field, lats, lons, bounds=bounds, width=1, height=height, crs="EPSG:4326")
    linear_change = next(row for row in range(height) if linear[row, 0, 3] == alpha_for(20))
    assert abs(linear_change - height / 2) <= 1


def test_a_non_uniform_axis_is_refused_rather_than_guessed():
    with pytest.raises(grids.GridUnavailable):
        grids.rasterize(FRAME0, numpy.array([48.0, 47.8, 47.5]), LONS, bounds=CELL_BOUNDS, width=4, height=4)


def test_an_unknown_crs_is_refused():
    with pytest.raises(ValueError):
        grids.rasterize(FRAME0, LATS, LONS, bounds=CELL_BOUNDS, width=4, height=4, crs="EPSG:32622")


# --- the layer index ------------------------------------------------------

def test_the_three_strata_layers_are_offered_with_only_ingested_times(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(grid_dataset()))
    payload = client.get(f"{PREFIX}/layers").json()
    by_id = {layer["id"]: layer for layer in payload["layers"]}
    stamps = [stamp.isoformat() for stamp in frame_times()]
    for layer_id, field in (
        ("noaa-gfs-surface-cloud-low", "cloud_low"),
        ("noaa-gfs-surface-cloud-middle", "cloud_middle"),
        ("noaa-gfs-surface-cloud-high", "cloud_high"),
    ):
        layer = by_id[layer_id]
        assert layer["group"] == "rendered_grid"
        assert layer["field"] == field
        assert layer["product"] == "Global Forecast System (GFS 0.25 deg)"
        assert layer["units"] == "percent"
        assert layer["evidence_basis"] == "published_artifact"
        assert layer["raster_available"] is True
        assert layer["legend_available"] is True
        assert layer["upstream_wms_layer"] is None
        assert [datetime.fromisoformat(stamp).isoformat() for stamp in layer["times"]] == stamps
        assert layer["cadence_seconds"] == 3600
        assert layer["staleness_tolerance_seconds"] == 1800
        semantics = layer["semantics"]
        assert "rendered by this experiment from retrieved NOAA GFS GRIB2 fields" in semantics
        assert "provider-declared" in semantics
        assert "0.25 deg native resolution" in semantics
        assert "nearest-neighbor" in semantics
        assert "never smoothed" in semantics
    assert payload["operational"] is False


def test_a_missing_variable_is_a_notice_and_no_layer_not_a_guess(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(grid_dataset(("cloud_low", "cloud_middle"))))
    payload = client.get(f"{PREFIX}/layers").json()
    ids = {layer["id"] for layer in payload["layers"]}
    assert "noaa-gfs-surface-cloud-low" in ids
    assert "noaa-gfs-surface-cloud-high" not in ids
    assert any("noaa-gfs-surface-cloud-high" in notice and "does not carry" in notice for notice in payload["notices"])


def test_no_gfs_artifact_means_no_strata_layers_at_all(monkeypatch, data_mode):
    other = CurrentArtifact(
        source_id="eccc-radar", logical_name="radar", revision_id="r", object_key="k",
        media_type="application/zarr+zip", byte_size=1, provenance={"geomet_layer": "RADAR_1KM_RRAI"},
        published_at=now(), run_time=now(), retrieved_at=now(), provider_run_id="x", native_crs="EPSG:4326",
    )
    store = GridStore(grid_dataset())
    store._artifact = other
    use_store(monkeypatch, data_mode, store)
    payload = client.get(f"{PREFIX}/layers").json()
    assert not any(layer["id"].startswith("noaa-gfs-surface-cloud") for layer in payload["layers"])


# --- the raster endpoint --------------------------------------------------

def raster_url(layer: str, **params: str) -> str:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{PREFIX}/layers/{layer}/raster" + (f"?{query}" if query else "")


def test_the_rendered_raster_carries_its_pixels_and_its_provenance(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(grid_dataset()))
    stamp = frame_times()[0]
    response = client.get(raster_url(
        "noaa-gfs-surface-cloud-low",
        valid_time=stamp.isoformat().replace("+00:00", "Z"),
        south=str(CELL_BOUNDS["south"]), west=str(CELL_BOUNDS["west"]),
        north=str(CELL_BOUNDS["north"]), east=str(CELL_BOUNDS["east"]),
        width="6", height="6",
    ))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    headers = response.headers
    assert headers["x-weather-image-basis"] == "rendered_grid"
    assert headers["x-weather-evidence-basis"] == "published_artifact"
    assert headers["x-weather-retrieval-status"] == "retrieved"
    assert headers["x-weather-operational"] == "false"
    assert headers["x-weather-source-id"] == "noaa-gfs"
    assert headers["x-weather-crs"] == "EPSG:4326"
    assert headers["x-weather-valid-time"] == stamp.isoformat()
    assert headers["x-weather-reference-time"] == (now() - timedelta(hours=6)).isoformat()
    assert "nearest-neighbor" in headers["x-weather-render-semantics"]
    assert "alpha = round(percent * 2.55)" in headers["x-weather-colormap"]
    assert headers["x-weather-derivation-version"] == "rendered-grid-nearest-v1"
    # The bytes decode to exactly the stored cells, block by block.
    rgba = decode_png(response.content)
    assert rgba[0, 2, 3] == alpha_for(25)
    assert rgba[2, 2, 3] == alpha_for(100)
    assert rgba[4, 0, 3] == 0  # NaN cell


def test_the_rendered_raster_accepts_epsg_3857(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(grid_dataset()))
    response = client.get(raster_url("noaa-gfs-surface-cloud-low", crs="EPSG:3857", width="8", height="8"))
    assert response.status_code == 200, response.text
    assert response.headers["x-weather-crs"] == "EPSG:3857"


def test_an_unknown_crs_is_a_422_not_a_guess(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(grid_dataset()))
    response = client.get(raster_url("noaa-gfs-surface-cloud-low", crs="EPSG:26919"))
    assert response.status_code == 422
    assert "EPSG:3857" in response.json()["detail"]


def test_an_instant_with_no_stored_frame_is_a_422_never_a_reused_frame(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(grid_dataset()))
    distant = (frame_times()[1] + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    response = client.get(raster_url("noaa-gfs-surface-cloud-low", valid_time=distant))
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "no stored frame within" in detail
    assert "only what was ingested" in detail


def test_a_variable_the_artifact_does_not_carry_is_a_404(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(grid_dataset(("cloud_low",))))
    response = client.get(raster_url("noaa-gfs-surface-cloud-high"))
    assert response.status_code == 404
    assert "does not carry cloud_high" in response.json()["detail"]


def test_an_unreadable_artifact_is_a_502_with_nothing_substituted(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(None))
    response = client.get(raster_url("noaa-gfs-surface-cloud-low"))
    assert response.status_code == 502
    assert "no grid was read" in response.json()["detail"]


def test_the_legend_is_the_renderers_own_declared_colormap(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, GridStore(grid_dataset()))
    response = client.get(f"{PREFIX}/layers/noaa-gfs-surface-cloud-low/legend")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-weather-legend-basis"] == "renderer_colormap"
    assert response.headers["x-weather-image-basis"] == "rendered_grid"
    assert "alpha = round(percent * 2.55)" in response.headers["x-weather-colormap"]
    rgba = decode_png(response.content)
    assert rgba[0, 0, 3] == 0 and rgba[0, -1, 3] == 255  # 0 percent to 100 percent
