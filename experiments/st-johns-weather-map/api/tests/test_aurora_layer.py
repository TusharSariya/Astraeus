"""The aurora-oval layer: a disclosed model nowcast, rendered fail-closed.

The store is stubbed with a synthetic OVATION grid of the shape the SWPC
adapter publishes. Under test is the rendering contract: cells below the
disclosed 2 percent threshold are fully transparent, the green-to-red ramp is
exactly the declared colormap, the offered frame is the file's own forecast
instant, staleness and absence remove the layer with a notice, and every
response says what it is.
"""

from __future__ import annotations

import sys as _sys
from datetime import datetime, timedelta, timezone

import numpy
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from ingest.store import CurrentArtifact
from weather_api import aurora
from weather_api.app import PREFIX, app
from weather_api.fixtures import now
from tests.test_rendered_grids import decode_png, use_store

UTC = timezone.utc
api_module = _sys.modules["weather_api.app"]
client = TestClient(app)

#: Cell centres, ascending, 1 degree, as the adapter stores them.
LATS = numpy.array([46.0, 47.0, 48.0, 49.0])
LONS = numpy.array([-54.0, -53.0, -52.0, -51.0])
CELL_BOUNDS = {"south": 45.5, "west": -54.5, "north": 49.5, "east": -50.5}

#: Distinct probabilities: below-threshold cells, the exact threshold, the
#: exact maximum, and a NaN (a cell the crop never filled).
PROBS = numpy.array([
    [0.0, 1.0, 1.9, 2.0],
    [5.0, 10.0, 20.0, 30.0],
    [50.0, 60.0, 70.0, numpy.nan],
    [90.0, 95.0, 99.0, 100.0],
], dtype="float64")

#: The forecast instant sits just ahead of the wall clock, as a real OVATION
#: nowcast does (~30-40 min past its observation instant). Fixed at import so
#: every reference within a test run agrees.
FORECAST_INSTANT = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=30)


def aurora_dataset(valid_time: datetime | None = None, variables: tuple[str, ...] = ("aurora_probability",)) -> xarray.Dataset:
    stamp = valid_time or FORECAST_INSTANT
    stamps = [numpy.datetime64(stamp.replace(tzinfo=None), "ns")]
    data = {
        name: (("valid_time", "latitude", "longitude"), PROBS[None, ...].copy(), {"units": "percent"})
        for name in variables
    }
    return xarray.Dataset(data, coords={"valid_time": stamps, "latitude": LATS, "longitude": LONS})


def ovation_artifact() -> CurrentArtifact:
    stamp = now()
    return CurrentArtifact(
        source_id="noaa-swpc-ovation",
        logical_name="aurora_grid",
        revision_id="revision-swpc-ovation",
        object_key="artifacts/noaa-swpc-ovation/aurora_grid",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={"product": "OVATION aurora probability nowcast"},
        published_at=stamp,
        run_time=stamp - timedelta(minutes=40),
        retrieved_at=stamp,
        provider_run_id="swpc-ovation-202608310149",
        native_crs="EPSG:4326",
    )


class AuroraStore:
    """A reachable live store publishing exactly one OVATION grid artifact."""

    skipped: list = []

    def __init__(self, dataset, artifact=None):
        self._dataset = dataset
        self._artifact = artifact if artifact is not None else ovation_artifact()

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


def _raster(params=None):
    query = {
        "valid_time": FORECAST_INSTANT.isoformat(),
        "width": 8, "height": 8,
        **CELL_BOUNDS,
    }
    query.update(params or {})
    return client.get(f"{PREFIX}/layers/{aurora.LAYER_ID}/raster", params=query)


# ------------------------------------------------------------- rendering


def test_below_threshold_is_transparent_and_the_ramp_is_the_declared_one(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, AuroraStore(aurora_dataset()))
    response = _raster()
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    pixels = decode_png(response.content)

    # 8x8 pixels over 4x4 cells: each cell is a 2x2 block; row 0 is north.
    def cell(row, col):
        return pixels[(3 - row) * 2, col * 2]

    for col in range(3):  # 0.0, 1.0 and 1.9 percent: below the threshold
        assert tuple(cell(0, col)) == (0, 0, 0, 0), f"cell {col} below the 2 percent threshold must be transparent"
    threshold = cell(0, 3)  # exactly 2 percent: the green end at minimum alpha
    assert tuple(threshold) == (*aurora.GREEN_RGB, aurora.ALPHA_MIN)
    maximum = cell(3, 3)  # 100 percent: the red end at maximum alpha
    assert tuple(maximum) == (*aurora.RED_RGB, aurora.ALPHA_MAX)
    assert aurora.ALPHA_MAX < 255, "the oval never fully hides the basemap"
    missing = cell(2, 3)  # NaN: no stored value, never painted
    assert tuple(missing) == (0, 0, 0, 0)


def test_blocks_are_uniform_nearest_neighbour(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, AuroraStore(aurora_dataset()))
    pixels = decode_png(_raster().content)
    for row in range(0, 8, 2):
        for col in range(0, 8, 2):
            block = pixels[row:row + 2, col:col + 2].reshape(4, 4)
            assert (block == block[0]).all(), "each 2x2 block is one stored cell, no blending"


