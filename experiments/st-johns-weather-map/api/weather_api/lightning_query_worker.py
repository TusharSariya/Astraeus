"""Bounded normalizer for ECCC GeoMet lightning metadata and samples."""
from __future__ import annotations

import json
import math
import re
import sys
import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime, timedelta
from typing import Mapping

LAYER = "Lightning_2.5km_Density"
MAX_TIMES = 64


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("lightning instant is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("lightning instant has no offset")
    return parsed.astimezone(UTC)


def _period(value: str) -> timedelta:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value.strip())
    if match is None:
        raise ValueError("lightning TIME has an unsupported period")
    duration = timedelta(hours=int(match.group(1) or 0), minutes=int(match.group(2) or 0), seconds=int(match.group(3) or 0))
    if duration <= timedelta(0):
        raise ValueError("lightning TIME has a non-positive period")
    return duration


def normalize_capabilities(body: bytes) -> dict[str, object]:
    if b"ServiceException" in body[:4096]:
        raise ValueError("lightning capabilities contains an OGC service exception")
    root = ElementTree.fromstring(body)
    layer = None
    for candidate in root.iter():
        if candidate.tag.rsplit("}", 1)[-1] != "Layer":
            continue
        name = next((child.text for child in candidate if child.tag.rsplit("}", 1)[-1] == "Name"), None)
        if name == LAYER:
            layer = candidate
            break
    if layer is None:
        raise ValueError("lightning layer is not advertised")
    dimension = next((child for child in layer if child.tag.rsplit("}", 1)[-1] in {"Dimension", "Extent"} and (child.get("name") or "").lower() == "time"), None)
    if dimension is None or not (dimension.text or "").strip():
        raise ValueError("lightning layer advertises no TIME extent")
    text = (dimension.text or "").strip()
    if "/" in text:
        pieces = text.split("/")
        if len(pieces) != 3:
            raise ValueError("lightning TIME interval is malformed")
        start, end, step = _instant(pieces[0]), _instant(pieces[1]), _period(pieces[2])
        times: list[datetime] = []
        cursor = start
        while cursor <= end and len(times) <= MAX_TIMES:
            times.append(cursor)
            cursor += step
        if cursor <= end or len(times) > MAX_TIMES:
            raise ValueError("lightning TIME extent exceeds its normalized bound")
    else:
        times = sorted({_instant(item.strip()) for item in text.split(",") if item.strip()})
    if not times or len(times) > MAX_TIMES:
        raise ValueError("lightning TIME list is empty or oversized")
    return {"times": [item.isoformat() for item in times], "update_sequence": root.get("updateSequence")}


def normalize_sample(body: bytes) -> dict[str, object]:
    if b"ServiceException" in body[:4096]:
        raise ValueError("lightning sample contains an OGC service exception")
    document = json.loads(body)
    if not isinstance(document, Mapping):
        raise ValueError("lightning sample is not an object")
    features = document.get("features")
    if features is None and not document:
        return {"value": None, "valid_time": None, "latitude": None, "longitude": None, "title": None, "native_units": None}
    if not isinstance(features, list) or len(features) > 1:
        raise ValueError("lightning sample has an invalid feature list")
    if not features:
        return {"value": None, "valid_time": None, "latitude": None, "longitude": None, "title": None, "native_units": None}
    feature = features[0]
    if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
        raise ValueError("lightning sample is not a GeoJSON Feature")
    properties, geometry = feature.get("properties"), feature.get("geometry")
    if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping) or geometry.get("type") != "Point":
        raise ValueError("lightning feature has invalid properties or geometry")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("lightning feature has no point coordinate")
    longitude, latitude = coordinates[:2]
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) for item in (latitude, longitude)):
        raise ValueError("lightning feature has invalid point coordinate")
    raw_value = properties.get("value")
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = None
    if value is not None and not math.isfinite(value):
        value = None
    title = properties.get("title_en")
    if not isinstance(title, str) or "flash/km" not in title or "/min" not in title:
        raise ValueError("lightning feature has unrecognized native units")
    return {
        "value": value,
        "valid_time": _instant(properties.get("time")).isoformat(),
        "latitude": float(latitude), "longitude": float(longitude),
        "title": title, "native_units": "flash/km²/min",
    }


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in {"capabilities", "sample"}:
        raise SystemExit("usage: lightning_query_worker.py capabilities|sample OUTPUT")
    body = sys.stdin.buffer.read()
    result = normalize_capabilities(body) if sys.argv[1] == "capabilities" else normalize_sample(body)
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
