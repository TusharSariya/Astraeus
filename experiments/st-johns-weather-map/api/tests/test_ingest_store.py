"""Cap enforcement and the stage-then-publish ordering.

The store is exercised against recording doubles for MinIO and PostgreSQL: the
invariants under test are about the order of operations and the quota
arithmetic, neither of which needs a live service to be wrong.
"""

from __future__ import annotations

import dataclasses

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

import pytest

from ingest.contract import Artifact, RunResult
from ingest.manifest import declared_classes
from ingest.store import (
    LOCAL_STORAGE_CAP_BYTES,
    ArtifactStore,
    QuotaExceeded,
    StoreConfig,
    StoreUnavailable,
    UndeclaredEvidenceClasses,
    _parse_cap,
    sha256_of,
)

UTC = timezone.utc


class RecordingCursor:
    """Records every statement so ordering can be asserted, and returns ids."""

    def __init__(self, events: list[tuple[str, Any]], rows: list[tuple[Any, ...]]) -> None:
        self._events = events
        self._rows = rows
        self._counter = 0
        self._last_kind = ""

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self._counter += 1
        self._last_kind = _statement_kind(sql)
        self._events.append((self._last_kind, params))

    def fetchone(self) -> tuple[Any, ...]:
        if self._last_kind == "publish_run":
            return (self._counter,)
        return (f"id-{self._counter}",)

    def fetchall(self) -> list[tuple[Any, ...]]:
        # ``_rows`` is the canned answer for the delete-and-return statements
        # these tests assert on. The restart-cache reads have their own row
        # shapes and no test here seeds them, so they answer empty rather than
        # being handed object keys meant for a different query.
        if self._last_kind in _EMPTY_BY_DEFAULT:
            return []
        return list(self._rows)


#: Restart-cache reads: a test that wants rows from one of these builds its own
#: double, so the shared one must not improvise an answer of the wrong shape.
_EMPTY_BY_DEFAULT = frozenset({"published_digests", "present_keys", "window_revisions"})


def _statement_kind(sql: str) -> str:
    text = " ".join(sql.split()).lower()
    for marker, name in (
        ("publish_run", "publish_run"),
        ("publish_revision", "publish"),
        ("with ranked", "prune_rows"),
        ("state = 'staged' and created_at", "discard_staging"),
        ("run_id = %s and state = 'staged'", "discard_run_staging"),
        ("insert into weather_experiment.model_runs", "record_run"),
        ("insert into weather_experiment.artifact_revisions", "insert_revision"),
        ("sum(byte_size)", "used_bytes"),
        ("a.logical_name, a.sha256", "published_digests"),
        ("select a.provenance", "present_keys"),
        ("a.revision_id, a.object_key, a.provenance", "window_revisions"),
    ):
        if marker in text:
            return name
    return text.split(" ", 1)[0]


class RecordingS3:
    def __init__(self, events: list[tuple[str, Any]]) -> None:
        self._events = events
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: Any, ContentType: str) -> None:  # noqa: N803
        self._events.append(("put_object", Key))
        self.objects[Key] = Body.read()

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        self._events.append(("delete_object", Key))
        self.objects.pop(Key, None)


@pytest.fixture
def config() -> StoreConfig:
    return StoreConfig(database_url="postgresql://unused", endpoint="http://unused", bucket="weather-artifacts", access_key="k", secret_key="s")


@pytest.fixture
def store(config: StoreConfig, monkeypatch: pytest.MonkeyPatch) -> tuple[ArtifactStore, list[tuple[str, Any]]]:
    events: list[tuple[str, Any]] = []
    rows: list[tuple[Any, ...]] = []
    instance = ArtifactStore(config)
    instance._client = RecordingS3(events)
    instance.returned_rows = rows

    @contextmanager
    def connection() -> Iterator[Any]:
        yield _Connection(events, rows)

    monkeypatch.setattr(instance, "connection", connection)
    return instance, events


class _Connection:
    def __init__(self, events: list[tuple[str, Any]], rows: list[tuple[Any, ...]]) -> None:
        self._events = events
        self._rows = rows

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self._events, self._rows)

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def make_artifact(tmp_path: Path, *, name: str = "hrdps-surface", payload: bytes = b"zarr-bytes") -> Artifact:
    path = tmp_path / f"{name}.zarr.zip"
    path.write_bytes(payload)
    return Artifact(
        logical_name=name,
        media_type="application/zarr+zip",
        payload_path=path,
        # Staging refuses an artifact that does not say how its values came to
        # exist, so the declaration is part of what a staged artifact is.
        provenance={"native_resolution": "2.5 km", **declared_classes(["retrieved"])},
    )


def make_result(artifacts: list[Artifact], *, complete: bool = True, qc_passed: bool = True) -> RunResult:
    return RunResult(
        source_id="eccc-hrdps",
        provider_run_id="2026082912",
        run_time=datetime(2026, 8, 29, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 29, 12, 40, tzinfo=UTC),
        complete=complete,
        qc_passed=qc_passed,
        artifacts=artifacts,
        native_crs="EPSG:4326",
    )


# --- cap enforcement -----------------------------------------------------

