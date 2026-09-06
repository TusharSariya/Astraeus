from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from weather_api.swpc_kp_query import SWPCKpQueryService


class BoundsProbe:
    def __init__(self) -> None:
        self.calls = 0

    def operation_bounds(self, _window) -> None:
        self.calls += 1


def observed_body() -> bytes:
    return json.dumps([
        ["time_tag", "Kp", "a_running"],
        ["2026-09-06T09:00:00Z", "2.00", "7"],
        ["2026-09-06T12:00:00Z", "3.33", "12"],
        ["2026-09-06T15:00:00Z", "4.00", "20"],
    ]).encode()


def forecast_body() -> bytes:
    return json.dumps([
        ["time_tag", "kp", "observed"],
        ["2026-09-06T12:00:00Z", "3.33", "observed"],
        ["2026-09-06T15:00:00Z", "4.00", "estimated"],
        ["2026-09-06T18:00:00Z", "5.00", "predicted"],
    ]).encode()


def service(*, forecast_status: int = 200):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "forecast" in str(request.url):
            return httpx.Response(forecast_status, content=forecast_body() if forecast_status == 200 else b"", request=request)
        return httpx.Response(200, content=observed_body(), request=request)

    bounds = BoundsProbe()
    query = SWPCKpQueryService(client=httpx.Client(transport=httpx.MockTransport(handler)), adapter=bounds)  # type: ignore[arg-type]
    return query, calls, bounds


def test_selected_time_filters_native_observed_and_forecast_without_nearest_substitution() -> None:
    query, calls, bounds = service()
    observed, forecast = query.series(datetime(2026, 9, 6, 14, tzinfo=UTC))
    assert [row.time.hour for row in observed.readings] == [9, 12]
    assert [row.value for row in observed.readings] == [2.0, 3.33]
    assert [(row.time.hour, row.status) for row in forecast.readings] == [(15, "estimated"), (18, "predicted")]
    assert len(calls) == 2
    assert bounds.calls == 1

    # A different selected instant reuses the same canonical feed bodies and
    # filters locally; it cannot turn a UI scrub into another provider call.
    observed, forecast = query.series(datetime(2026, 9, 6, 14, 30, tzinfo=UTC))
    assert [row.time.hour for row in observed.readings] == [9, 12]
    assert [(row.time.hour, row.status) for row in forecast.readings] == [(15, "estimated"), (18, "predicted")]
    assert len(calls) == 2


def test_current_document_refuses_a_selection_outside_its_native_coverage() -> None:
    query, _calls, _bounds = service()
    observed, forecast = query.series(datetime(2026, 9, 5, 14, tzinfo=UTC))
    assert observed.available is False
    assert forecast.available is False
    observed, forecast = query.series(datetime(2026, 9, 7, 14, tzinfo=UTC))
    assert observed.available is False
    assert forecast.available is False


def test_forecast_failure_preserves_observed_and_discloses_forecast_absence() -> None:
    query, calls, _bounds = service(forecast_status=503)
    observed, forecast = query.series(datetime(2026, 9, 6, 14, tzinfo=UTC))
    assert observed.available is True
    assert forecast.available is False
    assert forecast.readings == []
    assert forecast.notices == ["SWPC forecast Kp returned HTTP 503"]
    assert len(calls) == 2


def test_selected_time_requires_an_offset() -> None:
    query, _calls, _bounds = service()
    with pytest.raises(ValueError, match="include an offset"):
        query.series(datetime(2026, 9, 6, 14))
