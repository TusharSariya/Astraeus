"""A source outcome names what actually happened.

`ingestion-worker-scheduling` pins three cases this change creates: an
idempotent no-op is `succeeded` with zero artifacts and a reason naming the
satisfied window, so it is never mistaken for an upstream failure; a quota
failure names the 64 GiB cap and the projected size and evicts nothing; and a
run that never completes is `failed` every cycle without its staged bytes
accumulating, because abandoned staging is swept before the next attempt
reserves room.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

import pytest

from ingest.contract import Artifact, DiscoveryBounds, ResourceBounds, RunCandidate, RunResult
from ingest.manifest import declared_classes
from ingest.scheduler import SATISFIED_REASON
from ingest.store import (
    LOCAL_STORAGE_CAP_BYTES,
    STORAGE_CAP_LABEL,
    ArtifactStore,
    QuotaExceeded,
    ResourceBudgetExceeded,
    StoreConfig,
    StoreUnavailable,
)
from ingest.validate import to_nanoseconds
from worker.runtime import run_source

UTC = timezone.utc
T0 = datetime(2026, 9, 2, 12, tzinfo=UTC)
TIMES = (T0, T0 + timedelta(hours=1), T0 + timedelta(hours=2))


@dataclass
class _Config:
    source_id: str = "eccc-hrdps"
    producer: str = "ECCC"
    product: str = "HRDPS"
    registry_status: str = "implemented-unverified"
    cadence_seconds: int = 3600
    bounds: dict[str, float] = field(default_factory=dict)
    variables: tuple[str, ...] = ()


class _Adapter:
    adapter_version = "1"

    def __init__(self, result: RunResult | None = None, *, times: Sequence[datetime] = TIMES) -> None:
        self.source_id = "eccc-hrdps"
        self._result = result
        self._times = tuple(times)
        self.fetched = 0
        self.fetch_window: Any = None

    def discover(self, window: Any) -> list[RunCandidate]:
        return [RunCandidate(
            provider_run_id="2026090212", run_time=T0,
            detail={"valid_times": [moment.isoformat() for moment in self._times]},
        )]

    def discovery_bounds(self, window: Any) -> DiscoveryBounds:
        return DiscoveryBounds(received_bytes=1024)

    def fetch(self, candidate: Any, window: Any, workdir: Path) -> RunResult:
        self.fetched += 1
        self.fetch_window = window
        assert self._result is not None, "this adapter must never be asked to fetch"
        return self._result

    def resource_bounds(self, candidate: Any, window: Any) -> ResourceBounds:
        return ResourceBounds(store_bytes=1024, filesystem_bytes=2048, margin_bytes=256, received_bytes=1024)


class _Store:
    def __init__(self, *, present: set[int] | None = None, publish_error: Exception | None = None) -> None:
        self._present = present or set()
        self._publish_error = publish_error
        self.published = 0
        self.staged_bytes = 0
        self.events: list[str] = []

    def present_keys(self, source_id: str, provider_run_id: str) -> set[int]:
        return set(self._present)

    def upsert_source(self, **_kwargs: Any) -> None:
        return None

    @contextmanager
    def reserve_resources(self, **_kwargs: Any) -> Iterator[None]:
        self.events.append("reserved")
        try:
            yield
        finally:
            self.events.append("released")

    def stage_and_publish(self, result: RunResult) -> list[Any]:
        if self._publish_error is not None:
            raise self._publish_error
        self.published += 1
        return list(result.artifacts)


def _result(tmp_path: Path, *, complete: bool = True, qc_passed: bool = True, flags: Sequence[str] = ()) -> RunResult:
    payload = tmp_path / "surface.zarr.zip"
    payload.write_bytes(b"payload")
    provenance = {**declared_classes(["retrieved"]), "quality": {"flags": list(flags)}}
    return RunResult(
        source_id="eccc-hrdps", provider_run_id="2026090212", run_time=T0, retrieved_at=T0,
        complete=complete, qc_passed=qc_passed,
        artifacts=[Artifact(logical_name="surface", media_type="application/zarr+zip", payload_path=payload, provenance=provenance)],
    )


# --- an idempotent no-op --------------------------------------------------

def test_noop_a_satisfied_window_is_succeeded_with_zero_artifacts_and_a_reason() -> None:
    adapter = _Adapter(result=None)
    store = _Store(present={to_nanoseconds(moment) for moment in TIMES})

    outcome = run_source(adapter, _Config(), store, reference=T0)

    assert outcome.state == "succeeded"
    assert outcome.published == 0
    assert outcome.detail == SATISFIED_REASON
    assert adapter.fetched == 0, "no bulk upstream request is issued"
    assert store.published == 0, "nothing new is published"


def test_noop_is_not_reported_as_cancelled_or_failed() -> None:
    """An idempotent no-op must never be mistaken for an upstream failure."""
    store = _Store(present={to_nanoseconds(moment) for moment in TIMES})

    outcome = run_source(_Adapter(result=None), _Config(), store, reference=T0)

    assert outcome.state not in {"cancelled", "failed"}


def test_unrelated_retained_times_do_not_block_a_cold_window(tmp_path: Path) -> None:
    adapter = _Adapter(result=_result(tmp_path))
    store = _Store(present={to_nanoseconds(T0 - timedelta(hours=1))})
    outcome = run_source(adapter, _Config(), store, reference=T0)
    assert outcome.state == "succeeded"
    assert adapter.fetched == 1
    assert store.published == 1


def test_partial_aggregate_without_merge_support_fails_before_payload(tmp_path: Path) -> None:
    adapter = _Adapter(result=_result(tmp_path))
    store = _Store(present={to_nanoseconds(TIMES[0])})

    outcome = run_source(adapter, _Config(), store, reference=T0)

    assert outcome.state == "failed"
    assert "partial cache repair is unsupported" in outcome.detail
    assert "retained frames stay visible" in outcome.detail
    assert adapter.fetched == 0
    assert store.published == 0


def test_a_store_that_cannot_be_asked_fails_the_source_without_fetching() -> None:
    class _Unreadable(_Store):
        def present_keys(self, source_id: str, provider_run_id: str) -> set[int]:
            raise StoreUnavailable("database unavailable")

    adapter = _Adapter(result=None)

    outcome = run_source(adapter, _Config(), _Unreadable(), reference=T0)

    assert outcome.state == "failed"
    assert "could not be asked what is present" in outcome.detail
    assert adapter.fetched == 0, "an unknown cache state is not an empty one"


def test_unknown_resource_bounds_refuse_before_payload_retrieval(tmp_path: Path) -> None:
    adapter = _Adapter(result=_result(tmp_path))
    adapter.resource_bounds = None

    outcome = run_source(adapter, _Config(), _Store(), reference=T0)

    assert outcome.state == "failed"
    assert "upstream_budget_exhausted" in outcome.detail
    assert adapter.fetched == 0


def test_unknown_discovery_bounds_refuse_before_any_upstream_request(tmp_path: Path) -> None:
    adapter = _Adapter(result=_result(tmp_path))
    adapter.discovery_bounds = None
    adapter.discover = lambda _window: pytest.fail("discovery must not start without a measured bound")

    outcome = run_source(adapter, _Config(), _Store(), reference=T0)

    assert outcome.state == "failed"
    assert "upstream_budget_exhausted during discovery" in outcome.detail
    assert adapter.fetched == 0


def test_resource_refusal_precedes_payload_retrieval(tmp_path: Path) -> None:
    class _RefusingStore(_Store):
        @contextmanager
        def reserve_resources(self, **_kwargs: Any) -> Iterator[None]:
            raise ResourceBudgetExceeded("required 4097 bytes against 4096 unreserved free bytes")
            yield

    adapter = _Adapter(result=_result(tmp_path))
    outcome = run_source(adapter, _Config(), _RefusingStore(), reference=T0)

    assert outcome.state == "failed"
    assert "upstream_budget_exhausted" in outcome.detail
    assert adapter.fetched == 0


def test_payload_bearing_discovery_is_reserved_before_its_first_byte(tmp_path: Path) -> None:
    class _PayloadDiscovery(_Adapter):
        def operation_bounds(self, window: Any) -> ResourceBounds:
            return replace(self.resource_bounds(None, window), retained_memory_bytes=4096)

        def discover(self, window: Any) -> list[RunCandidate]:
            assert store.events == ["reserved"]
            return super().discover(window)

    store = _Store()
    adapter = _PayloadDiscovery(result=_result(tmp_path))

    outcome = run_source(adapter, _Config(), store, reference=T0)

    assert outcome.state == "succeeded"
    assert store.events == ["reserved", "released"]


def test_payload_discovery_never_starts_when_complete_admission_fails(tmp_path: Path) -> None:
    class _PayloadDiscovery(_Adapter):
        def operation_bounds(self, window: Any) -> ResourceBounds:
            return replace(self.resource_bounds(None, window), retained_memory_bytes=4096)

        def discover(self, window: Any) -> list[RunCandidate]:
            pytest.fail("payload discovery must remain behind admission")

    class _RefusingStore(_Store):
        @contextmanager
        def reserve_resources(self, **_kwargs: Any) -> Iterator[None]:
            raise ResourceBudgetExceeded("local capacity exhausted")
            yield

    outcome = run_source(_PayloadDiscovery(result=_result(tmp_path)), _Config(), _RefusingStore(), reference=T0)

    assert outcome.state == "failed"
    assert "pre-discovery admission" in outcome.detail


def test_payload_discovery_refuses_retained_objects_above_memory_bound(tmp_path: Path) -> None:
    class _PayloadDiscovery(_Adapter):
        def operation_bounds(self, window: Any) -> ResourceBounds:
            return replace(self.resource_bounds(None, window), retained_memory_bytes=1)

    store = _Store()
    outcome = run_source(_PayloadDiscovery(result=_result(tmp_path)), _Config(), store, reference=T0)

    assert outcome.state == "failed"
    assert "retained candidate objects" in outcome.detail
    assert store.events == ["reserved", "released"]


def test_underestimated_temporary_output_is_cleaned_and_never_published(tmp_path: Path) -> None:
    class _Underestimated(_Adapter):
        def resource_bounds(self, candidate: Any, window: Any) -> ResourceBounds:
            return ResourceBounds(store_bytes=1024, filesystem_bytes=4, margin_bytes=1, received_bytes=1024)

        def fetch(self, candidate: Any, window: Any, workdir: Path) -> RunResult:
            self.fetched += 1
            payload = workdir / "expanded.bin"
            payload.write_bytes(b"expanded")
            artifact = Artifact("expanded", "application/octet-stream", payload, declared_classes(["retrieved"]))
            return RunResult(self.source_id, candidate.provider_run_id, candidate.run_time, T0, True, True, [artifact])

    store = _Store()
    adapter = _Underestimated(result=None)
    outcome = run_source(adapter, _Config(), store, reference=T0)

    assert outcome.state == "failed"
    assert "temporary/extraction output" in outcome.detail
    assert store.published == 0
    assert store.events == ["reserved", "released"]


def test_cancellation_releases_the_resource_reservation() -> None:
    class _Cancelled(_Adapter):
        def fetch(self, candidate: Any, window: Any, workdir: Path) -> RunResult:
            self.fetched += 1
            from ingest.contract import AdapterUnavailable
            raise AdapterUnavailable("cancelled")

    store = _Store()
    outcome = run_source(_Cancelled(), _Config(), store, reference=T0)

    assert outcome.state == "cancelled"
    assert store.events == ["reserved", "released"]


def test_publication_failure_releases_the_resource_reservation(tmp_path: Path) -> None:
    store = _Store(publish_error=RuntimeError("publication broke"))
    outcome = run_source(_Adapter(result=_result(tmp_path)), _Config(), store, reference=T0)

    assert outcome.state == "failed"
    assert store.events == ["reserved", "released"]


# --- the quota ------------------------------------------------------------

def test_quota_the_failure_names_the_64_gib_cap_and_the_projected_size(tmp_path: Path) -> None:
    store = _Store(publish_error=QuotaExceeded("64 GiB hot storage cap would be exceeded: projected 70000000000 bytes against a cap of 68719476736 bytes"))

    outcome = run_source(_Adapter(result=_result(tmp_path)), _Config(), store, reference=T0)

    assert outcome.state == "failed"
    assert "64 GiB" in outcome.detail
    assert "projected" in outcome.detail
    assert outcome.published == 0


def test_quota_the_cap_is_64_gib_and_the_message_is_built_from_it(monkeypatch: pytest.MonkeyPatch) -> None:
    assert LOCAL_STORAGE_CAP_BYTES == 64 * 1024**3
    assert STORAGE_CAP_LABEL == "64 GiB"
    instance = ArtifactStore(StoreConfig(database_url="postgresql://x", endpoint="http://x", bucket="b", access_key="", secret_key=""))
    monkeypatch.setattr(instance, "used_bytes", lambda: LOCAL_STORAGE_CAP_BYTES)

    instance.check_projection(0)
    with pytest.raises(QuotaExceeded, match="64 GiB"):
        instance.check_projection(1)


def test_quota_no_visible_revision_is_evicted_to_make_room(monkeypatch: pytest.MonkeyPatch) -> None:
    """The projection refuses; it never plans a purge to satisfy itself."""
    events: list[str] = []
    instance = ArtifactStore(StoreConfig(database_url="postgresql://x", endpoint="http://x", bucket="b", access_key="", secret_key=""))
    monkeypatch.setattr(instance, "used_bytes", lambda: LOCAL_STORAGE_CAP_BYTES)
    monkeypatch.setattr(instance, "prune", lambda **_kwargs: events.append("prune"))
    monkeypatch.setattr(instance, "purge_outside_window", lambda *_a, **_k: events.append("purge"))

    with pytest.raises(QuotaExceeded):
        instance.check_projection(1)

    assert events == [], "there is nowhere to spill to and nothing is evicted"


# --- a run that never completes -------------------------------------------

def test_never_completes_is_failed_every_cycle_with_the_verdict_flags(tmp_path: Path) -> None:
    store = _Store()
    adapter = _Adapter(result=_result(tmp_path, complete=False, qc_passed=False, flags=["missing_field:temperature_2m"]))

    outcomes = [run_source(adapter, _Config(), store, reference=T0 + timedelta(hours=index)) for index in range(3)]

    assert [outcome.state for outcome in outcomes] == ["failed"] * 3
    assert all(outcome.published == 0 for outcome in outcomes)
    assert all("missing_field:temperature_2m" in outcome.detail for outcome in outcomes)
    assert all("previous revision stays visible" in outcome.detail for outcome in outcomes)


def test_never_completes_does_not_accumulate_staged_bytes_across_cycles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each attempt discards the previous attempt's staged rows and objects
    before it stages more, so projected usage does not grow across cycles."""
    events: list[tuple[str, Any]] = []
    payload = tmp_path / "surface.zarr.zip"
    payload.write_bytes(b"payload")
    artifact = Artifact(logical_name="surface", media_type="application/zarr+zip", payload_path=payload, provenance=declared_classes(["retrieved"]))
    result = RunResult(
        source_id="eccc-hrdps", provider_run_id="2026090212", run_time=T0, retrieved_at=T0,
        complete=False, qc_passed=False, artifacts=[artifact],
    )

    instance = ArtifactStore(StoreConfig(database_url="postgresql://x", endpoint="http://x", bucket="b", access_key="", secret_key=""))
    instance._client = _RecordingS3(events)
    monkeypatch.setattr(instance, "connection", _connection_factory(events))
    monkeypatch.setattr(instance, "used_bytes", lambda: (events.append(("used_bytes", None)), 0)[1])

    for _cycle in range(3):
        instance.stage_and_publish(result)

    kinds = [kind for kind, _ in events]
    assert kinds.count("discard_run_staging") == 3, "every attempt sweeps its predecessor's debris"
    assert kinds.count("publish_run") == 0, "an incomplete run is never published"
    for cycle in range(3):
        discard = [index for index, kind in enumerate(kinds) if kind == "discard_run_staging"][cycle]
        insert = [index for index, kind in enumerate(kinds) if kind == "insert_revision"][cycle]
        assert discard < insert, "staging debris goes before the next attempt reserves room"


