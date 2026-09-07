"""Validate and normalize one bounded GeoMet AQHI FeatureCollection."""
from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from typing import Mapping

MAX_FEATURES = 50


def _property(properties: Mapping[str, object], name: str) -> object:
    return properties.get(f"properties.{name}", properties.get(name))


def _instant(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("observation_datetime is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observation_datetime has no offset")
    return parsed.astimezone(UTC).isoformat()


def normalize(document: object) -> list[dict[str, object]]:
    if not isinstance(document, Mapping) or document.get("type") != "FeatureCollection":
        raise ValueError("AQHI response is not a GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list) or len(features) > MAX_FEATURES:
        raise ValueError("AQHI response has an invalid feature list")
    rows: list[dict[str, object]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise ValueError(f"AQHI feature {index} is not a GeoJSON Feature")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping) or geometry.get("type") != "Point":
            raise ValueError(f"AQHI feature {index} has invalid properties or point geometry")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError(f"AQHI feature {index} has no point coordinates")
        longitude, latitude = coordinates[:2]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in (latitude, longitude)):
            raise ValueError(f"AQHI feature {index} has invalid point coordinates")
        longitude, latitude = float(longitude), float(latitude)
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValueError(f"AQHI feature {index} has out-of-range point coordinates")
        raw_index = _property(properties, "aqhi")
        try:
            value = float(str(raw_index))
        except (TypeError, ValueError) as error:
            raise ValueError(f"AQHI feature {index} has no numeric AQHI") from error
        if not math.isfinite(value):
            raise ValueError(f"AQHI feature {index} has non-finite AQHI")
        identifier = feature.get("id") or _property(properties, "id") or _property(properties, "_id") or _property(properties, "identifier") or _property(properties, "station_id")
        if not isinstance(identifier, (str, int)) or not str(identifier).strip():
            raise ValueError(f"AQHI feature {index} has no station identifier")
        row: dict[str, object] = {
            "station_id": str(identifier),
            "station_name": str(_property(properties, "location_name_en") or "") or None,
            "observation_time": _instant(_property(properties, "observation_datetime")),
            "latitude": latitude,
            "longitude": longitude,
            "value": value,
        }
        quality = _property(properties, "quality") or _property(properties, "qc") or _property(properties, "quality_flag")
        if quality not in (None, ""):
            row["quality"] = str(quality)
        rows.append(row)
    return rows


def main() -> int:
    try:
        document = json.load(sys.stdin.buffer)
        json.dump(normalize(document), sys.stdout, separators=(",", ":"), ensure_ascii=True)
        return 0
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
