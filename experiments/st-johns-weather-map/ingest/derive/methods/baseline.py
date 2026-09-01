"""The construction the map has been drawing with since cloud-motion-development-v3.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    STEERING_LEVEL_BY_VARIABLE,
    _consistency,
    _development_agreement,
    _dis_flow,
    _display_weight,
    _prior_corrected,
    _steering_prior,
    _supported_flow,
    _warp_nearest,
)
from ingest.derive.methods.contract import InterpolationMethod, MethodContext, PairMotion
from ingest.derive.methods.harness import _interpolation_skill

class BaselineMethod(InterpolationMethod):
    """What shipped as ``cloud-motion-development-v3``.

    Relative forward-backward consistency, neighbourhood fill with a support
    field, an agreement-over-support display weight, and the optional model
    steering prior. The two frames are warped toward each other along the
    pair's own flow and mixed linearly by ``t``.
    """

    id = "baseline"
    # Named for what it draws, not for its place in the bench. "Baseline"
    # alone read as "no motion" in the menu, and a summary that led on the
    # word "dissolving" made the shipped advection look like a cross-fade -
    # this is the construction that has been drawing the map since
    # cloud-motion-development-v3, and the title has to say so.
    title = "Advection along derived motion"
    summary = (
        "The construction the map has been drawing with. Both frames are warped toward each "
        "other along the pair's own dense flow, following C1 trajectories fitted through the "
        "neighbouring published frames, and only the cells where the two warps disagree - where "
        "cloud grew or decayed in place rather than moved - fall back to a dissolve."
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
        and the prior is applied only if it predicts real frames better. Both
        numbers go to provenance either way, so "the wind helped" is
        checkable.
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
        )
        with_prior = _interpolation_skill(
            context.frames,
            method=build(use_prior=True),
            dataset=context.dataset,
            variable=context.variable,
            interval_seconds=context.interval_seconds,
            indices=context.indices,
        )
        use_prior = (
            with_prior is not None
            and without is not None
            and with_prior["improvement_over_reversed_flow"] > without["improvement_over_reversed_flow"]
        )
        notes = {
            "applied": bool(use_prior),
            "level_hpa": STEERING_LEVEL_BY_VARIABLE.get(context.variable),
            "held_out_improvement_with_prior": (
                with_prior["improvement_over_reversed_flow"] if with_prior else None
            ),
            "held_out_improvement_without_prior": (
                without["improvement_over_reversed_flow"] if without else None
            ),
            "skill": with_prior if use_prior else without,
        }
        return build(use_prior=use_prior), notes

    def motion(self, context: MethodContext) -> list[PairMotion]:
        import numpy  # noqa: PLC0415

        results: list[PairMotion] = []
        for position in range(len(context.frames) - 1):
            previous = context.frames[position]
            following = context.frames[position + 1]
            raw01 = _dis_flow(previous, following)
            raw10 = _dis_flow(following, previous)
            agreed = _consistency(raw01, raw10)
            flow01, support = _supported_flow(raw01.astype("float64"), agreed)
            flow10, _ = _supported_flow(raw10.astype("float64"), agreed)
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
                    advect_weight=_display_weight(support, _development_agreement(previous, following, flow01)),
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
