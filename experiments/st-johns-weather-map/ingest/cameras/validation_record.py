"""The 30-day METAR validation a camera method needs before it is enabled.

Every camera derivation method enters the derivation method registry with
``enabled=False`` and stays there. What lifts that is not an edit to the
registry - registration refuses an enabled camera entry outright - but a
validation record: the method's output compared against CYYT METAR
visibility and cloud over at least :data:`MINIMUM_DAYS` days spanning
:data:`REQUIRED_CONDITIONS`, with no gap in the METAR the window is
measured against, and approved by the owner.

**This module flips nothing.** :func:`may_enable` reads a record and says
whether that record would justify enabling the method. It does not touch
``enabled`` on any registry entry, it does not write to the registry, and
importing it enables nothing. It is the gate a future change would call
before proposing an entry with ``enabled=True``, and until such a record
exists every camera-derived field is ``null`` naming
``awaiting_validation``.

A record that falls short is refused by :data:`INCOMPLETE_VALIDATION`
naming what is missing: the conditions not covered, the days short, the
METAR gaps by date, the comparisons never made, or the absent approval. The
refusal names them so the shortfall is fixable rather than merely denied. A
record covering 30 days of fog and rain with no snow and no night is
refused for the two conditions it lacks, not accepted on its day count.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ingest.derive.registry import CAMERA_METHODS

__all__ = [
    "CAMERA_METHODS",
    "INCOMPLETE_VALIDATION",
    "METAR_STATION",
    "MINIMUM_DAYS",
    "REQUIRED_CONDITIONS",
    "ValidationRecord",
    "may_enable",
]

#: The five conditions a validation window must span. Fog, rain and snow are
#: the weather a camera is most likely to get wrong; day and night are there
#: because a method validated only in daylight has been validated on half
#: the frames it will meet.
REQUIRED_CONDITIONS = frozenset({"day", "night", "fog", "rain", "snow"})

#: The least number of days a validation window may span, counted
#: inclusively from ``start`` to ``end``.
MINIMUM_DAYS = 30

#: The station the comparison is made against. One station, named here, so a
#: record cannot quietly be validated against a different one.
METAR_STATION = "CYYT"

#: Why a method stays disabled when a record exists but falls short.
INCOMPLETE_VALIDATION = "incomplete_validation"


@dataclass(frozen=True)
class ValidationRecord:
    """One method's comparison against CYYT METAR over a window.

    ``conditions`` are the members of :data:`REQUIRED_CONDITIONS` the window
    actually observed. ``metar_gaps`` are the inclusive date ranges within
    the window for which METAR visibility or cloud could not be retrieved;
    any gap means the window is not complete, however long the window is.
    ``comparisons`` is how many frame-to-METAR comparisons were made, and
    ``approved_by`` is the owner who signed the record off, ``None`` until
    they have.
    """

    method: str
    start: date
    end: date
    conditions: frozenset[str]
    metar_gaps: tuple[tuple[date, date], ...]
    comparisons: int
    approved_by: str | None

    @property
    def days(self) -> int:
        """The inclusive span of the window in days."""
        return (self.end - self.start).days + 1


def may_enable(record: ValidationRecord) -> str | None:
    """``None`` when this record would justify enabling its method.

    Returning ``None`` is a statement about the record, not an action: this
    function never sets ``enabled`` on a registry entry and never asks
    anything else to. A future change that proposes an enabled camera entry
    calls this first; nothing today does more than read.

    Every other answer is ``incomplete_validation:`` followed by what is
    missing, with all shortfalls named at once so a record is not fixed one
    refusal at a time.
    """
    if record.method not in CAMERA_METHODS:
        return (
            f"{INCOMPLETE_VALIDATION}:{record.method!r} is not a camera derivation method; "
            f"the camera methods are {', '.join(CAMERA_METHODS)}"
        )

    missing: list[str] = []

    days = record.days
    if days < MINIMUM_DAYS:
        missing.append(
            f"the window spans {days} days, {MINIMUM_DAYS - days} short of the {MINIMUM_DAYS} required"
        )

    absent = REQUIRED_CONDITIONS - record.conditions
    if absent:
        missing.append(f"conditions not covered: {', '.join(sorted(absent))}")

    if record.metar_gaps:
        gaps = "; ".join(f"{start.isoformat()} to {end.isoformat()}" for start, end in record.metar_gaps)
        missing.append(f"{METAR_STATION} METAR gap in the window: {gaps}")

    if record.comparisons <= 0:
        missing.append(f"no comparison against {METAR_STATION} METAR was made")

    if not record.approved_by:
        missing.append("no owner approval is recorded")

    if not missing:
        return None
    return f"{INCOMPLETE_VALIDATION}:{'; '.join(missing)}"
