"""Retention is the sliding window, and a purge never serves truncated bytes.

Two halves. The rules themselves - which frames leave, the two-run ceiling,
that no archive accumulates with free space available - are properties of the
database and are proved against a real PostgreSQL in
``infra/postgres/tests/retention_invariants.sql`` (``make test-sql``). What is
asserted here is everything the Python side owns: that it asks the one purge
rather than deciding for itself, that the sweep survives a missing object, that
a purged revision can never keep answering out of the dataset cache, and that
an unreadable store fails closed instead of guessing an absence.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pytest

from weather_api import config
from weather_api.store import (
    ArtifactIntegrityError,
    LiveStore,
    PurgeResult,
    StoreUnavailable,
    drain_purged_objects,
    last_valid_times,
    published_frame_times,
    purge_outside_window,
    reclaimable_bytes,
    record_last_valid_time,
    stream_last_valid_times,
    valid_time_nanoseconds,
)

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATION = EXPERIMENT_ROOT / "infra" / "postgres" / "init" / "003_retention_window.sql"
T0 = datetime(2026, 9, 2, 12, tzinfo=UTC)


# --- doubles -------------------------------------------------------------

class _Cursor:
    def __init__(self, answers: dict[str, Any], events: list[tuple[str, Any]], fail: str | None) -> None:
        self._answers, self._events, self._fail, self._last = answers, events, fail, ""

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        text = " ".join(sql.split()).lower()
        for marker, name in (
            ("purge_outside_window", "purge"),
            ("claim_purged_objects", "claim"),
            ("reclaimable_bytes", "reclaimable"),
            ("record_last_valid_time", "record"),
            ("stream_last_valid_time", "streams"),
            ("artifact_revisions", "frames"),
        ):
            if marker in text:
                self._last = name
                break
        else:
            self._last = text
        if self._fail == self._last:
            raise RuntimeError("the metadata store is unreachable")
        self._events.append((self._last, params))

    def fetchone(self) -> tuple[Any, ...]:
        return (self._answers.get(self._last, 0),)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._answers.get(self._last, []))


class _S3:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        if Key == "already-gone":
            raise RuntimeError("NoSuchKey")
        self.deleted.append(Key)


class _Config:
    bucket = "weather-artifacts"
    cap_bytes = config.STORAGE_CAP_BYTES


class FakeStore:
    """An artifact store double that records the statements it is sent."""

    def __init__(self, answers: dict[str, Any] | None = None, *, fail: str | None = None, connect: bool = True) -> None:
        self.answers = answers or {}
        self.events: list[tuple[str, Any]] = []
        self.s3 = _S3()
        self.config = _Config()
        self._fail, self._connect = fail, connect

    def connection(self):
        if not self._connect:
            raise RuntimeError("postgres refused the connection")

        answers, events, fail = self.answers, self.events, self._fail

        @contextmanager
        def opened() -> Iterator[Any]:
            class _Connection:
                def cursor(self) -> _Cursor:
                    return _Cursor(answers, events, fail)

                def __enter__(self) -> Any:
                    return self

                def __exit__(self, *_exc: object) -> None:
                    return None

            yield _Connection()

        return opened()

    def used_bytes(self) -> int:
        return int(self.answers.get("used", 0))


# --- the window and the ceiling are stated once --------------------------

def test_the_migration_states_the_same_window_and_two_runs_ceiling_as_the_config():
    """SQL cannot import Python, so the two copies are pinned to each other."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"window_back\(\)[\s\S]{0,120}interval '24 hours'", sql)
    assert re.search(r"window_forward\(\)[\s\S]{0,120}interval '14 days'", sql)
    assert re.search(r"keep_complete_runs\(\)[\s\S]{0,120}SELECT 2", sql)
    assert config.WINDOW_BACK == timedelta(hours=24)
    assert config.WINDOW_FORWARD == timedelta(days=14)
    assert config.KEEP_COMPLETE_RUNS == 2


def test_publication_and_purge_are_one_transaction():
    """publish_run purges before it returns, inside its own function body."""
    sql = MIGRATION.read_text(encoding="utf-8")
    body = sql[sql.index("FUNCTION weather_experiment.publish_run(candidate_run uuid)"):]
    assert "PERFORM weather_experiment.purge_outside_window(now());" in body
    assert body.index("PERFORM weather_experiment.purge_outside_window") < body.index("RETURN published_count")


