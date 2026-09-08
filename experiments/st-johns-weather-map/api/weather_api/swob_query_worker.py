"""Bounded normalizer for canonical MSC SWOB station observations."""
from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from typing import Mapping

MAX_FEATURES = 64
MSC_PROVIDER = "MSC"
MSC_DATASET_PREFIX = "msc-observation-atmospheric-surface_weather-"
FIELDS = {
    "temperature_2m": ("air_temp", "degC"),
    "dew_point_2m": ("dwpt_temp", "degC"),
    "relative_humidity_2m": ("rel_hum", "percent"),
    "mean_sea_level_pressure": ("mslp", "hPa"),
    "wind_speed_10m": ("wnd_spd", "m s-1"),
    "wind_direction_10m": ("wnd_dir", "degree"),
}


def _property(properties: Mapping[str, object], name: str) -> object:
    return properties.get(f"properties.{name}", properties.get(name))


def _instant(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("SWOB report time is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("SWOB report time has no offset")
    return parsed.astimezone(UTC).isoformat()


def _number(value: object, *, field: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"SWOB {field} is not numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"SWOB {field} is not numeric") from error
    if not math.isfinite(parsed):
        raise ValueError(f"SWOB {field} is not finite")
    return parsed


def _field_token(properties: Mapping[str, object], name: str) -> str | None:
    for suffix in ("-qa", "-data_flag", "-data_flag-value", "_qa", "_data_flag"):
        value = _property(properties, f"{name}{suffix}")
        if value not in (None, ""):
            return str(value)
    return None


def _station_id(feature: Mapping[str, object], properties: Mapping[str, object], index: int) -> str:
    # OGC feature id can be a report id. Prefer native station identifiers, but
    # retain the raw feature id separately below when it is published.
    for name in ("stn_id", "station_id", "wmo_id", "wmo_stn", "msc_id", "msc_id-value"):
        value = _property(properties, name)
        if value not in (None, ""):
            return str(value)
    raise ValueError(f"SWOB feature {index} has no native station identifier")


def _complete_collection(document: Mapping[str, object], features: list[object]) -> None:
    """Refuse a response that cannot prove its bounded first page is complete."""
    count = len(features)
    for name in ("numberMatched", "numberReturned"):
        value = document.get(name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"SWOB {name} is invalid")
        if value != count:
            raise ValueError("SWOB collection is incomplete or paginated")
    links = document.get("links", [])
    if not isinstance(links, list):
        raise ValueError("SWOB collection links are invalid")
    if any(isinstance(link, Mapping) and str(link.get("rel", "")).lower() == "next" for link in links):
        raise ValueError("SWOB collection has an unconsumed next page")
    if count == MAX_FEATURES and document.get("numberMatched") is None:
        raise ValueError("SWOB collection at the feature ceiling has no completeness count")


def normalize(document: object) -> list[dict[str, object]]:
    if not isinstance(document, Mapping) or document.get("type") != "FeatureCollection":
        raise ValueError("SWOB response is not a GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list) or len(features) > MAX_FEATURES:
        raise ValueError("SWOB response has an invalid feature list")
    _complete_collection(document, features)
    rows: list[dict[str, object]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise ValueError(f"SWOB feature {index} is not a GeoJSON Feature")
        properties, geometry = feature.get("properties"), feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping) or geometry.get("type") != "Point":
            raise ValueError(f"SWOB feature {index} has invalid properties or point geometry")
        # The endpoint is shared. The hostname alone never authorizes a record.
        if _property(properties, "data_pvdr-value") != MSC_PROVIDER:
            continue
        dataset = _property(properties, "dataset")
        if not isinstance(dataset, str) or not dataset.startswith(MSC_DATASET_PREFIX):
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError(f"SWOB feature {index} has no point coordinates")
        longitude, latitude = coordinates[:2]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in (latitude, longitude)):
            raise ValueError(f"SWOB feature {index} has invalid point coordinates")
        latitude, longitude = float(latitude), float(longitude)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError(f"SWOB feature {index} has out-of-range point coordinates")
        tokens: dict[str, str] = {}
        values: dict[str, float | None] = {}
        for key, (native_name, _units) in FIELDS.items():
            token = _field_token(properties, native_name)
            if token is not None:
                tokens[key] = token
            value = _number(_property(properties, native_name), field=native_name)
            # No accepted per-field SWOB token-to-validity mapping exists.
            # Preserve every numeric value and token with local QC unknown;
            # only a missing native value becomes null.
            values[key] = value
        station_metadata = {
            name: str(_property(properties, name))
            for name in ("wmo_id", "wmo_stn", "msc_id", "msc_id-value", "stn_id")
            if _property(properties, name) not in (None, "")
        }
        rows.append({
            "station_id": _station_id(feature, properties, index),
            "provider_report_id": None if feature.get("id") in (None, "") else str(feature["id"]),
            "station_name": str(_property(properties, "stn_nam-value") or _property(properties, "stn_nam") or "") or None,
            "observation_time": _instant(_property(properties, "date_tm-value") or _property(properties, "date_tm")),
            "latitude": latitude,
            "longitude": longitude,
            "dataset": dataset,
            "field_quality_tokens": tokens,
            "station_metadata": station_metadata,
            "values": values,
        })
    return rows


def main() -> int:
    try:
        json.dump(normalize(json.load(sys.stdin.buffer)), sys.stdout, separators=(",", ":"), ensure_ascii=True)
        return 0
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
