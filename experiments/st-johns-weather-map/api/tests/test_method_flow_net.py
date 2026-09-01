"""The `flow-net` bench method: a learned estimator, everything else baseline.

What is pinned here: the method is registered and DISABLED (it measured a net
regression across the live layer set); it emits a displacement field only and
is therefore not `generative`; it reuses the baseline's composite object
itself, so the controlled comparison cannot silently become two changes at
once; it is endpoint-exact; and when the optional runtime or graph is absent
it falls back to DIS, says so in provenance, and reproduces the baseline's
fields EXACTLY - which is what makes the duplicated `motion` body checkable
rather than hoped for.
"""

from __future__ import annotations

import numpy
import pytest

pytest.importorskip("cv2")

from ingest.derive.methods import (
    BaselineMethod,
    MethodContext,
    method_by_id,
)
from ingest.derive.methods.flow_net import (
    FLOW_NET_MODEL_ENV,
    FlowNetMethod,
)


def blob_field(rows: int = 96, cols: int = 96, *, centre=(48, 48), sigma: float = 9.0) -> numpy.ndarray:
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    distance2 = (row_index - centre[0]) ** 2 + (col_index - centre[1]) ** 2
    return 100.0 * numpy.exp(-distance2 / (2 * sigma**2))


def moving_frames(count: int = 4) -> list[numpy.ndarray]:
    """A translating blob - a sequence both estimators should agree about."""
    return [blob_field(centre=(40 + 2 * step, 36 + 3 * step)) for step in range(count)]


@pytest.fixture
def no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployed reality: the optional graph is not configured."""
    monkeypatch.delenv(FLOW_NET_MODEL_ENV, raising=False)


def context_for(frames: list[numpy.ndarray]) -> MethodContext:
    return MethodContext(
        variable="total_cloud",
        frames=frames,
        indices=tuple(range(len(frames))),
        interval_seconds=3600.0,
    )


def test_flow_net_is_registered_disabled_and_is_not_generative():
    method = method_by_id("flow-net")
    assert method is not None
    # Disabled on measurement, not on principle: it wins on one live layer of
    # six. Registered anyway so the measurement stays reproducible.
    assert method.enabled is False
    # A displacement field is not synthesised content. The reserved carve-out
    # flag stays off, and this method may not be the thing that turns it on.
    assert method.generative is False
    # It draws with the shipped shader, because only the estimator changed.
    assert method.shader == BaselineMethod.shader


def test_flow_net_reuses_the_baseline_composite_object():
    # Not "produces the same numbers" - the SAME function. If a later edit
    # gives this method its own composite, the estimator is no longer the only
    # variable under test and this test is the thing that notices.
    assert FlowNetMethod.composite is BaselineMethod.composite


def test_flow_net_is_endpoint_exact(no_model):
    frames = moving_frames(2)
    method = FlowNetMethod()
    motion = method.motion(context_for(frames))[0]
    previous, following = frames[0], frames[1]
    assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
    assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)
    # And nothing in between is either endpoint, or the method is not moving.
    middle = method.composite(previous, following, motion, 0.5)
    assert not numpy.array_equal(middle, previous)
    assert not numpy.array_equal(middle, following)


def test_a_missing_model_falls_back_to_dis_and_says_so(no_model):
    # The governing constraint on this method: an optional dependency may
    # never fail the motion artifact the whole map depends on.
    method = FlowNetMethod()
    motions = method.motion(context_for(moving_frames(3)))
    assert len(motions) == 2
    assert all(motion.diagnostics["flow_net_fell_back"] == 1.0 for motion in motions)
    assert numpy.isfinite(motions[0].flow01).all()


def test_a_broken_model_path_falls_back_rather_than_raising(monkeypatch, tmp_path):
    # A file that exists and is not a graph is the nastier case: it gets past
    # the existence check and must still be an absent estimator, not a crash.
    broken = tmp_path / "not-a-graph.onnx"
    broken.write_bytes(b"this is not an onnx graph")
    monkeypatch.setenv(FLOW_NET_MODEL_ENV, str(broken))
    method = FlowNetMethod()
    motions = method.motion(context_for(moving_frames(2)))
    assert motions[0].diagnostics["flow_net_fell_back"] == 1.0


def test_flow_net_matches_baseline_when_it_falls_back(no_model):
    """The fallback path must BE the baseline, field for field.

    `FlowNetMethod.motion` duplicates the baseline's body because the baseline
    is not this change's to edit. That duplication is only safe if it is
    pinned, so this compares every published field bit for bit; a future edit
    to either derivation breaks it loudly.
    """
    frames = moving_frames(4)
    context = context_for(frames)
    baseline = BaselineMethod(use_prior=False).motion(context)
    fell_back = FlowNetMethod(use_prior=False).motion(context)
    assert len(baseline) == len(fell_back)
    for first, second in zip(baseline, fell_back):
        for name in ("flow01", "flow10", "confidence", "support", "advect_weight"):
            numpy.testing.assert_array_equal(getattr(first, name), getattr(second, name))


def test_the_estimator_returns_grid_cells_not_network_pixels():
    """A recovered translation must be in the source grid's own units.

    The graph runs at a fixed 360x480 whatever the field's size, so its flow
    is in network pixels; forgetting to rescale it back is a silent factor-of-
    three error that still looks like a plausible motion field. Skipped
    entirely unless the optional runtime and a graph are actually present.
    """
    import os

    pytest.importorskip("onnxruntime")
    path = os.environ.get(FLOW_NET_MODEL_ENV, "")
    if not path or not os.path.exists(path):
        pytest.skip(f"no flow-net graph at {FLOW_NET_MODEL_ENV}")
    previous = blob_field()
    following = numpy.roll(numpy.roll(previous, 4, axis=0), 7, axis=1)  # +4 rows, +7 cols
    method = FlowNetMethod()
    flow = method._estimate(previous, following)
    assert method.fell_back is False
    assert flow.shape == previous.shape + (2,)
    assert float(numpy.median(flow[..., 0])) == pytest.approx(7.0, abs=1.0)
    assert float(numpy.median(flow[..., 1])) == pytest.approx(4.0, abs=1.0)
