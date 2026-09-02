"""The `residual-generative` method: the computed residual, timed by the run's own physics.

This is the bench's only generative construction, so the order of what is
pinned here follows the order carve-out (d) states its conditions:

- it is zero at both real instants BY CONSTRUCTION, checked arbitrarily close
  to both ends where only `t(1-t) -> 0` can save it, and checked with a
  deliberately extreme envelope so a non-vanishing delivery would show;
- it is bounded - the fitted envelope is scaled down to the published cap, the
  drawn field stays on the percent scale, and the veto reaches all three
  stored fields;
- it reads only the same run's own retrieved fields, and each option's map
  from those fields to the two stored coefficients is checked on hand-built
  humidity, temperature and vertical-velocity profiles where the answer is
  arithmetic;
- it is applied only where `harness.admit` says it reconstructs the held-out
  frames better on error, structure and sharpness together, and refused
  entirely (with every number still published) where it does not;
- it is switchable: `WEATHER_GENERATED_DISPLAY=off` removes it from the
  derive;
- and it is HONEST about being generative - the test at the bottom shows the
  drawn value leaving the bracket the two retrieved frames form, which is the
  thing the non-generative sibling may never do and the reason this method
  needs the carve-out at all.
"""

from __future__ import annotations

import datetime

import numpy
import pytest

pytest.importorskip("cv2")
xarray = pytest.importorskip("xarray")

from ingest.derive.methods import (
    HELD_OUT_FRACTIONS,
    BaselineMethod,
    MethodContext,
    PairMotion,
    ResidualGenerativeMethod,
    enabled_methods,
)
from ingest.derive.methods.residual_advection import RESIDUAL_CAP_PERCENT, RESIDUAL_GAIN, ResidualAdvectionMethod
from ingest.derive.methods.residual_generative import (
    CRITICAL_RH_LIQUID_WATER_PERCENT,
    CRITICAL_RH_MIXED_PHASE_PERCENT,
    GAIN_CANDIDATES,
    REGIME_CORRELATION_FLOOR,
    SCALE_SPLIT_SIGMA_CELLS,
    SOLAR_DISSIPATION_T_STAR,
    TIMING_WIDTH,
    _capped,
    _crossing_time,
    _fit_envelope,
    _gain_fraction,
    _local_correlation,
    _omega_bow,
    _sigmoid_fraction,
    _solar_elevation_degrees,
)

SHAPE = (40, 40)
INTERVAL = 3600.0
FRACTIONS = numpy.asarray(HELD_OUT_FRACTIONS, dtype="float64").reshape(-1, 1, 1)


def blob(centre_row: float, centre_col: float, *, amplitude: float = 100.0, sigma: float = 5.0) -> numpy.ndarray:
    rows, cols = numpy.mgrid[0:SHAPE[0], 0:SHAPE[1]]
    return amplitude * numpy.exp(-((rows - centre_row) ** 2 + (cols - centre_col) ** 2) / (2 * sigma**2))


def uniform_flow(dx: float, dy: float) -> numpy.ndarray:
    flow = numpy.zeros(SHAPE + (2,))
    flow[..., 0] = dx
    flow[..., 1] = dy
    return flow


def pair_with(a: numpy.ndarray, b: numpy.ndarray | None = None, *, flow: numpy.ndarray | None = None) -> PairMotion:
    """A pair carrying a supplied STORED envelope - the two floats the shader reads."""
    flow = uniform_flow(0.0, 0.0) if flow is None else flow
    return PairMotion(
        flow01=flow,
        flow10=-flow,
        confidence=numpy.ones(SHAPE),
        support=numpy.ones(SHAPE),
        advect_weight=numpy.ones(SHAPE),
        extra={
            "res_s": numpy.zeros(SHAPE),
            "gen_a": numpy.asarray(a, dtype="float64"),
            "gen_b": numpy.zeros(SHAPE) if b is None else numpy.asarray(b, dtype="float64"),
        },
    )


def context(frames: list[numpy.ndarray], dataset=None) -> MethodContext:
    return MethodContext(
        variable="total_cloud_opacity",
        frames=frames,
        indices=tuple(range(len(frames))),
        interval_seconds=INTERVAL,
        dataset=dataset,
    )


def developing(profile) -> list[numpy.ndarray]:
    """A blob that stays put and develops on ``profile``, sampled at five instants.

    Nothing moves and no gradient changes, so advection has nothing to explain
    and the only thing a held-out score can be measuring is WHEN inside the
    interval the change is delivered - which is exactly this method's claim.
    """
    return [blob(20, 20, amplitude=40.0) + 55.0 * profile(step / 4.0) for step in range(5)]


def run_dataset(
    frames: list[numpy.ndarray],
    *,
    rh_first: float | numpy.ndarray = 90.0,
    rh_last: float | numpy.ndarray = 98.0,
    temperature_c: float = -5.0,
    omega: tuple[float, float] | None = None,
    convention: str = "liquid_water",
    hour: int = 15,
) -> xarray.Dataset:
    """A surface artifact carrying the run's own RH, T, omega and grid, as the derive sees it.

    ``total_cloud`` steers on 700 hPa (``STEERING_LEVEL_BY_VARIABLE``), so
    those are the level names the method looks up. RH is in percent and
    temperature in degC, which is what ``CANONICAL_FIELD_UNITS`` stores.
    """
    count = len(frames)
    base = datetime.datetime(2026, 6, 21, hour)
    stamps = [numpy.datetime64(base + datetime.timedelta(hours=step), "ns") for step in range(count)]
    humidity = numpy.stack([
        numpy.broadcast_to(numpy.asarray(rh_first, dtype="float64"), SHAPE)
        + (numpy.broadcast_to(numpy.asarray(rh_last, dtype="float64"), SHAPE)
           - numpy.broadcast_to(numpy.asarray(rh_first, dtype="float64"), SHAPE)) * step
        for step in range(count)
    ])
    variables = {
        "total_cloud_opacity": (("valid_time", "y", "x"), numpy.stack(frames), {"units": "percent"}),
        "relative_humidity_700hPa": (
            ("valid_time", "y", "x"), humidity,
            {"units": "percent", "rh_phase_convention": convention},
        ),
        "temperature_700hPa": (
            ("valid_time", "y", "x"), numpy.full((count,) + SHAPE, temperature_c), {"units": "degC"},
        ),
    }
    if omega is not None:
        column = numpy.stack([
            numpy.full(SHAPE, omega[0] + (omega[1] - omega[0]) * step) for step in range(count)
        ])
        variables["omega_700hPa"] = (("valid_time", "y", "x"), column, {"units": "Pa s**-1"})
    latitude = numpy.linspace(47.0, 48.0, SHAPE[0])
    longitude = numpy.linspace(-53.5, -52.0, SHAPE[1])
    return xarray.Dataset(
        variables,
        coords={"valid_time": stamps, "latitude": ("y", latitude), "longitude": ("x", longitude)},
    ).set_coords([])


