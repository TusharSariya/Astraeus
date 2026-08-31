"""The /layers/{id}/flow endpoint: derived motion, disclosed, fail-closed.

The flow texture is display-support for the interpolation shader. Pinned
here: it is served only for an exact adjacent published frame pair, aligned
with the frame raster's sampling, quantized over a declared scale, with
derivation headers; every absence (no motion artifact, stale base revision,
unknown pair, non-rendered layer) is a 404 the client answers with a plain
crossfade - never an invented motion field.
"""

from __future__ import annotations

import sys as _sys
from datetime import timezone

import numpy
import pytest
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from ingest.store import CurrentArtifact
from weather_api.app import PREFIX, app
from tests.test_rendered_grids import decode_png, use_store
from tests.test_rendered_cloud_curvilinear import (
    LAT2D,
    LON2D,
    CloudStore,
    cloud_dataset,
    frame_times,
    hrdps_artifact,
)

UTC = timezone.utc
api_module = _sys.modules["weather_api.app"]
client = TestClient(app)


def motion_dataset(
    *,
    u: float = 1.0,
    v: float = 0.0,
    confidence: float = 1.0,
    tangents: tuple[float, float] | None = None,
) -> xarray.Dataset:
    """One-pair motion dataset; ``tangents=(vs_u, ve_u)`` adds Hermite vars."""
    times = frame_times()
    shape = (1,) + LAT2D.shape
    data_vars = {
        "total_cloud_u01": (("pair", "y", "x"), numpy.full(shape, u, dtype="float32")),
        "total_cloud_v01": (("pair", "y", "x"), numpy.full(shape, v, dtype="float32")),
        "total_cloud_u10": (("pair", "y", "x"), numpy.full(shape, -u, dtype="float32")),
        "total_cloud_v10": (("pair", "y", "x"), numpy.full(shape, -v, dtype="float32")),
        "total_cloud_confidence": (("pair", "y", "x"), numpy.full(shape, confidence, dtype="float32")),
    }
    if tangents is not None:
        start_u, end_u = tangents
        data_vars.update({
            "total_cloud_vs_u": (("pair", "y", "x"), numpy.full(shape, start_u, dtype="float32")),
            "total_cloud_vs_v": (("pair", "y", "x"), numpy.zeros(shape, dtype="float32")),
            "total_cloud_ve_u": (("pair", "y", "x"), numpy.full(shape, end_u, dtype="float32")),
            "total_cloud_ve_v": (("pair", "y", "x"), numpy.zeros(shape, dtype="float32")),
        })
    return xarray.Dataset(
        data_vars,
        coords={
            "pair_from": ("pair", numpy.array([times[0].replace(tzinfo=None)], dtype="datetime64[ns]")),
            "pair_to": ("pair", numpy.array([times[1].replace(tzinfo=None)], dtype="datetime64[ns]")),
        },
        attrs={"method": "DIS optical flow (test)", "derivation_version": "cloud-motion-dis-v1", "base_revision_id": "revision-eccc-hrdps-surface"},
    )


def motion_artifact(base_revision: str = "revision-eccc-hrdps-surface") -> CurrentArtifact:
    surface = hrdps_artifact()
    return CurrentArtifact(
        source_id="eccc-hrdps",
        logical_name="cloud_motion",
        revision_id="revision-eccc-hrdps-cloud-motion",
        object_key="artifacts/eccc-hrdps/cloud_motion",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={"derived": True, "base_revision_id": base_revision},
        published_at=surface.published_at,
        run_time=surface.run_time,
        retrieved_at=surface.retrieved_at,
        provider_run_id="eccc-hrdps-2026083112+cloud-motion",
        native_crs="EPSG:4326",
    )


class MotionStore(CloudStore):
    """CloudStore plus the derived motion artifact and its dataset."""

    def __init__(self, *, motion: xarray.Dataset | None, motion_row: CurrentArtifact | None = None) -> None:
        super().__init__(cloud_dataset())
        self._motion = motion
        self._motion_row = motion_row if motion_row is not None else motion_artifact()

    def current(self):
        rows = super().current()
        if self._motion_row is not None:
            rows = rows + [self._motion_row]
        return rows

    def open(self, artifact):
        if artifact.logical_name == "cloud_motion":
            if self._motion is None:
                raise RuntimeError("unreadable motion artifact")
            return self._motion
        return super().open(artifact)


def flow_url(**overrides) -> str:
    from urllib.parse import urlencode

    times = frame_times()
    params = {
        "from": times[0].isoformat(),
        "to": times[1].isoformat(),
        "south": 47.7, "north": 48.1, "west": -53.1, "east": -52.7,
        "width": 8, "height": 8,
    }
    params.update(overrides)
    return f"{PREFIX}/layers/eccc-hrdps-surface-total-cloud/flow?{urlencode(params)}"


