"""Night frames, and the daytime derivations that refuse to run on them.

A camera frame is not assumed to be daylight. Whether the sun was above the
horizon at the moment the frame was captured is decided by the daylight
boundary of the registered derivation entry ``de442_sun_moon_geometry``
(:data:`ingest.derive.registry.DE442_GEOMETRY`), whose ``sun_altitude``
output is the only altitude this module will read. Three rules follow.

* **The boundary is the registered one.** :data:`SUN_HORIZON_DEG` is the
  refraction-inclusive horizon of that entry, mirrored here as a constant
  because ``ingest`` never imports ``api``. It is the same number as
  ``api.weather_api.astronomy.SUN_HORIZON_DEG``; the two are the same
  boundary named twice, not two boundaries.
* **Unknown is not daylight.** When the sun altitude is absent, or when the
  DE442 entry itself is refused at any of the three levels the registry
  checks (unregistered, entry disabled, ``WEATHER_DERIVED_HERE=off``, or
  switched off by this reader), the frame carries :data:`DARKNESS_UNKNOWN`.
  That flag refuses every daytime derivation exactly as :data:`DARKNESS`
  does. Nothing here falls back to a clock, a season or a default.
* **A refused derivation is null naming the flag.** :func:`refuse_daytime_derivation`
  returns the flag that stands, and the caller's field is ``null`` naming
  it. No substitute construction is run, and no neighbouring frame is used
  in place of the flagged one.

:data:`DAYTIME_METHODS` is every camera method except
:data:`ingest.derive.registry.CAMERA_SKYDOME_NIGHT_CLOUD`, which is the one
night path. That method is not exempted from anything else: like all five
camera methods it is registered disabled and stays disabled until the
30-day CYYT METAR validation of :mod:`ingest.cameras.validation_record`
exists, so asking for it today is ``awaiting_validation``.

Pure Python. Nothing here reads pixels: the ``darkness`` flag that
:func:`ingest.cameras.frames.compute_health_flags` raises from image
intensity is a statement about the image, and the flag this module computes
is a statement about the sun. They share the string :data:`DARKNESS`
deliberately, because a derivation refuses on either for the same reason.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from ingest.cameras.frames import Frame
from ingest.derive import registry as derive_registry
from ingest.derive.registry import (
    CAMERA_METHODS,
    CAMERA_SKYDOME_NIGHT_CLOUD,
    DE442_GEOMETRY,
)

__all__ = [
    "DARKNESS",
    "DARKNESS_UNKNOWN",
    "DAYTIME_METHODS",
    "DE442_GEOMETRY",
    "SUN_HORIZON_DEG",
    "darkness_flag",
    "darkness_flag_for",
    "flag_frame",
    "refuse_daytime_derivation",
]

#: The daylight boundary of the registered DE442 entry
#: ``de442_sun_moon_geometry``: the sun's centre at -0.833 degrees, which is
#: the standard refraction-inclusive horizon. Mirrored from
#: ``api.weather_api.astronomy.SUN_HORIZON_DEG`` because ``ingest`` never
#: imports ``api``; the two constants are one boundary.
SUN_HORIZON_DEG = -0.833

#: The flag a frame captured below that boundary carries. The same string as
#: the ``darkness`` member of :data:`ingest.cameras.frames.HEALTH_FLAGS`, so
#: a single refusal covers a dark image and a night sun.
DARKNESS = "darkness"

#: The flag a frame carries when darkness could not be decided at all. It is
#: not a weaker ``darkness``: it refuses the same derivations, because a
#: frame whose light is unknown is never assumed to be daylight.
DARKNESS_UNKNOWN = "darkness_unknown"

#: Every camera method that needs daylight: all of them but the sky-dome
#: night method, which is the one night path. Derived from
#: :data:`ingest.derive.registry.CAMERA_METHODS` rather than retyped, so a
#: camera method added there is a daytime method here until it is named as
#: the night path.
DAYTIME_METHODS: frozenset[str] = frozenset(CAMERA_METHODS) - {CAMERA_SKYDOME_NIGHT_CLOUD}


def darkness_flag(sun_altitude: float | None) -> str | None:
    """The darkness flag for a sun altitude in degrees, or ``None``.

    ``None`` in is :data:`DARKNESS_UNKNOWN` out: an absent altitude is not a
    daylight altitude. An altitude at or below :data:`SUN_HORIZON_DEG` is
    :data:`DARKNESS`. Anything above it carries no flag, which is the only
    way a frame is called daylight.
    """
    if sun_altitude is None:
        return DARKNESS_UNKNOWN
    if sun_altitude <= SUN_HORIZON_DEG:
        return DARKNESS
    return None


def darkness_flag_for(
    sun_altitude: float | None,
    *,
    reader_disabled: Iterable[str] = (),
) -> str | None:
    """:func:`darkness_flag`, but only if the DE442 entry may speak.

    The altitude is worth nothing unless the construction that produced it
    is allowed to produce it, so this resolves :data:`DE442_GEOMETRY`
    through :func:`ingest.derive.registry.resolve` first. Any refusal - the
    entry unregistered or disabled, ``WEATHER_DERIVED_HERE=off`` at the
    deployment, or the reader having switched the entry off - is
    :data:`DARKNESS_UNKNOWN`, never a silently kept altitude and never an
    assumption of daylight.
    """
    refusal = derive_registry.resolve(DE442_GEOMETRY, reader_disabled=reader_disabled)
    if refusal is not None:
        return DARKNESS_UNKNOWN
    return darkness_flag(sun_altitude)


def flag_frame(
    frame: Frame,
    sun_altitude: float | None,
    *,
    reader_disabled: Iterable[str] = (),
) -> Frame:
    """A copy of ``frame`` carrying the darkness flag its light earns.

    The frame's own computed health flags are kept: this only ever adds. A
    frame in daylight, decided by an entry that was allowed to decide, comes
    back with its flags unchanged - that is the single case in which no
    darkness flag is added, and it is never reached by default.
    """
    flag = darkness_flag_for(sun_altitude, reader_disabled=reader_disabled)
    if flag is None:
        return frame
    return replace(frame, flags=frozenset(frame.flags) | {flag})


def refuse_daytime_derivation(method: str, frame_flags: Iterable[str]) -> str | None:
    """The flag that refuses this daytime method on this frame, or ``None``.

    A method outside :data:`DAYTIME_METHODS` is not refused here: the
    sky-dome night method has its own reason to be null today, which is that
    it is registered disabled awaiting validation. A refusal returned here
    means the caller's field is ``null`` naming the flag; no substitute
    construction stands in for it.
    """
    if method not in DAYTIME_METHODS:
        return None
    raised = set(frame_flags)
    if DARKNESS in raised:
        return DARKNESS
    if DARKNESS_UNKNOWN in raised:
        return DARKNESS_UNKNOWN
    return None
