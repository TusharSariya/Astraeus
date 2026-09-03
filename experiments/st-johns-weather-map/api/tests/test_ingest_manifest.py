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
from ingest.grib import declare_time_average, stack_members
from ingest.manifest import (
    ManifestError,
    MemberReport,
    RequiredField,
    RunManifest,
    ValidationResult,
    validate_run,
)

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


# --- the member axis ------------------------------------------------------
#
# Member completeness is computed from what was decoded, never asserted from
# the request that was issued, so every test below builds the member axis the
# way ``ingest.grib.stack_members`` builds it and lets ``validate_run`` read it.


def make_member_dataset(
    members: tuple[str, ...] = ("01", "02", "03"),
    *,
    control: str | None = "01",
    times: tuple[datetime, ...] = (T0,),
    units: str = "degC",
) -> xarray.Dataset:
    """One run on a member axis: ``member`` in front of valid_time/lat/lon."""
    shape = (len(times), len(LATITUDES), len(LONGITUDES))
    per_member = {
        identifier: xarray.DataArray(
            numpy.full(shape, 10.0),
            dims=("valid_time", "latitude", "longitude"),
            coords={
                "valid_time": [_stamp(moment) for moment in times],
                "latitude": LATITUDES,
                "longitude": LONGITUDES,
            },
            attrs={"units": units},
        )
        for identifier in members
    }
    return xarray.Dataset({"temperature_2m": stack_members(per_member, control=control)})


def member_manifest(**kwargs) -> RunManifest:
    defaults: dict = dict(
        source_id="test-source",
        fields=(RequiredField("temperature_2m", "degC", level="2 m"),),
        member_count=3,
        control="01",
    )
    defaults.update(kwargs)
    return RunManifest(**defaults)


def test_a_complete_member_set_publishes_and_reports_its_members():
    result = validate_run(member_manifest(), make_member_dataset(), window=window())

    assert result.publishable is True
    assert result.members == MemberReport(declared=3, present=("01", "02", "03"), missing=(), control="01")
    assert result.as_members() == {
        "declared": 3,
        "present": ["01", "02", "03"],
        "missing": [],
        "control": "01",
        # The adapter knows the access shape and this one stated none, so the
        # block says so rather than guessing a shape from the member count.
        "control_retrieval": None,
    }


def test_the_adapter_states_how_the_control_was_retrieved():
    """REPS fetches each member as its own coverage, the control included."""
    result = validate_run(
        member_manifest(),
        make_member_dataset(),
        window=window(),
        control_retrieval="separate_coverage",
    )

    assert result.members.control_retrieval == "separate_coverage"
    assert result.as_members()["control_retrieval"] == "separate_coverage"


def test_the_two_file_aifs_ens_control_is_recorded_as_a_separate_retrieval():
    """One axis, two retrievals: provenance says the control came from ``cf``."""
    dataset = make_member_dataset(members=("0", "1", "2"), control="0")
    result = validate_run(
        member_manifest(control="0"),
        dataset,
        window=window(),
        declared_members=("0", "1", "2"),
        control_retrieval="separate_file",
    )

    assert result.publishable is True
    assert result.as_members() == {
        "declared": 3,
        "present": ["0", "1", "2"],
        "missing": [],
        "control": "0",
        "control_retrieval": "separate_file",
    }


def test_a_retrieval_shape_outside_the_declared_vocabulary_is_refused():
    with pytest.raises(ManifestError):
        validate_run(
            member_manifest(),
            make_member_dataset(),
            window=window(),
            control_retrieval="somehow",
        )


def test_a_family_with_no_control_records_no_retrieval_shape():
    """No control means no retrieval to describe, whatever the adapter passed."""
    dataset = make_member_dataset(control=None)
    result = validate_run(
        member_manifest(control=None), dataset, window=window(), control_retrieval="same_file"
    )

    assert result.as_members()["control_retrieval"] is None


