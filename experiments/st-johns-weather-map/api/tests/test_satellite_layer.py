"""The GOES-19 cloud-mask layer: five honest states, observed scans only.

The store is stubbed with a synthetic regridded cloud-mask artifact of the
shape the ingest adapter publishes. Under test is the rendering contract:
invalid is never clear, opacity is confidence, frames are exactly the stored
scans, staleness fails closed, and every response says what it is.
"""

from __future__ import annotations

import sys as _sys
from datetime import datetime, timedelta, timezone

import numpy
import pytest
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from ingest.store import CurrentArtifact
from weather_api import satellite
from weather_api.app import PREFIX, app
from weather_api.fixtures import now
from tests.test_rendered_grids import decode_png, use_store

UTC = timezone.utc
api_module = _sys.modules["weather_api.app"]
client = TestClient(app)

#: Cell centres, ascending like the adapter publishes.
LATS = numpy.array([47.0, 47.25, 47.5, 47.75])
LONS = numpy.array([-53.0, -52.75, -52.5, -52.25])
CELL_BOUNDS = {"south": 46.875, "west": -53.125, "north": 47.875, "east": -52.125}

#: One cell of every state: clear, probably clear, probably cloudy,
#: cloudy p=1.0, cloudy p=0.0, invalid.
CLASSES = numpy.array([
    [0, 0, 1, 1],
    [2, 2, 3, 3],
    [3, 3, 255, 255],
    [0, 1, 2, 3],
], dtype="uint8")
PROBS = numpy.array([
    [0.05, 0.05, 0.3, 0.3],
    [0.6, 0.6, 1.0, 1.0],
    [0.0, 0.0, numpy.nan, numpy.nan],
    [0.05, 0.3, 0.6, 0.8],
], dtype="float32")


#: Scan times sit just behind the WALL clock: the layer index judges
#: staleness against real now (fixtures.now() is floored to the hour, which
#: would misread every fresh 10-minute scan as future). Fixed at import so
#: every reference within a test run agrees.
_SCAN_BASE = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)


def scan_times() -> list[datetime]:
    return [_SCAN_BASE - timedelta(minutes=10), _SCAN_BASE]


def mask_dataset(variables=("cloud_class", "cloud_probability", "parallax_uncorrected")) -> xarray.Dataset:
    stamps = [numpy.datetime64(stamp.replace(tzinfo=None), "ns") for stamp in scan_times()]
    data = {}
    if "cloud_class" in variables:
        data["cloud_class"] = (("valid_time", "latitude", "longitude"), numpy.stack([CLASSES, CLASSES]))
    if "cloud_probability" in variables:
        data["cloud_probability"] = (("valid_time", "latitude", "longitude"), numpy.stack([PROBS, PROBS]))
    if "parallax_uncorrected" in variables:
        zero = numpy.zeros_like(CLASSES)
        data["parallax_uncorrected"] = (("valid_time", "latitude", "longitude"), numpy.stack([zero, zero]))
    return xarray.Dataset(data, coords={"valid_time": stamps, "latitude": LATS, "longitude": LONS})


def goes_artifact(published_at: datetime | None = None) -> CurrentArtifact:
    stamp = published_at or now()
    return CurrentArtifact(
        source_id="noaa-goes-east",
        logical_name="cloud_mask",
        revision_id="revision-goes-cloud-mask",
        object_key="artifacts/noaa-goes-east/cloud_mask",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={
            "product": "GOES-19 ABI L2 Enterprise Cloud Mask (ACMF Full Disk) + Cloud Top Height (ACHAF)",
            "cloud_top_height_maturity": "NOAA Provisional",
        },
        published_at=stamp,
        run_time=stamp,
        retrieved_at=stamp,
        provider_run_id="goes19-acmf-20262421150215",
        native_crs="EPSG:4326",
    )


class MaskStore:
    skipped: list = []

    def __init__(self, dataset, artifact=None):
        self._dataset = dataset
        self._artifact = artifact if artifact is not None else goes_artifact()

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
        "valid_time": scan_times()[-1].isoformat(),
        "width": 8, "height": 8,
        **CELL_BOUNDS,
    }
    query.update(params or {})
    return client.get(f"{PREFIX}/layers/{satellite.LAYER_ID}/raster", params=query)


# ------------------------------------------------------------- rendering

def test_five_states_render_with_declared_alphas(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(mask_dataset()))
    response = _raster()
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    pixels = decode_png(response.content)
    # 8x8 pixels over a 4x4 grid: each cell is a 2x2 block; row 0 is north.
    def cell(row, col):
        return pixels[(3 - row) * 2, col * 2]

    clear = cell(0, 0)
    assert tuple(clear) == (0, 0, 0, 0), "clear is fully transparent"
    probably_clear = cell(0, 2)
    assert tuple(probably_clear) == (255, 255, 255, satellite.ALPHA_PROBABLY_CLEAR)
    probably_cloudy = cell(1, 0)
    assert tuple(probably_cloudy) == (255, 255, 255, satellite.ALPHA_PROBABLY_CLOUDY)
    cloudy_full = cell(1, 2)
    assert tuple(cloudy_full) == (255, 255, 255, satellite.ALPHA_CLOUDY_MAX)
    cloudy_zero = cell(2, 0)
    assert tuple(cloudy_zero) == (255, 255, 255, satellite.ALPHA_CLOUDY_MIN)
    assert satellite.ALPHA_CLOUDY_MAX < 255, "cloudy never fully opaque"


