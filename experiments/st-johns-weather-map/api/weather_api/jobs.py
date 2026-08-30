from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from .models import Job, JobState


class FixtureJobStore:
    """Process-local refresh queue contract for a future single ingestion worker."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def enqueue(self, source_ids: list[str]) -> Job:
        now = datetime.now(timezone.utc)
        job = Job(id=str(uuid4()), state=JobState.QUEUED, created_at=now, updated_at=now, source_ids=source_ids, detail="fixture refresh queued; no operational ingestion performed")
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def advance_fixture(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            next_state = {JobState.QUEUED: JobState.RUNNING, JobState.RUNNING: JobState.SUCCEEDED}.get(job.state, job.state)
            updated = job.model_copy(update={"state": next_state, "updated_at": datetime.now(timezone.utc), "detail": "fixture refresh completed; no operational ingestion performed" if next_state == JobState.SUCCEEDED else "fixture refresh running"})
            self._jobs[job_id] = updated
            return updated


job_store = FixtureJobStore()
