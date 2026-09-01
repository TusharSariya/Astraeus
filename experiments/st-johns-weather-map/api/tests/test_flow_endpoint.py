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

from typing import Any

import numpy
import pytest
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from ingest.store import CurrentArtifact
from weather_api import grids
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
    advect_weight: float | None = None,
    tangents: tuple[float, float] | None = None,
    visibility: tuple[float, float] | None = None,
) -> xarray.Dataset:
    """One-pair motion dataset; ``tangents=(vs_u, ve_u)`` adds Hermite vars.

    ``visibility=(v0, v1)`` adds the per-frame fusion weights the
    ``visibility-blend`` method publishes for itself.
    """
    times = frame_times()
    shape = (1,) + LAT2D.shape
    data_vars = {
        "total_cloud_u01": (("pair", "y", "x"), numpy.full(shape, u, dtype="float32")),
        "total_cloud_v01": (("pair", "y", "x"), numpy.full(shape, v, dtype="float32")),
        "total_cloud_u10": (("pair", "y", "x"), numpy.full(shape, -u, dtype="float32")),
        "total_cloud_v10": (("pair", "y", "x"), numpy.full(shape, -v, dtype="float32")),
        "total_cloud_confidence": (("pair", "y", "x"), numpy.full(shape, confidence, dtype="float32")),
    }
    if advect_weight is not None:
        data_vars["total_cloud_advect_weight"] = (("pair", "y", "x"), numpy.full(shape, advect_weight, dtype="float32"))
    if tangents is not None:
        start_u, end_u = tangents
        data_vars.update({
            "total_cloud_vs_u": (("pair", "y", "x"), numpy.full(shape, start_u, dtype="float32")),
            "total_cloud_vs_v": (("pair", "y", "x"), numpy.zeros(shape, dtype="float32")),
            "total_cloud_ve_u": (("pair", "y", "x"), numpy.full(shape, end_u, dtype="float32")),
            "total_cloud_ve_v": (("pair", "y", "x"), numpy.zeros(shape, dtype="float32")),
        })
    if visibility is not None:
        first, second = visibility
        data_vars.update({
            "total_cloud_vis0": (("pair", "y", "x"), numpy.full(shape, first, dtype="float32")),
            "total_cloud_vis1": (("pair", "y", "x"), numpy.full(shape, second, dtype="float32")),
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


def test_the_blue_channel_carries_the_display_weight_when_the_artifact_has_one(monkeypatch, data_mode):
    # The client mixes advection against a crossfade on this channel. Newer
    # artifacts publish a display weight that already accounts for
    # neighbourhood support, in-place development and the held-out skill
    # veto; it is that, not the raw forward-backward agreement, that must be
    # served. Here the raw agreement is total and the display weight is a
    # fifth: the channel must read the fifth.
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset(confidence=1.0, advect_weight=0.2)))
    rgba = decode_png(client.get(flow_url()).content)
    inside = rgba[..., 0] > 0  # a stored cell answered here
    assert inside.any()
    assert int(rgba[..., 2][inside].max()) == pytest.approx(51, abs=1)
    assert "weight the display mixes advection" in client.get(flow_url()).headers["x-weather-render-semantics"]


def test_an_artifact_without_a_display_weight_still_serves_its_consistency(monkeypatch, data_mode):
    # An artifact from the earlier derivation carries no display weight. It
    # keeps serving the consistency it was built to be mixed on, rather than
    # 404ing or serving zero, which would silently turn every pair into a
    # crossfade.
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset(confidence=0.6)))
    response = client.get(flow_url())
    assert response.status_code == 200
    rgba = decode_png(response.content)
    inside = rgba[..., 0] > 0
    assert int(rgba[..., 2][inside].max()) == pytest.approx(153, abs=1)


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


