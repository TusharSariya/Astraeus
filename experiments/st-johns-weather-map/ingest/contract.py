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

from .window import WINDOW_BACK, WINDOW_FORWARD

UTC = timezone.utc

# Avalon core matches api.weather_api.fixtures.AVALON_CORE_BOUNDS. The context
# box adds the Grand Banks and upstream Atlantic at coarser resolution.
AVALON_CORE_BOUNDS = {"south": 46.5, "west": -55.0, "north": 48.5, "east": -51.0}
ATLANTIC_CONTEXT_BOUNDS = {"south": 40.0, "west": -70.0, "north": 55.0, "east": -40.0}

# The evidence box every gridded source is subset to on ingest (CONTEXT.md,
# storage window decision #20): 45.0 to 50.5 N, 58.0 to 46.0 W. Stated once
# here so an adapter that crops to it names the same numbers the registry's
# coverage checks and ``weather_api.sites.EVIDENCE_BOX`` name.
EVIDENCE_BOX_BOUNDS = {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}

# The location this experiment answers for.
ST_JOHNS = (47.5615, -52.7126)


@dataclass(frozen=True)
class FetchWindow:
    """The sliding evidence window: 24 hours back, 14 days forward.

    The offsets are not literals here. `evidence-window-timeline` requires the
    same window to bound the API's accepted ``valid_time``, this
    ``FetchWindow``, the manifest QC gate and what the store retains, defined
    in exactly one place; that place is ``weather_api.config``, re-exported by
    ``ingest.window``. ``back_hours`` and ``forward_hours`` stay as overrides
    for a caller that deliberately wants a narrower window in a test.
    """

    now: datetime
    back_hours: float = WINDOW_BACK.total_seconds() / 3600.0
    forward_hours: float = WINDOW_FORWARD.total_seconds() / 3600.0

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
class ResourceBounds:
    """Conservative allocations required by one complete fetch operation.

    These are admission bounds, not observations from a completed fetch.  An
    adapter derives them from discovery metadata and measured source evidence
    before the worker permits payload retrieval.
    """

    store_bytes: int
    filesystem_bytes: int
    margin_bytes: int
    received_bytes: int

    def validate(self) -> None:
        for name, value in (
            ("store_bytes", self.store_bytes),
            ("filesystem_bytes", self.filesystem_bytes),
            ("margin_bytes", self.margin_bytes),
            ("received_bytes", self.received_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"resource bound {name} must be a non-negative integer")
        if self.store_bytes == 0 or self.filesystem_bytes == 0 or self.received_bytes == 0:
            raise ValueError("store, filesystem and received-byte bounds must be measured and non-zero")


@dataclass(frozen=True)
class DiscoveryBounds:
    """Measured bytes permitted while enumerating candidate metadata."""

    received_bytes: int

    def validate(self) -> None:
        if isinstance(self.received_bytes, bool) or not isinstance(self.received_bytes, int) or self.received_bytes <= 0:
            raise ValueError("discovery received-byte bound must be a positive integer")


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

    def discovery_bounds(self, window: FetchWindow) -> DiscoveryBounds:
        """Return a measured finite metadata bound before discovery requests."""

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        """Return usable upstream runs, newest first. Must not download bulk."""

    def resource_bounds(self, candidate: RunCandidate, window: FetchWindow) -> ResourceBounds:
        """Return measured complete-operation bounds without reading payloads."""

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        """Retrieve, subset and normalize one candidate into staged artifacts."""


MEDIA_ZARR = "application/zarr+zip"
MEDIA_PARQUET = "application/vnd.apache.parquet"
MEDIA_GEOJSON = "application/geo+json"
MEDIA_COG = "image/tiff; application=geotiff; profile=cloud-optimized"
