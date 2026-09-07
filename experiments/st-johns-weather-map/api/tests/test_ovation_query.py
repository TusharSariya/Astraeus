from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from weather_api.ovation_query import OVATION_MAX_BODY_BYTES, OvationQueryService, OvationUnavailable, public_acquisition

FORECAST = datetime(2026, 9, 7, 1, 40, tzinfo=UTC)
OBSERVATION = FORECAST - timedelta(minutes=40)


def payload() -> bytes:
    import json
    return json.dumps({"type": "FeatureCollection", "Data Format": "[Longitude, Latitude, Aurora]", "Observation Time": OBSERVATION.isoformat().replace("+00:00", "Z"), "Forecast Time": FORECAST.isoformat().replace("+00:00", "Z"), "coordinates": [[-53, 47, 0], [-52, 48, 10], [0, -90, 2]]}).encode()


def decode(_body):
    return {"observation_time": OBSERVATION.isoformat(), "forecast_time": FORECAST.isoformat(), "cells": [[47, -53, 0], [48, -52, 10]]}


def service(handler, *, clock=lambda: 0.0):
    return OvationQueryService(client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False), clock=clock, utcnow=lambda: FORECAST, decode=decode)


def test_exact_existing_native_forecast_tolerance_preserves_zero_and_transport_receipt():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=payload(), headers={"cache-control": "max-age=60"}, request=request)
    query = service(handler)
    entry = query.entry_for(FORECAST + timedelta(seconds=600))
    assert entry.cells[0][2] == 0
    assert entry.acquisition.transport_completed_at == FORECAST
    assert entry.acquisition.body_bytes == len(payload())
    assert len(entry.acquisition.body_sha256) == 64
    assert len(public_acquisition(entry.acquisition).encode()) <= 12 * 1024
    assert len(calls) == 1


def test_outside_existing_one_native_interval_is_unavailable_without_second_request():
    calls = []
    query = service(lambda request: (calls.append(request) or httpx.Response(200, content=payload(), headers={"cache-control": "max-age=60"}, request=request)))
    with pytest.raises(OvationUnavailable, match="Forecast Time tolerance"):
        query.entry_for(FORECAST + timedelta(seconds=601))
    assert len(calls) == 1


def test_fresh_and_concurrent_identical_selected_requests_coalesce():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=payload(), headers={"cache-control": "max-age=60"}, request=request)
    query = service(handler)
    with ThreadPoolExecutor(max_workers=6) as pool:
        entries = list(pool.map(lambda _: query.entry_for(FORECAST), range(6)))
    assert len(calls) == 1
    assert all(entry is entries[0] for entry in entries)


def test_expiry_failure_never_reuses_grid_as_current():
    ticks, calls = [0.0], [0]
    def handler(request):
        calls[0] += 1
        if calls[0] == 2:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, content=payload(), headers={"cache-control": "max-age=1"}, request=request)
    query = service(handler, clock=lambda: ticks[0])
    query.entry_for(FORECAST)
    ticks[0] = 1.0
    with pytest.raises(OvationUnavailable) as caught:
        query.entry_for(FORECAST)
    assert calls[0] == 2 and query._entry is None
    assert query._expired_acquisition is not None
    assert caught.value.detail["cached_identity"] == query._expired_acquisition.body_sha256
    assert caught.value.detail["values_withheld"] is True


def test_declared_or_streamed_oversize_is_rejected_before_decode():
    calls = []
    query = service(lambda request: (calls.append(request) or httpx.Response(200, content=b"{}", headers={"content-length": str(OVATION_MAX_BODY_BYTES + 1)}, request=request)))
    with pytest.raises(OvationUnavailable, match="ceiling"):
        query.entry_for(FORECAST)
    assert len(calls) == 1


def test_retained_response_metadata_has_a_finite_structural_ceiling():
    query = service(lambda request: httpx.Response(200, content=payload(), headers={"cache-control": "max-age=60", "etag": "x" * 1025}, request=request))
    with pytest.raises(OvationUnavailable, match="retained-header ceiling"):
        query.entry_for(FORECAST)
