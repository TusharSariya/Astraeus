"""Unit tests for ``ingest.manifest.validate_run`` and its supporting types.

Every adapter used to hard-code ``complete=True, qc_passed=True``. This module
is what replaced that: an adapter declares a :class:`RunManifest` and hands
the assembled dataset (plus its own decode failures) to :func:`validate_run`,
which is the single place any of the nine ways a run can fail to be
publishable is judged. Each test below isolates exactly one of those ways so
a regression that reopens any of them is caught here, not downstream.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import numpy
import pytest
import xarray

from ingest.contract import FetchWindow
from ingest.manifest import ManifestError, RequiredField, RunManifest, ValidationResult, validate_run

UTC = timezone.utc

T0 = datetime(2026, 8, 29, 12, tzinfo=UTC)
T1 = datetime(2026, 8, 29, 13, tzinfo=UTC)

LATITUDES = numpy.array([45.0, 46.0])
LONGITUDES = numpy.array([-53.0, -52.0])


def _stamp(moment: datetime) -> numpy.datetime64:
    return numpy.datetime64(moment.astimezone(UTC).replace(tzinfo=None), "ns")


def make_dataset(
    *,
    times: tuple[datetime, ...] = (T0,),
    latitudes: numpy.ndarray = LATITUDES,
    longitudes: numpy.ndarray = LONGITUDES,
    temperature: numpy.ndarray | None = None,
    temperature_units: str = "degC",
    include_temperature: bool = True,
) -> xarray.Dataset:
    shape = (len(times), len(latitudes), len(longitudes))
    if temperature is None:
        temperature = numpy.full(shape, 10.0)
    data_vars = {}
    if include_temperature:
        data_vars["temperature_2m"] = (("valid_time", "latitude", "longitude"), temperature, {"units": temperature_units})
    return xarray.Dataset(
        data_vars,
        coords={
            "valid_time": [_stamp(moment) for moment in times],
            "latitude": latitudes,
            "longitude": longitudes,
        },
    )


def make_manifest(**kwargs) -> RunManifest:
    defaults: dict = dict(
        source_id="test-source",
        fields=(RequiredField("temperature_2m", "degC", level="2 m"),),
    )
    defaults.update(kwargs)
    return RunManifest(**defaults)


def window() -> FetchWindow:
    return FetchWindow(now=T0, back_hours=3, forward_hours=24)


# --- the happy path -------------------------------------------------------


def test_happy_path_is_publishable():
    manifest = make_manifest(required_valid_times=(T0,))
    result = validate_run(manifest, make_dataset(), window=window())

    assert result.complete is True
    assert result.qc_passed is True
    assert result.publishable is True
    assert result.coverage_fraction == 1.0
    assert result.flags == ()
    assert result.as_quality()["status"] == "passed"
    assert result.as_coverage()["status"] == "complete"


# --- the failure matrix, one condition per test ---------------------------


def test_missing_nonoptional_field():
    manifest = make_manifest()
    dataset = make_dataset(include_temperature=False)

    result = validate_run(manifest, dataset, window=window())

    assert result.complete is False
    assert any(flag.startswith("missing_field:temperature_2m") for flag in result.flags)
    assert result.publishable is False


def test_all_nan_field():
    manifest = make_manifest()
    dataset = make_dataset(temperature=numpy.full((1, 2, 2), numpy.nan))

    result = validate_run(manifest, dataset, window=window())

    assert result.complete is False
    assert any(flag.startswith("empty_field:temperature_2m") for flag in result.flags)
    assert result.coverage_fraction == 0.0


def test_wrong_normalized_units_fails_qc_specifically():
    manifest = make_manifest()
    dataset = make_dataset(temperature_units="K")

    result = validate_run(manifest, dataset, window=window())

    assert result.qc_passed is False
    assert result.complete is False
    assert any(flag.startswith("bad_units:temperature_2m:K") for flag in result.flags)
    # Units are a QC failure specifically, not merely an incompleteness.
    assert result.as_quality()["status"] == "failed"


def test_decode_error_entry_fails_the_run():
    manifest = make_manifest()
    dataset = make_dataset()

    result = validate_run(manifest, dataset, window=window(), decode_errors=["absent:wind_u_10m@000"])

    assert result.complete is False
    assert "decode_error:absent:wind_u_10m@000" in result.flags


def test_missing_required_valid_time():
    manifest = make_manifest(required_valid_times=(T0, T1))
    dataset = make_dataset(times=(T0,))  # T1 never arrived

    result = validate_run(manifest, dataset, window=window())

    assert result.complete is False
    assert any(flag.startswith("missing_valid_time:2026-08-29T13:00:00Z") for flag in result.flags)


@pytest.mark.parametrize("axis", ["latitude", "longitude"])
def test_zero_size_axis_from_an_empty_bbox_crop(axis: str):
    manifest = make_manifest()
    kwargs = {"latitudes": numpy.array([])} if axis == "latitude" else {"longitudes": numpy.array([])}
    dataset = make_dataset(temperature=numpy.zeros((1, 0, 2)) if axis == "latitude" else numpy.zeros((1, 2, 0)), **kwargs)

    result = validate_run(manifest, dataset, window=window())

    assert result.complete is False
    assert any(flag.startswith(f"empty_grid:{axis}") for flag in result.flags)


def test_coverage_below_min_coverage_fraction():
    manifest = make_manifest(min_coverage_fraction=0.9)
    # Half the cells are NaN: coverage 0.5 < the declared 0.9 minimum.
    temperature = numpy.array([[[10.0, numpy.nan], [10.0, numpy.nan]]])
    dataset = make_dataset(temperature=temperature)

    result = validate_run(manifest, dataset, window=window())

    assert result.complete is False
    assert result.coverage_fraction == pytest.approx(0.5)
    assert any(flag.startswith("coverage_below_threshold:0.5000<0.9000") for flag in result.flags)


# --- the one-way property ---------------------------------------------------


def test_validation_result_is_frozen():
    result = ValidationResult(complete=True, qc_passed=True, coverage_fraction=1.0, flags=(), detail="")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.complete = False  # type: ignore[misc]


def test_failing_can_only_lower_a_verdict_never_raise_one():
    result = ValidationResult(complete=True, qc_passed=True, coverage_fraction=1.0, flags=(), detail="ok")
    assert result.publishable is True

    lowered = result.failing("some_flag", "something went wrong")
    assert lowered.complete is False
    assert lowered.qc_passed is True  # qc is untouched unless qc=True is passed
    assert lowered.publishable is False

    # There is no way back up: failing() again cannot restore completeness,
    # and the dataclass exposes no other mutator.
    still_lowered = lowered.failing("another_flag", "still wrong")
    assert still_lowered.complete is False
    assert still_lowered.publishable is False
    assert {"some_flag", "another_flag"} <= set(still_lowered.flags)

    # The only mutator is `failing`; there is no inverse.
    public_methods = {name for name in vars(ValidationResult) if not name.startswith("_")}
    assert "failing" in public_methods
    assert not any(name in public_methods for name in ("passing", "succeed", "complete_run", "reset"))


def test_failing_with_qc_true_also_fails_qc_and_it_stays_failed():
    result = ValidationResult(complete=True, qc_passed=True, coverage_fraction=1.0, flags=(), detail="")
    lowered = result.failing("bad_units:x:K", "unit mismatch", qc=True)
    assert lowered.qc_passed is False

    # A later failing() call without qc=True must not resurrect qc_passed.
    again = lowered.failing("unrelated", "unrelated failure")
    assert again.qc_passed is False


# --- manifest construction guards ------------------------------------------


def test_manifest_requires_at_least_one_field():
    with pytest.raises(ManifestError):
        RunManifest(source_id="x", fields=())


def test_manifest_rejects_duplicate_fields():
    with pytest.raises(ManifestError):
        RunManifest(
            source_id="x",
            fields=(RequiredField("temperature_2m", "degC"), RequiredField("temperature_2m", "degC")),
        )


def test_manifest_rejects_out_of_range_coverage_fraction():
    with pytest.raises(ManifestError):
        RunManifest(source_id="x", fields=(RequiredField("temperature_2m", "degC"),), min_coverage_fraction=0.0)


def test_manifest_rejects_naive_required_valid_times():
    with pytest.raises(ManifestError):
        RunManifest(
            source_id="x",
            fields=(RequiredField("temperature_2m", "degC"),),
            required_valid_times=(datetime(2026, 8, 29, 12),),  # no tzinfo
        )


# --- the evidence boundary ------------------------------------------------
# Checking only that the REQUIRED valid times are PRESENT would let a run carry
# extra steps outside the -3h/+24h boundary. That matters twice over: the API
# samples the nearest published step within an hour, so an out-of-window step
# can answer a question it has no business answering, and every extra step
# spends the 25 GiB cap on evidence nothing is allowed to display.


def test_a_step_outside_the_evidence_window_fails_qc() -> None:
    window = FetchWindow(now=T0)
    beyond = datetime(2026, 9, 13, 12, tzinfo=UTC)  # +15 d, past the +14 d edge
    dataset = make_dataset(times=(T0, beyond))
    manifest = RunManifest(source_id="eccc-hrdps", fields=(RequiredField(name="temperature_2m", units="degC"),))

    result = validate_run(manifest, dataset, window=window)

    assert result.qc_passed is False, "an out-of-window step is a contract violation, not a gap"
    assert result.complete is False
    assert "out_of_window:2026-09-13T12:00:00Z" in result.flags
    assert result.as_quality()["status"] == "failed"


def test_a_step_before_the_window_start_is_caught_too() -> None:
    window = FetchWindow(now=T0)
    stale = datetime(2026, 8, 27, 12, tzinfo=UTC)  # -48 h, past the -24 h edge
    dataset = make_dataset(times=(stale, T0))

    result = validate_run(
        RunManifest(source_id="eccc-hrdps", fields=(RequiredField(name="temperature_2m", units="degC"),)),
        dataset,
        window=window,
    )

    assert result.qc_passed is False
    assert "out_of_window:2026-08-27T12:00:00Z" in result.flags


def test_steps_inside_the_window_are_not_flagged() -> None:
    """The boundary is inclusive at both edges, so an exact -24h/+14d step passes."""
    window = FetchWindow(now=T0)
    dataset = make_dataset(times=(window.start, T0, window.end))

    result = validate_run(
        RunManifest(source_id="eccc-hrdps", fields=(RequiredField(name="temperature_2m", units="degC"),)),
        dataset,
        window=window,
    )

    assert result.complete is True
    assert result.qc_passed is True
    assert not [flag for flag in result.flags if flag.startswith("out_of_window")]


def test_many_out_of_window_steps_are_reported_but_capped() -> None:
    """A badly-bounded run can carry hundreds; the flag list stays readable."""
    window = FetchWindow(now=T0)
    strays = tuple(datetime(2026, 9, day, 12, tzinfo=UTC) for day in range(14, 23))
    dataset = make_dataset(times=(T0, *strays))

    result = validate_run(
        RunManifest(source_id="eccc-hrdps", fields=(RequiredField(name="temperature_2m", units="degC"),)),
        dataset,
        window=window,
    )

    flagged = [flag for flag in result.flags if flag.startswith("out_of_window:")]
    assert len(flagged) == 6, "five named steps plus one summary flag"
    assert any(flag.endswith("_more") for flag in flagged)
    assert result.qc_passed is False
