"""Numeric primitives the cloud-motion derivation and its methods share.

This module is the toolbox: dense flow, warping, the forward-backward
consistency score, the neighbourhood fill, the development agreement, the
display weight and the model steering prior. It knows nothing about
artifacts, stores or methods, so an interpolation method in
``ingest.derive.methods`` can be written against it without touching the
derive loop.

Dependency direction is one way: ``flow_ops`` <- ``methods`` <-
``cloud_motion``. Nothing here may import either of the other two.
"""

from __future__ import annotations

from typing import Any

#: Forward-backward agreement is judged RELATIVE to how far the flow moved:
#: the round trip may miss by this fraction of the mean of the two
#: magnitudes, with an absolute floor for near-stationary cells, before
#: confidence reaches 0 (Sundaram, Brox & Keutzer 2010, as a continuous
#: score rather than a hard occlusion test).
#:
#: An absolute 2-cell limit shipped until 2026-08-31 and was the reason the
#: display looked like a cross-dissolve: these fields move ~15 cells an hour,
#: so it demanded the round trip close to 13% of the displacement, scored the
#: median cell 0, and sent three quarters of the map down the crossfade
#: fallback - in a region where warping still beat persistence 31.7 to 52.4
#: percent MAE. The tolerance now scales with the motion it is judging.
FB_TOLERANCE_FRACTION = 0.35
FB_TOLERANCE_FLOOR_CELLS = 1.5
#: Radius (grid cells) of the confidence-weighted fill and of the support
#: field: an untrusted cell drifts with its trusted neighbourhood instead of
#: standing still under a moving field.
FLOW_FILL_SIGMA_CELLS = 2.0
#: Cloud-percent disagreement between the two warps at which advection is
#: judged not to explain the change (growth or decay in place) and the
#: display weight falls to a plain crossfade.
DEVELOPMENT_TOLERANCE_PERCENT = 25.0
#: Radius (grid cells) the development agreement is smoothed over, so the
#: advection/crossfade weight varies gradually instead of per pixel.
DEVELOPMENT_SIGMA_CELLS = 3.0
#: Fraction of trusted flow a neighbourhood needs before its filled vector
#: counts as supported at all. Above this the display weight is the
#: development agreement alone - the direct measure of whether advection
#: explains the change here - and below it the weight fades to a crossfade,
#: because a vector with nothing trustworthy behind it is not a measurement.
#:
#: Chosen by held-out skill (2026-08-31). Weighting by min(support,
#: agreement) scored +0.056 against the reversed-flow control on HRDPS total
#: cloud and +0.351 on GFS; weighting by agreement over this floor scored
#: +0.090 and +0.377. The forward-backward score is a good test of whether a
#: vector is invertible and a poor test of whether advecting along it looks
#: like the weather, so it fills and floors rather than dims.
SUPPORT_FLOOR = 0.2
#: Held-out skill a variable must show, against a reversed-flow control,
#: before its motion is displayed at all. Measured 2026-08-31: independent
#: noise fields score -0.001 to +0.001 against this control (they score up to
#: +0.02 against a plain crossfade, which is why the control exists); live
#: HRDPS and RDPS total cloud score +0.056, and the GFS strata +0.35 to
#: +0.43. Two percent sits an order of magnitude above the null and well
#: below the weakest real field.
MIN_HELD_OUT_IMPROVEMENT = 0.02
#: Tangent deviation from the segment flow is clamped to this fraction of the
#: flow magnitude (plus a one-cell absolute floor), so a Hermite arc cannot
#: overshoot far between endpoints when a real acceleration is large.
TANGENT_DEVIATION_FRACTION = 0.5
TANGENT_DEVIATION_FLOOR_CELLS = 1.0


def _dis_flow(previous: Any, following: Any) -> Any:
    """DIS flow from ``previous`` to ``following``; (rows, cols, 2) as (dx, dy) cells."""
    import cv2  # noqa: PLC0415
    import numpy  # noqa: PLC0415

    def prepared(field: Any) -> Any:
        filled = numpy.nan_to_num(numpy.asarray(field, dtype="float64"), nan=0.0)
        scaled = numpy.clip(filled, 0.0, 100.0) * 2.55
        blurred = cv2.GaussianBlur(scaled.astype("float32"), (0, 0), 1.0)
        return numpy.clip(numpy.rint(blurred), 0, 255).astype("uint8")

    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    return dis.calc(prepared(previous), prepared(following), None)


