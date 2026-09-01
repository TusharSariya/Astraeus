"""The interpolation methods the map can be switched between.

One method is one complete answer to "what should be drawn between two real
frames". Each declares how it derives its motion fields from a variable's
frame sequence, and how it composites two frames at a fraction ``t`` of the
interval - the second being the Python statement of what its shader does, so
the held-out harness scores every method by its own rule rather than by the
baseline's.

Every enabled method is derived and published each cycle, so the scores in
provenance come from the same held-out frames of the same cycle and are
directly comparable. The client picks one; a method the artifact does not
carry 404s into the crossfade fallback that is already disclosed.

Evidence rules are unchanged by the bench: a method may decide HOW retrieved
frames are warped and mixed, never invent content that was not retrieved.
Every method here is endpoint-exact - at ``t = 0`` and ``t = 1`` the real
frame shows untouched - and that is a property tests pin, not a convention.

Dependency direction: ``flow_ops`` <- ``methods`` <- ``cloud_motion``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ingest.derive.flow_ops import (
    STEERING_LEVEL_BY_VARIABLE,
    _consistency,
    _development_agreement,
    _dis_flow,
    _display_weight,
    _prior_corrected,
    _ssim,
    _steering_prior,
    _supported_flow,
    _warp_nearest,
)


@dataclass(frozen=True)
class MethodContext:
    """Everything a method may read for one variable of one artifact.

    ``frames`` are the variable's published frames in time order, as percent
    fields that may contain NaN. ``indices`` are those frames' positions in
    the artifact's own time axis, which is what a method needs to look up
    another variable (a steering wind, a vertical velocity) at the same
    instants - the held-out harness passes a subsequence, so a method must
    never assume ``indices == range(len(frames))``.
    """

    variable: str
    frames: list[Any]
    indices: tuple[int, ...]
    interval_seconds: float
    dataset: Any = None


@dataclass
class PairMotion:
    """One adjacent pair's derived fields, in grid cells per frame interval.

    ``flow01`` is what the client warps along; ``confidence`` is the raw
    forward-backward agreement, ``support`` the trusted density behind the
    fill, and ``advect_weight`` the weight the display mixes advection
    against a crossfade on. ``extra`` carries whatever else a method needs
    the client to have, keyed by the field suffix it is stored under.
    """

    flow01: Any
    flow10: Any
    confidence: Any
    support: Any
    advect_weight: Any
    extra: dict[str, Any] = field(default_factory=dict)
    #: Scalars for provenance - how much of the field an optional ingredient
    #: actually reached, and anything else worth being able to check later.
    diagnostics: dict[str, float] = field(default_factory=dict)


class InterpolationMethod:
    """Base class: subclass, set the identity fields, override the two hooks.

    ``id`` is the wire name (``/flow?method=...``), stable forever once
    published. ``shader`` names the client construction this method's fields
    are meant for, so one shader can serve several derive-side methods.
    """

    id: str = "baseline"
    title: str = "Baseline"
    summary: str = ""
    #: Client construction: 'linear' | 'hermite' | one a method adds.
    shader: str = "hermite"
    #: Extra stored field suffixes, beyond the ones every method publishes.
    extra_suffixes: tuple[str, ...] = ()
    #: False keeps a method in the registry but out of every cycle.
    enabled: bool = True
    #: True where the disclosure must say the pixels were generated rather
    #: than retrieved. No such method may ship without a carve-out amendment.
    generative: bool = False

    def configure(self, context: MethodContext) -> tuple["InterpolationMethod", dict[str, Any]]:
        """Settle this variable's options by measurement, before deriving it.

        A method with an optional ingredient (a model wind, a terrain mask, a
        second source) decides here whether that ingredient earns its place -
        by scoring the held-out reconstruction with it and without it - and
        returns the configured method plus notes for provenance, so the claim
        is checkable rather than asserted. Returning ``self`` and ``{}`` is
        the right answer for a method with nothing to decide.

        Notes may carry ``"skill"``: the derive reuses it rather than paying
        for the same optical flow twice.
        """
        return self, {}

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """One PairMotion per adjacent frame pair. Never fewer, never more."""
        raise NotImplementedError

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        """What the client draws at ``t`` in [0, 1] - the shader, in Python.

        Endpoint exactness is required of every override: ``t = 0`` must
        return ``previous`` and ``t = 1`` must return ``following``, both
        untouched. The harness scores this function, so a composite that
        drifts from its shader silently mis-ranks its own method.
        """
        raise NotImplementedError


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


class IntermediateFlowMethod(BaselineMethod):
    """Super SloMo's intermediate flow: both directions, not one inverted.

    The baseline samples frame 0 at ``t * F01`` and frame 1 at
    ``-(1 - t) * F01``. That is the same field used twice, and it is only
    correct if the forward flow inverts exactly - which is precisely the
    assumption the forward-backward consistency score exists to measure, and
    the one it reports violated over most of this peninsula's cells.

    Jiang et al. (CVPR 2018, section 3.1) approximate the intermediate flows
    from BOTH derived directions instead, linearly in the local motion and
    quadratically in ``t``::

        F_{t->0} = -(1 - t) t F01 + t^2 F10
        F_{t->1} =  (1 - t)^2 F01 - t (1 - t) F10

    Both flows are already derived and stored per pair (``u10``/``v10`` were
    written every cycle and never served); this method only spends them. The
    derivation is the baseline's unchanged - the claim under test is about
    the COMPOSITE, so sharing the motion is what makes the comparison a
    controlled one rather than two changes at once.

    Where the round trip really does invert (``F10 == -F01``) both expressions
    collapse exactly to the baseline's, so this method can only differ where
    the two measured directions actually disagree.
    """

    id = "intermediate-flow"
    title = "Intermediate flow (both directions)"
    summary = (
        "The same two frames, warped along intermediate flows approximated from BOTH the "
        "forward and the backward derived field (Super SloMo, Jiang et al. 2018) rather than "
        "from the forward field assumed to invert; identical to the baseline wherever the "
        "round trip does invert."
    )
    shader = "intermediate"

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        """The `intermediate` shader branch, in Python. Keep the two in step.

        Sign convention, which is the whole risk here and was settled against
        ``_warp_nearest`` rather than by inspection: ``_warp_nearest(field, D)``
        reads ``field`` at ``p - D``, so displaying ``F_{t->k}`` means passing
        ``D = -F_{t->k}``. The baseline's ``D0 = t F01`` therefore already
        encodes ``F_{t->0} = -t F01``, which is what the quadratic form below
        reduces to on a pure translation (``F10 = -F01``) - checked by test,
        not by reading.

        The GLSL in ``web/src/FlowBlendLayer.ts`` samples frame 0 at
        ``v_uv - d0`` and frame 1 at ``v_uv + d1``, so ``d0 = D0`` and
        ``d1 = -D1``; if the two ever drift, this method mis-ranks itself
        against the picture actually drawn.
        """
        import numpy  # noqa: PLC0415

        first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
        second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
        # Endpoint exactness is by construction as well as by these guards:
        # at t = 0 the frame-0 displacement is zero and its blend weight is 1,
        # and at t = 1 the same holds of frame 1.
        if t <= 0.0:
            return first
        if t >= 1.0:
            return second
        flow01 = numpy.asarray(motion.flow01, dtype="float64")
        flow10 = numpy.asarray(motion.flow10, dtype="float64")
        displacement0 = (1.0 - t) * t * flow01 - t * t * flow10
        displacement1 = (1.0 - t) ** 2 * flow01 - t * (1.0 - t) * flow10
        warped = (1.0 - t) * _warp_nearest(first, displacement0) + t * _warp_nearest(second, -displacement1)
        plain = (1.0 - t) * first + t * second
        return plain + motion.advect_weight * (warped - plain)


#: The fractions of an interval a held-out frame is reconstructed at. The
#: midpoint is the hardest case and the one the shipped thresholds were
#: measured against; the thirds are reached by holding a frame out of a
#: three-interval span, and they catch a construction that is right at the
#: middle and wrong on the way there - which a midpoint-only score cannot
#: see, and which is exactly what the reader watches during playback.
HELD_OUT_FRACTIONS = (1.0 / 3.0, 0.5, 2.0 / 3.0)


def _score_one(composite: Any, truth: Any) -> tuple[float, float]:
    """``(mean absolute error, structural similarity)`` of one reconstruction.

    Both are reported because they disagree in the way that matters here. MAE
    rewards blur - a smooth field is close to everything - and blur is the
    artifact this bench exists to remove, so a method can win on MAE by
    dissolving harder. Structural similarity falls when structure is smeared,
    so a method that scores well on both has actually moved the weather.
    """
    import numpy  # noqa: PLC0415

    return float(numpy.mean(numpy.abs(composite - truth))), _ssim(composite, truth)


def _interpolation_skill(
    frames: list[Any],
    *,
    method: Any = None,
    dataset: Any = None,
    variable: str = "",
    interval_seconds: float = 0.0,
    indices: tuple[int, ...] | None = None,
) -> dict[str, Any] | None:
    """Leave-one-out skill: does this method actually predict a real frame?

    A frame is held out, its neighbours are interpolated to where it sits by
    exactly the rule ``method.composite`` applies, and the result is compared
    against the frame that was hidden - against a plain crossfade of the same
    neighbours, and against the same construction with its motion reversed.
    Every enabled method is scored on the same held-out frames of the same
    cycle, so the numbers in provenance rank the methods directly.

    The reversed-motion control is the honest baseline: any blend of two
    warps is smoother than the average of two frames and a smoother field
    scores better against almost anything (pure noise "improves" on a
    crossfade by up to 2% that way while scoring 0.000 against the control).
    Only the control isolates whether the DIRECTION carries information.

    ``None`` when the sequence is too short to hold a frame out, which is an
    absent measurement and never a zero.
    """
    import numpy  # noqa: PLC0415

    if len(frames) < 3:
        return None
    if method is None:
        method = BaselineMethod(use_prior=dataset is not None)
    positions = tuple(indices) if indices is not None else tuple(range(len(frames)))
    filled = [numpy.nan_to_num(frame, nan=0.0) for frame in frames]

    def reconstruct(first: int, last: int, held_out: int) -> tuple[float, tuple[float, float], tuple[float, float], tuple[float, float]] | None:
        """Score one hold-out: (t, composite, crossfade, reversed control)."""
        span = last - first
        fraction = (held_out - first) / span
        context = MethodContext(
            variable=variable,
            frames=[filled[first], filled[last]],
            indices=(positions[first], positions[last]),
            interval_seconds=interval_seconds * span,
            dataset=dataset,
        )
        motion = method.motion(context)
        if not motion:
            return None
        pair = motion[0]
        truth = filled[held_out]
        previous, following = filled[first], filled[last]
        reversed_pair = PairMotion(
            flow01=-numpy.asarray(pair.flow01),
            flow10=-numpy.asarray(pair.flow10),
            confidence=pair.confidence,
            support=pair.support,
            advect_weight=pair.advect_weight,
            extra=pair.extra,
        )
        crossfade = (1.0 - fraction) * previous + fraction * following
        return (
            fraction,
            _score_one(method.composite(previous, following, pair, fraction), truth),
            _score_one(crossfade, truth),
            _score_one(method.composite(previous, following, reversed_pair, fraction), truth),
        )

    holdouts: list[tuple[int, int, int]] = []
    # t = 1/2: every interior frame, from its immediate neighbours.
    holdouts += [(index - 1, index + 1, index) for index in range(1, len(filled) - 1)]
    # t = 1/3 and 2/3: both interior frames of a three-interval span.
    holdouts += [
        (start, start + 3, start + offset)
        for start in range(0, len(filled) - 3)
        for offset in (1, 2)
    ]

    by_fraction: dict[float, list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]] = {}
    for first, last, held_out in holdouts:
        scored = reconstruct(first, last, held_out)
        if scored is None:
            continue
        fraction, composite, crossfade, control = scored
        by_fraction.setdefault(round(fraction, 3), []).append((composite, crossfade, control))
    if not by_fraction:
        return None

    def summarise(entries: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]) -> dict[str, Any]:
        composite_mae = float(numpy.mean([entry[0][0] for entry in entries]))
        crossfade_mae = float(numpy.mean([entry[1][0] for entry in entries]))
        control_mae = float(numpy.mean([entry[2][0] for entry in entries]))
        return {
            "held_out_frames": len(entries),
            "mae_percent": composite_mae,
            "crossfade_mae_percent": crossfade_mae,
            "reversed_flow_mae_percent": control_mae,
            "improvement_over_crossfade": (crossfade_mae - composite_mae) / crossfade_mae if crossfade_mae > 0 else 0.0,
            "improvement_over_reversed_flow": (control_mae - composite_mae) / control_mae if control_mae > 0 else 0.0,
            "ssim": float(numpy.mean([entry[0][1] for entry in entries])),
            "crossfade_ssim": float(numpy.mean([entry[1][1] for entry in entries])),
            "reversed_flow_ssim": float(numpy.mean([entry[2][1] for entry in entries])),
        }

    fractions = {str(round(fraction, 3)): summarise(entries) for fraction, entries in sorted(by_fraction.items())}
    # The midpoint keeps the top-level names it has always had: the shipped
    # veto threshold was measured against it, and provenance readers (and the
    # display-weight veto below) must not silently change meaning.
    midpoint = fractions.get("0.5") or summarise([entry for entries in by_fraction.values() for entry in entries])
    return {
        "method": getattr(method, "id", "baseline"),
        "held_out_frames": midpoint["held_out_frames"],
        "midpoint_mae_percent": midpoint["mae_percent"],
        "midpoint_crossfade_mae_percent": midpoint["crossfade_mae_percent"],
        "midpoint_reversed_flow_mae_percent": midpoint["reversed_flow_mae_percent"],
        "improvement_over_crossfade": midpoint["improvement_over_crossfade"],
        "improvement_over_reversed_flow": midpoint["improvement_over_reversed_flow"],
        "midpoint_ssim": midpoint["ssim"],
        "midpoint_crossfade_ssim": midpoint["crossfade_ssim"],
        "by_fraction": fractions,
    }

#: Every method the bench knows, in menu order. `baseline` must stay first
#: and must stay enabled: it is the default the client falls back to and the
#: control every other method's score is read against.
METHODS: tuple[InterpolationMethod, ...] = (BaselineMethod(), IntermediateFlowMethod())

DEFAULT_METHOD_ID = "baseline"


def enabled_methods() -> tuple[InterpolationMethod, ...]:
    """The methods this cycle derives, baseline first."""
    return tuple(method for method in METHODS if method.enabled)


def method_by_id(method_id: str) -> InterpolationMethod | None:
    """The method with this wire name, or None - never a silent substitute."""
    return next((method for method in METHODS if method.id == method_id), None)


def method_catalogue() -> list[dict[str, Any]]:
    """The registry as plain data, for the API to serve and the menu to render."""
    return [
        {
            "id": method.id,
            "title": method.title,
            "summary": method.summary,
            "shader": method.shader,
            "enabled": method.enabled,
            "generative": method.generative,
        }
        for method in METHODS
    ]
