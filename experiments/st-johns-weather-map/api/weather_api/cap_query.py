"""Bounded selected-time query cache for ECCC's mutable Current-Alerts view."""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Callable, Mapping, Sequence

from ingest.adapters.eccc_geomet import ALERTS_LAYER, GeoMetClient, avalon_probe_boxes
from ingest.http import PoliteClient
from ingest.resources import acquisition_budget

CAP_DOCUMENT_MAX_BYTES = 2 * 1024 * 1024
CAP_FEATURES_PER_BOX = 50
CAP_CACHE_MAX_BYTES = 8 * 1024 * 1024
CAP_MAX_AGE_SECONDS = 300
CAP_MAX_BOXES = 4
CAP_FAILURE_BACKOFF_SECONDS = 30.0


class CapQueryUnavailable(RuntimeError):
    """The mutable current-alert document cannot truthfully answer the query."""

    def __init__(self, message: str, *, partial_features: Sequence[Mapping[str, object]] = ()) -> None:
        super().__init__(message)
        self.partial_features = tuple(dict(item) for item in partial_features)


@dataclass(frozen=True)
class CAPRequestKey:
    """All canonical provider requests needed to cover the declared Avalon domain."""

    urls: tuple[str, ...]


@dataclass(frozen=True)
class CAPCacheEntry:
    key: CAPRequestKey
    feature_collection: Mapping[str, object]
    receipts: tuple[Mapping[str, object], ...]
    fetched_at: datetime
    expires_at: datetime
    expires_at_monotonic: float
    content_digest: str
    backing_bytes: int