def test_the_observation_floor_is_the_window_not_three_hours():
    assert config.OBSERVATION_RETENTION == config.WINDOW_BACK == timedelta(hours=24)


# --- the purge: one definition, asked rather than reimplemented ----------

def test_the_purge_asks_the_database_and_then_drains_the_freed_objects():
    store = FakeStore({"purge": 3, "claim": [("key-a",), ("key-b",)]})

    result = purge_outside_window(store, now=T0)

    assert result == PurgeResult(revisions=3, objects_deleted=2, objects_missing=0)
    # Rows before objects: the purge statement has already returned by the time
    # the first object delete goes out.
    assert [kind for kind, _ in store.events] == ["purge", "claim"]
    assert store.events[0][1] == (T0,)
    assert store.s3.deleted == ["key-a", "key-b"]


def test_the_purge_is_asked_about_the_instant_given_not_about_now():
    store = FakeStore({"purge": 0, "claim": []})
    purge_outside_window(store, now=T0)
    assert store.events[0][1] == (T0,)


def test_a_missing_object_does_not_abort_the_sweep():
    """The metadata row is the record of truth; the object may already be gone."""
    store = FakeStore({"claim": [("already-gone",), ("key-b",)]})

    deleted, missing = drain_purged_objects(store)

    assert (deleted, missing) == (1, 1)
    assert store.s3.deleted == ["key-b"]


def test_an_unreadable_store_fails_closed_rather_than_reporting_nothing_purged():
    store = FakeStore(connect=False)
    with pytest.raises(StoreUnavailable):
        purge_outside_window(store, now=T0)


def test_a_purge_that_raises_never_reports_a_count():
    store = FakeStore({"claim": []}, fail="purge")
    with pytest.raises(StoreUnavailable):
        purge_outside_window(store, now=T0)


def test_no_archive_is_planned_by_the_python_side():
    """Nothing here can decide to keep a run: it has no rule of its own.

    The only statements the purge path sends are the purge and the drain. A
    Python-side rule about how much history to keep would be a second retention
    policy, and two policies is how a store becomes an archive by accident.
    """
    store = FakeStore({"purge": 5, "claim": []})
    purge_outside_window(store, now=T0)
    assert {kind for kind, _ in store.events} == {"purge", "claim"}


# --- what the store holds, and how far it ever reached -------------------

def test_published_frame_times_answer_in_integer_nanoseconds():
    stamps = [T0.isoformat(), (T0 + timedelta(hours=1)).isoformat()]
    store = FakeStore({"frames": [("eccc-hrdps", "2026090212", stamps, T0, T0 + timedelta(hours=1))]})

    present = published_frame_times(store)

    assert present == {
        ("eccc-hrdps", "2026090212"): {
            valid_time_nanoseconds(T0),
            valid_time_nanoseconds(T0 + timedelta(hours=1)),
        }
    }


def test_a_resolution_difference_cannot_read_as_a_missing_frame():
    """``Z`` and ``+00:00`` are the same instant and must key the same."""
    assert valid_time_nanoseconds(datetime.fromisoformat("2026-09-02T12:00:00+00:00")) == valid_time_nanoseconds(T0)
    assert valid_time_nanoseconds(T0.astimezone(UTC)) == valid_time_nanoseconds(T0)
    assert valid_time_nanoseconds(T0) == 1_788_350_400_000_000_000


def test_an_offsetless_frame_time_has_no_place_on_the_timeline():
    with pytest.raises(ValueError, match="offsetless"):
        valid_time_nanoseconds(T0.replace(tzinfo=None))


def test_an_unreadable_store_is_not_an_empty_one():
    """Refetching everything because the store blinked is how a restart
    becomes an outage on the constraint that binds."""
    store = FakeStore(connect=False)
    with pytest.raises(StoreUnavailable):
        published_frame_times(store)