def gridded(dataset: xarray.Dataset) -> xarray.Dataset:
    """The same dataset with 2-D lat/lon, which is what the grid helper reads."""
    latitude = numpy.linspace(47.0, 48.0, SHAPE[0])
    longitude = numpy.linspace(-53.5, -52.0, SHAPE[1])
    lat2d, lon2d = numpy.meshgrid(latitude, longitude, indexing="ij")
    return dataset.assign_coords(
        latitude=(("y", "x"), lat2d), longitude=(("y", "x"), lon2d)
    )


# ---------- identity ----------

def test_the_identity_the_bench_publishes():
    method = ResidualGenerativeMethod()
    assert method.id == "residual-generative"
    # The same wire as the sibling: one shader branch serves both, so the
    # client gains nothing to implement and cannot drift between them.
    assert method.shader == "residual-advection"
    assert method.extra_suffixes == ("res_s", "gen_a", "gen_b")
    assert method.vetoed_suffixes == ("res_s", "gen_a", "gen_b")
    # The declaration that turns on every disclosure and every switch.
    assert method.generative is True
    assert method.enabled is True
    assert isinstance(method, ResidualAdvectionMethod)
    # Reader copy, which carve-out (d) requires to name the generation.
    assert "GENERATED" in method.gap
    assert "GENERATED" in method.notes
    assert method.plain and method.summary


def test_the_requirements_name_the_diagnostics_that_answer_them():
    # Neither ingredient can be checked from a method-level call with no
    # variable and no dataset, so both are reported present with the
    # per-derive diagnostic named - the menu then shows what the last derive
    # actually found instead of a placeholder that reads as "missing".
    requirements = ResidualGenerativeMethod().requirements()
    assert [item.diagnostic for item in requirements] == ["rh_reached", "omega_reached"]
    assert all(item.met for item in requirements)
    assert all(item.detail for item in requirements)


def test_the_kill_switch_removes_the_method_from_the_derive(monkeypatch: pytest.MonkeyPatch):
    # The middle of carve-out (d)'s three switches. Off means the generative
    # construction is not derived at all - not derived and hidden, not derived
    # and zeroed: absent.
    assert "residual-generative" in {method.id for method in enabled_methods()}
    monkeypatch.setenv("WEATHER_GENERATED_DISPLAY", "off")
    remaining = {method.id for method in enabled_methods()}
    assert "residual-generative" not in remaining
    # And nothing else went with it: the non-generative sibling survives,
    # which is the whole reason the two are separate methods.
    assert "residual-advection" in remaining


# ---------- endpoint exactness ----------

def test_endpoint_exactness_at_both_ends():
    previous, following = blob(20, 14), blob(20, 26, amplitude=60.0)
    motion = pair_with(numpy.full(SHAPE, RESIDUAL_CAP_PERCENT), numpy.full(SHAPE, -RESIDUAL_CAP_PERCENT),
                       flow=uniform_flow(12.0, -7.0))
    method = ResidualGenerativeMethod()
    assert numpy.array_equal(method.composite(previous, following, motion, 0.0), previous)
    assert numpy.array_equal(method.composite(previous, following, motion, 1.0), following)


def test_endpoint_exactness_is_the_envelope_not_the_guards():
    # The condition carve-out (d) will not bend on: every RETRIEVED instant
    # shows its own retrieved frame untouched. Asked just inside both ends,
    # where only `t(1-t) -> 0` can save it, and with a tilted envelope at the
    # cap in both coefficients so a delivery that did not vanish would be
    # tens of percent out rather than a rounding difference.
    previous, following = blob(20, 20), blob(20, 20, amplitude=40.0)
    motion = pair_with(numpy.full(SHAPE, RESIDUAL_CAP_PERCENT), numpy.full(SHAPE, RESIDUAL_CAP_PERCENT))
    method = ResidualGenerativeMethod()
    for fraction in (1e-6, 1.0 - 1e-6):
        drawn = method.composite(previous, following, motion, fraction)
        truth = previous if fraction < 0.5 else following
        assert numpy.max(numpy.abs(drawn - truth)) < 1e-3


def test_every_target_this_module_builds_delivers_nothing_at_0_and_everything_at_1():
    # The other half of endpoint exactness, on the TARGET side: a timing that
    # did not renormalise to F*(0) = 0, F*(1) = 1 would be changing the pair's
    # NET change rather than only its timing, which two retrieved frames fix
    # and no construction may touch.
    ends = numpy.asarray([0.0, 1.0]).reshape(-1, 1, 1)
    for star in (0.1, 0.5, SOLAR_DISSIPATION_T_STAR, 0.9):
        delivered = _sigmoid_fraction(ends, numpy.full((2, 2), star), TIMING_WIDTH)
        assert delivered[0] == pytest.approx(0.0, abs=1e-12)
        assert delivered[1] == pytest.approx(1.0, abs=1e-12)
    for gain in GAIN_CANDIDATES:
        plain = _gain_fraction(ends, gain)
        assert plain[0] == pytest.approx(0.0)
        assert plain[1] == pytest.approx(1.0)


