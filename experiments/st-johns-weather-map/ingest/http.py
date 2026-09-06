"""Polite HTTP access shared by every adapter.

Providers here are public goods with no contract behind them, so a single
client centralises identification, per-host pacing, bounded retries and hard
byte ceilings. Adapters never construct their own transport.
"""

from __future__ import annotations

import logging
import hashlib
import os
import random
import re
import threading
import time
from datetime import datetime, timezone
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Self
from urllib.parse import unquote, urlparse

import httpx

from .resources import charge_received, remaining_received

_log = logging.getLogger(__name__)

USER_AGENT = (
    "astraeus-weather-experiment/0.1 (research; contact tushar.sariya77@gmail.com)"
)


def _effective_request_headers(response: httpx.Response) -> dict[str, str]:
    """Non-secret effective headers that identify a public payload request."""
    allowed = {"accept", "accept-encoding", "if-none-match", "range", "user-agent"}
    return {key.lower(): value for key, value in response.request.headers.items() if key.lower() in allowed}

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_ATTEMPTS = 5
DEFAULT_BACKOFF_SECONDS = 0.5
DEFAULT_MAX_BACKOFF_SECONDS = 30.0
#: The gap between two requests to one host, in seconds. The default is
#: deliberately polite (two requests a second). A deployment that fetches
#: many small files from a provider that tolerates more - MSC Datamart
#: serves ~1,200 GRIB files per HRDPS run once the low-level profile is
#: requested, and at two a second that is ten minutes of waiting whatever the
#: link does - may lower it through ``WEATHER_HTTP_MIN_HOST_INTERVAL``. The
#: client counts every 429 it is answered with (``retry_counts``) and logs
#: them, so a value that turns out to be impolite is visible in the worker
#: log rather than silently absorbed by the retry loop.
DEFAULT_MIN_HOST_INTERVAL_SECONDS = 0.5
DEFAULT_TIMEOUT_SECONDS = 60.0


