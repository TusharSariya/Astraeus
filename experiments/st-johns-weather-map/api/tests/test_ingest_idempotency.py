"""Ingestion is idempotent by provider run id and frame time.

`artifact-ingestion` keys a frame on `(source_id, provider_run_id, valid_time)`
in integer nanoseconds, asks the store what is published under that key before
fetching, fetches only the answers that are no, refuses a byte-different fetch
of a published key as `run_identity_conflict`, and fails the source outright
when the store cannot be asked - because an unknown cache state is not an empty
one, and refetching everything on an unreadable store is how a restart becomes
an outage on the constraint that binds.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest

from ingest.contract import Artifact, FetchWindow, RunCandidate, RunResult
from ingest.manifest import declared_classes
from ingest.scheduler import SATISFIED_REASON, candidate_valid_times, plan_fetch
from ingest.store import ArtifactStore, RunIdentityConflict, StoreConfig, StoreUnavailable, sha256_of
from ingest.validate import to_nanoseconds

UTC = timezone.utc
T0 = datetime(2026, 9, 2, 12, tzinfo=UTC)


def _candidate(*times: datetime, provider_run_id: str = "2026090212") -> RunCandidate:
    return RunCandidate(
        provider_run_id=provider_run_id,
        run_time=T0,
        detail={"valid_times": [moment.isoformat() for moment in times]},
    )


class _Store:
    """Answers the restart-cache protocol and records what was asked."""

    def __init__(self, present: set[int] | None = None, *, raises: Exception | None = None) -> None:
        self._present = present or set()
        self._raises = raises
        self.asked: list[tuple[str, str]] = []

    def present_keys(self, source_id: str, provider_run_id: str) -> set[int]:
        self.asked.append((source_id, provider_run_id))
        if self._raises is not None:
            raise self._raises
        return set(self._present)


# --- the key is nanoseconds ---------------------------------------------

def test_a_frame_is_keyed_by_integer_nanoseconds_so_resolution_cannot_read_as_missing() -> None:
    coarse = datetime(2026, 9, 2, 15, tzinfo=UTC)
    fine = coarse.replace(microsecond=0)
    assert to_nanoseconds(coarse) == to_nanoseconds(fine)
    # A naive coordinate is read as UTC, which is what every dataset time axis
    # in this experiment carries.
    assert to_nanoseconds(coarse.replace(tzinfo=None)) == to_nanoseconds(coarse)
    assert to_nanoseconds(coarse + timedelta(hours=1)) - to_nanoseconds(coarse) == 3600 * 10**9


def test_candidate_valid_times_are_read_from_what_discovery_declared() -> None:
    candidate = _candidate(T0, T0 + timedelta(hours=1))
    assert candidate_valid_times(candidate) == (T0, T0 + timedelta(hours=1))
    assert candidate_valid_times(RunCandidate(provider_run_id="x", run_time=None)) == ()


# --- ask before fetching -------------------------------------------------

def test_a_satisfied_window_asks_the_store_and_fetches_nothing() -> None:
    times = (T0, T0 + timedelta(hours=1), T0 + timedelta(hours=2))
    store = _Store({to_nanoseconds(moment) for moment in times})

    plan = plan_fetch(store, source_id="eccc-hrdps", candidate=_candidate(*times), window=FetchWindow(now=T0))

    assert store.asked == [("eccc-hrdps", "2026090212")]
    assert plan.satisfied and not plan.should_fetch
    assert plan.missing == ()
    assert "already holds every frame" in plan.reason == SATISFIED_REASON


def test_a_partly_filled_window_fetches_only_the_missing_frames() -> None:
    times = (T0, T0 + timedelta(hours=1), T0 + timedelta(hours=2))
    store = _Store({to_nanoseconds(times[0])})

    plan = plan_fetch(store, source_id="eccc-hrdps", candidate=_candidate(*times), window=FetchWindow(now=T0))

    assert not plan.satisfied
    assert plan.missing == (to_nanoseconds(times[1]), to_nanoseconds(times[2]))
    assert to_nanoseconds(times[0]) not in plan.missing, "a published frame is neither re-fetched nor re-uploaded"


def test_frames_outside_the_window_are_not_wanted_and_do_not_force_a_fetch() -> None:
    inside = (T0, T0 + timedelta(hours=1))
    outside = T0 + timedelta(days=15)
    store = _Store({to_nanoseconds(moment) for moment in inside})

    plan = plan_fetch(store, source_id="eccc-hrdps", candidate=_candidate(*inside, outside), window=FetchWindow(now=T0))

    assert plan.satisfied, "an out-of-window step is retention's business, not a missing frame"


def test_a_candidate_that_declares_no_times_is_fetched_rather_than_assumed_present() -> None:
    store = _Store(set())

    plan = plan_fetch(store, source_id="eccc-hrdps", candidate=RunCandidate(provider_run_id="r", run_time=T0), window=FetchWindow(now=T0))

    assert plan.should_fetch
    assert "rather than assuming" in plan.reason
    assert store.asked == [], "there is nothing to ask about, so the store is not consulted"


def test_a_store_that_cannot_be_asked_raises_rather_than_answering_empty() -> None:
    store = _Store(raises=StoreUnavailable("database unavailable"))

    with pytest.raises(StoreUnavailable):
        plan_fetch(store, source_id="eccc-hrdps", candidate=_candidate(T0), window=FetchWindow(now=T0))


# --- the same key with different bytes -----------------------------------

class _Cursor:
    def __init__(self, digests: dict[str, str]) -> None:
        self._digests = digests

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self._last = sql

    def fetchall(self) -> list[tuple[str, str]]:
        return list(self._digests.items())

    def fetchone(self) -> tuple[str, ...]:
        return ("run-1",)


class _Connection:
    def __init__(self, digests: dict[str, str]) -> None:
        self._digests = digests

    def cursor(self) -> _Cursor:
        return _Cursor(self._digests)

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _store_with(digests: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> ArtifactStore:
    instance = ArtifactStore(StoreConfig(database_url="postgresql://unused", endpoint="http://unused", bucket="b", access_key="k", secret_key="s"))

    @contextmanager
    def connection() -> Iterator[Any]:
        yield _Connection(digests)

    monkeypatch.setattr(instance, "connection", connection)
    return instance


def _result(path: Path) -> RunResult:
    artifact = Artifact(
        logical_name="hrdps-surface",
        media_type="application/zarr+zip",
        payload_path=path,
        provenance=declared_classes(["retrieved"]),
    )
    return RunResult(
        source_id="eccc-hrdps", provider_run_id="2026090212", run_time=T0,
        retrieved_at=T0, complete=True, qc_passed=True, artifacts=[artifact],
    )


def test_identical_bytes_for_a_published_key_pass_silently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = tmp_path / "a.zarr.zip"
    payload.write_bytes(b"the published bytes")
    store = _store_with({"hrdps-surface": sha256_of(payload)}, monkeypatch)

    store.assert_run_identity(_result(payload))  # an idempotent re-fetch is the ordinary case


def test_a_byte_different_fetch_of_a_published_key_is_refused_naming_both_digests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = tmp_path / "a.zarr.zip"
    payload.write_bytes(b"different bytes under the same run id")
    published = "0" * 64
    store = _store_with({"hrdps-surface": published}, monkeypatch)

    with pytest.raises(RunIdentityConflict) as caught:
        store.assert_run_identity(_result(payload))

    message = str(caught.value)
    assert "run_identity_conflict" in message
    assert published in message and sha256_of(payload) in message


def test_a_logical_name_that_was_never_published_is_not_a_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = tmp_path / "a.zarr.zip"
    payload.write_bytes(b"new stream")
    store = _store_with({"some-other-stream": "0" * 64}, monkeypatch)

    store.assert_run_identity(_result(payload))
