"""Declarative delivery identity, independent of retrieval and actual coverage.

Owning contract: api-first-source-delivery. Source adapters retain transport,
authentication, native time rules, decoding and finite caches.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceVariant(ContractModel):
    kind: Literal["deterministic", "observation", "member", "provider_statistic", "derived_statistic", "unknown"]
    member: str | None = None
    statistic: str | None = None
    quantile: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    threshold: float | None = Field(default=None, allow_inf_nan=False)
    comparison: str | None = None

    @model_validator(mode="after")
    def identity(self):
        if (self.kind == "member") != (self.member is not None):
            raise ValueError("only a member variant names a member")
        statistical = self.kind in ("provider_statistic", "derived_statistic")
        if statistical != (self.statistic is not None):
            raise ValueError("a statistical variant must name its statistic")
        if not statistical and any(value is not None for value in (self.quantile, self.threshold, self.comparison)):
            raise ValueError("statistic parameters require a statistical variant")
        if (self.threshold is None) != (self.comparison is None):
            raise ValueError("threshold and comparison must be supplied together")
        return self


class SourceCapability(ContractModel):
    """Implemented read path. Its declaration does not assert available data."""
    source_id: str
    product_id: str
    field: str
    variants: list[SourceVariant] = Field(min_length=1)
    levels: list[str] = Field(min_length=1)
    point: bool
    point_product: str | None = None
    native_series: bool
    point_time_kind: Literal["observation", "forecast"] | None = None
    directional_time_selection: bool = False
    run_selection: Literal["latest", "latest_previous", "not_applicable"]
    time_semantics: str
    coverage_description: str

    @model_validator(mode="after")
    def known_variant(self):
        if any(variant.kind == "unknown" for variant in self.variants):
            raise ValueError("an unknown reading identity cannot be a selectable capability")
        return self


class SourceConfiguration(ContractModel):
    """Safe configuration/acquisition disposition, separate from admission."""
    state: Literal["ready", "missing_configuration", "access_denied", "product_unavailable", "missing_compute", "acquisition_failed", "unknown"] = "unknown"
    reason: str = "This source delivery path has not been assessed"
    required_environment: list[str] = Field(default_factory=list)
    checked_at: datetime | None = None


class SourceReadingIdentity(ContractModel):
    """Identity of one actual reading; requested location stays separate."""
    source_id: str
    product_id: str
    field: str
    variant: SourceVariant
    level: str
    native_level: str | None = None
    run_time: datetime | None
    valid_time: datetime
    station_id: str | None = None
    sampled_latitude: float | None = None
    sampled_longitude: float | None = None
    artifact_revision: str | None = None


class SourceTransferReceipt(ContractModel):
    url: str = Field(max_length=2048)
    effective_url: str = Field(max_length=2048)
    http_status: int = Field(ge=100, le=599)
    request_headers: dict[str, str] = Field(max_length=16)
    response_headers: dict[str, str] = Field(max_length=16)
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_at: AwareDatetime


class SourceAcquisition(ContractModel):
    """Bounded native demand receipt, independent of storage or source admission."""
    source_id: str = Field(max_length=128)
    product_id: str = Field(max_length=128)
    provider_run_id: str | None = Field(default=None, max_length=128)
    run_time: AwareDatetime | None
    valid_time: AwareDatetime
    retrieval_time: AwareDatetime
    expires_at: AwareDatetime
    normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transport_receipts: tuple[SourceTransferReceipt, ...] = Field(max_length=12)

    @model_validator(mode="after")
    def bounded_receipt(self):
        if self.expires_at <= self.retrieval_time or len(self.model_dump_json().encode()) > 65536:
            raise ValueError("invalid or oversized native acquisition receipt")
        return self
