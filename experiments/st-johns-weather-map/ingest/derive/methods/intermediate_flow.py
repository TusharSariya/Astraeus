"""Super SloMo's intermediate flow: both derived directions, not one inverted.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import _warp_nearest
from ingest.derive.methods.baseline import BaselineMethod
from ingest.derive.methods.contract import PairMotion

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
