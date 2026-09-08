"""Bounded, nonpublishable CASHR DPQPE image acquisition.

The public Datamart exposes rendered GIFs.  Their palette is not an approved
numeric field encoding, so this module preserves source bytes and provenance
only; it never infers a rate, radar moment, geometry, or native volume.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ingest.contract import AdapterUnavailable, Artifact, DiscoveryBounds, FetchWindow, ResourceBounds, RunCandidate, RunResult
from ingest.http import MaxBytesExceeded, PoliteClient, RetriesExhausted, parse_directory_listing
from ingest.manifest import declared_classes, unresolved_manifest_validation

UTC = timezone.utc
BASE_URL = "https://dd.weather.gc.ca/today/radar/DPQPE/GIF/CASHR"
MAX_LISTING_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 512 * 1024
MAX_GIF_PIXELS = 4096 * 4096
RECEIPT_HEADERS = ("content-type", "content-length", "etag", "last-modified", "date")
_NAME = re.compile(r"^(?P<stamp>\d{8}T\d{4}Z)_MSC_Radar-DPQPE_CASHR_(?P<phase>Rain|Snow)\.gif$")


def _time(stamp: str) -> datetime:
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%MZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise AdapterUnavailable(f"eccc-holyrood-radar: invalid DPQPE filename time {stamp!r}") from error


def _receipt(url: str, body: bytes, headers: dict[str, str], completed_at: datetime) -> dict[str, Any]:
    return {
        "url": url,
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "completed_at": completed_at.isoformat(),
        "headers": {name: value for name in RECEIPT_HEADERS if (value := headers.get(name)) is not None},
    }


def _gif_metadata(body: bytes) -> dict[str, int]:
    """Validate bounded static GIF structure without decoding pixel values."""
    if len(body) < 14 or not body.startswith((b"GIF87a", b"GIF89a")):
        raise ValueError("missing GIF header or logical screen descriptor")
    width, height = int.from_bytes(body[6:8], "little"), int.from_bytes(body[8:10], "little")
    if not width or not height or width * height > MAX_GIF_PIXELS:
        raise ValueError(f"invalid or oversized GIF dimensions {width}x{height}")
    offset = 13
    if body[10] & 0x80:
        offset += 3 * (2 ** ((body[10] & 0x07) + 1))
    frames = 0
    while offset < len(body):
        marker = body[offset]
        offset += 1
        if marker == 0x3B:
            if offset != len(body) or frames != 1:
                raise ValueError("GIF must contain exactly one complete image frame")
            return {"width": width, "height": height, "frames": frames}
        if marker == 0x21:
            if offset >= len(body): raise ValueError("truncated GIF extension label")
            offset += 1
        elif marker == 0x2C:
            if offset + 9 > len(body): raise ValueError("truncated GIF image descriptor")
            left = int.from_bytes(body[offset:offset + 2], "little")
            top = int.from_bytes(body[offset + 2:offset + 4], "little")
            frame_width = int.from_bytes(body[offset + 4:offset + 6], "little")
            frame_height = int.from_bytes(body[offset + 6:offset + 8], "little")
            if not frame_width or not frame_height:
                raise ValueError("GIF image descriptor has zero width or height")
            if left + frame_width > width or top + frame_height > height:
                raise ValueError("GIF image descriptor extends outside the logical canvas")
            packed = body[offset + 8]
            offset += 9
            if packed & 0x80: offset += 3 * (2 ** ((packed & 0x07) + 1))
            if offset >= len(body): raise ValueError("truncated GIF image data")
            offset += 1  # LZW minimum code size
            frames += 1
        else:
            raise ValueError("invalid GIF block marker")
        while True:
            if offset >= len(body): raise ValueError("truncated GIF sub-block")
            size = body[offset]
            offset += 1
            if size == 0: break
            offset += size
            if offset > len(body): raise ValueError("truncated GIF sub-block payload")
    raise ValueError("GIF has no trailer")


class HolyroodDPQPEAdapter:
    """Acquire the paired native CASHR DPQPE rendered products without promotion."""

    source_id = "eccc-holyrood-cashr-dpqpe"
    adapter_version = "eccc-holyrood-cashr-dpqpe-v1"
    product = "Holyrood CASHR native DPQPE rendered imagery"

    def __init__(self, client: PoliteClient | None = None, *, base_url: str = BASE_URL) -> None:
        self._client = client or PoliteClient()
        self._base_url = base_url.rstrip("/")

    def discovery_bounds(self, _window: FetchWindow) -> DiscoveryBounds:
        return DiscoveryBounds(received_bytes=MAX_LISTING_BYTES)

    def resource_bounds(self, _candidate: RunCandidate, _window: FetchWindow) -> ResourceBounds:
        # Hard streaming ceilings, not a claim that the unregistered experiment
        # can be scheduled or published.
        return ResourceBounds(store_bytes=2 * MAX_IMAGE_BYTES, filesystem_bytes=2 * MAX_IMAGE_BYTES,
                              margin_bytes=2 * MAX_IMAGE_BYTES, received_bytes=2 * MAX_IMAGE_BYTES)

    def discover(self, _window: FetchWindow) -> list[RunCandidate]:
        listing_url = f"{self._base_url}/"
        try:
            raw, headers = self._client.get_bytes_with_headers(listing_url, max_bytes=MAX_LISTING_BYTES)
            completed_at = datetime.now(UTC)
            names = parse_directory_listing(raw.decode("utf-8", errors="strict"), suffixes=(".gif",))
        except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, UnicodeError, OSError, ValueError) as error:
            raise AdapterUnavailable(f"{self.source_id}: invalid or oversized CASHR directory listing: {error}") from error
        paired: dict[datetime, dict[str, str]] = {}
        for name in names:
            match = _NAME.fullmatch(name)
            if match is None:
                continue
            paired.setdefault(_time(match["stamp"]), {})[match["phase"].lower()] = name
        complete = [(moment, products) for moment, products in paired.items() if set(products) == {"rain", "snow"}]
        if not complete:
            raise AdapterUnavailable(f"{self.source_id}: CASHR listing has no paired non-contingency Rain/Snow DPQPE GIF")
        valid_time, products = max(complete, key=lambda item: item[0])
        receipt = _receipt(listing_url, raw, headers, completed_at)
        return [RunCandidate(
            provider_run_id=f"CASHR-DPQPE-{valid_time.strftime('%Y%m%dT%H%MZ')}-{receipt['body_sha256'][:12]}",
            run_time=valid_time,
            urls=[f"{self._base_url}/{products[name]}" for name in ("rain", "snow")],
            detail={"valid_times": [valid_time.isoformat()], "products": products, "listing_receipt": receipt},
        )]

    def fetch(self, candidate: RunCandidate, _window: FetchWindow, workdir: Path) -> RunResult:
        products = candidate.detail.get("products")
        listing = candidate.detail.get("listing_receipt")
        if not isinstance(products, dict) or set(products) != {"rain", "snow"} or not isinstance(listing, dict):
            raise AdapterUnavailable(f"{self.source_id}: candidate is missing paired products or listing receipt")
        validation = unresolved_manifest_validation(self.source_id, "rendered CASHR GIF has no owner-approved numeric field or image API contract")
        workdir.mkdir(parents=True, exist_ok=True)
        artifacts: list[Artifact] = []
        completions: list[datetime] = []
        try:
            for phase in ("rain", "snow"):
                name = products[phase]
                match = _NAME.fullmatch(str(name))
                if match is None or _time(match["stamp"]) != candidate.run_time:
                    raise AdapterUnavailable(f"{self.source_id}: invalid {phase} candidate filename")
                url = f"{self._base_url}/{name}"
                try:
                    body, headers = self._client.get_bytes_with_headers(url, max_bytes=MAX_IMAGE_BYTES)
                    completed_at = datetime.now(UTC)
                except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, OSError, ValueError) as error:
                    raise AdapterUnavailable(f"{self.source_id}: unavailable {phase} DPQPE image: {error}") from error
                try:
                    image = _gif_metadata(body)
                except ValueError as error:
                    raise AdapterUnavailable(f"{self.source_id}: {phase} DPQPE payload is not a complete bounded GIF: {error}") from error
                output = workdir / f"cashr-dpqpe-{phase}.gif"
                output.write_bytes(body)
                artifact_sha = hashlib.sha256(body).hexdigest()
                receipt = _receipt(url, body, headers, completed_at)
                receipts = {"listing": dict(listing), "image": receipt}
                artifacts.append(Artifact(f"cashr-dpqpe-{phase}", "image/gif", output, {
                "source_id": self.source_id, "producer": "Environment and Climate Change Canada", "product": self.product,
                "station": {"id": "CASHR", "name": "Holyrood"}, "phase": phase,
                "source_filename": name, "source_uri": url, "provider_run_id": candidate.provider_run_id,
                "run_time": candidate.run_time.isoformat() if candidate.run_time else None,
                "valid_times": [candidate.run_time.isoformat()] if candidate.run_time else [],
                "acquisition": receipts, "upstream_sha256": receipt["body_sha256"],
                "artifact_sha256": artifact_sha, "sha256": artifact_sha,
                "image": image,
                "field_dispositions": {
                    f"dpqpe_{phase}_rendered_image": "retrieved",
                    f"dpqpe_{phase}_rate": "deferred_no_palette_or_canonical_field_contract",
                    "dual_polarization_processing": "documented_producer_processing_not_a_retrieved_moment",
                    "independent_dual_polarization_moments": "unsupported_no_public_selected_bytes",
                    "raw_volume": "unsupported_no_verified_public_path",
                    "contingency_composite": "excluded_not_native_cashr",
                },
                # The validator's QC verdict is only the structural manifest
                # gate.  ECCC supplies no provider quality flag in this GIF,
                # so it remains unknown rather than inheriting that verdict.
                "quality": validation.as_quality(),
                "source_qc": {"status": "unknown", "flags": ["provider_quality_not_exposed_in_rendered_gif"]},
                "coverage": {"status": "image-only", "station": "CASHR"},
                "operational": False, "adapter_version": self.adapter_version,
                **declared_classes(["retrieved"]),
                }))
                completions.append(completed_at)
        except BaseException:
            for artifact in artifacts:
                artifact.payload_path.unlink(missing_ok=True)
            raise
        return RunResult(source_id=self.source_id, provider_run_id=candidate.provider_run_id, run_time=candidate.run_time,
                         retrieved_at=max(completions), complete=validation.complete, qc_passed=validation.qc_passed,
                         artifacts=artifacts, native_crs=None,
                         notes="paired native rendered DPQPE GIFs retained; manifest unresolved and publication prohibited")
