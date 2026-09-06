"""The out-of-window QC gate, on the one shared window definition.

`artifact-ingestion` requires a run to fail QC when any valid time falls
outside the sliding window, requires the bounds to be read from the single
window definition rather than restated as literals, caps the reported flags so
the list stays readable, and refuses a run carrying no in-window step at all
rather than publishing it empty.

The judgement lives here rather than in :mod:`ingest.manifest` because the
bounds are now shared with the API and the store: keeping the comparison in
one small module is what stops a fourth copy of ``now-24h .. now+14d`` being
written the next time something needs it. :func:`ingest.manifest.validate_run`
calls straight into :func:`out_of_window_verdict`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from .window import WINDOW_BACK, WINDOW_FORWARD, sliding_window

UTC = timezone.utc

#: How many offending steps are named individually before the remainder is
#: summarised. Five is enough to see the shape of the problem - a run that
#: starts early, a run that runs long - without a flag list that no reader
#: scrolls to the end of.
MAX_REPORTED_OUT_OF_WINDOW = 5

#: The flag a run carrying no valid time inside the window is refused with. It
#: is deliberately not an ``out_of_window`` flag: those say some steps do not
#: belong, this says the run answers nothing the window asks about.
NO_STEP_IN_WINDOW = "no_step_in_window"

__all__ = [
    "MAX_REPORTED_OUT_OF_WINDOW",
    "NO_STEP_IN_WINDOW",
    "WINDOW_BACK",
    "WINDOW_FORWARD",
    "OutOfWindowVerdict",
    "bounds_nanoseconds",
    "out_of_window_verdict",
    "sliding_window",
    "to_nanoseconds",
]


def to_nanoseconds(moment: datetime) -> int:
    """Integer nanoseconds since the epoch for an instant.

    Frames are keyed and compared in nanoseconds throughout this change, so a
    resolution difference between a coordinate and a manifest can never read as
    a missing frame. A naive instant is read as UTC, which is what every
    dataset coordinate in this experiment is.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.astimezone(UTC).timestamp() * 1_000_000_000)


def _iso(nanoseconds: int) -> str:
    """A second-resolution ISO stamp for a flag. Nanoseconds exceed
    ``datetime``'s microsecond resolution, so the value is floored first."""
    seconds = nanoseconds // 1_000_000_000
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def bounds_nanoseconds(window: Any) -> tuple[int, int] | None:
    """The window's inclusive bounds in nanoseconds, or ``None`` if it has none.

    Accepts either a ``FetchWindow`` (anything with ``start`` and ``end``) or a
    bare instant, which is read through :func:`sliding_window` so a caller that
    only has ``now`` never has to restate the offsets.
    """
    if window is None:
        return None
    if isinstance(window, datetime):
        start, end = sliding_window(window)
    else:
        start = getattr(window, "start", None)
        end = getattr(window, "end", None)
    if start is None or end is None:
        return None
    return to_nanoseconds(start), to_nanoseconds(end)


@dataclass(frozen=True)
class OutOfWindowVerdict:
    """What the window gate found. ``flags`` are ``(flag, detail)`` pairs."""

    flags: tuple[tuple[str, str], ...]
    outside: tuple[int, ...]
    inside: tuple[int, ...]

    @property
    def refused(self) -> bool:
        return bool(self.flags)


def out_of_window_verdict(stamps: Iterable[int] | Sequence[int], window: Any) -> OutOfWindowVerdict:
    """Judge a run's valid times, in nanoseconds, against the shared window.

    Returns the flags to raise in declaration order: the first
    ``MAX_REPORTED_OUT_OF_WINDOW`` offending instants individually, then a
    ``+N_more`` remainder, then the no-in-window refusal. A run with no steps
    at all is not judged here - a dataset with no time coordinate is a
    different failure, reported by the caller as ``missing_axis``.
    """
    values = [int(value) for value in stamps]
    limits = bounds_nanoseconds(window)
    if limits is None or not values:
        return OutOfWindowVerdict((), (), tuple(sorted(set(values))))

    low, high = limits
    outside = sorted({value for value in values if value < low or value > high})
    inside = sorted({value for value in values if low <= value <= high})

    flags: list[tuple[str, str]] = []
    for value in outside[:MAX_REPORTED_OUT_OF_WINDOW]:
        iso = _iso(value)
        flags.append((f"out_of_window:{iso}", f"valid time {iso} falls outside the evidence window"))
    if len(outside) > MAX_REPORTED_OUT_OF_WINDOW:
        remaining = len(outside) - MAX_REPORTED_OUT_OF_WINDOW
        flags.append((f"out_of_window:+{remaining}_more", f"{remaining} further step(s) fall outside the evidence window"))
    if not inside:
        # Published empty, this run would consume a revision and the quota for
        # evidence no request inside the window can ever name.
        flags.append((
            NO_STEP_IN_WINDOW,
            f"no valid time falls inside {_iso(low)} .. {_iso(high)}; the run answers nothing the window asks about",
        ))
    return OutOfWindowVerdict(tuple(flags), tuple(outside), tuple(inside))