# ------------------------------------------------------------- provenance


def test_headers_declare_rendered_grid_provenance(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, AuroraStore(aurora_dataset()))
    headers = _raster().headers
    assert headers["X-Weather-Image-Basis"] == "rendered_grid"
    assert headers["X-Weather-Evidence-Basis"] == "published_artifact"
    assert headers["X-Weather-Source-Id"] == "noaa-swpc-ovation"
    assert headers["X-Weather-Retrieval-Status"] == "retrieved"
    assert headers["X-Weather-Valid-Time"] == FORECAST_INSTANT.isoformat()
    assert "Forecast Time" in headers["X-Weather-Time-Semantics"]
    assert headers["X-Weather-Operational"] == "false"
    assert "2 percent" in headers["X-Weather-Colormap"]
    assert "green" in headers["X-Weather-Colormap"]


# --------------------------------------------------------------- failures


def test_frame_beyond_tolerance_is_422(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, AuroraStore(aurora_dataset()))
    late = FORECAST_INSTANT + timedelta(minutes=45)
    response = _raster({"valid_time": late.isoformat()})
    assert response.status_code == 422
    assert "nearest" in response.json()["detail"]


def test_missing_artifact_is_404(monkeypatch, data_mode):
    store = AuroraStore(aurora_dataset())
    store._artifact = None
    use_store(monkeypatch, data_mode, store)
    assert _raster().status_code == 404


def test_unreadable_artifact_is_502_nothing_substituted(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, AuroraStore(None))
    response = _raster()
    assert response.status_code == 502
    assert "no aurora grid was read" in response.json()["detail"]


# ------------------------------------------------------------- the index


def test_layer_listed_in_the_rendered_grid_group_once(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, AuroraStore(aurora_dataset()))
    layers = client.get(f"{PREFIX}/layers").json()["layers"]
    by_id = {layer["id"]: layer for layer in layers}
    assert aurora.LAYER_ID in by_id
    entry = by_id[aurora.LAYER_ID]
    assert entry["group"] == "rendered_grid"
    assert entry["evidence_basis"] == "published_artifact"
    assert entry["raster_available"] and entry["legend_available"]
    assert entry["upstream_wms_layer"] is None
    assert [datetime.fromisoformat(t) for t in entry["times"]] == [FORECAST_INSTANT]
    # One native interval of the OVATION grid.
    assert entry["staleness_tolerance_seconds"] == 600
    assert aurora.STALENESS_TOLERANCE_SECONDS == 600  # the unknown-cadence fallback agrees
    assert "OVATION model probabilities" in entry["semantics"]
    assert "Kp 4-5" in entry["semantics"]
    # The generic artifact-derived listing does not duplicate it.
    assert "noaa-swpc-ovation-aurora_grid" not in by_id


def test_stale_grid_removes_the_layer_with_a_notice(monkeypatch, data_mode):
    stale = aurora_dataset(valid_time=datetime.now(UTC) - timedelta(hours=3))
    use_store(monkeypatch, data_mode, AuroraStore(stale))
    body = client.get(f"{PREFIX}/layers").json()
    assert aurora.LAYER_ID not in {layer["id"] for layer in body["layers"]}
    assert any("staleness tolerance" in notice and "never rendered as absence of aurora" in notice for notice in body["notices"])


def test_absent_artifact_removes_the_layer_with_a_notice(monkeypatch, data_mode):
    """Another artifact is published, so the index is live; the aurora feed is
    simply missing, and the index says so rather than staying silent."""
    from tests.test_rendered_grids import GridStore, grid_dataset

    use_store(monkeypatch, data_mode, GridStore(grid_dataset()))
    body = client.get(f"{PREFIX}/layers").json()
    assert aurora.LAYER_ID not in {layer["id"] for layer in body["layers"]}
    assert any(aurora.LAYER_ID in notice and "never rendered as absence of aurora" in notice for notice in body["notices"])


def test_missing_variable_is_a_notice_not_a_guess(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, AuroraStore(aurora_dataset(variables=("something_else",))))
    body = client.get(f"{PREFIX}/layers").json()
    assert aurora.LAYER_ID not in {layer["id"] for layer in body["layers"]}
    assert any("aurora_probability" in notice for notice in body["notices"])


# --------------------------------------------------------------- legend


def test_legend_disclosure_names_the_model_the_horizon_the_threshold_and_the_guidance(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, AuroraStore(aurora_dataset()))
    response = client.get(f"{PREFIX}/layers/{aurora.LAYER_ID}/legend")
    assert response.status_code == 200
    assert response.headers["X-Weather-Legend-Basis"] == "renderer_colormap"
    assert response.headers["X-Weather-Image-Basis"] == "rendered_grid"
    caption = response.headers["X-Weather-Legend-Semantics"]
    assert "OVATION" in caption
    assert "30-40" in caption
    assert "2 percent" in caption
    assert "Kp 4-5" in caption
    assert "53-54" in caption
    pixels = decode_png(response.content)
    # The below-threshold segment is drawn over a visible checker (two greys).
    assert len(numpy.unique(pixels[:, :32, 0])) >= 2
