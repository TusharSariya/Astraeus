"""Worker liveness must distinguish a live process from advancing ingestion.

The old heartbeat was a bare mtime written only between cycles: a long serial
cycle read as death, and a process that had silently stopped publishing read as
health. Both directions are tested here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from worker.runtime import (
    HEARTBEAT_MAX_AGE_SECONDS,
    STALL_CADENCE_MULTIPLIER,
    check_heartbeat,
    read_heartbeat,
    stalled_sources,
    write_heartbeat,
)

UTC = timezone.utc


def test_write_heartbeat_is_atomic_and_carries_source_progress(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    write_heartbeat(path, {"awc-metar-speci": {"cadence_seconds": 900, "last_success": None, "last_state": "pending"}})

    document = read_heartbeat(path)
    assert document is not None
    assert "beat" in document
    assert document["sources"]["awc-metar-speci"]["cadence_seconds"] == 900
    assert not list(tmp_path.glob("*.tmp")), "the temporary file must be renamed, never left behind"


def test_missing_or_corrupt_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    assert check_heartbeat(tmp_path / "absent") == 1
    corrupt = tmp_path / "corrupt"
    corrupt.write_text("not json", encoding="utf-8")
    assert read_heartbeat(corrupt) is None
    assert check_heartbeat(corrupt) == 1


def test_fresh_beat_with_no_source_history_is_healthy(tmp_path: Path) -> None:
    """A source that has never succeeded is reported, not fatal.

    A 404 endpoint is an ingestion fact for the API's source status. Failing
    liveness on it would restart-loop the container without fixing anything.
    """
    path = tmp_path / "beat"
    write_heartbeat(path, {"ecmwf-ifs": {"cadence_seconds": 300, "last_success": None, "last_state": "failed"}})
    assert check_heartbeat(path) == 0


def test_stale_beat_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    stale = datetime.now(UTC) - timedelta(seconds=HEARTBEAT_MAX_AGE_SECONDS + 60)
    path.write_text(json.dumps({"beat": stale.isoformat(), "sources": {}}), encoding="utf-8")
    assert check_heartbeat(path) == 1


def test_source_that_stopped_succeeding_is_a_stall(tmp_path: Path) -> None:
    cadence = 900
    reference = datetime.now(UTC)
    recent = (reference - timedelta(seconds=cadence)).isoformat()
    lapsed = (reference - timedelta(seconds=cadence * STALL_CADENCE_MULTIPLIER + 60)).isoformat()

    document = {
        "beat": reference.isoformat(),
        "sources": {
            "eccc-hrdps": {"cadence_seconds": cadence, "last_success": recent},
            "awc-metar-speci": {"cadence_seconds": cadence, "last_success": lapsed},
        },
    }
    assert stalled_sources(document, reference=reference) == ["awc-metar-speci"]

    path = tmp_path / "beat"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert check_heartbeat(path) == 1, "a live process that stopped publishing is not healthy"


def test_unparseable_last_success_does_not_crash_the_healthcheck(tmp_path: Path) -> None:
    document = {"beat": datetime.now(UTC).isoformat(), "sources": {"x": {"cadence_seconds": 300, "last_success": "yesterday"}}}
    assert stalled_sources(document) == []