def test_invalid_is_distinct_never_clear_never_white(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(mask_dataset()))
    pixels = decode_png(_raster().content)
    invalid = pixels[(3 - 2) * 2, 2 * 2]
    assert tuple(invalid) == satellite.INVALID_RGBA
    assert invalid[3] > 0, "invalid is never transparent"
    assert not (invalid[0] == invalid[1] == invalid[2] == 255), "invalid is never white"


def test_block_uniform_nearest_neighbour(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(mask_dataset()))
    pixels = decode_png(_raster().content)
    for row in range(0, 8, 2):
        for col in range(0, 8, 2):
            block = pixels[row:row + 2, col:col + 2].reshape(4, 4)
            assert (block == block[0]).all(), "each 2x2 block is one stored cell, no blending"


# ------------------------------------------------------------- provenance

def test_headers_declare_rendered_grid_provenance(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(mask_dataset()))
    response = _raster()
    headers = response.headers
    assert headers["X-Weather-Image-Basis"] == "rendered_grid"
    assert headers["X-Weather-Evidence-Basis"] == "published_artifact"
    assert headers["X-Weather-Source-Id"] == "noaa-goes-east"
    assert headers["X-Weather-Retrieval-Status"] == "retrieved"
    assert headers["X-Weather-Time-Semantics"] == "observed at the instant in X-Weather-Valid-Time"
    assert headers["X-Weather-Valid-Time"] == scan_times()[-1].isoformat()
    assert headers["X-Weather-Cloud-Top-Height-Maturity"] == "NOAA Provisional"
    assert headers["X-Weather-Operational"] == "false"
    assert "confidence" in headers["X-Weather-Colormap"].lower()


# --------------------------------------------------------------- failures

def test_frame_beyond_half_cadence_is_422(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(mask_dataset()))
    late = scan_times()[-1] + timedelta(minutes=45)
    response = _raster({"valid_time": late.isoformat()})
    assert response.status_code == 422
    assert "nearest" in response.json()["detail"]


def test_missing_artifact_is_404(monkeypatch, data_mode):
    store = MaskStore(mask_dataset())
    store._artifact = None
    use_store(monkeypatch, data_mode, store)
    response = _raster()
    assert response.status_code == 404


def test_unreadable_artifact_is_502_nothing_substituted(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(None))
    response = _raster()
    assert response.status_code == 502
    assert "no cloud-mask grid was read" in response.json()["detail"]


# ------------------------------------------------------------- the index

def test_layer_listed_beside_untouched_proxies(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(mask_dataset()))
    layers = client.get(f"{PREFIX}/layers").json()["layers"]
    by_id = {layer["id"]: layer for layer in layers}
    assert satellite.LAYER_ID in by_id
    entry = by_id[satellite.LAYER_ID]
    assert entry["group"] == "satellite"
    assert entry["evidence_basis"] == "published_artifact"
    assert entry["raster_available"] and entry["legend_available"]
    assert entry["upstream_wms_layer"] is None
    assert [datetime.fromisoformat(t) for t in entry["times"]] == scan_times()
    assert entry["staleness_tolerance_seconds"] == satellite.STALENESS_TOLERANCE_SECONDS
    assert "never a definitive statement of clear sky" in entry["semantics"]
    # The generic artifact-derived listing does not duplicate it.
    assert "noaa-goes-east-cloud_mask" not in by_id


def test_stale_scan_makes_layer_unavailable_not_clear(monkeypatch, data_mode):
    old = mask_dataset()
    shift = numpy.timedelta64(2, "h")
    old = old.assign_coords(valid_time=old["valid_time"].values - shift)
    use_store(monkeypatch, data_mode, MaskStore(old))
    body = client.get(f"{PREFIX}/layers").json()
    assert satellite.LAYER_ID not in {layer["id"] for layer in body["layers"]}
    assert any("staleness tolerance" in notice and "clear sky" in notice for notice in body["notices"])


def test_missing_variable_is_a_notice_not_a_guess(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(mask_dataset(variables=("cloud_class",))))
    body = client.get(f"{PREFIX}/layers").json()
    assert satellite.LAYER_ID not in {layer["id"] for layer in body["layers"]}
    assert any("cloud_probability" in notice for notice in body["notices"])


# --------------------------------------------------------------- legend

def test_legend_is_renderers_own_with_caption(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MaskStore(mask_dataset()))
    response = client.get(f"{PREFIX}/layers/{satellite.LAYER_ID}/legend")
    assert response.status_code == 200
    assert response.headers["X-Weather-Legend-Basis"] == "renderer_colormap"
    caption = response.headers["X-Weather-Legend-Semantics"]
    assert "confidence" in caption.lower() and "thickness" in caption.lower()
    assert "90%" in caption and "88%" in caption
    assert "Provisional" in caption
    assert "parallax" in caption.lower()
    pixels = decode_png(response.content)
    # The clear swatch is visible: it shows the checkered backdrop, in two greys.
    clear_swatch = pixels[:, :52, 0]
    assert len(numpy.unique(clear_swatch)) >= 2, "the transparent clear state is drawn over a visible checker"