class _RecordingS3:
    def __init__(self, events: list[tuple[str, Any]]) -> None:
        self._events = events

    def put_object(self, *, Bucket: str, Key: str, Body: Any, ContentType: str) -> None:  # noqa: N803
        self._events.append(("put_object", Key))
        Body.read()

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        self._events.append(("delete_object", Key))


def _connection_factory(events: list[tuple[str, Any]]):
    @contextmanager
    def connection() -> Iterator[Any]:
        yield _Connection(events)

    return connection


class _Connection:
    def __init__(self, events: list[tuple[str, Any]]) -> None:
        self._events = events

    def cursor(self) -> _Cursor:
        return _Cursor(self._events)

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class _Cursor:
    def __init__(self, events: list[tuple[str, Any]]) -> None:
        self._events = events
        self._kind = ""

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        text = " ".join(sql.split()).lower()
        for marker, name in (
            ("publish_run", "publish_run"),
            ("run_id = %s and state = 'staged'", "discard_run_staging"),
            ("insert into weather_experiment.model_runs", "record_run"),
            ("insert into weather_experiment.artifact_revisions", "insert_revision"),
            ("a.logical_name, a.sha256", "published_digests"),
        ):
            if marker in text:
                self._kind = name
                break
        else:
            self._kind = text.split(" ", 1)[0]
        self._events.append((self._kind, params))

    def fetchone(self) -> tuple[Any, ...]:
        return ("run-1",)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []
