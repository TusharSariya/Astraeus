"""Derived artifacts are recomputed from retained inputs, never re-fetched.

`artifact-ingestion` requires a derived-here or display-derived artifact absent
after a restart to be rebuilt from the retained inputs already inside the
window, and requires one whose inputs are not all present to be absent and to
report the absence state of its *worst* input - `aged out` where an input was
purged, `null` where one was never retrieved. A derivation whose input is gone
must not reach for a substitute or compute from a shorter input set.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ingest.scheduler import ABSENCE_RANK, DerivedPlan, InputState, derived_plan, worst_absence

UTC = timezone.utc
T0 = datetime(2026, 9, 2, 12, tzinfo=UTC)
LAST = T0 - timedelta(days=2)


# --- an input's own state ------------------------------------------------

def test_an_input_reports_present_aged_out_or_null() -> None:
    assert InputState("goes19-cloud-mask", present=True).absence == "present"
    assert InputState("goes19-cloud-mask", last_valid_time=LAST).absence == "aged_out"
    assert InputState("goes19-cloud-mask").absence == "null"


def test_aged_out_requires_a_recorded_last_valid_time() -> None:
    """A deployment that never held a frame must not claim it did."""
    assert InputState("never-held").absence == "null"
    assert InputState("never-held").last_valid_time is None


def test_null_is_the_worse_state_because_it_names_no_edge_of_what_was_available() -> None:
    assert ABSENCE_RANK["present"] < ABSENCE_RANK["aged_out"] < ABSENCE_RANK["null"]
    assert worst_absence(["present", "aged_out"]) == "aged_out"
    assert worst_absence(["aged_out", "null"]) == "null"
    assert worst_absence([]) == "present"


# --- all inputs present: recompute ---------------------------------------

def test_a_derived_artifact_with_every_input_retained_is_recomputed_not_refetched() -> None:
    plan = derived_plan([
        InputState("eccc-hrdps/surface", present=True),
        InputState("goes19/cloud-mask", present=True),
    ])

    assert plan == DerivedPlan(True, detail="recomputing from 2 retained input(s); no upstream request is made")
    assert plan.absence is None
    assert "upstream" in plan.detail and "no upstream request" in plan.detail


# --- an input aged out ----------------------------------------------------

def test_an_aged_out_input_makes_the_derived_artifact_absent_naming_that_input() -> None:
    plan = derived_plan([
        InputState("eccc-hrdps/surface", present=True),
        InputState("goes19/cloud-mask", last_valid_time=LAST),
    ])

    assert not plan.recompute, "never computed from a shorter input set"
    assert plan.absence == "aged_out"
    assert plan.last_valid_time == LAST
    assert plan.blocking == ("goes19/cloud-mask",)
    assert plan.detail == f"aged out at {LAST.isoformat()} naming goes19/cloud-mask"


# --- an input never retrieved ---------------------------------------------

def test_an_input_that_was_never_retrieved_makes_the_derived_artifact_null() -> None:
    plan = derived_plan([InputState("open-meteo/weathernext", present=False)])

    assert plan.absence == "null"
    assert plan.last_valid_time is None
    assert plan.detail == "null naming open-meteo/weathernext"


def test_the_worst_input_wins_when_one_aged_out_and_another_was_never_held() -> None:
    plan = derived_plan([
        InputState("eccc-hrdps/surface", present=True),
        InputState("goes19/cloud-mask", last_valid_time=LAST),
        InputState("open-meteo/weathernext"),
    ])

    assert plan.absence == "null"
    assert plan.blocking == ("open-meteo/weathernext",)
    assert plan.last_valid_time is None, "the reported state is the worst input's, not a mixture"


def test_two_aged_out_inputs_report_the_later_edge_of_what_was_available() -> None:
    earlier, later = LAST, LAST + timedelta(hours=6)
    plan = derived_plan([
        InputState("a", last_valid_time=earlier),
        InputState("b", last_valid_time=later),
    ])

    assert plan.absence == "aged_out"
    assert plan.last_valid_time == later
    assert plan.blocking == ("a", "b")


def test_a_derivation_declaring_no_inputs_is_null_rather_than_recomputed() -> None:
    plan = derived_plan([])

    assert not plan.recompute and plan.absence == "null"
    assert "no inputs" in plan.detail


def test_inputs_may_be_given_as_a_mapping() -> None:
    plan = derived_plan({"a": InputState("a", present=True)})

    assert plan.recompute


# --- the recompute path reads the store, never an adapter -----------------

def test_the_cycle_that_recomputes_derived_artifacts_reads_current_artifacts_only() -> None:
    """`cloud_motion_cycle` is the recompute path this rule already governs:
    it reads the store's retained artifacts and stages a new derived artifact,
    and there is no adapter fetch anywhere on it."""
    from ingest.derive import cloud_motion

    class _Store:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def current_artifacts(self):
            self.calls.append("current_artifacts")
            return []

    store = _Store()
    lines = cloud_motion.cloud_motion_cycle(store)

    assert store.calls == ["current_artifacts"], "the retained inputs are the only thing read"
    assert lines == [], "nothing derivable and nothing fetched"


def test_an_unreadable_store_reports_rather_than_refetching_inputs() -> None:
    from ingest.derive import cloud_motion

    class _Store:
        def current_artifacts(self):
            raise RuntimeError("database unavailable")

    lines = cloud_motion.cloud_motion_cycle(_Store())

    assert len(lines) == 1 and "unreadable" in lines[0]
