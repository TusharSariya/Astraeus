"""HRDPS/RDPS total-cloud rasters rendered from stored rotated grids.

The ECCC models are published on rotated lat/lon grids, so their stored
``latitude``/``longitude`` are 2-D fields over anonymous dimensions and the
containing-cell lookup of the rectilinear renderer does not apply. What is
under test is the honesty of the curvilinear analogue:

* every painted pixel is the stored value of the single nearest published
  cell centre - never an interpolation, never a regrid;
* a pixel farther than half a cell diagonal from every centre is outside the
  grid and stays transparent;
* the layer, headers and semantics disclose the method
  (``curvilinear_nearest_cell``) and take product/resolution from the
  artifact's own provenance;
* the RDPS twin is offered under the same rules.
"""

from __future__ import annotations

import sys as _sys
from datetime import datetime, timedelta, timezone

import numpy
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from ingest.store import CurrentArtifact
from weather_api import grids
from weather_api.app import PREFIX, app
from weather_api.fixtures import now
from tests.test_rendered_grids import alpha_for, decode_png, use_store

UTC = timezone.utc
api_module = _sys.modules["weather_api.app"]
client = TestClient(app)

# --- the synthetic rotated grid -------------------------------------------

#: A 3x3 grid whose rows/columns are NOT aligned with latitude/longitude:
#: each step along an axis moves in both coordinates, exactly the shape a
#: rotated lat/lon grid produces after cfgrib decodes it.
_I, _J = numpy.meshgrid(numpy.arange(3), numpy.arange(3), indexing="ij")
LAT2D = 48.0 - 0.1 * _I + 0.02 * _J
LON2D = -53.0 + 0.1 * _J + 0.02 * _I

#: Distinct per-cell percentages; an interpolated pixel would be a wrong byte.
FRAME0 = numpy.array([
    [0.0, 25.0, 50.0],
    [75.0, 100.0, 12.0],
    [numpy.nan, 60.0, 88.0],
])
FRAME1 = numpy.clip(FRAME0 + 5.0, 0, 100)


def frame_times() -> list[datetime]:
    base = now().replace(minute=0, second=0, microsecond=0)
    return [base, base + timedelta(hours=1)]


def cloud_dataset() -> xarray.Dataset:
    stamps = [numpy.datetime64(stamp.replace(tzinfo=None), "ns") for stamp in frame_times()]
    data = numpy.stack([FRAME0, FRAME1])
    return xarray.Dataset(
        {"total_cloud_opacity": (("valid_time", "y", "x"), data, {"units": "percent"})},
        coords={
            "valid_time": stamps,
            "latitude": (("y", "x"), LAT2D),
            "longitude": (("y", "x"), LON2D),
        },
    )


def hrdps_artifact(source_id: str = "eccc-hrdps") -> CurrentArtifact:
    stamp = now()
    return CurrentArtifact(
        source_id=source_id,
        logical_name="surface",
        revision_id=f"revision-{source_id}-surface",
        object_key=f"artifacts/{source_id}/surface",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={"product": source_id.upper(), "native_resolution": "RLatLon0.0225"},
        published_at=stamp,
        run_time=stamp - timedelta(hours=3),
        retrieved_at=stamp,
        provider_run_id=f"{source_id}-2026083112",
        native_crs="EPSG:4326",
    )


class CloudStore:
    """A reachable live store publishing exactly one rotated-grid artifact."""

    def __init__(self, dataset: xarray.Dataset | None, artifact: CurrentArtifact | None = None) -> None:
        self._dataset = dataset
        self._artifact = artifact if artifact is not None else hrdps_artifact()

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


def centre_bounds(row: int, column: int, *, pad: float = 0.001) -> dict[str, float]:
    """A tiny box whose single-pixel centre is exactly one cell centre."""
    lat, lon = float(LAT2D[row, column]), float(LON2D[row, column])
    return {"south": lat - pad, "north": lat + pad, "west": lon - pad, "east": lon + pad}


# --- sampler exactness -----------------------------------------------------

def test_each_pixel_is_the_nearest_published_cell_and_nothing_else():
    for row, column in ((0, 0), (1, 1), (2, 2), (0, 2)):
        sampled, inside = grids.sample_field_curvilinear(
            FRAME0, LAT2D, LON2D, bounds=centre_bounds(row, column), width=1, height=1
        )
        assert bool(inside[0, 0]) is True
        expected = FRAME0[row, column]
        got = sampled[0, 0]
        assert (numpy.isnan(expected) and numpy.isnan(got)) or got == expected


