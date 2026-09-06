from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ingest.adapters.awc import AWC_METAR_ARTIFACT_BYTES, AWC_METAR_DOCUMENT_BYTES, AWCMetarAdapter
from ingest.awc_metar_isolated import _decode
from ingest.contract import AdapterUnavailable, FetchWindow

UTC = timezone.utc
NOW = datetime(2026, 9, 6, 6, 30, tzinfo=UTC)
WINDOW = FetchWindow(NOW)


def row(stamp: int, **updates):
    value = {"icaoId": "CYYT", "obsTime": stamp, "temp": 12.0, "dewp": 9.0, "clouds": []}
    value.update(updates)
    return value


def payload(*rows):
    return json.dumps(rows, separators=(",", ":")).encode()


def test_strict_decoder_retains_every_row() -> None:
    rows = [row(int(WINDOW.start.timestamp()) + index * 60) for index in range(64)]
    decoded = _decode(payload(*rows), WINDOW)
    assert decoded == rows


@pytest.mark.parametrize("rows, message", [
    ([row(int(WINDOW.start.timestamp()) - 1)], "outside"),
    ([row(int(WINDOW.end.timestamp()) + 1)], "outside"),
    ([row(int(WINDOW.start.timestamp()), icaoId="KBOS")], "identity"),
    ([row(int(WINDOW.start.timestamp()), obsTime=float("nan"))], "obsTime"),
    ([row(int(WINDOW.start.timestamp())), row(int(WINDOW.start.timestamp()))], "duplicate"),
    ([row(int(WINDOW.start.timestamp()) + index) for index in range(65)], "64-row"),
])
def test_strict_decoder_refuses_whole_invalid_response(rows, message) -> None:
    with pytest.raises(AdapterUnavailable, match=message):
        _decode(payload(*rows), WINDOW)


def test_declared_limits_cover_enforced_channels(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(AWCMetarAdapter, "_require_target", staticmethod(lambda _path: None))
    monkeypatch.setattr(AWCMetarAdapter, "_isolated", staticmethod(
        lambda action, raw, window, destination: object()))
    bounds = AWCMetarAdapter().demand_operation_bounds()
    assert bounds.received_bytes == AWC_METAR_DOCUMENT_BYTES
    assert bounds.store_bytes == bounds.filesystem_bytes == AWC_METAR_ARTIFACT_BYTES
    assert bounds.margin_bytes == 8192
    # At peak the worker TemporaryDirectory and the child's private workspace
    # coexist with the child output. The atomic rename does not create a
    # second output inode, so the complete physical reservation is exact.
    assert bounds.filesystem_bytes + bounds.margin_bytes == 65536 + 4096 + 4096


def test_scheduled_metar_ingestion_is_disabled_before_discovery() -> None:
    with pytest.raises(AdapterUnavailable, match="selected-timestamp demand"):
        AWCMetarAdapter().operation_bounds(WINDOW)
