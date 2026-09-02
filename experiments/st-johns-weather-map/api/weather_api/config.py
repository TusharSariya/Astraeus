"""The one place the evidence window and the storage cap are defined.

Four things used to state the window separately: the API's request validation,
the timeline, the ingestion ``FetchWindow`` and the manifest out-of-window QC
gate. They drifted - the API served ``now-3h .. now+24h`` while the planning
tier reached 14 days - so a forecast frame that was legitimately served failed
the QC gate that was supposed to protect it. One definition, imported by all
four, is what stops that recurring.

Nothing here imports from ``weather_api``, ``ingest`` or ``registry``. It is
the seam the ingest worker reads, and a seam with dependencies is not one:
``ingest/window.py`` loads this file by path so the worker takes the window
definition without taking the API package or a circular import with it.

Decision of record: wayfinder ticket 20,
https://github.com/TusharSariya/Astraeus/issues/20.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc

#: How far back the sliding evidence window reaches. 24 hours rather than the
#: 3 the fixed window used, because the core horizon tier is "24 h back to
#: 24 h ahead" and a day of observations is what makes a forecast frame's own
#: run-to-run change legible without any verification score being computed.
WINDOW_BACK = timedelta(hours=24)

#: How far forward it reaches. 14 days is the planning tier and the furthest
#: any admitted source publishes (GFS, GEFS and GEPS at 384 h; the ECMWF
#: families at 360 h).
WINDOW_FORWARD = timedelta(days=14)

#: Hourly steps the window holds, both boundaries inclusive: 24 + 336 + 1.
WINDOW_STEPS = int((WINDOW_BACK + WINDOW_FORWARD).total_seconds() // 3600) + 1


def sliding_window(now: datetime) -> tuple[datetime, datetime]:
    """The evidence window at one instant, as UTC-aware ``(start, end)``.

    Both boundaries are inclusive. The window slides continuously with the
    clock it is given rather than being pinned to a run or a cycle, so a
    caller that wants a stable window truncates ``now`` before calling.

    A naive ``now`` is refused rather than assumed to be UTC: an offsetless
    instant cannot be placed on a timeline, and guessing is how a window ends
    up 3.5 hours wrong in Newfoundland.
    """
    if now.tzinfo is None:
        raise ValueError("sliding_window needs an offset-aware instant; a naive time cannot be placed in the window")
    moment = now.astimezone(UTC)
    return moment - WINDOW_BACK, moment + WINDOW_FORWARD


def in_window(moment: datetime, now: datetime) -> bool:
    """Whether one instant lies inside the window, boundaries included."""
    start, end = sliding_window(now)
    if moment.tzinfo is None:
        raise ValueError("an offsetless instant cannot be placed in the window")
    return start <= moment.astimezone(UTC) <= end


# --- storage ---------------------------------------------------------------
#: The hard hot-store quota, as MinIO's own unit suffix. Scenario C of
#: docs/research/wayfinder/size-probe-full-fields.md - core plus planning with
#: subsetted ensemble members - is about 44 GB with the two-run staging overlap
#: and container overhead; 64 GiB is the smallest round quota that holds it
#: with real headroom.
STORAGE_CAP = "64GiB"
STORAGE_CAP_BYTES = 64 * 1024**3

#: There is no cold, archive or overflow tier, and none is created at runtime.
#: Reaching the cap is a failure the worker reports, never a condition the
#: store resolves by moving or evicting bytes.
COLD_TIER = None

#: Complete runs retained per forecast source: the latest and the previous. A
#: third displaces the oldest at publication. Stated as a ceiling rather than
#: derived from free space, because retaining every run whose valid times still
#: fall inside a 14-day window would make the store a vintage archive by
#: accident.
KEEP_COMPLETE_RUNS = 2

#: Observations and nowcasts keep the full window back-edge, raising the old
#: three-hour high-cadence floor. It is the same number as WINDOW_BACK by
#: decision, not by coincidence: retention is the window.
OBSERVATION_RETENTION = WINDOW_BACK

#: The quality flag that says a value is absent because the store held the
#: frame and purged it. Never set without a recorded last valid time.
AGED_OUT_FLAG = "aged_out"