def test_a_pixel_beyond_half_a_cell_diagonal_is_outside_and_unpainted():
    # Two cell pitches away from the grid's north-west corner.
    far = {"south": 48.35, "north": 48.45, "west": -53.35, "east": -53.25}
    sampled, inside = grids.sample_field_curvilinear(FRAME0, LAT2D, LON2D, bounds=far, width=2, height=2)
    assert not inside.any()
    rgba = grids.rasterize(FRAME0, LAT2D, LON2D, bounds=far, width=2, height=2)
    assert int(rgba[..., 3].max()) == 0


def test_rasterize_dispatches_on_coordinate_dimensionality():
    rgba = grids.rasterize(FRAME0, LAT2D, LON2D, bounds=centre_bounds(1, 1), width=1, height=1)
    assert rgba[0, 0, 3] == alpha_for(100.0)
    assert list(rgba[0, 0, 0:3]) == [255, 255, 255]
    # The stored-NaN cell renders transparent, never a guessed value.
    rgba = grids.rasterize(FRAME0, LAT2D, LON2D, bounds=centre_bounds(2, 0), width=1, height=1)
    assert rgba[0, 0, 3] == 0


# --- the layers ------------------------------------------------------------

def test_the_hrdps_total_cloud_layer_is_offered_from_the_stored_grid(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, CloudStore(cloud_dataset()))
    payload = client.get(f"{PREFIX}/layers").json()
    by_id = {layer["id"]: layer for layer in payload["layers"]}
    layer = by_id["eccc-hrdps-surface-total-cloud"]
    assert layer["group"] == "rendered_grid"
    assert layer["field"] == "total_cloud_opacity"
    assert layer["product"] == "ECCC-HRDPS"
    assert layer["units"] == "percent"
    assert layer["evidence_basis"] == "published_artifact"
    assert layer["raster_available"] is True
    assert layer["legend_available"] is True
    semantics = layer["semantics"]
    assert "rendered by this experiment from the retrieved ECCC-HRDPS field" in semantics
    assert "native grid RLatLon0.0225" in semantics
    assert "eccc-hrdps artifact" in semantics
    stamps = [stamp.isoformat() for stamp in frame_times()]
    assert [datetime.fromisoformat(stamp).isoformat() for stamp in layer["times"]] == stamps


def test_the_rdps_twin_is_offered_under_the_same_rules(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, CloudStore(cloud_dataset(), hrdps_artifact("eccc-rdps")))
    payload = client.get(f"{PREFIX}/layers").json()
    by_id = {layer["id"]: layer for layer in payload["layers"]}
    layer = by_id["eccc-rdps-surface-total-cloud"]
    assert layer["group"] == "rendered_grid"
    assert layer["product"] == "ECCC-RDPS"
    assert "eccc-hrdps-surface-total-cloud" not in by_id


def test_the_raster_disclosed_the_curvilinear_method_and_its_provenance(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, CloudStore(cloud_dataset()))
    bounds = centre_bounds(1, 1)
    stamp = frame_times()[0]
    response = client.get(
        f"{PREFIX}/layers/eccc-hrdps-surface-total-cloud/raster",
        params={
            "valid_time": stamp.isoformat(),
            "south": bounds["south"],
            "west": bounds["west"],
            "north": bounds["north"],
            "east": bounds["east"],
            "width": 1,
            "height": 1,
        },
    )
    assert response.status_code == 200
    headers = response.headers
    assert headers["x-weather-image-basis"] == "rendered_grid"
    assert headers["x-weather-sample-method"] == "curvilinear_nearest_cell"
    assert headers["x-weather-derivation-version"] == "rendered-grid-nearest-cell-v1"
    assert "nearest published cell centre" in headers["x-weather-render-semantics"]
    assert "half a cell diagonal" in headers["x-weather-render-semantics"]
    assert headers["x-weather-source-id"] == "eccc-hrdps"
    assert headers["x-weather-valid-time"] == stamp.isoformat()
    rgba = decode_png(response.content)
    assert rgba[0, 0, 3] == alpha_for(100.0)


def test_a_missing_variable_is_a_notice_and_no_layer(monkeypatch, data_mode):
    dataset = cloud_dataset().drop_vars("total_cloud_opacity")
    use_store(monkeypatch, data_mode, CloudStore(dataset))
    payload = client.get(f"{PREFIX}/layers").json()
    ids = {layer["id"] for layer in payload["layers"]}
    assert "eccc-hrdps-surface-total-cloud" not in ids
    assert any(
        "eccc-hrdps-surface-total-cloud" in notice and "does not carry" in notice for notice in payload["notices"]
    )
