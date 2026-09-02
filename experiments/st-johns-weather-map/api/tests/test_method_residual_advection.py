"""The `residual-advection` method: the growth-and-decay term, computed rather than learned.

What is pinned here, in the order the claim has to be defended:

- endpoint exactness, and that it is ALGEBRA rather than the two guards - the
  composite is checked arbitrarily close to both ends, where a residual
  delivered on a non-vanishing envelope would still be visible;
- the residual itself: zero when the two frames are a pure translation
  (nothing developed, so there is nothing to add), and non-zero AND correctly
  signed when cloud grows or decays in place;
- boundedness, three ways: the stored field is capped, the drawn field stays
  in [0, 100], and the delivered fraction never leaves the interval the two
  retrieved values bracket;
- the veto, which for this method has to reach the stored field because the
  term is fenced by neither `advect_weight` nor its inverse;
- and the measurement gate: the residual is switched OFF where it does not
  reconstruct the held-out frames better than doing nothing, and the negated
  control - the same change delivered back-loaded - is scored and published
  beside it so that a reader can check the residual's SIGN is what carried
  the improvement rather than the mere presence of a mid-interval bump.
"""

from __future__ import annotations

import numpy
import pytest

pytest.importorskip("cv2")

from ingest.derive.methods import BaselineMethod, MethodContext, PairMotion
from ingest.derive.methods.residual_advection import (
    RESIDUAL_CAP_PERCENT,
    RESIDUAL_GAIN,
    ResidualAdvectionMethod,
    _computed_residual,
)

SHAPE = (40, 40)
INTERVAL = 3600.0


def blob(centre_row: float, centre_col: float, *, amplitude: float = 100.0, sigma: float = 5.0) -> numpy.ndarray:
    rows, cols = numpy.mgrid[0:SHAPE[0], 0:SHAPE[1]]
    distance2 = (rows - centre_row) ** 2 + (cols - centre_col) ** 2
    return amplitude * numpy.exp(-distance2 / (2 * sigma**2))


def uniform_flow(dx: float, dy: float) -> numpy.ndarray:
    flow = numpy.zeros(SHAPE + (2,))
    flow[..., 0] = dx
    flow[..., 1] = dy
    return flow


def pair_with(residual: numpy.ndarray, *, flow: numpy.ndarray | None = None, weight: float = 1.0) -> PairMotion:
    """A pair carrying a supplied residual AND the envelope the derive stores for it.

    The composite evaluates the STORED parabola `t(1-t)(gen_a + gen_b t)`, not
    a recomputation from `res_s` - that is the point of the contract, so that
    the bench ranks exactly the picture the shader draws from exactly the two
    fields the shader is handed. A fixture that set only `res_s` would
    therefore be handed a pair with no envelope at all and would silently be
    testing the baseline.
    """
    flow = uniform_flow(0.0, 0.0) if flow is None else flow
    return PairMotion(
        flow01=flow,
        flow10=-flow,
        confidence=numpy.ones(SHAPE),
        support=numpy.ones(SHAPE),
        advect_weight=numpy.full(SHAPE, weight),
        extra={
            "res_s": residual,
            "gen_a": 4.0 * RESIDUAL_GAIN * numpy.asarray(residual, dtype="float64"),
            "gen_b": numpy.zeros(SHAPE),
        },
    )


def context(frames: list[numpy.ndarray]) -> MethodContext:
    return MethodContext(
        variable="total_cloud",
        frames=frames,
        indices=tuple(range(len(frames))),
        interval_seconds=INTERVAL,
    )


def developing(profile) -> list[numpy.ndarray]:
    """A blob that stays put and develops on ``profile``, sampled at five instants.

    A fixed blob plus a uniform, developing offset. Nothing moves and no
    gradient changes, so advection has nothing to explain, the whole of the
    change between any two frames is the residual, and the only thing the
    held-out score can be measuring is WHEN inside the interval that change
    is delivered - which is exactly the question the gate has to answer.
    """
    return [blob(20, 20, amplitude=40.0) + 55.0 * profile(step / 4.0) for step in range(5)]


