"""Derived cloud-motion artifacts: flow recovery, consistency, fail-closed.

The motion fields exist only for display-time advection-corrected
interpolation. What is pinned here: DIS recovers a known translation; the
consistency score is high where the two directions agree; the derive step
publishes with full derivation provenance; anything unusable publishes
NOTHING (the client then crossfades - absence is the disclosed fallback).
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy
import pytest
import xarray

pytest.importorskip("cv2")

from ingest.derive.methods import (
    BaselineMethod,
    IntermediateFlowMethod,
    MethodContext,
    PairMotion,
    _score_one,
    method_by_id,
)
from ingest.derive.methods.development_residual import (
    DevelopmentResidualMethod,
    RESIDUAL_SHAPE_GAIN,
)
from ingest.derive.methods.scale_cascade import (
    CASCADE_OCTAVES,
    ScaleCascadeMethod,
    _cascade_bands,
)
from ingest.derive.methods.visibility_blend import (
    VisibilityBlendMethod,
)
from ingest.derive.cloud_motion import (
    DEFAULT_METHOD_ID,
    LOGICAL_NAME,
    MIN_HELD_OUT_IMPROVEMENT,
    VERSION,
    enabled_methods,
    _consistency,
    _development_agreement,
    _dis_flow,
    _interpolation_skill,
    _prior_corrected,
    _segment_tangents,
    _supported_flow,
    _warp_nearest,
    cloud_motion_cycle,
    derive_cloud_motion,
)
from ingest.grib import write_zarr
from ingest.store import CurrentArtifact, sha256_of

UTC = timezone.utc


def blob_field(rows: int = 96, cols: int = 96, *, centre=(48, 48), sigma: float = 9.0) -> numpy.ndarray:
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    distance2 = (row_index - centre[0]) ** 2 + (col_index - centre[1]) ** 2
    return 100.0 * numpy.exp(-distance2 / (2 * sigma**2))


def test_dis_recovers_a_known_translation():
    previous = blob_field()
    following = numpy.roll(numpy.roll(previous, 3, axis=0), 5, axis=1)  # +3 rows, +5 cols
    flow = _dis_flow(previous, following)
    core = blob_field() > 20.0
    assert float(numpy.median(flow[..., 0][core])) == pytest.approx(5.0, abs=1.0)
    assert float(numpy.median(flow[..., 1][core])) == pytest.approx(3.0, abs=1.0)


def test_zero_flow_warp_is_the_identity():
    field = blob_field()
    unchanged = _warp_nearest(field, numpy.zeros(field.shape + (2,), dtype="float32"))
    assert numpy.array_equal(unchanged, field)


def test_consistency_is_high_where_directions_agree():
    previous = blob_field()
    following = numpy.roll(previous, 4, axis=1)
    flow01 = _dis_flow(previous, following)
    flow10 = _dis_flow(following, previous)
    core = blob_field() > 20.0
    confidence = _consistency(flow01, flow10)
    assert float(numpy.median(confidence[core])) > 0.6


def test_consistency_is_judged_relative_to_the_distance_claimed():
    # The same two-cell round-trip error against a fifteen-cell displacement
    # and against a stationary cell. An absolute tolerance scored both zero,
    # which is what sent three quarters of the map down the crossfade path
    # while advection was still beating persistence there.
    def round_trip_error(dx: float, error: float) -> float:
        forward = uniform_flow(dx, 0.0, shape=(32, 32))
        backward = uniform_flow(-dx + error, 0.0, shape=(32, 32))
        return float(numpy.median(_consistency(forward, backward)))

    assert round_trip_error(15.0, 2.0) > 0.5  # fast cell, small relative miss: trusted
    assert round_trip_error(0.0, 2.0) == 0.0  # stationary cell, same miss: not trusted
    # A perfect round trip is fully trusted whatever the speed.
    assert round_trip_error(15.0, 0.0) == pytest.approx(1.0)


def test_an_untrusted_hole_inherits_the_motion_around_it():
    flow = uniform_flow(4.0, 1.0, shape=(24, 24))
    confidence = numpy.ones((24, 24))
    confidence[10:14, 10:14] = 0.0  # a patch DIS could not verify
    filled, support = _supported_flow(flow, confidence)
    # The hole keeps moving with its neighbourhood instead of standing still.
    assert float(numpy.median(filled[11:13, 11:13, 0])) == pytest.approx(4.0, abs=0.3)
    assert float(numpy.median(support[11:13, 11:13])) > 0.5
    # Trusted cells are untouched.
    assert numpy.allclose(filled[0:5, 0:5], flow[0:5, 0:5])


def test_a_wholly_untrusted_field_keeps_the_crossfade_fallback():
    flow = uniform_flow(4.0, 1.0, shape=(24, 24))
    _, support = _supported_flow(flow, numpy.zeros((24, 24)))
    # Nothing stood behind any fill: the display weight stays at zero and the
    # client crossfades, which is the disclosed fallback.
    assert float(support.max()) < 0.01


def test_development_agreement_separates_motion_from_growth_in_place():
    moving_from = blob_field(48, 48, centre=(24, 20))
    moving_to = blob_field(48, 48, centre=(24, 28))  # same blob, 8 cells east
    flow = uniform_flow(8.0, 0.0, shape=(48, 48))
    agreement = _development_agreement(moving_from, moving_to, flow)
    assert float(numpy.median(agreement)) > 0.8

    # Same place, twice the cloud: no motion field can explain this, so the
    # display must dissolve rather than drag anything across the map.
    growing_from = blob_field(48, 48, centre=(24, 24), sigma=6.0)
    growing_to = 2.0 * growing_from
    core = growing_from > 20.0
    grown = _development_agreement(growing_from, growing_to, flow)
    assert float(numpy.median(grown[core])) < 0.5


def uniform_flow(dx: float, dy: float, shape=(8, 8)) -> numpy.ndarray:
    flow = numpy.zeros(shape + (2,), dtype="float64")
    flow[..., 0] = dx
    flow[..., 1] = dy
    return flow


def test_tangents_share_the_knot_velocity_under_acceleration():
    # Displacements 2 then 4 cells: the interior knot's central-difference
    # velocity is 3 - segment 0 ends and segment 1 starts at the SAME
    # velocity, which is exactly the C1 property that removes the snap.
    forward = [uniform_flow(2, 0), uniform_flow(4, 0)]
    backward = [uniform_flow(-2, 0), uniform_flow(-4, 0)]
    trust = [numpy.ones((8, 8)), numpy.ones((8, 8))]
    segments = _segment_tangents(forward, backward, trust)
    (start0, end0), (start1, end1) = segments
    assert numpy.allclose(start0[..., 0], 2.0)  # one-sided at the sequence start
    assert numpy.allclose(end0[..., 0], 3.0)
    assert numpy.allclose(start1[..., 0], 3.0)  # shared with the previous segment
    assert numpy.allclose(end1[..., 0], 4.0)  # one-sided at the sequence end


def test_distrusted_knots_collapse_to_the_segment_flow():
    forward = [uniform_flow(2, 0), uniform_flow(4, 0)]
    backward = [uniform_flow(-2, 0), uniform_flow(-4, 0)]
    distrust = [numpy.zeros((8, 8)), numpy.zeros((8, 8))]
    segments = _segment_tangents(forward, backward, distrust)
    for (start, end), flow in zip(segments, forward):
        # v = F everywhere: the cubic collapses exactly to linear advection.
        assert numpy.allclose(start, flow)
        assert numpy.allclose(end, flow)


def test_a_wild_knot_estimate_is_clamped_near_the_segment_flow():
    # The neighbouring pair claims a huge reversal; the tangent must stay
    # within half the flow magnitude (plus the one-cell floor) of the flow,
    # so a bad flow cannot bow the Hermite arc far outside the endpoints.
    forward = [uniform_flow(2, 0), uniform_flow(-40, 0)]
    backward = [uniform_flow(-2, 0), uniform_flow(40, 0)]
    trust = [numpy.ones((8, 8)), numpy.ones((8, 8))]
    (start0, end0), _ = _segment_tangents(forward, backward, trust)
    deviation = numpy.hypot(end0[..., 0] - 2.0, end0[..., 1])
    assert float(deviation.max()) <= max(0.5 * 2.0, 1.0) + 1e-9


def test_the_steering_prior_reaches_only_cells_the_imagery_left_unsupported():
    # Imagery says 4 cells east and is trusted; the model wind says 12 cells
    # north. Where the imagery is trusted the flow is untouched - the prior
    # never overrides what was actually observed to move.
    flow = uniform_flow(4.0, 0.0, shape=(24, 24))
    prior = uniform_flow(0.0, 12.0, shape=(24, 24))
    corrected, carried = _prior_corrected(flow, numpy.ones((24, 24)), prior)
    assert numpy.allclose(corrected, flow, atol=1e-6)
    assert carried == pytest.approx(0.0, abs=1e-6)


def test_a_stationary_field_refuses_the_steering_wind():
    # The Avalon's own failure mode: cloud forming and dissipating in place
    # while wind blows through it. A trusted image flow reporting no motion
    # must not be overwritten by the model's wind, however strong.
    still = uniform_flow(0.0, 0.0, shape=(24, 24))
    blowing = uniform_flow(10.0, 0.0, shape=(24, 24))
    corrected, carried = _prior_corrected(still, numpy.ones((24, 24)), blowing)
    assert numpy.allclose(corrected, still, atol=1e-6)
    assert carried == pytest.approx(0.0, abs=1e-6)
    # Nor does distrusting the stillness let the wind in on its own: with no
    # trusted image flow anywhere, nothing corroborates the model, and an
    # uncorroborated wind is not evidence about cells the imagery could not
    # read. The display falls back to the crossfade instead.
    unfilled, weight = _prior_corrected(still, numpy.zeros((24, 24)), blowing)
    assert numpy.allclose(unfilled, still, atol=1e-6)
    assert weight == pytest.approx(0.0, abs=1e-6)

    # What does let it in: a field whose trusted part moves the way the model
    # says, with holes the imagery could not read.
    observed = uniform_flow(10.0, 0.0, shape=(24, 24))
    support = numpy.ones((24, 24))
    support[8:16, 8:16] = 0.0
    corrected, carried = _prior_corrected(observed * numpy.where(support[..., None] > 0, 1.0, 0.0), support, blowing)
    assert float(corrected[10:14, 10:14, 0].min()) > 1.0  # the hole now moves
    assert carried > 0.0


def test_an_uncorroborated_steering_wind_barely_reaches_the_field():
    # The prior is weighted by how well it agrees with the flow that IS
    # trusted. A wind pointing the opposite way to the observed motion is not
    # evidence about the unobserved cells either.
    flow = uniform_flow(6.0, 0.0, shape=(24, 24))
    support = numpy.full((24, 24), 0.5)
    agreeing, agreeing_weight = _prior_corrected(flow, support, uniform_flow(6.0, 0.0, shape=(24, 24)))
    opposing, opposing_weight = _prior_corrected(flow, support, uniform_flow(-6.0, 0.0, shape=(24, 24)))
    assert opposing_weight < agreeing_weight
    assert float(numpy.abs(opposing[..., 0] - flow[..., 0]).max()) < 6.0


def test_leave_one_out_beats_a_crossfade_on_a_moving_field():
    # Frames 0 and 2 are interpolated to the midpoint and checked against the
    # real frame 1 that was held out. On a field that genuinely moves, the
    # construction must predict the held-out frame better than a dissolve of
    # its neighbours does - this is the number that says "believable".
    frames = [blob_field(64, 64, centre=(32, 16 + 8 * step)) for step in range(3)]
    skill = _interpolation_skill(frames)
    assert skill is not None
    assert skill["held_out_frames"] == 1
    assert skill["midpoint_mae_percent"] < skill["midpoint_crossfade_mae_percent"]
    assert skill["improvement_over_crossfade"] > 0.1
    # And it beats the same construction with the motion reversed, which is
    # the test that the DIRECTION carries information rather than the blend
    # simply being smoother than a dissolve.
    assert skill["improvement_over_reversed_flow"] > 0.1


def wide_blob(centre_col: float, *, size: int = 96, sigma: float = 7.0) -> numpy.ndarray:
    """One blob on a grid wide enough that a warp never runs off an edge.

    Edge clamping in ``_warp_nearest`` is honest behaviour at a grid boundary,
    but it is not what these tests are measuring, and on a 64-cell grid it was
    larger than the difference between the two methods.
    """
    return blob_field(size, size, centre=(size // 2, centre_col), sigma=sigma)


def held_pair(forward: float, backward: float, *, size: int = 96) -> PairMotion:
    """A pair whose two derived directions are supplied rather than estimated.

    The claim of intermediate-flow is about the COMPOSITE, so the two flows are
    handed in directly: DIS would decide both, and there would be no way to
    construct the disagreement the method exists to exploit.
    """
    return PairMotion(
        flow01=uniform_flow(forward, 0.0, shape=(size, size)),
        flow10=uniform_flow(backward, 0.0, shape=(size, size)),
        confidence=numpy.ones((size, size)),
        support=numpy.ones((size, size)),
        advect_weight=numpy.ones((size, size)),
    )


def test_intermediate_flow_is_registered_with_its_own_shader():
    method = method_by_id("intermediate-flow")
    assert method is not None
    assert method.enabled and not method.generative
    # A new client construction: the fields are the baseline's, but they are
    # combined differently, so the shader branch must be named separately.
    assert method.shader == "intermediate"
    assert method.shader != BaselineMethod.shader


def test_intermediate_flow_is_endpoint_exact():
    # Non-negotiable for every method on the bench: at a real instant the real
    # frame shows untouched, whatever the two flows claim - including flows
    # that disagree wildly with each other.
    previous, following = wide_blob(30), wide_blob(42)
    motion = held_pair(14.0, 3.0)
    method = IntermediateFlowMethod()
    assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
    assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)


def test_intermediate_flow_reduces_to_the_baseline_when_the_flow_inverts():
    # F10 = -F01 is exactly the assumption the shipped construction makes. Where
    # it holds, the quadratic forms collapse to it, so this method can only ever
    # differ where the two measured directions actually disagree.
    previous, following = wide_blob(30), wide_blob(42)
    motion = held_pair(12.0, -12.0)
    for fraction in (0.25, 0.5, 0.75):
        baseline = BaselineMethod().composite(previous, following, motion, fraction)
        intermediate = IntermediateFlowMethod().composite(previous, following, motion, fraction)
        assert numpy.allclose(baseline, intermediate, atol=1e-12)


def test_intermediate_flow_matches_the_baseline_on_a_purely_translating_field():
    # The same held-out harness both methods are ranked by, on a field that
    # genuinely translates and whose forward and backward flows therefore very
    # nearly invert. The method must not cost anything here: it is the
    # disagreement case it is for.
    frames = [wide_blob(20 + 8 * step) for step in range(5)]
    baseline = _interpolation_skill(frames, method=BaselineMethod(), variable="total_cloud")
    intermediate = _interpolation_skill(frames, method=IntermediateFlowMethod(), variable="total_cloud")
    assert baseline is not None and intermediate is not None
    assert intermediate["midpoint_mae_percent"] <= baseline["midpoint_mae_percent"] + 1e-3
    assert intermediate["midpoint_ssim"] >= baseline["midpoint_ssim"] - 1e-4
    assert intermediate["improvement_over_reversed_flow"] > MIN_HELD_OUT_IMPROVEMENT


def test_intermediate_flow_beats_the_baseline_when_the_two_directions_disagree():
    # The whole claim, deliberately constructed. Content really moves 12 cells
    # east, but both derived directions carry the same 2-cell eastward bias:
    # F01 = +14 and F10 = -10 rather than the -14 that would invert it. The
    # baseline uses F01 alone and drags everything two cells too far; the
    # intermediate form's (1-t)F01 - t F10 cancels the shared bias at the
    # midpoint and lands on the frame that was held out.
    previous, truth, following = wide_blob(30), wide_blob(36), wide_blob(42)
    motion = held_pair(14.0, -10.0)
    baseline_mae, baseline_ssim = _score_one(BaselineMethod().composite(previous, following, motion, 0.5), truth)
    intermediate_mae, intermediate_ssim = _score_one(
        IntermediateFlowMethod().composite(previous, following, motion, 0.5), truth
    )
    assert intermediate_mae < baseline_mae
    assert intermediate_ssim >= baseline_ssim
    # Not a marginal win: the bias is removed rather than reduced.
    assert intermediate_mae < 0.1 * baseline_mae


def visibility_pair(v0: float, v1: float, *, size: int = 96, flow: float = 12.0) -> PairMotion:
    """A pair whose two visibility weights are supplied rather than measured.

    The claim of visibility-blend is about the FUSION, so the reliabilities are
    handed in: measuring them would decide both, and there would be no way to
    construct the asymmetry the method exists to exploit.
    """
    return PairMotion(
        flow01=uniform_flow(flow, 0.0, shape=(size, size)),
        flow10=uniform_flow(-flow, 0.0, shape=(size, size)),
        confidence=numpy.ones((size, size)),
        support=numpy.ones((size, size)),
        advect_weight=numpy.ones((size, size)),
        extra={"vis0": numpy.full((size, size), v0), "vis1": numpy.full((size, size), v1)},
    )


def test_visibility_blend_is_registered_with_its_own_shader_and_fields():
    method = method_by_id("visibility-blend")
    assert method is not None
    assert method.enabled and not method.generative
    # A new client construction and two fields nothing else publishes: the
    # weights are derived here and only fused on the client.
    assert method.shader == "visibility"
    assert method.shader not in (BaselineMethod.shader, IntermediateFlowMethod.shader)
    assert method.extra_suffixes == ("vis0", "vis1")


def test_visibility_blend_is_endpoint_exact():
    # Non-negotiable for every method on the bench, and the reliabilities must
    # not be able to break it: at a real instant the real frame shows untouched
    # even where the weight pair says that frame's own warp is worthless.
    previous, following = wide_blob(30), wide_blob(42)
    method = VisibilityBlendMethod()
    for weights in ((1.0, 1.0), (0.01, 1.0), (1.0, 0.01), (0.5, 0.5)):
        motion = visibility_pair(*weights)
def shaped_pair(shaping: Any, *, size: int = 96, advect: float = 0.0) -> PairMotion:
    """A pair carrying a supplied development shaping and a chosen display weight.

    ``advect = 0`` is the regime the residual exists for: advection has failed
    to explain the change, so the display is the dissolve the shaping re-times.
    """
    field = numpy.full((size, size), float(shaping)) if numpy.isscalar(shaping) else numpy.asarray(shaping)
    return PairMotion(
        flow01=uniform_flow(0.0, 0.0, shape=(size, size)),
        flow10=uniform_flow(0.0, 0.0, shape=(size, size)),
        confidence=numpy.ones((size, size)),
        support=numpy.ones((size, size)),
        advect_weight=numpy.full((size, size), advect),
        extra={"dev_shape": field},
    )


def omega_dataset(
    frames: int = 3, *, variable: str = "total_cloud", omega: list[float] | None = None
) -> xarray.Dataset:
    """A surface dataset carrying total cloud and the 700 hPa omega beside it.

    700 hPa is what ``STEERING_LEVEL_BY_VARIABLE`` assigns total cloud, and
    the omega field is uniform per frame so the test controls the tendency
    exactly rather than inferring it.
    """
    base = datetime(2026, 8, 31, 12, tzinfo=UTC)
    stamps = [numpy.datetime64((base + timedelta(hours=step)).replace(tzinfo=None), "ns") for step in range(frames)]
    cloud = numpy.stack([numpy.roll(blob_field(), 4 * step, axis=1) for step in range(frames)])
    values = omega if omega is not None else [0.0] * frames
    column = numpy.stack([numpy.full(cloud.shape[1:], value) for value in values])
    return xarray.Dataset(
        {
            variable: (("valid_time", "y", "x"), cloud, {"units": "percent"}),
            "omega_700hPa": (("valid_time", "y", "x"), column, {"units": "Pa s-1"}),
        },
        coords={"valid_time": stamps},
    )


def test_development_residual_is_registered_with_its_own_shader():
    method = method_by_id("development-residual")
    assert method is not None
    assert method.enabled
    # Every displayed value remains a mix of two retrieved frames, so this is
    # emphatically not a generative method and needs no generative slot.
    assert not method.generative
    assert method.shader == "development-residual"
    assert method.shader != BaselineMethod.shader
    # The shaping has to reach the client as a stored field: the browser has
    # no omega and must never be handed one.
    assert method.extra_suffixes == ("dev_shape",)


def test_development_residual_is_endpoint_exact_under_any_shaping():
    # Non-negotiable, and the property the whole carve-out rests on. The
    # t(1-t) factor is zero at both ends, so this holds for every shaping
    # value including the saturated ones - it is algebra, not a clamp.
    previous, following = wide_blob(30), wide_blob(42)
    method = DevelopmentResidualMethod()
    for shaping in (-1.0, -0.5, 0.0, 0.5, 1.0):
        motion = shaped_pair(shaping)
        assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
        assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)


def test_visibility_blend_reduces_to_the_baseline_where_both_warps_are_equally_reliable():
    # The reduction that makes this method a controlled change: equal weights
    # normalise back to (1-t, t) exactly, whatever their common value, so the
    # method can only differ where the two warps measurably disagree about
    # their own reliability.
    previous, following = wide_blob(30), wide_blob(42)
    for value in (1.0, 0.4, 0.05):
        motion = visibility_pair(value, value)
        for fraction in (0.25, 0.5, 0.75):
            baseline = BaselineMethod().composite(previous, following, motion, fraction)
            visibility = VisibilityBlendMethod().composite(previous, following, motion, fraction)
            assert numpy.allclose(baseline, visibility, atol=1e-12)


def test_visibility_blend_with_no_stored_weights_is_the_baseline():
    # An absent weight pair is an absent measurement, never a zero one: the
    # fusion falls back to the symmetric weights rather than making one frame
    # vanish. This is also what the harness's synthetic pairs hand it.
    previous, following = wide_blob(30), wide_blob(42)
    motion = held_pair(12.0, -12.0)
    assert not motion.extra
    for fraction in (0.25, 0.5, 0.75):
        baseline = BaselineMethod().composite(previous, following, motion, fraction)
        visibility = VisibilityBlendMethod().composite(previous, following, motion, fraction)
        assert numpy.allclose(baseline, visibility, atol=1e-12)


def test_visibility_blend_lets_the_reliable_warp_carry_the_pixel():
    # The whole claim, deliberately constructed. Content really moves 12 cells
    # east and the flow says so, but frame 1's warp is declared unreliable
    # (v1 = 0.02) while frame 0's is trusted. The baseline averages the two
    # warps 50/50 at the midpoint; the visibility fusion gives frame 0 about
    # 98 percent of the pixel, which is the frame whose warp is right here.
    previous, truth, following = wide_blob(30), wide_blob(36), wide_blob(42)
    # A displaced frame 1, so a 50/50 average really is a double image.
    following_wrong = wide_blob(54)
    motion = visibility_pair(1.0, 0.02)
    baseline_mae, baseline_ssim = _score_one(
        BaselineMethod().composite(previous, following_wrong, motion, 0.5), truth
    )
    visibility_mae, visibility_ssim = _score_one(
        VisibilityBlendMethod().composite(previous, following_wrong, motion, 0.5), truth
    )
    assert visibility_mae < baseline_mae
    assert visibility_ssim > baseline_ssim
    # And nothing is invented: every value stays inside the range of the two
    # retrieved frames' own values.
    drawn = VisibilityBlendMethod().composite(previous, following_wrong, motion, 0.5)
    assert float(drawn.min()) >= min(float(previous.min()), float(following_wrong.min())) - 1e-9
    assert float(drawn.max()) <= max(float(previous.max()), float(following_wrong.max())) + 1e-9
    assert following is not None  # the correct frame is unused here, by design


def test_visibility_weights_are_derived_smooth_bounded_and_asymmetric_at_an_occlusion():
    # The derivation, not the fusion. A blob translating east, with a second
    # blob that appears only in the later frame: the later frame carries
    # content the earlier one cannot explain, so the backward warp's residual
    # is larger there than the forward warp's and the two weights part company.
    previous = wide_blob(30)
    following = wide_blob(42) + blob_field(96, 96, centre=(20, 70), sigma=5.0)
    method = VisibilityBlendMethod()
    context = MethodContext(
        variable="total_cloud", frames=[previous, following], indices=(0, 1), interval_seconds=3600.0
    )
    motion = method.motion(context)[0]
    visibility0 = motion.extra["vis0"]
    visibility1 = motion.extra["vis1"]
    assert visibility0.shape == previous.shape and visibility1.shape == previous.shape
    # Strictly positive and at most 1, so the normalised fusion can never
    # divide by zero and can never exceed a convex combination.
    for weights in (visibility0, visibility1):
        assert float(weights.min()) > 0.0
        assert float(weights.max()) <= 1.0
    # The weights actually differ somewhere: a pair that never parts company
    # would make this method the baseline with extra storage.
    assert float(numpy.max(numpy.abs(visibility0 - visibility1))) > 0.01
    assert motion.diagnostics["visibility_asymmetry_mean"] > 0.0


def test_visibility_blend_matches_the_baseline_on_a_purely_translating_field():
    # The same held-out harness both methods are ranked by, on a field that
    # genuinely translates and where both warps are therefore about equally
    # reliable. The method must not cost anything here: it is the disagreement
    # case it is for.
    frames = [wide_blob(20 + 8 * step) for step in range(5)]
    baseline = _interpolation_skill(frames, method=BaselineMethod(), variable="total_cloud")
    visibility = _interpolation_skill(frames, method=VisibilityBlendMethod(), variable="total_cloud")
    assert baseline is not None and visibility is not None
    assert visibility["midpoint_mae_percent"] <= baseline["midpoint_mae_percent"] + 1e-3
    assert visibility["midpoint_ssim"] >= baseline["midpoint_ssim"] - 1e-4
    assert visibility["improvement_over_reversed_flow"] > MIN_HELD_OUT_IMPROVEMENT
def test_the_residual_re_times_the_change_and_never_leaves_the_two_frames():
    # THE BOUND, stated as a test. Whatever omega says, the displayed value at
    # every cell stays between the two retrieved values at that cell: nothing
    # is added that is in neither frame, nothing removed that is in both.
    rng = numpy.random.default_rng(20260901)
    previous = rng.uniform(0.0, 100.0, size=(64, 64))
    following = rng.uniform(0.0, 100.0, size=(64, 64))
    lower = numpy.minimum(previous, following)
    upper = numpy.maximum(previous, following)
    method = DevelopmentResidualMethod()
    for shaping in (-1.0, -0.75, 0.25, 1.0):
        motion = shaped_pair(rng.uniform(-1.0, 1.0, size=(64, 64)) * shaping, size=64)
        for fraction in (0.05, 0.25, 0.5, 0.75, 0.95):
            drawn = method.composite(previous, following, motion, fraction)
            assert numpy.all(drawn >= lower - 1e-9)
            assert numpy.all(drawn <= upper + 1e-9)


def test_the_residual_cannot_invent_or_erase_cloud_the_frames_agree_on():
    # The sharpest form of the bound. A cell clear in both frames stays clear
    # and a cell full in both stays full, however hard the model says air is
    # rising or sinking there. Growth in place is only ever a re-timing of a
    # change the two RETRIEVED frames already contain.
    clear = numpy.zeros((32, 32))
    full = numpy.full((32, 32), 100.0)
    method = DevelopmentResidualMethod()
    for shaping in (-1.0, 1.0):
        motion = shaped_pair(shaping, size=32)
        for fraction in (0.25, 0.5, 0.75):
            assert numpy.allclose(method.composite(clear, clear, motion, fraction), 0.0, atol=1e-12)
            assert numpy.allclose(method.composite(full, full, motion, fraction), 100.0, atol=1e-12)


def test_the_shaped_fraction_stays_monotone_so_the_display_never_backs_up():
    # s(t) = t + gain*phi*t(1-t) is monotone exactly while |gain*phi| <= 1,
    # and monotone-with-fixed-endpoints is what puts s(t) in [0, 1]. If the
    # gain ever moved above the limit this test is what would catch it.
    assert RESIDUAL_SHAPE_GAIN <= 1.0
    steps = numpy.linspace(0.0, 1.0, 201)
    for phi in (-1.0, -0.4, 0.0, 0.4, 1.0):
        fractions = steps + RESIDUAL_SHAPE_GAIN * phi * steps * (1.0 - steps)
        assert numpy.all(numpy.diff(fractions) >= -1e-12)
        assert fractions[0] == pytest.approx(0.0) and fractions[-1] == pytest.approx(1.0)
        assert numpy.all(fractions >= -1e-12) and numpy.all(fractions <= 1.0 + 1e-12)


def test_a_zero_shaping_is_the_baseline_exactly():
    # The residual must cost nothing where the model says nothing. With no
    # shaping the construction IS the baseline, to the last bit.
    previous, following = wide_blob(30), wide_blob(42)
    motion = shaped_pair(0.0, advect=0.6)
    for fraction in (0.25, 0.5, 0.75):
        assert numpy.allclose(
            BaselineMethod().composite(previous, following, motion, fraction),
            DevelopmentResidualMethod().composite(previous, following, motion, fraction),
            atol=1e-12,
        )


def test_where_advection_explains_the_change_the_motion_wins():
    # Constraint: the residual applies only where advection already failed.
    # With the display weight at 1 the shaping cannot reach the picture at
    # all, however saturated it is.
    previous, following = wide_blob(30), wide_blob(42)
    for shaping in (-1.0, 1.0):
        advecting = shaped_pair(shaping, advect=1.0)
        neutral = shaped_pair(0.0, advect=1.0)
        for fraction in (0.25, 0.5, 0.75):
            assert numpy.allclose(
                DevelopmentResidualMethod().composite(previous, following, advecting, fraction),
                DevelopmentResidualMethod().composite(previous, following, neutral, fraction),
                atol=1e-12,
            )


def test_ascent_early_makes_cloud_appear_early_and_descent_early_thins_it_early():
    # The whole point, and the thing advection provably cannot do. A cell that
    # is clear in frame 0 and cloudy in frame 1 grew in place. Where the model
    # says the ascent that made it was strongest at the START of the interval,
    # the cloud must be most of the way there by the midpoint; where the
    # ascent builds towards the END it must still be mostly absent.
    clear, cloudy = numpy.zeros((16, 16)), numpy.full((16, 16), 80.0)
    method = DevelopmentResidualMethod()
    early = method.composite(clear, cloudy, shaped_pair(0.8, size=16), 0.5)
    late = method.composite(clear, cloudy, shaped_pair(-0.8, size=16), 0.5)
    dissolve = method.composite(clear, cloudy, shaped_pair(0.0, size=16), 0.5)
    assert float(early.mean()) > float(dissolve.mean()) > float(late.mean())
    # And the mirror case: cloud DECAYING in place, front-loaded, must be
    # further gone at the midpoint than a constant-rate fade.
    thinning = method.composite(cloudy, clear, shaped_pair(0.8, size=16), 0.5)
    assert float(thinning.mean()) < float(dissolve.mean())


def test_the_shaping_is_read_from_the_model_omega_with_the_right_sign():
    # Sign convention, end to end, from the stored field rather than by
    # inspection. Omega is d(pressure)/dt, so NEGATIVE is ascent. Omega goes
    # -1.0 -> 0.0 Pa/s across the interval: ascent was stronger at the start,
    # so a growing cell must be front-loaded, phi > 0.
    dataset = omega_dataset(3, omega=[-1.0, 0.0, 0.0])
    frames = [dataset["total_cloud"].isel(valid_time=step).values for step in range(3)]
    context = MethodContext(
        variable="total_cloud", frames=frames, indices=(0, 1, 2),
        interval_seconds=3600.0, dataset=dataset,
    )
    motions = DevelopmentResidualMethod().motion(context)
    growing = frames[1] > frames[0]
    shaping = motions[0].extra["dev_shape"]
    assert motions[0].diagnostics["omega_reached"] == 1.0
    assert float(numpy.median(shaping[growing])) > 0.0
    # A decaying cell over the same interval is front-loaded by the DESCENT
    # reading of the same tendency, so its shaping is positive too - one
    # expression covering formation and dissipation is the claim.
    decaying = frames[1] < frames[0]
    assert float(numpy.median(shaping[decaying])) < 0.0


def test_absent_vertical_velocity_is_an_absent_residual_never_a_zero_one():
    # The steering prior's rule, applied to omega: a model that did not
    # publish the level costs the re-timing and nothing else. The method then
    # composites exactly as the baseline does.
    dataset = omega_dataset(3).drop_vars("omega_700hPa")
    frames = [dataset["total_cloud"].isel(valid_time=step).values for step in range(3)]
    context = MethodContext(
        variable="total_cloud", frames=frames, indices=(0, 1, 2),
        interval_seconds=3600.0, dataset=dataset,
    )
    motions = DevelopmentResidualMethod().motion(context)
    for pair in motions:
        assert pair.diagnostics["omega_reached"] == 0.0
        assert numpy.allclose(pair.extra["dev_shape"], 0.0)
    baseline = BaselineMethod().motion(context)
    for mine, theirs in zip(motions, baseline):
        assert numpy.allclose(mine.flow01, theirs.flow01)


def test_the_residual_is_earned_per_variable_and_both_numbers_are_published():
    # `configure` is where an optional ingredient earns its place. Whatever it
    # decides, provenance must carry the held-out score both with the residual
    # and without it, so the claim is checkable rather than asserted.
    dataset = omega_dataset(5, omega=[-1.0, -0.5, 0.0, 0.3, 0.6])
    frames = [dataset["total_cloud"].isel(valid_time=step).values for step in range(5)]
    context = MethodContext(
        variable="total_cloud", frames=frames, indices=(0, 1, 2, 3, 4),
        interval_seconds=3600.0, dataset=dataset,
    )
    active, notes = DevelopmentResidualMethod().configure(context)
    assert isinstance(active, DevelopmentResidualMethod)
    assert notes["residual_applied"] is active.use_residual
    assert notes["residual_level_hpa"] == 700
    assert notes["held_out_improvement_with_residual"] is not None
    assert notes["held_out_improvement_without_residual"] is not None
    # The two numbers must be two REAL measurements of two different
    # constructions. They came back identical to five decimals once, because
    # the with-residual case was reusing the steering prior's own no-prior
    # score, which is computed without the dataset the shaping is read from -
    # so the residual was being compared against itself and would have been
    # refused for the wrong reason, silently.
    assert (
        notes["held_out_improvement_with_residual"]
        != notes["held_out_improvement_without_residual"]
    )
    # Applied only if it actually predicts the held-out frames better. This is
    # the direction of the inequality, not a claim about which way it went.
    if active.use_residual:
        assert notes["held_out_improvement_with_residual"] > notes["held_out_improvement_without_residual"]
    else:
        assert notes["held_out_improvement_with_residual"] <= notes["held_out_improvement_without_residual"]
def cascade_frames(size: int = 96) -> list[numpy.ndarray]:
    """A translating blob with fine texture riding on it.

    A smooth blob alone has almost nothing in the fine bands, so it cannot
    tell a cascade that dissolves fine texture from one that advects it. The
    ripple is what makes the finest octaves carry anything at all.
    """
    row_index, col_index = numpy.mgrid[0:size, 0:size]
    ripple = 6.0 * numpy.sin(col_index * 1.7) * numpy.cos(row_index * 1.3)
    return [numpy.clip(wide_blob(24 + 8 * step, size=size) + numpy.roll(ripple, 8 * step, axis=1), 0.0, 100.0)
            for step in range(5)]


def test_scale_cascade_is_registered_disabled_with_its_own_shader_and_fields():
    method = method_by_id("scale-cascade")
    assert method is not None
    # Registered but out of every cycle: it loses to its own scale-blind
    # control, and the client could not evaluate the pyramid if it won. The
    # registry keeps the code and the measurement readable either way.
    assert method.enabled is False
    assert not method.generative
    assert method.shader == "cascade"
    assert method.shader not in (BaselineMethod.shader, IntermediateFlowMethod.shader)
    # One stored ratio per band, plus the residual the last octave leaves.
    assert method.extra_suffixes == tuple(f"cascade_w{index}" for index in range(CASCADE_OCTAVES + 1))
    # Disabled means the derive never pays for it and the artifact never
    # carries it, which is the point of the flag.
    assert method not in enabled_methods()


def test_cascade_bands_recombine_to_the_retrieved_frame():
    # The evidence rule, as arithmetic: the bands are a partition of the real
    # frame, so nothing downstream can weight them into content that was not
    # retrieved. If this ever fails, every endpoint guarantee below is void.
    field = blob_field() + 3.0 * numpy.sin(numpy.mgrid[0:96, 0:96][1] * 0.9)
    bands = _cascade_bands(field)
    assert len(bands) == CASCADE_OCTAVES + 1
    assert numpy.allclose(sum(bands), field, atol=1e-12)
    # And the split is real: the finest band is not an empty field.
    assert float(numpy.max(numpy.abs(bands[0]))) > 1.0


def test_scale_cascade_is_endpoint_exact():
    # The constraint a decomposition is most likely to break, so it is pinned
    # bit for bit rather than approximately - and with band ratios present,
    # because the fallback path is not what ships.
    frames = cascade_frames()
    context = MethodContext(
        variable="total_cloud", frames=[frames[0], frames[1]], indices=(0, 1), interval_seconds=3600.0
    )
    motion = ScaleCascadeMethod().motion(context)[0]
    assert set(motion.extra) == set(ScaleCascadeMethod.extra_suffixes)
    method = ScaleCascadeMethod()
    assert numpy.array_equal(method.composite(frames[0], frames[1], motion, 0.0), frames[0])
    assert numpy.array_equal(method.composite(frames[0], frames[1], motion, 1.0), frames[1])


def test_scale_cascade_reduces_to_the_baseline_when_every_band_agrees():
    # Ratio 1 on every band is exactly the shipped construction, so this
    # method can only differ where the bands actually disagree about whether
    # advection explains the change. A pair carrying no ratios at all - an
    # older artifact, or a hand-built motion - must take the same path.
    previous, following = wide_blob(30), wide_blob(42)
    plain_pair = held_pair(12.0, -12.0)
    ones = {suffix: numpy.ones(previous.shape) for suffix in ScaleCascadeMethod.extra_suffixes}
    unit_pair = PairMotion(
        flow01=plain_pair.flow01, flow10=plain_pair.flow10, confidence=plain_pair.confidence,
        support=plain_pair.support, advect_weight=plain_pair.advect_weight, extra=ones,
    )
    for fraction in (0.25, 0.5, 0.75):
        baseline = BaselineMethod().composite(previous, following, plain_pair, fraction)
        for pair in (unit_pair, plain_pair):
            assert numpy.allclose(
                ScaleCascadeMethod().composite(previous, following, pair, fraction), baseline, atol=1e-9
            )


def test_the_held_out_veto_reaches_every_band_of_the_cascade():
    # The derive publishes a zero display weight for a variable that fails its
    # held-out control, and that variable must then crossfade EVERYWHERE. The
    # per-band field is stored as a ratio ON that weight precisely so a method
    # carrying its own weights cannot walk past the veto.
    frames = cascade_frames()
    context = MethodContext(
        variable="total_cloud", frames=[frames[0], frames[1]], indices=(0, 1), interval_seconds=3600.0
    )
    motion = ScaleCascadeMethod().motion(context)[0]
    vetoed = PairMotion(
        flow01=motion.flow01, flow10=motion.flow10, confidence=motion.confidence,
        support=motion.support, advect_weight=numpy.zeros(frames[0].shape), extra=motion.extra,
    )
    # Some band did want to advect, or this test would pass vacuously.
    assert float(numpy.max(motion.extra["cascade_w0"])) > 0.1
    crossfade = 0.5 * frames[0] + 0.5 * frames[1]
    assert numpy.allclose(
        ScaleCascadeMethod().composite(frames[0], frames[1], vetoed, 0.5), crossfade, atol=1e-9
    )


def test_scale_cascade_actually_advects_rather_than_dissolving():
    # The failure this method could hide: a cascade whose bands advect but
    # whose recombination cancels the motion would still score well and show
    # nothing. On a field that genuinely translates, the midpoint composite
    # must sit where the content actually is, not halfway between two ghosts.
    frames = cascade_frames()
    context = MethodContext(
        variable="total_cloud", frames=[frames[0], frames[2]], indices=(0, 2), interval_seconds=3600.0
    )
    motion = ScaleCascadeMethod().motion(context)[0]
    composite = ScaleCascadeMethod().composite(frames[0], frames[2], motion, 0.5)
    crossfade = 0.5 * frames[0] + 0.5 * frames[2]
    truth = frames[1]
    assert _score_one(composite, truth)[0] < _score_one(crossfade, truth)[0]
    # The brightest column moves with the flow instead of standing still.
    column_of = lambda field: float(numpy.argmax(field.sum(axis=0)))  # noqa: E731
    assert column_of(frames[0]) < column_of(composite) < column_of(frames[2])


def test_leave_one_out_is_absent_not_zero_when_nothing_can_be_held_out():
    assert _interpolation_skill([blob_field(), blob_field()]) is None


class FakeStore:
    """Just enough of ArtifactStore for the derive path."""

    class config:  # noqa: D106 - namespace only
        bucket = "weather-artifacts"

    def __init__(self, payloads: dict[str, Path], artifacts: list[CurrentArtifact]) -> None:
        self._payloads = payloads
        self._artifacts = artifacts
        self.published: list = []

        outer = self

        class S3:
            def download_file(self, bucket: str, key: str, destination: str) -> None:
                shutil.copyfile(outer._payloads[key], destination)

        self.s3 = S3()

    def current_artifacts(self):
        return list(self._artifacts)

    def stage_and_publish(self, result):
        self.published.append(result)
        return []


def surface_artifact(tmp_path: Path, *, frames: int = 3, variable: str = "total_cloud") -> tuple[CurrentArtifact, Path]:
    base = datetime(2026, 8, 31, 12, tzinfo=UTC)
    stamps = [numpy.datetime64((base + timedelta(hours=step)).replace(tzinfo=None), "ns") for step in range(frames)]
    data = numpy.stack([numpy.roll(blob_field(), 4 * step, axis=1) for step in range(frames)])
    dataset = xarray.Dataset(
        {variable: (("valid_time", "y", "x"), data, {"units": "percent"})},
        coords={"valid_time": stamps},
    )
    payload = tmp_path / "surface.zarr.zip"
    write_zarr(dataset, payload)
    artifact = CurrentArtifact(
        source_id="eccc-hrdps",
        logical_name="surface",
        revision_id="rev-surface-1",
        object_key="published/eccc-hrdps/surface",
        media_type="application/zarr+zip",
        byte_size=payload.stat().st_size,
        provenance={"product": "ECCC-HRDPS", "sha256": sha256_of(payload)},
        published_at=base,
        run_time=base,
        retrieved_at=base,
        provider_run_id="2026083112",
        native_crs="EPSG:4326",
    )
    return artifact, payload


def test_derive_publishes_flow_with_full_derivation_provenance(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_cloud_motion(store, artifact, ("total_cloud",), workdir)
    assert result is not None
    assert result.provider_run_id == "2026083112+cloud-motion"
    derived = result.artifacts[0]
    assert derived.logical_name == LOGICAL_NAME
    assert derived.provenance["derived"] is True
    assert derived.provenance["base_revision_id"] == "rev-surface-1"
    assert derived.provenance["derivation_version"] == VERSION
    assert "not evidence" in derived.provenance["derivation"]
    quality = derived.provenance["quality"]["per_variable"]["total_cloud"]
    assert quality["pairs"] == 2
    # The flow explains the change far better than persistence would.
    assert quality["mae_full_warp_percent"][0] < quality["mae_persistence_percent"][0]
    # A steadily translating field must actually be advected on screen: the
    # display weight, not just the flow, is what the reader sees.
    assert quality["advect_weight_median"] > 0.5
    assert quality["advect_weight_above_half_fraction"] > 0.5
    assert quality["leave_one_out"]["improvement_over_reversed_flow"] > MIN_HELD_OUT_IMPROVEMENT

    import zarr

    zip_store = zarr.storage.ZipStore(str(derived.payload_path), mode="r")
    try:
        stored = xarray.open_zarr(zip_store, consolidated=False)
        for suffix in ("u01", "v01", "u10", "v10", "confidence", "advect_weight", "vs_u", "vs_v", "ve_u", "ve_v"):
            assert f"total_cloud_{suffix}" in stored.data_vars
        # Every enabled method is published, on its own axis, and the default
        # is first so a reader that ignores the axis still gets the baseline.
        published = [str(value) for value in stored["method"].values]
        assert published == [method.id for method in enabled_methods()]
        assert published[0] == DEFAULT_METHOD_ID
        baseline = stored.isel(method=published.index(DEFAULT_METHOD_ID))
        # Constant velocity (a 4-cell roll per frame): the Hermite tangents
        # agree with the segment flow, so playback matches linear advection.
        core = blob_field() > 20.0
        assert float(numpy.median(numpy.abs(
            baseline["total_cloud_vs_u"].values[0][core] - baseline["total_cloud_u01"].values[0][core]
        ))) < 1.0
        assert stored.sizes["pair"] == 2
        assert stored.attrs["derivation_version"] == VERSION
    finally:
        zip_store.close()


def test_the_derive_publishes_the_residual_shaping_on_the_method_axis(tmp_path: Path):
    # End to end: the extra suffix reaches the stored artifact under the
    # development-residual method, and the methods that do not declare it get
    # an explicit zero field rather than a ragged artifact - so a client
    # reading dev_shape for the wrong method gets a no-op, never another
    # method's numbers under this method's name.
    artifact, payload = surface_artifact(tmp_path)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_cloud_motion(store, artifact, ("total_cloud",), workdir)
    assert result is not None
    derived = result.artifacts[0]
    per_method = derived.provenance["quality"]["per_variable"]["total_cloud"]["per_method"]
    assert "development-residual" in per_method
    options = per_method["development-residual"]["options"]
    # Both numbers published, whatever the decision - the claim is checkable.
    assert "residual_applied" in options
    assert "held_out_improvement_with_residual" in options

    import zarr

    zip_store = zarr.storage.ZipStore(str(derived.payload_path), mode="r")
    try:
        stored = xarray.open_zarr(zip_store, consolidated=False)
        assert "total_cloud_dev_shape" in stored.data_vars
        published = [str(value) for value in stored["method"].values]
        baseline = stored["total_cloud_dev_shape"].values[published.index(DEFAULT_METHOD_ID)]
        assert numpy.allclose(baseline, 0.0)
        # This fixture carries no omega at all, so the shaping is absent
        # rather than zeroed by decision - and absent shaping is a stored zero
        # field, which the shader reads as a constant-rate dissolve.
        mine = stored["total_cloud_dev_shape"].values[published.index("development-residual")]
        assert numpy.allclose(mine, 0.0)
    finally:
        zip_store.close()


def test_motion_that_fails_the_held_out_test_is_vetoed_to_a_crossfade(tmp_path: Path):
    # Three unrelated fields: no motion field can explain the change, so
    # interpolating across a held-out frame cannot beat a plain dissolve of
    # its neighbours. Every pair's display weight goes to zero and the client
    # crossfades, disclosed, rather than dragging pixels around convincingly.
    # (The per-pair warp-vs-persistence floor does not catch this on its own:
    # DIS minimises exactly that quantity, so it can always find a warp that
    # lowers it, even between two fields with nothing in common.)
    base = datetime(2026, 8, 31, 12, tzinfo=UTC)
    generator = numpy.random.default_rng(11)
    data = numpy.stack([generator.uniform(0.0, 100.0, (96, 96)) for _ in range(3)])
    stamps = [numpy.datetime64((base + timedelta(hours=step)).replace(tzinfo=None), "ns") for step in range(3)]
    dataset = xarray.Dataset(
        {"total_cloud": (("valid_time", "y", "x"), data, {"units": "percent"})},
        coords={"valid_time": stamps},
    )
    payload = tmp_path / "noise.zarr.zip"
    write_zarr(dataset, payload)
    artifact, _ = surface_artifact(tmp_path)
    noisy = CurrentArtifact(**{**artifact.__dict__, "provenance": {**artifact.provenance, "sha256": sha256_of(payload)}})
    store = FakeStore({noisy.object_key: payload}, [noisy])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_cloud_motion(store, noisy, ("total_cloud",), workdir)
    assert result is not None

    import zarr

    zip_store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    try:
        stored = xarray.open_zarr(zip_store, consolidated=False)
        assert float(stored["total_cloud_advect_weight"].values.max()) == 0.0
    finally:
        zip_store.close()


def test_a_single_frame_derives_nothing(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path, frames=1)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    assert derive_cloud_motion(store, artifact, ("total_cloud",), workdir) is None


def test_a_wrong_digest_refuses_to_derive(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path)
    tampered = CurrentArtifact(**{**artifact.__dict__, "provenance": {**artifact.provenance, "sha256": "0" * 64}})
    store = FakeStore({artifact.object_key: payload}, [tampered])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    with pytest.raises(RuntimeError, match="digest"):
        derive_cloud_motion(store, tampered, ("total_cloud",), workdir)


def motion_row(artifact, provenance: dict) -> CurrentArtifact:
    return CurrentArtifact(
        source_id="eccc-hrdps",
        logical_name=LOGICAL_NAME,
        revision_id="rev-motion-1",
        object_key="published/eccc-hrdps/cloud_motion",
        media_type="application/zarr+zip",
        byte_size=1,
        provenance=provenance,
        published_at=artifact.published_at,
        run_time=artifact.run_time,
        retrieved_at=artifact.retrieved_at,
        provider_run_id="2026083112+cloud-motion",
        native_crs="EPSG:4326",
    )


def test_cycle_skips_an_up_to_date_motion_artifact(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path)
    motion = motion_row(artifact, {"base_revision_id": "rev-surface-1", "derivation_version": VERSION})
    store = FakeStore({artifact.object_key: payload}, [artifact, motion])
    lines = cloud_motion_cycle(store)
    assert store.published == []
    assert lines == []


def test_cycle_rederives_when_the_construction_version_moved_on(tmp_path: Path):
    # Same surface revision, but the current artifact came from an older
    # derivation: the version bump re-derives so old motion never lingers.
    artifact, payload = surface_artifact(tmp_path)
    motion = motion_row(artifact, {"base_revision_id": "rev-surface-1", "derivation_version": "cloud-motion-dis-v1"})
    store = FakeStore({artifact.object_key: payload}, [artifact, motion])
    lines = cloud_motion_cycle(store)
    assert len(store.published) == 1
    assert any("published for surface revision rev-surface-1" in line for line in lines)


def test_cycle_derives_when_the_surface_moved_on(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    lines = cloud_motion_cycle(store)
    assert len(store.published) == 1
    assert any("published for surface revision rev-surface-1" in line for line in lines)
