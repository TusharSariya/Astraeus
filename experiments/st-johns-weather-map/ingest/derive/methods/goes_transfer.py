"""CMORPH: motion from the ten-minute observed cloud mask, applied to an hourly model layer.

One plugin, one module. See ``ingest.derive.methods`` for the contract.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    FB_TOLERANCE_FLOOR_CELLS,
    FLOW_FILL_SIGMA_CELLS,
    PRIOR_AGREEMENT_FRACTION,
    STATIONARY_CELLS,
    _cell_metres,
    _dis_flow,
    _display_weight,
    _gaussian,
    _prior_corrected,
)
from ingest.derive.methods.contract import Requirement, InterpolationMethod, MethodContext, PairMotion
from ingest.derive.methods.baseline import TCDC_NOTE, BaselineMethod
from ingest.derive.methods.harness import _interpolation_skill, admit, admit_reasons
from ingest.derive.methods.companion import published_companion


#: The observed companion `goes-transfer` propagates its motion from.
GOES_SOURCE_ID = "noaa-goes-east"
GOES_LOGICAL_NAME = "cloud_mask"
#: How close a GOES scan must sit to a model instant to be called that
#: instant. A Full Disk scan starts about 20 s past the ten-minute mark
#: (measured: 08:40:20.5Z, 08:50:20.5Z, ...), so the tolerance has to clear
#: that offset while refusing a missing scan, which would be 600 s away.
#: This is the "exact or absent" fence, not a smoothing parameter.
GOES_ALIGNMENT_TOLERANCE_SECONDS = 120.0
#: The largest step the composed chain may take. The product is ten-minutely;
#: a step past this means a scan is missing and the chain is refused rather
#: than stretched across the hole.
GOES_MAX_STEP_SECONDS = 900.0
#: Which stored field the flow is derived from. `cloud_class` is a four-level
#: categorical mask (0/1/2/3, 255 invalid) and DIS on it sees a field made of
#: plateaus and step edges; `cloud_probability` is the same retrieval's
#: continuous 0-1 confidence on the same cells, which is what a gradient-based
#: estimator can actually differentiate. Measured on the live 2026-09-01
#: sequence (see the change's tasks.md): the probability field is the better
#: input, and the class ramp is the documented fallback for a granule whose
#: probabilities did not survive its DQF screen.
GOES_MOTION_FIELD = "cloud_probability"
#: The class ramp used only when probabilities are unusable. Monotone in cloud
#: amount so the edges land where the mask's edges are; it is NOT a claim that
#: "probably cloudy" means 75 percent cover, and no value from it is ever
#: displayed - it exists to give the estimator something to track.
GOES_CLASS_PERCENT = {0: 0.0, 1: 25.0, 2: 75.0, 3: 100.0}
GOES_INVALID_CLASS = 255
#: Fraction of the composed chain a model cell must have been observed
#: through before a transferred displacement is offered there at all.
GOES_COVERAGE_FLOOR = 0.5
#: How long a fetched companion is reused. One GOES scan interval: within a
#: derive cycle every method and every variable then transfers from the same
#: scans, which is what makes their published scores comparable, and a later
#: cycle re-reads rather than propagating a stale mask.
GOES_COMPANION_TTL_SECONDS = 600.0

_COMPANION_CACHE: dict[tuple[str, str], tuple[float, Any]] = {}


def _cached_companion(source_id: str, logical_name: str) -> Any | None:
    """`published_companion` with a one-scan-interval memo. None stays None."""
    import time  # noqa: PLC0415

    key = (source_id, logical_name)
    now = time.monotonic()
    cached = _COMPANION_CACHE.get(key)
    if cached is not None and now - cached[0] < GOES_COMPANION_TTL_SECONDS:
        return cached[1]
    dataset = published_companion(source_id, logical_name)
    _COMPANION_CACHE[key] = (now, dataset)
    return dataset


def _instants(dataset: Any, indices: tuple[int, ...]) -> list[Any] | None:
    """The absolute UTC instants of these frame positions, or None.

    Positions index the SORTED time axis, which is what ``_frame_stack``
    hands the derive; sorting here rather than trusting the stored order
    keeps the alignment honest on an artifact whose axis is not monotonic.
    """
    from datetime import timezone  # noqa: PLC0415

    import numpy  # noqa: PLC0415
    import pandas  # noqa: PLC0415

    name = next((candidate for candidate in ("valid_time", "time") if candidate in dataset.coords), None)
    if name is None:
        return None
    try:
        stamps = [
            pandas.Timestamp(value).to_pydatetime().replace(tzinfo=timezone.utc)
            for value in numpy.asarray(dataset[name].values).ravel()
        ]
    except Exception:
        return None
    stamps.sort()
    if any(index >= len(stamps) for index in indices):
        return None
    return [stamps[index] for index in indices]


def _goes_percent(companion: Any, position: int) -> tuple[Any, Any] | None:
    """One GOES scan as a 0-100 field plus its observed mask, or None.

    A cloud MASK is not a cloud FRACTION, and nothing here pretends otherwise:
    the returned field is never displayed and never mixed into a model layer.
    It exists only to be differentiated, so that the displacement it yields
    can be transferred. Unobserved cells are returned as 0 with the mask
    saying so, because the estimator needs a filled array and the coverage
    mask is what stops those cells from carrying a displacement.
    """
    import numpy  # noqa: PLC0415

    def sliced(name: str) -> Any | None:
        if name not in companion.data_vars:
            return None
        field = companion[name]
        time_name = next((dim for dim in ("valid_time", "time") if dim in field.dims), None)
        if time_name is None or field.sizes[time_name] <= position:
            return None
        return numpy.asarray(field.isel({time_name: position}).values, dtype="float64")

    classes = sliced("cloud_class")
    if classes is None:
        return None
    observed = classes != GOES_INVALID_CLASS
    values = sliced(GOES_MOTION_FIELD) if GOES_MOTION_FIELD != "cloud_class" else None
    if values is not None and numpy.isfinite(values).any():
        percent = numpy.where(numpy.isfinite(values), values * 100.0, 0.0)
        observed = observed & numpy.isfinite(values)
    else:
        # The categorical fallback. Documented, measured, and second choice.
        percent = numpy.zeros(classes.shape, dtype="float64")
        for level, amount in GOES_CLASS_PERCENT.items():
            percent[classes == level] = amount
    return numpy.where(observed, percent, 0.0), observed.astype("float64")


def _goes_chain(companion: Any, start: Any, end: Any) -> list[tuple[Any, Any]] | None:
    """The scans that exactly span ``start``..``end``, in order, or None.

    Fence 5, and the reason it is a hard refusal: interpolation error grows
    with the gap, which is the entire premise of transferring motion from a
    ten-minute product onto an hourly one. A chain that does not actually
    reach both endpoints is not a shorter gap, it is an extrapolation - so a
    missing scan means no prior for that pair, disclosed, rather than a
    stretched or stale one.
    """
    import numpy  # noqa: PLC0415

    stamps = _instants(companion, tuple(range(int(companion.sizes.get("valid_time", 0)) or 0)))
    if not stamps:
        return None
    seconds = numpy.array([stamp.timestamp() for stamp in stamps], dtype="float64")
    order = numpy.argsort(seconds)
    seconds = seconds[order]
    first = int(numpy.argmin(numpy.abs(seconds - start.timestamp())))
    last = int(numpy.argmin(numpy.abs(seconds - end.timestamp())))
    if abs(seconds[first] - start.timestamp()) > GOES_ALIGNMENT_TOLERANCE_SECONDS:
        return None
    if abs(seconds[last] - end.timestamp()) > GOES_ALIGNMENT_TOLERANCE_SECONDS:
        return None
    if last <= first:
        return None
    steps = numpy.diff(seconds[first : last + 1])
    if steps.size == 0 or float(steps.max()) > GOES_MAX_STEP_SECONDS:
        return None
    scans: list[tuple[Any, Any]] = []
    for position in range(first, last + 1):
        scan = _goes_percent(companion, int(order[position]))
        if scan is None:
            return None
        scans.append(scan)
    return scans


def _composed_displacement(scans: list[tuple[Any, Any]]) -> tuple[Any, Any]:
    """Short-interval flows composed into one displacement, plus coverage.

    CMORPH's construction (Joyce et al., J. Hydrometeorol. 2004): motion is
    estimated across the frequent observed sequence and the displacements are
    chained, so the estimator never has to solve for an hour of motion in one
    step. The chaining is Lagrangian - each leg is read at where the parcel
    has already been carried to, not at where it started - because adding the
    legs at fixed positions would be an Eulerian sum and would only be correct
    for a uniform field.
    """
    import numpy  # noqa: PLC0415

    rows, cols = scans[0][0].shape
    row_index, col_index = numpy.mgrid[0:rows, 0:cols].astype("float64")
    total = numpy.zeros((rows, cols, 2), dtype="float64")
    coverage = numpy.ones((rows, cols), dtype="float64")
    for index in range(len(scans) - 1):
        leg = numpy.asarray(_dis_flow(scans[index][0], scans[index + 1][0]), dtype="float64")
        sample_rows = numpy.clip(numpy.rint(row_index + total[..., 1]).astype("int64"), 0, rows - 1)
        sample_cols = numpy.clip(numpy.rint(col_index + total[..., 0]).astype("int64"), 0, cols - 1)
        total[..., 0] += leg[sample_rows, sample_cols, 0]
        total[..., 1] += leg[sample_rows, sample_cols, 1]
        coverage = numpy.minimum(coverage, scans[index][1])
    coverage = numpy.minimum(coverage, scans[-1][1])
    return total, coverage


def _bilinear(field: Any, rows: Any, cols: Any) -> Any:
    """``field`` sampled at fractional (row, col), clamped at the edges."""
    import numpy  # noqa: PLC0415

    height, width = field.shape
    row0 = numpy.clip(numpy.floor(rows), 0, height - 1).astype("int64")
    col0 = numpy.clip(numpy.floor(cols), 0, width - 1).astype("int64")
    row1 = numpy.clip(row0 + 1, 0, height - 1)
    col1 = numpy.clip(col0 + 1, 0, width - 1)
    row_fraction = numpy.clip(rows - row0, 0.0, 1.0)
    col_fraction = numpy.clip(cols - col0, 0.0, 1.0)
    top = field[row0, col0] * (1.0 - col_fraction) + field[row0, col1] * col_fraction
    bottom = field[row1, col0] * (1.0 - col_fraction) + field[row1, col1] * col_fraction
    return top * (1.0 - row_fraction) + bottom * row_fraction


def _regridded_transfer(
    displacement: Any, coverage: Any, companion: Any, dataset: Any, shape: tuple[int, int]
) -> tuple[Any, Any] | None:
    """The GOES displacement expressed in the MODEL layer's own grid cells.

    The two grids share nothing: GOES is published on a regular lat/lon grid
    resampled from the ABI fixed grid (~0.050 lat x 0.062 lon here), and
    HRDPS and RDPS are rotated lat/lon with 2-D coordinates while GFS is a
    regular half-degree box. So the regrid rule is stated in the one thing
    both grids agree on - metres on the ground:

    1. GOES cells -> degrees, using the companion's own published axes;
    2. degrees -> metres east and north at each source cell's latitude;
    3. that metric field sampled bilinearly at every model cell's own
       latitude and longitude (nearest would quantise a sub-cell displacement
       to zero on the coarser model grids);
    4. metres -> model cells through ``_cell_metres``, the same conversion
       and the same row-sign convention the steering prior already uses.

    A shape that does not match the model layer's frames is refused, never
    coerced: a displacement filed against the wrong grid would move the
    weather in the wrong direction and look entirely plausible doing it.
    """
    import numpy  # noqa: PLC0415

    lat_name = "latitude" if "latitude" in companion.coords else "lat"
    lon_name = "longitude" if "longitude" in companion.coords else "lon"
    if lat_name not in companion.coords or lon_name not in companion.coords:
        return None
    source_lat = numpy.asarray(companion[lat_name].values, dtype="float64")
    source_lon = numpy.asarray(companion[lon_name].values, dtype="float64")
    if source_lat.ndim != 1 or source_lon.ndim != 1 or source_lat.size < 2 or source_lon.size < 2:
        return None
    if displacement.shape[:2] != (source_lat.size, source_lon.size):
        return None
    lat_step = float(source_lat[1] - source_lat[0])
    lon_step = float(source_lon[1] - source_lon[0])
    if not (lat_step and lon_step):
        return None

    metres_per_degree = 111_320.0
    source_lat2d = source_lat[:, None] * numpy.ones_like(source_lon)[None, :]
    east_metres = displacement[..., 0] * lon_step * metres_per_degree * numpy.cos(numpy.radians(source_lat2d))
    north_metres = displacement[..., 1] * lat_step * metres_per_degree

    model_lat_name = "latitude" if "latitude" in dataset.coords else "lat"
    model_lon_name = "longitude" if "longitude" in dataset.coords else "lon"
    if model_lat_name not in dataset.coords or model_lon_name not in dataset.coords:
        return None
    model_lat = numpy.asarray(dataset[model_lat_name].values, dtype="float64")
    model_lon = numpy.asarray(dataset[model_lon_name].values, dtype="float64")
    if model_lat.ndim == 1:
        model_lat2d, model_lon2d = numpy.meshgrid(model_lat, model_lon, indexing="ij")
    else:
        model_lat2d, model_lon2d = model_lat, model_lon
    if model_lat2d.shape != shape or model_lon2d.shape != shape:
        return None

    rows = (model_lat2d - source_lat[0]) / lat_step
    cols = (model_lon2d - source_lon[0]) / lon_step
    inside = (rows >= 0) & (rows <= source_lat.size - 1) & (cols >= 0) & (cols <= source_lon.size - 1)
    east = _bilinear(east_metres, rows, cols)
    north = _bilinear(north_metres, rows, cols)
    covered = _bilinear(coverage, rows, cols) * inside.astype("float64")

    cell_east, cell_north, row_sign = _cell_metres(model_lat2d, model_lon2d)
    transfer = numpy.zeros(shape + (2,), dtype="float64")
    transfer[..., 0] = numpy.where(inside, east / cell_east, 0.0)
    transfer[..., 1] = numpy.where(inside, row_sign * north / cell_north, 0.0)
    return transfer, (covered >= GOES_COVERAGE_FLOOR).astype("float64")


def _transfer_corrected(flow: Any, support: Any, transfer: Any, covered: Any) -> tuple[Any, float]:
    """``flow`` filled toward the transferred motion where the model is silent.

    The expressions are the steering prior's (``_prior_corrected``), because
    the fences are the same fences and a second, subtly different version of
    them would be a second thing to audit. The one addition is the coverage
    mask: a model cell the GOES chain did not observe through gets nothing,
    and - this is the part worth reading twice - it is also excluded from the
    corroboration average, so cells with no observation behind them cannot
    inflate the agreement that decides how far the transfer reaches.

    Fence 1: the weight carries ``1 - support``, so an observed model-layer
    motion is never overridden. Fence 2: it is scaled by how well the
    transferred field matches the model flow in the cells that ARE trusted.
    Fence 3: it is zeroed wherever a well-supported model flow reports the
    field standing still - the Avalon's orographic and marine cloud forms and
    dissipates in place while wind blows through it, and a transferred motion
    applied there would drag standing fog across the peninsula.
    """
    import numpy  # noqa: PLC0415

    trusted = numpy.clip(numpy.asarray(support, dtype="float64"), 0.0, 1.0)
    observed = numpy.clip(numpy.asarray(covered, dtype="float64"), 0.0, 1.0)
    speed = numpy.hypot(flow[..., 0], flow[..., 1])
    difference = numpy.hypot(transfer[..., 0] - flow[..., 0], transfer[..., 1] - flow[..., 1])
    tolerance = numpy.maximum(
        PRIOR_AGREEMENT_FRACTION * numpy.hypot(transfer[..., 0], transfer[..., 1]), FB_TOLERANCE_FLOOR_CELLS
    )
    agreement = numpy.clip(1.0 - difference / tolerance, 0.0, 1.0)
    weights = numpy.maximum(trusted * observed, 1e-6)
    corroboration = float(numpy.average(agreement, weights=weights))
    stationary = (trusted > 0.5) & (speed < STATIONARY_CELLS)
    weight = (1.0 - trusted) * corroboration * observed
    weight[stationary] = 0.0
    weight = _gaussian(weight, FLOW_FILL_SIGMA_CELLS)
    corrected = numpy.array(flow, dtype="float64", copy=True)
    for axis in (0, 1):
        corrected[..., axis] = flow[..., axis] + weight * (transfer[..., axis] - flow[..., axis])
    return corrected, float(numpy.mean(weight))


class GOESTransferMethod(BaselineMethod):
    """CMORPH: motion from the ten-minute observation, applied to the hourly model.

    Interpolation error grows with the gap being interpolated across, and the
    model layers are the wide-gap case: hourly frames whose cloud moves about
    fifteen grid cells between them. The GOES-19 Enterprise Cloud Mask this
    project already ingests is ten-minutely - a sixfold shorter gap - so the
    displacement across a model hour can be built out of six short steps the
    estimator can actually solve, rather than one long one it cannot. That is
    CMORPH's design (Joyce et al., J. Hydrometeorol. 2004), which propagates
    an infrequent product along motion vectors taken from frequent
    geostationary imagery.

    What crosses the source boundary is a DISPLACEMENT FIELD and nothing
    else. No GOES pixel is composited into a model layer; the two frames
    drawn stay the model layer's own retrieved frames, and the composite is
    the baseline's, inherited unchanged - so the only variable under test
    against `baseline` is the motion field, which is what makes the
    comparison controlled.

    Five fences, mirroring the steering prior's four and adding the one the
    cross-source case needs:

    1. **Unsupported cells only.** The imagery being drawn is the authority
       on its own motion; a transferred motion never overrides it.
    2. **Agreement-weighted.** Weighted by how well the transferred field
       matches the model flow where that flow IS trusted, so a motion the
       model layer contradicts reaches nothing.
    3. **Stationarity gate.** Refused wherever a well-supported model flow
       reports the field standing still.
    4. **Earned per variable.** Scored with and without, applied only if the
       held-out reconstruction improves, both numbers published either way.
    5. **Time alignment is exact or the prior is absent.** The GOES scans
       must actually span the model pair's interval, with no gap in the
       chain. Nothing is extrapolated, stretched or taken stale; a gap means
       no prior for that pair, disclosed.

    Absent, stale or non-spanning GOES is the ordinary case rather than a
    failure: model layers are forecasts running a day ahead and the
    observation only exists in the past, so most pairs get no transfer and
    fall back to the baseline motion exactly. The diagnostics say how many
    pairs were actually reached.
    """

    id = "goes-transfer"
    title = "Motion transferred from the GOES cloud mask"
    summary = (
        "The same two retrieved model frames, warped along a motion field built from the "
        "ten-minute GOES-19 cloud mask instead of from the hourly model layer alone (CMORPH, "
        "Joyce et al. 2004): six short observed steps composed into one hour rather than one "
        "hour solved in a single step. The observation contributes a displacement only - no "
        "satellite pixel is ever drawn into a model layer - it fills only cells the model "
        "layer's own flow leaves unsupported, is weighted by its agreement with that flow, is "
        "refused where the model flow says the field is standing still, and is absent entirely "
        "for any pair the GOES scans do not exactly span."
    )
    plain = "Ten-minute satellite frames give motion in short steps instead of one hourly jump."
    gap = "Needs a rolling scan sequence the ingest does not keep; today draws exactly entry 1."
    notes = (
        "CMORPH morphing (Joyce et al. 2004, J. Hydrometeorol. 5): short-step displacements from "
        "the ten-minute GOES-19 cloud mask composed Lagrangian into one model interval; "
        "displacement only, never a value. " + TCDC_NOTE
    )


    def requirements(self) -> list[Requirement]:
        """A sequence of scans, not one - the whole premise of the method."""
        companion = published_companion(GOES_SOURCE_ID, GOES_LOGICAL_NAME)
        scans = 0
        if companion is not None:
            for name in ("valid_time", "time"):
                if name in getattr(companion, "sizes", {}):
                    scans = int(companion.sizes[name])
                    break
        return [Requirement(
            name="ten-minute scan sequence",
            met=scans > 1,
            detail=(
                f"the published cloud-mask artifact carries {scans} scans, enough to compose a "
                "displacement across a model interval"
                if scans > 1 else
                f"the published cloud-mask artifact carries {scans} scan, so no interval can be "
                "spanned and every pair falls back to the layer's own motion. The adapter would "
                "have to retain a rolling sequence for this method to do anything"
            ),
        )]

    def __init__(self, *, use_prior: bool = False, use_transfer: bool = False) -> None:
        super().__init__(use_prior=use_prior)
        self.use_transfer = use_transfer

    def configure(self, context: MethodContext) -> tuple[InterpolationMethod, dict[str, Any]]:
        """Fence 4: the transfer is applied only where it measurably helps.

        The steering prior's own question is settled first, on this method's
        construction and with the transfer off, so the transfer is judged as
        an addition to a fully configured baseline rather than against a
        weaker one. Both scores are published either way.
        """
        based, prior_notes = super().configure(context)
        notes: dict[str, Any] = {
            "steering_prior": prior_notes,
            "applied": False,
            "companion": f"{GOES_SOURCE_ID}/{GOES_LOGICAL_NAME}",
            "motion_field": GOES_MOTION_FIELD,
            "skill": prior_notes.get("skill"),
        }
        if context.dataset is None:
            notes["absent_reason"] = "no model dataset, so no grid to transfer onto"
            return type(self)(use_prior=False, use_transfer=False), notes
        if _cached_companion(GOES_SOURCE_ID, GOES_LOGICAL_NAME) is None:
            notes["absent_reason"] = "no published GOES cloud mask to transfer from"
            return type(self)(use_prior=based.use_prior, use_transfer=False), notes
        without = prior_notes.get("skill")
        with_transfer = _interpolation_skill(
            context.frames,
            method=type(self)(use_prior=based.use_prior, use_transfer=True),
            dataset=context.dataset,
            variable=context.variable,
            interval_seconds=context.interval_seconds,
            indices=context.indices,
            cache=context.cache,
        )
        # Fixed controls only (`harness.admit`); the reversed-flow ratio is
        # published beside the decision, never read by it.
        use_transfer = admit(with_transfer, without)
        read = lambda skill, name: skill[name] if skill else None  # noqa: E731
        notes["applied"] = bool(use_transfer)
        notes["held_out_improvement_with_transfer"] = read(with_transfer, "improvement_over_crossfade")
        notes["held_out_improvement_without_transfer"] = read(without, "improvement_over_crossfade")
        notes["held_out_improvement_over_advection_with_transfer"] = read(with_transfer, "improvement_over_advection")
        notes["held_out_improvement_over_advection_without_transfer"] = read(without, "improvement_over_advection")
        notes["held_out_ssim_with_transfer"] = read(with_transfer, "midpoint_ssim")
        notes["held_out_ssim_without_transfer"] = read(without, "midpoint_ssim")
        notes["held_out_sharpness_ratio_with_transfer"] = read(with_transfer, "midpoint_sharpness_ratio")
        notes["held_out_sharpness_ratio_without_transfer"] = read(without, "midpoint_sharpness_ratio")
        notes["held_out_improvement_over_reversed_flow_with_transfer"] = read(
            with_transfer, "improvement_over_reversed_flow"
        )
        notes["held_out_improvement_over_reversed_flow_without_transfer"] = read(
            without, "improvement_over_reversed_flow"
        )
        notes["transfer_admission"] = admit_reasons(with_transfer, without)
        notes["skill"] = with_transfer if use_transfer else without
        return type(self)(use_prior=based.use_prior, use_transfer=use_transfer), notes

    def _transfer(self, context: MethodContext, position: int, shape: tuple[int, int]) -> tuple[Any, Any] | None:
        """This pair's transferred displacement and coverage, or None."""
        if not self.use_transfer or context.dataset is None:
            return None
        companion = _cached_companion(GOES_SOURCE_ID, GOES_LOGICAL_NAME)
        if companion is None:
            return None
        instants = _instants(context.dataset, (context.indices[position], context.indices[position + 1]))
        if instants is None or len(instants) != 2:
            return None
        scans = _goes_chain(companion, instants[0], instants[1])
        if scans is None or len(scans) < 2:
            return None
        displacement, coverage = _composed_displacement(scans)
        return _regridded_transfer(displacement, coverage, companion, context.dataset, shape)

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The baseline's derivation, plus the transferred fill where it is earned."""
        import numpy  # noqa: PLC0415

        results = super().motion(context)
        carried: list[float] = []
        reached = 0
        for position, pair in enumerate(results):
            shape = numpy.asarray(context.frames[position]).shape
            transferred = self._transfer(context, position, shape)
            if transferred is None:
                carried.append(0.0)
                continue
            transfer, covered = transferred
            flow01, weight = _transfer_corrected(pair.flow01, pair.support, transfer, covered)
            flow10, _ = _transfer_corrected(pair.flow10, pair.support, -transfer, covered)
            results[position] = PairMotion(
                flow01=flow01,
                flow10=flow10,
                confidence=pair.confidence,
                support=pair.support,
                advect_weight=_display_weight(pair.support),
                diagnostics=dict(pair.diagnostics),
            )
            carried.append(weight)
            reached += 1
        for position, pair in enumerate(results):
            pair.diagnostics["goes_transfer_weight_carried"] = carried[position]
            pair.diagnostics["goes_transfer_pairs_reached"] = float(reached)
        return results