# ---------- identity ----------

def test_the_identity_the_bench_publishes():
    method = ResidualAdvectionMethod()
    assert method.id == "residual-advection"
    assert method.shader == "residual-advection"
    assert method.enabled and not method.generative
    # `res_s` is the computed residual itself, a stored diagnostic that is
    # never served; `gen_a`/`gen_b` are the envelope coefficients the shader
    # evaluates as `t(1-t)(a + b t)`, and they are what the `residual` texture
    # actually carries. All three, because the client has no dense flow of its
    # own and cannot recompute any of them.
    assert method.extra_suffixes == ("res_s", "gen_a", "gen_b")
    # Not fenced by `advect_weight` - the envelope is ADDITIVE and survives a
    # zero weight untouched - so the veto has to reach every one of the three.
    # `test_a_vetoed_method_is_silenced_in_its_own_field` is the mechanism;
    # this is the declaration that turns it on.
    assert method.vetoed_suffixes == ("res_s", "gen_a", "gen_b")
    # Nothing optional: the residual is computed from the two frames the
    # method was handed, so there is no deployment in which it is missing.
    assert method.requirements() == []


# ---------- endpoint exactness ----------

def test_endpoint_exactness_at_both_ends():
    previous, following = blob(20, 14), blob(20, 26, amplitude=60.0)
    motion = pair_with(numpy.full(SHAPE, RESIDUAL_CAP_PERCENT), flow=uniform_flow(12.0, -7.0))
    method = ResidualAdvectionMethod()
    # Exact equality, not approximate: at a retrieved instant the retrieved
    # frame is what shows, untouched.
    assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
    assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)


def test_endpoint_exactness_is_the_envelope_not_the_guards():
    # The two `t <= 0` / `t >= 1` guards would satisfy the test above even if
    # the residual were delivered on an envelope that does not vanish - the
    # display would then JUMP by the residual the instant playback left a
    # retrieved frame. So the composite is asked just inside both ends, where
    # only `4t(1 - t) -> 0` can save it.
    previous, following = blob(20, 20), blob(20, 20, amplitude=40.0)
    motion = pair_with(numpy.full(SHAPE, RESIDUAL_CAP_PERCENT))
    method = ResidualAdvectionMethod()
    for fraction in (1e-6, 1.0 - 1e-6):
        drawn = method.composite(previous, following, motion, fraction)
        truth = previous if fraction < 0.5 else following
        # A constant envelope would put `RESIDUAL_GAIN * 50 = 6.25` percent
        # here; the envelope's own value at 1e-6 is 4e-6.
        assert numpy.max(numpy.abs(drawn - truth)) < 1e-3


def test_with_no_residual_the_composite_is_the_baseline_s_bit_for_bit():
    # The controlled comparison the bench is for: with the term switched off
    # this method is not "close to" the baseline, it IS the baseline, so any
    # difference a reader sees is the residual and nothing else.
    previous, following = blob(20, 14), blob(20, 26)
    motion = PairMotion(
        flow01=uniform_flow(6.0, 0.0), flow10=uniform_flow(-6.0, 0.0),
        confidence=numpy.ones(SHAPE), support=numpy.ones(SHAPE),
        advect_weight=numpy.full(SHAPE, 0.6),
    )
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert numpy.array_equal(
            ResidualAdvectionMethod().composite(previous, following, motion, fraction),
            BaselineMethod().composite(previous, following, motion, fraction),
        )


# ---------- the residual itself ----------

