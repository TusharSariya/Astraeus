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

UTC = timezone.utc

LOCAL_STORAGE_CAP_BYTES = 25 * 1024**3
STAGING_PREFIX = "staging"
PUBLISHED_PREFIX = "artifacts"
ABANDONED_STAGING_AGE = timedelta(hours=1)
OBSERVATION_RETENTION = timedelta(hours=3)
KEEP_COMPLETE_RUNS = 2


class StoreUnavailable(RuntimeError):
    """PostgreSQL or MinIO could not be reached; callers must degrade, not guess."""


class QuotaExceeded(RuntimeError):
    """The 25 GiB local cap would be exceeded. Fail the job, never evict a visible revision."""


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
        """Reserve room before downloading, as infra/STORAGE.md requires."""
        projected = self.used_bytes() - replacing_bytes + additional_bytes
        if projected > self.config.cap_bytes:
            raise QuotaExceeded("25 GiB local storage cap would be exceeded")

    # --- staging and publication ----------------------------------------
    def stage(self, result: RunResult, artifact: Artifact, *, run_id: str | None = None) -> StagedRevision:
        """Upload the immutable object first, then record the staged revision.

        The row must carry the digest and size of an object that already
        exists, otherwise publication could expose a key with nothing behind it.
        """
        import json  # noqa: PLC0415

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

    # --- retention -------------------------------------------------------
    def prune(self, *, now: datetime | None = None) -> int:
        """Keep the latest and previous complete run per logical stream.

        High-cadence observations additionally keep three hours, matching the
        registry's caching policy and infra/STORAGE.md.
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