# ---------- the default construction is the sibling's, exactly ----------

def test_with_no_option_accepted_it_stores_exactly_what_the_sibling_stores():
    # The controlled comparison the greedy search rests on: its starting point
    # is not "close to" `residual-advection`, it IS it, bit for bit on the two
    # fields the shader reads. Anything the search then accepts has measurably
    # beaten the picture the non-generative method draws.
    frames = [blob(20, 20, amplitude=40.0), blob(20, 20, amplitude=40.0) + 20.0]
    generative = ResidualGenerativeMethod().motion(context(frames))[0]
    sibling = ResidualAdvectionMethod().motion(context(frames))[0]
    assert numpy.allclose(generative.extra["gen_a"], sibling.extra["gen_a"], atol=1e-9)
    assert numpy.allclose(generative.extra["gen_b"], 0.0, atol=1e-9)
    assert numpy.array_equal(generative.extra["res_s"], sibling.extra["res_s"])


def test_the_composite_evaluates_the_STORED_parabola():
    # If the composite recomputed the envelope the bench would rank a picture
    # the shader cannot draw. So a pair whose stored envelope is zero draws
    # the baseline, and a pair whose stored envelope is non-zero draws it.
    previous, following = blob(20, 20), blob(20, 20, amplitude=40.0)
    method = ResidualGenerativeMethod()
    flat = pair_with(numpy.zeros(SHAPE))
    assert numpy.array_equal(
        method.composite(previous, following, flat, 0.5),
        BaselineMethod().composite(previous, following, flat, 0.5),
    )
    tilted = pair_with(numpy.full(SHAPE, 8.0), numpy.full(SHAPE, 16.0))
    drawn = method.composite(previous, following, tilted, 0.25)
    plain = BaselineMethod().composite(previous, following, tilted, 0.25)
    # t(1-t)(a + b t) at t = 0.25 with a = 8, b = 16 is 0.1875 * 12 = 2.25.
    assert numpy.allclose(drawn - plain, 0.25 * 0.75 * (8.0 + 16.0 * 0.25))


# ---------- the fit ----------

def test_the_gain_option_maps_to_the_symmetric_envelope_by_algebra():
    # Option 1: F*(t) = t + 4 g t(1-t) lies in the span of the two basis
    # functions, so the least-squares fit must return it EXACTLY - a = 4 g s
    # and b = 0 - rather than approximately. That is what makes the gain
    # option comparable to the sibling's published bound.
    residual = numpy.full((6, 6), 30.0)
    for gain in GAIN_CANDIDATES:
        a, b = _fit_envelope(residual, numpy.broadcast_to(_gain_fraction(FRACTIONS, gain), (3, 6, 6)))
        assert a == pytest.approx(4.0 * gain * 30.0, abs=1e-9)
        assert b == pytest.approx(0.0, abs=1e-9)


def test_the_fit_is_the_least_squares_projection_of_the_target():
    # A sharp sigmoid does NOT lie in the span of the two basis functions, so
    # the honest statement is not "the fit reproduces it" but "the fit is the
    # closest two-coefficient parabola to it". Checked by perturbing the
    # answer in both coefficients and in both directions: every neighbour must
    # be worse.
    residual = numpy.full((1, 1), 20.0)
    target = _sigmoid_fraction(FRACTIONS, numpy.full((1, 1), 0.7), TIMING_WIDTH)
    a, b = _fit_envelope(residual, target)
    wanted = 20.0 * (target[:, 0, 0] - numpy.asarray(HELD_OUT_FRACTIONS))
    basis = numpy.stack([
        numpy.asarray(HELD_OUT_FRACTIONS) * (1.0 - numpy.asarray(HELD_OUT_FRACTIONS)),
        numpy.asarray(HELD_OUT_FRACTIONS) ** 2 * (1.0 - numpy.asarray(HELD_OUT_FRACTIONS)),
    ], axis=1)
    error = lambda pair: float(numpy.sum((basis @ numpy.asarray(pair) - wanted) ** 2))  # noqa: E731
    best = error((a[0, 0], b[0, 0]))
    for da, db in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (0.5, 0.5), (-0.5, -0.5)):
        assert error((a[0, 0] + da, b[0, 0] + db)) > best
    # And the projection is a real re-timing: a late target delivers less than
    # half of the change by the midpoint.
    midpoint = 0.5 + 0.25 * (a[0, 0] + 0.5 * b[0, 0]) / 20.0
    assert midpoint < 0.5


def test_the_cap_scales_both_coefficients_together_rather_than_clipping_one():
    # The fence, exercised where it actually binds: a fit whose parabola peaks
    # well past the cap. It must come down to the cap EXACTLY - not below,
    # which would be a silent extra discount - and by a SCALING, because
    # clipping `a` alone would change WHEN the envelope peaks as a side effect
    # of bounding how much it delivers.
    a = numpy.full((5, 5), 900.0)
    b = numpy.full((5, 5), -450.0)
    grid = numpy.linspace(0.0, 1.0, 401).reshape(-1, 1, 1)
    before = float(numpy.max(numpy.abs(grid * (1.0 - grid) * (a + b * grid))))
    assert before > RESIDUAL_CAP_PERCENT, "this fixture does not exercise the cap"
    capped_a, capped_b = _capped(a, b)
    after = float(numpy.max(numpy.abs(grid * (1.0 - grid) * (capped_a + capped_b * grid))))
    assert after <= RESIDUAL_CAP_PERCENT + 1e-9
    assert after == pytest.approx(RESIDUAL_CAP_PERCENT, rel=1e-3)
    # Scaled together: the ratio b/a - the envelope's shape, and so its
    # timing - is untouched.
    assert float(capped_b[0, 0] / capped_a[0, 0]) == pytest.approx(float(b[0, 0] / a[0, 0]))


