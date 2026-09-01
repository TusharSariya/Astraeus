"""The `height-steering` method: one steering level per CELL, not per variable.

What is pinned here, in the order the claim has to be defended:

- the composite is the baseline's, bit for bit, so the ONLY variable under
  test is the motion field and the comparison is controlled;
- endpoint exactness, whatever the prior claims;
- the regridding rule from the GOES observation grid to the model grid, at
  its edges, where silence is the correct answer;
- the per-cell level assignment itself, on a column whose answer is known;
- and every fence, especially the fifth: with no observed height the method
  is EXACTLY the shipped single-level prior, so the two can only differ where
  a real cloud top says they should.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy
import pytest
import xarray

pytest.importorskip("cv2")

from ingest.derive.flow_ops import STEERING_LEVEL_BY_VARIABLE, _steering_prior
from ingest.derive.methods import (
    BaselineMethod,
    MethodContext,
    PairMotion,
    method_by_id,
)
from ingest.derive.methods.height_steering import (
    HEIGHT_OBSERVATION_WINDOW_SECONDS,
    HeightSteeringMethod,
    ISA_LEVEL_HEIGHT_M,
    _height_steering_prior,
    _nearest_on_regular_axes,
    _observed_cloud_top_height,
)

UTC = timezone.utc
START = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
INTERVAL = 3600.0
SHAPE = (24, 24)

# The model grid: a small regular box over the Avalon, published as 2-D
# latitude/longitude the way HRDPS and RDPS do, so the coordinate handling is
# exercised on the harder of the two layouts rather than the easier one.
MODEL_LAT = numpy.linspace(46.5, 48.5, SHAPE[0])
MODEL_LON = numpy.linspace(-54.0, -51.5, SHAPE[1])


def blob_field(centre_col: float, *, sigma: float = 4.0) -> numpy.ndarray:
    rows, cols = SHAPE
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    distance2 = (row_index - rows / 2) ** 2 + (col_index - centre_col) ** 2
    return 100.0 * numpy.exp(-distance2 / (2 * sigma**2))


def model_dataset(*, frames: int = 3, winds: dict[int, tuple[float, float]] | None = None) -> xarray.Dataset:
    """A surface artifact carrying cloud frames and the three steering levels."""
    winds = winds or {850: (10.0, 0.0), 700: (0.0, 10.0), 500: (-10.0, 0.0)}
    lat2d, lon2d = numpy.meshgrid(MODEL_LAT, MODEL_LON, indexing="ij")
    times = numpy.array(
        [numpy.datetime64((START + timedelta(seconds=INTERVAL * step)).replace(tzinfo=None), "ns")
         for step in range(frames)]
    )
    data = {
        "total_cloud": (("valid_time", "y", "x"),
                        numpy.stack([blob_field(6 + 3 * step) for step in range(frames)])),
    }
    for level, (u, v) in winds.items():
        data[f"wind_u_{level}hPa"] = (("valid_time", "y", "x"), numpy.full((frames,) + SHAPE, u))
        data[f"wind_v_{level}hPa"] = (("valid_time", "y", "x"), numpy.full((frames,) + SHAPE, v))
    return xarray.Dataset(
        data,
        coords={
            "valid_time": times,
            "latitude": (("y", "x"), lat2d),
            "longitude": (("y", "x"), lon2d),
        },
    )


def height_companion(height_m, *, scan: datetime = START, cells: int = 48) -> xarray.Dataset:
    """A GOES cloud-mask artifact carrying observed cloud-top height.

    Deliberately on its OWN regular axes, twice as fine as the model grid and
    slightly wider, so the regrid is doing real work rather than lining up.
    """
    lat = numpy.linspace(46.4, 48.6, cells)
    lon = numpy.linspace(-54.1, -51.4, cells)
    values = numpy.full((cells, cells), numpy.nan, dtype="float32")
    values[...] = height_m
    return xarray.Dataset(
        {"cloud_top_height": (("valid_time", "latitude", "longitude"), values[None, ...])},
        coords={
            "valid_time": numpy.array([numpy.datetime64(scan.replace(tzinfo=None), "ns")]),
            "latitude": lat,
            "longitude": lon,
        },
    )


def context(dataset: xarray.Dataset, *, frames: int = 3) -> MethodContext:
    stack = dataset["total_cloud"].values
    return MethodContext(
        variable="total_cloud",
        frames=[stack[index] for index in range(frames)],
        indices=tuple(range(frames)),
        interval_seconds=INTERVAL,
        dataset=dataset,
    )


def uniform_pair(dx: float, dy: float) -> PairMotion:
    flow = numpy.zeros(SHAPE + (2,))
    flow[..., 0] = dx
    flow[..., 1] = dy
    return PairMotion(
        flow01=flow,
        flow10=-flow,
        confidence=numpy.ones(SHAPE),
        support=numpy.ones(SHAPE),
        advect_weight=numpy.ones(SHAPE),
    )


# ---------- registry and composite ----------

def test_height_steering_is_registered_on_the_baseline_shader():
    method = method_by_id("height-steering")
    assert method is not None
    assert method.enabled and not method.generative
    # The client construction is unchanged. That is the point: the composite is
    # inherited untouched, so the only thing this method changes is the motion
    # field, and the comparison against the baseline is a controlled one.
    assert method.shader == BaselineMethod.shader


def test_the_composite_is_the_baseline_s_bit_for_bit():
    previous, following = blob_field(6), blob_field(12)
    motion = uniform_pair(6.0, 0.0)
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert numpy.array_equal(
            HeightSteeringMethod().composite(previous, following, motion, fraction),
            BaselineMethod().composite(previous, following, motion, fraction),
        )


def test_height_steering_is_endpoint_exact():
    # Non-negotiable for every method on the bench, and it must hold whatever
    # the prior claimed: at a real instant the real frame shows untouched.
    previous, following = blob_field(6), blob_field(18)
    motion = uniform_pair(14.0, -9.0)
    method = HeightSteeringMethod(use_prior=True)
    assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
    assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)


# ---------- the regridding rule ----------

def test_the_regrid_takes_the_cell_a_destination_centre_falls_inside():
    source_lat = numpy.array([0.0, 1.0, 2.0])
    source_lon = numpy.array([10.0, 11.0, 12.0])
    values = numpy.arange(9.0).reshape(3, 3)
    lat2d = numpy.array([[0.1, 2.0]])
    lon2d = numpy.array([[10.4, 12.0]])
    sampled = _nearest_on_regular_axes(values, source_lat, source_lon, lat2d, lon2d)
    assert sampled[0, 0] == 0.0  # nearest (0, 10)
    assert sampled[0, 1] == 8.0  # nearest (2, 12)


def test_a_destination_outside_the_observation_grid_takes_nothing():
    # Silence, not the edge value. Extending the last observed cell outward
    # would be publishing an observation where none was made - and the whole
    # method then falls back to the single level, which is the honest answer.
    source_lat = numpy.array([0.0, 1.0, 2.0])
    source_lon = numpy.array([10.0, 11.0, 12.0])
    values = numpy.ones((3, 3))
    lat2d = numpy.array([[-4.0, 1.0]])
    lon2d = numpy.array([[11.0, 40.0]])
    sampled = _nearest_on_regular_axes(values, source_lat, source_lon, lat2d, lon2d)
    assert numpy.isnan(sampled).all()


def test_a_grid_that_does_not_match_the_field_is_refused_not_broadcast():
    # Never silently accept a mismatched shape. The model grid's coordinates
    # are asked to describe a field of a different shape; the answer is None,
    # and the method then falls back to the single level.
    dataset = model_dataset()
    companion = height_companion(4000.0)
    assert _observed_cloud_top_height(dataset, (0, 1), (SHAPE[0] + 1, SHAPE[1]), companion) is None
    # And a companion whose own latitude/longitude are 2-D is refused too:
    # the regrid's index arithmetic is only valid on regular axes, so a
    # curvilinear observation grid is an absence rather than an assumption.
    lat2d, lon2d = numpy.meshgrid(companion["latitude"].values, companion["longitude"].values, indexing="ij")
    curvilinear = companion.drop_vars(["latitude", "longitude"]).rename(
        {"latitude": "j", "longitude": "i"}
    ).assign_coords(latitude=(("j", "i"), lat2d), longitude=(("j", "i"), lon2d))
    assert _observed_cloud_top_height(dataset, (0, 1), SHAPE, curvilinear) is None


def test_an_observation_too_far_from_the_pair_describes_nothing():
    # An observed cloud top is valid at one instant, and the layers being
    # interpolated run to +24 h. A scan six hours from this pair is not a
    # description of this pair's cloud, so it is refused and the cell falls
    # back to the single level.
    dataset = model_dataset()
    far = height_companion(4000.0, scan=START + timedelta(seconds=6 * HEIGHT_OBSERVATION_WINDOW_SECONDS))
    assert _observed_cloud_top_height(dataset, (0, 1), SHAPE, far) is None
    near = height_companion(4000.0, scan=START + timedelta(seconds=0.5 * HEIGHT_OBSERVATION_WINDOW_SECONDS))
    observed = _observed_cloud_top_height(dataset, (0, 1), SHAPE, near)
    assert observed is not None and numpy.isfinite(observed).all()


def test_an_absent_companion_is_an_absence_not_a_failure():
    assert _observed_cloud_top_height(model_dataset(), (0, 1), SHAPE, None) is None


# ---------- the level assignment ----------

def test_the_standard_atmosphere_heights_match_the_barometric_formula():
    # These three numbers decide which wind every cell gets, so they are
    # checked against the formula rather than trusted as constants.
    for level, height in ISA_LEVEL_HEIGHT_M.items():
        expected = (1.0 - (level / 1013.25) ** (1.0 / 5.25588)) / 2.25577e-5
        assert height == pytest.approx(expected, abs=1.0)
    assert ISA_LEVEL_HEIGHT_M[850] < ISA_LEVEL_HEIGHT_M[700] < ISA_LEVEL_HEIGHT_M[500]


def test_each_cell_takes_the_wind_at_its_own_observed_cloud_top():
    # Three winds pointing three different ways, so the level a cell was
    # assigned is legible from the direction alone. Low tops must move east
    # with the 850 wind, high tops west with the 500 wind.
    dataset = model_dataset(winds={850: (10.0, 0.0), 700: (0.0, 10.0), 500: (-10.0, 0.0)})
    height = numpy.full(SHAPE, ISA_LEVEL_HEIGHT_M[850])
    height[:, 12:] = ISA_LEVEL_HEIGHT_M[500]
    prior, observed = _height_steering_prior(dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, height)
    assert observed == pytest.approx(1.0)
    assert (prior[:, :12, 0] > 0).all()   # low cloud, 850 wind, eastward
    assert (prior[:, 12:, 0] < 0).all()   # high cloud, 500 wind, westward
    assert numpy.allclose(prior[..., 1], 0.0, atol=1e-9)  # neither level has a v


def test_a_top_between_two_levels_is_interpolated_between_their_winds():
    dataset = model_dataset(winds={850: (10.0, 0.0), 700: (0.0, 10.0), 500: (-10.0, 0.0)})
    midway = 0.5 * (ISA_LEVEL_HEIGHT_M[850] + ISA_LEVEL_HEIGHT_M[700])
    prior, _ = _height_steering_prior(
        dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, numpy.full(SHAPE, midway)
    )
    at_850, _ = _height_steering_prior(
        dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, numpy.full(SHAPE, ISA_LEVEL_HEIGHT_M[850])
    )
    at_700, _ = _height_steering_prior(
        dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, numpy.full(SHAPE, ISA_LEVEL_HEIGHT_M[700])
    )
    assert numpy.allclose(prior, 0.5 * (at_850 + at_700), atol=1e-9)


def test_a_top_outside_the_levels_is_clamped_and_never_extrapolated():
    # A 14 km cloud top is above every published level. The honest answer is
    # the highest wind that WAS published; extrapolating the shear beyond
    # 500 hPa would be inventing a wind at a level nothing was measured at.
    dataset = model_dataset(winds={850: (10.0, 0.0), 700: (0.0, 10.0), 500: (-10.0, 0.0)})
    aloft, _ = _height_steering_prior(dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, numpy.full(SHAPE, 14000.0))
    at_500, _ = _height_steering_prior(
        dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, numpy.full(SHAPE, ISA_LEVEL_HEIGHT_M[500])
    )
    assert numpy.allclose(aloft, at_500, atol=1e-12)
    ground, _ = _height_steering_prior(dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, numpy.full(SHAPE, 50.0))
    at_850, _ = _height_steering_prior(
        dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, numpy.full(SHAPE, ISA_LEVEL_HEIGHT_M[850])
    )
    assert numpy.allclose(ground, at_850, atol=1e-12)


# ---------- fence five ----------

def test_with_no_observed_height_the_prior_is_exactly_the_shipped_one():
    # THE fence this method adds. Where nothing was observed, this is not an
    # approximation of the single-level prior - it is the same numbers, so the
    # two methods can only ever differ where a real cloud top says they should.
    dataset = model_dataset(winds={850: (10.0, 3.0), 700: (4.0, -6.0), 500: (-8.0, 1.0)})
    assigned, observed = _height_steering_prior(dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, None)
    shipped = _steering_prior(dataset, "total_cloud", (0, 1), INTERVAL, SHAPE)
    assert observed == pytest.approx(0.0)
    assert shipped is not None
    assert numpy.allclose(assigned, shipped, atol=1e-12)
    # And the same holds cell by cell where only PART of the field was observed.
    partial = numpy.full(SHAPE, numpy.nan)
    partial[:, :8] = ISA_LEVEL_HEIGHT_M[500]
    mixed, fraction = _height_steering_prior(dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, partial)
    assert fraction == pytest.approx(8.0 / SHAPE[1])
    assert numpy.allclose(mixed[:, 8:], shipped[:, 8:], atol=1e-12)
    assert not numpy.allclose(mixed[:, :8], shipped[:, :8], atol=1e-6)


def test_the_fallback_level_is_the_variable_s_own():
    # cloud_low steers at 850 and cloud_high at 500; an unobserved cell of
    # each must land on its own level, not on a shared default.
    dataset = model_dataset(winds={850: (10.0, 0.0), 700: (0.0, 10.0), 500: (-10.0, 0.0)})
    for variable in ("cloud_low", "cloud_high"):
        assigned, _ = _height_steering_prior(dataset, variable, (0, 1), INTERVAL, SHAPE, None)
        shipped = _steering_prior(dataset, variable, (0, 1), INTERVAL, SHAPE)
        assert numpy.allclose(assigned, shipped, atol=1e-12), variable
    assert STEERING_LEVEL_BY_VARIABLE["cloud_low"] == 850


def test_a_missing_level_degrades_to_the_single_level_prior():
    # Only 700 published: no per-cell assignment is possible, so the method
    # returns None here and its `motion` falls back to the shipped prior
    # rather than failing the motion artifact the whole map depends on.
    dataset = model_dataset(winds={700: (5.0, 0.0)})
    assert _height_steering_prior(dataset, "total_cloud", (0, 1), INTERVAL, SHAPE, numpy.full(SHAPE, 3000.0)) is None
    motions = HeightSteeringMethod(use_prior=True).motion(context(dataset))
    assert len(motions) == 2
    assert all(numpy.isfinite(motion.flow01).all() for motion in motions)


# ---------- the four inherited fences ----------

def test_the_inherited_fences_still_hold_on_the_per_cell_prior(monkeypatch):
    # Fences one to three are not re-implemented by this method: it hands its
    # per-cell wind to the same `_prior_corrected` the shipped prior uses. What
    # is pinned here is that it really does - a fully trusted image flow comes
    # back untouched however hard the per-cell wind blows.
    from ingest.derive.methods import height_steering as methods

    dataset = model_dataset()
    monkeypatch.setattr(methods, "published_companion", lambda *a, **k: height_companion(5000.0))
    with_prior = HeightSteeringMethod(use_prior=True).motion(context(dataset))
    without = HeightSteeringMethod(use_prior=False).motion(context(dataset))
    for used, unused in zip(with_prior, without):
        trusted = used.support > 0.99
        assert numpy.allclose(used.flow01[trusted], unused.flow01[trusted], atol=1e-9)


def test_configure_publishes_both_numbers_and_names_the_assignment(monkeypatch):
    # Fence four, inherited: the prior is applied only if it improves the
    # held-out reconstruction, and both scores are published either way.
    from ingest.derive.methods import height_steering as methods

    dataset = model_dataset(frames=5)
    monkeypatch.setattr(methods, "published_companion", lambda *a, **k: height_companion(5000.0))
    method, notes = HeightSteeringMethod().configure(context(dataset, frames=5))
    assert isinstance(method, HeightSteeringMethod)
    assert isinstance(notes["applied"], bool)
    assert notes["held_out_improvement_with_prior"] is not None
    assert notes["held_out_improvement_without_prior"] is not None
    # A single `level_hpa` would be a false claim about a per-cell assignment.
    assert "per cell" in notes["level_assignment"]
    assert notes["fallback_level_hpa"] == STEERING_LEVEL_BY_VARIABLE["total_cloud"]


def test_the_observed_fraction_is_reported_so_the_claim_is_checkable(monkeypatch):
    from ingest.derive.methods import height_steering as methods

    dataset = model_dataset()
    monkeypatch.setattr(methods, "published_companion", lambda *a, **k: height_companion(5000.0))
    motions = HeightSteeringMethod(use_prior=True).motion(context(dataset))
    assert motions[0].diagnostics["observed_height_fraction"] == pytest.approx(1.0)
    # And with nothing observed it is zero rather than absent, which is what
    # tells a provenance reader the observation never reached this cycle.
    monkeypatch.setattr(methods, "published_companion", lambda *a, **k: None)
    silent = HeightSteeringMethod(use_prior=True).motion(context(dataset))
    assert silent[0].diagnostics["observed_height_fraction"] == 0.0


def test_a_broken_companion_never_fails_the_motion_artifact(monkeypatch):
    from ingest.derive.methods import height_steering as methods

    class Exploding:
        @property
        def data_vars(self):
            raise RuntimeError("object store on fire")

    dataset = model_dataset()
    monkeypatch.setattr(methods, "published_companion", lambda *a, **k: Exploding())
    motions = HeightSteeringMethod(use_prior=True).motion(context(dataset))
    assert len(motions) == 2
    assert all(numpy.isfinite(motion.flow01).all() for motion in motions)
