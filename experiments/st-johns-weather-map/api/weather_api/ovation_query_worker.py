"""Bounded normalization for one SWPC OVATION current-grid document."""
from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime

BOUNDS = {"south": 40.0, "north": 55.0, "west": -70.0, "east": -40.0}


def stamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"OVATION payload lacks {name}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"OVATION {name} has no offset")
    return parsed.astimezone(UTC)


def normalized(body: bytes) -> dict[str, object]:
    payload = json.loads(body)
    if not isinstance(payload, dict) or set(payload) != {"Data Format", "Forecast Time", "Observation Time", "coordinates", "type"}:
        raise ValueError("OVATION payload shape is not the declared current-grid document")
    if payload["Data Format"] != "[Longitude, Latitude, Aurora]":
        raise ValueError("OVATION Data Format does not declare longitude, latitude, aurora tuples")
    observation = stamp(payload["Observation Time"], "Observation Time")
    forecast = stamp(payload["Forecast Time"], "Forecast Time")
    coordinates = payload["coordinates"]
    if not isinstance(coordinates, list) or not coordinates or len(coordinates) > 70_000:
        raise ValueError("OVATION coordinates are absent or exceed the structural ceiling")
    cells: list[list[float]] = []
    seen: set[tuple[float, float]] = set()
    for item in coordinates:
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError("OVATION coordinate is malformed")
        try:
            longitude, latitude, probability = (float(value) for value in item)
        except (TypeError, ValueError) as error:
            raise ValueError("OVATION coordinate is not numeric") from error
        if not all(math.isfinite(value) for value in (longitude, latitude, probability)) or not -90 <= latitude <= 90 or not 0 <= probability <= 100:
            raise ValueError("OVATION coordinate is outside native bounds")
        if longitude > 180:
            longitude -= 360
        if not -180 <= longitude <= 180:
            raise ValueError("OVATION longitude is outside native bounds")
        if BOUNDS["south"] <= latitude <= BOUNDS["north"] and BOUNDS["west"] <= longitude <= BOUNDS["east"]:
            identity = (latitude, longitude)
            if identity in seen:
                raise ValueError("OVATION grid duplicates a native cell")
            seen.add(identity)
            cells.append([latitude, longitude, probability])
    if not cells:
        raise ValueError("OVATION grid has no Atlantic-context cell")
    return {"observation_time": observation.isoformat(), "forecast_time": forecast.isoformat(), "cells": cells}


if __name__ == "__main__":
    try:
        print(json.dumps(normalized(sys.stdin.buffer.read()), separators=(",", ":")))
    except Exception as error:
        print(f"OVATION validation failed: {error}", file=sys.stderr)
        raise SystemExit(2)
