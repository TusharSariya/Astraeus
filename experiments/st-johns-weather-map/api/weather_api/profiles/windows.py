"""Resolve a profile's window rule from registered DE442 Sun geometry.

A window is when an activity is possible, and every profile in this
deployment writes its window as a statement about the Sun's altitude:
astronomical night, dark hours, a margin either side of sunrise and sunset,
or any run of daylight long enough to go running in. The temptation, every
time, is to write that in wall-clock hours instead - "dark is 22:00 to 05:00"
- which is a second solar model, unregistered, unversioned, wrong twice a
year and wrong by a different amount at every latitude. This module exists so
that temptation has somewhere to fail loudly: :func:`validate_window_rule`
refuses a wall-clock parameter by name, and :func:`resolve_window` has no way
to invent an altitude.

It has no way because it computes none. Nothing here imports Skyfield, opens
the kernel or evaluates an ephemeris. Geometry arrives as
:class:`GeometrySample` values that somebody else derived through the one
registered entry, ``de442_sun_moon_geometry``. This module asks
:mod:`ingest.derive.registry` whether that entry may produce a value at all,
reads the altitude thresholds from :mod:`weather_api.astronomy` so the
horizon and twilight numbers are stated once in the deployment, and does
arithmetic on the samples it was handed.

When the geometry is not there - the entry is disabled, or a sample's
``sun_altitude`` is ``None`` - the answer is an unresolved window naming what
is absent, with no intervals. Never a guessed window, never an empty window
presented as "no opportunity": the two are different answers and a reader is
entitled to know which one they are looking at.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# ``ingest`` ships beside ``api`` in the repository and in both images. The
# app adds the same path at runtime; adding it here keeps this module
# importable from a bare interpreter as well.
_EXPERIMENT_ROOT = Path(__file__).resolve().parents[3]
if str(_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENT_ROOT))

from ingest.derive.registry import (  # noqa: E402
    DE442_GEOMETRY,
    Refusal,
    get as registry_get,
    resolve as registry_resolve,
)

from ..astronomy import ASTRONOMICAL_DEG, NAUTICAL_DEG, SUN_HORIZON_DEG  # noqa: E402
from ..ephemeris import EPHEMERIS_SHA256  # noqa: E402

#: The one geometry field every window rule here reads. Named as a constant
#: because it is what :attr:`WindowResolution.unresolved` reports when it is
#: absent, and a caller greps for that string.
SUN_ALTITUDE = "sun_altitude"

def _geometry_outputs() -> tuple[str, ...]:
    """The outputs of the registered DE442 entry, read from the entry itself.

    Read rather than restated so this module cannot drift from the registry
    it defers to. Empty if the entry has gone missing, in which case
    :func:`validate_window_rule` refuses the entry name anyway.
    """
    entry = registry_get(DE442_GEOMETRY)
    if entry is None:
        return ()
    return tuple(item.field for item in entry.outputs)


#: The window rules and the parameters each takes. Mirrors
#: ``registry/profile_audit.WINDOW_RULES``: the auditor checks the file on
#: disk, this checks the rule in memory, and both must refuse the same set.
WINDOW_RULES: dict[str, tuple[str, ...]] = {
    "any_window_within_24h": ("length_hours", "daylight_only"),
    "astronomical_night": (),
    "dark_hours": (),
    "sunrise_sunset_margin": ("margin_minutes",),
}

#: Parameter names that make a rule a wall-clock rule however astronomical
#: its ``rule`` field looks. Refused by name so the message says which key.
CLOCK_PARAMS: tuple[str, ...] = (
    "local_time",
    "wall_clock",
    "start_hour",
    "end_hour",
    "hours",
)

#: The horizon a sunrise and a sunset cross: the standard refraction-inclusive
#: solar horizon, taken from :mod:`weather_api.astronomy` rather than restated.
SUNRISE_SUNSET_DEG = SUN_HORIZON_DEG

#: How far ahead ``any_window_within_24h`` looks.
HORIZON = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class WindowRule:
    """A profile's ``window`` block, parsed and frozen.

    ``params`` stays the mapping the profile declared rather than being
    flattened into named fields: each rule takes a different set, and
    :func:`validate_window_rule` is what says whether this one took the right
    ones.
    """

    rule: str
    geometry_entry: str
    geometry_fields: tuple[str, ...]
    params: Mapping[str, Any]

    @classmethod
    def from_profile(cls, mapping: Mapping[str, Any]) -> "WindowRule":
        """Build a rule from a profile's ``window`` block.

        Accepts the whole profile mapping as well, for the common case of
        handing this a loaded profile: a mapping carrying a ``window`` key is
        read one level down. Shape is checked here only far enough to build
        the object; whether it is a legal rule is
        :func:`validate_window_rule`, which returns messages rather than
        raising, so a caller can report every fault of a profile at once.
        """
        if not isinstance(mapping, Mapping):
            raise TypeError(f"window rule must be a mapping, got {type(mapping).__name__}")
        block: Any = mapping
        if "rule" not in mapping and isinstance(mapping.get("window"), Mapping):
            block = mapping["window"]
        fields = block.get("geometry_fields") or ()
        if isinstance(fields, str):
            fields = (fields,)
        params = block.get("params") or {}
        if not isinstance(params, Mapping):
            raise TypeError(f"window params must be a mapping, got {type(params).__name__}")
        return cls(
            rule=block.get("rule"),
            geometry_entry=block.get("geometry_entry"),
            geometry_fields=tuple(str(name) for name in fields),
            params=dict(params),
        )


@dataclass(frozen=True, slots=True)
class GeometrySample:
    """One instant of Sun geometry, derived elsewhere through the registry.

    ``sun_altitude`` is nullable on purpose. A sample whose altitude is
    ``None`` is the shape a disabled or failed derivation takes on the way
    here, and it must make the window unresolved rather than being silently
    dropped from a run of daylight.
    """

    at: datetime
    sun_altitude: float | None = None


@dataclass(frozen=True, slots=True)
class WindowResolution:
    """The intervals a window rule resolves to, or why it did not resolve.

    ``intervals`` is empty whenever ``unresolved`` is set, and the two must be
    read together: an empty interval list with ``unresolved is None`` means
    the geometry was present and offered no window, which is a different
    answer from not knowing.
    """

    intervals: list[tuple[datetime, datetime]]
    unresolved: str | None
    provenance: dict[str, Any]

    @property
    def resolved(self) -> bool:
        return self.unresolved is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "intervals": [
                {"start": start.isoformat(), "end": end.isoformat()}
                for start, end in self.intervals
            ],
            "unresolved": self.unresolved,
            "provenance": dict(self.provenance),
        }


def geometry_provenance() -> dict[str, Any]:
    """What every window carries about where its geometry came from.

    The version is read from the registry entry rather than written here, so
    a re-versioned ephemeris entry re-versions the windows it produced without
    anybody remembering to edit this file.
    """
    entry = registry_get(DE442_GEOMETRY)
    return {
        "derivation": DE442_GEOMETRY,
        "derivation_version": entry.version if entry is not None else None,
        "kernel_sha256": EPHEMERIS_SHA256,
        "evidence_class": "derived_here",
    }


def validate_window_rule(rule: WindowRule, *, profile_id: str) -> list[str]:
    """Everything wrong with this window rule, as messages naming the profile.

    Returns messages rather than raising so a profile's faults can be reported
    together. Every message starts with the profile id and names the rule, so
    a failing line reads as "which profile, which rule" without opening a
    file.
    """
    errors: list[str] = []
    name = rule.rule

    if rule.geometry_entry != DE442_GEOMETRY:
        errors.append(
            f"{profile_id}: {name!r}: names geometry entry {rule.geometry_entry!r}; the only "
            f"registered ephemeris entry is {DE442_GEOMETRY} and a window may not be written "
            "in another solar model"
        )

    outputs = _geometry_outputs()
    for field in rule.geometry_fields:
        if field not in outputs:
            errors.append(
                f"{profile_id}: {name!r}: geometry field {field!r} is not an output of "
                f"{DE442_GEOMETRY} ({', '.join(outputs) or 'none registered'})"
            )

    clock = sorted(key for key in rule.params if str(key) in CLOCK_PARAMS)
    if clock:
        errors.append(
            f"{profile_id}: {name!r}: declares the wall-clock parameter "
            f"{', '.join(clock)}; a window is an astronomical quantity computed by "
            f"{DE442_GEOMETRY} and may not be written in local time"
        )

    if name not in WINDOW_RULES:
        errors.append(
            f"{profile_id}: {name!r}: is not one of the declared window rules "
            f"({', '.join(sorted(WINDOW_RULES))})"
        )
        return errors

    allowed = set(WINDOW_RULES[name])
    for key in sorted(set(map(str, rule.params)) - allowed - set(clock)):
        errors.append(f"{profile_id}: {name!r}: window rule takes no parameter {key!r}")
    for key in sorted(allowed - set(map(str, rule.params))):
        errors.append(f"{profile_id}: {name!r}: window rule requires the parameter {key!r}")
    return errors


def resolve_window(
    rule: WindowRule,
    samples: Sequence[GeometrySample],
    *,
    now: datetime,
    reader_disabled: Iterable[str] = (),
) -> WindowResolution:
    """The intervals this rule picks out of these samples, or why it cannot.

    Two ways to fail, both of them explicit and neither of them a guess:

    * the registered geometry entry may not produce a value now (disabled in
      the registry, refused by the deployment switch, or switched off by this
      reader), which is ``geometry_entry_disabled:<refusal code>``;
    * the geometry itself is absent - no samples, or a sample the rule needs
      whose ``sun_altitude`` is ``None`` - which is ``sun_altitude``.

    In both cases ``intervals`` is empty. Nothing here falls back to a clock.
    """
    provenance = geometry_provenance()

    refusal: Refusal | None = registry_resolve(DE442_GEOMETRY, reader_disabled=reader_disabled)
    if refusal is not None:
        return WindowResolution(
            intervals=[],
            unresolved=f"geometry_entry_disabled:{refusal.code}",
            provenance=provenance,
        )

    needed = _needed_samples(rule, samples, now=now)
    if not needed or any(sample.sun_altitude is None for sample in needed):
        return WindowResolution(intervals=[], unresolved=SUN_ALTITUDE, provenance=provenance)

    if rule.rule == "any_window_within_24h":
        intervals = _any_window_within_24h(rule, needed)
    elif rule.rule == "astronomical_night":
        intervals = _runs_below(needed, ASTRONOMICAL_DEG)
    elif rule.rule == "dark_hours":
        intervals = _runs_below(needed, NAUTICAL_DEG)
    elif rule.rule == "sunrise_sunset_margin":
        intervals = _sunrise_sunset_margin(rule, needed)
    else:
        return WindowResolution(
            intervals=[],
            unresolved=f"unknown_window_rule:{rule.rule}",
            provenance=provenance,
        )

    return WindowResolution(intervals=intervals, unresolved=None, provenance=provenance)


def _needed_samples(
    rule: WindowRule, samples: Sequence[GeometrySample], *, now: datetime
) -> list[GeometrySample]:
    """The samples this rule actually reads, in time order.

    ``any_window_within_24h`` reads only the next 24 hours, so a ``None``
    altitude three days out does not make today's window unresolved. Every
    other rule reads whatever it was handed.
    """
    ordered = sorted(samples, key=lambda sample: sample.at)
    if rule.rule == "any_window_within_24h":
        end = now + HORIZON
        return [sample for sample in ordered if now <= sample.at <= end]
    return ordered


def _runs(
    samples: Sequence[GeometrySample], predicate
) -> list[tuple[datetime, datetime]]:
    """Every maximal run of consecutive samples satisfying ``predicate``.

    A run of one sample has zero length and is still a run: the caller decides
    whether a zero-length interval is long enough, because only the caller
    knows what the rule asked for.
    """
    intervals: list[tuple[datetime, datetime]] = []
    start: datetime | None = None
    previous: datetime | None = None
    for sample in samples:
        if predicate(sample):
            if start is None:
                start = sample.at
            previous = sample.at
        elif start is not None and previous is not None:
            intervals.append((start, previous))
            start = None
            previous = None
    if start is not None and previous is not None:
        intervals.append((start, previous))
    return intervals


def _runs_below(
    samples: Sequence[GeometrySample], altitude_deg: float
) -> list[tuple[datetime, datetime]]:
    """Maximal runs with the Sun below a declared altitude."""
    return _runs(samples, lambda sample: float(sample.sun_altitude) < altitude_deg)


def _any_window_within_24h(
    rule: WindowRule, samples: Sequence[GeometrySample]
) -> list[tuple[datetime, datetime]]:
    """Runs inside the next 24 h that are long enough, optionally daylight.

    ``daylight_only`` is the profile's word for "above the refraction-inclusive
    horizon", which is the same number the twilight code uses, taken from the
    same constant.
    """
    length_hours = float(rule.params.get("length_hours", 0) or 0)
    daylight_only = bool(rule.params.get("daylight_only", False))
    if daylight_only:
        runs = _runs(samples, lambda sample: float(sample.sun_altitude) > SUN_HORIZON_DEG)
    else:
        runs = _runs(samples, lambda _: True)
    minimum = timedelta(hours=length_hours)
    return [(start, end) for start, end in runs if end - start >= minimum]


def _sunrise_sunset_margin(
    rule: WindowRule, samples: Sequence[GeometrySample]
) -> list[tuple[datetime, datetime]]:
    """A margin either side of every crossing of the solar horizon.

    The crossing time is interpolated linearly between the two samples that
    bracket it. That is an approximation of an approximation - the samples are
    already a discretisation of a continuous altitude - and it is stated here
    rather than hidden: at the sample spacings these profiles use (minutes),
    the error is well under the margins they declare (tens of minutes).
    """
    margin = timedelta(minutes=float(rule.params.get("margin_minutes", 0) or 0))
    crossings: list[datetime] = []
    # A sample sitting exactly on the horizon is the crossing itself, and is
    # taken first so the pairwise walk does not report it twice, once from
    # each side.
    for sample in samples:
        if float(sample.sun_altitude) - SUNRISE_SUNSET_DEG == 0.0:
            crossings.append(sample.at)
    for earlier, later in zip(samples, samples[1:]):
        first = float(earlier.sun_altitude) - SUNRISE_SUNSET_DEG
        second = float(later.sun_altitude) - SUNRISE_SUNSET_DEG
        if first == 0.0 or second == 0.0 or (first < 0) == (second < 0):
            continue
        span = (later.at - earlier.at).total_seconds()
        crossing = earlier.at + timedelta(seconds=span * first / (first - second))
        crossings.append(crossing)
    return [(at - margin, at + margin) for at in sorted(crossings)]
