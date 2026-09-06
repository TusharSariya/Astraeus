"""Retry, pacing and the streaming byte ceiling.

No test here touches the network: every response is served by an in-process
httpx transport, and sleeping is captured rather than performed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from ingest import http as ingest_http
from ingest.http import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_MAX_BACKOFF_SECONDS,
    USER_AGENT,
    MaxBytesExceeded,
    PoliteClient,
    RetriesExhausted,
    backoff_delay,
    parse_retry_after,
)
from ingest.resources import ReceivedBytesExceeded, acquisition_budget

URL = "https://dd.weather.gc.ca/model_hrdps/sample.grib2"


class Chunked(httpx.SyncByteStream):
    """A body with no Content-Length, so only the mid-stream guard can stop it."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        return iter(self._chunks)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(ingest_http.time, "sleep", recorded.append)
    return recorded


def build_client(
    handler: Callable[[httpx.Request], httpx.Response], *, attempts: int = 5
) -> PoliteClient:
    client = PoliteClient(attempts=attempts, min_host_interval_seconds=0.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        follow_redirects=True,
    )
    return client


def test_a_transient_failure_is_retried_and_then_succeeds(sleeps):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503) if len(seen) < 3 else httpx.Response(200, text="ok")

    with build_client(handler) as client:
        assert client.get_text(URL) == "ok"
    assert len(seen) == 3
    assert len(sleeps) == 2
    assert seen[0].headers["User-Agent"] == USER_AGENT