def test_the_backward_flow_is_served_quantized_and_disclosed(monkeypatch, data_mode):
    # The frame1 -> frame0 field has been derived and stored every cycle and
    # never served. The intermediate-flow construction needs it, and it must
    # arrive under the same quantization and pixel-conversion rule as the
    # motion texture or the two cannot be combined componentwise.
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset(u=1.0)))
    response = client.get(flow_url(texture="backward"))
    assert response.status_code == 200
    headers = response.headers
    assert headers["x-weather-image-basis"] == "derived_motion"
    assert headers["x-weather-flow-texture"] == "backward"
    assert "frame 1 -> frame 0" in headers["x-weather-render-semantics"]
    assert "not evidence" in headers["x-weather-render-semantics"]
    scale = float(headers["x-weather-flow-scale"])
    assert scale > 0
    rgba = decode_png(response.content)
    assert int(rgba[..., 3].min()) == 255  # a vector never rides the alpha channel
    decoded_dx = (rgba[..., 0].astype("float64") / 255.0 - 0.5) * 2.0 * scale
    # The fixture's backward flow is the negation of its +1-cell forward flow,
    # so inside pixels decode westward where the motion texture decodes east -
    # proof the served field is u10/v10 and not u01/v01 relabelled. Nothing
    # decodes east beyond one quantization step, which is what a cell whose
    # westward path is clamped at the grid edge reads as.
    forward = decode_png(client.get(flow_url()).content)
    inside = forward[..., 2] == 255
    assert inside.any()
    assert float(decoded_dx[inside].min()) < 0
    assert float(decoded_dx[inside].max()) <= scale / 255.0 + 1e-9


def test_an_artifact_without_a_backward_flow_is_a_404_for_it(monkeypatch, data_mode):
    # One honest rung down, named: the client then draws the construction the
    # forward field alone supports rather than inventing a backward field by
    # negating the forward one, which is the very assumption this texture exists
    # to stop the map from making.
    dataset = motion_dataset().drop_vars(["total_cloud_u10", "total_cloud_v10"])
    use_store(monkeypatch, data_mode, MotionStore(motion=dataset))
    response = client.get(flow_url(texture="backward"))
    assert response.status_code == 404
    assert "predates the stored backward flow" in response.json()["detail"]
    # The forward motion texture is unaffected.
    assert client.get(flow_url()).status_code == 200


def residual_dataset(shaping: float) -> xarray.Dataset:
    """The one-pair motion dataset plus a uniform development shaping."""
    dataset = motion_dataset()
    shape = (1,) + LAT2D.shape
    dataset["total_cloud_dev_shape"] = (("pair", "y", "x"), numpy.full(shape, shaping, dtype="float32"))
    return dataset


def test_the_development_shaping_is_served_signed_on_a_fixed_scale(monkeypatch, data_mode):
    # The re-timing is a signed scalar in [-1, 1], not a displacement, so it is
    # served on a FIXED scale of 1 rather than one fitted to the field: two
    # cycles must decode the same way, and a weak cycle must not be stretched
    # to look like a strong one.
    use_store(monkeypatch, data_mode, MotionStore(motion=residual_dataset(0.5)))
    response = client.get(flow_url(texture="residual"))
    assert response.status_code == 200
    headers = response.headers
    assert headers["x-weather-image-basis"] == "derived_motion"
    assert headers["x-weather-flow-texture"] == "residual"
    assert "vertical velocity" in headers["x-weather-render-semantics"]
    assert "not evidence" in headers["x-weather-render-semantics"]
    scale = float(headers["x-weather-flow-scale"])
    assert scale == 1.0
    rgba = decode_png(response.content)
    # Never on the alpha channel, where browser premultiplication would
    # destroy the precision of a value that is meant to pass through zero.
    assert int(rgba[..., 3].min()) == 255
    decoded = (rgba[..., 0].astype("float64") / 255.0 - 0.5) * 2.0 * scale
    inside = decode_png(client.get(flow_url()).content)[..., 2] == 255
    assert inside.any()
    assert float(numpy.abs(decoded[inside] - 0.5).max()) < 0.01
    # And the sign survives the round trip, which is the whole content of the
    # field: negative delivers the change later, positive earlier.
    use_store(monkeypatch, data_mode, MotionStore(motion=residual_dataset(-0.5)))
    negative = decode_png(client.get(flow_url(texture="residual")).content)
    decoded_negative = (negative[..., 0].astype("float64") / 255.0 - 0.5) * 2.0
    assert float(numpy.abs(decoded_negative[inside] + 0.5).max()) < 0.01


