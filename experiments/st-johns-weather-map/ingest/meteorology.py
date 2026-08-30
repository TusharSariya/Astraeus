"""Meteorological derivations shared by the worker and the API.

These live in ``ingest`` rather than ``api.weather_api`` because the adapters
need them and the worker image does not ship the API package: ``awc.py`` used
to import ``weather_api.science`` and would have failed at runtime in the
worker. ``api.weather_api.science`` now re-exports this module, so the API's
public surface is unchanged.

The MetPy dependency and the explicit ``phase="liquid"`` are deliberate
scientific decisions, not incidental: saturation over liquid water is what
aviation and surface reports assume, and letting MetPy pick would silently
switch to ice below freezing and change the number.
"""

from __future__ import annotations

from datetime import datetime
from math import atan2, cos, radians, sin, sqrt

from metpy.calc import relative_humidity_from_dewpoint as metpy_relative_humidity_from_dewpoint
from metpy.calc import wind_direction as metpy_wind_direction
from metpy.calc import wind_speed as metpy_wind_speed
from metpy.units import units

HUMIDITY_DERIVATION = "MetPy relative_humidity_from_dewpoint with explicit liquid-water phase"
HUMIDITY_DERIVATION_VERSION = "metpy-1.7.1-liquid-v1"

# Direction is the bearing the wind blows *from*, in degrees clockwise from
# north, which is what every surface report and forecast reads as. MetPy
# offers a "to" convention as well; it is named explicitly here so a reader
# of the provenance never has to wonder which one the number is.
WIND_DERIVATION = "MetPy wind_speed and wind_direction from stored u/v components, meteorological from-direction convention"
WIND_DERIVATION_VERSION = "metpy-1.7.1-wind-v1"
WIND_SPEED_UNITS = "m s-1"
WIND_DIRECTION_UNITS = "degree"


def relative_humidity_from_dewpoint(temperature_c: float, dewpoint_c: float) -> float:
    """Return percent RH from unit-bearing values with explicit liquid phase."""
    rh = metpy_relative_humidity_from_dewpoint(
        temperature_c * units.degC,
        dewpoint_c * units.degC,
        phase="liquid",
    ).to("percent").magnitude
    return round(max(0.0, min(100.0, float(rh))), 1)


def resolve_relative_humidity(
    direct_rh_percent: float | None,
    temperature_c: float | None,
    dewpoint_c: float | None,
) -> tuple[float | None, str | None, str | None]:
    if direct_rh_percent is not None:
        return direct_rh_percent, None, None
    if temperature_c is None or dewpoint_c is None:
        return None, None, None
    return (
        relative_humidity_from_dewpoint(temperature_c, dewpoint_c),
        HUMIDITY_DERIVATION,
        HUMIDITY_DERIVATION_VERSION,
    )


def resolve_wind(
    u_ms: float | None,
    v_ms: float | None,
) -> tuple[float | None, float | None, str | None, str | None]:
    """``(speed m s-1, from-direction degrees, derivation, version)`` from u/v.

    Both components are needed: a speed from one component alone is not a wind
    speed, so a missing component yields nothing rather than a partial number.
    """
    if u_ms is None or v_ms is None:
        return None, None, None, None
    u = u_ms * units("m/s")
    v = v_ms * units("m/s")
    speed = float(metpy_wind_speed(u, v).to("m/s").magnitude)
    direction = float(metpy_wind_direction(u, v, convention="from").to("degree").magnitude)
    return round(speed, 2), round(direction, 1), WIND_DERIVATION, WIND_DERIVATION_VERSION


def fog_state(*, provider_diagnostic: bool | None, visibility_m: float | None, fog_code: bool | None) -> str:
    if provider_diagnostic is True or fog_code is True:
        return "evidence_present"
    if provider_diagnostic is False and fog_code is False and visibility_m is not None:
        return "not_indicated"
    return "unknown"


def radar_echo_semantics(has_echo: bool | None) -> str:
    if has_echo is True:
        return "precipitating_echo_detected"
    if has_echo is False:
        return "no_detected_precipitating_echo"
    return "unknown"


def interpolate_wind(u0: float, v0: float, u1: float, v1: float, fraction: float) -> tuple[float, float]:
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between zero and one")
    return (u0 + (u1 - u0) * fraction, v0 + (v1 - v0) * fraction)


def precipitation_interval_hours(start: datetime, end: datetime) -> float:
    """Preserve accumulation interval semantics; never treat accumulation as rate."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("precipitation interval timestamps must include offsets")
    hours = (end - start).total_seconds() / 3600
    if hours <= 0:
        raise ValueError("precipitation interval end must be after start")
    return hours


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    earth_radius_km = 6371.0088
    lat1, lat2 = radians(a_lat), radians(b_lat)
    delta_lat = radians(b_lat - a_lat)
    delta_lon = radians(b_lon - a_lon)
    root = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return earth_radius_km * 2 * atan2(sqrt(root), sqrt(1 - root))