def test_a_pure_translation_leaves_no_residual():
    # Nothing developed, so there is nothing for this method to add. Checked
    # against the flow that actually generated the pair, so the warp is exact
    # and the answer is exactly zero rather than nearly: a residual defined
    # with the wrong sign or the wrong frame of reference (warping `previous`
    # forward instead of `following` back) reports the full translation
    # difference here instead.
    previous = blob(20, 14)
    following = blob(20, 22)
    residual = _computed_residual(previous, following, uniform_flow(8.0, 0.0))
    interior = residual[8:-8, 8:-8]
    assert numpy.max(numpy.abs(interior)) < 1e-9
    # And through the real derivation, where the flow is DIS' rather than
    # given: still negligible beside the field it is added to.
    motion = ResidualAdvectionMethod().motion(context([previous, following]))[0]
    assert motion.diagnostics["residual_mean_abs"] < 1.0


def test_growth_in_place_leaves_a_residual_that_is_non_zero_and_positive():
    # Cloud that grows where it stands: the same field everywhere plus 20
    # percent. No gradient changes, so no displacement can explain any of it
    # and the residual has to carry the whole 20 - which is the number
    # asserted, not merely its sign, because a residual scaled by anything
    # (an envelope left in, a factor of t) would still be positive.
    previous = blob(20, 20, amplitude=40.0)
    following = previous + 20.0
    motion = ResidualAdvectionMethod().motion(context([previous, following]))[0]
    residual = motion.extra["res_s"]
    assert (residual > 0.0).all()
    assert residual == pytest.approx(20.0, abs=0.05)
    assert motion.diagnostics["residual_mean_abs"] == pytest.approx(20.0, abs=0.05)
    assert motion.diagnostics["residual_p95"] == pytest.approx(20.0, abs=0.05)
    # Decay is the same statement with the sign turned over, which is the half
    # a test on growth alone cannot tell apart from a magnitude.
    decaying = ResidualAdvectionMethod().motion(context([following, previous]))[0]
    assert decaying.extra["res_s"] == pytest.approx(-20.0, abs=0.05)


def test_the_residual_is_delivered_front_loaded_and_only_between_the_endpoints():
    # What the reader actually sees: at the midpoint of a pair that grew in
    # place, more of the growth has been delivered than a dissolve would have
    # delivered - and still not more than the pair itself contains.
    previous = blob(20, 20, amplitude=40.0)
    following = previous + 20.0
    motion = ResidualAdvectionMethod().motion(context([previous, following]))[0]
    drawn = ResidualAdvectionMethod().composite(previous, following, motion, 0.5)
    crossfade = 0.5 * previous + 0.5 * following
    # At the midpoint the envelope is 1, so the term is exactly the gain times
    # the residual and the whole construction is checkable by arithmetic.
    assert drawn - crossfade == pytest.approx(RESIDUAL_GAIN * 20.0, abs=0.05)
    assert (drawn <= numpy.maximum(previous, following) + 1e-9).all()
    assert (drawn >= numpy.minimum(previous, following) - 1e-9).all()


def test_the_negated_residual_is_the_same_field_with_its_sign_turned_over():
    # The control has to be the residual's negation and nothing else, or it
    # is not a control. (It is the back-loaded delivery of the same change.)
    frames = [blob(20, 20, amplitude=40.0), blob(20, 20, amplitude=40.0) + 20.0]
    forward = ResidualAdvectionMethod().motion(context(frames))[0]
    negated = ResidualAdvectionMethod(negate_residual=True).motion(context(frames))[0]
    assert numpy.array_equal(negated.extra["res_s"], -forward.extra["res_s"])


# ---------- boundedness ----------

def test_the_stored_residual_is_capped():
    # A full-scale change is representable in these fields (0 to 100 percent
    # is a real thing for cloud), so the cap is a real fence and not a
    # formality: without it a single wrong vector at a cloud edge contributes
    # a full-scale correction.
    previous = numpy.zeros(SHAPE)
    following = numpy.full(SHAPE, 100.0)
    residual = _computed_residual(previous, following, uniform_flow(0.0, 0.0))
    assert numpy.max(numpy.abs(residual)) == pytest.approx(RESIDUAL_CAP_PERCENT)
    assert RESIDUAL_CAP_PERCENT < 100.0


