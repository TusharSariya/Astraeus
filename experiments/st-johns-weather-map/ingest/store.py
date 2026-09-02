"""The real artifact store: MinIO objects plus PostgreSQL metadata.

``api.weather_api.storage`` models the intended semantics without I/O; this is
the same contract against live services. The ordering below is the whole point
of the design: upload the immutable object, record its true size and digest,
then let ``weather_experiment.publish_revision`` flip visibility atomically.
Publication logic lives in SQL and is never reimplemented here.
"""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence
from uuid import uuid4

from .contract import Artifact, RunResult
from .validate import to_nanoseconds
from .window import sliding_window

UTC = timezone.utc

#: The hot quota, from wayfinder ticket 20. There is no cold tier: reaching
#: this cap is a failure that fails closed, never a condition resolved by
#: evicting a visible revision or spilling bytes somewhere else.
LOCAL_STORAGE_CAP_BYTES = 64 * 1024**3
STORAGE_CAP_LABEL = "64 GiB"
STAGING_PREFIX = "staging"
PUBLISHED_PREFIX = "artifacts"
ABANDONED_STAGING_AGE = timedelta(hours=1)
#: Observations and nowcasts keep the full window's history rather than the
#: three-hour high-cadence floor the old retention rule used.
OBSERVATION_RETENTION = timedelta(hours=24)
KEEP_COMPLETE_RUNS = 2


class StoreUnavailable(RuntimeError):
    """PostgreSQL or MinIO could not be reached; callers must degrade, not guess."""


class QuotaExceeded(RuntimeError):
    """The 64 GiB hot cap would be exceeded. Fail the job, never evict a visible revision."""


class RunIdentityConflict(RuntimeError):
    """A second fetch of a published key produced different bytes.

    `artifact-ingestion` refuses this rather than replacing published evidence:
    an artifact a reader may already have cited must not change under the same
    ``(source_id, provider_run_id, valid_time)`` key. Both digests are named so
    the disagreement can be investigated upstream.
    """


class UndeclaredEvidenceClasses(ValueError):
    """An artifact reached staging without saying how its values came to exist.

    Every value carries exactly one evidence class and every artifact records
    the set it contains, so a data path can admit or exclude it by class
    rather than by matching its name. Staging is the one gate every artifact
    passes, so an undeclared artifact is refused here: the alternative is an
    artifact that publishes and is then isolated at read time, which loses the
    evidence silently and long after the mistake was made.
    """


def assert_classes_declared(artifact: Artifact) -> None:
    """Refuse an artifact whose provenance declares no evidence classes."""
    from .manifest import EVIDENCE_CLASSES  # noqa: PLC0415

    provenance = artifact.provenance or {}
    declared = provenance.get("evidence_classes")
    if not declared:
        raise UndeclaredEvidenceClasses(
            f"{artifact.logical_name}: provenance declares no evidence_classes; "
            "build it from RunManifest.as_manifest_block or ingest.manifest.declared_classes"
        )
    unknown = sorted({str(name) for name in declared if str(name) not in EVIDENCE_CLASSES})
    if unknown:
        raise UndeclaredEvidenceClasses(f"{artifact.logical_name}: {', '.join(unknown)} is not one of the six evidence classes")
    stated = {str(name) for name in (provenance.get("evidence_class_by_variable") or {}).values()}
    undeclared = sorted(stated - {str(name) for name in declared})
    if undeclared:
        raise UndeclaredEvidenceClasses(
            f"{artifact.logical_name}: evidence_class_mismatch - values carry {', '.join(undeclared)}, "
            "which the artifact does not declare"
        )


def _cap_label(cap_bytes: int) -> str:
    """The cap as a reader sees it, so an outcome can name it.

    `ingestion-worker-scheduling` requires the quota outcome to name the cap;
    formatting it from the configured value rather than a literal keeps the
    message honest if a deployment configures something else.
    """
    if cap_bytes % 1024**3 == 0:
        return f"{cap_bytes // 1024**3} GiB"
    return f"{cap_bytes / 1024**3:.2f} GiB"


