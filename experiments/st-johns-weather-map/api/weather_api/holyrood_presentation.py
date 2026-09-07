"""Experimental native-image readback helpers; no route or registry activation.

The original rendered legend/map remain in the unmodified producer GIF. There
is no machine-readable palette, geographic transform, or numerical pixel API.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Literal
from urllib.parse import urlsplit

from weather_api.holyrood_query import (
    HolyroodImageEvidence, HolyroodQueryService, HolyroodUnavailable, RadarImage,
)


def pair_revision(evidence: HolyroodImageEvidence) -> str:
    """Bind valid time and both phase digests, even if their bytes are identical."""
    identity = [evidence.source_id, evidence.valid_time.isoformat(),
                [(image.phase, image.receipt.sha256) for image in evidence.images]]
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def image_metadata(evidence: HolyroodImageEvidence) -> dict[str, Any]:
    """Describe original paired evidence without asserting freshness or geometry."""
    return {
        "source_id": evidence.source_id,
        "producer": "Environment and Climate Change Canada",
        "station_id": evidence.station_id,
        "product": evidence.product,
        "pair_revision": pair_revision(evidence),
        "valid_time": evidence.valid_time,
        "retained_until": evidence.retained_until,
        "cache_status": evidence.cache_status,
        "semantics": evidence.semantics,
        "source_quality": evidence.source_quality,
        "operational": evidence.operational,
        "presentation": {
            "encoding": "image/gif",
            "transformation": "unmodified-producer-image",
            "legend": "preserved-in-producer-image",
            "native_crs": None,
            "georeferencing": "not-established",
            "numeric_pixel_values": "unavailable",
        },
        "listing_receipt": asdict(evidence.listing_receipt),
        "images": [{
            "phase": image.phase,
            "source_filename": urlsplit(image.receipt.url).path.rsplit("/", 1)[-1],
            "width": image.width,
            "height": image.height,
            "frames": 1,
            "receipt": asdict(image.receipt),
        } for image in evidence.images],
    }


def retained_image(query: HolyroodQueryService, *, revision: str,
                   phase: Literal["Rain", "Snow"]) -> RadarImage:
    """Exact revision lookup only; no provider read or fallback to a newer pair."""
    if phase not in ("Rain", "Snow"):
        raise HolyroodUnavailable("CASHR image phase is not supported")
    evidence = query.retained_images()
    if pair_revision(evidence) != revision:
        raise HolyroodUnavailable("CASHR image revision is not retained")
    return next(image for image in evidence.images if image.phase == phase)
