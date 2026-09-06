"""Bounded, request-coalesced live query for the CYYT AWC TAF.

The cache holds one provider response, not one entry per UI timestamp.  A
timestamp only selects native half-open forecast groups after the response has
been validated.
"""
from __future__ import annotations

import hashlib
import math
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

import httpx

from ingest.adapters.awc import (
    MAX_CLOUD_LAYERS,
    parse_cloud_cover_percent,
    parse_cloud_layers,
    parse_present_weather,
    parse_visibility_meters,
    parse_wind_components,
)
from ingest.awc_taf_isolated import _decode
from ingest.contract import FetchWindow

UTC = timezone.utc
AWC_TAF_URL = "https://aviationweather.gov/api/data/taf?ids=CYYT&format=json"
AWC_TAF_DOCUMENT_BYTES = 64 * 1024
TAF_PROVIDER_FIELD_DISPOSITIONS = {
    "wspd":"published_as_wind_components", "wdir":"published_as_wind_components", "wgst":"published_as_wind_gust",
    "visib":"published_as_visibility", "clouds":"published_as_ordered_cloud_layers", "vertVis":"preserved_native_group_metadata",
    "wxString":"published_as_raw_weather_and_fog_flags", "fcstChange":"preserved_native_group_metadata",
    "probability":"preserved_native_group_metadata", "timeFrom":"published_as_group_interval", "timeTo":"published_as_group_interval",
    "timeBec":"preserved_native_group_metadata", "cavok":"preserved_native_group_metadata", "windVariable":"preserved_native_group_metadata",
    "altim":"unsupported_preserved_in_raw_report", "temp":"unsupported_preserved_in_raw_report", "icgTurb":"unsupported_preserved_in_raw_report",
    "notDecoded":"unsupported_preserved_in_raw_report", "wshearDir":"unsupported_preserved_in_raw_report",
    "wshearHgt":"unsupported_preserved_in_raw_report", "wshearSpd":"unsupported_preserved_in_raw_report",
}
_MAX_AGE = re.compile(r"(?:^|,)\s*max-age=(\d+)\s*(?:,|$)", re.I)


class TafQueryUnavailable(RuntimeError):
    """No fresh, validated provider response can answer the query."""


@dataclass(frozen=True)
class TafCacheEntry:
    report: dict
    body_sha256: str
    body_bytes: int
    provider_url: str
    request_headers: Mapping[str, str]
    response_headers: Mapping[str, str]
    transport_completed_at: datetime
    fetched_at: datetime
    expires_at_monotonic: float
    etag: str | None
    last_revalidation: Mapping[str, object] | None = None


def _safe_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allowed = {"accept", "accept-encoding", "if-none-match", "user-agent"}
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


def _max_age(headers: Mapping[str, str]) -> int:
    match = _MAX_AGE.search(headers.get("cache-control", ""))
    if match is None:
        raise TafQueryUnavailable("AWC TAF response has no finite max-age")
    seconds = int(match.group(1))
    if seconds <= 0 or seconds > 300:
        raise TafQueryUnavailable("AWC TAF max-age is outside the measured 1..300 second bound")
    return seconds


def _presence(native: dict, key: str) -> str:
    if key not in native:
        return "not_stated_in_change_group"
    if native[key] is None:
        return "decoded_absence"
    if native[key] == []:
        return "decoded_empty"
    return "decoded_value"