def test_the_drawn_field_stays_inside_the_percent_scale():
    # Even handed a residual at the cap on top of a field already at the top
    # of the scale - which the derive cannot produce, but a corrupt stored
    # field could - nothing outside [0, 100] reaches the display.
    previous = numpy.full(SHAPE, 100.0)
    following = numpy.full(SHAPE, 100.0)
    high = ResidualAdvectionMethod().composite(
        previous, following, pair_with(numpy.full(SHAPE, 10 * RESIDUAL_CAP_PERCENT)), 0.5
    )
    low = ResidualAdvectionMethod().composite(
        numpy.zeros(SHAPE), numpy.zeros(SHAPE), pair_with(numpy.full(SHAPE, -10 * RESIDUAL_CAP_PERCENT)), 0.5
    )
    assert high.max() <= 100.0 and high.min() >= 0.0
    assert low.max() <= 100.0 and low.min() >= 0.0


def test_the_delivered_fraction_never_leaves_the_two_retrieved_values():
    # The bound the gain exists to hold: with the residual equal to the pair's
    # own change (which is what it IS when nothing moved), the drawn value is
    # `previous + f(t) * (following - previous)` and `f` must stay in [0, 1]
    # at every t, or the display would be showing cloud neither frame has.
    previous = numpy.full(SHAPE, 20.0)
    following = numpy.full(SHAPE, 80.0)
    change = following - previous
    for step in range(0, 101):
        fraction = step / 100.0
        drawn = ResidualAdvectionMethod().composite(previous, following, pair_with(change), fraction)
        delivered = (drawn - previous) / change
        assert delivered.min() >= -1e-12 and delivered.max() <= 1.0 + 1e-12, fraction
    assert RESIDUAL_GAIN <= 0.25  # the ceiling the algebra above rests on


# ---------- the veto ----------

def test_a_vetoed_method_is_silenced_in_its_own_field():
    # This method's term survives a zero `advect_weight` untouched - it is
    # additive, not mixed on the weight - so the veto has to reach `res_s`.
    # `vetoed_suffixes` is what makes that happen; this is the proof it does,
    # on the real class rather than on the stand-in in test_cloud_motion.
    from ingest.derive.cloud_motion import _derive_one_method

    generator = numpy.random.default_rng(11)
    frames = [generator.uniform(0.0, 100.0, (32, 32)) for _ in range(4)]
    variable = MethodContext(
        variable="total_cloud", frames=frames, indices=(0, 1, 2, 3), interval_seconds=INTERVAL
    )
    pairs = [(None, None, frames[index], frames[index + 1]) for index in range(3)]
    fields, _ = _derive_one_method(ResidualAdvectionMethod(), variable, pairs)

    assert float(numpy.max(fields["advect_weight"])) == 0.0, "the veto did not fire; this test proves nothing"
    for suffix in ("res_s", "gen_a", "gen_b"):
        assert float(numpy.max(numpy.abs(fields[suffix]))) == 0.0, (
            f"a vetoed pair kept its {suffix}: the term would draw at full strength on exactly "
            "the pairs the derive has just judged unfit"
        )


def test_the_residual_field_is_not_vacuously_zero_before_the_veto():
    # The guard on the test above: on frames the veto does NOT fire for, the
    # stored field has to be substantial, or the assertion there would pass
    # for a method that never wrote anything.
    frames = [blob(20, 20, amplitude=40.0), blob(20, 20, amplitude=40.0) + 20.0]
    motion = ResidualAdvectionMethod().motion(context(frames))[0]
    assert float(numpy.max(numpy.abs(motion.extra["res_s"]))) > 10.0


# ---------- the measurement gate ----------