def test_an_artifact_without_a_development_shaping_is_a_404_for_it(monkeypatch, data_mode):
    # Only one method publishes this suffix, so every other artifact answers
    # 404 naming the absence and the client dissolves at a constant rate -
    # never on a shaping the browser made up, which would be a displayed value
    # nothing retrieved.
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    response = client.get(flow_url(texture="residual"))
    assert response.status_code == 404
    assert "development-residual" in response.json()["detail"]
    assert client.get(flow_url()).status_code == 200


def test_the_served_shader_names_the_construction_the_fields_are_for(monkeypatch, data_mode):
    # The client must not infer its construction from which textures happened
    # to load. The server's own registry answers, in a header.
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    assert client.get(flow_url()).headers["x-weather-flow-shader"] == grids.flow_shader_for(grids.DEFAULT_FLOW_METHOD)
    assert grids.flow_shader_for("intermediate-flow") == "intermediate"
    # An unregistered name never invents a branch; it falls back to the
    # construction every method's fields support.
    assert grids.flow_shader_for("no-such-method") == "hermite"


def visibility_motion_dataset(first: float, second: float, *, method_id: str = "visibility-blend") -> xarray.Dataset:
    """The one-pair dataset on a method axis carrying only ``method_id``.

    The visibility weights belong to one method, so they can only be asked for
    on that method's slice of the axis - which is the point of the refusal
    pinned below.
    """
    base = motion_dataset(visibility=(first, second))
    expanded = base.expand_dims({"method": [method_id]})
    expanded.attrs = dict(base.attrs)
    return expanded


def test_the_visibility_weights_are_served_as_two_channels_and_disclosed(monkeypatch, data_mode):
    # The per-frame fusion weights the visibility-blend construction needs.
    # R is frame 0's reliability and G is frame 1's; neither may ride the alpha
    # channel, where browser premultiplication would destroy precision near
    # zero, and the two must be distinguishable from each other.
    use_store(monkeypatch, data_mode, MotionStore(motion=visibility_motion_dataset(0.8, 0.2)))
    response = client.get(flow_url(texture="visibility", method="visibility-blend"))
    assert response.status_code == 200
    headers = response.headers
    assert headers["x-weather-image-basis"] == "derived_motion"
    assert headers["x-weather-flow-texture"] == "visibility"
    assert headers["x-weather-interpolation-method"] == "visibility-blend"
    assert headers["x-weather-flow-shader"] == "visibility"
    assert "per-pixel visibility weights" in headers["x-weather-render-semantics"]
    assert "not evidence" in headers["x-weather-render-semantics"]
    # A weight is unitless, so the declared scale is 1 rather than a
    # displacement the channels do not carry.
    assert float(headers["x-weather-flow-scale"]) == pytest.approx(1.0)
    rgba = decode_png(response.content)
    assert int(rgba[..., 3].min()) == 255
    inside = rgba[..., 0] > 0  # a stored cell answered here
    assert inside.any()
    assert int(rgba[..., 0][inside].max()) == pytest.approx(204, abs=1)  # 0.8
    assert int(rgba[..., 1][inside].max()) == pytest.approx(51, abs=1)  # 0.2
    # Outside the grid both channels are zero: an absent measurement the
    # client answers with the symmetric time weights, never a reliability of
    # zero that would make one retrieved frame vanish.
    outside = ~inside
    if outside.any():
        assert int(rgba[..., 1][outside].max()) == 0


def test_a_method_that_derives_no_visibility_weights_is_refused_them(monkeypatch, data_mode):
    # The derive pads a suffix no method declared with an explicit zero field,
    # so the variable exists on every method's slice. Serving it would draw a
    # method with fusion weights it never derived; the absence is named.
    use_store(monkeypatch, data_mode, MotionStore(motion=visibility_motion_dataset(0.8, 0.2, method_id="baseline")))
    response = client.get(flow_url(texture="visibility"))
    assert response.status_code == 404
    assert "derives no visibility weights" in response.json()["detail"]
    # Every other texture is unaffected for that method.
    assert client.get(flow_url()).status_code == 200


