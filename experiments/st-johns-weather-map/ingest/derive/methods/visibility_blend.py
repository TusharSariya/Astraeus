"""Per-pixel visibility fusion instead of a symmetric (1-t, t) blend (Super SloMo, softmax splatting).

One plugin, one module. See ``ingest.derive.methods`` for the contract.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    DEVELOPMENT_SIGMA_CELLS,
    DEVELOPMENT_TOLERANCE_PERCENT,
    _gaussian,
    _warp_nearest,
)
from ingest.derive.methods.contract import MethodContext, PairMotion
from ingest.derive.methods.baseline import BaselineMethod


class VisibilityBlendMethod(BaselineMethod):
    """Per-pixel visibility weights instead of the symmetric ``(1 - t, t)``.

    The shipped construction fuses the two warped frames with the time weights
    alone, so a cell where one warp is locally unreliable - an occlusion, a
    divergent flow, a cell that came from off-grid - is averaged with one where
    the other warp is fine. Averaging two warps that disagree is how a double
    image is manufactured, and a double image is what "looks like blending"
    describes. Super SloMo (Jiang et al., CVPR 2018, section 3.3) and softmax
    splatting (Niklaus & Liu, CVPR 2020, section 3) both report per-pixel
    visibility weighting as the single largest artifact reduction at motion
    boundaries: where one source is unreliable the other should carry the
    pixel outright.

    The visibility pair is measured photometrically, per frame, from fields
    this derivation already computes:

    - ``e0 = |warp(frame0, F01) - frame1|`` - how well frame 0, carried the
      whole interval along its own forward flow, explains frame 1. It lives in
      frame 1's coordinates.
    - ``e1 = |warp(frame1, F10) - frame0|`` - the same question of frame 1,
      carried back along the SEPARATELY derived backward field. It lives in
      frame 0's coordinates.

    These are genuinely two different measurements - two flows, two reference
    frames - which is what makes the resulting weights asymmetric at all; a
    single midpoint disagreement ``|A - B|`` is symmetric by construction and
    could only reproduce the display weight that already exists. Each residual
    is then carried to midpoint coordinates along the same half-interval
    displacement the display uses, smoothed over ``DEVELOPMENT_SIGMA_CELLS`` so
    the weights vary as gradually as the display weight does, and turned into a
    reliability by ``v = 1 / (1 + r / tolerance)`` with the tolerance being the
    already-measured ``DEVELOPMENT_TOLERANCE_PERCENT``. No new constant is
    introduced: the percent disagreement at which advection is judged not to
    explain the change is the same quantity here.

    ``v`` is strictly positive, so the normalised fusion below can never divide
    by zero, and where the two warps are equally reliable (``v0 == v1``, which
    includes the whole field when neither warp has a residual) the weights are
    exactly ``(1 - t, t)`` and this method IS the baseline. It can only differ
    where the two warps measurably disagree about their own reliability.

    Evidence: every displayed pixel is still a convex combination of two
    samples read from the two retrieved frames. The weights decide which
    retrieved sample carries the pixel; they never add content.
    """

    id = "visibility-blend"
    title = "Visibility-weighted fusion"
    summary = (
        "The same two warped frames, fused by per-pixel visibility rather than by the time "
        "fraction alone (Super SloMo, Jiang et al. 2018; softmax splatting, Niklaus & Liu 2020): "
        "where one frame's warp is measurably unreliable - an occlusion, a divergent flow, a cell "
        "that came from off-grid - the other frame carries the pixel instead of the two being "
        "averaged into a double image. Identical to the baseline wherever the two warps are "
        "equally reliable."
    )
    shader = "visibility"
    #: The two reliabilities, one per source frame, in [0, 1]. Stored rather
    #: than recomputed on the client: they cost two full-interval warps per
    #: pair, which is derive-side work, and the client only fuses.
    extra_suffixes = ("vis0", "vis1")

    @staticmethod
    def _visibility_pair(previous: Any, following: Any, flow01: Any, flow10: Any) -> tuple[Any, Any]:
        """``(v0, v1)``: how reliable each frame's warp is, at the midpoint.

        Sign convention, settled against ``_warp_nearest`` rather than by
        inspection: ``_warp_nearest(field, D)`` reads ``field`` at ``p - D``.
        ``e0`` lives at frame 1's coordinates and a midpoint pixel ``p``
        corresponds to frame-1 location ``p + F01/2``, so it is pulled back
        with ``D = -F01/2``; ``e1`` lives at frame 0's coordinates, whose
        midpoint correspondence is ``p - F01/2``, so it is pulled with
        ``D = +F01/2``. Getting these two backwards would swap the weights and
        make the method actively worse than the baseline, so a test pins the
        asymmetry's direction on a constructed occlusion.
        """
        import numpy  # noqa: PLC0415

        from ingest.derive.flow_ops import (  # noqa: PLC0415
            DEVELOPMENT_SIGMA_CELLS,
            DEVELOPMENT_TOLERANCE_PERCENT,
            _gaussian,
        )

        first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
        second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
        forward = numpy.asarray(flow01, dtype="float64")
        backward = numpy.asarray(flow10, dtype="float64")
        residual0 = numpy.abs(_warp_nearest(first, forward) - second)
        residual1 = numpy.abs(_warp_nearest(second, backward) - first)
        half = 0.5 * forward
        at_midpoint0 = _gaussian(_warp_nearest(residual0, -half), DEVELOPMENT_SIGMA_CELLS)
        at_midpoint1 = _gaussian(_warp_nearest(residual1, half), DEVELOPMENT_SIGMA_CELLS)
        tolerance = DEVELOPMENT_TOLERANCE_PERCENT
        visibility0 = 1.0 / (1.0 + numpy.maximum(at_midpoint0, 0.0) / tolerance)
        visibility1 = 1.0 / (1.0 + numpy.maximum(at_midpoint1, 0.0) / tolerance)
        return visibility0, visibility1

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The baseline's motion exactly, plus the pair's visibility fields.

        The derivation is deliberately unchanged: the claim under test is about
        the FUSION, so sharing the motion with the baseline is what makes the
        held-out comparison a controlled one rather than two changes at once -
        the same discipline ``intermediate-flow`` was landed under.
        """
        import numpy  # noqa: PLC0415

        motions = super().motion(context)
        for position, motion in enumerate(motions):
            visibility0, visibility1 = self._visibility_pair(
                context.frames[position], context.frames[position + 1], motion.flow01, motion.flow10
            )
            motion.extra["vis0"] = visibility0
            motion.extra["vis1"] = visibility1
            # How far the two reliabilities actually pull apart. Where this is
            # ~0 the method is the baseline, so provenance can say outright
            # whether the fusion had anything to do rather than asserting it.
            motion.diagnostics["visibility_asymmetry_mean"] = float(
                numpy.mean(numpy.abs(visibility0 - visibility1))
            )
        return motions

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        """The `visibility` shader branch, in Python. Keep the two in step.

        Only the fusion weights change. The trajectory is the baseline's
        ``D0 = t F01`` / ``D1 = -(1 - t) F01`` - exactly as the GLSL leaves
        ``d0``/``d1`` alone in the visibility branch and rewrites only the two
        blend weights - so where ``v0 == v1`` this returns the baseline's
        pixels bit for bit.

        Endpoint exactness is by construction as well as by the guards below:
        ``w0 = (1 - t) v0`` is zero at ``t = 1`` and ``w1 = t v1`` is zero at
        ``t = 0``, and ``v`` is strictly positive, so the normalised weight of
        the surviving frame is exactly 1 at either end whatever the residuals
        said.

        A pair carrying no visibility fields - the harness's synthetic pairs,
        an artifact from another method - falls back to the symmetric weights,
        which is the baseline, never to a guessed reliability.
        """
        import numpy  # noqa: PLC0415

        first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
        second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
        if t <= 0.0:
            return first
        if t >= 1.0:
            return second
        flow = numpy.asarray(motion.flow01, dtype="float64")
        visibility0 = motion.extra.get("vis0")
        visibility1 = motion.extra.get("vis1")
        if visibility0 is None or visibility1 is None:
            weight0 = numpy.full(first.shape, 1.0 - t)
            weight1 = numpy.full(first.shape, t)
        else:
            weight0 = (1.0 - t) * numpy.asarray(visibility0, dtype="float64")
            weight1 = t * numpy.asarray(visibility1, dtype="float64")
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


#: The fractions of an interval a held-out frame is reconstructed at. The
#: midpoint is the hardest case and the one the shipped thresholds were
#: measured against; the thirds are reached by holding a frame out of a
#: three-interval span, and they catch a construction that is right at the
#: middle and wrong on the way there - which a midpoint-only score cannot
#: see, and which is exactly what the reader watches during playback.