def test_the_residual_is_applied_only_where_it_reconstructs_better():
    # Cloud that develops FASTER EARLY than a dissolve would draw it: the
    # front-loaded delivery is the truth here, so the gate must switch the
    # residual on and publish the numbers that say why.
    method, notes = ResidualAdvectionMethod().configure(context(developing(lambda t: 2 * t - t * t)))
    assert notes["residual_applied"] is True
    assert method.use_residual is True
    assert notes["held_out_improvement_with_residual"] > notes["held_out_improvement_without_residual"]
    assert notes["held_out_improvement_with_residual"] > notes["held_out_improvement_with_negated_residual"]
    assert notes["residual_cap_percent"] == RESIDUAL_CAP_PERCENT
    assert notes["residual_gain"] == RESIDUAL_GAIN
    # Published either way, so "the residual helped" is checkable rather than
    # asserted - including the statistic the bench's own veto reads.
    for name in (
        "held_out_ssim_with_residual",
        "held_out_ssim_without_residual",
        "held_out_ssim_with_negated_residual",
        "held_out_improvement_over_reversed_flow_with_residual",
        "held_out_improvement_over_reversed_flow_without_residual",
    ):
        assert notes[name] is not None


def test_the_negated_control_is_scored_and_published():
    # The control the method could not honestly ship without: negating the
    # residual delivers the same change back-loaded instead of front-loaded,
    # which is an equally admissible shape a priori. On data that really is
    # front-loaded the negation must come out WORSE than doing nothing, or
    # the improvement was about having a bump rather than about the residual.
    #
    # Note what this can and cannot be: the composite is affine in `s` and MAE
    # is convex, so "beats off" already implies "beats its negation" except at
    # the clip. The number is still scored and published, because it is what
    # lets a reader check the sign carries the improvement - and it is
    # asserted here in the direction the algebra predicts, so a residual
    # applied with the wrong sign would fail this test rather than pass it.
    _, notes = ResidualAdvectionMethod().configure(context(developing(lambda t: 2 * t - t * t)))
    assert notes["held_out_improvement_with_negated_residual"] < notes["held_out_improvement_without_residual"]
    assert notes["held_out_ssim_with_negated_residual"] < notes["held_out_ssim_without_residual"]


def test_a_residual_that_reconstructs_worse_is_switched_off():
    # Cloud that develops faster LATE. The front-loaded delivery is then the
    # wrong shape, so the term must be refused - and refused despite the fact
    # that a reader watching one pair would see it "do something".
    frames = developing(lambda t: t * t)
    method, notes = ResidualAdvectionMethod().configure(context(frames))
    assert notes["held_out_improvement_with_residual"] < notes["held_out_improvement_without_residual"]
    assert notes["residual_applied"] is False
    assert method.use_residual is False
    # And with it off, this method draws exactly what the baseline draws.
    motion = method.motion(context(frames))[0]
    assert numpy.array_equal(motion.extra["res_s"], numpy.zeros(SHAPE))
    assert numpy.array_equal(
        method.composite(frames[0], frames[1], motion, 0.5),
        BaselineMethod().composite(frames[0], frames[1], motion, 0.5),
    )


def test_nothing_that_can_be_measured_means_the_residual_is_off():
    # Two frames cannot hold one out, so there is no measurement, and an
    # unmeasured optional term is not applied. An absent score is never read
    # as a passing one.
    frames = developing(lambda t: 2 * t - t * t)[:2]
    method, notes = ResidualAdvectionMethod().configure(context(frames))
    assert notes["residual_applied"] is False
    assert notes["held_out_improvement_with_residual"] is None


def test_the_diagnostics_describe_the_field_that_was_stored():
    frames = developing(lambda t: 2 * t - t * t)
    for motion in ResidualAdvectionMethod().motion(context(frames)):
        magnitude = numpy.abs(motion.extra["res_s"])
        assert motion.diagnostics["residual_mean_abs"] == pytest.approx(float(numpy.mean(magnitude)))
        assert motion.diagnostics["residual_p95"] == pytest.approx(float(numpy.percentile(magnitude, 95)))
        assert 0.0 <= motion.diagnostics["residual_capped_fraction"] <= 1.0


# ---------- the stored envelope (the thing the shader actually reads) ----------

