"""Per-cell steering level from the observed cloud-top height (the AMV height-assignment problem).

One plugin, one module. See ``ingest.derive.methods`` for the contract.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    STEERING_LEVEL_BY_VARIABLE,
    _cell_metres,
    _consistency,
    _development_agreement,
    _dis_flow,
    _display_weight,
    _prior_corrected,
    _steering_prior,
    _supported_flow,
)
from ingest.derive.methods.contract import Requirement, InterpolationMethod, MethodContext, PairMotion
from ingest.derive.methods.baseline import BaselineMethod
from ingest.derive.methods.companion import published_companion


#: ``(deadline, resolver identity, dataset)`` of the last companion fetch.
#: ``configure`` scores the held-out reconstruction with and without the
#: prior, and each of those runs ``motion`` over a dozen hold-outs, so an
#: uncached hook would download the same artifact dozens of times per variable
#: per cycle. The resolver's identity is part of the key so a test that swaps
#: the hook is never answered from a cache filled by the real one.
#: The resolver is held by reference, not by id: two short-lived test doubles
#: can share an id once the first is collected, and a cache that confused them
#: would answer one test with another's fixture.
_companion_cache: tuple[float, Any, Any] | None = None

#: Refresh interval of the companion cache, seconds. Well inside the GOES
#: 10-minute scan cadence, so a cycle never reads a scan older than one it
#: could have had, and comfortably longer than one variable's derive.
COMPANION_CACHE_SECONDS = 300.0


def _cached_companion(source_id: str, logical_name: str) -> Any | None:
    """``published_companion`` with a short TTL. Absence caches too."""
    import time  # noqa: PLC0415

    global _companion_cache
    now = time.monotonic()
    resolver = published_companion
    if _companion_cache is not None:
        deadline, cached_resolver, dataset = _companion_cache
        if now < deadline and cached_resolver is resolver:
            return dataset
    dataset = published_companion(source_id, logical_name)
    _companion_cache = (now + COMPANION_CACHE_SECONDS, resolver, dataset)
    return dataset


#: The source and logical name of the observed cloud-top height artifact.
HEIGHT_SOURCE_ID = "noaa-goes-east"
HEIGHT_LOGICAL_NAME = "cloud_mask"
HEIGHT_VARIABLE = "cloud_top_height"

#: Geometric height of each steering level in the ICAO standard atmosphere,
#: metres above mean sea level - 1013.25 hPa, 288.15 K, 6.5 K/km, inverted
#: through p = p0 (1 - 2.25577e-5 z)^5.25588.
#:
#: The winds are published on pressure surfaces and ACHAF retrieves a HEIGHT,
#: so the two have to meet somewhere. The model's own geopotential heights are
#: not ingested, so the standard atmosphere is the honest substitute and its
#: error is stated rather than hidden: a warm or cold column moves a pressure
#: surface by roughly +/-150 m near 850 hPa and +/-400 m near 500 hPa, which
#: is small against the ~4.1 km gap between adjacent steering levels. This is
#: an assignment rule, not a retrieval - no displayed pixel comes from it.
ISA_LEVEL_HEIGHT_M = {850: 1457.3, 700: 3012.2, 500: 5574.4}

#: How far a GOES scan may sit from a frame pair's midpoint and still describe
#: that pair's cloud. One hour is the model frame interval itself: an observed
#: cloud-top height is valid at one instant, and the layers being interpolated
#: are forecast frames running to +24 h, so most pairs of a 28-hour artifact
#: have NO contemporaneous observation and must fall back. Widening this would
#: be applying an observation to weather it did not observe.
HEIGHT_OBSERVATION_WINDOW_SECONDS = 3600.0


def _pair_midpoint(dataset: Any, indices: tuple[int, int]) -> Any | None:
    """The instant halfway between a pair's two frames, or None."""
    import numpy  # noqa: PLC0415

    name = next((candidate for candidate in ("valid_time", "time") if candidate in dataset.coords), None)
    if name is None:
        return None
    try:
        values = numpy.asarray(dataset[name].values)
        if max(indices) >= values.size:
            return None
        stamps = values[list(indices)].astype("datetime64[ns]").astype("int64")
        return numpy.datetime64(int(stamps.mean()), "ns")
    except Exception:
        return None