def _group_values(native: dict) -> tuple[dict[str, float | None], dict[str, str]]:
    values: dict[str, float | None] = {}
    presence: dict[str, str] = {}
    u, v = parse_wind_components(native.get("wspd"), native.get("wdir"))
    for name, value in (("wind_u_10m", u), ("wind_v_10m", v)):
        state = "not_stated_in_change_group" if "wspd" not in native or "wdir" not in native else "decoded_absence" if value is None else "decoded_value"
        values[name], presence[name] = value, state
    vis = parse_visibility_meters(native.get("visib"))
    values["visibility"] = vis
    presence["visibility"] = _presence(native, "visib") if vis is not None else ("not_stated_in_change_group" if "visib" not in native else "decoded_absence")
    gust = native.get("wgst")
    values["wind_gust_10m"] = None if gust is None else float(gust) * 0.514444
    presence["wind_gust_10m"] = _presence(native, "wgst")
    cloud_total = parse_cloud_cover_percent(None, native.get("clouds"))
    values["total_cloud_okta"] = cloud_total
    presence["total_cloud_okta"] = _presence(native, "clouds") if cloud_total is not None else ("not_stated_in_change_group" if "clouds" not in native else "decoded_absence")
    weather = parse_present_weather(native.get("wxString"))
    for name, value in (("weather_fog_code", weather.fog), ("weather_fog_vicinity_code", weather.fog_vicinity), ("weather_mist_code", weather.mist)):
        values[name] = 1.0 if value else 0.0
        presence[name] = _presence(native, "wxString")
    layers, errors = parse_cloud_layers(native.get("clouds"))
    if errors:
        raise TafQueryUnavailable("validated AWC TAF cloud conversion failed")
    for slot in range(1, MAX_CLOUD_LAYERS + 1):
        layer = layers[slot - 1] if slot <= len(layers) else None
        native_state = _presence(native, "clouds")
        if layer is None:
            state = "not_stated_in_change_group" if native_state == "not_stated_in_change_group" else "decoded_absence"
            values[f"cloud_layer_{slot}_cover_code"] = None
            values[f"cloud_layer_{slot}_cover"] = None
            values[f"cloud_layer_{slot}_base"] = None
            for suffix in ("cover_code", "cover", "base"):
                presence[f"cloud_layer_{slot}_{suffix}"] = state
        else:
            values[f"cloud_layer_{slot}_cover_code"] = float(layer.code_flag)
            values[f"cloud_layer_{slot}_cover"] = layer.cover_pct
            values[f"cloud_layer_{slot}_base"] = layer.base_m
            presence[f"cloud_layer_{slot}_cover_code"] = "decoded_value"
            presence[f"cloud_layer_{slot}_cover"] = "decoded_value" if layer.cover_pct is not None else "decoded_absence"
            presence[f"cloud_layer_{slot}_base"] = "decoded_value" if layer.base_m is not None else "decoded_absence"
    return values, presence


