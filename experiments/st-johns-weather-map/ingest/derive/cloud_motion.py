"""Cloud-motion fields between adjacent published cloud frames.

For each cloud variable of a published surface grid, dense optical flow is
computed between every pair of adjacent frames (OpenCV DIS - the estimator
radar nowcasting standardised on) in both directions, with a
forward-backward consistency score. The web client uses these fields for
**display-time advection-corrected interpolation** (Anagnostou & Krajewski;
the pySTEPS advection-correction construction): warp both real frames toward
each other along the motion field and cross-dissolve. The scheme is
endpoint-exact - at the two real instants the real frames show untouched -
and where the flow is zero or unconfident it degrades to a plain crossfade.

Evidence rules (owner carve-out 2026-08-31): this artifact is a display
derivation. It is published with its method, version and base revision in
provenance, it never feeds ``/point``, ``/timeline`` or any reading, and a
pair whose flow cannot be computed is simply absent - the client then
crossfades, disclosed as such.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ingest.contract import Artifact, MEDIA_ZARR, RunResult
from ingest.grib import write_zarr
from ingest.store import sha256_of

UTC = timezone.utc

#: Cloud variables worth motion fields, per source. Only the rendered-grid
#: cloud layers consume them; nothing else is derived.
CLOUD_MOTION_SOURCES: dict[str, tuple[str, ...]] = {
    "noaa-gfs": ("cloud_low", "cloud_middle", "cloud_high", "total_cloud"),
    "eccc-hrdps": ("total_cloud",),
    "eccc-rdps": ("total_cloud",),
}

LOGICAL_NAME = "cloud_motion"
METHOD = (
    "dense optical flow between adjacent published frames: OpenCV DIS (medium preset) on the "
    "Gaussian-presmoothed percent field, forward and backward, with a forward-backward "
    "consistency score per cell judged relative to the distance the flow claims; cells the "
    "round trip fails inherit the confidence-weighted flow of their trusted neighbourhood "
    "(normalized convolution), with the local trusted density kept as support; per-knot "
    "velocities by QVI central difference of the two adjacent pairs' flows (one-sided at the "
    "sequence ends), stored as cubic Hermite segment tangents so displayed velocity is C1 "
    "across every real frame; the display weight between advection and a plain crossfade is the "
    "photometric agreement of the two half-interval warps, gated by that support, so cloud that "
    "grew or decayed in place dissolves rather than being dragged; a variable whose held-out "
    "midpoint reconstruction does not beat the same construction with the motion reversed is "
    "published with a zero weight and crossfades everywhere; where the model publishes the "
    "stratum's steering wind (850/700/500 hPa) that wind may fill cells the imagery leaves "
    "unsupported, weighted by its agreement with the trusted image flow, never where a "
    "well-supported image flow reports the field standing still, and only for a variable whose "
    "held-out reconstruction the prior measurably improves"
)
VERSION = "cloud-motion-development-v3"
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


def _interpolation_skill(
    frames: list[Any],
    *,
    dataset: Any = None,
    variable: str = "",
    interval_seconds: float = 0.0,
) -> dict[str, Any] | None:
    """Leave-one-out skill: does the construction actually predict a real frame?

    For each interior frame k the two frames on either side are interpolated
    to the midpoint by exactly the rule the client applies, and the result is
    compared against the real frame k that was held out - against a plain
    crossfade of the same two frames as the baseline. This is the number that
    says whether the display is believable; "it looks smoother" is not
    evidence. ``None`` when the sequence is too short to hold one out, which
    is an absent measurement, never a zero.
    """
    import numpy  # noqa: PLC0415

    if len(frames) < 3:
        return None
    filled = [numpy.nan_to_num(frame, nan=0.0) for frame in frames]
    composite_error: list[float] = []
    crossfade_error: list[float] = []
    control_error: list[float] = []
    for index in range(1, len(filled) - 1):
        previous, held_out, following = filled[index - 1], filled[index], filled[index + 1]
        raw01 = _dis_flow(previous, following)
        raw10 = _dis_flow(following, previous)
        flow, support = _supported_flow(raw01.astype("float64"), _consistency(raw01, raw10))
        if dataset is not None:
            prior = _steering_prior(dataset, variable, (index - 1, index + 1), interval_seconds, flow.shape[:2])
            if prior is not None:
                flow, _ = _prior_corrected(flow, support, prior)
        weight = _display_weight(support, _development_agreement(previous, following, flow))
        composite = _midpoint_composite(previous, following, flow, weight)
        composite_error.append(float(numpy.mean(numpy.abs(composite - held_out))))
        crossfade_error.append(float(numpy.mean(numpy.abs(0.5 * previous + 0.5 * following - held_out))))
        # Null model: the same warping, the same smoothing, the motion
        # reversed. Beating a plain crossfade can be had for free, because
        # any blend of two warps is smoother than the average of the frames
        # and a smoother field scores better against anything (pure noise
        # "improves" on the crossfade by up to 2% this way). Beating the
        # reversed control cannot: it isolates whether the DIRECTION of the
        # motion is right, which is the only thing that makes the display
        # believable.
        control_error.append(float(numpy.mean(numpy.abs(_midpoint_composite(previous, following, -flow, weight) - held_out))))
    composite_mae = float(numpy.mean(composite_error))
    crossfade_mae = float(numpy.mean(crossfade_error))
    control_mae = float(numpy.mean(control_error))
    return {
        "held_out_frames": len(composite_error),
        "midpoint_mae_percent": composite_mae,
        "midpoint_crossfade_mae_percent": crossfade_mae,
        "midpoint_reversed_flow_mae_percent": control_mae,
        "improvement_over_crossfade": (crossfade_mae - composite_mae) / crossfade_mae if crossfade_mae > 0 else 0.0,
        "improvement_over_reversed_flow": (control_mae - composite_mae) / control_mae if control_mae > 0 else 0.0,
    }


def _open_zarr_zip(path: Path) -> Any:
    import xarray  # noqa: PLC0415
    import zarr  # noqa: PLC0415

    store = zarr.storage.ZipStore(str(path), mode="r")
    return xarray.open_zarr(store, consolidated=False)


def _frame_stack(dataset: Any, variable: str) -> tuple[list[Any], list[Any]] | None:
    """Sorted (times, 2-D frames) for one variable, or None when unusable."""
    import numpy  # noqa: PLC0415
    import pandas  # noqa: PLC0415

    if variable not in dataset.data_vars:
        return None
    time_name = next((name for name in ("valid_time", "time") if name in dataset[variable].dims), None)
    if time_name is None:
        return None
    data = dataset[variable]
    spatial = [dim for dim in data.dims if dim != time_name]
    if len(spatial) != 2:
        return None
    stamps = [pandas.Timestamp(value).to_pydatetime().replace(tzinfo=UTC) for value in dataset[time_name].values]
    order = numpy.argsort(numpy.asarray([stamp.timestamp() for stamp in stamps]))
    times = [stamps[int(position)] for position in order]
    frames = [numpy.asarray(data.isel({time_name: int(position)}).values, dtype="float64") for position in order]
    return times, frames


def derive_cloud_motion(store: Any, surface: Any, variables: Iterable[str], workdir: Path) -> RunResult | None:
    """One motion artifact for one published surface artifact, or None.

    Reads the surface artifact back from the object store (digest-verified),
    computes per-variable per-pair flow, and returns the RunResult to stage.
    ``None`` means nothing usable (no variable, fewer than two frames, or
    every pair degenerate) - and nothing is published in that case.
    """
    import numpy  # noqa: PLC0415
    import xarray  # noqa: PLC0415

    local = workdir / "surface.zarr.zip"
    store.s3.download_file(store.config.bucket, surface.object_key, str(local))
    expected = str(surface.provenance.get("sha256", ""))
    if expected and sha256_of(local) != expected:
        raise RuntimeError(f"{surface.source_id}: surface artifact bytes do not match their recorded digest")
    dataset = _open_zarr_zip(local)

    data_vars: dict[str, Any] = {}
    quality: dict[str, Any] = {}
    pair_from: list[datetime] = []
    pair_to: list[datetime] = []
    for variable in variables:
        stack = _frame_stack(dataset, variable)
        if stack is None:
            continue
        times, frames = stack
        if len(frames) < 2:
            continue
        pairs = list(zip(times, times[1:], frames, frames[1:]))
        if not pair_from:
            pair_from = [start for start, _, _, _ in pairs]
            pair_to = [end for _, end, _, _ in pairs]
        elif [start for start, _, _, _ in pairs] != pair_from:
            # Variables of one artifact share a time axis; one that does not is
            # refused rather than filed under the wrong pair instants.
            continue
        # Does the model steering wind actually help? Measured, not assumed:
        # the held-out reconstruction is scored with the prior and without it,
        # and the prior is applied only if it predicts real frames better. A
        # prior that changes nothing is not shipped, and both numbers are
        # published so the claim can be checked.
        interval_seconds = (pairs[0][1] - pairs[0][0]).total_seconds()
        skill_without_prior = _interpolation_skill(frames)
        skill_with_prior = _interpolation_skill(
            frames, dataset=dataset, variable=variable, interval_seconds=2.0 * interval_seconds,
        )
        use_prior = (
            skill_with_prior is not None
            and skill_without_prior is not None
            and skill_with_prior["improvement_over_reversed_flow"]
            > skill_without_prior["improvement_over_reversed_flow"]
        )
        skill = skill_with_prior if use_prior else skill_without_prior

        u01 = numpy.zeros((len(pairs),) + frames[0].shape, dtype="float32")
        v01 = numpy.zeros_like(u01)
        u10 = numpy.zeros_like(u01)
        v10 = numpy.zeros_like(u01)
        confidence = numpy.zeros_like(u01)
        advect_weight = numpy.zeros_like(u01)
        forward_flows: list[Any] = []
        backward_flows: list[Any] = []
        supports: list[Any] = []
        mae_warp: list[float] = []
        mae_persistence: list[float] = []
        prior_weights: list[float] = []
        for index, (start, end, previous, following) in enumerate(pairs):
            raw01 = _dis_flow(previous, following)
            raw10 = _dis_flow(following, previous)
            agreed = _consistency(raw01, raw10)
            # The stored field is the filled one: it is what the client warps
            # along, so an untrusted cell must carry its neighbourhood's
            # motion rather than a vector nothing stood behind.
            flow01, support = _supported_flow(raw01.astype("float64"), agreed)
            flow10, _ = _supported_flow(raw10.astype("float64"), agreed)
            if use_prior:
                prior = _steering_prior(
                    dataset, variable, (index, index + 1), (end - start).total_seconds(), frames[0].shape
                )
                if prior is not None:
                    flow01, carried = _prior_corrected(flow01, support, prior)
                    flow10, _ = _prior_corrected(flow10, support, -prior)
                    prior_weights.append(carried)
            u01[index] = flow01[..., 0]
            v01[index] = flow01[..., 1]
            u10[index] = flow10[..., 0]
            v10[index] = flow10[..., 1]
            confidence[index] = agreed
            advect_weight[index] = _display_weight(support, _development_agreement(previous, following, flow01))
            forward_flows.append(flow01)
            backward_flows.append(flow10)
            supports.append(support)
            filled_previous = numpy.nan_to_num(previous, nan=0.0)
            filled_following = numpy.nan_to_num(following, nan=0.0)
            mae_warp.append(float(numpy.mean(numpy.abs(_warp_nearest(filled_previous, flow01) - filled_following))))
            mae_persistence.append(float(numpy.mean(numpy.abs(filled_previous - filled_following))))
        # Two vetoes, both on measured skill rather than on taste.
        #
        # Per pair: a warp that cannot even beat persistence has no motion
        # worth displaying. This is a weak floor - DIS minimises exactly this
        # quantity, so it passes almost always - and it is kept for the cases
        # where the flow is genuinely useless.
        for index, (warped, persisted) in enumerate(zip(mae_warp, mae_persistence)):
            if warped >= persisted:
                advect_weight[index] = 0.0
        # Per variable: the honest test is the held-out one. If interpolating
        # across a real frame predicts that frame no better than the same
        # construction with the motion reversed, then the direction carries no
        # information, this variable's motion is not display-worthy at all
        # whatever the flow looks like, and every pair falls back to the
        # crossfade the fallback ladder already discloses.
        if skill is not None and skill["improvement_over_reversed_flow"] < MIN_HELD_OUT_IMPROVEMENT:
            advect_weight[:] = 0.0
        tangents = _segment_tangents(forward_flows, backward_flows, supports)
        vs_u = numpy.stack([start[..., 0] for start, _ in tangents]).astype("float32")
        vs_v = numpy.stack([start[..., 1] for start, _ in tangents]).astype("float32")
        ve_u = numpy.stack([end[..., 0] for _, end in tangents]).astype("float32")
        ve_v = numpy.stack([end[..., 1] for _, end in tangents]).astype("float32")
        attrs = {
            "units": "grid cells per frame interval",
            "fb_tolerance_fraction": FB_TOLERANCE_FRACTION,
            "fb_tolerance_floor_cells": FB_TOLERANCE_FLOOR_CELLS,
        }
        data_vars[f"{variable}_u01"] = (("pair", "y", "x"), u01, attrs)
        data_vars[f"{variable}_v01"] = (("pair", "y", "x"), v01, attrs)
        data_vars[f"{variable}_u10"] = (("pair", "y", "x"), u10, attrs)
        data_vars[f"{variable}_v10"] = (("pair", "y", "x"), v10, attrs)
        data_vars[f"{variable}_confidence"] = (
            ("pair", "y", "x"), confidence,
            {"units": "1", "role": "forward-backward agreement of the raw flow, relative to its own magnitude"},
        )
        data_vars[f"{variable}_advect_weight"] = (
            ("pair", "y", "x"), advect_weight,
            {"units": "1", "role": "display weight: 1 advects, 0 crossfades; min(neighbourhood support, warp agreement), zero where the pair's warp does not beat persistence"},
        )
        tangent_attrs = {**attrs, "role": "cubic Hermite segment tangent (QVI central-difference knot velocity)"}
        data_vars[f"{variable}_vs_u"] = (("pair", "y", "x"), vs_u, tangent_attrs)
        data_vars[f"{variable}_vs_v"] = (("pair", "y", "x"), vs_v, tangent_attrs)
        data_vars[f"{variable}_ve_u"] = (("pair", "y", "x"), ve_u, tangent_attrs)
        data_vars[f"{variable}_ve_v"] = (("pair", "y", "x"), ve_v, tangent_attrs)
        quality[variable] = {
            "pairs": len(pairs),
            "mae_full_warp_percent": mae_warp,
            "mae_persistence_percent": mae_persistence,
            # The distribution the display actually mixes on, so the
            # tolerance constants are chosen from data rather than taste.
            "advect_weight_median": float(numpy.median(advect_weight)),
            "advect_weight_above_half_fraction": float(numpy.mean(advect_weight > 0.5)),
            "confidence_median": float(numpy.median(confidence)),
            "leave_one_out": skill,
            "steering_prior": {
                "applied": bool(use_prior),
                "level_hpa": STEERING_LEVEL_BY_VARIABLE.get(variable),
                "mean_weight_carried": float(numpy.mean(prior_weights)) if prior_weights else 0.0,
                "held_out_improvement_with_prior": (
                    skill_with_prior["improvement_over_reversed_flow"] if skill_with_prior else None
                ),
                "held_out_improvement_without_prior": (
                    skill_without_prior["improvement_over_reversed_flow"] if skill_without_prior else None
                ),
            },
        }

    if not data_vars:
        return None

    derived = xarray.Dataset(
        data_vars,
        coords={
            "pair_from": ("pair", numpy.array([stamp.replace(tzinfo=None) for stamp in pair_from], dtype="datetime64[ns]")),
            "pair_to": ("pair", numpy.array([stamp.replace(tzinfo=None) for stamp in pair_to], dtype="datetime64[ns]")),
        },
        attrs={"method": METHOD, "derivation_version": VERSION, "base_revision_id": str(surface.revision_id)},
    )
    path = workdir / f"{surface.source_id}-cloud-motion.zarr.zip"
    write_zarr(derived, path)

    provenance = {
        "source_id": surface.source_id,
        "product": f"{surface.provenance.get('product', surface.source_id)} cloud motion (derived, display only)",
        "derived": True,
        "derivation": (
            "display-time interpolation support: " + METHOD + ". Derived here from the published "
            "surface artifact; not provider output, not evidence, never served on a data path."
        ),
        "derivation_version": VERSION,
        "base_revision_id": str(surface.revision_id),
        "base_object_key": surface.object_key,
        "quality": {"status": "derived", "per_variable": quality},
    }
    return RunResult(
        source_id=surface.source_id,
        provider_run_id=f"{surface.provider_run_id}+cloud-motion",
        run_time=surface.run_time,
        retrieved_at=datetime.now(UTC),
        complete=True,
        qc_passed=True,
        artifacts=[Artifact(LOGICAL_NAME, MEDIA_ZARR, path, provenance)],
        native_crs=surface.native_crs,
        notes=f"cloud motion derived from surface revision {surface.revision_id}",
    )


def cloud_motion_cycle(store: Any) -> list[str]:
    """Derive missing/stale motion artifacts. Never raises; returns log lines."""
    lines: list[str] = []
    try:
        current = {(item.source_id, item.logical_name): item for item in store.current_artifacts()}
    except Exception as error:
        return [f"cloud-motion: current artifacts unreadable - {error!r}"]
    for source_id, variables in CLOUD_MOTION_SOURCES.items():
        surface = current.get((source_id, "surface"))
        if surface is None:
            continue
        existing = current.get((source_id, LOGICAL_NAME))
        if (
            existing is not None
            and str(existing.provenance.get("base_revision_id", "")) == str(surface.revision_id)
            # A version bump re-derives even for an unchanged surface: an
            # artifact from an older construction never lingers as current.
            and str(existing.provenance.get("derivation_version", "")) == VERSION
        ):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix=f"{source_id}-cloud-motion-") as workdir:
                result = derive_cloud_motion(store, surface, variables, Path(workdir))
                if result is None:
                    lines.append(f"cloud-motion {source_id}: nothing derivable (no cloud variable with two frames)")
                    continue
                store.stage_and_publish(result)
            lines.append(f"cloud-motion {source_id}: published for surface revision {surface.revision_id}")
        except Exception as error:
            lines.append(f"cloud-motion {source_id}: derive failed - {error!r}")
    return lines