def test_the_stored_envelope_is_the_contract_s_own_arithmetic():
    # The contract fixes the wire: `gen_a = 4 * RESIDUAL_GAIN * res_s` and
    # `gen_b = 0`, so `t(1-t)(a + b t)` is exactly the `gain * 4t(1-t) * s`
    # every bound in this module is derived for. Asserted against the STORED
    # fields, because those two floats are all the client is handed - it has
    # no dense flow of its own and cannot recompute the residual.
    frames = [blob(20, 20, amplitude=40.0), blob(20, 20, amplitude=40.0) + 20.0]
    motion = ResidualAdvectionMethod().motion(context(frames))[0]
    assert numpy.allclose(motion.extra["gen_a"], 4.0 * RESIDUAL_GAIN * motion.extra["res_s"])
    # Zero, not absent: the non-generative sibling's envelope is the symmetric
    # parabola with no timing term, and the client must read a real zero
    # rather than fall back to something.
    assert "gen_b" in motion.extra
    assert numpy.array_equal(motion.extra["gen_b"], numpy.zeros_like(motion.extra["res_s"]))


def test_the_composite_evaluates_the_STORED_parabola_not_the_residual():
    # Why this matters: if the composite recomputed the envelope from `res_s`
    # the bench would be ranking a picture the shader cannot draw, and the
    # menu's scores would be about a different construction than the map. So
    # a pair whose stored envelope is zero must draw the baseline however
    # large its `res_s` is, and a pair whose stored envelope is non-zero must
    # draw it even with `res_s` absent.
    previous, following = blob(20, 20), blob(20, 20, amplitude=40.0)
    method = ResidualAdvectionMethod()
    baseline_pair = pair_with(numpy.full(SHAPE, RESIDUAL_CAP_PERCENT))
    baseline_pair.extra["gen_a"] = numpy.zeros(SHAPE)
    assert numpy.array_equal(
        method.composite(previous, following, baseline_pair, 0.5),
        BaselineMethod().composite(previous, following, baseline_pair, 0.5),
    )

    envelope_only = pair_with(numpy.zeros(SHAPE))
    envelope_only.extra.pop("res_s")
    envelope_only.extra["gen_a"] = numpy.full(SHAPE, 8.0)
    drawn = method.composite(previous, following, envelope_only, 0.5)
    plain = BaselineMethod().composite(previous, following, envelope_only, 0.5)
    # t(1-t)(a + b t) at t = 0.5 with a = 8, b = 0 is 0.25 * 8 = 2.0.
    assert numpy.allclose(drawn - plain, 2.0)


def test_the_stored_b_coefficient_tilts_the_envelope_in_time():
    # `gen_b` is zero for this method, but the SHADER contract is the full
    # parabola and the generative sibling stores a non-zero b on the same
    # wire. Pinned here so the two coefficients cannot quietly become one:
    # t(1-t)(a + b t) at t = 0.25 is 0.1875(a + 0.25 b), at t = 0.75 it is
    # 0.1875(a + 0.75 b) - equal areas, different times.
    previous = numpy.full(SHAPE, 30.0)
    following = numpy.full(SHAPE, 30.0)
    method = ResidualAdvectionMethod()
    tilted = pair_with(numpy.zeros(SHAPE))
    tilted.extra["gen_a"] = numpy.zeros(SHAPE)
    tilted.extra["gen_b"] = numpy.full(SHAPE, 16.0)
    early = method.composite(previous, following, tilted, 0.25)
    late = method.composite(previous, following, tilted, 0.75)
    assert numpy.allclose(early - 30.0, 0.25 * 0.75 * (0.0 + 16.0 * 0.25))
    assert numpy.allclose(late - 30.0, 0.75 * 0.25 * (0.0 + 16.0 * 0.75))
    assert float(late.mean()) > float(early.mean())
    # And it still vanishes at both retrieved instants, whatever b says.
    assert numpy.array_equal(method.composite(previous, following, tilted, 0.0), previous)
    assert numpy.array_equal(method.composite(previous, following, tilted, 1.0), following)