def _grid_lat_lon(dataset: Any, shape: tuple[int, int]) -> tuple[Any, Any] | None:
    """The 2-D latitude/longitude of a dataset's cells, or None.

    HRDPS and RDPS publish on a rotated grid, so `latitude`/`longitude` are
    2-D over anonymous y/x; GFS publishes 1-D axes. Both are handled, and a
    grid whose coordinates do not match the field's own shape is refused
    rather than broadcast into something that looks plausible.
    """
    import numpy  # noqa: PLC0415

    lat_name = "latitude" if "latitude" in dataset.coords else "lat"
    lon_name = "longitude" if "longitude" in dataset.coords else "lon"
    if lat_name not in dataset.coords or lon_name not in dataset.coords:
        return None
    lat_values = numpy.asarray(dataset[lat_name].values, dtype="float64")
    lon_values = numpy.asarray(dataset[lon_name].values, dtype="float64")
    if lat_values.ndim == 1:
        lat2d, lon2d = numpy.meshgrid(lat_values, lon_values, indexing="ij")
    else:
        lat2d, lon2d = lat_values, lon_values
    if lat2d.shape != shape or lon2d.shape != shape:
        return None
    return lat2d, lon2d


def _nearest_on_regular_axes(values: Any, source_lat: Any, source_lon: Any, lat2d: Any, lon2d: Any) -> Any:
    """``values`` sampled at (lat2d, lon2d) by nearest source cell, else NaN.

    THE REGRIDDING RULE, stated once. The observed height arrives on the GOES
    artifact's regular latitude/longitude axes (already regridded off the ABI
    fixed grid by the adapter, nearest-neighbour, at no finer than the native
    footprint) and has to reach the model's own grid, which is rotated for
    HRDPS/RDPS and regular for GFS. Each destination cell centre takes the
    value of the single source cell it falls inside - index arithmetic on the
    regular source axes, no tree, no interpolation - and takes NOTHING where
    it falls inside no source cell.

    Nearest rather than an area mean, deliberately: a mean cloud-top height
    over a cell containing two strata is a height no cloud has, and height
    assignment is up to 70% of the error budget in multi-layer atmospheric
    motion vectors (Liu et al., GRL 2025). An observed value stays an observed
    value or becomes absent; it never becomes an average of two of them.

    Where the model cell is much coarser than the observation - GFS at 0.25
    degrees against a ~0.05 degree GOES cell - this under-samples, and that is
    accepted: one real cloud top is a better level assignment than a blend of
    twenty-five, and the alternative invents a level nothing was measured at.
    """
    import numpy  # noqa: PLC0415

    if source_lat.size < 2 or source_lon.size < 2:
        return numpy.full(lat2d.shape, numpy.nan)
    lat_step = float(numpy.median(numpy.diff(source_lat)))
    lon_step = float(numpy.median(numpy.diff(source_lon)))
    if not (numpy.isfinite(lat_step) and numpy.isfinite(lon_step)) or lat_step == 0.0 or lon_step == 0.0:
        return numpy.full(lat2d.shape, numpy.nan)
    rows = numpy.rint((lat2d - source_lat[0]) / lat_step).astype("int64")
    cols = numpy.rint((lon2d - source_lon[0]) / lon_step).astype("int64")
    inside = (rows >= 0) & (rows < source_lat.size) & (cols >= 0) & (cols < source_lon.size)
    safe_rows = numpy.clip(rows, 0, source_lat.size - 1)
    safe_cols = numpy.clip(cols, 0, source_lon.size - 1)
    # Half a source cell in each axis: the destination centre must actually
    # fall INSIDE the cell it was rounded to, not merely be closest to a grid
    # that ended before it.
    within = (
        (numpy.abs(source_lat[safe_rows] - lat2d) <= 0.5 * abs(lat_step))
        & (numpy.abs(source_lon[safe_cols] - lon2d) <= 0.5 * abs(lon_step))
    )
    sampled = numpy.asarray(values, dtype="float64")[safe_rows, safe_cols]
    return numpy.where(inside & within, sampled, numpy.nan)