def test_the_cap_holds_over_every_option_the_search_can_reach():
    # The invariant that matters on the wire: whatever combination of options
    # is accepted, the drawn envelope never exceeds the published cap. Swept
    # over the whole option set on a field whose residual saturates the
    # residual cap, so the fit starts from the largest input it can ever see.
    frames = [numpy.zeros(SHAPE), numpy.full(SHAPE, 100.0) - blob(20, 20, amplitude=90.0)]
    dataset = gridded(run_dataset(frames, omega=(0.0, -0.4)))
    grid = numpy.linspace(0.0, 1.0, 201).reshape(-1, 1, 1)
    seen = 0.0
    for options in (
        {"gain": 1.0},
        {"gain": 1.0, "rh_timing": True},
        {"gain": 1.0, "rh_timing": True, "omega_shift": True},
        {"gain": 1.0, "rh_timing": True, "solar_dissipation": True},
        {"gain": 1.0, "scale_split": True},
        {"gain": 1.0, "rh_timing": True, "scale_split": True, "regime_gate": True},
    ):
        pair = ResidualGenerativeMethod(**options).motion(context(frames, dataset))[0]
        peak = float(numpy.max(numpy.abs(
            grid * (1.0 - grid) * (pair.extra["gen_a"] + pair.extra["gen_b"] * grid)
        )))
        seen = max(seen, peak)
        assert peak <= RESIDUAL_CAP_PERCENT + 1e-9, options
    assert seen > 1.0, "the sweep never produced an envelope; it proves nothing"


def test_an_envelope_inside_the_cap_is_left_alone():
    a = numpy.full((3, 3), 4.0)
    b = numpy.full((3, 3), 2.0)
    capped_a, capped_b = _capped(a, b)
    assert numpy.array_equal(capped_a, a) and numpy.array_equal(capped_b, b)


def test_the_drawn_field_stays_inside_the_percent_scale():
    previous = numpy.full(SHAPE, 100.0)
    following = numpy.full(SHAPE, 100.0)
    method = ResidualGenerativeMethod()
    high = method.composite(previous, following, pair_with(numpy.full(SHAPE, 10 * RESIDUAL_CAP_PERCENT)), 0.5)
    low = method.composite(
        numpy.zeros(SHAPE), numpy.zeros(SHAPE), pair_with(numpy.full(SHAPE, -10 * RESIDUAL_CAP_PERCENT)), 0.5
    )
    assert high.max() <= 100.0 and high.min() >= 0.0
    assert low.max() <= 100.0 and low.min() >= 0.0


# ---------- option 2: the humidity crossing ----------

def test_the_humidity_crossing_is_the_arithmetic_it_claims_to_be():
    # RH 90 -> 98 percent crosses the liquid-water critical value 94 exactly
    # halfway through the interval; RH 80 -> 90 never reaches it at all and
    # must report an ABSENT crossing (NaN), not a clamped one at an endpoint.
    crossing = _crossing_time(numpy.array([[90.0, 80.0]]), numpy.array([[98.0, 90.0]]),
                              CRITICAL_RH_LIQUID_WATER_PERCENT)
    assert crossing[0, 0] == pytest.approx(0.5)
    assert numpy.isnan(crossing[0, 1])
    # Drying air crosses downward at the same place, and a pair already above
    # the threshold at both ends has no crossing inside the interval.
    falling = _crossing_time(numpy.array([[98.0, 96.0]]), numpy.array([[90.0, 99.0]]),
                             CRITICAL_RH_LIQUID_WATER_PERCENT)
    assert falling[0, 0] == pytest.approx(0.5)
    assert numpy.isnan(falling[0, 1])


def test_the_two_producers_do_not_share_a_critical_value():
    # ECCC RH is over liquid water at every temperature; GFS RH is
    # mixed-phase and reads up to ~24 % higher below -25 degC, so a threshold
    # calibrated on one is not valid on the other. The convention travels in
    # the variable's own attrs (`ingest.grib.declare_rh_phase`) and picks the
    # number; an undeclared field takes the lower, more conservative one.
    assert CRITICAL_RH_MIXED_PHASE_PERCENT < CRITICAL_RH_LIQUID_WATER_PERCENT
    frames = developing(lambda t: 2 * t - t * t)
    liquid = run_dataset(frames, convention="liquid_water")
    mixed = run_dataset(frames, convention="mixed_linear_253K_273K")
    method = ResidualGenerativeMethod(rh_timing=True)
    _, notes_liquid = method.configure(context(frames, liquid))
    _, notes_mixed = method.configure(context(frames, mixed))
    assert notes_liquid["critical_rh_percent"] == CRITICAL_RH_LIQUID_WATER_PERCENT
    assert notes_mixed["critical_rh_percent"] == CRITICAL_RH_MIXED_PHASE_PERCENT
    assert notes_liquid["rh_phase_convention"] == "liquid_water"


def test_the_humidity_timing_reaches_the_field_and_moves_the_envelope():
    # End to end through `motion`: a run whose 700 hPa RH crosses at t = 0.5
    # must report the crossing in its diagnostics and store an envelope that
    # is NOT the symmetric gain envelope.
    frames = [blob(20, 20, amplitude=40.0), blob(20, 20, amplitude=40.0) + 20.0]
    dataset = run_dataset(frames, rh_first=90.0, rh_last=98.0)
    timed = ResidualGenerativeMethod(rh_timing=True).motion(context(frames, dataset))[0]
    plain = ResidualGenerativeMethod().motion(context(frames, dataset))[0]
    assert timed.diagnostics["rh_reached"] == pytest.approx(1.0)
    assert not numpy.allclose(timed.extra["gen_b"], 0.0)
    assert not numpy.allclose(timed.extra["gen_a"], plain.extra["gen_a"])
    # A run whose humidity never reaches the critical value keeps option 1's
    # envelope exactly - "no crossing" is a no-op, never a zeroing.
    dry = run_dataset(frames, rh_first=80.0, rh_last=90.0)
    unchanged = ResidualGenerativeMethod(rh_timing=True).motion(context(frames, dry))[0]
    assert unchanged.diagnostics["rh_reached"] == 0.0
    assert numpy.allclose(unchanged.extra["gen_a"], plain.extra["gen_a"])
    assert numpy.allclose(unchanged.extra["gen_b"], plain.extra["gen_b"])