def test_an_artifact_without_visibility_weights_is_a_404_for_them(monkeypatch, data_mode):
    # One honest rung down, named: the client then fuses symmetrically, which
    # is the construction already approved, rather than inventing a
    # reliability of its own from the frames it holds.
    dataset = visibility_motion_dataset(0.8, 0.2).drop_vars(["total_cloud_vis0", "total_cloud_vis1"])
    use_store(monkeypatch, data_mode, MotionStore(motion=dataset))
    response = client.get(flow_url(texture="visibility", method="visibility-blend"))
    assert response.status_code == 404
    assert "predates the stored visibility weights" in response.json()["detail"]
    assert client.get(flow_url(method="visibility-blend")).status_code == 200


def test_the_visibility_method_names_its_own_shader(monkeypatch, data_mode):
    # The client must not infer the fusion from which textures happened to
    # load. The server's own registry answers.
    assert grids.flow_shader_for("visibility-blend") == "visibility"


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


def bench_motion_dataset(per_method: dict[str, float]) -> xarray.Dataset:
    """A motion dataset on the bench's method axis, one flow speed per method.

    The differing speed is what lets a test prove the endpoint served the
    method it was asked for rather than the first one it found.
    """
    times = frame_times()
    ids = list(per_method)
    shape = (len(ids), 1) + LAT2D.shape

    def stacked(values: list[float]) -> Any:
        return numpy.stack([numpy.full((1,) + LAT2D.shape, value, dtype="float32") for value in values])

    data_vars = {
        "total_cloud_u01": (("method", "pair", "y", "x"), stacked(list(per_method.values()))),
        "total_cloud_v01": (("method", "pair", "y", "x"), numpy.zeros(shape, dtype="float32")),
        "total_cloud_u10": (("method", "pair", "y", "x"), stacked([-value for value in per_method.values()])),
        "total_cloud_v10": (("method", "pair", "y", "x"), numpy.zeros(shape, dtype="float32")),
        "total_cloud_confidence": (("method", "pair", "y", "x"), numpy.ones(shape, dtype="float32")),
        "total_cloud_advect_weight": (("method", "pair", "y", "x"), numpy.ones(shape, dtype="float32")),
    }
    return xarray.Dataset(
        data_vars,
        coords={
            "pair_from": ("pair", numpy.array([times[0].replace(tzinfo=None)], dtype="datetime64[ns]")),
            "pair_to": ("pair", numpy.array([times[1].replace(tzinfo=None)], dtype="datetime64[ns]")),
            "method": ("method", numpy.array(ids, dtype="<U32")),
        },
        attrs={"method": "bench (test)", "derivation_version": "cloud-motion-bench-v4", "base_revision_id": "revision-eccc-hrdps-surface"},
    )


def two_method_registry(monkeypatch) -> None:
    """A registry with a second method, so selection can be tested at all.

    Only `baseline` is registered today; every other method arrives with its
    own change. Patching the catalogue keeps these tests about the selection
    machinery rather than about which methods happen to exist this week.
    """
    monkeypatch.setattr(grids, "flow_method_catalogue", lambda: [
        {"id": "baseline", "title": "Baseline", "summary": "", "shader": "hermite", "enabled": True, "generative": False},
        {"id": "other", "title": "Other", "summary": "", "shader": "linear", "enabled": True, "generative": False},
    ])


def test_the_default_method_matches_the_derivation_registry():
    # The API names its default without importing the ingest package at
    # import time; if the two ever drift, every default request silently
    # asks for a method the derivation does not publish.
    from ingest.derive.methods import DEFAULT_METHOD_ID

    assert grids.DEFAULT_FLOW_METHOD == DEFAULT_METHOD_ID


def test_each_method_serves_its_own_fields(monkeypatch, data_mode):
    # Two methods, two different flows. Asking for one must serve that one's
    # vectors and say so in the header - switching the menu is a selection
    # among published fields, never a recomputation and never a substitution.
    two_method_registry(monkeypatch)
    use_store(monkeypatch, data_mode, MotionStore(motion=bench_motion_dataset({"baseline": 1.0, "other": 4.0})))
    first = client.get(flow_url())
    second = client.get(flow_url(method="other"))
    assert first.status_code == 200 and second.status_code == 200
    assert first.headers["X-Weather-Interpolation-Method"] == "baseline"
    assert second.headers["X-Weather-Interpolation-Method"] == "other"
    # A larger declared scale means a larger stored displacement was read:
    # a different field, not the same one relabelled. (The two scales are not
    # in the fields' 1:4 ratio because the larger flow runs off the edge of
    # this small test grid and is clamped there, which is the honest
    # behaviour at a grid boundary.)
    assert float(second.headers["X-Weather-Flow-Scale"]) > float(first.headers["X-Weather-Flow-Scale"])


