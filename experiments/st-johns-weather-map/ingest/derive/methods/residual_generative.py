"""The computed residual, delivered on a timing the run's own physics decides.

One plugin, one module. See ``ingest.derive.methods`` for the contract, and
carve-out (d) of the governing rule for the licence this method uses and the
non-generative sibling does not.
"""

from __future__ import annotations

import datetime as _datetime
from typing import Any

from ingest.derive.flow_ops import (
    STEERING_LEVEL_BY_VARIABLE,
    _gaussian,
    _omega_tendency,
    _warp_linear,
)
from ingest.derive.methods.baseline import TCDC_NOTE
from ingest.derive.methods.contract import (
    InterpolationMethod,
    MethodContext,
    PairMotion,
    Requirement,
)
from ingest.derive.methods.harness import (
    HELD_OUT_FRACTIONS,
    _interpolation_skill,
    admit,
    admit_reasons,
)
from ingest.derive.methods.residual_advection import (
    RESIDUAL_CAP_PERCENT,
    RESIDUAL_GAIN,
    ResidualAdvectionMethod,
)

#: The gains this method is allowed to consider, in the order the greedy
#: search tries them. A quarter is the non-generative ceiling (see
#: ``ResidualAdvectionMethod``): at ``gain <= 1/4`` the delivered fraction
#: ``f(t) = t + 4 g t(1-t)`` stays inside [0, 1], so the drawn value never
#: leaves the bracket the two retrieved values form. Above it the display MAY
#: draw a value in neither frame, which is precisely the licence carve-out (d)
#: grants and precisely why this method is ``generative = True``.
GAIN_CANDIDATES = (0.25, 0.5, 0.75, 1.0)

#: Critical relative humidity, in percent, at which GEM's own Sundqvist
#: closure starts making cloud - ``b = 1 - sqrt((1-U)/(1-U0))`` (Sundqvist,
#: Berge & Kristjansson 1989, MWR 117; RPN physics doc v3.6 sec 6.3/8.2),
#: with ``RH_crit ~ 0.94`` at 2.5 km resolution (Morcrette 2012).
#:
#: TWO VALUES, because the two producers do not publish the same quantity.
#: HRDPS and RDPS divide by saturation over LIQUID WATER at every temperature;
#: GFS divides by a mixed-phase saturation ramping linearly from ice at
#: 253.16 K to water at 273.16 K, and reads up to ~24 % higher for identical
#: air below -25 degC (``ingest.grib.ECCC_RH_PHASE_BASIS`` /
#: ``GFS_RH_PHASE_BASIS``, both measured 2026-09-01 against each model's own
#: specific humidity). A threshold calibrated on one is not valid on the
#: other, so the convention declared in the variable's own attrs picks the
#: number and the choice is published as ``rh_phase_convention``.
CRITICAL_RH_LIQUID_WATER_PERCENT = 94.0
CRITICAL_RH_MIXED_PHASE_PERCENT = 88.0

#: Width of the timing sigmoid, in units of the interval. 0.15 of an hour is
#: about nine minutes: sharp enough that the crossing is visible as a
#: transition rather than a slow ramp, wide enough that a t* which is one
#: sixth of an interval wrong does not put the whole change on the wrong side
#: of the midpoint.
TIMING_WIDTH = 0.15

#: Daytime dissipation: a decaying cell under sun clears LATE and fast, not
#: evenly. Ghonima et al. 2016 (JAS 73) and Pauli et al. 2022 (QJRMS 148):
#: entrainment-driven thinning accelerates once the layer is thin enough for
#: shortwave to reach through it, so the bulk of the clearing happens in the
#: last third of the hour rather than at its start.
SOLAR_DISSIPATION_T_STAR = 0.65
SOLAR_DISSIPATION_WIDTH = 0.12

#: The scale split (Seed 2003 S-PROG; Bowler, Pierce & Seed 2006 QJRMS): the
#: large scales of a cloud field live far longer than the small ones, so the
#: coarse band of the residual is delivered LINEARLY (no re-timing claim is
#: defensible for a feature that outlives the interval) and only the fine band
#: takes a timing. Five cells is 12.5 km on HRDPS, the break the S-PROG
#: cascade puts between "advected" and "evolving" at hourly lead.
SCALE_SPLIT_SIGMA_CELLS = 5.0

#: The regime gate (Bley, Deneke & Senf 2016, JAMC 55): a motion-compensated
#: lag-1 correlation below this over a 9x9 box says the field has decorrelated
#: within the interval - convective, ~30 min decorrelation time - and no
#: timing derived from a smooth humidity field describes it. Those cells fall
#: back to the permitted advection with a zero envelope.
REGIME_CORRELATION_FLOOR = 0.5
REGIME_BOX_CELLS = 9

#: ``d ln RH/dt = (omega/p)(1 - kappa L/(R_v T))``. Dry-air Poisson constant,
#: latent heat of vaporisation (J kg-1) and the gas constant for water vapour
#: (J kg-1 K-1).
POISSON_KAPPA = 0.286
LATENT_HEAT_VAPORISATION = 2.5e6
GAS_CONSTANT_VAPOUR = 461.5

#: The omega closure's per-hour humidity multiplier is clamped into this band
#: (and its reciprocal for descent). Below the floor the forcing is too weak
#: to move a crossing time by anything the display can show and is treated as
#: absent rather than as a tiny nudge; above the ceiling the linearised
#: closure is outside the range it was derived for and a single noisy omega
#: cell would otherwise dominate the timing.
OMEGA_MULTIPLIER_FLOOR = 1.02
OMEGA_MULTIPLIER_CEILING = 1.20