def test_the_last_valid_time_is_kept_per_stream_and_folded_per_source():
    rows = [
        ("eccc-hrdps", "surface", T0),
        ("eccc-hrdps", "profile", T0 + timedelta(hours=6)),
        ("awc-metar-speci", "metar", T0 - timedelta(hours=2)),
    ]
    store = FakeStore({"streams": rows})

    assert stream_last_valid_times(store) == {
        ("eccc-hrdps", "surface"): T0,
        ("eccc-hrdps", "profile"): T0 + timedelta(hours=6),
        ("awc-metar-speci", "metar"): T0 - timedelta(hours=2),
    }
    assert last_valid_times(store) == {
        "eccc-hrdps": T0 + timedelta(hours=6),
        "awc-metar-speci": T0 - timedelta(hours=2),
    }


def test_a_stream_with_no_record_is_absent_rather_than_zero():
    """Absent means never held. A default would be a claim about history."""
    store = FakeStore({"streams": []})
    assert stream_last_valid_times(store) == {}
    assert last_valid_times(store) == {}


def test_recording_a_last_valid_time_goes_through_the_never_lowered_function():
    store = FakeStore()
    record_last_valid_time(store, source_id="eccc-hrdps", logical_name="surface", valid_time=T0)
    assert store.events == [("record", ("eccc-hrdps", "surface", T0))]


def test_an_unreadable_last_valid_time_record_is_unavailable_not_an_absence():
    """Guessing between aged out and null is itself a fabrication."""
    store = FakeStore(connect=False)
    with pytest.raises(StoreUnavailable):
        last_valid_times(store)


# --- the projection may only count what is already outside ---------------

def test_reclaimable_bytes_are_asked_of_the_database_for_the_given_instant():
    store = FakeStore({"reclaimable": 4 << 30})
    assert reclaimable_bytes(store, now=T0) == 4 << 30
    assert store.events == [("reclaimable", (T0,))]


# --- purge safety against an open read -----------------------------------

class _ArtifactStoreStub:
    """Just enough of the store for LiveStore's cache and integrity paths."""

    def __init__(self, artifacts: list[Any]) -> None:
        self._artifacts = artifacts

    def current_artifacts(self, **_kwargs: Any) -> list[Any]:
        return list(self._artifacts)


class _Artifact:
    def __init__(self, revision_id: str) -> None:
        self.revision_id = revision_id
        self.source_id = "eccc-hrdps"
        self.logical_name = "surface"
        self.object_key = f"artifacts/{revision_id}"
        self.byte_size = 16
        self.media_type = "application/zarr+zip"
        self.provenance: dict[str, Any] = {"sha256": "0" * 64}


def test_cache_drop_of_a_purged_revision_means_it_never_answers_again(tmp_path):
    """A cached dataset whose revision the purge removed must never answer again."""
    kept, purged = _Artifact("rev-kept"), _Artifact("rev-purged")
    live = LiveStore(_ArtifactStoreStub([kept, purged]), tmp_path)
    live._datasets["rev-kept"] = object()
    live._datasets["rev-purged"] = object()

    live._forget_stale_datasets({"rev-kept"})

    assert set(live._datasets) == {"rev-kept"}


def test_a_purge_during_read_fails_closed_rather_than_serving_truncated_bytes(tmp_path):
    """Truncated bytes are an outage, not a reading."""
    artifact = _Artifact("rev-a")
    live = LiveStore(_ArtifactStoreStub([artifact]), tmp_path)

    with pytest.raises(ArtifactIntegrityError):
        live._verify(artifact, size=8, sha256="1" * 64)


def test_a_purge_during_read_never_removes_bytes_behind_a_current_pointer():
    """No object is removed while a current pointer still references it."""
    sql = MIGRATION.read_text(encoding="utf-8")
    body = sql[sql.index("FUNCTION weather_experiment.purge_outside_window("):]
    body = body[: body.index("$$;")]
    assert "DELETE FROM weather_experiment.current_artifacts" in body
    assert "DELETE FROM weather_experiment.artifact_revisions" in body
    assert body.index("current_artifacts c") < body.index("DELETE FROM weather_experiment.artifact_revisions")
    # And the last valid time is recorded before anything is removed, or the
    # absence the purge creates could only ever be reported as null.
    assert body.index("INSERT INTO weather_experiment.stream_last_valid_time") < body.index("WITH doomed")
