"""Read-only public registered geometry for the desktop (no source admission)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from .models import StrictModel
from .sites import load_site_registry
from registry import site_audit


class PublicHorizon(StrictModel):
    site_id: str
    bearing_resolution_deg: float = Field(gt=0, le=360)
    elevation_deg: list[float]
    terrain_check_status: Literal["passed", "failed", "not_run"]
    terrain_check_note: str


class PublicSite(StrictModel):
    id: str
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float | None
    datum: str
    horizon: PublicHorizon
    registered_on: str
    registered_by: str
    geometry_note: str | None


class PublicSiteRegistry(StrictModel):
    operational: Literal[False] = False
    version: str
    sites: list[PublicSite]
    notice: str | None


router = APIRouter()


@router.get("/registry/sites", response_model=PublicSiteRegistry)
def get_sites() -> PublicSiteRegistry:
    registry = load_site_registry()
    records = site_audit.load_sites(site_audit.SITES_ROOT)
    sites = []
    for site in registry.sites:
        record = records.get(site.id)
        note = record.record.get("note") if isinstance(record, site_audit.Site) else None
        # The audited SiteSummary is already an explicit public-field allowlist;
        # only the registered geometry note is added, never the whole YAML record.
        sites.append(PublicSite(**asdict(site), geometry_note=note if isinstance(note, str) else None))
    public = {"sites": [site.model_dump(mode="json") for site in sites], "notice": registry.notice}
    version = hashlib.sha256(json.dumps(public, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return PublicSiteRegistry(version=version, sites=sites, notice=registry.notice)