class TafQueryService:
    def __init__(self, *, client: httpx.Client | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._client = client or httpx.Client(headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"}, timeout=60, follow_redirects=True)
        self._clock = clock
        self._entry: TafCacheEntry | None = None
        self._condition = threading.Condition()
        self._fetching = False
        self._generation = 0
        self._last_error: TafQueryUnavailable | None = None
        self._last_error_generation = -1
        self._retry_after_monotonic = 0.0

    def _fetch(self, prior: TafCacheEntry | None) -> TafCacheEntry:
        request_headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if prior and prior.etag:
            request_headers["If-None-Match"] = prior.etag
        with self._client.stream("GET", AWC_TAF_URL, headers=request_headers) as response:
            completed: datetime
            if response.status_code == 304:
                response.read()
                completed = datetime.now(UTC)
                if prior is None:
                    raise TafQueryUnavailable("AWC returned 304 without a cached TAF")
                headers = {k.lower(): v for k, v in response.headers.items()}
                ttl = _max_age(headers or prior.response_headers)
                revalidation = {"status": 304, "request_headers": _safe_request_headers(response.request.headers),
                                "response_headers": headers, "transport_completed_at": completed}
                return TafCacheEntry(**{**prior.__dict__, "expires_at_monotonic": self._clock() + ttl,
                                        "last_revalidation": revalidation})
            if response.status_code != 200:
                raise TafQueryUnavailable(f"AWC TAF returned HTTP {response.status_code}")
            declared = response.headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > AWC_TAF_DOCUMENT_BYTES):
                raise TafQueryUnavailable("AWC TAF response exceeds the 65536-byte ceiling")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes(8192):
                size += len(chunk)
                if size > AWC_TAF_DOCUMENT_BYTES:
                    raise TafQueryUnavailable("AWC TAF response exceeds the 65536-byte ceiling")
                chunks.append(chunk)
            body = b"".join(chunks)
            completed = datetime.now(UTC)
            headers = {k.lower(): v for k, v in response.headers.items()}
        # The accepted live-query slice is CYYT only; this broad window lets the
        # validator judge the report's own intervals without using the UI `at`.
        report = _decode(body, FetchWindow(datetime(2100, 1, 1, tzinfo=UTC), back_hours=200 * 365 * 24, forward_hours=0))
        report.pop("_issue_epoch", None)
        for index, group in enumerate(report["fcsts"]):
            change = str(group.get("fcstChange") or "").upper()
            if index == 0 and change:
                raise TafQueryUnavailable("AWC TAF first group is not prevailing")
            if change in {"", "FM"}:
                variable = str(group.get("wdir") or "").upper() == "VRB" or bool(group.get("windVariable"))
                has_sky = bool(group.get("clouds")) or group.get("vertVis") is not None or bool(group.get("cavok"))
                if group.get("wspd") is None or (group.get("wdir") is None and not variable) or (group.get("visib") is None and not group.get("cavok")) or not has_sky:
                    raise TafQueryUnavailable(f"AWC TAF group {index} is not structurally complete")
        ttl = _max_age(headers)
        return TafCacheEntry(report, hashlib.sha256(body).hexdigest(), len(body), AWC_TAF_URL,
                             _safe_request_headers(response.request.headers), headers, completed, completed,
                             self._clock() + ttl, headers.get("etag"))

    def entry(self) -> TafCacheEntry:
        with self._condition:
            observed_generation = self._generation
            while True:
                now = self._clock()
                if self._entry is not None and now < self._entry.expires_at_monotonic:
                    return self._entry
                if self._last_error is not None and now < self._retry_after_monotonic:
                    raise TafQueryUnavailable(str(self._last_error))
                if not self._fetching:
                    self._fetching = True
                    self._generation += 1
                    fetch_generation = self._generation
                    prior = self._entry
                    break
                self._condition.wait()
                if self._last_error is not None and self._last_error_generation > observed_generation:
                    raise TafQueryUnavailable(str(self._last_error))
        try:
            replacement = self._fetch(prior)
        except Exception as error:
            unavailable = error if isinstance(error, TafQueryUnavailable) else TafQueryUnavailable(str(error))
            with self._condition:
                self._last_error = unavailable
                self._last_error_generation = fetch_generation
                self._retry_after_monotonic = self._clock() + 1.0
                self._fetching = False
                self._condition.notify_all()
            raise unavailable
        with self._condition:
            self._entry = replacement
            self._last_error = None
            self._retry_after_monotonic = 0.0
            self._fetching = False
            self._condition.notify_all()
            return replacement

    def query(self, station: str, at: datetime) -> dict:
        if station.upper() != "CYYT":
            raise ValueError("only the contracted CYYT TAF is available")
        entry = self.entry()
        taf = entry.report
        groups = []
        for index, native in enumerate(taf["fcsts"]):
            start = datetime.fromtimestamp(int(native["timeFrom"]), tz=UTC)
            end = datetime.fromtimestamp(int(native["timeTo"]), tz=UTC)
            if start <= at < end:
                values, presence = _group_values(native)
                groups.append({"index": index, "time_from": start, "time_to": end,
                               "change": native.get("fcstChange") or "", "probability": native.get("probability"),
                               "time_bec": native.get("timeBec"), "presence": presence, "values": values,
                               "native": {"wind_speed_kt": native.get("wspd"), "wind_direction_deg": None if str(native.get("wdir", "")).upper() == "VRB" else native.get("wdir"),
                                          "wind_variable": str(native.get("wdir", "")).upper() == "VRB" or native.get("windVariable"),
                                          "wind_gust_kt": native.get("wgst"), "visibility_sm": native.get("visib"), "weather": native.get("wxString"),
                                          "vertical_visibility_ft": native.get("vertVis"), "clouds": native.get("clouds"), "cavok": native.get("cavok")},
                               "native_presence": {"wind_speed_kt": _presence(native, "wspd"), "wind_direction_deg": _presence(native, "wdir"),
                                                   "wind_variable": "decoded_value" if str(native.get("wdir", "")).upper() == "VRB" else _presence(native, "windVariable"),
                                                   "wind_gust_kt": _presence(native, "wgst"), "visibility_sm": _presence(native, "visib"),
                                                   "weather": _presence(native, "wxString"), "vertical_visibility_ft": _presence(native, "vertVis"),
                                                   "clouds": _presence(native, "clouds"), "cavok": _presence(native, "cavok")},
                               "native_units": {"wind_speed_kt": "kt", "wind_direction_deg": "degree", "wind_gust_kt": "kt",
                                                "visibility_sm": "statute mile", "vertical_visibility_ft": "ft"}})
        return {"data_mode": "live", "operational": False, "station": "CYYT", "at": at, "source_id": "awc-taf",
                "revision_id": entry.body_sha256, "run_time": taf["issueTime"], "issue_time": taf["issueTime"],
                "valid_time_from": taf["validTimeFrom"], "valid_time_to": taf["validTimeTo"], "raw_taf": taf["rawTAF"],
                "quality": {"status": "passed"}, "provider_field_dispositions": TAF_PROVIDER_FIELD_DISPOSITIONS,
                "native_report_metadata": {k: v for k, v in taf.items() if k not in {"fcsts", "rawTAF"}},
                "applicable": bool(groups), "applicability_reason": None if groups else "no native TAF group applies at this timestamp",
                "acquisition": {"provider_url": entry.provider_url, "request_headers": dict(entry.request_headers),
                                "response_headers": dict(entry.response_headers), "transport_completed_at": entry.transport_completed_at,
                                "fetched_at": entry.fetched_at, "body_sha256": entry.body_sha256, "body_bytes": entry.body_bytes,
                                "last_revalidation": entry.last_revalidation},
                "groups": groups}


_service: TafQueryService | None = None


def taf_query_service() -> TafQueryService:
    global _service
    if _service is None:
        _service = TafQueryService()
    return _service
