"""The `error-variance-blend` bench method: CMORPH-KF weights on the shipped wire.

What is pinned here: the method rides the EXISTING `visibility` shader and the
existing `vis0`/`vis1` suffixes, so it needs no client change; it is endpoint
exact by construction (exact equality, not approximate); its weights are
strictly positive, bounded and normalise to one; it reduces to the baseline's
`(1 - t, t)` exactly wherever the two error variances are equal; it goes
asymmetric where one warp is genuinely worse; and it is applied only on the
held-out measurement, with the time-weight control published beside it.
"""

from __future__ import annotations

import numpy
import pytest

pytest.importorskip("cv2")

from ingest.derive.flow_ops import WARP_ERROR_FLOOR_PERCENT
from ingest.derive.methods import (
    BaselineMethod,
    MethodContext,
    PairMotion,
    _score_one,
)
from ingest.derive.methods.error_variance_blend import ErrorVarianceBlendMethod


def blob_field(rows: int = 96, cols: int = 96, *, centre=(48, 48), sigma: float = 9.0) -> numpy.ndarray:
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    distance2 = (row_index - centre[0]) ** 2 + (col_index - centre[1]) ** 2
    return 100.0 * numpy.exp(-distance2 / (2 * sigma**2))


def wide_blob(centre_col: float, *, size: int = 96, sigma: float = 7.0) -> numpy.ndarray:
    """One blob on a grid wide enough that a warp never runs off an edge."""
    return blob_field(size, size, centre=(size // 2, centre_col), sigma=sigma)


def uniform_flow(dx: float, dy: float, shape=(96, 96)) -> numpy.ndarray:
    flow = numpy.zeros(tuple(shape) + (2,), dtype="float64")
    flow[..., 0] = dx
    flow[..., 1] = dy
    return flow


def weighted_pair(v0, v1, *, size: int = 96, flow: float = 12.0) -> PairMotion:
    """A pair whose two reliabilities are supplied rather than measured.

    The claim of this method is about the FUSION, so the weight pair is handed
    in: measuring it would decide both, and there would be no way to construct
    the asymmetry the method exists to exploit. Scalars broadcast to a field.
    """
    def field(value):
        return numpy.full((size, size), float(value)) if numpy.isscalar(value) else numpy.asarray(value, dtype="float64")

    return PairMotion(
        flow01=uniform_flow(flow, 0.0, shape=(size, size)),
        flow10=uniform_flow(-flow, 0.0, shape=(size, size)),
        confidence=numpy.ones((size, size)),
        support=numpy.ones((size, size)),
        advect_weight=numpy.ones((size, size)),
        extra={"vis0": field(v0), "vis1": field(v1)},
    )


def context_for(frames: list[numpy.ndarray]) -> MethodContext:
    return MethodContext(
        variable="total_cloud",
        frames=frames,
        indices=tuple(range(len(frames))),
        interval_seconds=3600.0,
    )


def test_error_variance_blend_reuses_the_shipped_visibility_wire():
    # The whole point of the method: the client already fuses two warps by a
    # stored per-pixel weight pair, so a different way of computing that pair
    # must need ZERO client change. A new shader name or a new suffix here
    # would mean the opposite.
    method = ErrorVarianceBlendMethod()
    assert method.id == "error-variance-blend"
    assert method.enabled and not method.generative
    assert method.shader == "visibility"
    assert method.extra_suffixes == ("vis0", "vis1")
    assert method.shader != BaselineMethod.shader


def test_error_variance_blend_is_endpoint_exact():
    # Non-negotiable for every method on the bench, and the weights must not
    # be able to break it: at a real instant the real frame shows UNTOUCHED,
    # bit for bit, even where the weight pair says that frame's own warp is
    # worthless. Exact equality, not approximate.
    previous, following = wide_blob(30), wide_blob(42)
    method = ErrorVarianceBlendMethod()
    for weights in ((1.0, 1.0), (0.001, 1.0), (1.0, 0.001), (0.5, 0.5)):
        motion = weighted_pair(*weights)
        assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
        assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)


def test_endpoint_exactness_survives_a_measured_weight_pair():
    # The same property with the weights DERIVED rather than handed in, on a
    # pair whose two warps really do disagree - the case where a t-dependent
    # weight could most easily leak into the endpoints.
    previous = wide_blob(30)
    following = wide_blob(42) + blob_field(96, 96, centre=(20, 70), sigma=5.0)
    method = ErrorVarianceBlendMethod()
    motion = method.motion(context_for([previous, following]))[0]
    assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
    assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)


