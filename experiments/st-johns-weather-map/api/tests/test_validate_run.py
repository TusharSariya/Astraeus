"""The out-of-window QC gate reads the one shared window definition.

`artifact-ingestion` requires the bounds to come from the single window
definition rather than being restated as literals in an adapter, caps the
reported flags at five with a `+N_more` remainder, and refuses a run carrying
no valid time inside the window rather than publishing it empty. A step inside
the window that retention will later purge is still published: ageing out is
retention's decision, not a QC verdict.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ingest.contract import FetchWindow
from ingest.validate import (
    MAX_REPORTED_OUT_OF_WINDOW,
    NO_STEP_IN_WINDOW,
    WINDOW_BACK,
    WINDOW_FORWARD,
    bounds_nanoseconds,
    out_of_window_verdict,
    sliding_window,
    to_nanoseconds,
)

UTC = timezone.utc
T0 = datetime(2026, 9, 2, 12, tzinfo=UTC)


def _ns(*times: datetime) -> list[int]:
    return [to_nanoseconds(moment) for moment in times]


# --- one definition, four readers ----------------------------------------

def test_out_of_window_bounds_come_from_the_single_window_definition() -> None:
    assert WINDOW_BACK == timedelta(hours=24)
    assert WINDOW_FORWARD == timedelta(days=14)
    assert sliding_window(T0) == (T0 - timedelta(hours=24), T0 + timedelta(days=14))
    # The FetchWindow, the QC gate and a bare instant all resolve to the same
    # bounds, which is the drift this change exists to stop.
    from_window = bounds_nanoseconds(FetchWindow(now=T0))
    from_instant = bounds_nanoseconds(T0)
    assert from_window == from_instant == tuple(_ns(*sliding_window(T0)))


def test_no_window_at_all_judges_nothing() -> None:
    verdict = out_of_window_verdict(_ns(T0 + timedelta(days=400)), None)
    assert verdict.flags == () and not verdict.refused


# --- inside the window ----------------------------------------------------

def test_out_of_window_boundaries_are_inclusive_at_both_edges() -> None:
    start, end = sliding_window(T0)
    verdict = out_of_window_verdict(_ns(start, T0, end), FetchWindow(now=T0))

    assert verdict.flags == ()
    assert verdict.outside == ()
    assert len(verdict.inside) == 3


def test_out_of_window_does_not_judge_a_step_retention_will_later_purge() -> None:
    """A frame at `now-23h` is inside the window today and will age out
    tomorrow. Ageing out is retention's decision, not a QC verdict."""
    verdict = out_of_window_verdict(_ns(T0 - timedelta(hours=23)), FetchWindow(now=T0))

    assert not verdict.refused


# --- outside the window ---------------------------------------------------

def test_out_of_window_flags_a_step_beyond_the_forward_edge() -> None:
    beyond = T0 + timedelta(days=15)
    verdict = out_of_window_verdict(_ns(T0, beyond), FetchWindow(now=T0))

    assert verdict.refused
    assert verdict.flags[0][0] == "out_of_window:2026-09-17T12:00:00Z"
    assert "falls outside the evidence window" in verdict.flags[0][1]


def test_out_of_window_flags_a_step_before_the_back_edge() -> None:
    stale = T0 - timedelta(hours=25)
    verdict = out_of_window_verdict(_ns(stale, T0), FetchWindow(now=T0))

    assert [flag for flag, _ in verdict.flags] == ["out_of_window:2026-09-01T11:00:00Z"]


def test_out_of_window_reports_five_steps_then_the_remainder() -> None:
    strays = tuple(T0 + timedelta(days=15 + index) for index in range(9))
    verdict = out_of_window_verdict(_ns(T0, *strays), FetchWindow(now=T0))

    named = [flag for flag, _ in verdict.flags if not flag.endswith("_more")]
    remainder = [flag for flag, _ in verdict.flags if flag.endswith("_more")]
    assert len(named) == MAX_REPORTED_OUT_OF_WINDOW == 5
    assert remainder == ["out_of_window:+4_more"], "nine strays, five named, four counted"
    assert "4 further step(s)" in dict(verdict.flags)["out_of_window:+4_more"]


def test_out_of_window_deduplicates_repeated_instants_before_capping() -> None:
    stray = T0 + timedelta(days=20)
    verdict = out_of_window_verdict(_ns(T0, stray, stray, stray), FetchWindow(now=T0))

    assert len(verdict.flags) == 1, "one instant is one flag however often the axis repeats it"


# --- a run with no in-window step ----------------------------------------

def test_out_of_window_refuses_a_run_with_no_step_inside_the_window() -> None:
    strays = (T0 + timedelta(days=15), T0 + timedelta(days=16))
    verdict = out_of_window_verdict(_ns(*strays), FetchWindow(now=T0))

    flags = [flag for flag, _ in verdict.flags]
    assert NO_STEP_IN_WINDOW in flags
    assert verdict.inside == ()
    detail = dict(verdict.flags)[NO_STEP_IN_WINDOW]
    assert "2026-09-01T12:00:00Z" in detail and "2026-09-16T12:00:00Z" in detail


def test_out_of_window_does_not_refuse_a_run_with_no_steps_at_all() -> None:
    """A dataset with no time coordinate is a different failure, reported by
    the caller as `missing_axis`, not as an empty window."""
    verdict = out_of_window_verdict([], FetchWindow(now=T0))

    assert verdict.flags == ()


def test_out_of_window_one_in_window_step_is_enough_to_keep_the_run() -> None:
    verdict = out_of_window_verdict(_ns(T0, T0 + timedelta(days=20)), FetchWindow(now=T0))

    flags = [flag for flag, _ in verdict.flags]
    assert NO_STEP_IN_WINDOW not in flags
    assert flags == ["out_of_window:2026-09-22T12:00:00Z"]


# --- the manifest validator carries the verdict through -------------------

def test_out_of_window_reaches_validate_run_as_a_qc_failure() -> None:
    xarray = pytest.importorskip("xarray")
    numpy = pytest.importorskip("numpy")
    from ingest.manifest import RequiredField, RunManifest, validate_run

    beyond = T0 + timedelta(days=15)
    dataset = xarray.Dataset(
        {"temperature_2m": (("valid_time", "latitude", "longitude"), numpy.zeros((2, 2, 2)), {"units": "degC"})},
        coords={
            "valid_time": numpy.array([T0, beyond], dtype="datetime64[ns]"),
            "latitude": [47.0, 48.0],
            "longitude": [-53.0, -52.0],
        },
    )
    manifest = RunManifest(source_id="eccc-hrdps", fields=(RequiredField(name="temperature_2m", units="degC"),))

    result = validate_run(manifest, dataset, window=FetchWindow(now=T0))

    assert result.qc_passed is False
    assert "out_of_window:2026-09-17T12:00:00Z" in result.flags
    assert result.as_quality()["status"] == "failed"