def test_flow_is_served_aligned_quantized_and_disclosed(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    response = client.get(flow_url())
    assert response.status_code == 200
    headers = response.headers
    assert headers["x-weather-image-basis"] == "derived_motion"
    assert headers["x-weather-derivation-version"] == "cloud-motion-dis-v1"
    assert headers["x-weather-frame-from"] == frame_times()[0].isoformat()
    assert headers["x-weather-frame-to"] == frame_times()[1].isoformat()
    assert "not evidence" in headers["x-weather-render-semantics"]
    scale = float(headers["x-weather-flow-scale"])
    assert scale > 0
    rgba = decode_png(response.content)
    inside = rgba[..., 2] == 255  # confidence 1 where a stored cell answers
    assert inside.any()
    # Uniform +1-cell column flow: decoded x-displacement is positive (east)
    # everywhere inside, and the largest magnitude decodes back to the scale.
    decoded_dx = (rgba[..., 0].astype("float64") / 255.0 - 0.5) * 2.0 * scale
    assert float(decoded_dx[inside].min()) > 0
    assert float(numpy.abs(decoded_dx[inside]).max()) <= scale + 1e-6
    # Outside pixels carry zero flow and zero confidence, never an invention.
    outside = ~inside
    if outside.any():
        assert int(rgba[..., 2][outside].max()) == 0


def test_tangents_are_served_side_by_side_with_their_own_scale(monkeypatch, data_mode):
    # Start knot 0.5 cells east, end knot 1 cell east (small enough that the
    # 3x3 fixture grid does not clamp every path at its edge): the left half
    # of the double-width texture decodes to half the right half's largest
    # displacement, and the largest magnitude decodes back to the scale.
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset(tangents=(0.5, 1.0))))
    response = client.get(flow_url(texture="tangents"))
    assert response.status_code == 200
    headers = response.headers
    assert headers["x-weather-image-basis"] == "derived_motion"
    assert headers["x-weather-flow-texture"] == "tangents"
    assert "Hermite" in headers["x-weather-render-semantics"]
    assert "not evidence" in headers["x-weather-render-semantics"]
    scale = float(headers["x-weather-flow-scale"])
    assert scale > 0
    rgba = decode_png(response.content)
    width = rgba.shape[1] // 2
    assert rgba.shape[1] == 2 * width
    assert int(rgba[..., 3].min()) == 255  # a vector never rides the alpha channel
    start_dx = (rgba[:, :width, 0].astype("float64") / 255.0 - 0.5) * 2.0 * scale
    end_dx = (rgba[:, width:, 0].astype("float64") / 255.0 - 0.5) * 2.0 * scale
    end_max = float(numpy.abs(end_dx).max())
    assert end_max == pytest.approx(scale, rel=0.02)
    assert float(numpy.abs(start_dx).max()) / end_max == pytest.approx(0.5, abs=0.05)


def test_an_artifact_without_tangents_is_a_404_for_tangents(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    response = client.get(flow_url(texture="tangents"))
    assert response.status_code == 404
    assert "predates the Hermite derivation" in response.json()["detail"]
    # The motion texture is still served: the client falls back one rung.
    assert client.get(flow_url()).status_code == 200


def test_an_unknown_texture_is_a_422(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    response = client.get(flow_url(texture="curvature"))
    assert response.status_code == 422


def test_a_stale_base_revision_is_a_404_not_a_wrong_warp(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset(), motion_row=motion_artifact("some-older-revision")))
    response = client.get(flow_url())
    assert response.status_code == 404
    assert "not the current surface revision" in response.json()["detail"]


def test_an_unknown_pair_is_a_404(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    times = frame_times()
    response = client.get(flow_url(**{"from": times[1].isoformat(), "to": times[0].isoformat()}))
    assert response.status_code == 404
    assert "no derived motion pair" in response.json()["detail"]


def test_no_motion_artifact_is_a_404(monkeypatch, data_mode):
    store = MotionStore(motion=None, motion_row=None)
    store._motion_row = None
    use_store(monkeypatch, data_mode, store)
    response = client.get(flow_url())
    assert response.status_code == 404
    assert "no derived cloud-motion artifact" in response.json()["detail"]


def test_a_non_rendered_layer_has_no_flow(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    from urllib.parse import urlencode

    times = frame_times()
    response = client.get(
        f"{PREFIX}/layers/geomet-live-hrdps-nt/flow?{urlencode({'from': times[0].isoformat(), 'to': times[1].isoformat()})}"
    )
    assert response.status_code == 404
    assert "rendered-grid layers" in response.json()["detail"]


def test_the_motion_artifact_is_not_listed_as_a_layer(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    payload = client.get(f"{PREFIX}/layers").json()
    ids = {layer["id"] for layer in payload["layers"]}
    assert not any("cloud-motion" in identifier or "cloud_motion" in identifier for identifier in ids)