def test_a_late_crossing_is_drawn_later_than_an_early_one():
    # The claim the whole option exists to make: WHERE the run's own humidity
    # says cloud appeared late, less of the change is on the display at the
    # midpoint than where it appeared early.
    residual = numpy.full((4, 4), 30.0)
    early = _fit_envelope(residual, _sigmoid_fraction(FRACTIONS, numpy.full((4, 4), 0.25), TIMING_WIDTH))
    late = _fit_envelope(residual, _sigmoid_fraction(FRACTIONS, numpy.full((4, 4), 0.75), TIMING_WIDTH))
    delivered = lambda fit, t: t + t * (1.0 - t) * (fit[0] + fit[1] * t) / 30.0  # noqa: E731
    assert float(delivered(early, 0.5)[0, 0]) > float(delivered(late, 0.5)[0, 0])
    assert float(delivered(early, 0.5)[0, 0]) > 0.5 > float(delivered(late, 0.5)[0, 0])


# ---------- option 3: the omega shift ----------

def test_ascent_moves_the_crossing_earlier_and_descent_moves_it_later():
    # `d ln RH/dt = (omega/p)(1 - kappa L/(R_v T))`, and with kappa L/(R_v T)
    # about 5.7 at these levels the bracket is negative - so omega NEGATIVE
    # (ascent, since omega is dp/dt) moistens and brings the crossing forward.
    # The sign falls out of the units; this test is what stops it falling out
    # the other way.
    first, last = numpy.full((3, 3), 90.0), numpy.full((3, 3), 98.0)
    linear = _crossing_time(first, last, CRITICAL_RH_LIQUID_WATER_PERCENT)
    assert linear[0, 0] == pytest.approx(0.5)
    moistening = _crossing_time(first, last, CRITICAL_RH_LIQUID_WATER_PERCENT, numpy.full((3, 3), 8.0))
    drying = _crossing_time(first, last, CRITICAL_RH_LIQUID_WATER_PERCENT, numpy.full((3, 3), -8.0))
    assert moistening[0, 0] < 0.5 < drying[0, 0]
    # And it still crosses inside the interval, which the renormalised sigmoid
    # depends on.
    assert 0.0 < moistening[0, 0] and drying[0, 0] < 1.0


def test_the_omega_bow_reads_the_runs_own_vertical_velocity_and_clamps_it():
    frames = developing(lambda t: t)
    shape = SHAPE
    rising = run_dataset(frames, omega=(0.0, -0.5))
    bow, reached = _omega_bow(rising, "total_cloud_opacity", (0, 1), shape,
                              numpy.full(shape, 90.0), numpy.full(shape, 98.0))
    # Stronger ASCENT at the end of the interval: the tendency is negative,
    # the closure's bracket is negative, so the bow moistens.
    assert float(bow[0, 0]) > 0.0
    assert reached == pytest.approx(1.0)
    sinking = run_dataset(frames, omega=(0.0, 0.5))
    dry_bow, _ = _omega_bow(sinking, "total_cloud_opacity", (0, 1), shape,
                            numpy.full(shape, 90.0), numpy.full(shape, 98.0))
    assert float(dry_bow[0, 0]) < 0.0
    # The clamp: the implied per-hour multiplier is bounded, so one absurd
    # omega cell cannot dominate the timing. 1.2 of a 94 percent mid-interval
    # RH is the ceiling, and the bow is 2 * RH_mid * (m - 1).
    absurd = run_dataset(frames, omega=(0.0, -500.0))
    huge, _ = _omega_bow(absurd, "total_cloud_opacity", (0, 1), shape,
                         numpy.full(shape, 90.0), numpy.full(shape, 98.0))
    assert float(huge[0, 0]) == pytest.approx(2.0 * 94.0 * 0.2, rel=1e-6)


def test_absent_omega_is_a_no_op_and_says_so():
    # Carve-out (d): "a generative construction whose ingredient is absent
    # reduces to the permitted advection and says so". Absent omega is a ZERO
    # bow and `omega_reached = 0`, never a small shift invented from nothing.
    frames = developing(lambda t: t)
    without = run_dataset(frames, omega=None)
    bow, reached = _omega_bow(without, "total_cloud_opacity", (0, 1), SHAPE,
                              numpy.full(SHAPE, 90.0), numpy.full(SHAPE, 98.0))
    assert reached == 0.0
    assert numpy.array_equal(bow, numpy.zeros(SHAPE))
    # And through `motion`: the stored envelope is the humidity-timed one, not
    # a shifted one, and the diagnostic says the ingredient never arrived.
    pair_frames = [blob(20, 20, amplitude=40.0), blob(20, 20, amplitude=40.0) + 20.0]
    dataset = run_dataset(pair_frames, omega=None)
    shifted = ResidualGenerativeMethod(rh_timing=True, omega_shift=True).motion(context(pair_frames, dataset))[0]
    timed = ResidualGenerativeMethod(rh_timing=True).motion(context(pair_frames, dataset))[0]
    assert shifted.diagnostics["omega_reached"] == 0.0
    assert numpy.allclose(shifted.extra["gen_a"], timed.extra["gen_a"])


