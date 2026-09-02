"""Everything advection fails to explain, computed from the two retrieved frames and added back.

One plugin, one module. See ``ingest.derive.methods`` for the contract.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import _warp_nearest
from ingest.derive.methods.baseline import TCDC_NOTE, BaselineMethod
from ingest.derive.methods.contract import (
    InterpolationMethod,
    MethodContext,
    PairMotion,
    Requirement,
)
from ingest.derive.methods.harness import _interpolation_skill, admit, admit_reasons

#: The largest per-cell residual, in cloud percent, that is treated as
#: development rather than as a flow blunder.
#:
#: A cap is not optional here and it cannot be left at the structural bound.
#: Both terms of ``s = warp(following, -flow01) - previous`` are retrieved
#: percent values, so ``|s| <= 100`` holds by construction and a cap of 100
#: would be no cap at all. What the cap is actually for is the case the warp
#: manufactures: at a sharp cloud boundary a flow that is one cell wrong
#: subtracts clear sky from solid overcast and reports a full-scale residual
#: for a cell where nothing developed.
#:
#: Measured on HRDPS ``total_cloud`` over the Avalon crop (2026-09-01 00Z
#: run, f005-f009, 2.5 km, 148x149 cells, four pairs): |s| median 2.5, mean
#: 9.9, p90 30.6, p95 46.2, p99 75.6, max 100.0 percent, with 4.2% of cells
#: above 50. So the field really does run to full scale, and the cap has to
#: be chosen rather than inherited.
#:
#: What decided 50 is that it costs nothing. Held-out midpoint MAE against
#: the cap, same run, gain as below: 14.277 at cap 15, 14.228 at 25, 14.186
#: at 40, 14.171 at 50, 14.162 at 75, 14.164 uncapped - flat from 50 upward
#: and falling away below it, because the large residuals are where the
#: development actually is. Fifty is therefore the tightest fence that has
#: not started to cut into the signal: it bounds one bad vector's
#: contribution to an eighth of half scale and leaves the measurement where
#: it would have been with no cap at all.
RESIDUAL_CAP_PERCENT = 50.0

#: The residual's gain: a structural ceiling, and a measured value under it.
#:
#: THE CEILING. The baseline already delivers the residual LINEARLY - the
#: forward warp carries ``previous`` with no development, the backward warp
#: carries ``following`` with all of it, and mixing them by ``t`` puts
#: ``previous + t*s`` on the display. This term adds ``gain * 4t(1-t) * s``
#: on top, so the delivered fraction of the pair's own change is
#:
#:     f(t) = t + 4 * gain * t * (1 - t),      f(0) = 0, f(1) = 1.
#:
#: ``f(t) <= 1`` on [0, 1] rearranges to ``(4*gain*t - 1)(t - 1) >= 0``, which
#: holds for every ``t < 1`` exactly when ``gain <= 1/4``. At ``gain = 1/4``,
#: ``f(t) = 2t - t^2``: monotone, and confined to [0, 1]. So a quarter is the
#: largest gain at which the drawn value stays inside the interval the two
#: retrieved values bracket - it cannot show cloud that is in neither frame,
#: nor remove cloud that is in both. Anything above it buys strength by
#: leaving that interval, which is the one thing this method may not do.
#:
#: THE VALUE, half of the ceiling, and measured rather than chosen. Held-out
#: reconstruction on HRDPS ``total_cloud`` over the Avalon crop (2026-09-01
#: 00Z, f005-f009), midpoint MAE percent and SSIM against the frame that was
#: hidden:
#:
#:     gain     0 (off)   1/16     1/8      3/16     1/4
#:     MAE      14.381    14.248   14.171   14.138   14.149
#:     SSIM     0.4073    0.4100   0.4101   0.4086   0.4060
#:
#: MAE keeps falling almost to the ceiling while SSIM turns over after 1/8.
#: That divergence is the signature the research note warns about at §7: a
#: reconstruction can always lower MAE by smearing more of the change over
#: the middle of the interval, and structural similarity is what catches it.
#: An eighth is where both agree, and it is half the bound rather than at it,
#: so the display is not sitting on the edge of its own admissibility.
RESIDUAL_GAIN = 0.125


def _computed_residual(previous: Any, following: Any, flow01: Any) -> Any:
    """``s = warp(following, -flow01) - previous``: the unexplained change, in percent.

    This is NowcastNet's ``s`` in ``dx/dt + (v.grad)x = s`` (Zhang et al.,
    Nature 619, 2023) and Tatsubori et al.'s third flow channel ``dz``
    (ICASSP 2022, arXiv:2203.01277), with the one difference that decides
    whether this method is admissible at all: both of those LEARN it, because
    a nowcast has only one endpoint and the future is genuinely unknown. This
    experiment holds BOTH endpoints, so the same field is a subtraction.
    Nothing is predicted, nothing is diagnosed, nothing is generated - the
    residual is a measurement of how far the pair's own flow failed to carry
    one retrieved frame onto the other.

    Frame of reference matters and is chosen deliberately. ``following`` is
    warped BACKWARD onto ``previous``' grid, so ``s`` is expressed at the
    trajectory's START and the composite can add it with no displacement at
    all. The alternative - warping ``previous`` forward and differencing
    against ``following`` - expresses the residual at the trajectory's END,
    which for a term drawn at every ``t`` in between would need a second
    resampling to place: the chained resampling NowcastNet abandoned.

    Exactly one resampling is spent here, on ``following``, and it is spent
    on the raw retrieved frame rather than on an already-warped one.
    """
    import numpy  # noqa: PLC0415

    first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
    second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
    flow = numpy.asarray(flow01, dtype="float64")
    return numpy.clip(
        _warp_nearest(second, -flow) - first, -RESIDUAL_CAP_PERCENT, RESIDUAL_CAP_PERCENT
    )


class ResidualAdvectionMethod(BaselineMethod):
    """The computed growth-and-decay residual, added back where it was measured.

    Growth and decay in place is the acknowledged limit of every advection
    method: it violates brightness constancy, so no flow field can express
    it. The nowcasting literature answers it with a learned intensity
    residual - NowcastNet's evolution network emits ``s`` beside the motion
    field, and Tatsubori et al. carry an additive ``dz`` as a third flow
    channel, reporting up to 20% error reduction over linear interpolation on
    radar in exactly this two-endpoint setting.

    **We do not have to learn it.** With both endpoints retrieved,

        s = warp(following, -flow01) - previous

    is everything advection failed to explain, directly computed. The display
    is then the baseline's construction plus that residual, delivered on an
    envelope that vanishes at both ends:

        base(t)  = plain + advect_weight * (warped - plain)   # the baseline
        drawn(t) = base(t) + t(1 - t) * (a + b t)             # the STORED envelope
        a = 4 * gain * s,   b = 0                             # for this method

    The envelope's two coefficients are what is STORED and what is SERVED
    (``gen_a``, ``gen_b``, cloud percent), not the residual itself: the
    shader evaluates ``t(1-t)(a + b t)`` from the two stored fields and the
    Python composite evaluates the same stored parabola, so the bench ranks
    exactly what the map draws. For this method ``b`` is identically zero
    and ``a`` is the quarter-gain residual, so ``t(1-t)(a) = gain * 4t(1-t) *
    s`` as before; the generative sibling (``residual-generative``) fits
    ``(a, b)`` to a physics-timed target on the same wire. ``res_s`` stays
    stored as a diagnostic and is never served.

    MEASURED, AND AGAINST THE PLAN. Tatsubori et al. carry ``dz`` ALONG the
    trajectory - ``g(I, F) = sum_q (I^q + dz^q) w^q`` - and that was built
    first here, as ``warp(s, t * flow01)``. On HRDPS ``total_cloud`` over the
    Avalon (2026-09-01 00Z, f005-f009) it is the WORSE of the two placements
    at every gain tried, and above a gain of about an eighth it is worse than
    not applying the residual at all: at gain 1/4, midpoint MAE 14.57 and
    SSIM 0.402 carried, against 14.15 and 0.406 in place, on a residual-off
    baseline of 14.38 and 0.4073. The residual is therefore left where it was
    computed. Two reasons, and the second is the interesting one:

    - it removes a resampling. ``s`` is itself built from a warp, so carrying
      it resamples an already-resampled field, which is exactly the chained
      resampling NowcastNet abandoned and §6 of the research note names as a
      manufactured blur source.
    - on this coast much of what advection fails to explain is not travelling
      with the air. Cloud tied to the coastline, to the terrain and to the
      SST front forms and clears at fixed GROUND positions, and moving that
      correction downwind puts it where the weather is not. A residual is
      Lagrangian only where the development is; here it measurably is not.

    THE BOUNDS, which are the licence for this method:

    1. ``4t(1 - t)`` is zero at ``t = 0`` and ``t = 1``, so at every retrieved
       instant the retrieved frame is drawn untouched. Endpoint exactness is
       algebra here, not a clamp applied afterwards.
    2. The delivered fraction ``f(t) = t + 4*gain*t(1 - t)`` stays inside
       [0, 1] for every ``gain <= 1/4``, and the shipped gain is half of that
       (see ``RESIDUAL_GAIN``). Where nothing moved - which is where this
       term is largest, since ``s`` IS the change there - that makes the
       drawn value a convex combination of the two retrieved values at that
       cell, so the display cannot show cloud that is in neither frame nor
       clear sky where both are overcast. The residual RE-TIMES the pair's
       own change; it never invents one.
    3. ``s`` is capped at ``RESIDUAL_CAP_PERCENT`` so a single wrong vector at
       a cloud edge cannot contribute a full-scale correction, and the result
       is clipped to [0, 100] because these are percent fields.
    4. The term is applied per variable only where the held-out
       reconstruction says it helps, against BOTH the no-residual
       construction and the negated residual (``configure``), with all three
       numbers published either way.

    On the fourth: negating the residual delivers the same change back-loaded
    rather than front-loaded - an equally admissible shape a priori - so the
    control asks whether the residual's SIGN carries the improvement or only
    the presence of a mid-interval bump. ``configure`` says what that control
    can and cannot decide, which is less than it first appears and worth
    reading before relying on it.

    Also deliberate: this method is fenced by nothing that ``advect_weight``
    zeroes, which is why ``res_s``, ``gen_a`` and ``gen_b`` are all named in
    ``vetoed_suffixes``. Its term acts everywhere, including where advection
    worked - there ``s`` is close to zero on its own, which is the honest
    fence, and where the derive has judged the pair unfit to advect at all
    every stored field is zeroed with the weight.

    NON-GENERATIVE, and why. Under carve-out (d) a method may draw a value in
    neither frame if it is cited, bounded, gated on a fixed control,
    disclosed as GENERATED and switchable. This method does not need that
    licence: at ``gain <= 1/4`` the drawn value stays inside the bracket the
    two retrieved values form at every cell (bound 2 above), so nothing in
    neither frame is ever shown. It therefore stays ``generative = False``,
    survives the ``WEATHER_GENERATED_DISPLAY=off`` kill switch, and is the
    construction the generative sibling reduces to when its ingredient is
    absent or its option is refused.
    """

    id = "residual-advection"
    title = "Computed development residual (both endpoints)"
    plain = (
        "Same slide, plus we measure how much cloud formed or dissolved in place and draw that "
        "happening - here at a quarter of its strength, so nothing is drawn that is in neither "
        "picture."
    )
    gap = (
        "Cloud that forms and clears entirely inside one hour is invisible; delivery is timed by "
        "the measured residual alone, not by physics - the generative sibling adds the timing "
        "switches (humidity reaching saturation, rising air, daytime burn-off)."
    )
    notes = (
        "Computed residual s = warp(I1, backward) - I0: NowcastNet's source term in dx/dt + "
        "(v.grad)x = s (Zhang et al. 2023, Nature 619); Tatsubori et al. 2022 (arXiv:2203.01277) "
        "third flow channel; computed, not learned, because both endpoints are held. This entry "
        "is the non-generative quarter-gain form: gain <= 1/4 keeps every drawn value inside the "
        "bracket the two retrieved values form, so no timing switch is applied and nothing is "
        "generated. The generative sibling adds timing: humidity threshold crossing under GEM's "
        "own Sundqvist closure b = 1 - sqrt((1-U)/(1-U0)) (Sundqvist, Berge & Kristjansson 1989 "
        "MWR 117; RPN physics doc v3.6 sec 6.3/8.2), RH_crit ~0.94 at 2.5 km (Morcrette 2012); "
        "omega via d ln RH/dt = (omega/p)(1 - kappa L/(R_v T)); daytime dissipation acceleration "
        "(Ghonima et al. 2016 JAS; Pauli et al. 2022 QJRMS 148); scale-split lifetimes (Seed 2003 "
        "S-PROG; Bowler, Pierce & Seed 2006 QJRMS); spatially varying non-linear time weighting "
        "validated on GOES (Vandal & Nemani 2021 IEEE TNNLS, arXiv:1907.12013). Regime gate from "
        "motion-compensated lag-1 correlation (Bley, Deneke & Senf 2016 JAMC 55: ~30 min "
        "decorrelation for convective fields). Gated on fixed controls with sharpness and PSD "
        "ratio (Ravuri et al. 2021 Nature 597; Harris et al. 2001; Roberts & Lean 2008 FSS; "
        "Wernli et al. 2008 SAL). " + TCDC_NOTE
    )
    summary = (
        "The same two frames and the same derived motion, plus the one thing advection cannot "
        "express: the residual left when the following frame is warped backward onto the previous "
        "one is everything that grew or decayed in place rather than moved. Because both frames "
        "are retrieved, that field is computed rather than predicted or learned, and it is added "
        "back on an envelope that vanishes at both ends - so cloud that forms and clears in place "
        "does so on the display too, instead of being dissolved through, while every retrieved "
        "instant still shows its own retrieved frame untouched."
    )
    shader = "residual-advection"
    #: ``res_s``: the computed per-cell residual in cloud percent, expressed
    #: at the trajectory's start - a diagnostic, stored so the field the
    #: envelope was built from is auditable, never served. ``gen_a``/``gen_b``:
    #: the envelope coefficients the shader evaluates, ``t(1-t)(a + b t)`` in
    #: cloud percent. Stored rather than recomputed because the client has no
    #: dense flow of its own to warp `following` backward with.
    extra_suffixes = ("res_s", "gen_a", "gen_b")
    #: Fenced by neither ``advect_weight`` nor its inverse: the envelope term
    #: is additive and survives a zero weight untouched, so the veto has to
    #: reach every stored field. See ``InterpolationMethod.vetoed_suffixes``.
    vetoed_suffixes = ("res_s", "gen_a", "gen_b")

    def __init__(self, *, use_prior: bool = False, use_residual: bool = True, negate_residual: bool = False) -> None:
        super().__init__(use_prior=use_prior)
        self.use_residual = use_residual
        self.negate_residual = negate_residual

    def requirements(self) -> list[Requirement]:
        """Nothing. That is the point, and it is worth stating.

        Every other optional ingredient on this bench - a steering wind, an
        observed cloud top, the model's vertical velocity - can be absent
        from a deployment, and its method then reduces to something else. The
        residual is computed from the two frames the method was already
        handed, so it is available in every cycle that has a pair at all.
        """
        return []

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The baseline's derivation exactly, plus each pair's computed residual.

        The motion is deliberately untouched. The claim under test is about
        the COMPOSITE, so sharing the derivation with the baseline is what
        makes the comparison controlled rather than two changes at once.

        Stores the envelope the shader will evaluate: ``gen_a = 4 * gain *
        s`` and ``gen_b = 0``, so ``t(1-t)(gen_a + gen_b t)`` is exactly the
        ``gain * 4t(1-t) * s`` the docstring derives its bounds for.
        """
        import numpy  # noqa: PLC0415

        results = super().motion(context)
        for position, pair in enumerate(results):
            previous = context.frames[position]
            following = context.frames[position + 1]
            if self.use_residual:
                residual = _computed_residual(previous, following, pair.flow01)
                if self.negate_residual:
                    residual = -residual
            else:
                residual = numpy.zeros(numpy.asarray(previous).shape, dtype="float64")
            pair.extra["res_s"] = residual
            pair.extra["gen_a"] = 4.0 * RESIDUAL_GAIN * residual
            pair.extra["gen_b"] = numpy.zeros_like(residual)
            magnitude = numpy.abs(residual)
            pair.diagnostics["residual_mean_abs"] = float(numpy.mean(magnitude))
            pair.diagnostics["residual_p95"] = float(numpy.percentile(magnitude, 95))
            # How much of the field the cap actually held. A large number here
            # says the cap is doing structural work rather than trimming a
            # tail, which would mean it is set wrong for this variable.
            pair.diagnostics["residual_capped_fraction"] = float(
                numpy.mean(magnitude >= RESIDUAL_CAP_PERCENT - 1e-9)
            )
        return results

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        """The ``residual-advection`` shader branch, in Python. Keep them in step.

        The GLSL computes the same thing from the same two stored fields:
        one texture read of the served ``residual`` texture (R = ``gen_a``,
        G = ``gen_b``) at the fragment's OWN coordinate - undisplaced, so no
        second resampling and no chained resampling blur - evaluated as
        ``t(1 - t)(a + b t)`` and added to the construction the baseline
        shader already draws, then clamped. The STORED parabola is what is
        evaluated, not a recomputation from ``res_s``, so the bench ranks
        exactly the picture the map draws.

        Endpoint exactness is structural: ``t(1 - t)`` vanishes at both ends
        whatever the coefficients say, so the guards below agree with the
        algebra rather than covering for it. A pair carrying no envelope (an
        older artifact, the harness's synthetic pairs) draws the baseline.
        """
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
        base = plain + motion.advect_weight * (warped - plain)
        stored_a = motion.extra.get("gen_a")
        if stored_a is None:
            return base
        a = numpy.nan_to_num(numpy.asarray(stored_a, dtype="float64"), nan=0.0)
        stored_b = motion.extra.get("gen_b")
        b = numpy.zeros_like(a) if stored_b is None else numpy.nan_to_num(numpy.asarray(stored_b, dtype="float64"), nan=0.0)
        envelope = t * (1.0 - t) * (a + b * t)
        # These are percent cloud fields and nothing outside [0, 100] is a
        # meaningful value to draw. `base` is already inside it (a convex
        # combination of two retrieved fields), so this clip only ever acts
        # on the envelope term.
        return numpy.clip(base + envelope, 0.0, 100.0)

    def configure(self, context: MethodContext) -> tuple[InterpolationMethod, dict[str, Any]]:
        """Three decisions, all measured: the steering prior, then the residual against two controls.

        The prior is settled first by the baseline's own procedure, which
        scores THIS class' composite (it builds through ``type(self)``), so
        the wind is judged on the construction it will actually serve. The
        residual is then scored three ways against the held-out frames - on,
        off, and negated - and applied only if it beats BOTH controls.

        The negated control is what separates "this residual is the weather"
        from "any bump in the middle of the interval scores better here".
        Only the first is a reason to draw it.

        One honest caveat on that control, because it changes what it is FOR.
        The composite is affine in ``s`` and mean absolute error is convex, so
        the off case is a convex combination of the on and negated cases and
        cannot be worse than both: if the residual beats off on MAE, its
        negation must lose to off. On the MAE-derived comparison the negated
        control is therefore IMPLIED by the comparison against off, and it
        cannot be the deciding vote. It is kept, and published, for three
        reasons that survive that: the clip to [0, 100] makes the composite
        only piecewise affine, so the argument has a boundary case; the
        structural-similarity comparison beside it is not convex and can bind
        on its own; and a reader deciding whether to believe this method is
        owed the number that says the SIGN of the residual - not just the
        presence of a bump - is what carries the improvement.

        WHICH NUMBER DECIDES, and why it is not the one the other gated
        methods use. ``improvement_over_reversed_flow`` is the right statistic
        for the bench's VETO - it asks whether a construction beats itself
        with its motion reversed, which is the question "does the direction
        carry information" - but it is a ratio against a control that MOVES
        WITH THE METHOD, so it cannot rank two variants of one method against
        each other. Measured, on HRDPS ``total_cloud`` (2026-09-01 00Z,
        f005-f009): a variant scoring midpoint MAE 14.87 and SSIM 0.392
        reported ``improvement_over_reversed_flow`` 0.195, while the variant
        scoring MAE 14.57 and SSIM 0.402 reported 0.137. The worse
        reconstruction won on the ratio because it had also made its own
        control worse. Gating on that would have switched on the variant that
        draws the worse picture.

        So the gate is ``harness.admit``, whose controls are FIXED - a plain
        dissolve and a plain advection of the same two frames, identical for
        all three cases - which makes it a ranking of the reconstructions
        themselves: strictly better on ``improvement_over_crossfade`` at the
        midpoint, structural similarity not lower, mean error over every
        held-out fraction not worse, and the sharpness ratio not further
        from 1. All are needed: MAE alone rewards smearing more of the change
        into the middle of the interval (research note §7), SSIM catches
        that, and the sharpness ratio catches a win bought by blur that SSIM
        forgives. The gate is applied twice, against the off control and
        against the negated one. Every number, including the reversed-flow
        ratio, is published either way.

        An unmeasurable sequence (fewer than three published frames, so
        nothing can be held out) switches the residual off. That is not a
        judgement that it fails; it is the same rule the rest of the bench
        follows, that an optional term is applied where it has been shown to
        help and nowhere else.
        """
        settled, notes = super().configure(context)
        use_prior = bool(getattr(settled, "use_prior", False))
        build = type(self)

        def score(**options: bool) -> dict[str, Any] | None:
            return _interpolation_skill(
                context.frames,
                method=build(use_prior=use_prior, **options),
                dataset=context.dataset,
                variable=context.variable,
                interval_seconds=context.interval_seconds,
                indices=context.indices,
                cache=context.cache,
            )

        with_residual = score(use_residual=True)
        without_residual = score(use_residual=False)
        negated = score(use_residual=True, negate_residual=True)
        # The control that decides whether the residual's SIGN carries
        # anything: negating it delivers the same change back-loaded instead
        # of front-loaded - an equally admissible shape a priori - so a
        # residual that cannot beat it has shown only that a bump helps, not
        # that this bump is the weather.
        use_residual = admit(with_residual, without_residual) and admit(with_residual, negated)
        read = lambda skill, name: skill[name] if skill else None  # noqa: E731
        return build(use_prior=use_prior, use_residual=use_residual), {
            **notes,
            "residual_applied": use_residual,
            "residual_cap_percent": RESIDUAL_CAP_PERCENT,
            "residual_gain": RESIDUAL_GAIN,
            "envelope": "t(1-t)(gen_a + gen_b t), gen_a = 4 * gain * s, gen_b = 0",
            "held_out_improvement_with_residual": read(with_residual, "improvement_over_crossfade"),
            "held_out_improvement_without_residual": read(without_residual, "improvement_over_crossfade"),
            "held_out_improvement_with_negated_residual": read(negated, "improvement_over_crossfade"),
            "held_out_improvement_over_advection_with_residual": read(with_residual, "improvement_over_advection"),
            "held_out_improvement_over_advection_without_residual": read(without_residual, "improvement_over_advection"),
            "held_out_improvement_over_advection_with_negated_residual": read(negated, "improvement_over_advection"),
            "held_out_ssim_with_residual": read(with_residual, "midpoint_ssim"),
            "held_out_ssim_without_residual": read(without_residual, "midpoint_ssim"),
            "held_out_ssim_with_negated_residual": read(negated, "midpoint_ssim"),
            "held_out_sharpness_ratio_with_residual": read(with_residual, "midpoint_sharpness_ratio"),
            "held_out_sharpness_ratio_without_residual": read(without_residual, "midpoint_sharpness_ratio"),
            "held_out_sharpness_ratio_with_negated_residual": read(negated, "midpoint_sharpness_ratio"),
            # Published as well, because it is the statistic the bench's own
            # veto reads and a provenance reader will look for it - but see
            # the docstring for why it is not what decides here.
            "held_out_improvement_over_reversed_flow_with_residual": read(
                with_residual, "improvement_over_reversed_flow"
            ),
            "held_out_improvement_over_reversed_flow_without_residual": read(
                without_residual, "improvement_over_reversed_flow"
            ),
            "residual_admission": admit_reasons(with_residual, without_residual),
            "residual_admission_against_negated": admit_reasons(with_residual, negated),
            "skill": with_residual if use_residual else without_residual,
        }
