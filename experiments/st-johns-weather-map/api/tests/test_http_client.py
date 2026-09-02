"""The polite client's throttling knobs and its 429 accounting."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ingest.http import DEFAULT_MIN_HOST_INTERVAL_SECONDS, PoliteClient, USER_AGENT, min_host_interval_from_env


def _client(handler, *, attempts: int = 3) -> PoliteClient:
    client = PoliteClient(min_host_interval_seconds=0.0, attempts=attempts)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return client


def test_the_host_interval_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("WEATHER_HTTP_MIN_HOST_INTERVAL", raising=False)
    assert min_host_interval_from_env() == DEFAULT_MIN_HOST_INTERVAL_SECONDS
    assert PoliteClient().min_host_interval_seconds == DEFAULT_MIN_HOST_INTERVAL_SECONDS
    monkeypatch.setenv("WEATHER_HTTP_MIN_HOST_INTERVAL", "0.1")
    assert min_host_interval_from_env() == pytest.approx(0.1)
    assert PoliteClient().min_host_interval_seconds == pytest.approx(0.1)
    # Nonsense and negatives fall back rather than disabling politeness.
    monkeypatch.setenv("WEATHER_HTTP_MIN_HOST_INTERVAL", "fast")
    assert min_host_interval_from_env() == DEFAULT_MIN_HOST_INTERVAL_SECONDS
    monkeypatch.setenv("WEATHER_HTTP_MIN_HOST_INTERVAL", "-1")
    assert min_host_interval_from_env() == 0.0


def test_every_429_is_counted_and_the_request_still_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ingest.http.time.sleep", lambda _seconds: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, content=b"grib-bytes")

    client = _client(handler, attempts=4)
    written = client.download("https://dd.weather.gc.ca/x.grib2", tmp_path / "x.grib2", max_bytes=1024)
    assert written == len(b"grib-bytes")
    # The count is what a worker log reader checks after lowering the host
    # interval: two 429s here means the provider pushed back twice.
    assert client.retry_counts[429] == 2
    assert calls["n"] == 3


def test_the_counter_is_shared_across_threads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr("ingest.http.time.sleep", lambda _seconds: None)
    seen: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 1:
            return httpx.Response(429)
        return httpx.Response(200, content=b"ok")

    client = _client(handler, attempts=3)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: client.download(f"https://dd.weather.gc.ca/{i}.grib2", tmp_path / f"{i}.grib2", max_bytes=64), range(8)))
    assert client.retry_counts[429] == 8