def _parse_time(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _property(properties: Mapping[str, object], name: str) -> object:
    if name in properties:
        return properties[name]
    nested: object = properties
    for part in name.split("."):
        if not isinstance(nested, Mapping) or part not in nested:
            return None
        nested = nested[part]
    return nested


def _feature_key(feature: Mapping[str, object]) -> str:
    properties = feature.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    for name in ("identifier", "properties.identifier", "id", "properties.id", "_id"):
        value = _property(props, name)
        if value not in (None, ""):
            return str(value)
    if feature.get("id") not in (None, ""):
        return str(feature["id"])
    return hashlib.sha256(json.dumps(feature, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_collection(document: object) -> list[dict[str, object]]:
    if not isinstance(document, Mapping) or document.get("type") != "FeatureCollection":
        raise CapQueryUnavailable("ECCC CAP response is not a GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list):
        raise CapQueryUnavailable("ECCC CAP response has no feature list")
    if len(features) > CAP_FEATURES_PER_BOX:
        raise CapQueryUnavailable("ECCC CAP response exceeds the per-box feature ceiling")
    checked: list[dict[str, object]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise CapQueryUnavailable(f"ECCC CAP feature {index} is not a GeoJSON Feature")
        if not isinstance(feature.get("properties"), Mapping):
            raise CapQueryUnavailable(f"ECCC CAP feature {index} properties are not an object")
        geometry = feature.get("geometry")
        if geometry is not None:
            _validate_geometry(geometry, index)
        properties = feature["properties"]
        assert isinstance(properties, Mapping)
        for name in ("identifier", "senderName", "headline", "description", "sent", "expires", "severity", "urgency", "certainty"):
            if _property(properties, name) in (None, "") and _property(properties, f"properties.{name}") in (None, ""):
                raise CapQueryUnavailable(f"ECCC CAP feature {index} is missing native {name}")
        for name in ("sent", "effective", "onset", "expires"):
            value = _property(properties, name) or _property(properties, f"properties.{name}")
            if value not in (None, ""):
                parsed = _parse_time(value)
                if parsed is None or datetime.fromisoformat(str(value).replace("Z", "+00:00")).tzinfo is None:
                    raise CapQueryUnavailable(f"ECCC CAP feature {index} has invalid native {name}")
        checked.append(dict(feature))
    return checked


def _validate_geometry(geometry: object, index: int) -> None:
    if not isinstance(geometry, Mapping) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise CapQueryUnavailable(f"ECCC CAP feature {index} geometry is not a supported polygon")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise CapQueryUnavailable(f"ECCC CAP feature {index} geometry has no coordinates")
    points = 0
    def position(value: object) -> tuple[float, float]:
        nonlocal points
        if not (isinstance(value, list) and len(value) >= 2 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:2])):
            raise CapQueryUnavailable(f"ECCC CAP feature {index} geometry position is invalid")
        lon, lat = float(value[0]), float(value[1])
        if not all(math.isfinite(item) for item in (lon, lat)) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise CapQueryUnavailable(f"ECCC CAP feature {index} geometry coordinate is invalid")
        points += 1
        if points > 100_000:
            raise CapQueryUnavailable(f"ECCC CAP feature {index} geometry exceeds the coordinate ceiling")
        return lon, lat

    def ring(value: object) -> None:
        if not isinstance(value, list) or len(value) < 4:
            raise CapQueryUnavailable(f"ECCC CAP feature {index} polygon ring is too short")
        parsed = [position(item) for item in value]
        if parsed[0] != parsed[-1]:
            raise CapQueryUnavailable(f"ECCC CAP feature {index} polygon ring is not closed")

    def polygon(value: object) -> None:
        if not isinstance(value, list) or not value:
            raise CapQueryUnavailable(f"ECCC CAP feature {index} polygon has no rings")
        for item in value:
            ring(item)

    if geometry["type"] == "Polygon":
        polygon(coordinates)
    else:
        if not isinstance(coordinates, list) or not coordinates:
            raise CapQueryUnavailable(f"ECCC CAP feature {index} multipolygon has no polygons")
        for item in coordinates:
            polygon(item)


def _max_age(headers: Mapping[str, object], completed: datetime) -> tuple[int, int]:
    cache_control = str(headers.get("cache-control", headers.get("Cache-Control", "")))
    seconds: int | None = None
    for token in cache_control.split(","):
        name, separator, value = token.strip().partition("=")
        if separator and name.lower() == "max-age" and value.isdigit():
            seconds = int(value)
            break
    if seconds is None or not 1 <= seconds <= CAP_MAX_AGE_SECONDS:
        raise CapQueryUnavailable("ECCC CAP response has no supported finite max-age")
    age_text = str(headers.get("age", headers.get("Age", "0"))).strip()
    if not age_text.isdigit():
        raise CapQueryUnavailable("ECCC CAP response has an invalid Age header")
    apparent_age = 0
    date_text = headers.get("date", headers.get("Date"))
    if date_text:
        try:
            provider_date = parsedate_to_datetime(str(date_text))
        except (TypeError, ValueError) as error:
            raise CapQueryUnavailable("ECCC CAP response has an invalid Date header") from error
        if provider_date.tzinfo is None:
            raise CapQueryUnavailable("ECCC CAP response has an invalid Date header")
        apparent_age = max(0, math.floor((completed - provider_date.astimezone(UTC)).total_seconds()))
    remaining = seconds - max(int(age_text), apparent_age)
    if remaining <= 0:
        raise CapQueryUnavailable("ECCC CAP response is already expired")
    return seconds, remaining


def _applies(feature: Mapping[str, object], selected_at: datetime) -> tuple[bool, str]:
    properties = feature["properties"]
    assert isinstance(properties, Mapping)
    sent = _parse_time(_property(properties, "properties.sent") or _property(properties, "sent"))
    effective = _parse_time(_property(properties, "properties.effective") or _property(properties, "effective"))
    onset = _parse_time(_property(properties, "properties.onset") or _property(properties, "onset"))
    expires = _parse_time(_property(properties, "properties.expires") or _property(properties, "expires"))
    start = effective or onset or sent
    if sent is None or start is None or expires is None or expires <= start:
        return False, "feature has incomplete or invalid native CAP validity"
    if sent > selected_at:
        return False, "feature was sent after the selected instant"
    if selected_at < start:
        return False, "feature is not yet effective at the selected instant"
    if selected_at >= expires:
        return False, "feature expired before the selected instant"
    return True, "native CAP validity contains the selected instant"


class CAPQueryService:
    """Fetch every declared box once, coalesce misses, and cache one current view."""

    def __init__(
        self,
        *,
        client: PoliteClient | None = None,
        boxes: Sequence[Mapping[str, float]] | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client or PoliteClient()
        self._boxes = tuple(dict(box) for box in (boxes or avalon_probe_boxes()))
        if not 1 <= len(self._boxes) <= CAP_MAX_BOXES:
            raise ValueError("ECCC CAP query requires 1..4 declared Avalon boxes")
        if len({tuple(sorted(box.items())) for box in self._boxes}) != len(self._boxes):
            raise ValueError("ECCC CAP declared boxes must be unique")
        for box in self._boxes:
            if set(box) != {"south", "west", "north", "east"}:
                raise ValueError("ECCC CAP box must contain south, west, north and east")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in box.values()):
                raise ValueError("ECCC CAP box coordinates must be finite numbers")
            if not (-90 <= box["south"] < box["north"] <= 90 and -180 <= box["west"] < box["east"] <= 180):
                raise ValueError("ECCC CAP box must be ordered south-west to north-east")
        geomet = GeoMetClient(client=self._client)
        urls = []
        for box in self._boxes:
            latitude = round((box["south"] + box["north"]) / 2, 6)
            longitude = round((box["west"] + box["east"]) / 2, 6)
            params = {
                "request": "GetFeatureInfo", "layers": ALERTS_LAYER, "query_layers": ALERTS_LAYER,
                "info_format": "application/json", "feature_count": CAP_FEATURES_PER_BOX,
                **geomet._probe_params(latitude, longitude, box),
            }
            urls.append(geomet.url(params))
        self.key = CAPRequestKey(tuple(urls))
        self._clock, self._now = clock, now
        self._lock = threading.Lock()
        self._entry: CAPCacheEntry | None = None
        self._inflight: Future[CAPCacheEntry] | None = None
        self._last_error: CapQueryUnavailable | None = None
        self._retry_after = 0.0

    def _fetch(self) -> CAPCacheEntry:
        merged: dict[str, dict[str, object]] = {}
        receipts: list[Mapping[str, object]] = []
        encoded_total = 0
        with acquisition_budget(len(self.key.urls) * CAP_DOCUMENT_MAX_BYTES):
            for url in self.key.urls:
                try:
                    raw, receipt = self._client.get_bytes_with_receipt(url, max_bytes=CAP_DOCUMENT_MAX_BYTES)
                    if receipt.get("byte_size") != len(raw) or receipt.get("sha256") != hashlib.sha256(raw).hexdigest():
                        raise CapQueryUnavailable("ECCC CAP transport receipt does not match the response body")
                    document = json.loads(raw)
                    features = _validate_collection(document)
                except Exception as error:
                    raise CapQueryUnavailable(f"ECCC CAP declared-box query failed: {error}", partial_features=merged.values()) from error
                encoded_total += len(raw)
                if encoded_total > CAP_CACHE_MAX_BYTES:
                    raise CapQueryUnavailable("ECCC CAP combined response exceeds the cache byte ceiling", partial_features=merged.values())
                receipts.append(receipt)
                for feature in features:
                    key = _feature_key(feature)
                    prior = merged.get(key)
                    if prior is not None and json.dumps(prior, sort_keys=True) != json.dumps(feature, sort_keys=True):
                        raise CapQueryUnavailable(f"ECCC CAP identifier {key!r} conflicts across declared boxes", partial_features=merged.values())
                    if prior is None:
                        merged[key] = feature
        if len(receipts) != len(self.key.urls):
            raise CapQueryUnavailable("ECCC CAP did not complete every declared box", partial_features=merged.values())
        completed_values = []
        for item in receipts:
            raw_completed = item.get("completed_at")
            parsed_completed = _parse_time(raw_completed)
            try:
                has_offset = datetime.fromisoformat(str(raw_completed).replace("Z", "+00:00")).tzinfo is not None
            except ValueError:
                has_offset = False
            completed_values.append(parsed_completed if has_offset else None)
        if any(item is None for item in completed_values):
            raise CapQueryUnavailable("ECCC CAP receipt has no valid final-byte completion")
        fetched_at = max(item for item in completed_values if item is not None)
        ttl_values = [_max_age(item.get("response_headers", {}), fetched_at)[1] for item in receipts]
        ttl = min(ttl_values)
        collection = {"type": "FeatureCollection", "features": list(merged.values())}
        canonical = json.dumps(collection, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        backing = len(canonical) + sum(len(json.dumps(item, default=str)) for item in receipts)
        if backing > CAP_CACHE_MAX_BYTES:
            raise CapQueryUnavailable("ECCC CAP normalized entry exceeds the cache byte ceiling")
        return CAPCacheEntry(self.key, collection, tuple(receipts), fetched_at, fetched_at + timedelta(seconds=ttl), self._clock() + ttl, digest, backing)

    def entry(self) -> CAPCacheEntry:
        with self._lock:
            if self._entry is not None and self._clock() < self._entry.expires_at_monotonic:
                return self._entry
            if self._last_error is not None and self._clock() < self._retry_after:
                raise self._last_error
            future = self._inflight
            if future is None:
                future = Future()
                self._inflight = future
                owner = True
            else:
                owner = False
        if not owner:
            return future.result()
        try:
            entry = self._fetch()
            with self._lock:
                self._entry = entry
                self._last_error = None
            future.set_result(entry)
            return entry
        except BaseException as error:
            if isinstance(error, CapQueryUnavailable):
                with self._lock:
                    self._last_error = error
                    self._retry_after = self._clock() + CAP_FAILURE_BACKOFF_SECONDS
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight = None

    def query(self, selected_at: datetime) -> dict[str, object]:
        if selected_at.tzinfo is None:
            raise ValueError("ECCC CAP selected timestamp must be timezone-aware")
        selected_at = selected_at.astimezone(UTC)
        entry = self.entry()
        context_start = entry.fetched_at - (entry.expires_at - entry.fetched_at)
        if selected_at < context_start or selected_at > entry.expires_at:
            raise CapQueryUnavailable("selected timestamp is outside the mutable current-alert acquisition context")
        selected: list[dict[str, object]] = []
        excluded: dict[str, str] = {}
        for feature in entry.feature_collection["features"]:
            assert isinstance(feature, Mapping)
            applies, reason = _applies(feature, selected_at)
            if applies:
                selected.append(dict(feature))
            else:
                excluded[_feature_key(feature)] = reason
        return {
            "type": "FeatureCollection", "features": selected, "data_mode": "live", "operational": False,
            "alerts_in_force": len(selected), "all_boxes_succeeded": True, "empty_is_an_answer": not selected,
            "selected_time": selected_at.isoformat(), "retrieved_at": entry.fetched_at.isoformat(),
            "expires_at": entry.expires_at.isoformat(), "content_digest": entry.content_digest,
            "acquisition": list(entry.receipts), "excluded_features": excluded,
            "source_id": "eccc-cap-alerts", "layer": ALERTS_LAYER,
        }
