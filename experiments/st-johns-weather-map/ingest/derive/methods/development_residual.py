"""The model's own vertical velocity re-times the dissolve where advection failed.

One plugin, one module. See ``ingest.derive.methods`` for the contract.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    DEVELOPMENT_SIGMA_CELLS,
    STEERING_LEVEL_BY_VARIABLE,
    _development_agreement,
    _gaussian,
    _warp_nearest,
)
from ingest.derive.methods.contract import Requirement, InterpolationMethod, MethodContext, PairMotion
from ingest.derive.methods.baseline import BaselineMethod
from ingest.derive.methods.intermediate_flow import IntermediateFlowMethod
from ingest.derive.methods.harness import _interpolation_skill


#: Hour-to-hour change in the model's own omega at which the residual's
#: shaping saturates, in Pa s-1. Measured, not chosen: HRDPS 700 hPa omega
#: over the Avalon crop for the 2026-09-01 00Z run, f006 -> f007, gives
#: |omega| median 0.15 and |omega_1 - omega_0| median 0.090, p90 0.265,
#: p95 0.335, p99 0.465 Pa s-1. Saturating at 0.35 puts full strength at
#: about the 95th percentile of the real tendency and leaves the median cell
#: at roughly a quarter strength, so the common case is nudged and only a
#: genuinely large swing in the model's forcing moves the display far.
OMEGA_TENDENCY_SCALE_PA_PER_S = 0.35

#: The residual's gain, and there is deliberately no freedom in it. The
#: shaped mixing fraction is s(t) = t + gain * phi * t(1 - t), whose
#: derivative is 1 + gain*phi*(1 - 2t); with |phi| <= 1 a gain of 1 is exactly
#: the value at which s stays monotone on [0, 1]. Anything larger makes s
#: non-monotone and lets the display leave the interval between the two
#: retrieved frames, which is the bound this method is not allowed to break.
#: So the strength that is actually tunable is the measured scale above.
RESIDUAL_SHAPE_GAIN = 1.0


def _omega_tendency(
    dataset: Any, variable: str, indices: tuple[int, int], shape: tuple[int, int]
) -> Any | None:
    """``omega_1 - omega_0`` at the stratum's steering level, in Pa s-1, or None.

    Vertical velocity on pressure surfaces, WMO discipline 0 category 2
    parameter 8 - verified in the message's own coded keys, not inferred from
    a name (HRDPS ``VVEL_ISBL_0850``, RDPS ``VerticalVelocity_IsbL-0850``,
    GFS ``VVEL:850 mb``, all decoding to ecCodes ``w``, paramId 135,
    ``Pa s**-1``). The sign convention follows from the units: omega is
    d(pressure)/dt, so NEGATIVE is ascent and positive is descent.

    What is read is the DIFFERENCE between the pair's two instants rather
    than the interval mean, because a mean says only which way the forcing
    points and this method needs to know WHEN inside the interval the change
    happened. Stronger ascent at the start means the growth it forced
    happened early; stronger ascent at the end means it happened late. That
    is the only thing a re-timing can honestly express.

    Absent omega is an absent shaping, never a zero one: the method then
    composites exactly as the baseline does, which is the same rule the
    steering prior already follows.
    """
    import numpy  # noqa: PLC0415

    level = STEERING_LEVEL_BY_VARIABLE.get(variable)
    if level is None:
        return None
    name = f"omega_{level}hPa"
    if name not in getattr(dataset, "data_vars", {}):
        return None
    try:
        field = dataset[name]
        time_name = next((dim for dim in ("valid_time", "time") if dim in field.dims), None)
        if time_name is None or field.sizes[time_name] <= max(indices):
            return None
        pair = numpy.asarray(field.isel({time_name: list(indices)}).values, dtype="float64")
        if pair.shape[1:] != shape:
            return None
        return numpy.nan_to_num(pair[1] - pair[0], nan=0.0)
    except Exception:
        # Unreadable omega is simply absent. It never fails the motion
        # artifact, which stands on the imagery.
        return None


class DevelopmentResidualMethod(BaselineMethod):
    """Growth and decay re-timed by the model's own vertical velocity.

    Growth and decay in place is the acknowledged hard limit of every
    advection method: Vandal & Nemani (IEEE TGRS 2021) name rapid cloud
    growth and decay as THE failure mode of optical-flow interpolation on
    GOES, because it violates brightness constancy outright, and NowcastNet
    (Zhang et al., Nature 2023) answers it with an evolution network that
    emits an intensity residual beside the motion field. Where
    ``_development_agreement`` is low the shipped construction falls back to a
    symmetric dissolve, which delivers the whole change at a constant rate
    because it has nothing better to say.

    This experiment interpolates MODEL OUTPUT, so it has something better to
    say without learning anything: the same model run publishes the vertical
    velocity that made the cloud. Ascent supports formation, descent supports
    dissipation, and the change in omega across the interval says whether the
    forcing was front-loaded or back-loaded.

    The construction is a re-timing and nothing else. The un-advected part of
    the display is

        s(t) = t + gain * phi * t (1 - t)
        plain(t) = previous + s(t) * (following - previous)

    with ``phi`` in [-1, 1] the signed shaping and ``gain = 1``.

    THE BOUND, which is the whole licence for this method:

    1. ``s(0) = 0`` and ``s(1) = 1`` structurally - the ``t(1 - t)`` factor
       vanishes at both ends - so endpoint exactness is a property of the
       algebra and not of a clamp.
    2. ``s`` is monotone on [0, 1] because ``|gain * phi| <= 1``, so
       ``s(t)`` stays in [0, 1] and ``plain(t)`` is a CONVEX COMBINATION of
       the two retrieved frames AT THE SAME CELL. It therefore never exceeds
       ``max(previous, following)`` nor falls below ``min(previous, following)``
       there: this method cannot add cloud that is in neither frame, and
       cannot remove cloud that is in both. Omega decides only how the change
       between two retrieved values is delivered in time; it never decides
       what the change is.
    3. It reaches the display only in proportion to ``1 - advect_weight``,
       through the same mix the baseline already uses, so where the imagery
       shows motion the motion wins and the residual is worth nothing.
    4. It is applied per variable only where the held-out reconstruction says
       it helps (``configure``), with both numbers published either way.

    Deliberately NOT done: a diagnostic cloud-fraction closure (Xu-Randall
    from interpolated humidity) is the fuller version of this idea, and it is
    refused. A diagnosed cloud fraction would not match the model's own
    published total cloud, which comes from a different closure, so it would
    be a second opinion drawn over a retrieved field rather than a re-timing
    of it - a displayed value nothing retrieved. The residual is shaped; the
    field is never replaced.
    """

    id = "development-residual"
    title = "Development residual (model vertical velocity)"
    summary = (
        "The same two frames and the same derived motion, but where advection fails to explain "
        "the change - where cloud grew or decayed in place rather than moved - the dissolve is "
        "re-timed by the model run's own vertical velocity, so cloud appears while the model says "
        "air is rising and thins while it says air is sinking, instead of fading at a constant "
        "rate. The displayed value stays between the two retrieved frames at every cell, so "
        "nothing is added that is in neither frame and nothing removed that is in both."
    )
    shader = "development-residual"
    #: The per-cell signed shaping, in [-1, 1]. Stored rather than recomputed
    #: because the client has no omega and must not be handed one.
    extra_suffixes = ("dev_shape",)


    def requirements(self) -> list[Requirement]:
        """The model's own vertical velocity, which a cycle must have ingested."""
        return [Requirement(
            name="vertical velocity on pressure levels",
            met=False,
            detail=(
                "checked per variable when the method is derived: a surface artifact without the "
                "stratum's omega leaves the dissolve at its constant rate, which is exactly what "
                "the baseline draws"
            ),
        )]

    def __init__(self, *, use_prior: bool = False, use_residual: bool = True) -> None:
        super().__init__(use_prior=use_prior)
        self.use_residual = use_residual

    def _shape(self, context: MethodContext, position: int, previous: Any, following: Any) -> tuple[Any, bool]:
        """The pair's signed shaping ``phi`` in [-1, 1], and whether omega reached it.

        Sign, worked through once so it is not re-derived at every reading.
        Let ``a = -omega`` be ascent, so ``a_0 - a_1 = omega_1 - omega_0``.

        - Cloud GREW (``change > 0``) with ascent stronger early
          (``a_0 > a_1``, so ``omega_1 - omega_0 > 0``): the growth was forced
          early, so front-load it - ``phi > 0``, ``s(t) > t``.
        - Cloud DECAYED (``change < 0``) with descent stronger early
          (``omega_0 > omega_1``, so ``omega_1 - omega_0 < 0``): the decay was
          forced early, front-load it again - ``phi > 0``.

        Both cases are ``phi ~ (omega_1 - omega_0) * sign(change)``, which is
        why one expression covers formation and dissipation.
        """
        import numpy  # noqa: PLC0415

        shape = numpy.asarray(previous).shape
        if not self.use_residual or context.dataset is None:
            return numpy.zeros(shape, dtype="float64"), False
        tendency = _omega_tendency(
            context.dataset,
            context.variable,
            (context.indices[position], context.indices[position + 1]),
            shape,
        )
        if tendency is None:
            return numpy.zeros(shape, dtype="float64"), False
        change = numpy.nan_to_num(following, nan=0.0) - numpy.nan_to_num(previous, nan=0.0)
        signed = numpy.clip(tendency / OMEGA_TENDENCY_SCALE_PA_PER_S, -1.0, 1.0) * numpy.sign(change)
        # Smoothed over the same radius the development agreement is, so the
        # re-timing varies gradually rather than per pixel. A Gaussian is a
        # positive-weight average, so this cannot leave [-1, 1]; the clip is
        # float hygiene, not a bound being enforced after the fact. Smearing
        # across a sign change of `change` is harmless because the residual's
        # effect is proportional to `change`, which vanishes there.
        return numpy.clip(_gaussian(signed, DEVELOPMENT_SIGMA_CELLS), -1.0, 1.0), True

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The baseline's derivation exactly, plus the pair's shaping field.

        The motion is deliberately untouched: the claim under test is about
        the COMPOSITE, so sharing the derivation with the baseline is what
        makes the comparison controlled rather than two changes at once - the
        same reason ``IntermediateFlowMethod`` shares it.
        """
        import numpy  # noqa: PLC0415

        results = super().motion(context)
        for position, pair in enumerate(results):
            shaping, reached = self._shape(
                context, position, context.frames[position], context.frames[position + 1]
            )
            pair.extra["dev_shape"] = shaping
            pair.diagnostics["omega_reached"] = 1.0 if reached else 0.0
            pair.diagnostics["shape_mean_abs"] = float(numpy.mean(numpy.abs(shaping)))
        return results

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        """The `development-residual` shader branch, in Python. Keep them in step.

        The GLSL in ``web/src/FlowBlendLayer.ts`` computes the same ``s(t)``
        from the same stored shaping and mixes the two frames on it in place
        of ``u_t``; if the two ever drift, this method mis-ranks itself
        against the picture actually drawn.

        Endpoint exactness is by construction as well as by the guards below:
        ``t(1 - t)`` is zero at both ends, so ``s(0) = 0`` and ``s(1) = 1``
        whatever omega said, and the warped term degenerates to the same real
        frame there.
        """
        import numpy  # noqa: PLC0415

        first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
        second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
        if t <= 0.0:
            return first
        if t >= 1.0:
            return second
        shaping = motion.extra.get("dev_shape")
        if shaping is None:
            fraction: Any = t
        else:
            fraction = t + RESIDUAL_SHAPE_GAIN * numpy.asarray(shaping, dtype="float64") * t * (1.0 - t)
        # A convex combination of the two RETRIEVED frames at this cell: the
        # residual re-times the change, it never changes what the change is.
        plain = first + fraction * (second - first)
        flow = numpy.asarray(motion.flow01, dtype="float64")
        warped = (1.0 - t) * _warp_nearest(first, t * flow) + t * _warp_nearest(second, -(1.0 - t) * flow)
        return plain + motion.advect_weight * (warped - plain)

    def configure(self, context: MethodContext) -> tuple[InterpolationMethod, dict[str, Any]]:
        """Two decisions, both measured: the steering prior, then the residual.

        The prior is settled first by the baseline's own procedure, which
        scores THIS class' composite (it builds through ``type(self)``), so
        the wind is judged on the construction it will actually serve. The
        residual is then scored against that settled prior with the shaping
        turned off, and applied only if it predicts the held-out frames
        better. Both numbers reach provenance either way, so "the model's
        omega helped" is checkable rather than asserted.
        """
        settled, notes = super().configure(context)
        use_prior = bool(getattr(settled, "use_prior", False))
        build = type(self)
        if context.dataset is None:
            return build(use_prior=False, use_residual=False), {
                **notes,
                "residual_applied": False,
                "residual_reason": "no dataset, so no vertical velocity to read",
            }
        # Both cases are scored explicitly rather than reusing the prior's own
        # numbers. `BaselineMethod.configure` scores its no-prior case WITHOUT
        # passing the dataset - correctly, since a prior it will not use need
        # not be read - and this method's shaping is read from that same
        # dataset, so reusing that score would silently compare the residual
        # against itself. It reported a dead heat to five decimals before this
        # was traced; the two calls below are the fix.
        #
        # Settling the prior on the residual-off construction is not a defect
        # either: the prior changes only the motion and the residual changes
        # only the composite, so the two decisions do not interact.
        with_residual = _interpolation_skill(
            context.frames,
            method=build(use_prior=use_prior, use_residual=True),
            dataset=context.dataset,
            variable=context.variable,
            interval_seconds=context.interval_seconds,
            indices=context.indices,
        )
        without_residual = _interpolation_skill(
            context.frames,
            method=build(use_prior=use_prior, use_residual=False),
            dataset=context.dataset,
            variable=context.variable,
            interval_seconds=context.interval_seconds,
            indices=context.indices,
        )
        use_residual = (
            with_residual is not None
            and without_residual is not None
            and with_residual["improvement_over_reversed_flow"]
            > without_residual["improvement_over_reversed_flow"]
        )
        return build(use_prior=use_prior, use_residual=use_residual), {
            **notes,
            "residual_applied": bool(use_residual),
            "residual_level_hpa": STEERING_LEVEL_BY_VARIABLE.get(context.variable),
            "omega_tendency_scale_pa_per_s": OMEGA_TENDENCY_SCALE_PA_PER_S,
            "held_out_improvement_with_residual": (
                with_residual["improvement_over_reversed_flow"] if with_residual else None
            ),
            "held_out_improvement_without_residual": (
                without_residual["improvement_over_reversed_flow"] if without_residual else None
            ),
            "skill": with_residual if use_residual else without_residual,
        }


#: The fractions of an interval a held-out frame is reconstructed at. The
#: midpoint is the hardest case and the one the shipped thresholds were
#: measured against; the thirds are reached by holding a frame out of a
#: three-interval span, and they catch a construction that is right at the
#: middle and wrong on the way there - which a midpoint-only score cannot
#: see, and which is exactly what the reader watches during playback.
