"""Explicit acquisition scope for isolated WeatherNext experiments.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006 (experiment).
No production registration or redistribution permission is implied.
"""
from datetime import datetime
from .weathernext_query import HISTORICAL_DELAY, WeatherNextSelection

HISTORICAL = "historical"
INTERNAL_FORECAST = "internal_experimental_forecast"


def validate_scope(selection: WeatherNextSelection, now: datetime, scope: str) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("WeatherNext aware acquisition clock required")
    if scope == HISTORICAL:
        if selection.valid_time >= now - HISTORICAL_DELAY:
            raise ValueError("WeatherNext historical permission boundary")
    elif scope == INTERNAL_FORECAST:
        if selection.initialization > now:
            raise ValueError("WeatherNext initialization has not occurred")
    else:
        raise ValueError("WeatherNext unknown acquisition scope")