def test_the_omega_shift_moves_the_stored_envelope_the_right_way():
    frames = [blob(20, 20, amplitude=40.0), blob(20, 20, amplitude=40.0) + 20.0]
    rising = run_dataset(frames, rh_first=90.0, rh_last=98.0, omega=(0.0, -0.5))
    shifted = ResidualGenerativeMethod(rh_timing=True, omega_shift=True).motion(context(frames, rising))[0]
    timed = ResidualGenerativeMethod(rh_timing=True).motion(context(frames, rising))[0]
    assert shifted.diagnostics["omega_reached"] == pytest.approx(1.0)
    delivered = lambda pair, t: t * (1.0 - t) * (pair.extra["gen_a"] + pair.extra["gen_b"] * t)  # noqa: E731
    # Ascent brings the crossing forward, so MORE of the change is on the
    # display at the midpoint than the unshifted humidity timing draws.
    assert float(numpy.mean(delivered(shifted, 0.5))) > float(numpy.mean(delivered(timed, 0.5)))


# ---------- option 4: daytime dissipation ----------

def test_the_solar_elevation_formula_against_a_known_value():
    # The known value: at the June solstice the subsolar point is the Tropic
    # of Cancer, so solar noon there is the sun overhead - 90 degrees. Found
    # by maximising over the day rather than assuming solar noon is 12:00 UTC
    # at the prime meridian, which the equation of time says it is not.
    latitude = numpy.array([[23.44]])
    longitude = numpy.array([[0.0]])
    day = datetime.datetime(2026, 6, 21)
    elevations = [
        float(_solar_elevation_degrees(latitude, longitude, day + datetime.timedelta(minutes=step))[0, 0])
        for step in range(0, 24 * 60, 2)
    ]
    assert max(elevations) == pytest.approx(90.0, abs=0.2)
    # And the night half is genuinely negative, which is the only thing the
    # dissipation option asks of it.
    assert min(elevations) == pytest.approx(-(90.0 - 2 * 23.44), abs=0.5)
    # St John's, local midnight (03:30 UTC): the sun is down.
    assert float(_solar_elevation_degrees(
        numpy.array([[47.56]]), numpy.array([[-52.71]]), datetime.datetime(2026, 6, 21, 3, 30)
    )[0, 0]) < 0.0


def test_daytime_dissipation_reaches_only_decaying_cells_under_sun():
    # Half the field grows and half decays; the run is at local afternoon, so
    # the sun is up over the whole (small) grid. Only the decaying half may be
    # re-timed - a growing cell has nothing to burn off.
    growing = blob(20, 20, amplitude=40.0)
    mixed = growing.copy()
    mixed[:20, :] += 20.0
    mixed[20:, :] -= 20.0
    frames = [growing, mixed]
    dataset = gridded(run_dataset(frames, hour=16))
    method = ResidualGenerativeMethod(solar_dissipation=True)
    pair = method.motion(context(frames, dataset))[0]
    plain = ResidualGenerativeMethod().motion(context(frames, dataset))[0]
    assert pair.diagnostics["solar_reached"] > 0.3
    # Rows 0-19 GREW (+20) and rows 20-39 DECAYED (-20).
    grown_untouched = numpy.allclose(pair.extra["gen_a"][2:18, 2:38], plain.extra["gen_a"][2:18, 2:38])
    decayed_retimed = not numpy.allclose(pair.extra["gen_a"][22:38, 2:38], plain.extra["gen_a"][22:38, 2:38])
    assert grown_untouched, "a growing cell was re-timed by an option about burn-off"
    assert decayed_retimed, "the decaying half was not re-timed"
    # At night nothing is re-timed at all, whatever the residual says.
    night = gridded(run_dataset(frames, hour=3))
    dark = ResidualGenerativeMethod(solar_dissipation=True).motion(context(frames, night))[0]
    assert dark.diagnostics["solar_reached"] == 0.0
    assert numpy.allclose(dark.extra["gen_a"], plain.extra["gen_a"])


def test_the_dissipation_target_is_late_weighted():
    # Ghonima 2016 / Pauli 2022: the clearing accelerates once the layer is
    # thin, so most of it happens in the last third of the hour. At the
    # midpoint the target must therefore have delivered LESS than half.
    late = _sigmoid_fraction(numpy.array([[[0.5]]]), SOLAR_DISSIPATION_T_STAR, 0.12)
    assert float(late[0, 0, 0]) < 0.3


# ---------- option 5: the scale split ----------

def test_the_split_bands_sum_to_the_unsplit_envelope_under_one_option():
    # The split is a decomposition, not a discount: s = s_coarse + s_fine and
    # the fit is linear in s, so giving both bands the SAME target must return
    # exactly the unsplit envelope. That is what makes "the coarse band is
    # delivered linearly" a statement about lifetimes rather than a quiet
    # reduction in strength.
    from ingest.derive.flow_ops import _gaussian

    residual = blob(20, 14, amplitude=30.0) - blob(20, 26, amplitude=25.0)
    coarse = _gaussian(residual, SCALE_SPLIT_SIGMA_CELLS)
    fine = residual - coarse
    assert numpy.allclose(coarse + fine, residual)
    target = numpy.broadcast_to(_gain_fraction(FRACTIONS, 0.5), (3,) + SHAPE)
    whole = _fit_envelope(residual, target)
    split = [_fit_envelope(coarse, target), _fit_envelope(fine, target)]
    assert numpy.allclose(whole[0], split[0][0] + split[1][0])
    assert numpy.allclose(whole[1], split[0][1] + split[1][1])
    # And the split is not vacuous: the two bands really are different fields.
    assert float(numpy.max(numpy.abs(fine))) > 1.0