def test_cap_parses_the_units_the_compose_file_uses():
    assert _parse_cap("64GiB") == LOCAL_STORAGE_CAP_BYTES
    assert _parse_cap("512MiB") == 512 * 1024**2
    assert _parse_cap("1GB") == 1000**3
    assert _parse_cap("4096") == 4096
    assert _parse_cap(None) == LOCAL_STORAGE_CAP_BYTES
    assert _parse_cap("") == LOCAL_STORAGE_CAP_BYTES


def test_room_is_reserved_before_download_and_the_cap_is_inclusive(store, monkeypatch):
    instance, _ = store
    monkeypatch.setattr(instance, "used_bytes", lambda: LOCAL_STORAGE_CAP_BYTES - 1024)
    instance.check_projection(1024)
    with pytest.raises(QuotaExceeded, match="64 GiB"):
        instance.check_projection(1025)


def test_replacing_an_existing_revision_frees_its_bytes_in_the_projection(store, monkeypatch):
    instance, _ = store
    monkeypatch.setattr(instance, "used_bytes", lambda: LOCAL_STORAGE_CAP_BYTES)
    with pytest.raises(QuotaExceeded):
        instance.check_projection(1)
    instance.check_projection(1, replacing_bytes=1)


def test_an_oversize_artifact_is_never_uploaded(store, monkeypatch, tmp_path):
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: LOCAL_STORAGE_CAP_BYTES)
    with pytest.raises(QuotaExceeded):
        instance.stage(make_result([]), make_artifact(tmp_path))
    assert [name for name, _ in events if name == "put_object"] == []
    assert [name for name, _ in events if name == "insert_revision"] == []


def test_the_cap_is_checked_before_the_object_is_uploaded(store, monkeypatch, tmp_path):
    instance, events = store
    order: list[str] = []
    monkeypatch.setattr(instance, "used_bytes", lambda: (order.append("used_bytes"), 0)[1])
    instance.stage(make_result([]), make_artifact(tmp_path))
    kinds = [name for name, _ in events]
    assert order == ["used_bytes"]
    assert kinds.index("put_object") < kinds.index("insert_revision")


# --- stage then publish --------------------------------------------------

def test_stage_uploads_the_object_before_recording_the_row_that_points_at_it(store, monkeypatch, tmp_path):
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: 0)
    artifact = make_artifact(tmp_path, payload=b"a normalized zarr payload")
    staged = instance.stage(make_result([artifact]), artifact)

    kinds = [name for name, _ in events]
    assert kinds.index("record_run") < kinds.index("put_object") < kinds.index("insert_revision")
    assert staged.object_key.startswith("staging/eccc-hrdps/2026082912/")
    assert staged.object_key.endswith("/hrdps-surface")
    assert staged.byte_size == artifact.byte_size == len(b"a normalized zarr payload")
    assert staged.sha256 == sha256_of(artifact.payload_path)
    assert instance._client.objects[staged.object_key] == b"a normalized zarr payload"


def test_an_artifact_that_declares_no_evidence_classes_is_never_staged(store, monkeypatch, tmp_path):
    """Staging is the one gate every artifact passes.

    An artifact that does not say how its values came to exist would publish
    and then be isolated at read time, which loses the evidence silently and
    long after the mistake was made. Refuse it where it is written instead.

    Spec-Refs: "Every value declares exactly one evidence class"
    (openspec/changes/evidence-classes-and-derived-here).
    """
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: 0)
    artifact = make_artifact(tmp_path)
    undeclared = dataclasses.replace(artifact, provenance={"native_resolution": "2.5 km"})

    with pytest.raises(UndeclaredEvidenceClasses, match="evidence_classes"):
        instance.stage(make_result([undeclared]), undeclared)
    assert [name for name, _ in events] == [], "nothing is uploaded or recorded for a refused artifact"


def test_an_artifact_whose_values_carry_an_undeclared_class_is_never_staged(store, monkeypatch, tmp_path):
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: 0)
    artifact = make_artifact(tmp_path)
    mismatched = dataclasses.replace(
        artifact,
        provenance={"evidence_classes": ["retrieved"], "evidence_class_by_variable": {"low_cloud": "generated_display"}},
    )

    with pytest.raises(UndeclaredEvidenceClasses, match="evidence_class_mismatch"):
        instance.stage(make_result([mismatched]), mismatched)


def test_an_evidence_class_outside_the_six_is_never_staged(store, monkeypatch, tmp_path):
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: 0)
    artifact = make_artifact(tmp_path)
    unknown = dataclasses.replace(artifact, provenance={"evidence_classes": ["consensus"]})

    with pytest.raises(UndeclaredEvidenceClasses, match="six evidence classes"):
        instance.stage(make_result([unknown]), unknown)


def test_publication_happens_only_after_every_artifact_is_staged(store, monkeypatch, tmp_path):
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: 0)
    artifacts = [make_artifact(tmp_path, name="surface"), make_artifact(tmp_path, name="pressure-levels")]
    staged = instance.stage_and_publish(make_result(artifacts))

    kinds = [name for name, _ in events]
    assert len(staged) == 2
    assert kinds.count("put_object") == 2
    assert kinds.count("insert_revision") == 2
    assert kinds.count("publish_run") == 1
    assert max(index for index, name in enumerate(kinds) if name == "insert_revision") < min(index for index, name in enumerate(kinds) if name == "publish_run")