def _warp_nearest(field: Any, flow: Any) -> Any:
    """``field`` advected by the full flow, nearest-cell, clamped at edges."""
    import numpy  # noqa: PLC0415

    rows, cols = field.shape
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    source_rows = numpy.clip(numpy.rint(row_index - flow[..., 1]).astype("int64"), 0, rows - 1)
    source_cols = numpy.clip(numpy.rint(col_index - flow[..., 0]).astype("int64"), 0, cols - 1)
    return field[source_rows, source_cols]


def _consistency(flow01: Any, flow10: Any) -> Any:
    """1 where the two directions agree, falling to 0 at the disagreement limit.

    The limit is relative to how far the flow claims the cell moved: a
    round-trip error of two cells is a failure for a stationary cell and
    well within reason for one that travelled fifteen. Judging both by the
    same absolute tolerance is what made the display a cross-dissolve.
    """
    import numpy  # noqa: PLC0415

    rows, cols = flow01.shape[:2]
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    target_rows = numpy.clip(numpy.rint(row_index + flow01[..., 1]).astype("int64"), 0, rows - 1)
    target_cols = numpy.clip(numpy.rint(col_index + flow01[..., 0]).astype("int64"), 0, cols - 1)
    returned = flow10[target_rows, target_cols]
    error = numpy.hypot(flow01[..., 0] + returned[..., 0], flow01[..., 1] + returned[..., 1])
    travelled = 0.5 * (
        numpy.hypot(flow01[..., 0], flow01[..., 1]) + numpy.hypot(returned[..., 0], returned[..., 1])
    )
    tolerance = numpy.maximum(FB_TOLERANCE_FLOOR_CELLS, FB_TOLERANCE_FRACTION * travelled)
    return numpy.clip(1.0 - error / tolerance, 0.0, 1.0).astype("float32")


def _gaussian(field: Any, sigma: float) -> Any:
    """Gaussian blur of a 2-D float field (OpenCV, edge-replicating)."""
    import cv2  # noqa: PLC0415
    import numpy  # noqa: PLC0415

    return cv2.GaussianBlur(numpy.asarray(field, dtype="float32"), (0, 0), sigma).astype("float64")


def _ssim(first: Any, second: Any) -> float:
    """Mean structural similarity of two percent fields, in [-1, 1].

    Wang et al. 2004 with a Gaussian window, on the 0-100 percent scale. The
    bench needs a score that a blurrier answer cannot win: MAE falls when a
    construction dissolves harder, while SSIM's contrast and structure terms
    fall with it, so the two together separate "closer on average" from
    "actually the same weather".
    """
    import numpy  # noqa: PLC0415

    sigma = 1.5
    dynamic_range = 100.0
    c1 = (0.01 * dynamic_range) ** 2
    c2 = (0.03 * dynamic_range) ** 2
    a = numpy.nan_to_num(numpy.asarray(first, dtype="float64"), nan=0.0)
    b = numpy.nan_to_num(numpy.asarray(second, dtype="float64"), nan=0.0)
    mean_a = _gaussian(a, sigma)
    mean_b = _gaussian(b, sigma)
    variance_a = _gaussian(a * a, sigma) - mean_a * mean_a
    variance_b = _gaussian(b * b, sigma) - mean_b * mean_b
    covariance = _gaussian(a * b, sigma) - mean_a * mean_b
    numerator = (2.0 * mean_a * mean_b + c1) * (2.0 * covariance + c2)
    denominator = (mean_a**2 + mean_b**2 + c1) * (variance_a + variance_b + c2)
    return float(numpy.mean(numerator / numpy.maximum(denominator, 1e-12)))


def _supported_flow(flow: Any, confidence: Any) -> tuple[Any, Any]:
    """``(filled flow, support)``: untrusted cells inherit trusted neighbours.

    A cell whose forward-backward round trip failed is not a cell that stands
    still - it is a cell whose own estimate is unusable while everything
    around it is moving. Filling it with the confidence-weighted average of
    the trusted flow nearby (normalized convolution) keeps the field
    coherent, and the returned support says how much trusted flow actually
    stood behind the fill: where a whole region is untrusted, support stays
    near zero and the display still falls back to a crossfade, disclosed.

    Trusted cells keep their own vector exactly; the fill is applied in
    proportion to how untrusted a cell is, so the field has no seam.
    """
    import numpy  # noqa: PLC0415

    weight = numpy.clip(numpy.asarray(confidence, dtype="float64"), 0.0, 1.0)
    support = numpy.clip(_gaussian(weight, FLOW_FILL_SIGMA_CELLS), 0.0, 1.0)
    denominator = _gaussian(weight, FLOW_FILL_SIGMA_CELLS)
    filled = numpy.array(flow, dtype="float64", copy=True)
    usable = denominator > 1e-3
    for axis in (0, 1):
        smoothed = _gaussian(flow[..., axis] * weight, FLOW_FILL_SIGMA_CELLS)
        neighbourhood = numpy.where(usable, smoothed / numpy.maximum(denominator, 1e-9), flow[..., axis])
        filled[..., axis] = flow[..., axis] + (1.0 - weight) * (neighbourhood - flow[..., axis])
    return filled, support


def _development_agreement(previous: Any, following: Any, flow: Any) -> Any:
    """How well advection explains the change, per cell, in [0, 1].

    Both frames are warped to the midpoint along the flow. Where they land on
    the same picture, the change between the two published frames really is
    motion and the display should advect. Where they disagree, cloud grew or
    decayed in place - the Avalon's own regime - and a plain cross-dissolve
    is the honest picture, because no motion field can move cloud that was
    never somewhere else.
    """
    import numpy  # noqa: PLC0415

    half = 0.5 * numpy.asarray(flow, dtype="float64")
    forward_half = _warp_nearest(numpy.nan_to_num(previous, nan=0.0), half)
    backward_half = _warp_nearest(numpy.nan_to_num(following, nan=0.0), -half)
    disagreement = numpy.abs(forward_half - backward_half)
    agreement = numpy.clip(1.0 - disagreement / DEVELOPMENT_TOLERANCE_PERCENT, 0.0, 1.0)
    return numpy.clip(_gaussian(agreement, DEVELOPMENT_SIGMA_CELLS), 0.0, 1.0)


def _clamped_tangent(velocity: Any, flow: Any) -> Any:
    """``velocity`` pulled toward ``flow`` so its deviation stays bounded.

    The knot velocity is a central-difference estimate from two different
    pairs; where it disagrees wildly with the segment's own displacement the
    Hermite arc would bow far outside the endpoints. Deviation is limited to
    a fraction of the flow magnitude plus a one-cell floor (Fritsch-Carlson
    in spirit). The clamp is per segment, against that segment's own flow:
    where it bites, the two segments sharing the knot each relax toward
    their own linear model - boundedness is bought with a small, bounded
    velocity step, never with an overshooting arc.
    """
    import numpy  # noqa: PLC0415

    deviation = velocity - flow
    magnitude = numpy.hypot(deviation[..., 0], deviation[..., 1])
    cap = numpy.maximum(
        TANGENT_DEVIATION_FRACTION * numpy.hypot(flow[..., 0], flow[..., 1]),
        TANGENT_DEVIATION_FLOOR_CELLS,
    )
    scale = numpy.where(magnitude > cap, cap / numpy.maximum(magnitude, 1e-9), 1.0)
    return flow + deviation * scale[..., None]


def _segment_tangents(flow01: list[Any], flow10: list[Any], confidence: list[Any]) -> list[tuple[Any, Any]]:
    """Per segment, the (start, end) Hermite tangents, anchored per knot.

    Knot k's velocity is the QVI central difference of the two flows anchored
    at frame k: v_k = 1/2 (F_{k->k+1} - F_{k->k-1}), where F_{k->k+1} is pair
    k's forward flow and F_{k->k-1} is pair k-1's backward flow. The sequence
    ends are one-sided (v = the segment's own flow). Where the knot's
    forward-backward consistency is low the velocity relaxes continuously to
    the segment flow, so a distrusted knot renders exactly as the linear
    advection already approved. Velocity is exactly continuous at fully
    trusted, unclamped knots; a distrusted or clamped knot trades that for a
    bounded step toward each segment's own linear model.
    """
    import numpy  # noqa: PLC0415

    pairs = len(flow01)
    segments: list[tuple[Any, Any]] = []
    for index in range(pairs):
        forward = flow01[index]
        # Start knot = frame `index`: central difference needs pair index-1.
        if index == 0:
            start = forward
        else:
            knot = 0.5 * (flow01[index] - flow10[index - 1])
            trust = numpy.minimum(confidence[index], confidence[index - 1])[..., None]
            start = forward + trust * (knot - forward)
        # End knot = frame `index + 1`: central difference needs pair index+1.
        if index + 1 >= pairs:
            end = forward
        else:
            knot = 0.5 * (flow01[index + 1] - flow10[index])
            trust = numpy.minimum(confidence[index], confidence[index + 1])[..., None]
            end = forward + trust * (knot - forward)
        segments.append((_clamped_tangent(start, forward), _clamped_tangent(end, forward)))
    return segments


#: Steering level per cloud variable: the model wind at the level that
#: actually carries that stratum (CIRACast's cloud-top steering level, INCA,
#: Liang MWR 2020). Total cloud has no single top, so it takes the mid-level
#: wind, which is the conventional single-level steering choice.
STEERING_LEVEL_BY_VARIABLE = {
    "cloud_low": 850,
    "cloud_middle": 700,
    "cloud_high": 500,
    "total_cloud": 700,
}
#: Below this speed (grid cells over the frame interval) a well-supported
#: image flow is reporting that the field is NOT moving, and the steering
#: prior is refused there however hard the model says the wind blows.
#:
#: This gate is mandatory, not a tuning knob. Orographic and marine cloud
#: over the Avalon forms and dissipates in place while wind blows through it
#: - the documented failure mode of every steering-wind nowcast - and a prior
#: applied there would drag standing fog across the peninsula and call it
#: motion.
STATIONARY_CELLS = 1.0
#: How far the prior may sit from the corroborating image flow before it is
#: judged uncorroborated, as a fraction of the prior's own magnitude.
PRIOR_AGREEMENT_FRACTION = 1.0


def _cell_metres(lat2d: Any, lon2d: Any) -> tuple[Any, Any, float]:
    """Local cell size in metres (east, north) and the sign of north per row."""
    import numpy  # noqa: PLC0415

    lat_step = numpy.gradient(lat2d, axis=0)
    lon_step = numpy.gradient(lon2d, axis=1)
    metres_per_degree = 111_320.0
    east = numpy.abs(lon_step) * metres_per_degree * numpy.cos(numpy.radians(lat2d))
    north = numpy.abs(lat_step) * metres_per_degree
    row_sign = 1.0 if float(numpy.nanmean(lat_step)) > 0 else -1.0
    return numpy.maximum(east, 1.0), numpy.maximum(north, 1.0), row_sign