def test_the_split_delivers_the_fine_band_and_nothing_else():
    # The coarse band gets a = b = 0 - a linear delivery, because no re-timing
    # of a feature that outlives the interval is defensible - so the stored
    # envelope of a split derivation is EXACTLY the fine band's own fit, and
    # not the whole residual's.
    from ingest.derive.flow_ops import _gaussian

    frames = [blob(20, 20, amplitude=40.0), blob(20, 20, amplitude=40.0) + blob(20, 26, amplitude=25.0)]
    dataset = run_dataset(frames)
    split = ResidualGenerativeMethod(gain=1.0, scale_split=True).motion(context(frames, dataset))[0]
    whole = ResidualGenerativeMethod(gain=1.0).motion(context(frames, dataset))[0]
    residual = split.extra["res_s"]
    fine = residual - _gaussian(residual, SCALE_SPLIT_SIGMA_CELLS)
    expected, _ = _fit_envelope(fine, numpy.broadcast_to(_gain_fraction(FRACTIONS, 1.0), (3,) + SHAPE))
    assert numpy.allclose(split.extra["gen_a"], expected, atol=1e-9)
    # And it is a different picture from the unsplit one, over a substantial
    # part of the grid rather than at the rounding level.
    difference = numpy.abs(split.extra["gen_a"] - whole.extra["gen_a"])
    assert float(numpy.max(difference)) > 1.0
    assert float(numpy.max(numpy.abs(split.extra["gen_a"]))) > 0.0


# ---------- option 6: the regime gate ----------

def test_the_regime_gate_keeps_a_translating_field_and_drops_a_decorrelated_one():
    # Bley/Deneke/Senf 2016: a motion-compensated lag-1 correlation below 0.5
    # says the field decorrelated inside the interval and no smooth timing
    # describes it. A pure translation, motion-compensated, correlates at 1.
    from ingest.derive.flow_ops import _warp_linear

    generator = numpy.random.default_rng(7)
    texture = generator.uniform(0.0, 100.0, SHAPE)
    previous = numpy.asarray(_gaussian_blur(texture, 2.0))
    following = numpy.roll(previous, 5, axis=1)
    warped = _warp_linear(previous, uniform_flow(5.0, 0.0))
    assert float(numpy.mean(_local_correlation(warped, following)[6:-6, 6:-6])) > 0.9
    noise = _gaussian_blur(generator.uniform(0.0, 100.0, SHAPE), 2.0)
    assert float(numpy.mean(_local_correlation(previous, noise)[6:-6, 6:-6])) < REGIME_CORRELATION_FLOOR


def _gaussian_blur(field, sigma):
    from ingest.derive.flow_ops import _gaussian

    return _gaussian(field, sigma)


def test_the_gate_zeroes_the_envelope_where_the_field_decorrelated():
    generator = numpy.random.default_rng(3)
    previous = _gaussian_blur(generator.uniform(0.0, 100.0, SHAPE), 2.0)
    following = _gaussian_blur(generator.uniform(0.0, 100.0, SHAPE), 2.0)
    frames = [previous, following]
    dataset = run_dataset(frames)
    gated = ResidualGenerativeMethod(gain=1.0, regime_gate=True).motion(context(frames, dataset))[0]
    open_ = ResidualGenerativeMethod(gain=1.0).motion(context(frames, dataset))[0]
    assert gated.diagnostics["regime_gated_fraction"] > 0.4
    assert open_.diagnostics["regime_gated_fraction"] == 0.0
    # Where the gate fired the envelope is exactly zero - the cell falls back
    # to the permitted advection - and nowhere else was touched.
    zeroed = gated.extra["gen_a"] == 0.0
    assert zeroed.any()
    assert numpy.allclose(gated.extra["gen_a"][~zeroed], open_.extra["gen_a"][~zeroed])
    # A translating field is not gated at all: the term survives where the
    # regime is one a timing can describe.
    moving = [previous, numpy.roll(previous, 4, axis=1) + 10.0]
    kept = ResidualGenerativeMethod(gain=1.0, regime_gate=True).motion(context(moving, run_dataset(moving)))[0]
    assert kept.diagnostics["regime_gated_fraction"] < 0.2


# ---------- the veto ----------

def test_a_vetoed_method_is_silenced_in_all_three_stored_fields():
    # The envelope is ADDITIVE and survives a zero `advect_weight` untouched,
    # so the veto has to reach every stored field or a vetoed pair would draw
    # a generated term at full strength.
    from ingest.derive.cloud_motion import _derive_one_method

    generator = numpy.random.default_rng(11)
    frames = [generator.uniform(0.0, 100.0, (32, 32)) for _ in range(4)]
    variable = MethodContext(
        variable="total_cloud_opacity", frames=frames, indices=(0, 1, 2, 3), interval_seconds=INTERVAL
    )
    pairs = [(None, None, frames[index], frames[index + 1]) for index in range(3)]
    fields, _ = _derive_one_method(ResidualGenerativeMethod(gain=1.0), variable, pairs)
    assert float(numpy.max(fields["advect_weight"])) == 0.0, "the veto did not fire; this test proves nothing"
    for suffix in ("res_s", "gen_a", "gen_b"):
        assert float(numpy.max(numpy.abs(fields[suffix]))) == 0.0, f"a vetoed pair kept its {suffix}"


# ---------- the gate ----------

def test_every_published_number_is_present_whether_the_option_was_admitted_or_not():
    frames = developing(lambda t: 2 * t - t * t)
    dataset = run_dataset(frames, omega=(0.0, -0.2))
    _, notes = ResidualGenerativeMethod().configure(context(frames, dataset))
    for name in (
        "applied", "gain", "gain_applied", "rh_timing_applied", "omega_shift_applied",
        "solar_dissipation_applied", "scale_split_applied", "regime_gate_applied",
        "residual_applied", "prior_applied", "generative", "envelope",
        "residual_cap_percent", "gain_candidates", "rh_phase_convention", "critical_rh_percent",
    ):
        assert name in notes, name
    # Every candidate the greedy search offered, with the four numbers a
    # reader ranks on - including the ones that LOST, which is what makes the
    # search auditable rather than asserted.
    for gain in GAIN_CANDIDATES:
        assert f"gain={gain}" in notes["candidates"]
    for name in ("rh_timing", "omega_shift", "solar_dissipation", "scale_split", "regime_gate"):
        assert name in notes["candidates"], name
        assert name in notes["admissions"], name
        assert "admitted" in notes["admissions"][name]
    for name, scores in notes["candidates"].items():
        assert set(scores) == {
            "improvement_over_crossfade", "improvement_over_advection",
            "midpoint_ssim", "midpoint_sharpness_ratio",
        }, name
    # `applied` is the switch the menu reads to say GENERATED; the steering
    # prior's own decision keeps its own name rather than shadowing it.
    assert isinstance(notes["applied"], bool)
    assert isinstance(notes["prior_applied"], bool)