def _observed_cloud_top_height(
    dataset: Any, indices: tuple[int, int], shape: tuple[int, int], companion: Any
) -> Any | None:
    """The observed cloud-top height on this pair's own grid, or None.

    None where there is no companion artifact, no height variable, no usable
    grid, or no scan close enough in time to describe this pair. Every one of
    those is an absence, and an absence sends the method back to the single
    steering level rather than to a guessed height.
    """
    import numpy  # noqa: PLC0415

    if companion is None:
        return None
    try:
        if HEIGHT_VARIABLE not in companion.data_vars:
            return None
        grid = _grid_lat_lon(dataset, shape)
        if grid is None:
            return None
        lat2d, lon2d = grid
        field = companion[HEIGHT_VARIABLE]
        time_name = next((dim for dim in ("valid_time", "time") if dim in field.dims), None)
        if time_name is not None:
            midpoint = _pair_midpoint(dataset, indices)
            if midpoint is None:
                return None
            scans = numpy.asarray(companion[time_name].values).astype("datetime64[ns]")
            offsets = numpy.abs((scans - midpoint).astype("timedelta64[s]").astype("float64"))
            nearest = int(numpy.argmin(offsets))
            if float(offsets[nearest]) > HEIGHT_OBSERVATION_WINDOW_SECONDS:
                # An observation of now is not an observation of +18 h.
                return None
            field = field.isel({time_name: nearest})
        source_lat = numpy.asarray(companion["latitude"].values, dtype="float64")
        source_lon = numpy.asarray(companion["longitude"].values, dtype="float64")
        if source_lat.ndim != 1 or source_lon.ndim != 1:
            return None
        values = numpy.asarray(field.values, dtype="float64")
        if values.shape != (source_lat.size, source_lon.size):
            # A mismatched shape is refused, never reshaped into agreement.
            return None
        height = _nearest_on_regular_axes(values, source_lat, source_lon, lat2d, lon2d)
    except Exception:
        return None
    if height.shape != shape:
        return None
    return numpy.where(numpy.isfinite(height) & (height > 0.0), height, numpy.nan)


def _height_steering_prior(
    dataset: Any,
    variable: str,
    indices: tuple[int, int],
    interval_seconds: float,
    shape: tuple[int, int],
    height: Any | None,
) -> tuple[Any, float] | None:
    """The per-cell steering wind at each cell's own cloud top, in grid cells.

    Returns ``(prior, observed fraction)``, or None when the levels are not
    all published - in which case the caller falls back to the single-level
    prior the baseline already earns its place with.

    Where a cell has an observed cloud top, the wind is interpolated linearly
    in height between the two bracketing steering levels and clamped outside
    them, because an extrapolated wind at 12 km is not a measurement of
    anything. Where it has no observed top - clear sky, off the observation's
    grid, a flagged retrieval, or a pair with no contemporaneous scan - the
    cell keeps the variable's single steering level exactly as before. An
    absent height is an absent height.
    """
    import numpy  # noqa: PLC0415

    fallback_level = STEERING_LEVEL_BY_VARIABLE.get(variable)
    if fallback_level is None or interval_seconds <= 0 or fallback_level not in ISA_LEVEL_HEIGHT_M:
        return None
    # Ordered by HEIGHT, not by pressure: 850 is the lowest level and 500 the
    # highest, and the blend below walks upward through the column.
    levels = sorted(ISA_LEVEL_HEIGHT_M, key=ISA_LEVEL_HEIGHT_M.__getitem__)
    winds: dict[int, tuple[Any, Any]] = {}
    try:
        for level in levels:
            names = (f"wind_u_{level}hPa", f"wind_v_{level}hPa")
            if any(name not in dataset.data_vars for name in names):
                return None
            pair_values = []
            for name in names:
                field = dataset[name]
                time_name = next((dim for dim in ("valid_time", "time") if dim in field.dims), None)
                if time_name is None or field.sizes[time_name] <= max(indices):
                    return None
                # The interval's mean wind: the two endpoints' own values, the
                # same rule the single-level prior uses.
                pair = field.isel({time_name: list(indices)}).values
                component = numpy.nanmean(numpy.asarray(pair, dtype="float64"), axis=0)
                if component.shape != shape:
                    return None
                pair_values.append(numpy.nan_to_num(component))
            winds[level] = (pair_values[0], pair_values[1])
        grid = _grid_lat_lon(dataset, shape)
        if grid is None:
            return None
        lat2d, lon2d = grid
    except Exception:
        # A prior that cannot be read is simply absent, exactly as before.
        return None

    observed = numpy.zeros(shape, dtype=bool) if height is None else numpy.isfinite(height)
    # Start every cell on the variable's single steering level, then move only
    # the cells that have an observation of their own. This is fence five in
    # code: the method reduces EXACTLY to the shipped single-level prior
    # wherever nothing was observed, so the two can only differ where a real
    # cloud top says they should.
    wind_u = numpy.array(winds[fallback_level][0], dtype="float64", copy=True)
    wind_v = numpy.array(winds[fallback_level][1], dtype="float64", copy=True)
    if observed.any():
        tops = numpy.where(observed, numpy.nan_to_num(height, nan=0.0), 0.0)
        # The piecewise blend, written out rather than through numpy.interp,
        # which interpolates a shared table and cannot take a per-cell one.
        # Starting at the lowest level and clamping each weight into [0, 1] is
        # the no-extrapolation rule made explicit: a cell below 850 hPa keeps
        # the 850 wind and a cell above 500 hPa keeps the 500 wind, because an
        # extrapolated wind at 12 km is not a measurement of anything.
        blend_u = numpy.array(winds[levels[0]][0], dtype="float64", copy=True)
        blend_v = numpy.array(winds[levels[0]][1], dtype="float64", copy=True)
        for lower, upper in zip(levels, levels[1:]):
            span = ISA_LEVEL_HEIGHT_M[upper] - ISA_LEVEL_HEIGHT_M[lower]
            weight = numpy.clip((tops - ISA_LEVEL_HEIGHT_M[lower]) / span, 0.0, 1.0)
            blend_u = blend_u + weight * (winds[upper][0] - blend_u)
            blend_v = blend_v + weight * (winds[upper][1] - blend_v)
        wind_u = numpy.where(observed, blend_u, wind_u)
        wind_v = numpy.where(observed, blend_v, wind_v)

    east_metres, north_metres, row_sign = _cell_metres(lat2d, lon2d)
    prior = numpy.zeros(shape + (2,), dtype="float64")
    prior[..., 0] = wind_u * interval_seconds / east_metres
    prior[..., 1] = row_sign * wind_v * interval_seconds / north_metres
    return prior, float(numpy.mean(observed))


