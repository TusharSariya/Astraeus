"""Astronomical darkness geometry from the pinned DE442 ephemeris.

Everything served from here is computed - not retrieved per request - from
one retrieved, checksum-verified artifact (the DE442 kernel, registry source
``nasa-jpl-de442``) plus published constants. The derivation strings say
exactly that. Nothing here reads weather evidence: the geometric core window
is geometry only and must never be blended with cloud, transparency or light
pollution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import numpy

from .ephemeris import EPHEMERIS_ID, EPHEMERIS_SHA256, verify_ephemeris

UTC = timezone.utc

SOURCE_ID = "nasa-jpl-de442"

#: Standard sun-altitude thresholds (degrees): refraction-inclusive horizon,
#: civil, nautical and astronomical twilight.
SUN_HORIZON_DEG = -0.833
CIVIL_DEG = -6.0
NAUTICAL_DEG = -12.0
ASTRONOMICAL_DEG = -18.0

#: Rise/set horizon for the moon's centre: standard refraction plus mean
#: lunar semidiameter, the convention printed in almanacs.
MOON_HORIZON_DEG = -0.567

#: The galactic centre (Sgr A*), J2000 - fixed catalogue coordinates.
SGR_A_RA_HOURS = (17.0, 45.0, 40.04)
SGR_A_DEC_DEGREES = (-29.0, 0.0, 28.1)

#: Minimum core altitude for the geometric window: below ~5 degrees the core
#: sits in the horizon murk at any latitude.
CORE_MIN_ALTITUDE_DEG = 5.0

#: Sampling resolution of the altitude scan across the window. Crossing
#: instants are linearly interpolated between samples and reported to the
#: minute; the derivation string states this.
STEP_SECONDS = 60

DERIVATION_VERSION = "astronomy-de442-v1"


class AstronomyUnavailable(RuntimeError):
    """The pinned kernel is missing or failed verification; nothing is computed."""


@dataclass(frozen=True)
class Interval:
    kind: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class MoonFacts:
    rise: datetime | None
    set: datetime | None
    above_horizon: list[Interval]
    phase_deg: float
    illuminated_fraction: float


@dataclass(frozen=True)
class CoreWindow:
    windows: list[Interval]
    max_altitude_deg: float


@dataclass(frozen=True)
class SkyGeometry:
    window_start: datetime
    window_end: datetime
    twilight_bands: list[Interval]
    moon: MoonFacts
    core: CoreWindow
    sun_altitude_deg: float
    moon_altitude_deg: float
    core_altitude_deg: float


def derivation() -> str:
    import skyfield  # noqa: PLC0415

    return (
        f"skyfield {skyfield.__version__} + JPL {EPHEMERIS_ID} (sha256 {EPHEMERIS_SHA256[:8]}...), "
        f"topocentric altitudes sampled every {STEP_SECONDS} s with linear crossing interpolation; "
        f"sun horizon {SUN_HORIZON_DEG} deg, twilight at {CIVIL_DEG}/{NAUTICAL_DEG}/{ASTRONOMICAL_DEG} deg, "
        f"moon horizon {MOON_HORIZON_DEG} deg (refraction + mean semidiameter), "
        f"galactic centre Sgr A* J2000 17h45m40.04s -29d00m28.1s"
    )


@lru_cache(maxsize=1)
def _load():
    """Verified kernel handles, once per process. Raises AstronomyUnavailable."""
    try:
        path = verify_ephemeris()
    except (FileNotFoundError, ValueError) as error:
        raise AstronomyUnavailable(str(error)) from error
    from skyfield.api import Loader, Star, wgs84  # noqa: PLC0415

    loader = Loader(str(path.parent), verbose=False)
    ts = loader.timescale(builtin=True)
    eph = loader(path.name)
    star = Star(ra_hours=SGR_A_RA_HOURS, dec_degrees=SGR_A_DEC_DEGREES)
    return ts, eph, star, wgs84


def reset_cache() -> None:
    """Test hook: forget the loaded kernel so a changed path is re-verified."""
    _load.cache_clear()


def _crossing(times: numpy.ndarray, values: numpy.ndarray, index: int, threshold: float) -> datetime:
    """The interpolated instant where ``values`` crosses ``threshold`` between
    samples ``index`` and ``index + 1``, floored to the minute."""
    v0, v1 = values[index], values[index + 1]
    fraction = 0.0 if v1 == v0 else (threshold - v0) / (v1 - v0)
    t0 = times[index]
    instant = t0 + timedelta(seconds=float(fraction) * STEP_SECONDS)
    return instant.replace(second=0, microsecond=0, tzinfo=UTC)


def _intervals_above(times, values: numpy.ndarray, threshold: float, kind: str, start: datetime, end: datetime) -> list[Interval]:
    """Contiguous intervals where ``values > threshold``, edges interpolated."""
    above = values > threshold
    intervals: list[Interval] = []
    current_start: datetime | None = start if above[0] else None
    for i in range(len(values) - 1):
        if not above[i] and above[i + 1]:
            current_start = _crossing(times, values, i, threshold)
        elif above[i] and not above[i + 1] and current_start is not None:
            intervals.append(Interval(kind, current_start, _crossing(times, values, i, threshold)))
            current_start = None
    if current_start is not None:
        intervals.append(Interval(kind, current_start, end))
    return intervals


def _band_kind(sun_alt: float) -> str:
    if sun_alt > SUN_HORIZON_DEG:
        return "day"
    if sun_alt > CIVIL_DEG:
        return "civil_twilight"
    if sun_alt > NAUTICAL_DEG:
        return "nautical_twilight"
    if sun_alt > ASTRONOMICAL_DEG:
        return "astronomical_twilight"
    return "night"


def sky_geometry(latitude: float, longitude: float, window_start: datetime, window_end: datetime, at: datetime) -> SkyGeometry:
    """All astronomy served for one coordinate over one window.

    Raises :class:`AstronomyUnavailable` when the kernel cannot be verified.
    """
    ts, eph, star, wgs84 = _load()
    from skyfield import almanac  # noqa: PLC0415

    observer = eph["earth"] + wgs84.latlon(latitude, longitude)
    steps = int((window_end - window_start).total_seconds() // STEP_SECONDS) + 1
    instants = [window_start + timedelta(seconds=i * STEP_SECONDS) for i in range(steps)]
    t = ts.from_datetimes(instants)

    sun_alt = observer.at(t).observe(eph["sun"]).apparent().altaz()[0].degrees
    moon_alt = observer.at(t).observe(eph["moon"]).apparent().altaz()[0].degrees
    core_alt = observer.at(t).observe(star).apparent().altaz()[0].degrees
    times = numpy.array(instants)

    # Twilight bands: classify each sample, then merge contiguous kinds. The
    # band edges are the sample boundaries (minute resolution, disclosed).
    kinds = [_band_kind(v) for v in sun_alt]
    bands: list[Interval] = []
    band_start = instants[0]
    for i in range(1, steps):
        if kinds[i] != kinds[i - 1]:
            bands.append(Interval(kinds[i - 1], band_start, instants[i]))
            band_start = instants[i]
    bands.append(Interval(kinds[-1], band_start, window_end))

    moon_up = _intervals_above(times, moon_alt, MOON_HORIZON_DEG, "moon_up", window_start, window_end)
    rises = [iv.start for iv in moon_up if iv.start != window_start]
    sets = [iv.end for iv in moon_up if iv.end != window_end]

    t_at = ts.from_datetime(at)
    phase_deg = float(almanac.moon_phase(eph, t_at).degrees)
    illuminated = float(almanac.fraction_illuminated(eph, "moon", t_at))

    # The geometric core window: pure intersection of three altitude tests.
    visible = (core_alt > CORE_MIN_ALTITUDE_DEG) & (sun_alt < ASTRONOMICAL_DEG) & (moon_alt < MOON_HORIZON_DEG)
    core_windows: list[Interval] = []
    current: datetime | None = instants[0] if visible[0] else None
    for i in range(1, steps):
        if visible[i] and current is None:
            current = instants[i]
        elif not visible[i] and current is not None:
            core_windows.append(Interval("geometric_core_window", current, instants[i]))
            current = None
    if current is not None:
        core_windows.append(Interval("geometric_core_window", current, window_end))

    at_index = min(range(steps), key=lambda i: abs((instants[i] - at).total_seconds()))
    return SkyGeometry(
        window_start=window_start,
        window_end=window_end,
        twilight_bands=bands,
        moon=MoonFacts(
            rise=rises[0] if rises else None,
            set=sets[0] if sets else None,
            above_horizon=moon_up,
            phase_deg=round(phase_deg, 1),
            illuminated_fraction=round(illuminated, 3),
        ),
        core=CoreWindow(windows=core_windows, max_altitude_deg=round(float(numpy.max(core_alt)), 1)),
        sun_altitude_deg=round(float(sun_alt[at_index]), 1),
        moon_altitude_deg=round(float(moon_alt[at_index]), 1),
        core_altitude_deg=round(float(core_alt[at_index]), 1),
    )


CORE_CAPTION = (
    "Geometry only - says nothing about cloud, transparency, or light pollution; "
    "at this latitude the galactic core culminates low (about 10-15 degrees at 47.6 N)."
)