def test_an_option_is_refused_when_the_crossfade_is_already_exact():
    # Cloud that develops LINEARLY in place: a plain fade reconstructs every
    # held-out frame exactly, so no envelope of any shape or strength can beat
    # it and every option must be refused - including on a fixture where a
    # reader watching one pair would certainly see the term "do something".
    frames = developing(lambda t: t)
    dataset = run_dataset(frames, omega=(0.0, -0.2))
    method, notes = ResidualGenerativeMethod().configure(context(frames, dataset))
    assert notes["applied"] is False
    for name in (
        "gain_applied", "rh_timing_applied", "omega_shift_applied",
        "solar_dissipation_applied", "scale_split_applied", "regime_gate_applied",
    ):
        assert notes[name] is False, name
    assert notes["gain"] == RESIDUAL_GAIN
    assert notes["reduced_to"]
    # And the construction it returns really does draw the sibling's picture.
    pair = method.motion(context(frames, dataset))[0]
    sibling = ResidualAdvectionMethod(use_residual=method.use_residual).motion(context(frames, dataset))[0]
    assert numpy.allclose(pair.extra["gen_a"], sibling.extra["gen_a"], atol=1e-9)


def test_a_refused_residual_publishes_zeros_and_every_option_off():
    # If the parent refused the residual there is no delivery to time, so the
    # generative search is not run at all: every switch is off, the envelope
    # is zeros, and the method draws the baseline.
    frames = developing(lambda t: t * t)
    dataset = run_dataset(frames)
    method, notes = ResidualGenerativeMethod().configure(context(frames, dataset))
    assert notes["residual_applied"] is False
    assert notes["applied"] is False
    assert method.use_residual is False
    pair = method.motion(context(frames, dataset))[0]
    assert numpy.array_equal(pair.extra["gen_a"], numpy.zeros(SHAPE))
    assert numpy.array_equal(pair.extra["gen_b"], numpy.zeros(SHAPE))
    assert numpy.array_equal(
        method.composite(frames[0], frames[1], pair, 0.5),
        BaselineMethod().composite(frames[0], frames[1], pair, 0.5),
    )


def test_nothing_that_can_be_measured_means_nothing_is_generated():
    # Two frames cannot hold one out. An unmeasured generative term is never
    # applied - carve-out (d) makes the measurement a condition, not a bonus.
    frames = developing(lambda t: 2 * t - t * t)[:2]
    method, notes = ResidualGenerativeMethod().configure(context(frames, run_dataset(frames)))
    assert notes["applied"] is False
    assert notes["residual_applied"] is False
    assert method.use_residual is False


def test_a_stronger_gain_is_accepted_where_it_reconstructs_better():
    # Development sharply front-loaded well past what a quarter-gain envelope
    # can deliver: the generative search must reach for a gain above the
    # non-generative ceiling and say so.
    saturating = lambda t: (1.0 - numpy.exp(-12.0 * t)) / (1.0 - numpy.exp(-12.0))  # noqa: E731
    frames = developing(saturating)
    dataset = run_dataset(frames)
    method, notes = ResidualGenerativeMethod().configure(context(frames, dataset))
    assert notes["gain_applied"] is True
    assert notes["applied"] is True
    assert notes["gain"] > 0.25, notes["gain"]
    assert method.gain == notes["gain"]
    # And it beat the sibling's own construction on the fixed control, which
    # is the only reason it is allowed to draw.
    start = notes["candidates"]["accepted_start"]["improvement_over_crossfade"]
    chosen = notes["candidates"][f"gain={notes['gain']}"]["improvement_over_crossfade"]
    assert chosen > start


# ---------- what makes it GENERATIVE ----------

def test_above_the_quarter_bound_the_drawn_value_leaves_the_two_retrieved_values():
    # The whole reason this method needs carve-out (d), demonstrated rather
    # than asserted. With the residual equal to the pair's own change (which
    # is what it IS where nothing moved), the sibling's quarter-gain ceiling
    # keeps the delivered fraction inside [0, 1] at every t; a full gain does
    # not, and the display then shows a value that is in NEITHER frame.
    previous = numpy.full(SHAPE, 20.0)
    following = numpy.full(SHAPE, 80.0)
    change = following - previous
    method = ResidualGenerativeMethod()

    bounded = pair_with(4.0 * 0.25 * change)
    generated = pair_with(4.0 * 1.0 * change)
    worst_bounded, worst_generated = 0.0, 0.0
    for step in range(101):
        fraction = step / 100.0
        inside = (method.composite(previous, following, bounded, fraction) - previous) / change
        outside = (method.composite(previous, following, generated, fraction) - previous) / change
        worst_bounded = max(worst_bounded, float(inside.max()))
        worst_generated = max(worst_generated, float(outside.max()))
    assert worst_bounded <= 1.0 + 1e-12, "the quarter bound is the sibling's guarantee and must hold"
    assert worst_generated > 1.0, "at full gain nothing was generated; the method would not need the carve-out"
    # Bounded even so, on the scale that matters: the percent range.
    drawn = method.composite(previous, following, generated, 0.5)
    assert drawn.max() <= 100.0 and drawn.min() >= 0.0
