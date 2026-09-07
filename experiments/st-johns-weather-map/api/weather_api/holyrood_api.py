"""Experimental exact-time native CASHR image delivery; no numerical radar API."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, ConfigDict

from weather_api.holyrood_presentation import image_metadata, retained_image
from weather_api.holyrood_query import HolyroodQueryService, HolyroodUnavailable

PREFIX = "/sources/eccc-holyrood-cashr-dpqpe/images"
router = APIRouter(tags=["experimental-native-images"])


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HolyroodReceipt(ClosedModel):
    url: str
    body_bytes: int
    sha256: str
    completed_at: datetime
    headers: tuple[tuple[str, str], ...]


class HolyroodPresentation(ClosedModel):
    encoding: Literal["image/gif"]
    transformation: Literal["unmodified-producer-image"]
    legend: Literal["preserved-in-producer-image"]
    native_crs: None
    georeferencing: Literal["not-established"]
    numeric_pixel_values: Literal["unavailable"]


class HolyroodImageMetadata(ClosedModel):
    phase: Literal["Rain", "Snow"]
    source_filename: str
    width: int
    height: int
    frames: Literal[1]
    receipt: HolyroodReceipt
    image_url: str


class HolyroodImagesResponse(ClosedModel):
    source_id: Literal["eccc-holyrood-cashr-dpqpe"]
    producer: Literal["Environment and Climate Change Canada"]
    station_id: Literal["CASHR"]
    product: str
    pair_revision: str
    valid_time: datetime
    retained_until: datetime
    cache_status: Literal["hit", "miss", "refresh"]
    semantics: Literal["rendered-image-only"]
    source_quality: Literal["unknown"]
    scientific_freshness: Literal["unknown"] = "unknown"
    primary: Literal[False] = False
    operational: Literal[False]
    presentation: HolyroodPresentation
    listing_receipt: HolyroodReceipt
    images: tuple[HolyroodImageMetadata, HolyroodImageMetadata]


@lru_cache(maxsize=1)
def holyrood_service() -> HolyroodQueryService:
    return HolyroodQueryService()


@router.get(PREFIX, response_model=HolyroodImagesResponse)
def get_holyrood_images(
    response: Response,
    valid_time: Annotated[datetime, Query(description="Exact paired native filename UTC time; no nearest/latest substitution")],
    refresh: bool = False,
    query: HolyroodQueryService = Depends(holyrood_service),
) -> HolyroodImagesResponse:
    if valid_time.tzinfo is None or valid_time.utcoffset() is None:
        raise HTTPException(422, "valid_time must include a timezone")
    try:
        evidence = query.read_images(refresh=refresh, valid_time=valid_time)
    except HolyroodUnavailable:
        raise HTTPException(503, "CASHR selected paired image evidence unavailable", headers={"Cache-Control": "no-store"}) from None
    metadata = image_metadata(evidence)
    for image in metadata["images"]:
        image["image_url"] = f'{PREFIX}/{metadata["pair_revision"]}/{image["phase"]}.gif'
    response.headers["Cache-Control"] = "no-store"
    return HolyroodImagesResponse.model_validate(metadata)


@router.get(PREFIX + "/{revision}/{phase}.gif", response_class=Response,
            responses={200: {"content": {"image/gif": {"schema": {"type": "string", "format": "binary"}}}}})
def get_holyrood_image(
    revision: Annotated[str, Path(pattern="^[0-9a-f]{64}$")],
    phase: Literal["Rain", "Snow"],
    query: HolyroodQueryService = Depends(holyrood_service),
) -> Response:
    try:
        image = retained_image(query, revision=revision, phase=phase)
    except HolyroodUnavailable:
        raise HTTPException(404, "CASHR exact image revision is not retained", headers={"Cache-Control": "no-store"}) from None
    return Response(image.body, media_type="image/gif", headers={
        "ETag": f'"{image.receipt.sha256}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })
