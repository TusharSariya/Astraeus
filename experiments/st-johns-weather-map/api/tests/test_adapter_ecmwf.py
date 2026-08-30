"""Unit tests for the ECMWF IFS Open Data adapter.

The adapter is deliberately non-publishing: ``data.ecmwf.int/forecasts/``
retains only the last four dates and the current date 404s, so the dated
cycle path the adapter would need cannot address a run in the window. Both
``discover`` and ``fetch`` refuse rather than guess a cycle, so these tests
assert the refusal and the reason, not a returned candidate. The ``.index``
parser is untouched production logic and is still exercised directly.
"""

from __future__ import annotations

import pytest

from ingest.adapters.ecmwf_opendata import (
    ECMWFIFSAdapter,
    UNRESOLVED_REASON,
    parse_ecmwf_index,
)
from ingest.contract import AdapterUnavailable, FetchWindow
from datetime import datetime, timezone

UTC = timezone.utc

SAMPLE_INDEX_LINES = """\
{"domain": "g", "levtype": "sfc", "date": "20260829", "time": "1200", "step": "0", "param": "2t", "_offset": 0, "_length": 50000}
{"domain": "g", "levtype": "sfc", "date": "20260829", "time": "1200", "step": "0", "param": "2d", "_offset": 50000, "_length": 50000}
{"domain": "g", "levtype": "sfc", "date": "20260829", "time": "1200", "step": "0", "param": "10u", "_offset": 100000, "_length": 50000}
{"domain": "g", "levtype": "sfc", "date": "20260829", "time": "1200", "step": "0", "param": "10v", "_offset": 150000, "_length": 50000}
{"domain": "g", "levtype": "sfc", "date": "20260829", "time": "1200", "step": "0", "param": "msl", "_offset": 200000, "_length": 50000}
{"domain": "g", "levtype": "pl", "date": "20260829", "time": "1200", "step": "0", "param": "gh", "_offset": 250000, "_length": 50000}
"""


def test_parse_ecmwf_index():
    target_params = {"2t", "2d", "msl"}
    ranges = parse_ecmwf_index(SAMPLE_INDEX_LINES, target_params)
    assert len(ranges) == 3
    assert ranges[0] == (0, 49999)
    assert ranges[1] == (50000, 99999)
    assert ranges[2] == (200000, 249999)


def test_ecmwf_discover():
    adapter = ECMWFIFSAdapter()
    window = FetchWindow(now=datetime(2026, 8, 29, 14, tzinfo=UTC))

    with pytest.raises(AdapterUnavailable) as excinfo:
        adapter.discover(window)

    assert str(excinfo.value) == UNRESOLVED_REASON
    assert "data.ecmwf.int/forecasts" in str(excinfo.value)
    assert "404" in str(excinfo.value)


def test_ecmwf_fetch():
    adapter = ECMWFIFSAdapter()
    window = FetchWindow(now=datetime(2026, 8, 29, 14, tzinfo=UTC))

    with pytest.raises(AdapterUnavailable) as excinfo:
        adapter.discover(window)
    # fetch() is unreachable through discover(), but it must independently
    # refuse too -- an adapter must never publish from a hand-built candidate.
    with pytest.raises(AdapterUnavailable) as fetch_excinfo:
        adapter.fetch(candidate=None, window=window, workdir=None)  # type: ignore[arg-type]

    assert str(fetch_excinfo.value) == UNRESOLVED_REASON