def test_fusion_weights_are_positive_bounded_and_sum_to_one():
    # The weights are read straight out of the construction rather than
    # inferred from the picture: w0 = (1-t)v0 and w1 = t v1, normalised. Both
    # strictly positive, both at most 1, summing to exactly 1 - which is what
    # makes every displayed pixel a convex combination of two retrieved
    # samples, the bound the disclosure rests on.
    previous = wide_blob(30)
    following = wide_blob(42) + blob_field(96, 96, centre=(20, 70), sigma=5.0)
    method = ErrorVarianceBlendMethod()
    motion = method.motion(context_for([previous, following]))[0]
    visibility0 = numpy.asarray(motion.extra["vis0"])
    visibility1 = numpy.asarray(motion.extra["vis1"])
    assert visibility0.shape == previous.shape and visibility1.shape == previous.shape
    for weights in (visibility0, visibility1):
        assert float(weights.min()) > 0.0
        assert float(weights.max()) <= 1.0
    for fraction in (0.1, 0.25, 0.5, 0.75, 0.9):
        weight0 = (1.0 - fraction) * visibility0
        weight1 = fraction * visibility1
        total = weight0 + weight1
        assert float(total.min()) > 0.0
        normalised0, normalised1 = weight0 / total, weight1 / total
        assert float(normalised0.min()) > 0.0 and float(normalised1.min()) > 0.0
        assert numpy.allclose(normalised0 + normalised1, 1.0, atol=1e-12)
        # And the picture obeys the same bound: nothing outside the two frames.
        drawn = method.composite(previous, following, motion, fraction)
        low = numpy.minimum(previous.min(), following.min())
        high = numpy.maximum(previous.max(), following.max())
        assert float(drawn.min()) >= float(low) - 1e-9
        assert float(drawn.max()) <= float(high) + 1e-9


def test_equal_error_variances_reduce_to_the_time_linear_weights():
    # THE reduction that makes this a controlled change rather than a new
    # construction: where the two errors are equal the weights are exactly
    # (1 - t, t) and the method IS the baseline, so it degrades to the shipped
    # blend rather than to something arbitrary.
    previous, following = wide_blob(30), wide_blob(42)
    for value in (1.0, 0.4, 0.05):
        motion = weighted_pair(value, value)
        for fraction in (0.25, 0.5, 0.75):
            baseline = BaselineMethod().composite(previous, following, motion, fraction)
            variance = ErrorVarianceBlendMethod().composite(previous, following, motion, fraction)
            assert numpy.allclose(baseline, variance, atol=1e-12)


def test_equal_measured_variances_reduce_to_the_baseline_pixel_for_pixel():
    # The same reduction with the variances MEASURED. A field that purely
    # translates gives both warps the same error everywhere, so the derived
    # weights must be equal to within rounding and the drawn frame must be the
    # baseline's.
    previous, following = wide_blob(30), wide_blob(42)
    method = ErrorVarianceBlendMethod()
    motion = method.motion(context_for([previous, following]))[0]
    visibility0 = numpy.asarray(motion.extra["vis0"])
    visibility1 = numpy.asarray(motion.extra["vis1"])
    assert float(numpy.mean(numpy.abs(visibility0 - visibility1))) < 0.05
    for fraction in (0.25, 0.5, 0.75):
        baseline = BaselineMethod().composite(previous, following, motion, fraction)
        variance = ErrorVarianceBlendMethod().composite(previous, following, motion, fraction)
        assert float(numpy.max(numpy.abs(baseline - variance))) < 2.0


def test_a_missing_weight_pair_is_the_baseline_not_a_guess():
    # An absent weight pair is an absent measurement, never a zero one - this
    # is also what the harness's synthetic pairs and another method's artifact
    # hand it.
    previous, following = wide_blob(30), wide_blob(42)
    motion = PairMotion(
        flow01=uniform_flow(12.0, 0.0),
        flow10=uniform_flow(-12.0, 0.0),
        confidence=numpy.ones((96, 96)),
        support=numpy.ones((96, 96)),
        advect_weight=numpy.ones((96, 96)),
    )
    for fraction in (0.25, 0.5, 0.75):
        baseline = BaselineMethod().composite(previous, following, motion, fraction)
        variance = ErrorVarianceBlendMethod().composite(previous, following, motion, fraction)
        assert numpy.allclose(baseline, variance, atol=1e-12)