def _envelope_basis() -> Any:
    """The 3x2 design matrix of ``[t(1-t), t^2(1-t)]`` at ``HELD_OUT_FRACTIONS``.

    The fit is over exactly the fractions the harness holds frames out at, so
    "fitted to the target" and "scored against the truth" are the same three
    instants. Nothing here is fitted to a picture - the target is a physical
    timing and the truth is a retrieved frame - which is the condition
    carve-out (d) makes non-negotiable.
    """
    import numpy  # noqa: PLC0415

    fractions = numpy.asarray(HELD_OUT_FRACTIONS, dtype="float64")
    return numpy.stack([fractions * (1.0 - fractions), fractions**2 * (1.0 - fractions)], axis=1)


def _fit_envelope(residual: Any, target: Any) -> tuple[Any, Any]:
    """Least-squares ``(a, b)`` per cell for ``t(1-t)(a + bt) ~ s (F*(t) - t)``.

    ``target`` is ``F*`` evaluated at ``HELD_OUT_FRACTIONS``, shape
    ``(3,) + grid``: the fraction of the cell's own measured change the option
    says should have been delivered by then. ``F*(0) = 0`` and ``F*(1) = 1``
    are properties of every target this module builds, and the envelope's own
    ``t(1-t)`` factor makes them structural on the drawn side whatever the fit
    returns - so endpoint exactness is algebra here too, exactly as it is for
    the non-generative sibling.

    The design matrix does not depend on the cell, so one 2x3 pseudo-inverse
    solves the whole grid: ``a`` and ``b`` are fixed linear combinations of
    the three residuals. That is what keeps a per-cell least-squares fit
    affordable inside a greedy search over six options.
    """
    import numpy  # noqa: PLC0415

    values = numpy.nan_to_num(numpy.asarray(residual, dtype="float64"), nan=0.0)
    fractions = numpy.asarray(HELD_OUT_FRACTIONS, dtype="float64").reshape((-1,) + (1,) * values.ndim)
    wanted = values[None, ...] * (numpy.nan_to_num(numpy.asarray(target, dtype="float64"), nan=0.0) - fractions)
    solver = numpy.linalg.pinv(_envelope_basis())
    a = numpy.tensordot(solver[0], wanted, axes=(0, 0))
    b = numpy.tensordot(solver[1], wanted, axes=(0, 0))
    return a, b


def _capped(a: Any, b: Any) -> tuple[Any, Any]:
    """``(a, b)`` scaled down TOGETHER until ``|t(1-t)(a + bt)| <= RESIDUAL_CAP_PERCENT``.

    Scaled together rather than clipped separately, because the two
    coefficients are not two quantities: they are one parabola's amplitude and
    its tilt, and clipping ``a`` alone would change WHEN the envelope peaks as
    a side effect of bounding HOW MUCH it delivers. Scaling preserves the
    timing the option decided and bounds only the amount.

    The bound is checked on the drawn curve over the whole interval, not at
    the fitted fractions, so a tilt that peaks between them cannot slip past -
    and the peak is found ANALYTICALLY rather than by sampling. A sampled
    maximum is always a slight underestimate, which would let the published
    cap be exceeded by whatever fell between two samples; the envelope is a
    cubic, so its stationary points are the roots of a quadratic and there is
    no reason to approximate them.
    """
    import numpy  # noqa: PLC0415

    coefficient_a = numpy.asarray(a, dtype="float64")
    coefficient_b = numpy.asarray(b, dtype="float64")
    # d/dt [ a t - (a - b) t^2 - b t^3 ] = 0  ->  3b t^2 + 2(a - b) t - a = 0
    quadratic = 3.0 * coefficient_b
    linear = 2.0 * (coefficient_a - coefficient_b)
    constant = -coefficient_a
    discriminant = numpy.maximum(linear * linear - 4.0 * quadratic * constant, 0.0)
    root = numpy.sqrt(discriminant)
    safe = numpy.where(numpy.abs(quadratic) > 1e-12, quadratic, 1.0)
    candidates = [
        numpy.where(numpy.abs(quadratic) > 1e-12, (-linear + root) / (2.0 * safe), 0.5),
        numpy.where(numpy.abs(quadratic) > 1e-12, (-linear - root) / (2.0 * safe), 0.5),
    ]
    peak = numpy.zeros_like(coefficient_a)
    for candidate in candidates:
        inside = numpy.clip(candidate, 0.0, 1.0)
        peak = numpy.maximum(
            peak, numpy.abs(inside * (1.0 - inside) * (coefficient_a + coefficient_b * inside))
        )
    scale = numpy.where(peak > RESIDUAL_CAP_PERCENT, RESIDUAL_CAP_PERCENT / numpy.maximum(peak, 1e-12), 1.0)
    return a * scale, b * scale


def _sigmoid_fraction(fractions: Any, t_star: Any, width: float) -> Any:
    """``F*(t) = sigmoid((t - t*)/w)`` renormalised so ``F*(0) = 0`` and ``F*(1) = 1``.

    The renormalisation is what makes the timing admissible at all: a bare
    sigmoid delivers neither 0 at the start nor 1 at the end, so it would
    change the pair's NET change rather than only its timing - and the net
    change is the one thing two retrieved frames fix and no construction may
    touch.
    """
    import numpy  # noqa: PLC0415

    def sigmoid(value: Any) -> Any:
        return 1.0 / (1.0 + numpy.exp(-numpy.clip(value, -50.0, 50.0)))

    star = numpy.asarray(t_star, dtype="float64")
    raw = sigmoid((numpy.asarray(fractions, dtype="float64") - star) / width)
    low = sigmoid(-star / width)
    high = sigmoid((1.0 - star) / width)
    return (raw - low) / numpy.maximum(high - low, 1e-9)


def _gain_fraction(fractions: Any, gain: float) -> Any:
    """``F*(t) = t + 4 g t(1-t)``: the plain gain option's delivered fraction."""
    import numpy  # noqa: PLC0415

    t = numpy.asarray(fractions, dtype="float64")
    return t + 4.0 * gain * t * (1.0 - t)


