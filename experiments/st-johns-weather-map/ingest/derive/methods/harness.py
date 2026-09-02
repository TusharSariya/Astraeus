"""Held-out scoring: does a method actually predict a real frame?

The harness is what makes the bench a bench. It takes the method, so every
construction is scored by its own rule rather than by the baseline's, and
it scores against FIXED controls - a plain crossfade of the same two frames
and a plain linear advection of them - so the numbers rank methods against
each other. The reversed-motion control is kept for the one question it
answers (does the DIRECTION carry information), which is the motion veto in
``cloud_motion.py``; it moves with the method and cannot rank methods.

``admit`` is the gate every ``configure`` shares: an optional term earns its
place only on the fixed controls, on both mean error and structural
similarity, and only if it did not buy either by blurring.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import _fss, _radial_psd_log_ratio, _sharpness_ratio, _ssim
from ingest.derive.methods.contract import MethodContext, PairMotion

#: The fractions of an interval a held-out frame is reconstructed at. The
#: midpoint is the hardest case and the one the shipped thresholds were
#: measured against; the thirds are reached by holding a frame out of a
#: three-interval span, and they catch a construction that is right at the
#: middle and wrong on the way there - which a midpoint-only score cannot
#: see, and which is exactly what the reader watches during playback.
HELD_OUT_FRACTIONS = (1.0 / 3.0, 0.5, 2.0 / 3.0)

#: The fractions-skill-score cells: percent threshold and neighbourhood
#: radius in grid cells. Keys in the published ``fss`` dict are
#: ``"<threshold>/<radius>"``.
FSS_THRESHOLDS_PERCENT = (25.0, 50.0, 75.0)
FSS_RADII_CELLS = (1, 3)
#: A cell counts as having GROWN or DECAYED across the pair when the two
#: retrieved frames differ by more than this (percent). Radanovics et al.
#: 2025 (GMD 18): score cells that grew and cells that decayed separately,
#: since "conventional pixel-based metrics obscure these fundamental
#: development prediction failures".
DEVELOPMENT_CHANGE_PERCENT = 5.0


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


def _score_full(composite: Any, truth: Any, previous: Any, following: Any) -> dict[str, Any]:
    """Every score of one reconstruction against the frame that was hidden.

    ``mae`` and ``ssim`` as ``_score_one``; ``sharpness_ratio`` (1 is as sharp
    as reality); ``spectral_ratio_error`` (0 is a matching power spectrum);
    ``fss`` at the thresholds and radii above; and ``mae_grew`` /
    ``mae_decayed``, the mean error over the cells whose two retrieved
    frames say cloud formed or dissolved there - ``None`` when no cell did,
    which is an absent measurement and never a zero.
    """
    import numpy  # noqa: PLC0415

    error = numpy.abs(composite - truth)
    change = numpy.asarray(following, dtype="float64") - numpy.asarray(previous, dtype="float64")
    grew = change > DEVELOPMENT_CHANGE_PERCENT
    decayed = change < -DEVELOPMENT_CHANGE_PERCENT
    return {
        "mae": float(numpy.mean(error)),
        "ssim": _ssim(composite, truth),
        "sharpness_ratio": _sharpness_ratio(composite, truth),
        "spectral_ratio_error": _radial_psd_log_ratio(composite, truth),
        "fss": {
            f"{int(threshold)}/{radius}": _fss(composite, truth, threshold, radius)
            for threshold in FSS_THRESHOLDS_PERCENT
            for radius in FSS_RADII_CELLS
        },
        "mae_grew": float(numpy.mean(error[grew])) if grew.any() else None,
        "mae_decayed": float(numpy.mean(error[decayed])) if decayed.any() else None,
    }


def _advection_control(context: MethodContext, key: tuple[Any, ...]) -> PairMotion | None:
    """The fixed ``advection_linear`` control's motion for one pair, memoised.

    ``BaselineMethod(use_prior=False)`` on the same two frames: DIS both
    ways, consistency, fill, support-floored weight, no model wind. It is
    fixed in the sense that matters - it does not move with the method being
    scored - and it is what every method reduces to when its own ingredient
    is absent, so ``improvement_over_advection`` reads directly as "what the
    method's own term bought". Memoised in ``context.cache`` so the residual
    and generative variants, which settle several options each, pay for the
    control's optical flow once per pair rather than once per option.
    """
    if key in context.cache:
        return context.cache[key]
    # Imported here rather than at module scope: baseline imports this
    # harness for its own `configure`, and the control must not turn that
    # into an import cycle.
    from ingest.derive.methods.baseline import BaselineMethod  # noqa: PLC0415

    motion = BaselineMethod(use_prior=False).motion(context)
    pair = motion[0] if motion else None
    context.cache[key] = pair
    return pair


def _interpolation_skill(
    frames: list[Any],
    *,
    method: Any = None,
    dataset: Any = None,
    variable: str = "",
    interval_seconds: float = 0.0,
    indices: tuple[int, ...] | None = None,
    cache: dict | None = None,
) -> dict[str, Any] | None:
    """Leave-one-out skill: does this method actually predict a real frame?

    A frame is held out, its neighbours are interpolated to where it sits by
    exactly the rule ``method.composite`` applies, and the result is compared
    against the frame that was hidden - and so are three controls on the same
    two neighbours: a plain crossfade (``crossfade``), a plain linear
    advection with no optional ingredient (``advection_linear``), and the
    same construction with its motion reversed (``reversed_flow``). Every
    enabled method is scored on the same held-out frames of the same cycle,
    so the numbers in provenance rank the methods directly.

    The two FIXED controls are the ones to rank on: they are the same for
    every method and every option, so a better number is a better picture.
    The reversed-motion control is the honest test of whether the DIRECTION
    carries information - any blend of two warps is smoother than the average
    of two frames, and pure noise "improves" on a crossfade by up to 2% that
    way while scoring 0.000 against its own reversal - and that is the only
    thing it is read for (``MIN_HELD_OUT_IMPROVEMENT`` in ``cloud_motion``).
    It moves with the method, so a method can raise it by making its own
    control worse; it must not rank methods and does not here.

    ``cache`` is the caller's ``MethodContext.cache``; passed through to the
    per-pair contexts so the advection control and the baseline's flow are
    memoised across every option a ``configure`` scores.

    ``None`` when the sequence is too short to hold a frame out, which is an
    absent measurement and never a zero.
    """
    import numpy  # noqa: PLC0415

    if len(frames) < 3:
        return None
    if method is None:
        from ingest.derive.methods.baseline import BaselineMethod  # noqa: PLC0415

        method = BaselineMethod(use_prior=dataset is not None)
    positions = tuple(indices) if indices is not None else tuple(range(len(frames)))
    filled = [numpy.nan_to_num(frame, nan=0.0) for frame in frames]
    shared: dict = cache if cache is not None else {}

    def reconstruct(first: int, last: int, held_out: int) -> tuple[float, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]] | None:
        """Score one hold-out: (t, composite, crossfade, reversed control, advection control)."""
        span = last - first
        fraction = (held_out - first) / span
        context = MethodContext(
            variable=variable,
            frames=[filled[first], filled[last]],
            indices=(positions[first], positions[last]),
            interval_seconds=interval_seconds * span,
            dataset=dataset,
            cache=shared,
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
        control_pair = _advection_control(context, ("advection_linear", positions[first], positions[last]))
        if control_pair is None:
            advection = crossfade
        else:
            from ingest.derive.methods.baseline import BaselineMethod  # noqa: PLC0415

            advection = BaselineMethod(use_prior=False).composite(previous, following, control_pair, fraction)
        return (
            fraction,
            _score_full(method.composite(previous, following, pair, fraction), truth, previous, following),
            _score_full(crossfade, truth, previous, following),
            _score_full(method.composite(previous, following, reversed_pair, fraction), truth, previous, following),
            _score_full(advection, truth, previous, following),
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

    by_fraction: dict[float, list[tuple[dict[str, Any], ...]]] = {}
    for first, last, held_out in holdouts:
        scored = reconstruct(first, last, held_out)
        if scored is None:
            continue
        fraction, *entries = scored
        by_fraction.setdefault(round(fraction, 3), []).append(tuple(entries))
    if not by_fraction:
        return None

    def mean_of(values: list[Any]) -> float | None:
        present = [value for value in values if value is not None]
        return float(numpy.mean(present)) if present else None

    def summarise(entries: list[tuple[dict[str, Any], ...]]) -> dict[str, Any]:
        composite = [entry[0] for entry in entries]
        crossfade = [entry[1] for entry in entries]
        control = [entry[2] for entry in entries]
        advection = [entry[3] for entry in entries]
        composite_mae = mean_of([item["mae"] for item in composite])
        crossfade_mae = mean_of([item["mae"] for item in crossfade])
        control_mae = mean_of([item["mae"] for item in control])
        advection_mae = mean_of([item["mae"] for item in advection])
        return {
            "held_out_frames": len(entries),
            "mae_percent": composite_mae,
            "crossfade_mae_percent": crossfade_mae,
            "reversed_flow_mae_percent": control_mae,
            "advection_mae_percent": advection_mae,
            "improvement_over_crossfade": (crossfade_mae - composite_mae) / crossfade_mae if crossfade_mae > 0 else 0.0,
            "improvement_over_reversed_flow": (control_mae - composite_mae) / control_mae if control_mae > 0 else 0.0,
            "improvement_over_advection": (advection_mae - composite_mae) / advection_mae if advection_mae > 0 else 0.0,
            "ssim": mean_of([item["ssim"] for item in composite]),
            "crossfade_ssim": mean_of([item["ssim"] for item in crossfade]),
            "reversed_flow_ssim": mean_of([item["ssim"] for item in control]),
            "advection_ssim": mean_of([item["ssim"] for item in advection]),
            "sharpness_ratio": mean_of([item["sharpness_ratio"] for item in composite]),
            "advection_sharpness_ratio": mean_of([item["sharpness_ratio"] for item in advection]),
            "spectral_ratio_error": mean_of([item["spectral_ratio_error"] for item in composite]),
            "fss": {
                key: mean_of([item["fss"][key] for item in composite])
                for key in composite[0]["fss"]
            },
            "mae_grew": mean_of([item["mae_grew"] for item in composite]),
            "mae_decayed": mean_of([item["mae_decayed"] for item in composite]),
            "advection_mae_grew": mean_of([item["mae_grew"] for item in advection]),
            "advection_mae_decayed": mean_of([item["mae_decayed"] for item in advection]),
        }

    fractions = {str(round(fraction, 3)): summarise(entries) for fraction, entries in sorted(by_fraction.items())}
    # The midpoint keeps the top-level names it has always had: the shipped
    # veto threshold was measured against it, and provenance readers (and the
    # display-weight veto in `cloud_motion`) must not silently change meaning.
    midpoint = fractions.get("0.5") or summarise([entry for entries in by_fraction.values() for entry in entries])
    return {
        "method": getattr(method, "id", "baseline"),
        "held_out_frames": midpoint["held_out_frames"],
        "midpoint_mae_percent": midpoint["mae_percent"],
        "midpoint_crossfade_mae_percent": midpoint["crossfade_mae_percent"],
        "midpoint_reversed_flow_mae_percent": midpoint["reversed_flow_mae_percent"],
        "midpoint_advection_mae_percent": midpoint["advection_mae_percent"],
        "improvement_over_crossfade": midpoint["improvement_over_crossfade"],
        "improvement_over_reversed_flow": midpoint["improvement_over_reversed_flow"],
        "improvement_over_advection": midpoint["improvement_over_advection"],
        "midpoint_ssim": midpoint["ssim"],
        "midpoint_crossfade_ssim": midpoint["crossfade_ssim"],
        "midpoint_advection_ssim": midpoint["advection_ssim"],
        "midpoint_sharpness_ratio": midpoint["sharpness_ratio"],
        "midpoint_spectral_ratio_error": midpoint["spectral_ratio_error"],
        "midpoint_fss": midpoint["fss"],
        "midpoint_mae_grew": midpoint["mae_grew"],
        "midpoint_mae_decayed": midpoint["mae_decayed"],
        "by_fraction": fractions,
    }


def _mean_mae(skill: dict[str, Any]) -> float:
    """Mean of ``mae_percent`` over every held-out fraction in ``by_fraction``."""
    import numpy  # noqa: PLC0415

    values = [block["mae_percent"] for block in skill.get("by_fraction", {}).values() if block.get("mae_percent") is not None]
    return float(numpy.mean(values)) if values else float(skill.get("midpoint_mae_percent", 0.0))


#: How much closer to 1.0 the control's sharpness ratio has to be before the
#: gate calls it a real loss of structure. The three error checks are one-sided
#: and admit an exact tie; the sharpness check is a DISTANCE from 1.0, so
#: without a tolerance two ratios that differ in the seventh decimal - a field
#: whose edge energy the term did not touch at all - decide the gate on
#: floating-point noise. Measured differences that matter here are order 0.02
#: (0.98 against 1.00 on the shipped layers); 0.001 is two orders below that
#: and still an order above the noise seen on synthetic uniform fields.
SHARPNESS_TIE_TOLERANCE = 1e-3


def admit_reasons(with_: dict[str, Any] | None, without: dict[str, Any] | None) -> dict[str, Any]:
    """Every check ``admit`` makes, with both numbers, for provenance.

    The contract's "harness gate": an optional term is admitted only if, on
    the same held-out frames and against the same FIXED controls, it is
    strictly better on ``improvement_over_crossfade`` at the midpoint, not
    lower on ``midpoint_ssim``, not worse on the mean MAE over every held-out
    fraction, and its sharpness ratio is not further from 1.0 (beyond
    ``SHARPNESS_TIE_TOLERANCE``) - so it cannot
    have bought the first three by blurring, nor by manufacturing edges.
    Absent skill on either side (nothing could be held out) refuses.
    """
    if with_ is None or without is None:
        return {
            "admitted": False,
            "reason": "no held-out measurement on one side (fewer than three frames), so nothing is admitted unmeasured",
            "checks": {},
        }
    checks = {
        "improvement_over_crossfade": {
            "with": with_["improvement_over_crossfade"],
            "without": without["improvement_over_crossfade"],
            "rule": "strictly greater at the midpoint",
            "passed": bool(with_["improvement_over_crossfade"] > without["improvement_over_crossfade"]),
        },
        "midpoint_ssim": {
            "with": with_["midpoint_ssim"],
            "without": without["midpoint_ssim"],
            "rule": "not lower",
            "passed": bool(with_["midpoint_ssim"] >= without["midpoint_ssim"]),
        },
        "mean_mae_over_fractions": {
            "with": _mean_mae(with_),
            "without": _mean_mae(without),
            "rule": "not worse over every held-out fraction",
            "passed": bool(_mean_mae(with_) <= _mean_mae(without)),
        },
        "sharpness_ratio": {
            "with": with_["midpoint_sharpness_ratio"],
            "without": without["midpoint_sharpness_ratio"],
            "rule": f"not further from 1.0 by more than {SHARPNESS_TIE_TOLERANCE}",
            "passed": bool(
                abs(with_["midpoint_sharpness_ratio"] - 1.0)
                <= abs(without["midpoint_sharpness_ratio"] - 1.0) + SHARPNESS_TIE_TOLERANCE
            ),
        },
    }
    return {
        "admitted": all(check["passed"] for check in checks.values()),
        "checks": checks,
        # Published beside the decision, never read by it: the moving control.
        "improvement_over_reversed_flow": {
            "with": with_["improvement_over_reversed_flow"],
            "without": without["improvement_over_reversed_flow"],
        },
        "improvement_over_advection": {
            "with": with_["improvement_over_advection"],
            "without": without["improvement_over_advection"],
        },
    }


def admit(with_: dict[str, Any] | None, without: dict[str, Any] | None) -> bool:
    """Does the construction WITH the optional term earn its place over the one WITHOUT?

    See ``admit_reasons`` for the four checks. Shared by every ``configure``
    on the bench, so "measured to help" means one thing everywhere.
    """
    return bool(admit_reasons(with_, without)["admitted"])
