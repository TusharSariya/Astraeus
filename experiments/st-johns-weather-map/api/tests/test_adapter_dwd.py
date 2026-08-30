"""Unit tests for the DWD ICON Global adapter.

The adapter is deliberately non-publishing: ICON Global is served on its
native icosahedral mesh (``icon_global_icosahedral_single-level_*``), and this
stack has no regrid to a rectilinear lat/lon grid. Inventing one would produce
numbers that are not the value at the requested coordinate, so both
``discover`` and ``fetch`` refuse outright. These tests assert the refusal and
the reason.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ingest.adapters.dwd_icon import DWDICONAdapter, UNRESOLVED_REASON
from ingest.contract import AdapterUnavailable, FetchWindow

UTC = timezone.utc


def test_dwd_discover():
    adapter = DWDICONAdapter()
    window = FetchWindow(now=datetime(2026, 8, 29, 14, tzinfo=UTC))

    with pytest.raises(AdapterUnavailable) as excinfo:
        adapter.discover(window)

    assert str(excinfo.value) == UNRESOLVED_REASON
    assert "icosahedral" in str(excinfo.value)


def test_dwd_fetch():
    adapter = DWDICONAdapter()
    window = FetchWindow(now=datetime(2026, 8, 29, 14, tzinfo=UTC))

    with pytest.raises(AdapterUnavailable):
        adapter.discover(window)
    # fetch() is unreachable through discover(), but it must independently
    # refuse too -- an adapter must never publish from a hand-built candidate.
    with pytest.raises(AdapterUnavailable) as excinfo:
        adapter.fetch(candidate=None, window=window, workdir=None)  # type: ignore[arg-type]

    assert str(excinfo.value) == UNRESOLVED_REASON
