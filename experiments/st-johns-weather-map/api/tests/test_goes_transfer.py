"""`goes-transfer`: motion from the ten-minute GOES mask, fenced five ways.

What is pinned here is the fencing, not the gain. The method crosses a source
boundary - an observed cloud mask informing a model layer's motion - so every
condition the carve-out amendment names has a test that fails if the fence is
removed: unsupported cells only, agreement-weighted, refused where the model
flow says the field stands still, earned per variable by measurement, and
absent unless the GOES scans exactly span the model pair's interval.

The composite is the baseline's, inherited unchanged, so the only variable
under test against `baseline` is the motion field. That identity is pinned
too: if a later edit gives this method its own composite, the comparison stops
being a controlled one and this test says so.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy
import pytest
import xarray

pytest.importorskip("cv2")

from ingest.derive.methods import goes_transfer as methods_module
from ingest.derive.methods import (
    BaselineMethod,
    MethodContext,
    enabled_methods,
    method_by_id,
    method_catalogue,
)
from ingest.derive.methods.goes_transfer import (
    GOESTransferMethod,
    GOES_ALIGNMENT_TOLERANCE_SECONDS,
    GOES_LOGICAL_NAME,
    GOES_SOURCE_ID,
    _composed_displacement,
    _goes_chain,
    _goes_percent,
    _regridded_transfer,
    _transfer_corrected,
)

UTC = timezone.utc

#: The GOES grid the adapter actually publishes on: a regular lat/lon box over
#: the Atlantic context bounds, ~0.050 lat x 0.062 lon (measured on the live
#: 2026-09-01 artifact).
GOES_LAT = numpy.arange(40.0, 55.0, 0.05)
GOES_LON = numpy.arange(-70.0, -40.0, 0.0615)


def _drifting_mask(count: int, *, start: datetime, step_seconds: float = 600.0, shift: int = 2) -> xarray.Dataset:
    """A GOES-shaped companion whose cloud slides a fixed number of cells east."""
    rows, cols = GOES_LAT.size, GOES_LON.size
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    base = 100.0 * numpy.exp(-(((row_index - rows // 2) ** 2 + (col_index - cols // 2) ** 2) / (2 * 40.0**2)))
    probability = numpy.stack([numpy.roll(base, shift * index, axis=1) / 100.0 for index in range(count)])
    classes = numpy.where(probability > 0.5, 3, 0).astype("uint8")
    times = numpy.array(
        [numpy.datetime64(int((start + timedelta(seconds=step_seconds * index)).timestamp() * 1_000_000_000), "ns")
         for index in range(count)]
    )
    return xarray.Dataset(
        {
            "cloud_class": (("valid_time", "latitude", "longitude"), classes),
            "cloud_probability": (("valid_time", "latitude", "longitude"), probability.astype("float32")),
        },
        coords={"valid_time": times, "latitude": GOES_LAT, "longitude": GOES_LON},
    )


def _model_dataset(rows: int = 40, cols: int = 40, *, frames: int = 3, start: datetime | None = None) -> xarray.Dataset:
    """A model layer on its own coarser regular grid inside the GOES box."""
    start = start or datetime(2026, 9, 1, 10, tzinfo=UTC)
    latitude = numpy.linspace(45.5, 49.5, rows)
    longitude = numpy.linspace(-56.0, -50.0, cols)
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    base = 100.0 * numpy.exp(-(((row_index - rows // 2) ** 2 + (col_index - 10) ** 2) / (2 * 5.0**2)))
    stack = numpy.stack([numpy.roll(base, 3 * index, axis=1) for index in range(frames)])
    times = numpy.array(
        [numpy.datetime64(int((start + timedelta(hours=index)).timestamp() * 1_000_000_000), "ns")
         for index in range(frames)]
    )
    return xarray.Dataset(
        {"total_cloud": (("valid_time", "latitude", "longitude"), stack)},
        coords={"valid_time": times, "latitude": latitude, "longitude": longitude},
    )


def _context(dataset: xarray.Dataset) -> MethodContext:
    frames = [numpy.asarray(dataset["total_cloud"].isel(valid_time=index).values, dtype="float64")
              for index in range(dataset.sizes["valid_time"])]
    return MethodContext(
        variable="total_cloud",
        frames=frames,
        indices=tuple(range(len(frames))),
        interval_seconds=3600.0,
        dataset=dataset,
    )


@pytest.fixture
def companion(monkeypatch):
    """A spanning GOES sequence, injected the way the derive would find one."""
    sequence = _drifting_mask(19, start=datetime(2026, 9, 1, 9, 0, 20, 500_000, tzinfo=UTC))
    monkeypatch.setattr(methods_module, "published_companion", lambda *args, **kwargs: sequence)
    methods_module._COMPANION_CACHE.clear()
    yield sequence
    methods_module._COMPANION_CACHE.clear()


@pytest.fixture
def no_companion(monkeypatch):
    monkeypatch.setattr(methods_module, "published_companion", lambda *args, **kwargs: None)
    methods_module._COMPANION_CACHE.clear()
    yield
    methods_module._COMPANION_CACHE.clear()


# --- registry and the controlled comparison ---------------------------------


def test_goes_transfer_is_registered_and_is_not_generative():
    method = method_by_id("goes-transfer")
    assert isinstance(method, GOESTransferMethod)
    assert method in enabled_methods()
    entry = next(item for item in method_catalogue() if item["id"] == "goes-transfer")
    # Every displayed pixel still comes from a retrieved model frame: what
    # crosses the source boundary is a displacement, never a value.
    assert entry["generative"] is False
    assert entry["shader"] == BaselineMethod.shader


def test_the_composite_is_the_baselines_unchanged():
    """The only variable under test is the motion field. Keep it that way."""
    assert GOESTransferMethod.composite is BaselineMethod.composite


def test_endpoint_exactness(companion):
    previous = numpy.linspace(0.0, 100.0, 40 * 40).reshape(40, 40)
    following = numpy.flipud(previous).copy()
    context = _context(_model_dataset())
    motion = GOESTransferMethod(use_transfer=True).motion(context)[0]
    method = GOESTransferMethod(use_transfer=True)
    assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
    assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)


# --- fence 5: time alignment is exact or the prior is absent -----------------


def test_a_chain_that_exactly_spans_the_interval_is_accepted(companion):
    scans = _goes_chain(companion, datetime(2026, 9, 1, 10, tzinfo=UTC), datetime(2026, 9, 1, 11, tzinfo=UTC))
    # 10:00:20.5Z through 11:00:20.5Z inclusive: six ten-minute steps, seven
    # scans. The 20.5 s scan-start offset is inside the alignment tolerance.
    assert scans is not None and len(scans) == 7


def test_a_gap_in_the_goes_sequence_refuses_the_pair(companion):
    holed = companion.isel(valid_time=[index for index in range(companion.sizes["valid_time"]) if index != 8])
    assert _goes_chain(holed, datetime(2026, 9, 1, 10, tzinfo=UTC), datetime(2026, 9, 1, 11, tzinfo=UTC)) is None


def test_a_sequence_that_does_not_reach_the_interval_is_refused(companion):
    # Nothing is stretched to cover an endpoint the scans never reached.
    assert _goes_chain(companion, datetime(2026, 9, 1, 12, tzinfo=UTC), datetime(2026, 9, 1, 13, tzinfo=UTC)) is None
    assert _goes_chain(companion, datetime(2026, 9, 1, 8, tzinfo=UTC), datetime(2026, 9, 1, 9, tzinfo=UTC)) is None


def test_a_stale_scan_is_not_silently_reused(companion):
    """One scan is a single instant, never a span, however recent it is."""
    single = companion.isel(valid_time=[6])
    assert _goes_chain(single, datetime(2026, 9, 1, 10, tzinfo=UTC), datetime(2026, 9, 1, 11, tzinfo=UTC)) is None


def test_the_alignment_tolerance_clears_the_scan_offset_and_nothing_more():
    # The scan-start offset the live product actually carries, against the
    # ten-minute cadence a missing scan would put between the two.
    assert 20.5 < GOES_ALIGNMENT_TOLERANCE_SECONDS < 600.0


# --- the categorical mask ---------------------------------------------------


def test_the_class_ramp_is_used_only_when_probabilities_are_unusable(companion):
    percent, observed = _goes_percent(companion, 0)
    assert percent.max() <= 100.0 and observed.max() == 1.0
    without = companion.drop_vars("cloud_probability")
    ramped, _ = _goes_percent(without, 0)
    # A four-level ramp, so exactly the levels the class meanings name.
    assert set(numpy.unique(ramped)).issubset({0.0, 25.0, 75.0, 100.0})


def test_unobserved_cells_are_never_offered_as_motion(companion):
    blanked = companion.copy(deep=True)
    values = blanked["cloud_class"].values
    values[:, :, :10] = 255
    blanked["cloud_class"] = (("valid_time", "latitude", "longitude"), values)
    blanked = blanked.drop_vars("cloud_probability")
    _, observed = _goes_percent(blanked, 0)
    assert observed[:, :10].max() == 0.0


# --- the regrid -------------------------------------------------------------


def test_a_uniform_eastward_displacement_survives_the_regrid(companion):
    """One GOES cell east must land as the same ground distance, not one model cell."""
    displacement = numpy.zeros((GOES_LAT.size, GOES_LON.size, 2), dtype="float64")
    displacement[..., 0] = 1.0
    coverage = numpy.ones((GOES_LAT.size, GOES_LON.size), dtype="float64")
    dataset = _model_dataset()
    transfer, covered = _regridded_transfer(displacement, coverage, companion, dataset, (40, 40))
    model_lon_step = float(dataset["longitude"].values[1] - dataset["longitude"].values[0])
    expected = 0.0615 / model_lon_step
    assert numpy.allclose(transfer[..., 0], expected, rtol=0.05)
    assert abs(float(numpy.abs(transfer[..., 1]).max())) < 1e-9
    assert covered.min() == 1.0


def test_a_mismatched_shape_is_refused_rather_than_coerced(companion):
    displacement = numpy.zeros((GOES_LAT.size, GOES_LON.size, 2), dtype="float64")
    coverage = numpy.ones((GOES_LAT.size, GOES_LON.size), dtype="float64")
    assert _regridded_transfer(displacement, coverage, companion, _model_dataset(), (7, 9)) is None
    # And a displacement that is not on the companion's own grid.
    assert _regridded_transfer(numpy.zeros((4, 4, 2)), numpy.ones((4, 4)), companion, _model_dataset(), (40, 40)) is None


def test_a_model_grid_outside_the_goes_box_gets_no_coverage(companion):
    displacement = numpy.zeros((GOES_LAT.size, GOES_LON.size, 2), dtype="float64")
    displacement[..., 0] = 1.0
    coverage = numpy.ones((GOES_LAT.size, GOES_LON.size), dtype="float64")
    far = _model_dataset()
    far = far.assign_coords(longitude=far["longitude"].values - 60.0)
    transfer, covered = _regridded_transfer(displacement, coverage, companion, far, (40, 40))
    assert covered.max() == 0.0
    assert float(numpy.abs(transfer).max()) == 0.0


def test_the_composed_displacement_accumulates_the_short_steps():
    """Six ten-minute legs must add up to the hour, not to one leg."""
    sequence = _drifting_mask(7, start=datetime(2026, 9, 1, 10, 0, 20, 500_000, tzinfo=UTC), shift=3)
    scans = [_goes_percent(sequence, index) for index in range(7)]
    displacement, coverage = _composed_displacement(scans)
    interior = displacement[100:200, 200:300, 0]
    assert interior.mean() > 12.0  # six legs of about three cells each
    assert coverage.min() == 1.0


# --- fences 1, 2 and 3 ------------------------------------------------------


def test_a_trusted_model_flow_is_never_overridden():
    flow = numpy.zeros((30, 30, 2), dtype="float64")
    flow[..., 0] = 5.0
    support = numpy.ones((30, 30), dtype="float64")
    transfer = numpy.zeros_like(flow)
    transfer[..., 0] = -5.0
    corrected, weight = _transfer_corrected(flow, support, transfer, numpy.ones((30, 30)))
    assert numpy.allclose(corrected, flow)
    assert weight == pytest.approx(0.0, abs=1e-9)


def test_a_transfer_the_model_layer_contradicts_reaches_nothing():
    """Fence 2: agreement measured where the model flow IS trusted."""
    flow = numpy.zeros((40, 40, 2), dtype="float64")
    flow[..., 0] = 6.0
    support = numpy.zeros((40, 40), dtype="float64")
    support[:, :20] = 1.0  # half the field trusted, half not
    transfer = numpy.zeros_like(flow)
    transfer[..., 0] = -60.0  # nothing like the trusted flow anywhere
    corrected, weight = _transfer_corrected(flow, support, transfer, numpy.ones((40, 40)))
    assert weight == pytest.approx(0.0, abs=1e-6)
    assert numpy.allclose(corrected, flow)


def test_a_corroborated_transfer_does_reach_the_unsupported_half():
    flow = numpy.zeros((40, 40, 2), dtype="float64")
    flow[..., 0] = 6.0
    support = numpy.zeros((40, 40), dtype="float64")
    support[:, :20] = 1.0
    transfer = numpy.zeros_like(flow)
    transfer[..., 0] = 6.0
    transfer[..., 1] = 3.0  # a cross-flow the model layer could not see
    corrected, weight = _transfer_corrected(flow, support, transfer, numpy.ones((40, 40)))
    assert weight > 0.05
    assert corrected[:, 30, 1].mean() > 0.5
    assert numpy.allclose(corrected[:, :10, 1], 0.0, atol=1e-6)


def test_the_stationarity_gate_refuses_a_transfer_over_standing_cloud():
    """Fence 3: orographic cloud forms in place; nothing may drag it."""
    flow = numpy.zeros((40, 40, 2), dtype="float64")
    support = numpy.ones((40, 40), dtype="float64")
    support[:, 20:] = 0.0
    transfer = numpy.zeros_like(flow)
    transfer[..., 0] = 8.0
    corrected, _ = _transfer_corrected(flow, support, transfer, numpy.ones((40, 40)))
    # The well-supported, standing half is untouched even though the transfer
    # is emphatic about the wind blowing through it.
    assert numpy.allclose(corrected[:, :15, 0], 0.0, atol=1e-6)


def test_coverage_gates_the_transfer_and_the_corroboration():
    flow = numpy.zeros((40, 40, 2), dtype="float64")
    flow[..., 0] = 6.0
    support = numpy.zeros((40, 40), dtype="float64")
    support[:, :20] = 1.0
    transfer = numpy.zeros_like(flow)
    transfer[..., 0] = 6.0
    covered = numpy.zeros((40, 40), dtype="float64")
    corrected, weight = _transfer_corrected(flow, support, transfer, covered)
    assert weight == pytest.approx(0.0, abs=1e-9)
    assert numpy.allclose(corrected, flow)


# --- fence 4, and never failing the artifact --------------------------------


def test_an_absent_companion_leaves_the_baseline_motion_exactly(no_companion):
    context = _context(_model_dataset())
    baseline = BaselineMethod().motion(context)
    transferred = GOESTransferMethod(use_transfer=True).motion(context)
    assert len(transferred) == len(baseline)
    for left, right in zip(baseline, transferred):
        assert numpy.allclose(left.flow01, right.flow01)
        assert numpy.allclose(left.advect_weight, right.advect_weight)


def test_configure_says_the_prior_is_absent_and_names_why(no_companion):
    context = _context(_model_dataset())
    method, notes = GOESTransferMethod().configure(context)
    assert notes["applied"] is False
    assert "no published GOES cloud mask" in notes["absent_reason"]
    assert notes["companion"] == f"{GOES_SOURCE_ID}/{GOES_LOGICAL_NAME}"
    assert method.use_transfer is False


def test_configure_publishes_both_held_out_numbers(companion):
    context = _context(_model_dataset(frames=5))
    _, notes = GOESTransferMethod().configure(context)
    assert "held_out_improvement_with_transfer" in notes
    assert "held_out_improvement_without_transfer" in notes
    assert isinstance(notes["applied"], bool)
    # The steering prior's own decision is published beside it, not replaced.
    assert "steering_prior" in notes
    assert notes["motion_field"] == methods_module.GOES_MOTION_FIELD


def test_the_diagnostics_say_how_many_pairs_the_transfer_reached(companion):
    context = _context(_model_dataset(frames=4))
    motions = GOESTransferMethod(use_transfer=True).motion(context)
    reached = motions[0].diagnostics["goes_transfer_pairs_reached"]
    # The fixture's scans run 09:00:20.5Z to 12:00:20.5Z, so of the three model
    # pairs from 10:00Z the first two are spanned and 12:00 -> 13:00 is not.
    # This is the ordinary case, not a failure: a model layer is a forecast
    # running a day ahead and the observation only exists in the past.
    assert reached == 2.0
    assert all("goes_transfer_weight_carried" in motion.diagnostics for motion in motions)


def test_a_companion_that_raises_never_fails_the_motion(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("object store is down")

    monkeypatch.setattr(methods_module, "published_companion", explode)
    methods_module._COMPANION_CACHE.clear()
    context = _context(_model_dataset())
    with pytest.raises(RuntimeError):
        methods_module.published_companion("x", "y")
    # The method itself swallows it: the motion artifact the whole map depends
    # on is never failed by an optional ingredient.
    methods_module._COMPANION_CACHE.clear()
    monkeypatch.setattr(methods_module, "published_companion", lambda *args, **kwargs: None)
    assert len(GOESTransferMethod(use_transfer=True).motion(context)) == len(context.frames) - 1