def _parse_cap(value: str | None) -> int:
    if not value:
        return LOCAL_STORAGE_CAP_BYTES
    text = value.strip().upper()
    for suffix, factor in (("GIB", 1024**3), ("MIB", 1024**2), ("KIB", 1024), ("GB", 1000**3), ("B", 1)):
        if text.endswith(suffix):
            return int(float(text[: -len(suffix)]) * factor)
    return int(text)


@dataclass(frozen=True)
class StoreConfig:
    database_url: str
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    cap_bytes: int = LOCAL_STORAGE_CAP_BYTES

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> StoreConfig:
        env = dict(environ or os.environ)
        missing = [name for name in ("WEATHER_DATABASE_URL", "WEATHER_MINIO_ENDPOINT", "WEATHER_MINIO_BUCKET") if not env.get(name)]
        if missing:
            raise StoreUnavailable(f"missing store configuration: {', '.join(missing)}")
        return cls(
            database_url=env["WEATHER_DATABASE_URL"],
            endpoint=env["WEATHER_MINIO_ENDPOINT"],
            bucket=env["WEATHER_MINIO_BUCKET"],
            access_key=env.get("WEATHER_MINIO_ACCESS_KEY", ""),
            secret_key=env.get("WEATHER_MINIO_SECRET_KEY", ""),
            cap_bytes=_parse_cap(env.get("WEATHER_STORAGE_CAP")),
        )


@dataclass(frozen=True)
class StagedRevision:
    revision_id: str
    run_id: str
    logical_name: str
    object_key: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class CurrentArtifact:
    source_id: str
    logical_name: str
    revision_id: str
    object_key: str
    media_type: str
    byte_size: int
    provenance: dict[str, Any]
    published_at: datetime | None
    run_time: datetime | None
    retrieved_at: datetime | None
    provider_run_id: str
    native_crs: str | None


