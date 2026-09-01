"""Bandpass cascade: coarse structure advects, fine texture dissolves (S-PROG/ANVIL).

One plugin, one module. See ``ingest.derive.methods`` for the contract.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    _development_agreement,
    _display_weight,
    _gaussian,
    _warp_nearest,
)
from ingest.derive.methods.contract import Requirement, MethodContext, PairMotion
from ingest.derive.methods.baseline import BaselineMethod


#: Octaves of the à trous (undecimated) cascade: bands at dilation 1, 2, 4
#: and 8 grid cells, plus the residual the last one leaves. A separable
#: [1,2,1]/4 kernel at dilation 2^j is the starlet step pySTEPS' own cascade
#: decomposition descends from (Starck & Murtagh; Pulkkinen et al., GMD 2019),
#: and it reconstructs the frame EXACTLY - band sum plus residual is the
#: identity in floating point up to rounding - which is what lets a cascade
#: composite stay endpoint-exact and stay inside the evidence rule.
#:
#: Chosen by held-out skill over the six live rendered-grid cloud layers of
#: the 2026-09-01 06Z cycle (HRDPS/RDPS total cloud, GFS low/middle/high/total),
#: all held-out fractions, mean change against the baseline:
#:   1 octave  -0.033 MAE / +0.0015 SSIM, better on 3 of 6 layers
#:   2 octaves -0.105 MAE / +0.0038 SSIM, better on 5 of 6
#:   3 octaves -0.144 MAE / +0.0046 SSIM, better on 6 of 6
#:   4 octaves -0.161 MAE / +0.0048 SSIM, better on 6 of 6
#: Four is where every layer turns positive against the baseline; the fifth
#: buys +0.0002 SSIM for another stored float32 field per pair, which is not
#: worth its bytes. Depth is settled here so the class docstring's decisive
#: control is run against the best configuration this family has, rather than
#: against a straw one - and that control still refuses it.
CASCADE_OCTAVES = 4
#: The per-band weight is stored as a RATIO the client multiplies the pair's
#: display weight by, never as an absolute weight. That is not a compression
#: choice: the derive loop vetoes a variable that fails its held-out control
#: by zeroing the stored ``advect_weight``, and a method carrying its own
#: absolute weights would walk straight past that veto and keep advecting.
#: As a ratio, a zeroed display weight zeroes every band. Measured cost of the
#: ratio form against the same construction reading absolute weights: +0.002
#: MAE and +0.00006 SSIM over the six layers - below the noise, and the
#: SSIM sign is favourable.
#:
#: The floor keeps the ratio finite where the whole-field agreement collapsed,
#: and the cap keeps a band whose agreement is high in a cell the field
#: agreement calls hopeless from dominating; both bite rarely and the product
#: is clipped into [0, 1] afterwards either way.
CASCADE_AGREEMENT_FLOOR = 0.05
CASCADE_RATIO_CAP = 4.0


def _atrous_smooth(field: Any, dilation: int) -> Any:
    """Separable [1,2,1]/4 at ``dilation`` cells, clamped at the edges.

    Written out rather than delegated to ``_gaussian`` because this kernel has
    to be reproducible exactly, tap for tap, by whatever evaluates the cascade
    on the client: a composite that drifts from what is drawn mis-ranks its own
    method. Edge clamping matches GL's CLAMP_TO_EDGE for the same reason.
    """
    import numpy  # noqa: PLC0415

    out = numpy.asarray(field, dtype="float64")
    for axis in (0, 1):
        size = out.shape[axis]
        index = numpy.arange(size)
        lower = out.take(numpy.clip(index - dilation, 0, size - 1), axis=axis)
        upper = out.take(numpy.clip(index + dilation, 0, size - 1), axis=axis)
        out = 0.25 * lower + 0.5 * out + 0.25 * upper
    return out


def _cascade_bands(field: Any, octaves: int = CASCADE_OCTAVES) -> list[Any]:
    """``field`` split into ``octaves`` bandpasses plus its residual.

    Finest first, residual last. The list sums back to ``field``, so nothing
    downstream can add energy the retrieved frame did not carry: a band is a
    linear filter of retrieved pixels and the set of them is a partition of
    the frame, not a basis anything can be synthesised in.
    """
    import numpy  # noqa: PLC0415

    level = numpy.asarray(field, dtype="float64")
    bands: list[Any] = []
    for index in range(octaves):
        coarser = _atrous_smooth(level, 1 << index)
        bands.append(level - coarser)
        level = coarser
    bands.append(level)
    return bands


class ScaleCascadeMethod(BaselineMethod):
    """S-PROG/ANVIL's insight: advection is a per-SCALE question, not one number.

    The shipped display weight varies in space and is scale-blind - one
    advect-or-dissolve number per pixel, applied to the whole image. pySTEPS'
    S-PROG and ANVIL (Pulkkinen et al., GMD 2019) decompose into a spatial
    cascade precisely because scales behave differently in time, and ANVIL's
    stated advantage is predicting growth and decay WITHOUT smearing
    small-scale structure - our failure mode exactly.

    Applied to interpolation: each frame is split into an à trous cascade,
    every band is advected along the SAME pair flow, and each band is mixed
    against its own dissolve on its OWN measured weight - the development
    agreement of that band alone, gated by the same support the whole-field
    weight is gated by. Coarse structure, whose two half-interval warps land
    on the same picture, advects; fine texture, whose warps do not, dissolves.
    Nothing about that ordering is asserted: it is what the measurement
    returned (mean band weight fine -> coarse on GFS low cloud, 2026-09-01:
    0.714, 0.758, 0.819, 0.795 for the bands and the residual).

    The derivation is the baseline's unchanged, and every displayed pixel is
    still a sum of linear filters of the two retrieved frames. Endpoint
    exactness is by construction as well as by guard: at ``t = 0`` each band's
    warp displacement is zero, so every band returns its own share of
    ``previous`` whatever its weight says, and the bands sum back to the frame.

    What was tried and refused, because the honest record is the point.

    A per-band CONSTANT multiplier - the obvious reading of "coarse advects,
    fine dissolves" - lost monotonically over the same six layers. One
    constant multiplier of 0.5 on the finest band cost +0.27 MAE and -0.0095
    SSIM at the midpoint, three-octave geometric profiles cost up to +1.64 MAE
    and -0.084 SSIM, and the best admissible constant profile was the
    degenerate one that turns the cascade off. Dissolving fine texture by a
    fixed amount is worse than advecting it: a warp at least lands the texture
    near where it belongs, while a fixed dissolve ghosts it in two places at
    once. (Multipliers ABOVE 1 did score better, and are refused on the rule
    rather than the number: amplifying a band puts contrast on screen that no
    retrieved frame carried.)

    And the gain the measured per-band weight does show is NOT the scale
    hypothesis. The decisive control gives every band the same per-pixel
    ratio - the mean of the band ratios there - so the total weight is
    unchanged and only the scale dependence is removed. That scale-BLIND
    control beats this method on five of the six layers (mean over all
    held-out fractions, against the baseline: control -0.214 MAE / +0.00586
    SSIM, cascade -0.142 MAE / +0.00468 SSIM). The whole win is that a
    bandpass agrees with its own warp far more readily than the full field
    does against an absolute 25-percent tolerance, so the ratio comes out
    above 1 nearly everywhere and the display simply advects harder. Splitting
    that boost by scale costs some of it back. The cascade's own contribution,
    isolated, is negative - which is the answer to the question this method
    was written to ask, and it is not tuned further to get a different one.
    The useful residue is a finding for the bench rather than a method: on
    this data the shipped display weight under-advects, and that belongs to
    whoever owns ``_display_weight``, not here.

    Not enabled, for two independent reasons, either of which suffices. It
    does not beat its own control, above. And the client could not draw it if
    it did: evaluating a four-octave à trous pyramid at the warped sample
    point costs a nested dilated blur per fragment - the collapsed 1-D kernel
    for the fourth octave spans 31 taps, so of order 961 texture reads per
    frame per sample point - which no fragment shader here will do. Drawing it
    would need the band decomposition served as textures, which is the render
    path's to give and not this method's to take. Registering it disabled
    keeps the code and its measured score readable, which is what the bench's
    design says to do with a method that cannot earn its place; enabling it
    while the client silently drew the baseline instead would be the one thing
    the governing rule does not tolerate.
    """

    id = "scale-cascade"
    title = "Scale cascade (per-band advection weight)"
    summary = (
        "The same two frames and the same derived motion, split into a four-octave à trous "
        "cascade and recombined band by band, each band mixed between advection and a dissolve "
        "on its own measured agreement rather than on one number for the whole image "
        "(S-PROG/ANVIL, Pulkkinen et al. 2019); coarse structure advects while fine texture "
        "dissolves, and the bands sum back to the retrieved frame exactly."
    )
    shader = "cascade"
    #: One ratio field per band, finest first, residual last.
    extra_suffixes = tuple(f"cascade_w{index}" for index in range(CASCADE_OCTAVES + 1))
    #: Refused by its own scale-blind control, and undrawable by the client
    #: even if it had passed. See the class docstring for both numbers.
    enabled = False


    def requirements(self) -> list[Requirement]:
        """A client construction, which this method has no correct one-pass form for."""
        return [Requirement(
            name="a drawable client construction",
            met=False,
            detail=(
                "evaluating a four-octave a trous pyramid at the warped sample point is about 961 "
                "texture reads per fragment, and there is no correct one-pass shader for it. "
                "Drawing this needs the bands served as textures. Registered disabled rather than "
                "given a branch that silently drew the baseline under this method's name"
            ),
        )]

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The baseline's motion, plus one weight ratio per band per pair.

        The motion itself is deliberately untouched: the claim under test is
        about how the frames are RECOMBINED, so sharing the derivation is what
        makes this a controlled comparison rather than two changes at once.
        """
        import numpy  # noqa: PLC0415

        results = super().motion(context)
        for position, pair in enumerate(results):
            previous = numpy.nan_to_num(numpy.asarray(context.frames[position], dtype="float64"), nan=0.0)
            following = numpy.nan_to_num(numpy.asarray(context.frames[position + 1], dtype="float64"), nan=0.0)
            flow = numpy.asarray(pair.flow01, dtype="float64")
            whole = _development_agreement(previous, following, flow)
            bands = zip(_cascade_bands(previous), _cascade_bands(following))
            for index, (band_previous, band_following) in enumerate(bands):
                agreement = _development_agreement(band_previous, band_following, flow)
                pair.extra[f"cascade_w{index}"] = numpy.clip(
                    agreement / numpy.maximum(whole, CASCADE_AGREEMENT_FLOOR), 0.0, CASCADE_RATIO_CAP
                ).astype("float32")
        return results

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        """The `cascade` construction, in Python. Keep this and the client in step.

        Every band is warped along the same displacements the baseline uses -
        ``t F01`` from frame 0 and ``-(1 - t) F01`` from frame 1 - so the only
        difference from the shipped construction is the weight each band is
        mixed on. A pair carrying no ratios (a hand-built motion in a test, or
        an artifact from before this method) falls back to the pair's own
        display weight for every band, which IS the baseline: one honest rung
        down, never a weight invented to stand in for a missing measurement.
        """
        import numpy  # noqa: PLC0415

        first = numpy.nan_to_num(numpy.asarray(previous, dtype="float64"), nan=0.0)
        second = numpy.nan_to_num(numpy.asarray(following, dtype="float64"), nan=0.0)
        if t <= 0.0:
            return first
        if t >= 1.0:
            return second
        flow = numpy.asarray(motion.flow01, dtype="float64")
        display = numpy.asarray(motion.advect_weight, dtype="float64")
        composed = numpy.zeros_like(first)
        bands = zip(_cascade_bands(first), _cascade_bands(second))
        for index, (band_previous, band_following) in enumerate(bands):
            ratio = motion.extra.get(f"cascade_w{index}")
            # The stored field is a ratio ON the display weight, so the derive
            # loop's veto (advect_weight forced to zero) reaches every band.
            weight = display if ratio is None else numpy.clip(display * numpy.asarray(ratio, dtype="float64"), 0.0, 1.0)
            warped = (1.0 - t) * _warp_nearest(band_previous, t * flow) + t * _warp_nearest(
                band_following, -(1.0 - t) * flow
            )
            plain = (1.0 - t) * band_previous + t * band_following
            composed += plain + weight * (warped - plain)
        return composed


#: The fractions of an interval a held-out frame is reconstructed at. The
#: midpoint is the hardest case and the one the shipped thresholds were
#: measured against; the thirds are reached by holding a frame out of a
#: three-interval span, and they catch a construction that is right at the
#: middle and wrong on the way there - which a midpoint-only score cannot
#: see, and which is exactly what the reader watches during playback.
