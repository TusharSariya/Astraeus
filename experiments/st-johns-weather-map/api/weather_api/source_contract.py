"""Declarative delivery identity, independent of retrieval and actual coverage.

Owning contract: api-first-source-delivery. Source adapters retain transport,
authentication, native time rules, decoding and finite caches.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    native_series: bool
    run_selection: Literal["latest", "latest_previous", "not_applicable"]
    time_semantics: str
    coverage_description: str


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
    run_time: datetime | None
    valid_time: datetime
    station_id: str | None = None
    sampled_latitude: float | None = None
    sampled_longitude: float | None = None
    artifact_revision: str | None = None
