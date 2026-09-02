"""ECCC's own low-cloud repair for HRDPS, from the RH/T profile.

WHY THIS EXISTS
---------------
HRDPS's published total cloud is not a cloud fraction. ECCC's WEonG technical
note states the field is opacity-weighted::

    NT_HRDPS = TCC * [ 1 - exp(-0.1*(W3 + W4)) ],  NT_HRDPS in [0, 1]

with ``TCC`` the true cloud cover and ``W3``, ``W4`` the vertically integrated
(total) optical thickness in water and in ice respectively. Optically thin
cloud therefore reads near zero, and the published value is always <= the true
cover. ECCC then says in its own words that ``NT_HRDPS`` "has challenges
detecting low-level clouds in certain synoptic situations", and adds a
post-processed Low Level Cloud (LLC) field diagnosed from relative humidity::

    NT_WEonG = max[ NT_HRDPS ; LLC ],  NT_WEonG in [0, 1]

PRIMARY SOURCE, VERIFIED
------------------------
Both claims were checked against the primary PDF, not a summary:

    Environment and Climate Change Canada, "Weather Elements on grid (WEonG),
    Implementation of version 2.4.1, Technical Note", 23 June 2025, section
    7.9 "Sky State (cloud cover and opacity combined)", pp. 45-47.
    https://collaboration.cmc.ec.gc.ca/cmc/cmoi/product_guide/docs/tech_notes/technote_weong-hrdps_e.pdf
    Retrieved and read with ``pdftotext -layout`` on 2026-09-01 (WebFetch will
    not parse it; curl + pdftotext does).

Every constant below is transcribed from that section. Where this module
departs from it, the departure is named in the function that makes it.

Two differences from the second-hand summary this work started from, both in
step 4:

* The ice-covered-water zeroing is on the saturated layer's MAXIMUM
  temperature being **less than -15 degC**, not on a bare "T < -15 degC", and
  the note says "over an area of open water covered with ice".
* The -38 degC zeroing is "**less than or equal to** -38 degC", stated as
  indicative of homogeneous nucleation (the note classes the result as Ice
  Crystals, which is not a WEonG weather element at the time of writing).

The summary was otherwise accurate, including the RH->LLC table, which the
note gives as half-open intervals rather than as breakpoints.

WHICH RH? (this is not a detail)
--------------------------------
The thresholds below are numbers about a specific saturation convention. At
-20 degC ``e_s,water / e_s,ice ~ 1.21``, so air reading RH 0.85 over water
reads ~1.03 over ice - the difference between LLC 0.5 and LLC 1.0 under this
very table.

Measured on 2026-09-01 by reconstructing vapour pressure from each model's own
specific humidity on the same isobaric level (see
``ingest.grib.ECCC_RH_PHASE_BASIS`` and ``ingest.grib.GFS_RH_PHASE_BASIS``):

* HRDPS and RDPS divide by saturation over **liquid water at every
  temperature** - which is the convention this table is calibrated on, since
  WEonG runs on HRDPS.
* GFS divides by a **mixed-phase** saturation ramping linearly from ice at
  253.16 K to water at 273.16 K, and reads up to ~24 % higher below -25 degC.

So this module is for HRDPS (and, with the same convention, RDPS). Feeding it
GFS relative humidity would silently apply an ECCC-calibrated threshold to a
different quantity. ``assert_liquid_water_rh`` exists to make that a loud
failure rather than a quiet bias.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy

from ingest.grib import RH_PHASE_LIQUID_WATER

#: Technote section 7.9: "A saturated layer is defined as a layer where RH is
#: greater or equal to 0.74."
SATURATION_RH_THRESHOLD = 0.74

#: "a base under 2000 m AGL and a thickness greater or equal to 150 m".
MAX_LAYER_BASE_AGL_M = 2000.0
MIN_LAYER_THICKNESS_M = 150.0

#: Near-surface suppression, applied to RH *before* the vertical scan:
#: "(a) for each vertical level, RH decreases with height in the lowest 122 m
#: AGL"; "(b) for each vertical level in the first 930 m AGL when the dry bulb
#: temperature (TT) increases with height (for TTs below -15 degC only)".
RH_DECREASE_SUPPRESSION_DEPTH_M = 122.0
INVERSION_SUPPRESSION_DEPTH_M = 930.0
INVERSION_SUPPRESSION_MAX_TEMP_C = -15.0

#: "the maximum temperature in the saturated layer is less than or equal to
#: -38 degC and would be indicative of homogeneous nucleation".
HOMOGENEOUS_NUCLEATION_MAX_TEMP_C = -38.0

#: "a saturated layer has a maximum temperature less than -15 degC and lies
#: over an area of open water covered with ice".
ICE_COVERED_WATER_MAX_TEMP_C = -15.0

#: The published RH -> LLC table, transcribed as the note's half-open
#: intervals: ``[0.00-0.74) -> 0.0``, ``[0.74-0.78) -> 0.1``, ...,
#: ``[0.96-1.00] -> 1.0``. Stored as (lower bound inclusive, LLC) in
#: ascending order; the last bin's upper bound is closed.
RH_TO_LLC_TABLE: tuple[tuple[float, float], ...] = (
    (0.00, 0.0),
    (0.74, 0.1),
    (0.78, 0.2),
    (0.80, 0.3),
    (0.82, 0.4),
    (0.84, 0.5),
    (0.86, 0.6),
    (0.88, 0.7),
    (0.90, 0.8),
    (0.92, 0.9),
    (0.96, 1.0),
)

#: The opacity weighting the note gives for the published field. Recorded so a
#: reader of this module can see what ``NT_HRDPS`` is, and reproduced by
#: ``nt_hrdps_from_opacity`` for tests; nothing here inverts it, because
#: ``W3``/``W4`` are not published on Datamart.
OPACITY_EXTINCTION_COEFFICIENT = 0.1


def llc_from_max_rh(max_rh: Any) -> Any:
    """Map a saturated layer's maximum RH (a fraction) to the note's LLC.

    Pure lookup against ``RH_TO_LLC_TABLE``. Accepts a scalar or any array;
    NaN in gives NaN out rather than a fabricated 0.
    """
    rh = numpy.asarray(max_rh, dtype=float)
    bounds = numpy.array([bound for bound, _ in RH_TO_LLC_TABLE])
    values = numpy.array([value for _, value in RH_TO_LLC_TABLE])
    # searchsorted with 'right' gives the index of the bin whose lower bound
    # the value meets or exceeds; bins are half-open upward, exactly as
    # printed, and the top bin is closed at 1.00.
    index = numpy.clip(numpy.searchsorted(bounds, rh, side="right") - 1, 0, len(values) - 1)
    llc = values[index]
    return numpy.where(numpy.isnan(rh), numpy.nan, llc)


def nt_hrdps_from_opacity(true_cloud_cover: Any, water_optical_depth: Any, ice_optical_depth: Any) -> Any:
    """``TCC * [1 - exp(-0.1*(W3 + W4))]`` - the note's own definition of NT.

    Provided so the opacity weighting this module cites is executable rather
    than only quoted. It is NOT part of the diagnosis: HRDPS publishes NT, not
    ``TCC``/``W3``/``W4``, so the forward form cannot be inverted from what we
    ingest.
    """
    tcc = numpy.asarray(true_cloud_cover, dtype=float)
    total_depth = numpy.asarray(water_optical_depth, dtype=float) + numpy.asarray(ice_optical_depth, dtype=float)
    return tcc * (1.0 - numpy.exp(-OPACITY_EXTINCTION_COEFFICIENT * total_depth))


def combine_nt_weong(nt_hrdps: Any, llc: Any) -> Any:
    """``NT_WEonG = max[NT_HRDPS ; LLC]``, both fractions in [0, 1].

    Fractions, not percent: the note states the range explicitly and the
    RH->LLC table is in fractions, so the caller converts. ``NaN`` in either
    input propagates - an absent diagnosis must not silently become a zero
    that then loses the max.
    """
    a = numpy.asarray(nt_hrdps, dtype=float)
    b = numpy.asarray(llc, dtype=float)
    return numpy.maximum(a, b)


def suppress_near_surface_rh(
    height_agl_m: Sequence[Any],
    relative_humidity: Sequence[Any],
    temperature_c: Sequence[Any],
) -> list[Any]:
    """Step (a)/(b): force RH below threshold where the note says to.

    ``height_agl_m`` must be ascending. Returns a new RH profile; the inputs
    are not mutated.

    Both rules compare a level with the one below it, so the lowest level has
    no predecessor and is never suppressed - the note's "RH decreases with
    height" and "TT increases with height" are both differences.
    """
    heights = [numpy.asarray(level, dtype=float) for level in height_agl_m]
    rh = [numpy.array(level, dtype=float) for level in relative_humidity]
    temp = [numpy.asarray(level, dtype=float) for level in temperature_c]
    if not (len(heights) == len(rh) == len(temp)):
        raise ValueError("height, relative humidity and temperature profiles must have the same number of levels")

    below_threshold = SATURATION_RH_THRESHOLD - 1e-6
    for k in range(1, len(rh)):
        rh_decreases = rh[k] < rh[k - 1]
        in_shallow_layer = heights[k] <= RH_DECREASE_SUPPRESSION_DEPTH_M
        rule_a = in_shallow_layer & rh_decreases

        temp_increases = temp[k] > temp[k - 1]
        in_inversion_layer = heights[k] <= INVERSION_SUPPRESSION_DEPTH_M
        cold = temp[k] < INVERSION_SUPPRESSION_MAX_TEMP_C
        rule_b = in_inversion_layer & temp_increases & cold

        rh[k] = numpy.where(rule_a | rule_b, numpy.minimum(rh[k], below_threshold), rh[k])
    return rh


def weong_low_cloud_from_profile(
    height_agl_m: Sequence[Any],
    relative_humidity: Sequence[Any],
    temperature_c: Sequence[Any],
    *,
    over_ice_covered_water: Any = False,
) -> Any:
    """The technote's LLC diagnosis, over a real vertical profile.

    Faithful to section 7.9 given a profile with enough levels to define a
    layer: suppression, 3D vertical scan for RH >= 0.74, base/thickness test,
    the published RH->LLC table, and the two zeroing scenarios.

    Arguments are level-major sequences: ``height_agl_m[k]`` is the height of
    level ``k`` (ascending), and each element may be a scalar or an array of
    identical shape, so one call diagnoses a whole grid. ``relative_humidity``
    is a FRACTION over LIQUID WATER (see the module docstring).

    Where the note leaves a choice, this makes one and says so:

    * The note describes checking for "saturated layers with these two
      characteristics" and then using "the maximum RH in the layer", without
      saying what to do when more than one qualifies. This takes the largest
      LLC among the qualifying layers, which is the reading consistent with
      the field's purpose (adding cloud NT_HRDPS missed).
    * A layer's base and top are taken as the heights of its lowest and
      highest saturated levels, so its thickness is a level-spacing
      underestimate of the true saturated depth. On a coarse profile this
      makes the 150 m test strictly conservative, and a single-level layer has
      thickness 0 and can never qualify. That is a property of the input, not
      of the algorithm: it is why the ECCC adapters retrieve nine levels
      between 1015 and 850 hPa rather than the three steering levels, and why
      the documented three-level reduction this module used to carry was
      deleted once the real profile was ingested.
    """
    heights = [numpy.asarray(level, dtype=float) for level in height_agl_m]
    temp = [numpy.asarray(level, dtype=float) for level in temperature_c]
    rh = suppress_near_surface_rh(height_agl_m, relative_humidity, temperature_c)
    if not heights:
        raise ValueError("an empty profile diagnoses nothing")

    shape = numpy.broadcast(heights[0], rh[0], temp[0]).shape
    over_ice = numpy.broadcast_to(numpy.asarray(over_ice_covered_water, dtype=bool), shape)

    best_llc = numpy.zeros(shape, dtype=float)
    in_layer = numpy.zeros(shape, dtype=bool)
    layer_base = numpy.full(shape, numpy.nan)
    layer_top = numpy.full(shape, numpy.nan)
    layer_max_rh = numpy.full(shape, -numpy.inf)
    layer_max_temp = numpy.full(shape, -numpy.inf)

    def close_open_layers(best: Any) -> Any:
        thickness = layer_top - layer_base
        qualifies = in_layer & (layer_base < MAX_LAYER_BASE_AGL_M) & (thickness >= MIN_LAYER_THICKNESS_M)
        zeroed = (layer_max_temp <= HOMOGENEOUS_NUCLEATION_MAX_TEMP_C) | (
            over_ice & (layer_max_temp < ICE_COVERED_WATER_MAX_TEMP_C)
        )
        candidate = numpy.where(qualifies & ~zeroed, llc_from_max_rh(layer_max_rh), 0.0)
        return numpy.maximum(best, candidate)

    for k in range(len(rh)):
        saturated = numpy.broadcast_to(rh[k] >= SATURATION_RH_THRESHOLD, shape)
        height = numpy.broadcast_to(heights[k], shape)
        level_temp = numpy.broadcast_to(temp[k], shape)

        # A layer that ends at level k-1 is scored before level k can start a
        # new one, so two layers separated by a dry level stay two layers.
        ending = in_layer & ~saturated
        if ending.any():
            was_in_layer = in_layer
            in_layer = ending
            best_llc = close_open_layers(best_llc)
            in_layer = was_in_layer & saturated

        starting = saturated & ~in_layer
        layer_base = numpy.where(starting, height, layer_base)
        layer_max_rh = numpy.where(starting, numpy.broadcast_to(rh[k], shape), layer_max_rh)
        layer_max_temp = numpy.where(starting, level_temp, layer_max_temp)

        continuing = saturated & in_layer
        layer_max_rh = numpy.where(continuing, numpy.maximum(layer_max_rh, rh[k]), layer_max_rh)
        layer_max_temp = numpy.where(continuing, numpy.maximum(layer_max_temp, level_temp), layer_max_temp)

        layer_top = numpy.where(saturated, height, layer_top)
        in_layer = saturated

    best_llc = close_open_layers(best_llc)
    return best_llc


def assert_liquid_water_rh(variable: Any) -> None:
    """Refuse an RH field whose measured saturation phase is not liquid water.

    The table in this module is an ECCC calibration against HRDPS RH, which is
    liquid-water-based at every temperature. GFS RH is not the same quantity
    below freezing (mixed phase, up to ~24 % higher at -25 degC), so applying
    this table to it would be a quiet bias. This turns that into a raised
    exception.

    An undeclared field is refused too: the convention cannot be read off a
    GRIB message (0/1/1 codes no phase key), so silence means unknown, not
    liquid water.
    """
    convention = getattr(variable, "attrs", {}).get("rh_phase_convention")
    if convention != RH_PHASE_LIQUID_WATER:
        raise ValueError(
            "the WEonG LLC table is calibrated on relative humidity over liquid water; "
            f"this field declares rh_phase_convention={convention!r}. See the module "
            "docstring: GFS RH is mixed-phase and reads up to ~24 percent higher below "
            "-25 degC, which this table would turn into fabricated cloud."
        )