def _solar_elevation_degrees(latitude: Any, longitude: Any, when: _datetime.datetime) -> Any:
    """Solar elevation in degrees over a lat/lon grid at one UTC instant.

    Spencer's (1971) Fourier declination and equation of time, then the
    standard hour-angle geometry - the NOAA solar-position calculator's own
    formulation, kept in this module because the only question asked of it is
    "is the sun up", to about a tenth of a degree, and pulling an ephemeris
    dependency in for a boolean would be the larger claim. No refraction and
    no parallax: both are tenths of a degree at the horizon and neither
    changes a daylight test on an hourly interval.

    ``longitude`` is degrees EAST (the datasets' own convention).
    """
    import numpy  # noqa: PLC0415

    moment = when if when.tzinfo is None else when.astimezone(_datetime.timezone.utc).replace(tzinfo=None)
    day_of_year = moment.timetuple().tm_yday
    hour = moment.hour + moment.minute / 60.0 + moment.second / 3600.0
    angle = 2.0 * numpy.pi / 365.0 * (day_of_year - 1 + (hour - 12.0) / 24.0)
    declination = (
        0.006918
        - 0.399912 * numpy.cos(angle)
        + 0.070257 * numpy.sin(angle)
        - 0.006758 * numpy.cos(2 * angle)
        + 0.000907 * numpy.sin(2 * angle)
        - 0.002697 * numpy.cos(3 * angle)
        + 0.001480 * numpy.sin(3 * angle)
    )
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * numpy.cos(angle)
        - 0.032077 * numpy.sin(angle)
        - 0.014615 * numpy.cos(2 * angle)
        - 0.040849 * numpy.sin(2 * angle)
    )
    lon = numpy.asarray(longitude, dtype="float64")
    lat = numpy.radians(numpy.asarray(latitude, dtype="float64"))
    true_solar_minutes = hour * 60.0 + equation_of_time + 4.0 * lon
    hour_angle = numpy.radians(true_solar_minutes / 4.0 - 180.0)
    sine = numpy.sin(lat) * numpy.sin(declination) + numpy.cos(lat) * numpy.cos(declination) * numpy.cos(hour_angle)
    return numpy.degrees(numpy.arcsin(numpy.clip(sine, -1.0, 1.0)))


def _local_correlation(first: Any, second: Any, box: int = REGIME_BOX_CELLS) -> Any:
    """Pearson correlation of two fields inside a ``box`` x ``box`` neighbourhood.

    Where both neighbourhoods are flat there is no structure to correlate and
    nothing to gate, so the correlation is reported as 1 (ungated) rather than
    as an undefined 0/0 that would zero the envelope over every uniform patch.
    """
    import cv2  # noqa: PLC0415
    import numpy  # noqa: PLC0415

    a = numpy.nan_to_num(numpy.asarray(first, dtype="float32"), nan=0.0)
    b = numpy.nan_to_num(numpy.asarray(second, dtype="float32"), nan=0.0)
    size = (box, box)
    mean_a = cv2.blur(a, size)
    mean_b = cv2.blur(b, size)
    covariance = cv2.blur(a * b, size) - mean_a * mean_b
    variance_a = numpy.maximum(cv2.blur(a * a, size) - mean_a * mean_a, 0.0)
    variance_b = numpy.maximum(cv2.blur(b * b, size) - mean_b * mean_b, 0.0)
    flat = (variance_a < 1e-6) & (variance_b < 1e-6)
    correlation = covariance / numpy.sqrt(numpy.maximum(variance_a * variance_b, 1e-12))
    return numpy.where(flat, 1.0, numpy.clip(correlation, -1.0, 1.0)).astype("float64")


def _level_pair(dataset: Any, variable: str, template: str, indices: tuple[int, ...], shape: tuple[int, int]) -> Any | None:
    """The named per-level field at the pair's two instants, or None.

    The lookup pattern of ``flow_ops._steering_prior``: the stratum's own
    steering level, the variable's two endpoint values on the artifact's own
    time axis, and ``None`` - never a zero - for anything absent or the wrong
    shape. An ingredient this deployment does not have makes the option a
    no-op that says so, which is the rule carve-out (d) states for a
    generative construction whose ingredient is missing.
    """
    import numpy  # noqa: PLC0415

    level = STEERING_LEVEL_BY_VARIABLE.get(variable)
    if level is None or dataset is None or len(indices) < 2:
        return None
    name = template.format(level=level)
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
        return numpy.nan_to_num(pair, nan=0.0)
    except Exception:
        return None


def _grid_latlon(dataset: Any, shape: tuple[int, int]) -> tuple[Any, Any] | None:
    """The grid's own latitude/longitude as 2-D arrays, or None."""
    import numpy  # noqa: PLC0415

    if dataset is None:
        return None
    coords = getattr(dataset, "coords", {})
    lat_name = "latitude" if "latitude" in coords else "lat"
    lon_name = "longitude" if "longitude" in coords else "lon"
    if lat_name not in coords or lon_name not in coords:
        return None
    try:
        lat = numpy.asarray(dataset[lat_name].values, dtype="float64")
        lon = numpy.asarray(dataset[lon_name].values, dtype="float64")
        if lat.ndim == 1:
            lat, lon = numpy.meshgrid(lat, lon, indexing="ij")
        return (lat, lon) if lat.shape == shape else None
    except Exception:
        return None


