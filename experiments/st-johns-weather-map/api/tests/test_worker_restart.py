"""A restart resumes the window instead of refilling it.

`ingestion-worker-scheduling` fixes the order: sweep abandoned staging, purge
frames outside `now-24h .. now+14d`, then fetch only what the window is
missing. The store is never cleared on start, a frame already held is never
re-fetched, and a worker that cannot read the store reports unhealthy and
schedules nothing - because a worker that cannot see the cache would refetch
everything.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import pytest

from ingest.contract import FetchWindow, RunCandidate
from ingest.scheduler import plan_fetch, reconcile_on_start
from ingest.store import ArtifactStore, StoreConfig, StoreUnavailable
from ingest.validate import to_nanoseconds
from ingest.window import sliding_window

UTC = timezone.utc
T0 = datetime(2026, 9, 2, 12, tzinfo=UTC)


class _Store:
    """Records the order of the reconciliation steps."""

    def __init__(self, *, swept: int = 0, purged: int = 0, present: set[int] | None = None,
                 sweep_error: Exception | None = None, purge_error: Exception | None = None,
                 present_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._swept, self._purged = swept, purged
        self._present = present or set()
        self._sweep_error, self._purge_error, self._present_error = sweep_error, purge_error, present_error

    def sweep_abandoned_staging(self) -> int:
        self.calls.append("sweep")
        if self._sweep_error is not None:
            raise self._sweep_error
        return self._swept

    def purge_outside_window(self, now: datetime) -> int:
        self.calls.append(f"purge:{now.isoformat()}")
        if self._purge_error is not None:
            raise self._purge_error
        return self._purged

    def present_keys(self, source_id: str, provider_run_id: str) -> set[int]:
        self.calls.append(f"present:{source_id}")
        if self._present_error is not None:
            raise self._present_error
        return set(self._present)


def _candidate(*times: datetime) -> RunCandidate:
    return RunCandidate(provider_run_id="2026090212", run_time=T0, detail={"valid_times": [m.isoformat() for m in times]})


# --- the order of the three steps ---------------------------------------

def test_reconciliation_sweeps_then_purges_then_permits_fetching() -> None:
    store = _Store(swept=3, purged=7)

    reconciliation = reconcile_on_start(store, now=T0)

    assert store.calls == ["sweep", f"purge:{T0.isoformat()}"], "staging debris goes before the window purge"
    assert reconciliation.healthy and reconciliation.may_fetch
    assert (reconciliation.swept, reconciliation.purged) == (3, 7)
    assert "swept 3" in reconciliation.detail and "purged 7" in reconciliation.detail
    assert "clear" not in reconciliation.detail, "the store is never cleared on start"


# --- restart mid publication ---------------------------------------------

def test_a_restart_mid_publication_discards_staging_and_leaves_the_visible_run_current() -> None:
    """The sweep touches only staged rows; publication is what the previously
    visible run still answers from."""
    store = _Store(swept=4, purged=0)

    reconciliation = reconcile_on_start(store, now=T0)

    assert reconciliation.swept == 4
    assert reconciliation.purged == 0, "nothing inside the window is removed to tidy up an interrupted run"
    assert reconciliation.may_fetch, "the interrupted run is re-attempted from its own provider run id"


# --- a full window --------------------------------------------------------

def test_a_restart_with_a_full_window_purges_nothing_and_issues_no_fetch() -> None:
    times = (T0, T0 + timedelta(hours=1), T0 + timedelta(hours=2))
    store = _Store(swept=0, purged=0, present={to_nanoseconds(m) for m in times})

    reconciliation = reconcile_on_start(store, now=T0)
    plan = plan_fetch(store, source_id="eccc-hrdps", candidate=_candidate(*times), window=FetchWindow(now=T0))

    assert reconciliation.purged == 0
    assert plan.satisfied and plan.missing == ()


# --- a long outage --------------------------------------------------------

def test_a_restart_after_a_long_outage_purges_the_store_and_refills_no_history() -> None:
    """Every retained frame left the window while the stack was down."""
    store = _Store(swept=0, purged=412, present=set())

    reconciliation = reconcile_on_start(store, now=T0)
    # The window wants only what discovery offers now. Past frames are not
    # wanted, so no plan ever asks for them.
    past = T0 - timedelta(days=3)
    plan = plan_fetch(store, source_id="eccc-hrdps", candidate=_candidate(past), window=FetchWindow(now=T0))

    assert reconciliation.purged == 412
    assert plan.wanted == (), "no attempt is made to fetch past frames to refill the 24 hours of history"


def test_the_purge_boundary_is_the_shared_sliding_window() -> None:
    start, end = sliding_window(T0)
    assert start == T0 - timedelta(hours=24)
    assert end == T0 + timedelta(days=14)
    window = FetchWindow(now=T0)
    assert (window.start, window.end) == (start, end), "the FetchWindow reads the one definition"


# --- an unreadable store --------------------------------------------------

def test_a_restart_with_an_unreadable_store_schedules_no_fetch() -> None:
    store = _Store(sweep_error=StoreUnavailable("database unavailable"))

    reconciliation = reconcile_on_start(store, now=T0)

    assert not reconciliation.healthy and not reconciliation.may_fetch
    assert "could not be swept" in reconciliation.detail
    assert store.calls == ["sweep"], "nothing is purged and nothing is fetched after the store failed"


def test_a_purge_that_cannot_run_is_also_unhealthy() -> None:
    store = _Store(purge_error=StoreUnavailable("minio unreachable"))

    reconciliation = reconcile_on_start(store, now=T0)

    assert not reconciliation.may_fetch
    assert "could not be purged" in reconciliation.detail


def test_no_store_at_all_is_unhealthy_rather_than_an_empty_window() -> None:
    reconciliation = reconcile_on_start(None, now=T0)

    assert not reconciliation.may_fetch
    assert "no artifact store" in reconciliation.detail


# --- purge_outside_window delegates to the one purge ----------------------
#
# Which frames leave the window is decided by
# ``weather_experiment.purge_outside_window`` and proved against a real
# PostgreSQL in infra/postgres/tests/retention_invariants.sql. It has to be
# decided there and not here: only that transaction can record each stream's
# last valid time before removing anything, and only it can drop the
# ``current_artifacts`` pointer alongside the revision without tripping the
# foreign key. What these tests assert is the part that is this method's own -
# that it calls the one purge, drains the freed keys, and survives an object
# that is already gone.

class _Cursor:
    """Answers the two statements the delegated purge sends, in order."""

    def __init__(self, purged: int, queued: list[str], events: list[tuple[str, Any]]) -> None:
        self._purged, self._queued, self._events = purged, queued, events
        self._last = ""

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        text = " ".join(sql.split()).lower()
        self._last = "claim" if "claim_purged_objects" in text else "purge" if "purge_outside_window" in text else text
        self._events.append((self._last, params))

    def fetchone(self) -> tuple[Any, ...]:
        return (self._purged,)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return [(key,) for key in self._queued] if self._last == "claim" else []


class _Connection:
    def __init__(self, purged: int, queued: list[str], events: list[tuple[str, Any]]) -> None:
        self._purged, self._queued, self._events = purged, queued, events

    def cursor(self) -> _Cursor:
        return _Cursor(self._purged, self._queued, self._events)

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class _S3:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        if Key == "already-gone":
            raise RuntimeError("NoSuchKey")
        self.deleted.append(Key)


@pytest.fixture
def store_over(monkeypatch: pytest.MonkeyPatch):
    def build(purged: int, queued: list[str]) -> tuple[ArtifactStore, list[tuple[str, Any]], _S3]:
        events: list[tuple[str, Any]] = []
        instance = ArtifactStore(StoreConfig(database_url="postgresql://unused", endpoint="http://unused", bucket="b", access_key="k", secret_key="s"))
        client = _S3()
        instance._client = client

        @contextmanager
        def connection() -> Iterator[Any]:
            yield _Connection(purged, queued, events)

        monkeypatch.setattr(instance, "connection", connection)
        return instance, events, client

    return build


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def test_the_purge_is_the_databases_and_runs_before_any_object_is_touched(store_over) -> None:
    store, events, client = store_over(3, ["key-aged", "key-older"])

    assert store.purge_outside_window(T0) == 3
    # Rows before objects: the purge transaction has already committed by the
    # time the first delete_object goes out, and it is what named these keys.
    assert [kind for kind, _ in events] == ["purge", "claim"]
    assert events[0][1] == (T0,), "the purge is asked about the instant the caller gave, not about now()"
    assert client.deleted == ["key-aged", "key-older"]


def test_nothing_outside_the_window_frees_nothing_to_delete(store_over) -> None:
    store, events, client = store_over(0, [])

    assert store.purge_outside_window(T0) == 0
    assert client.deleted == []
    assert [kind for kind, _ in events] == ["purge", "claim"]


def test_an_object_already_gone_does_not_abort_the_sweep(store_over) -> None:
    store, _events, client = store_over(2, ["already-gone", "key-b"])

    assert store.purge_outside_window(T0) == 2
    assert client.deleted == ["key-b"], "the row is the record of truth; a missing object is skipped"