def sha256_of(path: Path, *, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ArtifactStore:
    """Stage, publish, prune and read artifacts. One instance per process."""

    def __init__(self, config: StoreConfig) -> None:
        self.config = config
        self._client: Any = None

    # --- connections -----------------------------------------------------
    @contextmanager
    def connection(self) -> Iterator[Any]:
        try:
            import psycopg  # noqa: PLC0415
        except ImportError as error:
            raise StoreUnavailable("psycopg is not installed") from error
        try:
            connection = psycopg.connect(self.config.database_url, autocommit=False)
        except Exception as error:
            raise StoreUnavailable(f"database unavailable: {error}") from error
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @property
    def s3(self) -> Any:
        if self._client is None:
            try:
                import boto3  # noqa: PLC0415
            except ImportError as error:
                raise StoreUnavailable("boto3 is not installed") from error
            self._client = boto3.client(
                "s3",
                endpoint_url=self.config.endpoint,
                aws_access_key_id=self.config.access_key or None,
                aws_secret_access_key=self.config.secret_key or None,
                region_name="us-east-1",
            )
        return self._client

    # --- metadata --------------------------------------------------------
    def upsert_source(self, *, source_id: str, producer: str, product: str, registry_status: str, adapter_version: str, metadata: dict[str, Any] | None = None) -> None:
        import json  # noqa: PLC0415

        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO weather_experiment.sources (source_id, producer, product, registry_status, adapter_version, native_metadata)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (source_id) DO UPDATE
                    SET producer = EXCLUDED.producer, product = EXCLUDED.product,
                        registry_status = EXCLUDED.registry_status,
                        adapter_version = EXCLUDED.adapter_version,
                        native_metadata = EXCLUDED.native_metadata,
                        updated_at = now()
                """,
                (source_id, producer, product, registry_status, adapter_version, json.dumps(metadata or {})),
            )

    def record_run(self, result: RunResult) -> str:
        """Insert or refresh the model run row and return its id."""
        import json  # noqa: PLC0415

        run_time = result.run_time or result.retrieved_at
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO weather_experiment.model_runs
                    (source_id, provider_run_id, run_time, retrieved_at, complete, qc_passed, native_crs, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (source_id, provider_run_id) DO UPDATE
                    SET retrieved_at = EXCLUDED.retrieved_at, complete = EXCLUDED.complete,
                        qc_passed = EXCLUDED.qc_passed, native_crs = EXCLUDED.native_crs,
                        metadata = EXCLUDED.metadata
                RETURNING run_id
                """,
                (result.source_id, result.provider_run_id, run_time, result.retrieved_at, result.complete, result.qc_passed, result.native_crs, json.dumps({"notes": result.notes})),
            )
            return str(cursor.fetchone()[0])

    # --- quota -----------------------------------------------------------
    def used_bytes(self) -> int:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT coalesce(sum(byte_size), 0) FROM weather_experiment.artifact_revisions WHERE state <> 'rejected'")
            return int(cursor.fetchone()[0])

    def check_projection(self, additional_bytes: int, *, replacing_bytes: int = 0) -> None:
        """Reserve room before downloading, as infra/STORAGE.md requires.

        The cap is never satisfied by planning to purge an in-window frame:
        the projection reads what is stored and refuses, and retention runs on
        its own rule. There is nowhere to spill to.
        """
        projected = self.used_bytes() - replacing_bytes + additional_bytes
        if projected > self.config.cap_bytes:
            raise QuotaExceeded(
                f"{_cap_label(self.config.cap_bytes)} hot storage cap would be exceeded: "
                f"projected {projected} bytes against a cap of {self.config.cap_bytes} bytes"
            )

    # --- staging and publication ----------------------------------------
    def stage(self, result: RunResult, artifact: Artifact, *, run_id: str | None = None) -> StagedRevision:
        """Upload the immutable object first, then record the staged revision.

        The row must carry the digest and size of an object that already
        exists, otherwise publication could expose a key with nothing behind it.
        """
        import json  # noqa: PLC0415

        assert_classes_declared(artifact)
        run = run_id or self.record_run(result)
        byte_size = artifact.byte_size
        self.check_projection(byte_size)
        digest = sha256_of(artifact.payload_path)
        object_key = f"{STAGING_PREFIX}/{result.source_id}/{result.provider_run_id}/{uuid4().hex}/{artifact.logical_name}"
        with artifact.payload_path.open("rb") as handle:
            self.s3.put_object(Bucket=self.config.bucket, Key=object_key, Body=handle, ContentType=artifact.media_type)
        provenance = {**artifact.provenance, "object_key": object_key, "sha256": digest, "media_type": artifact.media_type}
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO weather_experiment.artifact_revisions
                    (run_id, logical_name, object_key, media_type, byte_size, sha256, state, complete, qc_passed, provenance)
                VALUES (%s, %s, %s, %s, %s, %s, 'staged', %s, %s, %s::jsonb)
                RETURNING revision_id
                """,
                (run, artifact.logical_name, object_key, artifact.media_type, byte_size, digest, result.complete, result.qc_passed, json.dumps(provenance, default=str)),
            )
            revision_id = str(cursor.fetchone()[0])
        return StagedRevision(revision_id, run, artifact.logical_name, object_key, byte_size, digest)

    def publish(self, revision_id: str) -> None:
        """Flip one revision through the schema's own function, never in Python.

        Kept for single-artifact callers. A worker cycle goes through
        :meth:`publish_run` instead, so a run is never half visible.
        """
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT weather_experiment.publish_revision(%s)", (revision_id,))

    def publish_run(self, run_id: str) -> int:
        """Publish every staged artifact of one run in a single transaction.

        The function raises unless the parent ``model_runs`` row is itself
        complete and QC-passed, so a failed manifest validation leaves the prior
        ``current_artifacts`` pointer exactly where it was.
        """
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT weather_experiment.publish_run(%s)", (run_id,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def stage_and_publish(self, result: RunResult) -> list[StagedRevision]:
        """Record the run, stage every artifact, then publish the run as a unit.

        Publication is one ``publish_run`` call rather than a ``publish`` per
        revision: the previous ordering ran each flip in its own transaction, so
        a crash mid-run left some logical streams advanced and the rest behind.
        """
        if not result.artifacts:
            return []
        # A published key must never change under a second fetch. Checked
        # before the run row is touched, so a conflicting attempt neither
        # stages bytes nor moves the run's flags: the published artifact stays
        # visible and the source reports `run_identity_conflict`.
        self.assert_run_identity(result)
        run_id = self.record_run(result)
        # A retry of the same provider cycle reuses this run row, so a previous
        # attempt's staged revisions are still attached to it. publish_run walks
        # every staged revision of the run and raises if any one contradicts the
        # run's own flags, so an attempt that failed QC and left f/f rows behind
        # would block the later attempt that passes - permanently, because the
        # scheduler keeps retrying the same cycle. Re-staging supersedes the
        # earlier attempt, so its rows and objects go first.
        self.discard_staged(run_id)
        staged = [self.stage(result, artifact, run_id=run_id) for artifact in result.artifacts]
        if result.complete and result.qc_passed:
            self.publish_run(run_id)
        return staged

    def assert_run_identity(self, result: RunResult) -> None:
        """Refuse a byte-different re-fetch of an already-published key.

        Idempotency means a second fetch of `(source_id, provider_run_id,
        valid_time)` publishes nothing new. Identical bytes are the ordinary
        case and pass silently; different bytes mean the provider reissued a
        run under the same stamp, which `artifact-ingestion` refuses outright
        rather than replacing evidence a reader may already have cited.
        """
        published = self.published_digests(result.source_id, result.provider_run_id)
        if not published:
            return
        conflicts: list[str] = []
        for artifact in result.artifacts:
            existing = published.get(artifact.logical_name)
            if existing is None:
                continue
            digest = sha256_of(artifact.payload_path)
            if digest != existing:
                conflicts.append(f"{artifact.logical_name}: published {existing}, fetched {digest}")
        if conflicts:
            raise RunIdentityConflict(
                f"run_identity_conflict for {result.source_id} run {result.provider_run_id}: " + "; ".join(conflicts)
            )

    def discard_staged(self, run_id: str) -> int:
        """Drop every still-staged revision of one run, with its stored objects.

        Only ``staged`` rows are touched: a published revision is what
        ``current_artifacts`` points at, and removing one would retract evidence
        a reader may already have cited.
        """
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM weather_experiment.artifact_revisions "
                "WHERE run_id = %s AND state = 'staged' RETURNING object_key",
                (run_id,),
            )
            keys = [row[0] for row in cursor.fetchall()]
        self._delete_objects(keys)
        return len(keys)

    def restart(self) -> int:
        """Discard abandoned staging while preserving every current pointer."""
        cutoff = datetime.now(UTC) - ABANDONED_STAGING_AGE
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM weather_experiment.artifact_revisions WHERE state = 'staged' AND created_at < %s RETURNING object_key",
                (cutoff,),
            )
            keys = [row[0] for row in cursor.fetchall()]
        self._delete_objects(keys)
        return len(keys)

    # --- the restart-cache protocol --------------------------------------
    #
    # The three methods below are the seam this change fixes between the
    # ingest owner and the storage owner; it is recorded in the change's
    # design.md under "Seam". They are implemented over the existing schema so
    # the worker side does not have to wait for the retention migration.

    def sweep_abandoned_staging(self) -> int:
        """Discard staging debris left by an interrupted run. Named alias of
        :meth:`restart`, so the reconciliation reads as the three steps
        `ingestion-worker-scheduling` names rather than as one legacy verb."""
        return self.restart()

    def present_keys(self, source_id: str, provider_run_id: str) -> set[int]:
        """Valid times, in nanoseconds, already published under this run key.

        The answer is what a restart must not fetch again. It is read from the
        published revisions' own declared ``valid_times``: an artifact that
        declared none contributes nothing, so the worker fetches it rather
        than assuming a frame it cannot see is present. Guessing the other way
        would silently drop evidence.

        Raises :class:`StoreUnavailable` when the store cannot answer, because
        `artifact-ingestion` requires the source to fail rather than read an
        unknown cache state as an empty one.
        """
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.provenance
                  FROM weather_experiment.artifact_revisions a
                  JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
                 WHERE r.source_id = %s AND r.provider_run_id = %s AND a.state = 'published'
                """,
                (source_id, provider_run_id),
            )
            rows = cursor.fetchall()
        present: set[int] = set()
        for row in rows:
            present.update(_declared_valid_time_nanoseconds(row[0]))
        return present

    def published_digests(self, source_id: str, provider_run_id: str) -> dict[str, str]:
        """SHA-256 per logical name already published under this run key.

        A second fetch producing different bytes for one of these is a
        ``run_identity_conflict``: the published artifact stays visible.
        """
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.logical_name, a.sha256
                  FROM weather_experiment.artifact_revisions a
                  JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
                 WHERE r.source_id = %s AND r.provider_run_id = %s AND a.state = 'published'
                """,
                (source_id, provider_run_id),
            )
            return {str(row[0]): str(row[1]) for row in cursor.fetchall()}

    def purge_outside_window(self, now: datetime | None = None) -> int:
        """Purge every retained frame whose valid time left the window.

        The rules live in ``weather_experiment.purge_outside_window`` rather
        than here. There is one purge, not two: the database's version is the
        one publication commits with, it records each stream's last valid time
        before removing anything (which is what makes an aged-out report
        possible at all), and it deletes the ``current_artifacts`` pointer in
        the same transaction, which a row delete from here could not do
        without tripping the foreign key.

        Rows go before objects. The freed keys are queued by that transaction
        and drained here, so an object already gone does not abort the sweep
        and a sweep that dies mid-way resumes on the next call.
        """
        moment = now or datetime.now(UTC)
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT weather_experiment.purge_outside_window(%s)", (moment,))
            row = cursor.fetchone()
            purged = int(row[0]) if row else 0
            cursor.execute("SELECT weather_experiment.claim_purged_objects(%s)", (1000,))
            keys = [item[0] for item in cursor.fetchall()]
        self._delete_objects(keys)
        return purged

    # --- retention -------------------------------------------------------
    def prune(self, *, now: datetime | None = None) -> int:
        """Keep the latest and previous complete run per logical stream.

        The run-position fallback for revisions that declared no frame times,
        which :meth:`purge_outside_window` deliberately leaves alone rather
        than purging on a guess. Observations keep the full 24 hours the
        window reaches back; the old three-hour high-cadence floor is gone
        (infra/STORAGE.md).
        """
        moment = now or datetime.now(UTC)
        floor = moment - OBSERVATION_RETENTION
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH ranked AS (
                    SELECT a.revision_id, a.object_key, a.created_at,
                           row_number() OVER (PARTITION BY r.source_id, a.logical_name ORDER BY a.created_at DESC) AS position
                      FROM weather_experiment.artifact_revisions a
                      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
                     WHERE a.state = 'superseded'
                )
                DELETE FROM weather_experiment.artifact_revisions a
                 USING ranked
                 WHERE a.revision_id = ranked.revision_id
                   AND ranked.position >= %s
                   AND ranked.created_at < %s
                RETURNING a.object_key
                """,
                (KEEP_COMPLETE_RUNS, floor),
            )
            keys = [row[0] for row in cursor.fetchall()]
        self._delete_objects(keys)
        return len(keys)

    def _delete_objects(self, keys: Sequence[str]) -> None:
        for key in keys:
            try:
                self.s3.delete_object(Bucket=self.config.bucket, Key=key)
            except Exception:  # object already gone; the row is the record of truth
                continue

    # --- reads -----------------------------------------------------------
    def current_artifacts(self, *, source_ids: Sequence[str] | None = None) -> list[CurrentArtifact]:
        clause, params = "", []
        if source_ids is not None:
            clause = "WHERE c.source_id = ANY(%s)"
            params = [list(source_ids)]
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.source_id, c.logical_name, a.revision_id, a.object_key, a.media_type,
                       a.byte_size, a.provenance, a.published_at, r.run_time, r.retrieved_at,
                       r.provider_run_id, r.native_crs
                  FROM weather_experiment.current_artifacts c
                  JOIN weather_experiment.artifact_revisions a ON a.revision_id = c.revision_id
                  JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
                  {clause}
                 ORDER BY c.source_id, c.logical_name
                """,
                params,
            )
            rows = cursor.fetchall()
        return [
            CurrentArtifact(row[0], row[1], str(row[2]), row[3], row[4], int(row[5]), row[6] or {}, row[7], row[8], row[9], row[10], row[11])
            for row in rows
        ]

    def source_activity(self) -> dict[str, datetime]:
        """Most recent successful retrieval per source, for freshness reporting."""
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT source_id, max(retrieved_at) FROM weather_experiment.model_runs GROUP BY source_id")
            return {row[0]: row[1] for row in cursor.fetchall() if row[1] is not None}

    # --- jobs ------------------------------------------------------------
    def enqueue_job(self, source_ids: Sequence[str], *, detail: str = "refresh requested") -> dict[str, Any]:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO weather_experiment.jobs (state, requested_sources, detail) VALUES ('queued', %s, %s) RETURNING job_id, state, requested_sources, detail, created_at, updated_at",
                (list(source_ids), detail),
            )
            return _job_row(cursor.fetchone())

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT job_id, state, requested_sources, detail, created_at, updated_at FROM weather_experiment.jobs WHERE job_id = %s",
                (job_id,),
            )
            row = cursor.fetchone()
        return _job_row(row) if row else None

    def claim_job(self) -> dict[str, Any] | None:
        """Take the oldest queued job. One worker, so a simple lock suffices."""
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE weather_experiment.jobs SET state = 'running', started_at = now(), updated_at = now()
                 WHERE job_id = (
                    SELECT job_id FROM weather_experiment.jobs WHERE state = 'queued'
                     ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
                RETURNING job_id, state, requested_sources, detail, created_at, updated_at
                """
            )
            row = cursor.fetchone()
        return _job_row(row) if row else None

    def finish_job(self, job_id: str, *, state: str, detail: str) -> None:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE weather_experiment.jobs SET state = %s, detail = %s, finished_at = now(), updated_at = now() WHERE job_id = %s",
                (state, detail, job_id),
            )

    def record_outcome(self, source_id: str, *, state: str, detail: str) -> None:
        """Persist a cycle outcome as a terminal job row.

        Failure has to survive the process, and ``jobs`` is the only table the
        schema gives us for per-source run state.
        """
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO weather_experiment.jobs (state, requested_sources, detail, started_at, finished_at) VALUES (%s, %s, %s, now(), now())",
                (state, [source_id], detail),
            )


def _declared_valid_time_nanoseconds(provenance: Any) -> set[int]:
    """The instants a revision's provenance says it covers, in nanoseconds.

    An artifact that declares no ``valid_times`` returns the empty set, which
    every caller here reads as "the store cannot say", never as "it covers
    nothing".
    """
    block = provenance if isinstance(provenance, dict) else {}
    stamps: set[int] = set()
    for raw in block.get("valid_times") or ():
        moment = _parse_instant(raw)
        if moment is not None:
            stamps.add(to_nanoseconds(moment))
    return stamps


def _parse_instant(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    try:
        text = str(raw).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _job_row(row: Sequence[Any]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "state": str(row[1]),
        "source_ids": list(row[2] or []),
        "detail": row[3] or "",
        "created_at": row[4],
        "updated_at": row[5],
    }


def store_from_env(environ: dict[str, str] | None = None) -> ArtifactStore:
    return ArtifactStore(StoreConfig.from_env(environ))