def test_retries_are_bounded_and_the_last_status_is_surfaced(sleeps):
    """A persistently failing status is raised as itself, not hidden behind a count."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503)

    with build_client(handler, attempts=3) as client:
        with pytest.raises(httpx.HTTPStatusError) as error:
            client.get(URL)
    assert error.value.response.status_code == 503
    assert len(seen) == 3
    assert len(sleeps) == 2


def test_transport_errors_are_retried_then_reported_as_exhausted(sleeps):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("upstream unreachable", request=request)

    with build_client(handler, attempts=4) as client:
        with pytest.raises(RetriesExhausted, match="failed after 4 attempts"):
            client.get(URL)
    assert len(attempts) == 4
    assert len(sleeps) == 3


def test_a_non_retryable_status_fails_on_the_first_attempt(sleeps):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404)

    with build_client(handler) as client, pytest.raises(httpx.HTTPStatusError):
        client.get(URL)
    assert len(seen) == 1
    assert sleeps == []


def test_retry_after_overrides_the_computed_backoff(sleeps):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "7"})
            if len(seen) == 1
            else httpx.Response(200, text="ok")
        )

    with build_client(handler) as client:
        assert client.get_text(URL) == "ok"
    assert sleeps == [7.0]


def test_retry_response_bodies_count_against_the_operation_bound(sleeps):
    yielded: list[int] = []

    class RetryBody(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(10):
                yielded.append(index)
                yield b"x" * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, stream=RetryBody())

    with build_client(handler, attempts=3) as client, acquisition_budget(2048), pytest.raises(
        ReceivedBytesExceeded, match="2048"
    ):
        client.get(URL)
    assert yielded == [0, 1, 2]
    assert sleeps == []


def test_retry_after_in_http_date_form_is_ignored_rather_than_misread():
    assert parse_retry_after("Wed, 29 Aug 2026 12:00:00 GMT") is None
    assert parse_retry_after(None) is None
    assert parse_retry_after("-5") == 0.0
    assert parse_retry_after(" 2.5 ") == 2.5


def test_backoff_grows_exponentially_and_is_capped():
    delays = [backoff_delay(attempt, jitter=1.0) for attempt in range(1, 8)]
    assert delays[0] == DEFAULT_BACKOFF_SECONDS
    assert delays == sorted(delays)
    assert all(later <= 2 * earlier for earlier, later in zip(delays, delays[1:]))
    assert backoff_delay(50, jitter=1.0) == DEFAULT_MAX_BACKOFF_SECONDS
    assert backoff_delay(50, jitter=0.0) == 0.0
    assert 0.0 <= backoff_delay(3) <= DEFAULT_MAX_BACKOFF_SECONDS


def test_a_declared_oversize_body_is_refused_before_a_single_byte_lands(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"Content-Length": "1048576"}, stream=Chunked([b"x" * 1024])
        )

    destination = tmp_path / "oversize.grib2"
    with build_client(handler) as client:
        with pytest.raises(MaxBytesExceeded, match="above the"):
            client.download(URL, destination, max_bytes=4096)
    assert not destination.exists()


def test_an_undeclared_oversize_body_is_abandoned_mid_stream(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Chunked([b"x" * 1024] * 16))

    destination = tmp_path / "runaway.grib2"
    with build_client(handler) as client:
        with pytest.raises(MaxBytesExceeded, match="exceeded the"):
            client.download(URL, destination, max_bytes=4096, chunk_size=1024)
    assert not destination.exists()


def test_bounded_in_memory_read_does_not_consume_the_rest_of_an_oversize_stream():
    yielded: list[int] = []

    class ObservedChunks(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(100):
                yielded.append(index)
                yield b"x" * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ObservedChunks())

    with build_client(handler) as client, pytest.raises(
        MaxBytesExceeded, match="exceeded the"
    ):
        client.get_bytes(URL, max_bytes=4096, chunk_size=1024)
    assert yielded == [0, 1, 2, 3, 4]


def test_bounded_in_memory_read_refuses_declared_oversize_before_iteration():
    yielded: list[int] = []

    class NeverRead(httpx.SyncByteStream):
        def __iter__(self):
            yielded.append(1)
            yield b"x"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"Content-Length": "9999"}, stream=NeverRead()
        )

    with build_client(handler) as client, pytest.raises(MaxBytesExceeded, match="above the"):
        client.get_bytes(URL, max_bytes=4096)
    assert yielded == []


def test_a_body_within_the_ceiling_is_written_whole(tmp_path: Path):
    payload = b"GRIB" + b"\x00" * 2044

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    destination = tmp_path / "ok.grib2"
    with build_client(handler) as client:
        assert client.download(URL, destination, max_bytes=4096, chunk_size=512) == len(
            payload
        )
    assert destination.read_bytes() == payload


def test_a_non_positive_ceiling_is_a_programming_error(tmp_path: Path):
    with build_client(lambda request: httpx.Response(200, content=b"")) as client:
        with pytest.raises(ValueError):
            client.download(URL, tmp_path / "never", max_bytes=0)


def test_range_requests_send_the_header_and_reject_a_server_that_ignores_it():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        value = request.headers["Range"]
        requested.append(value)
        if value == "bytes=100-199":
            return httpx.Response(206, headers={"Content-Range": "bytes 100-199/1000"}, content=b"x" * 100)
        return httpx.Response(206, headers={"Content-Range": "bytes 100-106/1000"}, content=b"partial")

    with build_client(handler) as client:
        assert client.get_range(URL, 100, 199) == b"x" * 100
        assert client.get_range(URL, 100, max_bytes=100) == b"partial"
        with pytest.raises(ValueError):
            client.get_range(URL, 200, 100)
    assert requested == ["bytes=100-199", "bytes=100-"]

    with build_client(lambda request: httpx.Response(206, content=b"partial")) as client:
        with pytest.raises(ValueError, match="finite byte ceiling"):
            client.get_range(URL, 100)

    with build_client(
        lambda request: httpx.Response(200, content=b"whole file")
    ) as client:
        with pytest.raises(RetriesExhausted, match="ignored the Range header"):
            client.get_range(URL, 0, 10)


def test_oversized_range_is_stopped_while_streaming_before_the_rest_is_read():
    yielded: list[int] = []

    class ObservedChunks(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(100):
                yielded.append(index)
                yield b"x" * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(206, headers={"Content-Range": "bytes 0-4095/100000"}, stream=ObservedChunks())

    with build_client(handler) as client, pytest.raises(MaxBytesExceeded, match="requested"):
        client.get_range(URL, 0, 4095)
    assert yielded == [0, 1, 2, 3, 4]


def test_range_that_cannot_fit_the_remaining_operation_budget_makes_no_request():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(206, headers={"Content-Range": "bytes 0-9/100"}, content=b"x" * 10)

    with build_client(handler) as client, acquisition_budget(9), pytest.raises(
        MaxBytesExceeded, match="only 9 bytes remain"
    ):
        client.get_range(URL, 0, 9)
    assert requests == []


@pytest.mark.parametrize("content_range", ["", "bytes 1-10/100", "bytes 0-8/100"])
def test_range_response_identity_must_match_the_request(content_range: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(206, headers={"Content-Range": content_range}, content=b"x" * 10)

    with build_client(handler) as client, pytest.raises(MaxBytesExceeded, match="Content-Range"):
        client.get_range(URL, 0, 9)


def test_operation_received_byte_bound_spans_multiple_streamed_requests(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Chunked([b"x" * 1024, b"y" * 1024]))

    with build_client(handler) as client, acquisition_budget(3072), pytest.raises(
        ReceivedBytesExceeded, match="3072"
    ):
        client.download(URL, tmp_path / "one", max_bytes=4096, chunk_size=1024)
        client.download(URL, tmp_path / "two", max_bytes=4096, chunk_size=1024)
    assert not (tmp_path / "two").exists()


def test_concatenated_ranges_stop_at_the_ceiling_and_leave_no_partial_file(
    tmp_path: Path,
):
    def handler(request: httpx.Request) -> httpx.Response:
        value = request.headers["Range"]
        start, end = (int(item) for item in value.removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {start}-{end}/10000"},
            content=b"y" * (end - start + 1),
        )

    destination = tmp_path / "subset.grib2"
    with build_client(handler) as client:
        assert (
            client.download_ranges(
                URL, destination, [(0, 1023), (2048, 3071)], max_bytes=4096
            )
            == 2048
        )
        with pytest.raises(MaxBytesExceeded):
            client.download_ranges(URL, destination, [(0, 1023)] * 8, max_bytes=4096)
    assert not destination.exists()


def test_per_host_pacing_delays_the_second_request_to_the_same_host(
    monkeypatch: pytest.MonkeyPatch,
):
    slept: list[float] = []
    monkeypatch.setattr(ingest_http.time, "sleep", slept.append)
    limiter = ingest_http.HostRateLimiter(min_interval_seconds=0.5)
    assert limiter.wait("dd.weather.gc.ca") == 0.0
    assert limiter.wait("dd.weather.gc.ca") > 0.0
    assert limiter.wait("noaa-gfs-bdp-pds.s3.amazonaws.com") == 0.0


def test_at_least_one_attempt_is_required():
    with pytest.raises(ValueError):
        PoliteClient(attempts=0)
