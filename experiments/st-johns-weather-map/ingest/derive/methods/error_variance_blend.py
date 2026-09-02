"""Fusing the two warps by inverse error variance rather than by time (CMORPH-KF, IMERG V06).

One plugin, one module. See ``ingest.derive.methods`` for the contract.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    ERROR_SMOOTHING_SIGMA_CELLS,
    WARP_ERROR_FLOOR_PERCENT,
    _gaussian,
    _warp_nearest,
)
from ingest.derive.methods.baseline import TCDC_NOTE, BaselineMethod
from ingest.derive.methods.contract import InterpolationMethod, MethodContext, PairMotion
from ingest.derive.methods.harness import _interpolation_skill, admit, admit_reasons


class ErrorVarianceBlendMethod(BaselineMethod):
    """The same two warps, fused by inverse error variance instead of by time.

    CMORPH (Joyce et al., J. Hydrometeorol. 5(3), 2004) fuses a
    forward-propagated and a backward-propagated field by inverse time
    distance, ``w_fwd = (t2 - t)/(t2 - t1)`` - which is exactly the ``(1 - t,
    t)`` the shipped construction blends its two warps with. Joyce & Xie
    (*Kalman Filter-Based CMORPH*, J. Hydrometeorol. 12(6), 2011) replaced
    those fixed time weights with weights **inversely proportional to error
    variance**, and IMERG V06 (Tan et al., JTECH 36(12), 2019) uses squared
    correlation coefficients for the same purpose. Both are the principled
    generalisation of a time-linear blend: time distance is only a proxy for
    how wrong a propagated field is, and here the error can be measured
    directly instead of assumed.

    The two error variances are estimated per pixel from fields this
    derivation already computes, and they are genuinely two different
    measurements rather than one symmetric disagreement:

    - ``e0 = warp(frame0, F01) - frame1`` - how badly frame 0, carried the
      whole interval along its own forward flow, fails to explain frame 1. It
      lives in frame 1's coordinates.
    - ``e1 = warp(frame1, F10) - frame0`` - the same question of frame 1,
      carried back along the SEPARATELY derived backward field, in frame 0's
      coordinates.

    Each squared residual is carried to midpoint coordinates along the same
    half-interval displacement the display uses and then smoothed over
    ``ERROR_SMOOTHING_SIGMA_CELLS``, which is what makes it a local error
    variance rather than one pixel's noisy squared error - an unsmoothed
    per-pixel square is not an estimate of anything. The reliability is the
    inverse variance, floored by the already-measured warp-error scale so it
    can never divide by zero:

        ``v = tol^2 / (sigma^2 + tol^2)``,  ``tol = WARP_ERROR_FLOOR_PERCENT``

    which is ``1 / (sigma^2 + eps)`` up to the common factor that the
    normalisation below removes. No new constant is introduced: the percent
    error at which a warp was judged materially wrong (the floor of the
    retired development test) is the same quantity that sets where an error
    variance stops being small.

    The stored pair is ``vis0``/``vis1`` and the shader is ``visibility`` -
    the wire the retired linear-reliability ``visibility-blend`` introduced
    and this method inherited, so it needs **zero client changes**. The
    client already fuses two warps by a stored per-pixel weight pair; this
    one only computes that pair differently.

    Reduction to the baseline is exact and is the point: the fusion weights
    are ``w0 = (1 - t) v0`` and ``w1 = t v1``, normalised, so wherever the two
    error variances are equal - which includes the whole field when neither
    warp has a residual - the weights are exactly ``(1 - t, t)`` and this IS
    the shipped construction. It can only differ where the two warps
    measurably disagree about how wrong they are.

    Evidence: every displayed pixel remains a convex combination of two
    samples read from the two retrieved frames. The weights decide which
    retrieved sample carries the pixel; they never add content.
    """

    id = "error-variance-blend"
    title = "Inverse-error-variance fusion"
    summary = (
        "The same two warped frames, fused by inverse error variance rather than by the time "
        "fraction (Kalman Filter-Based CMORPH, Joyce & Xie 2011; IMERG V06, Tan et al. 2019): "
        "each frame's own warp is scored against the other frame, the squared residual is "
        "smoothed into a local error variance, and the more certain warp carries the pixel "
        "instead of the two being averaged into a double image. Exactly the shipped blend "
        "wherever the two variances agree, and applied only where the held-out score says it "
        "beats the time weights."
    )
    plain = (
        "Same slide, but where one picture explains the in-between better, it wins instead of "
        "the two being averaged into a ghost."
    )
    gap = "Only changes the mix, not what appears."
    notes = (
        "Inverse-error-variance fusion: Joyce & Xie 2011 (KF-CMORPH, J. Hydrometeorol. 12); "
        "IMERG V06 squared-correlation weights, Tan et al. 2019 (JTECH 36). " + TCDC_NOTE
    )
    #: Reused deliberately: the client construction is unchanged, only the
    #: weights that reach it are computed differently.
    shader = "visibility"
    extra_suffixes = ("vis0", "vis1")

    def __init__(self, *, use_prior: bool = False, use_error_variance: bool = True) -> None:
        super().__init__(use_prior=use_prior)
        #: Settled by measurement in `configure`. False publishes a weight pair
        #: of ones, which normalises to (1 - t, t) - the baseline fusion, on
        #: the same wire, rather than a second unmeasured construction.
        self.use_error_variance = use_error_variance

    @staticmethod
    def _error_variances(previous: Any, following: Any, flow01: Any, flow10: Any) -> tuple[Any, Any]:
        """``(sigma0^2, sigma1^2)``: each warp's local error variance, at the midpoint.

        Sign convention, settled against ``_warp_nearest`` rather than by
        inspection: ``_warp_nearest(field, D)`` reads ``field`` at ``p - D``.
        ``e0`` lives at frame 1's coordinates and a midpoint pixel ``p``
        corresponds to frame-1 location ``p + F01/2``, so it is pulled back
        with ``D = -F01/2``; ``e1`` lives at frame 0's coordinates, whose
        midpoint correspondence is ``p - F01/2``, so it is pulled with
        ``D = +F01/2``. Getting these backwards would swap the weights and
        make the method actively worse than the baseline, so a test pins the
        asymmetry's direction on a constructed occlusion.

        The square is taken BEFORE the warp and the smoothing after it, so
        what is smoothed is a squared error field in midpoint coordinates -
        a local second moment of the warp's error, which for a zero-mean
        residual is its variance.
        """
        import numpy  # noqa: PLC0415

        first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
        second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
        forward = numpy.asarray(flow01, dtype="float64")
        backward = numpy.asarray(flow10, dtype="float64")
        squared0 = numpy.square(_warp_nearest(first, forward) - second)
        squared1 = numpy.square(_warp_nearest(second, backward) - first)
        half = 0.5 * forward
        variance0 = numpy.maximum(_gaussian(_warp_nearest(squared0, -half), ERROR_SMOOTHING_SIGMA_CELLS), 0.0)
        variance1 = numpy.maximum(_gaussian(_warp_nearest(squared1, half), ERROR_SMOOTHING_SIGMA_CELLS), 0.0)
        return variance0, variance1

    @classmethod
    def _reliability_pair(cls, previous: Any, following: Any, flow01: Any, flow10: Any) -> tuple[Any, Any, Any, Any]:
        """``(v0, v1, sigma0^2, sigma1^2)`` - inverse variances, normalised to (0, 1]."""
        variance0, variance1 = cls._error_variances(previous, following, flow01, flow10)
        floor = WARP_ERROR_FLOOR_PERCENT**2
        return floor / (variance0 + floor), floor / (variance1 + floor), variance0, variance1

    def configure(self, context: MethodContext) -> tuple[InterpolationMethod, dict[str, Any]]:
        """Do the variance weights actually beat the time weights? Measured.

        The held-out reconstruction is scored twice on the same frames with
        the same motion - once fusing by inverse error variance, once by the
        baseline's time-linear weights, which this class expresses as the same
        construction with the estimator switched off - and the variance
        weights are kept only if ``harness.admit`` says they draw the better
        picture on the FIXED controls (crossfade and plain advection of the
        same frames), on mean error, structural similarity and sharpness
        together. Every number goes to provenance either way, including the
        reversed-flow ratio that used to decide, so "the variance weighting
        helped" is checkable rather than asserted.
        """
        settled, notes = super().configure(context)
        use_prior = bool(getattr(settled, "use_prior", False))
        build = type(self)
        with_variance = _interpolation_skill(
            context.frames,
            method=build(use_prior=use_prior, use_error_variance=True),
            dataset=context.dataset,
            variable=context.variable,
            interval_seconds=context.interval_seconds,
            indices=context.indices,
            cache=context.cache,
        )
        # The control is this same method with the estimator off, NOT
        # `BaselineMethod`: it shares the motion, the composite and the
        # advection fence, so the only thing that differs between the two
        # numbers is the weight pair. That is what makes it a controlled
        # comparison rather than two changes at once.
        with_time_weights = _interpolation_skill(
            context.frames,
            method=build(use_prior=use_prior, use_error_variance=False),
            dataset=context.dataset,
            variable=context.variable,
            interval_seconds=context.interval_seconds,
            indices=context.indices,
            cache=context.cache,
        )
        use_error_variance = admit(with_variance, with_time_weights)
        read = lambda skill, name: skill[name] if skill else None  # noqa: E731
        return build(use_prior=use_prior, use_error_variance=use_error_variance), {
            **notes,
            "error_variance_applied": bool(use_error_variance),
            "error_variance_floor_percent_squared": WARP_ERROR_FLOOR_PERCENT**2,
            # The gate's numbers: improvement over the FIXED crossfade.
            "held_out_improvement_with_error_variance": read(with_variance, "improvement_over_crossfade"),
            "held_out_improvement_with_time_weights": read(with_time_weights, "improvement_over_crossfade"),
            "held_out_improvement_over_advection_with_error_variance": read(with_variance, "improvement_over_advection"),
            "held_out_improvement_over_advection_with_time_weights": read(with_time_weights, "improvement_over_advection"),
            "held_out_ssim_with_error_variance": read(with_variance, "midpoint_ssim"),
            "held_out_ssim_with_time_weights": read(with_time_weights, "midpoint_ssim"),
            "held_out_sharpness_ratio_with_error_variance": read(with_variance, "midpoint_sharpness_ratio"),
            "held_out_sharpness_ratio_with_time_weights": read(with_time_weights, "midpoint_sharpness_ratio"),
            # The moving control, published beside the decision, not read by it.
            "held_out_improvement_over_reversed_flow_with_error_variance": read(
                with_variance, "improvement_over_reversed_flow"
            ),
            "held_out_improvement_over_reversed_flow_with_time_weights": read(
                with_time_weights, "improvement_over_reversed_flow"
            ),
            "error_variance_admission": admit_reasons(with_variance, with_time_weights),
            "skill": with_variance if use_error_variance else with_time_weights,
        }

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The baseline's motion exactly, plus the pair's inverse-variance weights.

        The derivation is deliberately unchanged: the claim under test is
        about the FUSION, so sharing the motion with the baseline is what
        makes the held-out comparison a controlled one.
        """
        import numpy  # noqa: PLC0415

        motions = super().motion(context)
        for position, motion in enumerate(motions):
            previous = context.frames[position]
            following = context.frames[position + 1]
            if not self.use_error_variance:
                # A weight pair of ones normalises to (1 - t, t) exactly, so a
                # method whose gate said no publishes the baseline fusion on
                # its own wire rather than publishing nothing.
                ones = numpy.ones(numpy.asarray(previous).shape, dtype="float64")
                motion.extra["vis0"] = ones
                motion.extra["vis1"] = ones.copy()
                motion.diagnostics["variance_asymmetry_mean"] = 0.0
                motion.diagnostics["error_variance_mean"] = 0.0
                motion.diagnostics["error_variance_applied"] = 0.0
                continue
            weight0, weight1, variance0, variance1 = self._reliability_pair(
                previous, following, motion.flow01, motion.flow10
            )
            motion.extra["vis0"] = weight0
            motion.extra["vis1"] = weight1
            floor = WARP_ERROR_FLOOR_PERCENT**2
            # How far the two error variances actually pull apart, scaled by
            # their own size so it reads the same on a quiet field and a busy
            # one. Where this is ~0 the method IS the baseline, so provenance
            # can say outright whether the fusion had anything to do.
            motion.diagnostics["variance_asymmetry_mean"] = float(
                numpy.mean(numpy.abs(variance0 - variance1) / (variance0 + variance1 + floor))
            )
            motion.diagnostics["error_variance_mean"] = float(numpy.mean(0.5 * (variance0 + variance1)))
            motion.diagnostics["weight_asymmetry_mean"] = float(numpy.mean(numpy.abs(weight0 - weight1)))
            motion.diagnostics["error_variance_applied"] = 1.0
        return motions

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        """The `visibility` shader branch, in Python. Keep the two in step.

        Byte for byte the fusion the ``visibility`` shader draws: the
        trajectory stays the baseline's ``D0 = t F01`` / ``D1 = -(1 - t)
        F01``; only the two blend weights are rewritten.

        Endpoint exactness is by construction as well as by the guards below:
        ``w0 = (1 - t) v0`` is zero at ``t = 1`` and ``w1 = t v1`` is zero at
        ``t = 0``, and ``v`` is strictly positive, so the surviving frame's
        normalised weight is exactly 1 at either end whatever the variances
        said.

        A pair carrying no weight fields - the harness's synthetic pairs, an
        artifact from another method - falls back to the time weights, which
        is the baseline, never to a guessed reliability.
        """
        import numpy  # noqa: PLC0415

        first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
        second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
        if t <= 0.0:
            return first
        if t >= 1.0:
            return second
        flow = numpy.asarray(motion.flow01, dtype="float64")
        stored0 = motion.extra.get("vis0")
        stored1 = motion.extra.get("vis1")
        if stored0 is None or stored1 is None or not self.use_error_variance:
            weight0 = numpy.full(first.shape, 1.0 - t)
            weight1 = numpy.full(first.shape, t)
        else:
            weight0 = (1.0 - t) * numpy.asarray(stored0, dtype="float64")
            weight1 = t * numpy.asarray(stored1, dtype="float64")
        # A stored zero pair (an off-grid pixel of the served texture) is an
        # absent measurement, not a reliability of zero: it falls back to the
        # time weights rather than dividing 0 by 0.
        total = weight0 + weight1
        blank = total <= 1e-9
        weight0 = numpy.where(blank, 1.0 - t, weight0)
        weight1 = numpy.where(blank, t, weight1)
        total = numpy.where(blank, 1.0, weight0 + weight1)
        warped = (
            weight0 / total * _warp_nearest(first, t * flow)
            + weight1 / total * _warp_nearest(second, -(1.0 - t) * flow)
        )
        plain = (1.0 - t) * first + t * second
        return plain + motion.advect_weight * (warped - plain)
