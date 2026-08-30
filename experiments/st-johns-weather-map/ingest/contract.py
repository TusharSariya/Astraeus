"""Shared ingestion contract.

Every adapter in this experiment implements :class:`Adapter`. The worker owns
discovery, fetching and publication; the API never reaches upstream. Types here
are the only coordination point between adapter families, so they must stay
stable while individual adapters are written independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

UTC = timezone.utc

# Avalon core matches api.weather_api.fixtures.AVALON_CORE_BOUNDS. The context
# box adds the Grand Banks and upstream Atlantic at coarser resolution.
AVALON_CORE_BOUNDS = {"south": 46.5, "west": -55.0, "north": 48.5, "east": -51.0}
ATLANTIC_CONTEXT_BOUNDS = {"south": 40.0, "west": -70.0, "north": 55.0, "east": -40.0}

# The location this experiment answers for.
ST_JOHNS = (47.5615, -52.7126)


@dataclass(frozen=True)
class FetchWindow:
    """The rolling evidence window: three hours back, twenty-four forward."""

    now: datetime
    back_hours: int = 3
    forward_hours: int = 24

    @property
    def start(self) -> datetime:
        return self.now - timedelta(hours=self.back_hours)

    @property
    def end(self) -> datetime:
        return self.now + timedelta(hours=self.forward_hours)

    def covers(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end


@dataclass(frozen=True)
class RunCandidate:
    """One provider run or observation batch that discovery found upstream."""

    provider_run_id: str
    run_time: datetime | None
    urls: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Artifact:
    """A normalized artifact staged locally, ready for MinIO upload.

    ``logical_name`` is stable per (source, product, variable) so that
    ``weather_experiment.current_artifacts`` can carry a single published
    pointer per logical stream.
    """

    logical_name: str
    media_type: str
    payload_path: Path
    provenance: dict[str, Any]

    @property
    def byte_size(self) -> int:
        return self.payload_path.stat().st_size


@dataclass(frozen=True)
class RunResult:
    """Outcome of fetching one candidate. ``complete`` and ``qc_passed`` gate
    publication in ``weather_experiment.publish_revision``."""

    source_id: str
    provider_run_id: str
    run_time: datetime | None
    retrieved_at: datetime
    complete: bool
    qc_passed: bool
    artifacts: list[Artifact] = field(default_factory=list)
    native_crs: str | None = None
    notes: str = ""


class AdapterUnavailable(RuntimeError):
    """Upstream is reachable but has nothing usable for this window.

    Raise this rather than returning empty results so the scheduler can record
    an explicit unavailable state instead of a silent gap.
    """


@runtime_checkable
class Adapter(Protocol):
    """Discovery and retrieval for exactly one registry source id."""

    source_id: str

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        """Return usable upstream runs, newest first. Must not download bulk."""

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        """Retrieve, subset and normalize one candidate into staged artifacts."""


MEDIA_ZARR = "application/zarr+zip"
MEDIA_PARQUET = "application/vnd.apache.parquet"
MEDIA_GEOJSON = "application/geo+json"
MEDIA_COG = "image/tiff; application=geotiff; profile=cloud-optimized"