@pytest.mark.parametrize(("complete", "qc_passed"), [(False, True), (True, False), (False, False)])
def test_an_incomplete_or_failed_run_is_staged_but_never_published(store, monkeypatch, tmp_path, complete, qc_passed):
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: 0)
    artifact = make_artifact(tmp_path)
    staged = instance.stage_and_publish(make_result([artifact], complete=complete, qc_passed=qc_passed))

    kinds = [name for name, _ in events]
    assert len(staged) == 1
    assert kinds.count("insert_revision") == 1
    assert "publish" not in kinds


def test_a_run_without_artifacts_touches_neither_object_store_nor_metadata(store, monkeypatch):
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: 0)
    assert instance.stage_and_publish(make_result([])) == []
    assert events == []


def test_publication_is_delegated_to_the_schema_function(store):
    instance, events = store
    instance.publish("revision-1")
    assert events == [("publish", ("revision-1",))]


def test_pruning_removes_the_rows_first_and_only_then_the_objects(store):
    instance, events = store
    instance._client.objects.update({"artifacts/old-a": b"", "artifacts/old-b": b""})
    instance.returned_rows.extend([("artifacts/old-a",), ("artifacts/old-b",)])

    assert instance.prune(now=datetime(2026, 8, 29, 12, tzinfo=UTC)) == 2
    kinds = [name for name, _ in events]
    assert kinds == ["prune_rows", "delete_object", "delete_object"]
    assert instance._client.objects == {}


def test_restart_discards_abandoned_staging_objects(store):
    instance, events = store
    instance.returned_rows.append(("staging/eccc-hrdps/2026082906/abc/surface",))
    assert instance.restart() == 1
    assert [name for name, _ in events] == ["discard_staging", "delete_object"]


def test_an_object_already_gone_does_not_abort_the_sweep(store):
    instance, events = store
    instance.returned_rows.extend([("artifacts/missing",), ("artifacts/present",)])

    def explode(*, Bucket: str, Key: str) -> None:  # noqa: N803
        events.append(("delete_object", Key))
        if Key == "artifacts/missing":
            raise RuntimeError("no such key")

    instance._client.delete_object = explode
    assert instance.prune() == 2
    assert [key for name, key in events if name == "delete_object"] == ["artifacts/missing", "artifacts/present"]


def test_missing_configuration_is_reported_rather_than_defaulted():
    with pytest.raises(StoreUnavailable, match="WEATHER_MINIO_BUCKET"):
        StoreConfig.from_env({"WEATHER_DATABASE_URL": "postgresql://x", "WEATHER_MINIO_ENDPOINT": "http://x"})
    config = StoreConfig.from_env(
        {"WEATHER_DATABASE_URL": "postgresql://x", "WEATHER_MINIO_ENDPOINT": "http://x", "WEATHER_MINIO_BUCKET": "b", "WEATHER_STORAGE_CAP": "64GiB"}
    )
    assert config.cap_bytes == LOCAL_STORAGE_CAP_BYTES


# --- re-staging a retried cycle ------------------------------------------
#
# A source that fails QC and is then retried lands on the same provider run id,
# so record_run returns the same run row and the failed attempt's staged
# revisions are still hanging off it. publish_run walks every staged revision of
# a run and raises if one contradicts the run's flags, so those leftovers used
# to block the attempt that finally passed - and block it permanently, since the
# scheduler keeps retrying the same cycle. Observed live on eccc-hrdps cycle
# 2026083006: two f/f revisions from earlier attempts sat in front of a t/t one.


def test_restaging_a_run_discards_the_previous_attempts_staged_revisions(store, monkeypatch, tmp_path):
    instance, events = store
    monkeypatch.setattr(instance, "used_bytes", lambda: 0)
    instance.returned_rows.append(("staging/eccc-hrdps/2026083006/old/surface",))
    instance.stage_and_publish(make_result([make_artifact(tmp_path, name="surface")]))

    kinds = [name for name, _ in events]
    assert kinds.count("discard_run_staging") == 1
    # The stale rows must be gone before the new revision is written, and the
    # object they pointed at must be swept with them.
    assert kinds.index("discard_run_staging") < kinds.index("insert_revision")
    assert ("delete_object", "staging/eccc-hrdps/2026083006/old/surface") in events
    assert kinds.count("publish_run") == 1


def test_discarding_a_runs_staging_never_touches_a_published_revision(store):
    """Only staged rows may be swept; a published one is cited evidence.

    ``_statement_kind`` only names this event ``discard_run_staging`` when the
    statement carries ``run_id = %s AND state = 'staged'``, so the classification
    is itself the assertion that the delete is scoped to one run's staging.
    """
    instance, events = store
    assert instance.discard_staged("some-run-id") == 0
    assert [name for name, _ in events] == ["discard_run_staging"]
    assert events[0][1] == ("some-run-id",)