def _steering_prior(
    dataset: Any, variable: str, indices: tuple[int, int], interval_seconds: float, shape: tuple[int, int]
) -> Any | None:
    """The model steering wind for this pair, in grid cells, or None.

    Absent winds are an absent prior, never a zero one: the flow then stands
    on the imagery alone, exactly as it did before the winds were ingested.
    """
    import numpy  # noqa: PLC0415

    level = STEERING_LEVEL_BY_VARIABLE.get(variable)
    if level is None or interval_seconds <= 0:
        return None
    names = (f"wind_u_{level}hPa", f"wind_v_{level}hPa")
    if any(name not in dataset.data_vars for name in names):
        return None
    lat_name = "latitude" if "latitude" in dataset.coords else "lat"
    lon_name = "longitude" if "longitude" in dataset.coords else "lon"
    if lat_name not in dataset.coords or lon_name not in dataset.coords:
        return None
    try:
        components = []
        for name in names:
            field = dataset[name]
            time_name = next((dim for dim in ("valid_time", "time") if dim in field.dims), None)
            if time_name is None or field.sizes[time_name] <= max(indices):
                return None
            # The interval's mean wind: the two endpoints' own values.
            pair = field.isel({time_name: list(indices)}).values
            components.append(numpy.nanmean(numpy.asarray(pair, dtype="float64"), axis=0))
        wind_u, wind_v = components
        if wind_u.shape != shape or wind_v.shape != shape:
            return None
        lat_values = numpy.asarray(dataset[lat_name].values, dtype="float64")
        lon_values = numpy.asarray(dataset[lon_name].values, dtype="float64")
        if lat_values.ndim == 1:
            lat2d, lon2d = numpy.meshgrid(lat_values, lon_values, indexing="ij")
        else:
            lat2d, lon2d = lat_values, lon_values
        if lat2d.shape != shape:
            return None
        east_metres, north_metres, row_sign = _cell_metres(lat2d, lon2d)
        prior = numpy.zeros(shape + (2,), dtype="float64")
        prior[..., 0] = numpy.nan_to_num(wind_u) * interval_seconds / east_metres
        prior[..., 1] = row_sign * numpy.nan_to_num(wind_v) * interval_seconds / north_metres
        return prior
    except Exception:
        # A prior that cannot be read is simply absent. It never fails the
        # motion artifact, which stands on the imagery.
        return None


def _prior_corrected(flow: Any, support: Any, prior: Any) -> tuple[Any, float]:
    """``flow`` filled toward the steering wind where the imagery is silent.

    The prior never overrides the imagery. It reaches only cells with no
    trusted flow behind them, only in proportion to how well it agrees with
    the trusted flow nearby, and never where a well-supported image flow says
    the field is standing still (``STATIONARY_CELLS``). Returns the corrected
    flow and the mean weight the prior actually carried, so provenance can
    say how much of the field the model touched.
    """
    import numpy  # noqa: PLC0415

    trusted = numpy.clip(numpy.asarray(support, dtype="float64"), 0.0, 1.0)
    speed = numpy.hypot(flow[..., 0], flow[..., 1])
    # Corroboration: where the imagery IS trusted, how close is the prior?
    difference = numpy.hypot(prior[..., 0] - flow[..., 0], prior[..., 1] - flow[..., 1])
    tolerance = numpy.maximum(
        PRIOR_AGREEMENT_FRACTION * numpy.hypot(prior[..., 0], prior[..., 1]), FB_TOLERANCE_FLOOR_CELLS
    )
    agreement = numpy.clip(1.0 - difference / tolerance, 0.0, 1.0)
    corroboration = float(numpy.average(agreement, weights=numpy.maximum(trusted, 1e-6)))
    stationary = (trusted > 0.5) & (speed < STATIONARY_CELLS)
    weight = (1.0 - trusted) * corroboration
    weight[stationary] = 0.0
    weight = _gaussian(weight, FLOW_FILL_SIGMA_CELLS)
    corrected = numpy.array(flow, dtype="float64", copy=True)
    for axis in (0, 1):
        corrected[..., axis] = flow[..., axis] + weight * (prior[..., axis] - flow[..., axis])
    return corrected, float(numpy.mean(weight))


def _display_weight(support: Any, agreement: Any) -> Any:
    """The weight the client mixes advection against a crossfade on.

    Agreement leads: it measures the thing the reader sees - whether warping
    the two frames toward each other lands on the same picture. Support only
    gates it, so a vector nothing trustworthy stood behind cannot carry the
    display however plausible the two warps happen to look.
    """
    import numpy  # noqa: PLC0415

    return agreement * numpy.clip(numpy.asarray(support, dtype="float64") / SUPPORT_FLOOR, 0.0, 1.0)


def _midpoint_composite(previous: Any, following: Any, flow: Any, weight: Any) -> Any:
    """What the client draws at t = 0.5, computed the same way the shader does."""
    import numpy  # noqa: PLC0415

    half = 0.5 * numpy.asarray(flow, dtype="float64")
    warped = 0.5 * _warp_nearest(previous, half) + 0.5 * _warp_nearest(following, -half)
    plain = 0.5 * previous + 0.5 * following
    return plain + weight * (warped - plain)