def test_a_method_the_artifact_does_not_carry_is_a_404(monkeypatch, data_mode):
    # The disclosed crossfade rung, named. Serving another method's fields
    # under the requested method's name would be the one thing the governing
    # rule does not tolerate.
    two_method_registry(monkeypatch)
    use_store(monkeypatch, data_mode, MotionStore(motion=bench_motion_dataset({"baseline": 1.0})))
    known_but_absent = client.get(flow_url(method="other"))
    assert known_but_absent.status_code == 404
    assert "carries no 'other' method" in known_but_absent.json()["detail"]
    # A method no registry knows is refused outright rather than guessed at.
    unknown = client.get(flow_url(method="invented-by-the-caller"))
    assert unknown.status_code == 422
    assert "invented-by-the-caller" in unknown.json()["detail"]


def test_an_artifact_without_a_method_axis_still_serves_the_baseline(monkeypatch, data_mode):
    # Artifacts derived before the bench have no method dimension. They are
    # read as the single method they were, rather than 404ing a map that
    # worked yesterday.
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset(advect_weight=0.5)))
    response = client.get(flow_url())
    assert response.status_code == 200
    assert response.headers["X-Weather-Interpolation-Method"] == grids.DEFAULT_FLOW_METHOD


def test_the_methods_endpoint_reports_the_bench_and_its_scores(monkeypatch, data_mode):
    row = motion_artifact()
    scored = CurrentArtifact(**{**row.__dict__, "provenance": {
        **row.provenance,
        "derivation_version": "cloud-motion-bench-v4",
        "quality": {"status": "derived", "per_variable": {"total_cloud": {
            "per_method": {"baseline": {
                "advect_weight_median": 0.44,
                "leave_one_out": {
                    "held_out_frames": 3,
                    "improvement_over_reversed_flow": 0.114,
                    "improvement_over_crossfade": 0.09,
                    "midpoint_mae_percent": 12.5,
                    "midpoint_ssim": 0.81,
                },
            }},
        }}},
    }})
    use_store(monkeypatch, data_mode, MotionStore(motion=bench_motion_dataset({"baseline": 1.0}), motion_row=scored))
    payload = client.get(f"{PREFIX}/methods").json()
    assert payload["operational"] is False
    assert payload["default_method"] == grids.DEFAULT_FLOW_METHOD
    baseline = next(item for item in payload["methods"] if item["id"] == grids.DEFAULT_FLOW_METHOD)
    assert baseline["published"] is True
    assert baseline["generative"] is False
    score = baseline["scores"][0]
    assert score["layer_id"] == "eccc-hrdps-surface-total-cloud"
    assert score["improvement_over_reversed_flow"] == pytest.approx(0.114)
    assert score["midpoint_ssim"] == pytest.approx(0.81)


def test_a_method_with_no_measurement_reports_no_score_rather_than_a_zero(monkeypatch, data_mode):
    # An unmeasured method and a measured-and-beaten one are different facts.
    use_store(monkeypatch, data_mode, MotionStore(motion=bench_motion_dataset({"baseline": 1.0})))
    payload = client.get(f"{PREFIX}/methods").json()
    baseline = next(item for item in payload["methods"] if item["id"] == grids.DEFAULT_FLOW_METHOD)
    assert baseline["scores"] == []


def test_the_motion_artifact_is_not_listed_as_a_layer(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, MotionStore(motion=motion_dataset()))
    payload = client.get(f"{PREFIX}/layers").json()
    ids = {layer["id"] for layer in payload["layers"]}
    assert not any("cloud-motion" in identifier or "cloud_motion" in identifier for identifier in ids)
