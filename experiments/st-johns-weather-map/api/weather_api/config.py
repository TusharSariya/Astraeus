"""The single sliding evidence window.

Defined once so the API's accepted ``valid_time``, the ingestion
``FetchWindow``, the manifest out-of-window QC gate and what the store retains
cannot drift apart. `evidence-window-timeline` requires exactly one definition;
this module is it, and both the API and ``ingest`` read it from here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

WINDOW_BACK = timedelta(hours=24)
WINDOW_FORWARD = timedelta(days=14)


def sliding_window(now: datetime) -> tuple[datetime, datetime]:
    """The inclusive window bounds around ``now``, which must be UTC-aware."""
    return (now - WINDOW_BACK, now + WINDOW_FORWARD)