def min_host_interval_from_env(
    default: float = DEFAULT_MIN_HOST_INTERVAL_SECONDS,
) -> float:
    """``WEATHER_HTTP_MIN_HOST_INTERVAL`` as seconds, else ``default``; never negative."""
    raw = os.environ.get("WEATHER_HTTP_MIN_HOST_INTERVAL", "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


class MaxBytesExceeded(RuntimeError):
    """A response body grew past the caller's ceiling and was abandoned."""


class RetriesExhausted(RuntimeError):
    """Every permitted attempt failed with a retryable condition."""


class HostRateLimiter:
    """Serialises requests per host so one provider is never hammered."""

    def __init__(
        self, min_interval_seconds: float = DEFAULT_MIN_HOST_INTERVAL_SECONDS
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._next_allowed: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def wait(self, host: str) -> float:
        with self._lock:
            now = time.monotonic()
            earliest = self._next_allowed[host]
            delay = max(0.0, earliest - now)
            self._next_allowed[host] = max(now, earliest) + self.min_interval_seconds
        if delay:
            time.sleep(delay)
        return delay


def parse_retry_after(value: str | None) -> float | None:
    """Honour ``Retry-After`` in its delta-seconds form; ignore HTTP dates."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return max(0.0, seconds)


def backoff_delay(
    attempt: int,
    *,
    base: float = DEFAULT_BACKOFF_SECONDS,
    cap: float = DEFAULT_MAX_BACKOFF_SECONDS,
    jitter: float | None = None,
) -> float:
    """Exponential backoff with full jitter, so retries never synchronise."""
    ceiling = min(cap, base * (2 ** max(0, attempt - 1)))
    fraction = random.random() if jitter is None else jitter
    return ceiling * fraction


class _HrefCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                self.hrefs.append(value)


def parse_directory_listing(html: str, *, suffixes: tuple[str, ...] = ()) -> list[str]:
    """Return entry names from an Apache/nginx index page.

    ECCC Datamart and DWD both expose plain autoindex HTML rather than an API,
    so listing is the only discovery mechanism available.
    """
    collector = _HrefCollector()
    collector.feed(html)
    names: list[str] = []
    for href in collector.hrefs:
        if href.startswith(("?", "#", "/")) or "://" in href or href in {"..", "../"}:
            continue
        name = unquote(href)
        if name in names:
            continue
        if suffixes and not name.endswith(suffixes):
            continue
        names.append(name)
    return names


@dataclass
class PoliteClient:
    """A retrying, rate-limited, identified HTTP client."""

    attempts: int = DEFAULT_ATTEMPTS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    min_host_interval_seconds: float = field(default_factory=min_host_interval_from_env)
    limiter: HostRateLimiter = field(init=False)
    _client: httpx.Client = field(init=False)
    #: Retryable statuses seen, by code, across the client's life. A 429 here
    #: means the provider asked us to slow down; a run that shows any must be
    #: read as having been throttled, and the host interval raised.
    retry_counts: Counter = field(init=False, default_factory=Counter)

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least one")
        self.limiter = HostRateLimiter(self.min_host_interval_seconds)
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        stream: bool = False,
    ):
        host = urlparse(url).netloc
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            self.limiter.wait(host)
            try:
                request = self._client.build_request(
                    method, url, headers=dict(headers or {})
                )
                response = self._client.send(request, stream=stream)
            except httpx.TransportError as error:
                last_error = error
                if attempt == self.attempts:
                    break
                time.sleep(backoff_delay(attempt))
                continue
            if response.status_code in RETRY_STATUS and attempt < self.attempts:
                retry_after = parse_retry_after(response.headers.get("Retry-After"))
                self.retry_counts[response.status_code] += 1
                if response.status_code == 429:
                    _log.warning(
                        "429 from %s (attempt %d/%d, Retry-After %s, %d so far): slow down",
                        host,
                        attempt,
                        self.attempts,
                        retry_after,
                        self.retry_counts[429],
                    )
                try:
                    self._charge_error_body(response)
                finally:
                    response.close()
                time.sleep(
                    retry_after if retry_after is not None else backoff_delay(attempt)
                )
                continue
            if response.is_error:
                self._charge_error_body(response)
            response.raise_for_status()
            return response
        raise RetriesExhausted(
            f"{method} {url} failed after {self.attempts} attempts"
        ) from last_error

    @staticmethod
    def _charge_error_body(response: httpx.Response) -> None:
        """Count bounded retry/error bodies without buffering them."""
        if remaining_received() is None:
            return
        for chunk in response.iter_bytes(1 << 10):
            charge_received(len(chunk))

    def get(
        self, url: str, *, headers: Mapping[str, str] | None = None
    ) -> httpx.Response:
        if remaining_received() is None:
            return self._request("GET", url, headers=headers)
        response = self._request("GET", url, headers=headers, stream=True)
        chunks: list[bytes] = []
        try:
            for chunk in response.iter_bytes(1 << 16):
                charge_received(len(chunk))
                chunks.append(chunk)
            response._content = b"".join(chunks)
            return response
        except BaseException:
            response.close()
            raise

    def get_bytes_with_headers(
        self,
        url: str,
        *,
        max_bytes: int,
        headers: Mapping[str, str] | None = None,
        chunk_size: int = 1 << 16,
    ) -> tuple[bytes, Mapping[str, str]]:
        """Read a decoded response body under a hard byte ceiling."""
        body, response_headers, _completed = self.get_bytes_with_headers_completed(
            url, max_bytes=max_bytes, headers=headers, chunk_size=chunk_size
        )
        return body, response_headers

    def get_bytes_with_headers_completed(
        self,
        url: str,
        *,
        max_bytes: int,
        headers: Mapping[str, str] | None = None,
        chunk_size: int = 1 << 16,
    ) -> tuple[bytes, Mapping[str, str], datetime]:
        """As :meth:`get_bytes_with_headers`, with UTC completion after the final byte.

        Adapters that retain raw-response provenance use this timestamp instead
        of recording a later bookkeeping time.
        """
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        response = self._request("GET", url, headers=headers, stream=True)
        try:
            declared = response.headers.get("Content-Length")
            if declared is not None:
                try:
                    declared_bytes = int(declared)
                except ValueError as error:
                    raise MaxBytesExceeded(
                        f"{url} carries an invalid Content-Length {declared!r}"
                    ) from error
                if declared_bytes < 0 or declared_bytes > max_bytes:
                    raise MaxBytesExceeded(
                        f"{url} declares {declared_bytes} bytes, above the {max_bytes} byte ceiling"
                    )
            chunks: list[bytes] = []
            read = 0
            for chunk in response.iter_bytes(chunk_size):
                charge_received(len(chunk))
                read += len(chunk)
                if read > max_bytes:
                    raise MaxBytesExceeded(
                        f"{url} exceeded the {max_bytes} byte ceiling"
                    )
                chunks.append(chunk)
            return b"".join(chunks), dict(response.headers), datetime.now(timezone.utc)
        finally:
            response.close()

    def get_bytes_with_receipt(
        self, url: str, *, max_bytes: int, chunk_size: int = 1 << 16
    ) -> tuple[bytes, dict[str, object]]:
        """Read a bounded body and retain effective transport identity."""
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        response = self._request("GET", url, stream=True)
        try:
            declared = response.headers.get("Content-Length")
            if declared is not None and (not declared.isdigit() or int(declared) > max_bytes):
                raise MaxBytesExceeded(f"{url} carries invalid or oversized Content-Length {declared!r}")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes(chunk_size):
                charge_received(len(chunk))
                total += len(chunk)
                if total > max_bytes:
                    raise MaxBytesExceeded(f"{url} exceeded the {max_bytes} byte ceiling")
                chunks.append(chunk)
            completed = datetime.now(timezone.utc)
            payload = b"".join(chunks)
            return payload, {
                "url": str(response.request.url),
                "request_headers": _effective_request_headers(response),
                "response_headers": dict(response.headers),
                "completed_at": completed.isoformat(),
                "byte_size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        finally:
            response.close()

    def get_text(self, url: str) -> str:
        return self.get(url).text

    def get_bytes(self, url: str, *, max_bytes: int, chunk_size: int = 1 << 20) -> bytes:
        """Read a small response into memory under the same hard ceiling as downloads."""
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        response = self._request("GET", url, stream=True)
        chunks: list[bytes] = []
        total = 0
        try:
            declared = response.headers.get("Content-Length")
            if declared is not None and declared.isdigit() and int(declared) > max_bytes:
                raise MaxBytesExceeded(f"{url} declares {declared} bytes, above the {max_bytes} byte ceiling")
            for chunk in response.iter_bytes(chunk_size):
                charge_received(len(chunk))
                total += len(chunk)
                if total > max_bytes:
                    raise MaxBytesExceeded(f"{url} exceeded the {max_bytes} byte ceiling")
                chunks.append(chunk)
        finally:
            response.close()
        return b"".join(chunks)

    def get_range(self, url: str, start: int, end: int | None = None, *, max_bytes: int | None = None) -> bytes:
        """Fetch one byte range. GRIB2 ``.idx`` subsetting depends on this."""
        payload, _request_headers, _response_headers, _completed = self.get_range_with_headers_completed(
            url, start, end, max_bytes=max_bytes
        )
        return payload

    def get_range_with_headers_completed(
        self, url: str, start: int, end: int | None = None, *, max_bytes: int | None = None
    ) -> tuple[bytes, dict[str, str], dict[str, str], datetime]:
        """Fetch one range and retain its exact transport receipt."""
        if start < 0 or (end is not None and end < start):
            raise ValueError("invalid byte range")
        expected = None if end is None else end - start + 1
        operation_remaining = remaining_received()
        available = [value for value in (max_bytes, operation_remaining) if value is not None]
        if expected is not None and any(value < expected for value in available):
            raise MaxBytesExceeded(
                f"{url} requested {expected} bytes but only {min(available)} bytes remain in the finite ceiling"
            )
        ceiling = min(([expected] if expected is not None else []) + available, default=None)
        if ceiling is None or ceiling <= 0:
            raise ValueError("an open-ended range requires a positive finite byte ceiling")
        header = f"bytes={start}-{'' if end is None else end}"
        request_headers = {"Range": header, "Accept-Encoding": "identity", "User-Agent": USER_AGENT}
        response = self._request("GET", url, headers=request_headers, stream=True)
        if response.status_code != 206:
            response.close()
            raise RetriesExhausted(
                f"{url} ignored the Range header (status {response.status_code})"
            )
        content_range = response.headers.get("Content-Range", "")
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(?:\d+|\*)", content_range)
        if match is None:
            response.close()
            raise MaxBytesExceeded(f"{url} returned invalid Content-Range {content_range!r}")
        returned_start, returned_end = (int(value) for value in match.groups())
        if returned_start != start or returned_end < returned_start or (end is not None and returned_end != end):
            response.close()
            raise MaxBytesExceeded(
                f"{url} returned Content-Range {content_range!r} for requested {header}"
            )
        response_bytes = returned_end - returned_start + 1
        if response_bytes > ceiling:
            response.close()
            raise MaxBytesExceeded(f"{url} range response declares {response_bytes} bytes above the {ceiling} byte ceiling")
        chunks: list[bytes] = []
        read = 0
        try:
            for chunk in response.iter_bytes(1 << 10):
                charge_received(len(chunk))
                read += len(chunk)
                if read > ceiling:
                    raise MaxBytesExceeded(f"{url} returned more than the requested {ceiling}-byte range")
                chunks.append(chunk)
            completed = datetime.now(timezone.utc)
        finally:
            response.close()
        payload = b"".join(chunks)
        if len(payload) != response_bytes:
            raise MaxBytesExceeded(
                f"{url} returned {len(payload)} bytes for Content-Range {content_range!r}"
            )
        return payload, _effective_request_headers(response), dict(response.headers), completed

    def list_directory(
        self, url: str, *, suffixes: tuple[str, ...] = (), max_bytes: int | None = None
    ) -> list[str]:
        if max_bytes is None:
            text = self.get_text(url)
        else:
            text = self.get_bytes(url, max_bytes=max_bytes).decode("utf-8", errors="strict")
        return parse_directory_listing(text, suffixes=suffixes)

    def download(
        self,
        url: str,
        destination: Path,
        *,
        max_bytes: int,
        headers: Mapping[str, str] | None = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Stream to ``destination``, aborting mid-stream past ``max_bytes``.

        Aborting during the stream — not after — is what keeps a single
        mis-sized global file from consuming the 25 GiB cap.
        """
        written, _headers = self.download_with_headers(url, destination, max_bytes=max_bytes, headers=headers, chunk_size=chunk_size)
        return written

    def download_with_headers(self, url: str, destination: Path, *, max_bytes: int, headers: Mapping[str, str] | None = None, chunk_size: int = 1 << 20) -> tuple[int, dict[str, str]]:
        """``download``, also returning the response headers.

        The space-weather receipts record the provider's own ``Last-Modified``
        beside the byte count and digest, and that header is only available
        from the streamed response, so this variant hands it back.
        """
        receipt = self.download_with_receipt(
            url, destination, max_bytes=max_bytes, headers=headers, chunk_size=chunk_size
        )
        return int(receipt["byte_size"]), dict(receipt["response_headers"])

    def download_with_receipt(self, url: str, destination: Path, *, max_bytes: int,
                              headers: Mapping[str, str] | None = None,
                              chunk_size: int = 1 << 20) -> dict[str, object]:
        """Stream one file and timestamp immediately after its final byte."""
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        response = self._request("GET", url, headers=headers, stream=True)
        digest = hashlib.sha256()
        try:
            response_headers = {str(key): str(value) for key, value in response.headers.items()}
            declared = response.headers.get("Content-Length")
            if (
                declared is not None
                and declared.isdigit()
                and int(declared) > max_bytes
            ):
                raise MaxBytesExceeded(
                    f"{url} declares {declared} bytes, above the {max_bytes} byte ceiling"
                )
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size):
                    charge_received(len(chunk))
                    written += len(chunk)
                    if written > max_bytes:
                        raise MaxBytesExceeded(
                            f"{url} exceeded the {max_bytes} byte ceiling"
                        )
                    handle.write(chunk)
                    digest.update(chunk)
            completed = datetime.now(timezone.utc)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        finally:
            response.close()
        return {
            "url": str(response.request.url),
            "request_headers": _effective_request_headers(response),
            "response_headers": response_headers,
            "completed_at": completed,
            "byte_size": written,
            "sha256": digest.hexdigest(),
        }

    def download_ranges(
        self,
        url: str,
        destination: Path,
        ranges: Iterator[tuple[int, int | None]] | list[tuple[int, int | None]],
        *,
        max_bytes: int,
    ) -> int:
        """Concatenate selected byte ranges into one local file."""
        written, receipts = self.download_ranges_with_receipts(
            url, destination, ranges, max_bytes=max_bytes
        )
        self.last_range_receipts = receipts
        return written

    def download_ranges_with_receipts(
        self,
        url: str,
        destination: Path,
        ranges: Iterator[tuple[int, int | None]] | list[tuple[int, int | None]],
        *,
        max_bytes: int,
    ) -> tuple[int, list[dict[str, object]]]:
        """Concatenate ranges and return one final-byte receipt per request."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        receipts: list[dict[str, object]] = []
        try:
            with destination.open("wb") as handle:
                for start, end in ranges:
                    payload, request_headers, response_headers, completed = self.get_range_with_headers_completed(
                        url, start, end, max_bytes=max_bytes - written
                    )
                    written += len(payload)
                    if written > max_bytes:
                        raise MaxBytesExceeded(f"{url} range set exceeded the {max_bytes} byte ceiling")
                    handle.write(payload)
                    receipts.append({
                        "url": url,
                        "request_headers": request_headers,
                        "response_headers": response_headers,
                        "completed_at": completed.isoformat(),
                        "byte_size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    })
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return written, receipts
