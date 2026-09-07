"""Private lightning experiment receipts; public integration is separately gated."""
from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from .models import StrictModel, _BoundedUrl, _BoundedHeaders, _SHA256, _BoundedName

LIGHTNING_METADATA_MAX_BYTES = 16 * 1024


class LightningDemandRequest(StrictModel):
    source_id: Literal["eccc-lightning"] = "eccc-lightning"
    product: Literal["Lightning_2.5km_Density"] = "Lightning_2.5km_Density"
    selected_time: AwareDatetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    capabilities_url: _BoundedUrl
    sample_url: _BoundedUrl


class LightningTransportReceipt(StrictModel):
    kind: Literal["capabilities", "sample"]
    url: _BoundedUrl
    request_headers: _BoundedHeaders
    response_headers: _BoundedHeaders
    body_bytes: int = Field(gt=0, le=256 * 1024)
    body_sha256: _SHA256
    completed_at: AwareDatetime


class LightningAcquisition(StrictModel):
    request: LightningDemandRequest
    native_valid_time: AwareDatetime
    transport_receipts: tuple[LightningTransportReceipt, LightningTransportReceipt]
    cached_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bound_metadata(self):
        if self.expires_at <= self.cached_at:
            raise ValueError("lightning cache expiry must follow admission")
        if tuple(item.kind for item in self.transport_receipts) != ("capabilities", "sample"):
            raise ValueError("lightning acquisition requires capabilities then sample receipts")
        if len(self.model_dump_json().encode()) > LIGHTNING_METADATA_MAX_BYTES:
            raise ValueError("lightning acquisition metadata exceeds its byte ceiling")
        return self


class LightningDemandUnavailable(StrictModel):
    source_id: Literal["eccc-lightning"] = "eccc-lightning"
    reason: Literal["unsupported_time", "refresh_failed", "query_failed"]
    error_type: _BoundedName
    expired_acquisition: LightningAcquisition | None = None
    values_withheld: Literal[True] = True


