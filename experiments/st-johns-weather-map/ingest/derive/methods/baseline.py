"""The construction the map draws with by default: advection along derived motion.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    STEERING_LEVEL_BY_VARIABLE,
    _consistency,
    _dis_flow,
    _display_weight,
    _prior_corrected,
    _steering_prior,
    _supported_flow,
    _warp_nearest,
)
from ingest.derive.methods.contract import InterpolationMethod, MethodContext, PairMotion
from ingest.derive.methods.harness import _interpolation_skill, admit, admit_reasons

#: The line every method's science note ends on. HRDPS and GFS both publish a
#: field called total cloud and they are not the same quantity; a reader
#: comparing the two layers is owed that sentence wherever a method is
#: described.
TCDC_NOTE = (
    "HRDPS TCDC is opacity-weighted, NT = TCC[1 - exp(-0.1(W3+W4))] (ECCC WEonG technote v2.4.1 "
    "sec 7.9); GFS TCDC is a geometric max-random fraction (ccpp-physics gethml). Not the same "
    "quantity."
)


def _raw_pair_motion(context: MethodContext, position: int) -> tuple[Any, Any, Any, Any]:
    """``(flow01, flow10, confidence, support)`` of one pair from the imagery alone, memoised.

    DIS both ways, relative forward-backward consistency, and the
    confidence-weighted fill with its support field - everything a pair's
    motion is before any optional ingredient touches it. Memoised in
    ``context.cache`` under the pair's own frame indices, because every
    method on the bench that shares the baseline's derivation (the residual
    and its generative sibling settle several options each, the harness
    scores each option over a dozen hold-outs, and the fixed advection
    control is this exact computation) would otherwise pay for the same
    optical flow again and again. Nothing here depends on the method's
    options, so the memo is exact, not approximate. The arrays are shared by
    reference and never modified in place by any consumer; a consumer that
    needs to change one copies it (``_prior_corrected`` does).
    """
    key = ("dis", context.indices[position], context.indices[position + 1])
    cached = context.cache.get(key)
    if cached is not None:
        return cached
    previous = context.frames[position]
    following = context.frames[position + 1]
    raw01 = _dis_flow(previous, following)
    raw10 = _dis_flow(following, previous)
    agreed = _consistency(raw01, raw10)
    flow01, support = _supported_flow(raw01.astype("float64"), agreed)
    flow10, _ = _supported_flow(raw10.astype("float64"), agreed)
    context.cache[key] = (flow01, flow10, agreed, support)
    return context.cache[key]


class BaselineMethod(InterpolationMethod):
    """Advection along the pair's own derived motion, with a support-gated weight.

    Relative forward-backward consistency, neighbourhood fill with a support
    field, a display weight that is the support over its floor and nothing
    else, and the optional model steering prior. The two frames are warped
    toward each other along the pair's own flow and mixed linearly by ``t``.

    Until ``cloud-motion-bench-v6`` the weight was also multiplied by a
    "development agreement": wherever the two half-warps disagreed the
    display fell back to a cross-dissolve, on the reasoning that cloud grew
    or decayed in place and no motion field can move what was never
    somewhere else. That reasoning did not survive being measured, and the
    construction with the agreement dropped (then a separate method,
    ``full-advection``) is now this one. The measurements are kept here so
    the decision stays checkable.

    MEASURED on the live cycle of 2026-09-01, same held-out frames, same
    downstream, HRDPS total_cloud, "shipped" being the agreement-gated
    weight and "this" the support-only weight:

        metric                                shipped   this method
        improvement over crossfade  (fixed)    0.1341      0.1527
        midpoint MAE, percent       (fixed)   19.0510     18.6408
        midpoint SSIM               (fixed)    0.3073      0.3072
        improvement over reversed flow        0.2314      0.2898

    READ THE LAST ROW WITH CARE, AND DO NOT RANK METHODS ON IT. The
    reversed-flow control is the same construction with its motion negated,
    so the control MOVES WITH THE METHOD: an agreement-gated weight still
    dissolves wherever agreement is low and is therefore less damaged by the
    reversal, while a support-only weight advects at full strength in the
    wrong direction and is very badly damaged. That inflates the apparent
    lead more than twofold - +0.0584 against a moving control, +0.0186
    against a fixed one. The reversed-flow score answers "does this
    method's motion carry information", which is what it was built for and
    what ``MIN_HELD_OUT_IMPROVEMENT`` gates on; it does not answer "which
    method draws the better picture". Since bench-v6 every ``configure``
    admits an optional term on fixed controls only (``harness.admit``).

    A mean-error win is also exactly what a blurrier construction produces,
    so the fixed-control table alone would not settle it: pySTEPS measures
    S-PROG cutting MAE ~40 percent by scale filtering, and Ebert (2008) and
    Wernli et al. (2008) both give worked examples where the mean-error
    winner is the worst picture. So the check that matters is the one
    Radanovics et al. (GMD 18, 2025) prescribe - score cells that GREW and
    cells that DECAYED separately, since "conventional pixel-based metrics
    obscure these fundamental development prediction failures" - plus a
    sharpness ratio, mean |grad| of the reconstruction over mean |grad| of
    the held-out truth, where 1.0 is as sharp as reality:

        layer                    variant     MAE grew  MAE decayed  sharpness
        eccc-hrdps total_cloud   shipped       26.49      23.35       0.775
                                 this          24.91      22.40       0.853
        noaa-gfs   total_cloud   shipped       15.72      16.04       0.790
                                 this          14.26      14.18       0.867
        noaa-gfs   cloud_middle  shipped       18.17      17.66       0.778
                                 this          14.99      15.50       0.862

    Better on cloud that grew, better on cloud that decayed, and LESS
    blurred, on every layer. The blur hypothesis is refused by its own
    diagnostic: the construction with the lowest error is also the sharpest.
    The development test was not protecting growth and decay - it was
    suppressing advection where the FLOW was imperfect, which on this coast
    is not the same thing.

    Why this coast in particular. Offshore Newfoundland roughly 75 percent of
    fog is warm-advection fog, and it has NO diurnal cycle in frequency of
    occurrence (21 years of Hibernia platform observations, Weather and
    Forecasting 35(2), 2020) - radiation fog and burn-off stratus both carry a
    strong diurnal signature by construction, so its absence is close to a
    direct measurement that this cloud arrives already formed rather than
    being made and destroyed in place. C-FOG (BAMS 102(2), 2021), whose
    supersite sat at Ferryland on this peninsula, found a genuine orographic
    in-place component on the higher ground - so development here is real
    but local, and suppressing advection everywhere to represent it is the
    wrong trade.

    What this method is NOT. It does not represent growth and decay at all;
    it only stops pretending that a cross-dissolve represents them. Cloud
    that appeared or vanished in place is delivered linearly along the
    trajectory. The physically grounded treatment is an additive residual -
    NowcastNet's ``s`` in ``dx/dt + (v.grad)x = s`` (Nature 619, 2023),
    computed rather than learned because both endpoints are held - which is
    ``residual-advection``'s job.
    """

    id = "baseline"
    # Named for what it draws, not for its place in the bench. "Baseline"
    # alone read as "no motion" in the menu, and a summary that led on the
    # word "dissolving" made the shipped advection look like a cross-fade.
    title = "Advection along derived motion"
    summary = (
        "The construction the map draws with by default. Both frames are warped toward each "
        "other along the pair's own dense flow, following C1 trajectories fitted through the "
        "neighbouring published frames; every cell with a trustworthy motion vector behind it "
        "advects at full strength, and only cells whose fill nothing trustworthy stood behind "
        "fall back to a dissolve. Where the model publishes the stratum's steering wind it may "
        "fill what the imagery could not read, if the held-out score says it helps."
    )
    plain = "We work out how the cloud moved between the two hourly pictures and slide it along that path."
    gap = "Cloud that appeared or vanished in place fades evenly; that is most Avalon fog."
    notes = (
        "Dense optical flow (OpenCV DIS, Kroeger et al. 2016) both ways; forward-backward "
        "consistency (Sundaram, Brox & Keutzer 2010); normalized-convolution fill; C1 cubic "
        "Hermite trajectories through neighbouring frames. Advection correction: Anagnostou & "
        "Krajewski 1999 (JTECH 16); pySTEPS advection_correction; Shapiro et al. 2010 (JAS 67). "
        "Steering wind fill at 850/700/500 hPa from the same run. Development test dropped "
        "2026-09-01: measured worse on growth, decay and sharpness on every layer (Radanovics "
        "et al. 2025 GMD 18). " + TCDC_NOTE
    )
    shader = "hermite"

    #: Set by the derive when the steering prior earned its place for this
    #: variable; the harness constructs the method itself, so this is an
    #: instance flag rather than a class one.
    def __init__(self, *, use_prior: bool = False) -> None:
        self.use_prior = use_prior

    def configure(self, context: MethodContext) -> tuple[InterpolationMethod, dict[str, Any]]:
        """Does the model steering wind actually help? Measured, not assumed.

        The held-out reconstruction is scored with the prior and without it,
        and the prior is applied only if ``harness.admit`` says the version
        with it is the better picture on the FIXED controls - a plain
        crossfade and a plain advection of the same frames - on mean error,
        structural similarity and sharpness together. Every number goes to
        provenance either way, including the reversed-flow ratio that used
        to decide and now only informs, so "the wind helped" is checkable.
        """
        # `type(self)` rather than the class name: a subclass that keeps this
        # derivation and changes only the composite (the bench's point) must
        # score ITS OWN construction here, or it would decide the prior's fate
        # on the baseline's numbers. For BaselineMethod itself this is exactly
        # what it always did.
        build = type(self)
        if context.dataset is None:
            return build(use_prior=False), {"applied": False}
        without = _interpolation_skill(
            context.frames,
            method=build(use_prior=False),
            variable=context.variable,
            interval_seconds=context.interval_seconds,
            indices=context.indices,
            cache=context.cache,
        )
        with_prior = _interpolation_skill(
            context.frames,
            method=build(use_prior=True),
            dataset=context.dataset,
            variable=context.variable,
            interval_seconds=context.interval_seconds,
            indices=context.indices,
            cache=context.cache,
        )
        use_prior = admit(with_prior, without)
        read = lambda skill, name: skill[name] if skill else None  # noqa: E731
        notes = {
            "applied": bool(use_prior),
            "level_hpa": STEERING_LEVEL_BY_VARIABLE.get(context.variable),
            # The gate's own numbers: improvement over the FIXED crossfade.
            "held_out_improvement_with_prior": read(with_prior, "improvement_over_crossfade"),
            "held_out_improvement_without_prior": read(without, "improvement_over_crossfade"),
            "held_out_improvement_over_advection_with_prior": read(with_prior, "improvement_over_advection"),
            "held_out_improvement_over_advection_without_prior": read(without, "improvement_over_advection"),
            "held_out_ssim_with_prior": read(with_prior, "midpoint_ssim"),
            "held_out_ssim_without_prior": read(without, "midpoint_ssim"),
            "held_out_sharpness_ratio_with_prior": read(with_prior, "midpoint_sharpness_ratio"),
            "held_out_sharpness_ratio_without_prior": read(without, "midpoint_sharpness_ratio"),
            # The moving control, published because the bench's veto reads it
            # and a provenance reader that predates bench-v6 looks for it. It
            # no longer decides anything here.
            "held_out_improvement_over_reversed_flow_with_prior": read(with_prior, "improvement_over_reversed_flow"),
            "held_out_improvement_over_reversed_flow_without_prior": read(without, "improvement_over_reversed_flow"),
            "admission": admit_reasons(with_prior, without),
            "skill": with_prior if use_prior else without,
        }
        return build(use_prior=use_prior), notes

    def motion(self, context: MethodContext) -> list[PairMotion]:
        import numpy  # noqa: PLC0415

        results: list[PairMotion] = []
        for position in range(len(context.frames) - 1):
            previous = context.frames[position]
            flow01, flow10, agreed, support = _raw_pair_motion(context, position)
            carried = 0.0
            if self.use_prior and context.dataset is not None:
                pair_indices = (context.indices[position], context.indices[position + 1])
                prior = _steering_prior(
                    context.dataset,
                    context.variable,
                    pair_indices,
                    context.interval_seconds,
                    numpy.asarray(previous).shape,
                )
                if prior is not None:
                    flow01, carried = _prior_corrected(flow01, support, prior)
                    flow10, _ = _prior_corrected(flow10, support, -prior)
            results.append(
                PairMotion(
                    flow01=flow01,
                    flow10=flow10,
                    confidence=agreed,
                    support=support,
                    # Support over its floor, and nothing else: a cell with a
                    # trustworthy vector behind it advects at full strength.
                    # See the class docstring for the measurement that
                    # removed the agreement factor.
                    advect_weight=_display_weight(support),
                    diagnostics={"prior_weight_carried": carried},
                )
            )
        return results

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        import numpy  # noqa: PLC0415

        first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
        second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
        if t <= 0.0:
            return first
        if t >= 1.0:
            return second
        flow = numpy.asarray(motion.flow01, dtype="float64")
        warped = (1.0 - t) * _warp_nearest(first, t * flow) + t * _warp_nearest(second, -(1.0 - t) * flow)
        plain = (1.0 - t) * first + t * second
        return plain + motion.advect_weight * (warped - plain)