class HeightSteeringMethod(BaselineMethod):
    """The steering level assigned per cell, from the observed cloud top.

    ``total_cloud`` superposes strata moving at different speeds, so no single
    flow field is correct for it and no single steering level is either. The
    shipped prior gives it a flat 700 hPa. This is the multi-layer
    atmospheric-motion-vector problem, where HEIGHT ASSIGNMENT is up to 70% of
    the total error (Liu et al., GRL 2025, on overlapped cloud-motion vectors;
    the EUMETrain AMV tutorial says the same in the operational voice), and
    the textbook answer is to give each tracked feature the wind at its own
    cloud-top height.

    Both halves are retrievals this store already holds: GOES-19 ACHAF gives
    an observed per-pixel cloud top, and the model publishes 850/700/500 hPa
    winds. So each cell takes the wind interpolated to ITS OWN observed top,
    and the result is then used exactly as the shipped prior is used - the
    four fences of the existing carve-out are not re-implemented here, they
    are the same ``_prior_corrected`` call, unchanged:

    1. Unsupported cells only - an observed image motion is never overridden.
    2. Agreement-weighted - an uncorroborated wind reaches nothing.
    3. Stationarity gate - refused where a well-supported image flow reports
       the field standing still, which is the Avalon's in-place orographic and
       marine regime, and where a prior would drag standing fog across the
       peninsula and call it motion.
    4. Earned per variable, through the inherited ``configure`` hook, with
       both held-out numbers published either way.

    And a fifth, which is this method's own: where no ACHAF height is
    available for a cell - clear sky, off the observation's grid, a flagged
    retrieval, or a forecast pair with no contemporaneous scan - the cell
    falls back to the existing single-level behaviour rather than guessing a
    height. An absent height is an absent height.

    The composite is the baseline's, INHERITED UNCHANGED and deliberately so:
    the only variable under test here is the motion field, which is what makes
    the comparison against the baseline a controlled one. That is also why the
    shader stays ``hermite`` - the client draws this method with exactly the
    construction it already draws the baseline with.

    Cross-source: this is a GOES observation informing a model layer's motion,
    which the steering-prior carve-out as written does not permit. It ships
    only under the amendment recorded in this change's proposal.
    """

    id = "height-steering"
    title = "Steering wind at the observed cloud top"
    summary = (
        "The same construction as the shipped advection, with one change to the motion: instead "
        "of one steering level for the whole variable, each cell takes the model wind at the "
        "cloud-top height GOES-19 actually observed over it, interpolated between the 850, 700 "
        "and 500 hPa winds. Cells with no observed cloud top keep the single-level behaviour "
        "exactly, and the wind still only fills what the imagery could not read."
    )
    shader = "hermite"


    def requirements(self) -> list[Requirement]:
        """The observed cloud top, and a scan close enough in time to use it."""
        companion = published_companion(HEIGHT_SOURCE_ID, HEIGHT_LOGICAL_NAME)
        has_height = companion is not None and "cloud_top_height" in getattr(companion, "data_vars", {})
        return [Requirement(
            name="observed cloud-top height",
            met=bool(has_height),
            detail=(
                "GOES-19 cloud-top height is published, so each cell can take the wind at the "
                "height observed over it"
                if has_height else
                "no published GOES-19 artifact carries cloud_top_height, so every cell falls back "
                "to the variable's single steering level and this method draws exactly what the "
                "shipped prior draws"
            ),
        )]

    def configure(self, context: MethodContext) -> tuple[InterpolationMethod, dict[str, Any]]:
        """The baseline's measurement, with the level assignment named honestly.

        ``BaselineMethod.configure`` builds ``type(self)``, so this scores THIS
        method's own construction with and without the prior. Only the note
        changes: reporting a single ``level_hpa`` for a per-cell assignment
        would be a false claim about what was applied.
        """
        method, notes = super().configure(context)
        return method, {
            **notes,
            "level_assignment": (
                "per cell, from the observed GOES-19 ACHAF cloud top, interpolated between the "
                "850/700/500 hPa winds at their standard-atmosphere heights"
            ),
            "fallback_level_hpa": notes.get("level_hpa"),
        }

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The baseline's derivation with the per-cell prior substituted.

        The loop is the baseline's, written out rather than hooked, because
        the baseline is not this change's to alter and a seam added to it
        would be. Everything up to the prior is identical, and the prior is
        applied through the same ``_prior_corrected``.
        """
        import numpy  # noqa: PLC0415

        shape = numpy.asarray(context.frames[0]).shape
        companion = None
        if self.use_prior and context.dataset is not None:
            companion = _cached_companion(HEIGHT_SOURCE_ID, HEIGHT_LOGICAL_NAME)
        results: list[PairMotion] = []
        for position in range(len(context.frames) - 1):
            previous = context.frames[position]
            following = context.frames[position + 1]
            raw01 = _dis_flow(previous, following)
            raw10 = _dis_flow(following, previous)
            agreed = _consistency(raw01, raw10)
            flow01, support = _supported_flow(raw01.astype("float64"), agreed)
            flow10, _ = _supported_flow(raw10.astype("float64"), agreed)
            carried = 0.0
            observed_fraction = 0.0
            if self.use_prior and context.dataset is not None:
                pair_indices = (context.indices[position], context.indices[position + 1])
                height = _observed_cloud_top_height(context.dataset, pair_indices, shape, companion)
                assigned = _height_steering_prior(
                    context.dataset, context.variable, pair_indices, context.interval_seconds, shape, height
                )
                if assigned is not None:
                    prior, observed_fraction = assigned
                else:
                    # Not all three levels published: no per-cell assignment is
                    # possible, so the method degrades to the shipped
                    # single-level prior rather than failing the artifact.
                    prior = _steering_prior(
                        context.dataset,
                        context.variable,
                        pair_indices,
                        context.interval_seconds,
                        shape,
                    )
                if prior is not None:
                    flow01, carried = _prior_corrected(flow01, support, prior)
                    flow10, _ = _prior_corrected(flow10, support, -prior)
            results.append(
                PairMotion(
                    flow01=flow01,
                    flow10=flow10,
                    confidence=agreed,
                    support=support,
                    advect_weight=_display_weight(support, _development_agreement(previous, following, flow01)),
                    diagnostics={
                        "prior_weight_carried": carried,
                        # How much of the field the OBSERVATION actually
                        # reached, so "the cloud top was used" is checkable
                        # rather than asserted. On a 28-hour forecast artifact
                        # most pairs have no contemporaneous scan and this is
                        # legitimately zero.
                        "observed_height_fraction": observed_fraction,
                    },
                )
            )
        return results


#: The fractions of an interval a held-out frame is reconstructed at. The
#: midpoint is the hardest case and the one the shipped thresholds were
#: measured against; the thirds are reached by holding a frame out of a
#: three-interval span, and they catch a construction that is right at the
#: middle and wrong on the way there - which a midpoint-only score cannot
#: see, and which is exactly what the reader watches during playback.