def test_variances_part_company_where_one_warp_is_genuinely_worse():
    # The derivation, not the fusion. A blob translating east, with a second
    # blob that exists only in the later frame: the later frame carries content
    # the earlier one cannot explain, so ONE of the two warps is measurably
    # worse there and the two error variances - and hence the two weights -
    # must part company.
    previous = wide_blob(30)
    occluded = wide_blob(42) + blob_field(96, 96, centre=(20, 70), sigma=5.0)
    method = ErrorVarianceBlendMethod()
    motion = method.motion(context_for([previous, occluded]))[0]
    visibility0 = numpy.asarray(motion.extra["vis0"])
    visibility1 = numpy.asarray(motion.extra["vis1"])
    # A pair that never parts company would make this the baseline with extra
    # storage, so the asymmetry is required, not merely allowed.
    assert float(numpy.max(numpy.abs(visibility0 - visibility1))) > 0.05
    assert motion.diagnostics["variance_asymmetry_mean"] > 0.0
    assert motion.diagnostics["error_variance_mean"] > 0.0
    assert motion.diagnostics["error_variance_applied"] == 1.0
    # And it is asymmetric WHERE the unexplained content is, not uniformly:
    # the disagreement near the appearing blob exceeds the field's own mean.
    difference = numpy.abs(visibility0 - visibility1)
    near = blob_field(96, 96, centre=(20, 70), sigma=5.0) > 20.0
    assert float(numpy.mean(difference[near])) > float(numpy.mean(difference))
    # The same pair on a purely translating sequence stays symmetric, so the
    # asymmetry is a property of the occlusion rather than of the estimator.
    clean = method.motion(context_for([wide_blob(30), wide_blob(42)]))[0]
    assert clean.diagnostics["variance_asymmetry_mean"] < motion.diagnostics["variance_asymmetry_mean"]


def test_the_reliability_is_the_inverse_VARIANCE_not_a_linear_penalty():
    # What separates this method from the retired linear-reliability fusion it
    # replaced: the penalty is quadratic in the residual, which is what
    # "inversely proportional to error variance" (Joyce & Xie 2011) means. On a
    # uniform residual of e the weight must be floor^2/(e^2 + floor^2) exactly
    # - 0.2 at e = 2 floor - where a linear reliability would say 0.333.
    flat = uniform_flow(0.0, 0.0)
    floor_percent = WARP_ERROR_FLOOR_PERCENT
    residual = 2.0 * floor_percent
    previous = numpy.zeros((96, 96))
    following = numpy.full((96, 96), residual)
    weight0, weight1, variance0, variance1 = ErrorVarianceBlendMethod._reliability_pair(
        previous, following, flat, flat
    )
    expected = floor_percent**2 / (residual**2 + floor_percent**2)
    assert numpy.allclose(variance0, residual**2, rtol=1e-4)
    assert numpy.allclose(weight0, expected, rtol=1e-4)
    assert numpy.allclose(weight1, expected, rtol=1e-4)
    # And it is NOT the linear reliability the visibility method uses.
    assert abs(expected - 1.0 / (1.0 + residual / floor_percent)) > 0.1


def test_the_variances_are_smoothed_before_they_are_inverted():
    # An unsmoothed per-pixel squared error is noise, not a variance. A step
    # residual - a square patch present in one frame only, with no motion -
    # must come back as a graded weight field rather than a two-valued mask.
    flat = uniform_flow(0.0, 0.0)
    patch = numpy.zeros((96, 96))
    patch[40:56, 40:56] = 80.0
    weight0, _, _, _ = ErrorVarianceBlendMethod._reliability_pair(
        numpy.zeros((96, 96)), patch, flat, flat
    )
    graded = numpy.count_nonzero((weight0 > weight0.min() + 1e-3) & (weight0 < weight0.max() - 1e-3))
    # The patch has 256 cells and 60 boundary cells; a hard mask would leave
    # essentially none of the field in between.
    assert graded > 500


def test_the_two_residuals_are_carried_to_the_SAME_midpoint_coordinates():
    # The sign convention, pinned rather than inspected. Content translates 12
    # cells east and a blob at column 70 exists only in the later frame, so
    # `e0` carries its error at column 70 in frame 1's coordinates and `e1`
    # carries it at column 58 in frame 0's. Both must land on column 64 - the
    # midpoint - and they can only do that if `e0` is pulled with -F01/2 and
    # `e1` with +F01/2. Swapping the two sends them to 76 and 46 instead.
    previous = wide_blob(30)
    following = wide_blob(42) + blob_field(96, 96, centre=(20, 70), sigma=5.0)
    _, _, variance0, variance1 = ErrorVarianceBlendMethod._reliability_pair(
        previous, following, uniform_flow(12.0, 0.0), uniform_flow(-12.0, 0.0)
    )
    band = slice(17, 24)  # the rows the appearing blob occupies
    peak0 = int(numpy.argmax(variance0[band].mean(axis=0)))
    peak1 = int(numpy.argmax(variance1[band].mean(axis=0)))
    assert peak0 == pytest.approx(64, abs=2)
    assert peak1 == pytest.approx(64, abs=2)


