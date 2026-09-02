"""Numeric primitives the cloud-motion derivation and its methods share.

This module is the toolbox: dense flow, warping (nearest and linear), the
forward-backward consistency score, the neighbourhood fill, the display
weight, the model steering prior and vertical-velocity tendency, and the
held-out scoring primitives (structural similarity, sharpness ratio, radial
power-spectrum ratio, fractions skill score). It knows nothing about
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
#: Floor, in cloud percent, of the warp error at which an error-variance
#: estimate stops being "small": the inverse-variance reliability in
#: ``error_variance_blend`` is ``floor^2 / (sigma^2 + floor^2)``, so this is
#: the squared-error scale that halves a warp's weight.
#:
#: HISTORY, kept so the number is not re-derived. Until cloud-motion-bench-v6
#: this was ``DEVELOPMENT_TOLERANCE_PERCENT``, the floor of the "development
#: agreement" test that dropped the display weight to a crossfade wherever
#: the two half-warps disagreed by more than this. That test was measured
#: against a fixed control and against stratified growth/decay error on
#: 2026-09-01 and lost on every layer tried (the table is in
#: ``BaselineMethod``'s docstring), so it was deleted rather than tuned. The
#: value survives only as this floor, where it does a different job: it was
#: the scale at which a warp error was judged material, and that is exactly
#: what an error-variance floor has to be. Two things measured on the way to
#: deleting the test, recorded so they are not re-derived: smoothing the
#: disagreement BEFORE the ratio rather than the agreement after it was much
#: worse (-0.05 HRDPS, -0.15 GFS total), and forcing the agreement to 1
#: everywhere scored higher on every layer - which is what the deletion is.
WARP_ERROR_FLOOR_PERCENT = 25.0
#: Radius (grid cells) a per-pixel squared warp error is smoothed over before
#: it is inverted into a reliability, so the fusion weight is a local error
#: VARIANCE rather than one pixel's noisy square. Was ``DEVELOPMENT_SIGMA_CELLS``
#: (the same radius, applied to the agreement field that no longer exists).
ERROR_SMOOTHING_SIGMA_CELLS = 3.0
#: Fraction of trusted flow a neighbourhood needs before its filled vector
#: counts as supported at all. Above this the display advects at full
#: strength; below it the weight fades to a crossfade, because a vector with
#: nothing trustworthy behind it is not a measurement. Since bench-v6 this is
#: the ONLY thing the display weight reads (see ``_display_weight``).
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


def _warp_linear(field: Any, flow: Any) -> Any:
    """``field`` advected by the full flow, bilinear, edges replicated.

    Same sign convention as ``_warp_nearest``: the result at ``p`` reads
    ``field`` at ``p - flow``. OpenCV ``remap`` with ``INTER_LINEAR`` and
    ``BORDER_REPLICATE`` does the sampling; the nearest-cell warp stays the
    one the display and the composites use (a bilinear warp of a bimodal
    cloud field manufactures intermediate values at every edge, which is the
    blur the bench exists to remove). This one is for the residual
    computation and the regime gate, where the quantity being read is an
    error rather than a picture and sub-cell placement matters more than
    crispness.
    """
    import cv2  # noqa: PLC0415
    import numpy  # noqa: PLC0415

    values = numpy.asarray(field, dtype="float32")
    rows, cols = values.shape
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    map_x = (col_index - numpy.asarray(flow)[..., 0]).astype("float32")
    map_y = (row_index - numpy.asarray(flow)[..., 1]).astype("float32")
    warped = cv2.remap(values, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return warped.astype("float64")


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
#: Every column-cover key takes the mid-level wind for the same reason: the
#: choice follows from the quantity having no single top, not from which
#: producer's definition of column cover it is.
STEERING_LEVEL_BY_VARIABLE = {
    "cloud_low": 850,
    "cloud_middle": 700,
    "cloud_high": 500,
    "total_cloud_opacity": 700,
    "total_cloud_geometric": 700,
    "total_cloud_mean_6h": 700,
    "total_cloud_weong": 700,
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


def _display_weight(support: Any) -> Any:
    """The weight the client mixes advection against a crossfade on.

    Support only: ``clip(support / SUPPORT_FLOOR, 0, 1)``. A cell with a
    trustworthy vector behind it advects at full strength; a cell with
    nothing trustworthy behind its fill fades to the crossfade, which is a
    statement about the measurement rather than about the weather.

    Until bench-v6 this was multiplied by a "development agreement" - the
    photometric agreement of the two half-warps - on the reasoning that
    where the warps disagree cloud grew or decayed in place and no motion
    field can move it. Measured on fixed controls and on growth and decay
    separately, that term made every layer worse and blurrier (the table is
    in ``BaselineMethod``'s docstring): it was not protecting development,
    it was suppressing advection wherever the flow was imperfect. Growth and
    decay are now the computed residual's job (``residual-advection``), not
    the weight's.
    """
    import numpy  # noqa: PLC0415

    return numpy.clip(numpy.asarray(support, dtype="float64") / SUPPORT_FLOOR, 0.0, 1.0)


def _midpoint_composite(previous: Any, following: Any, flow: Any, weight: Any) -> Any:
    """What the client draws at t = 0.5, computed the same way the shader does."""
    import numpy  # noqa: PLC0415

    half = 0.5 * numpy.asarray(flow, dtype="float64")
    warped = 0.5 * _warp_nearest(previous, half) + 0.5 * _warp_nearest(following, -half)
    plain = 0.5 * previous + 0.5 * following
    return plain + weight * (warped - plain)


def _omega_tendency(
    dataset: Any, variable: str, indices: tuple[int, int], shape: tuple[int, int]
) -> Any | None:
    """``omega_1 - omega_0`` at the stratum's steering level, in Pa s-1, or None.

    Vertical velocity on pressure surfaces, WMO discipline 0 category 2
    parameter 8 - verified in the message's own coded keys, not inferred from
    a name (HRDPS ``VVEL_ISBL_0850``, RDPS ``VerticalVelocity_IsbL-0850``,
    GFS ``VVEL:850 mb``, all decoding to ecCodes ``w``, paramId 135,
    ``Pa s**-1``). The sign convention follows from the units: omega is
    d(pressure)/dt, so NEGATIVE is ascent and positive is descent.

    What is read is the DIFFERENCE between the pair's two instants rather
    than the interval mean, because a mean says only which way the forcing
    points and a timing needs to know WHEN inside the interval the change
    happened. Stronger ascent at the start means the growth it forced
    happened early; stronger ascent at the end means it happened late. That
    is the only thing a re-timing can honestly express, and the rationale the
    retired ``development-residual`` method rested on (carve-out (c), now
    subsumed by (d)): where the two retrieved frames fix the net change per
    cell, omega may shift the timing envelope of a computed residual - it
    never decides what the change is. A ``d ln RH/dt = (omega/p)(1 - kappa
    L/(R_v T))`` closure turns the same tendency into a humidity crossing
    time for the generative sibling of ``residual-advection``.

    Absent omega is an absent tendency, never a zero one: a consumer then
    reduces to the permitted advection and says so, which is the same rule
    the steering prior already follows.
    """
    import numpy  # noqa: PLC0415

    level = STEERING_LEVEL_BY_VARIABLE.get(variable)
    if level is None:
        return None
    name = f"omega_{level}hPa"
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
        return numpy.nan_to_num(pair[1] - pair[0], nan=0.0)
    except Exception:
        # Unreadable omega is simply absent. It never fails the motion
        # artifact, which stands on the imagery.
        return None


def _sharpness_ratio(composite: Any, truth: Any) -> float:
    """Mean gradient magnitude of ``composite`` over that of ``truth``; 1 is as sharp as reality.

    Pointwise error rewards blur - a smooth field is close to everything -
    so a construction can win on MAE by dissolving harder. The ratio of mean
    |grad| is the plainest measure of whether it did (Harris et al. 2001, on
    the smoothness of NWP precipitation fields relative to radar; the
    sharpness diagnostics of Ravuri et al. 2021, Nature 597). Below 1 the
    reconstruction is blurrier than the frame it is scored against; above 1
    it has manufactured edges. A featureless truth returns 1.0 against a
    featureless reconstruction, since nothing was lost.
    """
    import numpy  # noqa: PLC0415

    a = numpy.nan_to_num(numpy.asarray(composite, dtype="float64"), nan=0.0)
    b = numpy.nan_to_num(numpy.asarray(truth, dtype="float64"), nan=0.0)
    rows_a, cols_a = numpy.gradient(a)
    rows_b, cols_b = numpy.gradient(b)
    sharp_a = float(numpy.mean(numpy.hypot(rows_a, cols_a)))
    sharp_b = float(numpy.mean(numpy.hypot(rows_b, cols_b)))
    if sharp_b <= 1e-9:
        return 1.0 if sharp_a <= 1e-9 else float("inf")
    return sharp_a / sharp_b


def _radial_psd_log_ratio(composite: Any, truth: Any, bins: int = 16) -> float:
    """Mean |log10| ratio of the two radially averaged power spectra; 0 is a perfect match.

    The spectral counterpart of the sharpness ratio (Ravuri et al. 2021,
    Nature 597, radially averaged PSD; Harris et al. 2001, power spectra of
    NWP versus radar): a blurred reconstruction loses power at high
    wavenumber and a noisy one gains it, and either shows here as a log
    ratio far from zero in the bins it affects. Averaged over radial bins
    so every scale counts once rather than the many high-wavenumber cells
    swamping the few low ones. Plain numpy FFT on the mean-removed fields.
    """
    import numpy  # noqa: PLC0415

    a = numpy.nan_to_num(numpy.asarray(composite, dtype="float64"), nan=0.0)
    b = numpy.nan_to_num(numpy.asarray(truth, dtype="float64"), nan=0.0)
    rows, cols = a.shape
    freq_rows = numpy.fft.fftfreq(rows)[:, None]
    freq_cols = numpy.fft.fftfreq(cols)[None, :]
    radius = numpy.hypot(freq_rows, freq_cols)
    edges = numpy.linspace(0.0, 0.5, bins + 1)
    membership = numpy.clip(numpy.digitize(radius, edges) - 1, 0, bins - 1)
    power_a = numpy.abs(numpy.fft.fft2(a - a.mean())) ** 2
    power_b = numpy.abs(numpy.fft.fft2(b - b.mean())) ** 2
    ratios = []
    for index in range(bins):
        selected = membership == index
        if not selected.any():
            continue
        mean_a = float(numpy.mean(power_a[selected]))
        mean_b = float(numpy.mean(power_b[selected]))
        if mean_a <= 1e-12 and mean_b <= 1e-12:
            continue
        ratios.append(abs(numpy.log10((mean_a + 1e-12) / (mean_b + 1e-12))))
    return float(numpy.mean(ratios)) if ratios else 0.0


def _fss(composite: Any, truth: Any, threshold: float, radius: int) -> float:
    """Fractions skill score at one percent threshold and one neighbourhood radius.

    Roberts & Lean 2008 (MWR 136): both fields are thresholded, the fraction
    of exceeding cells in a ``(2 radius + 1)`` square around each cell is
    taken (``cv2.blur``), and the score is ``1 - MSE(fractions) / (mean f_c^2
    + mean f_t^2)``. 1 is a perfect match at that scale, 0 is no skill, and
    a reconstruction that puts the right amount of cloud a little in the
    wrong place scores well at a radius that covers the displacement and
    badly at one that does not - which is the scale-aware verdict a cell-wise
    error cannot give. Two fields that both exceed nowhere are identical at
    every scale and score 1.
    """
    import cv2  # noqa: PLC0415
    import numpy  # noqa: PLC0415

    size = 2 * int(radius) + 1
    exceed_a = (numpy.nan_to_num(numpy.asarray(composite, dtype="float64"), nan=0.0) >= threshold).astype("float32")
    exceed_b = (numpy.nan_to_num(numpy.asarray(truth, dtype="float64"), nan=0.0) >= threshold).astype("float32")
    fraction_a = cv2.blur(exceed_a, (size, size), borderType=cv2.BORDER_REFLECT).astype("float64")
    fraction_b = cv2.blur(exceed_b, (size, size), borderType=cv2.BORDER_REFLECT).astype("float64")
    denominator = float(numpy.mean(fraction_a**2) + numpy.mean(fraction_b**2))
    if denominator <= 1e-12:
        return 1.0
    return float(1.0 - numpy.mean((fraction_a - fraction_b) ** 2) / denominator)