def _midpoint_time(dataset: Any, indices: tuple[int, ...]) -> _datetime.datetime | None:
    """The instant halfway between the pair's two retrieved frames, UTC."""
    import numpy  # noqa: PLC0415

    if dataset is None or len(indices) < 2:
        return None
    coords = getattr(dataset, "coords", {})
    name = next((candidate for candidate in ("valid_time", "time") if candidate in coords), None)
    if name is None:
        return None
    try:
        values = numpy.asarray(dataset[name].values)
        if values.shape[0] <= max(indices):
            return None
        first = numpy.datetime64(values[indices[0]], "s").astype("int64")
        last = numpy.datetime64(values[indices[1]], "s").astype("int64")
        return _datetime.datetime.fromtimestamp((first + last) // 2, tz=_datetime.timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def _critical_rh_percent(dataset: Any, variable: str) -> tuple[float, str]:
    """``(RH_crit, convention)`` for this run's own humidity convention.

    The threshold follows the DECLARED convention rather than the source id,
    because the declaration is the measured fact (``ingest.grib.declare_rh_phase``)
    and the source id is a name. An undeclared field is treated as
    mixed-phase, the more conservative reading: the mixed-phase threshold is
    the lower one, so an unknown convention crosses earlier and cannot invent
    a crossing that a liquid-water field would not have had.
    """
    level = STEERING_LEVEL_BY_VARIABLE.get(variable)
    name = f"relative_humidity_{level}hPa" if level else None
    convention = ""
    if dataset is not None and name in getattr(dataset, "data_vars", {}):
        convention = str(getattr(dataset[name], "attrs", {}).get("rh_phase_convention", ""))
    if convention == "liquid_water":
        return CRITICAL_RH_LIQUID_WATER_PERCENT, convention
    return CRITICAL_RH_MIXED_PHASE_PERCENT, convention or "undeclared"


def _crossing_time(rh_first: Any, rh_last: Any, threshold: float, bow: Any = None) -> Any:
    """When inside the interval humidity crosses ``threshold``; NaN where it does not.

    Humidity is carried linearly between the pair's two instants,
    ``RH(t) = RH0 + t (RH1 - RH0)``, optionally bowed by the omega closure's
    ``+ c t(1-t)`` (option 3) - a term that is zero at both retrieved instants
    by construction, so it can move the crossing WITHOUT contradicting either
    retrieved humidity.

    With the bow the crossing solves ``-c t^2 + (d + c) t + (RH0 - U0) = 0``
    and the FIRST root inside (0, 1) is taken: the display shows the interval
    once, so the moment cloud starts existing is the one it can express.
    """
    import numpy  # noqa: PLC0415

    first = numpy.asarray(rh_first, dtype="float64")
    last = numpy.asarray(rh_last, dtype="float64")
    difference = last - first
    offset = first - threshold
    curvature = numpy.zeros_like(first) if bow is None else numpy.asarray(bow, dtype="float64")

    linear = numpy.where(numpy.abs(difference) > 1e-9, offset / numpy.where(numpy.abs(difference) > 1e-9, -difference, 1.0), numpy.nan)

    # -c t^2 + (d + c) t + offset = 0  ->  c t^2 - (d + c) t - offset = 0
    a = curvature
    b = -(difference + curvature)
    c = -offset
    discriminant = b * b - 4.0 * a * c
    quadratic_ok = (numpy.abs(a) > 1e-12) & (discriminant >= 0.0)
    root = numpy.sqrt(numpy.maximum(discriminant, 0.0))
    denominator = numpy.where(numpy.abs(a) > 1e-12, 2.0 * a, 1.0)
    low = (-b - root) / denominator
    high = (-b + root) / denominator
    early = numpy.minimum(low, high)
    late = numpy.maximum(low, high)
    inside = lambda value: (value > 0.0) & (value < 1.0)  # noqa: E731
    quadratic = numpy.where(inside(early), early, numpy.where(inside(late), late, numpy.nan))

    crossing = numpy.where(quadratic_ok, quadratic, linear)
    return numpy.where(inside(crossing), crossing, numpy.nan)


def _omega_bow(dataset: Any, variable: str, indices: tuple[int, ...], shape: tuple[int, int], rh_first: Any, rh_last: Any) -> tuple[Any, float]:
    """``(c, reached)``: the humidity bow the run's own vertical velocity implies.

    ``d ln RH/dt = (omega/p)(1 - kappa L/(R_v T))`` (the closure the retired
    carve-out (c) rested on, now the timing term of a carve-out (d)
    construction). With ``kappa L/(R_v T) ~ 5.7`` at these levels the bracket
    is about -4.7, so ASCENT (omega negative, since omega is dp/dt) moistens
    and descent dries - the sign falls out of the units rather than being
    asserted.

    What is read is ``omega_1 - omega_0`` (``flow_ops._omega_tendency``): a
    mean says only which way the forcing points, and a TIMING needs to know
    whether the forcing was stronger at the start of the interval or at its
    end. The implied per-hour multiplier is clamped into
    ``OMEGA_MULTIPLIER_FLOOR..CEILING`` and zeroed below the floor, so the
    published bow is always a forcing the closure is valid for.

    ``c`` is set so the mid-interval departure from the linear humidity is
    half the interval's implied change: ``c/4 = RH_mid (m - 1)/2``. Absent
    omega is an absent bow (zeros) and ``reached = 0``, never a small one.
    """
    import numpy  # noqa: PLC0415

    tendency = _omega_tendency(dataset, variable, (indices[0], indices[1]), shape)
    if tendency is None:
        return numpy.zeros(shape, dtype="float64"), 0.0
    level = STEERING_LEVEL_BY_VARIABLE.get(variable)
    temperature = _level_pair(dataset, variable, "temperature_{level}hPa", indices, shape)
    if temperature is None:
        return numpy.zeros(shape, dtype="float64"), 0.0
    # Stored in degC (`CANONICAL_FIELD_UNITS`); the closure is in kelvin.
    kelvin = numpy.maximum(numpy.mean(temperature, axis=0) + 273.15, 180.0)
    pressure_pa = float(level) * 100.0
    bracket = 1.0 - POISSON_KAPPA * LATENT_HEAT_VAPORISATION / (GAS_CONSTANT_VAPOUR * kelvin)
    rate = (numpy.asarray(tendency, dtype="float64") / pressure_pa) * bracket
    logarithm = rate * 3600.0
    ceiling = numpy.log(OMEGA_MULTIPLIER_CEILING)
    floor = numpy.log(OMEGA_MULTIPLIER_FLOOR)
    clamped = numpy.clip(logarithm, -ceiling, ceiling)
    clamped = numpy.where(numpy.abs(clamped) < floor, 0.0, clamped)
    multiplier = numpy.exp(clamped)
    middle = 0.5 * (numpy.asarray(rh_first, dtype="float64") + numpy.asarray(rh_last, dtype="float64"))
    bow = 2.0 * middle * (multiplier - 1.0)
    return bow, float(numpy.mean(numpy.abs(clamped) > 0.0))


class ResidualGenerativeMethod(ResidualAdvectionMethod):
    """The same computed residual, timed by the run's own physics - and allowed to leave the bracket.

    The non-generative sibling (``residual-advection``) delivers the measured
    residual on one fixed symmetric envelope at a quarter-gain ceiling, which
    keeps every drawn value inside the interval the two retrieved values
    bracket. That ceiling is also its limit: cloud that the run's own humidity
    says formed in the last twenty minutes of an hour is still drawn as
    forming smoothly across the whole of it, and the delivered amount can
    never exceed what a convex mix of the two frames contains.

    This method removes both restrictions, under carve-out (d) and only under
    its conditions. The wire is identical - the same ``res_s`` diagnostic and
    the same two envelope coefficients ``gen_a``/``gen_b``, evaluated by the
    same ``residual-advection`` shader as ``t(1-t)(a + b t)`` - so nothing
    about what the client draws changes. What changes is how ``(a, b)`` are
    chosen:

        F*(t)      the fraction of THIS cell's own measured change that a
                   cited physical construction says had been delivered by t
        (a, b)     least squares over HELD_OUT_FRACTIONS of
                   t(1-t)(a + b t)  against  s (F*(t) - t)
        |e|        scaled down, a and b together, to RESIDUAL_CAP_PERCENT

    ``t(1-t)`` still vanishes at both ends, so every retrieved instant still
    shows its own retrieved frame untouched - endpoint exactness is algebra
    here exactly as it is for the sibling, and it is what makes a generative
    term admissible at all. And the net change across the pair is still the
    pair's own: every ``F*`` this module builds is renormalised to
    ``F*(0) = 0, F*(1) = 1``, so the timing decides WHEN, never WHAT.

    WHAT IS GENERATED, stated plainly because the disclosure has to be true.
    Two things this method may do that the sibling may not:

    - the gain may exceed 1/4 (up to 1.0), so the delivered fraction ``f(t)``
      may leave [0, 1] in the interior of the interval;
    - a timing option may put ``F*(t)`` outside [0, 1] near a sharp crossing.

    Either way the drawn value may leave the bracket the two retrieved values
    form - it may show more cloud than either frame has, or less. That is a
    value in neither frame, it is GENERATED, and it is disclosed as such on
    the map with the option names that produced it. It is bounded three ways
    even so: the residual is capped, the envelope is capped, and the composite
    is clipped to the percent scale.

    SIX OPTIONS, EACH ONE A CITED CONSTRUCTION, each admitted or refused on
    its own measurement by ``harness.admit`` against the FIXED controls (a
    plain crossfade and a plain advection of the same two frames):

    1. ``gain`` in {0.25, 0.5, 0.75, 1.0} - the symmetric envelope, stronger
       than the sibling's ceiling allows.
    2. ``rh_timing`` - GEM's own Sundqvist closure. Cloud fraction goes as
       ``b = 1 - sqrt((1-U)/(1-U0))`` (Sundqvist, Berge & Kristjansson 1989,
       MWR 117; RPN physics doc v3.6 sec 6.3/8.2), so the moment the run's own
       RH at the stratum's steering level crosses ``U0`` is the moment its own
       physics makes cloud. That crossing time becomes a sigmoid ``F*``.
    3. ``omega_shift`` - the same crossing, moved by the run's own vertical
       velocity through ``d ln RH/dt = (omega/p)(1 - kappa L/(R_v T))``.
    4. ``solar_dissipation`` - decaying cells in daylight clear late and fast
       rather than evenly (Ghonima et al. 2016 JAS 73; Pauli et al. 2022
       QJRMS 148).
    5. ``scale_split`` - S-PROG's scale-dependent lifetimes (Seed 2003;
       Bowler, Pierce & Seed 2006 QJRMS): the coarse band of the residual is
       delivered linearly, only the fine band is re-timed.
    6. ``regime_gate`` - a motion-compensated lag-1 correlation below 0.5 over
       a 9x9 box says the field decorrelated inside the interval (Bley, Deneke
       & Senf 2016, JAMC 55) and no humidity-derived timing describes it;
       those cells get a zero envelope and fall back to the advection.

    The whole construction is spatially varying and non-linear in time, which
    is the one quantitative both-endpoints result the literature actually has:
    Vandal & Nemani 2021 (IEEE TNNLS, arXiv:1907.12013) measured -57 % RMSE
    against linear interpolation at the midpoint on GOES band 13 for exactly
    that. Nothing here is learned from the pictures it produces; every
    ingredient is the same model run's own retrieved field.

    THE OPTIONS MAY ALL BE REFUSED, and that is a result rather than a
    failure. ``configure`` starts from the sibling's settled construction and
    adds options greedily, keeping only what ``admit`` says draws a better
    picture on both mean error and structural similarity without buying either
    with blur. A layer where every option is refused publishes
    ``applied = False`` and every option's score, draws exactly what
    ``residual-advection`` draws, and says so on the map.
    """

    id = "residual-generative"
    title = "Computed development residual, timed by the run's own physics (GENERATED)"
    plain = (
        "Same slide, plus we measure how much cloud formed or dissolved in place and draw that "
        "happening; switches decide WHEN in the hour: humidity reaching saturation, rising air, "
        "daytime burn-off."
    )
    gap = (
        "Cloud that forms and clears entirely inside one hour is invisible; timing is "
        "physics-based and measured against real frames, not observed. This entry may draw a "
        "value that is in neither picture - the strength is allowed past the quarter bound that "
        "keeps the sibling inside the two frames, so a moment mid-hour can show more cloud than "
        "either real frame has, or less. That is disclosed on the map as GENERATED."
    )
    notes = (
        "Computed residual s = warp(I1, backward) - I0: NowcastNet's source term in dx/dt + "
        "(v.grad)x = s (Zhang et al. 2023, Nature 619); Tatsubori et al. 2022 (arXiv:2203.01277) "
        "third flow channel; computed, not learned, because both endpoints are held. Timing: "
        "humidity threshold crossing under GEM's own Sundqvist closure b = 1 - sqrt((1-U)/(1-U0)) "
        "(Sundqvist, Berge & Kristjansson 1989 MWR 117; RPN physics doc v3.6 sec 6.3/8.2), "
        "RH_crit ~0.94 at 2.5 km (Morcrette 2012); omega via d ln RH/dt = (omega/p)(1 - kappa "
        "L/(R_v T)); daytime dissipation acceleration (Ghonima et al. 2016 JAS; Pauli et al. 2022 "
        "QJRMS 148); scale-split lifetimes (Seed 2003 S-PROG; Bowler, Pierce & Seed 2006 QJRMS); "
        "spatially varying non-linear time weighting validated on GOES (Vandal & Nemani 2021 IEEE "
        "TNNLS, arXiv:1907.12013). Regime gate from motion-compensated lag-1 correlation (Bley, "
        "Deneke & Senf 2016 JAMC 55: ~30 min decorrelation for convective fields). Gated on fixed "
        "controls with sharpness and PSD ratio (Ravuri et al. 2021 Nature 597; Harris et al. "
        "2001; Roberts & Lean 2008 FSS; Wernli et al. 2008 SAL). GENERATED: the envelope's gain "
        "is allowed past the quarter bound that keeps the non-generative sibling inside the "
        "bracket the two retrieved frames form, so a drawn value may be in neither frame. It is "
        "still zero at both real instants by construction, still capped, and still clipped to the "
        "percent scale. " + TCDC_NOTE
    )
    summary = (
        "The same computed growth-and-decay residual as its non-generative sibling, delivered on "
        "the timing the same model run's own physics implies rather than on one fixed symmetric "
        "bump: humidity crossing GEM's own critical value, vertical velocity moving that "
        "crossing, daytime burn-off clearing late, large scales delivered linearly while small "
        "ones are re-timed, and a decorrelation gate that falls back to plain advection where no "
        "smooth timing describes the field. Every option is admitted per variable only where it "
        "reconstructs held-out frames better than a plain fade AND a plain advection, on error, "
        "structure and sharpness together. Because the strength is allowed past the bound that "
        "keeps the sibling inside the two retrieved values, a drawn moment may show cloud that is "
        "in neither frame - GENERATED, disclosed, and off by default."
    )
    shader = "residual-advection"
    generative = True
    enabled = True
    extra_suffixes = ("res_s", "gen_a", "gen_b")
    vetoed_suffixes = ("res_s", "gen_a", "gen_b")

    def __init__(
        self,
        *,
        use_prior: bool = False,
        use_residual: bool = True,
        negate_residual: bool = False,
        gain: float = RESIDUAL_GAIN,
        rh_timing: bool = False,
        omega_shift: bool = False,
        solar_dissipation: bool = False,
        scale_split: bool = False,
        regime_gate: bool = False,
    ) -> None:
        super().__init__(use_prior=use_prior, use_residual=use_residual, negate_residual=negate_residual)
        self.gain = float(gain)
        self.rh_timing = bool(rh_timing)
        self.omega_shift = bool(omega_shift)
        self.solar_dissipation = bool(solar_dissipation)
        self.scale_split = bool(scale_split)
        self.regime_gate = bool(regime_gate)

    def requirements(self) -> list[Requirement]:
        """The two run fields the timing reads, answered by the last derive's own diagnostics.

        Neither can be answered here: this call has no variable and no
        dataset, and the honest answer for both is per variable - the humidity
        and the vertical velocity live in the surface artifact being derived,
        at the level that variable steers on. So both are reported as present
        with the diagnostic that actually answers them named, and the menu
        shows the reader what the last derive found rather than a placeholder
        that would read as a verdict. Both absent is not a broken method: the
        options that read them are then no-ops, the construction reduces to
        the permitted advection plus the sibling's residual, and it says so.
        """
        return [
            Requirement(
                name="relative humidity at the steering level",
                met=True,
                detail=(
                    "the timing options read the run's own RH at the stratum's steering level "
                    "(850/700/500 hPa); rh_reached in the last derive says how much of the field "
                    "actually crossed the critical value inside the interval, and a cell that "
                    "never crosses keeps the plain gain envelope"
                ),
                diagnostic="rh_reached",
            ),
            Requirement(
                name="vertical velocity at the steering level",
                met=True,
                detail=(
                    "omega at the same level moves the humidity crossing through d ln RH/dt = "
                    "(omega/p)(1 - kappa L/(R_v T)); omega_reached in the last derive says how "
                    "much of the field carried a forcing strong enough for the closure to be "
                    "applied at all, and absent omega is a no-op rather than a zero shift"
                ),
                diagnostic="omega_reached",
            ),
        ]

    # ---------- the envelope ----------

    def _target(self, context: MethodContext, pair_indices: tuple[int, ...], residual: Any) -> tuple[Any, dict[str, float], dict[str, Any]]:
        """``F*`` at ``HELD_OUT_FRACTIONS`` for the accepted options, plus diagnostics.

        Built in the order the options are decided, each one overriding the
        previous where its own precondition holds and leaving it alone where
        it does not. That is what makes the greedy search meaningful: adding
        an option can only change the cells that option actually speaks about.
        """
        import numpy  # noqa: PLC0415

        shape = numpy.asarray(residual).shape
        fractions = numpy.asarray(HELD_OUT_FRACTIONS, dtype="float64").reshape((-1,) + (1,) * len(shape))
        target = numpy.broadcast_to(_gain_fraction(fractions, self.gain), (len(HELD_OUT_FRACTIONS),) + shape).copy()
        diagnostics: dict[str, float] = {"rh_reached": 0.0, "omega_reached": 0.0}
        notes: dict[str, Any] = {}

        dataset = context.dataset
        humidity = _level_pair(dataset, context.variable, "relative_humidity_{level}hPa", pair_indices, shape) if self.rh_timing else None
        if humidity is not None:
            threshold, convention = _critical_rh_percent(dataset, context.variable)
            notes["rh_phase_convention"] = convention
            notes["critical_rh_percent"] = threshold
            bow = None
            if self.omega_shift:
                bow, reached = _omega_bow(dataset, context.variable, pair_indices, shape, humidity[0], humidity[1])
                diagnostics["omega_reached"] = reached
            crossing = _crossing_time(humidity[0], humidity[1], threshold, bow)
            crossed = numpy.isfinite(crossing)
            diagnostics["rh_reached"] = float(numpy.mean(crossed))
            if crossed.any():
                timed = _sigmoid_fraction(fractions, numpy.where(crossed, crossing, 0.5), TIMING_WIDTH)
                target = numpy.where(crossed[None, ...], timed, target)

        if self.solar_dissipation:
            latlon = _grid_latlon(dataset, shape)
            moment = _midpoint_time(dataset, pair_indices)
            if latlon is not None and moment is not None:
                elevation = _solar_elevation_degrees(latlon[0], latlon[1], moment)
                daylit = (numpy.asarray(residual, dtype="float64") < 0.0) & (elevation > 0.0)
                diagnostics["solar_reached"] = float(numpy.mean(daylit))
                if daylit.any():
                    late = _sigmoid_fraction(fractions, SOLAR_DISSIPATION_T_STAR, SOLAR_DISSIPATION_WIDTH)
                    target = numpy.where(daylit[None, ...], numpy.broadcast_to(late, target.shape), target)
            else:
                diagnostics["solar_reached"] = 0.0
        return target, diagnostics, notes

    def _envelope(self, context: MethodContext, position: int, pair: PairMotion, residual: Any) -> tuple[Any, Any, dict[str, float], dict[str, Any]]:
        """``(gen_a, gen_b, diagnostics, notes)`` for one pair."""
        import numpy  # noqa: PLC0415

        values = numpy.nan_to_num(numpy.asarray(residual, dtype="float64"), nan=0.0)
        if not self.use_residual:
            zeros = numpy.zeros_like(values)
            return zeros, zeros, {"rh_reached": 0.0, "omega_reached": 0.0, "regime_gated_fraction": 0.0}, {}

        pair_indices = (context.indices[position], context.indices[position + 1]) if len(context.indices) > position + 1 else (position, position + 1)

        if self.scale_split:
            # Seed 2003: the large scales outlive the interval, so no re-timing
            # of them is defensible - they are delivered linearly (a = b = 0)
            # and only the fine band takes the timing. The two bands sum back
            # to the whole residual, so nothing is dropped by splitting.
            coarse = _gaussian(values, SCALE_SPLIT_SIGMA_CELLS)
            fine = values - coarse
            target, diagnostics, notes = self._target(context, pair_indices, fine)
            a, b = _fit_envelope(fine, target)
        else:
            target, diagnostics, notes = self._target(context, pair_indices, values)
            a, b = _fit_envelope(values, target)

        a, b = _capped(a, b)

        gated = 0.0
        if self.regime_gate:
            previous = numpy.nan_to_num(numpy.asarray(context.frames[position], dtype="float64"), nan=0.0)
            following = numpy.nan_to_num(numpy.asarray(context.frames[position + 1], dtype="float64"), nan=0.0)
            correlation = _local_correlation(_warp_linear(previous, pair.flow01), following)
            keep = correlation >= REGIME_CORRELATION_FLOOR
            gated = float(numpy.mean(~keep))
            a = numpy.where(keep, a, 0.0)
            b = numpy.where(keep, b, 0.0)
        diagnostics["regime_gated_fraction"] = gated
        return a, b, diagnostics, notes

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The sibling's derivation and residual, with the envelope refitted to the timing.

        ``super().motion`` computes ``res_s`` and stores the sibling's
        symmetric quarter-gain envelope; this replaces ``gen_a``/``gen_b`` with
        the fit to the accepted options' target and leaves ``res_s`` - the
        measurement everything else is derived from - exactly as computed.
        """
        results = super().motion(context)
        for position, pair in enumerate(results):
            a, b, diagnostics, _ = self._envelope(context, position, pair, pair.extra["res_s"])
            pair.extra["gen_a"] = a
            pair.extra["gen_b"] = b
            pair.diagnostics.update(diagnostics)
        return results

    # ---------- the gate ----------

    def configure(self, context: MethodContext) -> tuple[InterpolationMethod, dict[str, Any]]:
        """Six options, decided greedily, each on ``harness.admit`` over the accepted set.

        The starting point is the sibling's own settled construction: the
        steering prior and the residual decision come from
        ``ResidualAdvectionMethod.configure``, which scores THIS class'
        composite (it builds through ``type(self)``), so the residual is
        judged on the construction it will actually serve. If that refuses the
        residual there is nothing to time: every option is published as
        refused, the envelope is zeros, and this method draws the baseline.

        Greedy rather than exhaustive, and the reason is the cost. Six options
        are 64 combinations, each needing a full held-out reconstruction over
        every pair; greedy is 12 measurements and each one answers a question a
        reader can check ("did the humidity timing help, given everything
        already accepted"). Every candidate's numbers are published whether it
        was accepted or not, so the search is auditable rather than asserted -
        including the ones that lost.

        The gate is ``harness.admit`` throughout: strictly better
        ``improvement_over_crossfade`` at the midpoint against the FIXED
        crossfade, structural similarity not lower, mean error over every
        held-out fraction not worse, and the sharpness ratio not further from
        1. A generative term must clear all four, because the whole reason
        carve-out (d) allows it at all is that it measurably reconstructs the
        frames that were hidden - and MAE alone would let it buy that by
        smearing more of the change into the middle of the interval.

        ``omega_shift`` is only offered once ``rh_timing`` has been accepted:
        it shifts a humidity crossing time, so with no crossing to shift it is
        arithmetically a no-op and offering it would publish a decision about
        nothing.
        """
        settled, notes = super().configure(context)
        use_prior = bool(getattr(settled, "use_prior", False))
        use_residual = bool(getattr(settled, "use_residual", False))
        build = type(self)

        candidates: dict[str, Any] = {}
        admissions: dict[str, Any] = {}
        threshold, convention = _critical_rh_percent(context.dataset, context.variable)

        def read(skill: dict[str, Any] | None) -> dict[str, Any]:
            if not skill:
                return {
                    "improvement_over_crossfade": None,
                    "improvement_over_advection": None,
                    "midpoint_ssim": None,
                    "midpoint_sharpness_ratio": None,
                }
            return {
                "improvement_over_crossfade": skill.get("improvement_over_crossfade"),
                "improvement_over_advection": skill.get("improvement_over_advection"),
                "midpoint_ssim": skill.get("midpoint_ssim"),
                "midpoint_sharpness_ratio": skill.get("midpoint_sharpness_ratio"),
            }

        def published(**options: Any) -> dict[str, Any]:
            """Every option's decision, as the menu and the disclosure read it."""
            return {
                **notes,
                "generative": True,
                # The steering prior's own decision, which arrived as `applied`
                # from the baseline's notes. Renamed here so that `applied` can
                # mean what carve-out (d) needs it to mean in the menu: did
                # this method GENERATE anything on this layer.
                "prior_applied": bool(notes.get("applied", False)),
                "residual_applied": use_residual,
                "envelope": (
                    "t(1-t)(gen_a + gen_b t), (gen_a, gen_b) least squares over "
                    "HELD_OUT_FRACTIONS against s (F*(t) - t)"
                ),
                "residual_cap_percent": RESIDUAL_CAP_PERCENT,
                # Which saturation convention this run's RH is on, and so
                # which critical value the timing crossed. Published because a
                # threshold calibrated on ECCC's liquid-water RH is NOT valid
                # on GFS's mixed-phase RH below freezing, and a reader looking
                # at the timing is owed the number that was actually used.
                "rh_phase_convention": convention,
                "critical_rh_percent": threshold,
                "gain_candidates": list(GAIN_CANDIDATES),
                "non_generative_gain_ceiling": 0.25,
                "candidates": candidates,
                "admissions": admissions,
                **options,
            }

        refused = {
            "applied": False,
            "gain": RESIDUAL_GAIN,
            "gain_applied": False,
            "rh_timing_applied": False,
            "omega_shift_applied": False,
            "solar_dissipation_applied": False,
            "scale_split_applied": False,
            "regime_gate_applied": False,
        }

        if not use_residual:
            # Nothing measured a residual worth drawing, so there is no
            # delivery to time. Publish zeros and every switch off - an
            # unmeasured generative term is never applied.
            return build(use_prior=use_prior, use_residual=False), published(
                **refused,
                reduced_to="residual-advection with its residual refused (the baseline construction)",
            )

        def score(**options: Any) -> dict[str, Any] | None:
            return _interpolation_skill(
                context.frames,
                method=build(use_prior=use_prior, use_residual=True, **options),
                dataset=context.dataset,
                variable=context.variable,
                interval_seconds=context.interval_seconds,
                indices=context.indices,
                cache=context.cache,
            )

        # The accepted set starts where the sibling stopped: the shipped
        # quarter-of-the-ceiling gain, no timing. Anything this search accepts
        # has beaten that, which is the picture `residual-advection` draws.
        accepted: dict[str, Any] = {
            "gain": RESIDUAL_GAIN,
            "rh_timing": False,
            "omega_shift": False,
            "solar_dissipation": False,
            "scale_split": False,
            "regime_gate": False,
        }
        best = score(**accepted)
        candidates["accepted_start"] = read(best)

        def offer(name: str, **change: Any) -> bool:
            nonlocal best, accepted
            trial = {**accepted, **change}
            skill = score(**trial)
            candidates[name] = read(skill)
            reasons = admit_reasons(skill, best)
            admissions[name] = reasons
            if reasons["admitted"]:
                accepted = trial
                best = skill
                return True
            return False

        gain_applied = False
        for gain in GAIN_CANDIDATES:
            if offer(f"gain={gain}", gain=gain):
                gain_applied = True
        rh_applied = offer("rh_timing", rh_timing=True)
        omega_applied = offer("omega_shift", omega_shift=True) if rh_applied else False
        if not rh_applied:
            admissions["omega_shift"] = {
                "admitted": False,
                "reason": (
                    "not offered: omega shifts a humidity crossing time and the humidity timing "
                    "was refused, so the option is arithmetically a no-op here"
                ),
                "checks": {},
            }
            candidates["omega_shift"] = read(None)
        solar_applied = offer("solar_dissipation", solar_dissipation=True)
        split_applied = offer("scale_split", scale_split=True)
        gate_applied = offer("regime_gate", regime_gate=True)

        applied = bool(gain_applied or rh_applied or omega_applied or solar_applied or split_applied or gate_applied)
        method = build(use_prior=use_prior, use_residual=True, **accepted)
        return method, published(
            applied=applied,
            gain=accepted["gain"],
            gain_applied=gain_applied,
            rh_timing_applied=rh_applied,
            omega_shift_applied=omega_applied,
            solar_dissipation_applied=solar_applied,
            scale_split_applied=split_applied,
            regime_gate_applied=gate_applied,
            generated=applied and accepted["gain"] > 0.25,
            reduced_to=None if applied else "residual-advection (every generative option refused)",
            skill=best,
        )
