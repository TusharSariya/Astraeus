"""Held-out scoring: does a method actually predict a real frame?

The harness is what makes the bench a bench. It takes the method, so every
construction is scored by its own rule rather than by the baseline's.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import _ssim
from ingest.derive.methods.contract import MethodContext, PairMotion

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
        # Imported here rather than at module scope: baseline imports this
        # harness for its own `configure`, and the default must not turn that
        # into an import cycle.
        from ingest.derive.methods.baseline import BaselineMethod  # noqa: PLC0415

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
