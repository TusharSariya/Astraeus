"""Experimental CASHR image evidence cache; never a numeric point reader.

The retention TTL is a local memory policy, not a claim that imagery is current.
Only complete native Rain/Snow pairs replace the single cached revision.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx

from ingest.experimental.holyrood_radar import (
    BASE_URL, MAX_IMAGE_BYTES, MAX_LISTING_BYTES, _NAME, _time,
)
from ingest.http import USER_AGENT, parse_directory_listing
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

RETENTION_SECONDS = 60
DECODE_LIMITS = ProcessAllocationLimits(256 * 1024 * 1024, 1, MAX_IMAGE_BYTES, 4096, 4096)


class HolyroodUnavailable(RuntimeError):
    """No complete retained image evidence; no numerical fallback exists."""


@dataclass(frozen=True)
class ImageReceipt:
    url: str
    body_bytes: int
    sha256: str
    completed_at: datetime
    headers: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RadarImage:
    phase: str
    body: bytes
    width: int
    height: int
    receipt: ImageReceipt


@dataclass(frozen=True)
class HolyroodImageEvidence:
    valid_time: datetime
    images: tuple[RadarImage, RadarImage]
    listing_receipt: ImageReceipt
    retained_until: datetime
    cache_status: str = "miss"
    source_id: str = "eccc-holyrood-radar"
    station_id: str = "CASHR"
    product: str = "DPQPE"
    semantics: str = "rendered-image-only"
    source_quality: str = "unknown"
    operational: bool = False


def decode_image(body: bytes) -> dict[str, int]:
    result = run_bounded_process(
        command=[sys.executable, str(Path(__file__).with_name("holyrood_query_worker.py")), "{output}"],
        stdin=body, destination=None, limits=DECODE_LIMITS, require_output=False,
    )
    image = json.loads(result.stdout)
    if not isinstance(image, dict) or set(image) != {"width", "height", "frames"} or image["frames"] != 1:
        raise ValueError("invalid image metadata")
    return image


class HolyroodQueryService:
    """One finite revision, bounded fetches, coalesced misses and explicit refresh.

    No route or registry activation is implied by this experimental service.
    """

    def __init__(self, *, client: httpx.Client | None = None,
                 clock: Callable[[], datetime] | None = None,
                 decoder: Callable[[bytes], dict[str, int]] = decode_image) -> None:
        self._client = client or httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": USER_AGENT})
        self._clock = clock or (lambda: datetime.now(UTC))
        self._decoder = decoder
        self._lock = threading.Lock()
        self._cached: HolyroodImageEvidence | None = None

    def _fetch(self, url: str, cap: int) -> tuple[bytes, ImageReceipt]:
        with self._client.stream("GET", url, follow_redirects=False, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200:
                raise HolyroodUnavailable("CASHR provider request failed")
            if response.headers.get("content-encoding", "identity") != "identity":
                raise HolyroodUnavailable("CASHR encoded response refused")
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=16384):
                if len(body) + len(chunk) > cap:
                    raise HolyroodUnavailable("CASHR response exceeds byte ceiling")
                body.extend(chunk)
            completed_at = self._clock()
            safe = tuple((name, response.headers[name][:1024]) for name in
                         ("content-type", "content-length", "etag", "last-modified", "date") if name in response.headers)
        payload = bytes(body)
        return payload, ImageReceipt(url, len(payload), hashlib.sha256(payload).hexdigest(), completed_at, safe)

    def read_images(self, *, refresh: bool = False) -> HolyroodImageEvidence:
        # Requests already waiting when a refresh finishes reuse that revision.
        observed = self._cached
        with self._lock:
            now = self._clock()
            if self._cached is not None and now < self._cached.retained_until:
                if not refresh or self._cached is not observed:
                    return replace(self._cached, cache_status="hit")
            self._cached = None  # A failed replacement must never return expired bytes.
            try:
                listing, receipt = self._fetch(BASE_URL + "/", MAX_LISTING_BYTES)
                paired: dict[datetime, dict[str, str]] = {}
                for name in parse_directory_listing(listing.decode("utf-8"), suffixes=(".gif",)):
                    match = _NAME.fullmatch(name)
                    if match is None:
                        continue
                    stamp = _time(match["stamp"])
                    if stamp > receipt.completed_at:
                        continue
                    paired.setdefault(stamp, {})[match["phase"]] = name
                complete = [stamp for stamp, phases in paired.items() if set(phases) == {"Rain", "Snow"}]
                if not complete:
                    raise HolyroodUnavailable("CASHR has no native paired image evidence")
                valid_time = max(complete)
                images = []
                for phase in ("Rain", "Snow"):
                    body, image_receipt = self._fetch(BASE_URL + "/" + paired[valid_time][phase], MAX_IMAGE_BYTES)
                    metadata = self._decoder(body)
                    images.append(RadarImage(phase, body, metadata["width"], metadata["height"], image_receipt))
                # Expiry uses listing completion, so slow acquisition cannot reset retention.
                expiry = receipt.completed_at + timedelta(seconds=RETENTION_SECONDS)
                if self._clock() >= expiry:
                    raise HolyroodUnavailable("CASHR acquisition exceeded retention window")
                self._cached = HolyroodImageEvidence(valid_time, (images[0], images[1]), receipt, expiry,
                                                    cache_status="refresh" if refresh else "miss")
                return self._cached
            except HolyroodUnavailable:
                raise
            except Exception as error:
                raise HolyroodUnavailable("CASHR image evidence unavailable") from error