def test_a_member_axis_in_front_leaves_coverage_and_the_lat_lon_checks_working():
    """The grid checks must not care that ``member`` is now the leading axis."""
    dataset = make_member_dataset()
    assert dataset["temperature_2m"].dims == ("member", "valid_time", "latitude", "longitude")

    result = validate_run(member_manifest(), dataset, window=window())

    assert result.coverage_fraction == 1.0
    assert not [flag for flag in result.flags if flag.startswith(("missing_axis", "empty_grid"))]


def test_partial_members_names_the_missing_ones_when_they_are_declared():
    result = validate_run(
        member_manifest(),
        make_member_dataset(members=("01", "03")),
        window=window(),
        declared_members=("01", "02", "03"),
    )

    assert result.complete is False
    assert "partial_members:02" in result.flags
    # A shortfall is not a QC failure: what arrived is right, there is less of it.
    assert result.qc_passed is True
    assert result.as_quality()["status"] == "suspect"
    assert result.members.missing == ("02",)


def test_partial_members_reports_a_ratio_when_the_identifiers_are_not_declared():
    result = validate_run(member_manifest(), make_member_dataset(members=("01", "03")), window=window())

    assert result.complete is False
    assert "partial_members:2/3" in result.flags
    assert result.members.present == ("01", "03")


def test_no_members_at_all_fails_the_run_rather_than_publishing_thin():
    result = validate_run(member_manifest(), make_dataset(), window=window())

    assert result.complete is False
    assert "no_members" in result.flags
    assert result.members.present == ()


def test_a_declared_control_that_no_member_carries_fails_the_run():
    """The AIFS-ENS ``cf`` file did not arrive: partial, not a complete 50."""
    dataset = make_member_dataset(members=("1", "2", "3"), control="0")
    manifest = member_manifest(member_count=4, control="0")

    result = validate_run(manifest, dataset, window=window(), declared_members=("0", "1", "2", "3"))

    assert result.complete is False
    assert "control_missing:0" in result.flags
    assert "partial_members:0" in result.flags
    assert result.qc_passed is True
    assert result.members.control == "0"
    assert "0" in result.members.missing
    assert not bool(dataset["control"].values.any()), "no perturbed member may take the flag"


def test_a_family_with_no_control_is_judged_on_its_members_alone():
    dataset = make_member_dataset(members=("01", "02", "03"), control=None)
    result = validate_run(member_manifest(control=None), dataset, window=window())

    assert result.publishable is True
    assert not [flag for flag in result.flags if flag.startswith("control_missing")]
    assert result.as_members()["control"] is None


def test_a_deterministic_run_with_no_member_axis_validates_exactly_as_before():
    manifest = make_manifest(required_valid_times=(T0,))
    result = validate_run(manifest, make_dataset(), window=window())

    assert result.publishable is True
    assert result.flags == ()
    assert result.members is None
    assert result.as_members() is None


def test_a_manifest_rejects_a_member_count_below_one():
    with pytest.raises(ManifestError):
        make_manifest(member_count=0)


# --- the averaging window -------------------------------------------------


def _averaged_dataset(*, window_label: str | None) -> xarray.Dataset:
    dataset = make_dataset()
    variable = dataset["temperature_2m"]
    if window_label is None:
        # A time mean whose producer record stated no window: the attribute the
        # window would have gone in is simply absent.
        variable.attrs = {**variable.attrs, "cell_methods": "time: mean"}
    else:
        declare_time_average(variable, window_label=window_label)
    return dataset


def test_a_time_mean_that_states_its_averaging_window_passes():
    result = validate_run(make_manifest(), _averaged_dataset(window_label="18-24 hour ave fcst"), window=window())

    assert result.publishable is True
    assert not [flag for flag in result.flags if flag.startswith("averaging_window")]


def test_a_time_mean_with_no_averaging_window_fails_qc():
    """A mean whose window is unknown is not a quantity anyone can weigh."""
    result = validate_run(make_manifest(), _averaged_dataset(window_label=None), window=window())

    assert result.qc_passed is False
    assert "averaging_window_unstated:temperature_2m" in result.flags
    assert result.as_quality()["status"] == "failed"


def test_an_instantaneous_field_is_not_asked_for_an_averaging_window():
    result = validate_run(make_manifest(), make_dataset(), window=window())
    assert not [flag for flag in result.flags if flag.startswith("averaging_window")]