def test_the_gate_refuses_where_the_variance_weights_do_not_help():
    # The gate has to be able to say no, or it is not a measurement. On pure
    # noise there is no coherent motion for either weighting to exploit and the
    # variance weights score WORSE than the time weights, so the method must
    # settle to the baseline fusion and say so.
    rng = numpy.random.default_rng(7)
    frames = [rng.uniform(0.0, 100.0, size=(64, 64)) for _ in range(5)]
    settled, notes = ErrorVarianceBlendMethod().configure(context_for(frames))
    assert notes["held_out_improvement_with_error_variance"] < notes["held_out_improvement_with_time_weights"]
    assert notes["error_variance_applied"] is False
    assert settled.use_error_variance is False


def test_the_more_certain_warp_carries_the_pixel():
    # The claim, deliberately constructed. Content really moves 12 cells east
    # and the flow says so, but frame 1 is displaced, so a 50/50 average at the
    # midpoint really is a double image. Told that frame 1's warp has the far
    # larger error variance, the fusion gives frame 0 nearly the whole pixel.
    previous, truth = wide_blob(30), wide_blob(36)
    following_wrong = wide_blob(54)
    floor = WARP_ERROR_FLOOR_PERCENT**2
    certain = floor / (0.0 + floor)  # sigma^2 = 0: a warp that explains the other frame
    uncertain = floor / (50.0 * floor + floor)  # a warp that badly does not
    motion = weighted_pair(certain, uncertain)
    baseline_mae, baseline_ssim = _score_one(
        BaselineMethod().composite(previous, following_wrong, motion, 0.5), truth
    )
    variance_mae, variance_ssim = _score_one(
        ErrorVarianceBlendMethod().composite(previous, following_wrong, motion, 0.5), truth
    )
    assert variance_mae < baseline_mae
    assert variance_ssim > baseline_ssim


def test_the_gate_measures_the_weights_against_the_time_weights_and_publishes_both():
    # Non-negotiable 3: applied only if it improves, scored against the
    # BASELINE'S time-linear weights on the same motion, with both numbers in
    # provenance so "the variance weighting helped" is checkable.
    frames = [wide_blob(20 + 8 * step) for step in range(5)]
    settled, notes = ErrorVarianceBlendMethod().configure(context_for(frames))
    assert isinstance(settled, ErrorVarianceBlendMethod)
    with_variance = notes["held_out_improvement_with_error_variance"]
    with_time = notes["held_out_improvement_with_time_weights"]
    assert with_variance is not None and with_time is not None
    # The gate is the comparison itself, not a hope about which way it went.
    assert notes["error_variance_applied"] is (with_variance > with_time)
    assert settled.use_error_variance is notes["error_variance_applied"]
    assert notes["skill"] is not None
    assert notes["skill"]["method"] == "error-variance-blend"


def test_the_gate_refusing_publishes_the_baseline_fusion_on_the_same_wire():
    # A method whose gate said no must still publish a well-formed weight pair:
    # ones normalise to (1 - t, t), which is the shipped blend, rather than a
    # zero pair the client would have to guess about.
    previous, following = wide_blob(30), wide_blob(42) + blob_field(96, 96, centre=(20, 70), sigma=5.0)
    method = ErrorVarianceBlendMethod(use_error_variance=False)
    motion = method.motion(context_for([previous, following]))[0]
    assert numpy.array_equal(motion.extra["vis0"], numpy.ones(previous.shape))
    assert numpy.array_equal(motion.extra["vis1"], numpy.ones(previous.shape))
    assert motion.diagnostics["error_variance_applied"] == 0.0
    for fraction in (0.25, 0.5, 0.75):
        baseline = BaselineMethod().composite(previous, following, motion, fraction)
        drawn = method.composite(previous, following, motion, fraction)
        assert numpy.allclose(baseline, drawn, atol=1e-12)


def test_error_variance_blend_costs_nothing_on_a_purely_translating_field():
    # The same held-out harness every method is ranked by, on a field that
    # genuinely translates and where both warps are therefore about equally
    # certain. The method must not cost anything here: it is the disagreement
    # case it exists for.
    from ingest.derive.methods.harness import _interpolation_skill

    frames = [wide_blob(20 + 8 * step) for step in range(5)]
    baseline = _interpolation_skill(frames, method=BaselineMethod(), variable="total_cloud")
    variance = _interpolation_skill(frames, method=ErrorVarianceBlendMethod(), variable="total_cloud")
    assert baseline is not None and variance is not None
    assert variance["midpoint_mae_percent"] <= baseline["midpoint_mae_percent"] + 1e-3
    assert variance["midpoint_ssim"] >= baseline["midpoint_ssim"] - 1e-4
