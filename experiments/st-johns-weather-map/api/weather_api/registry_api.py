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


class PublicCamera(StrictModel):
    id: str
    name: str
    source_id: str
    operator: str
    status: str
    latitude: float | None
    longitude: float | None
    position_surveyed: bool
    bearing_deg: float | None
    horizontal_fov_deg: float | None
    vertical_fov_deg: float | None
    geometry_validation: str
    registration_complete: bool
    missing_registration: list[str]
    declared_retrieval_eligible: bool
    refusal_code: str | None
    image_delivery_implemented: Literal[False] = False


class PublicCameraRegistry(StrictModel):
    operational: Literal[False] = False
    version: str
    cameras: list[PublicCamera]
    notices: list[str]


@router.get('/registry/cameras', response_model=PublicCameraRegistry)
def get_cameras() -> PublicCameraRegistry:
    from registry import camera_audit
    cameras = []
    notices = []
    for identity, entry in sorted(camera_audit.load_cameras().items()):
        if isinstance(entry, camera_audit.CameraError):
            # Audit exceptions may include private endpoint/configuration values.
            notices.append(f'{identity}: registration could not be validated')
            continue
        record = entry.record
        verdict = camera_audit.audit_camera(entry)
        refusal = camera_audit.retrieval_allowed(entry)
        cameras.append(PublicCamera(
            id=entry.camera_id, name=record['name'], source_id=record['source_id'], operator=record['operator'],
            status=entry.status, latitude=record['position']['latitude'], longitude=record['position']['longitude'],
            position_surveyed=record['position']['surveyed'], bearing_deg=record['orientation']['bearing_deg'],
            horizontal_fov_deg=record['orientation']['hfov_deg'], vertical_fov_deg=record['orientation']['vfov_deg'],
            geometry_validation=record['geometry_validation']['status'], registration_complete=verdict.status == 'complete',
            missing_registration=verdict.missing, declared_retrieval_eligible=refusal is None,
            refusal_code=refusal.code if refusal else None,
        ))
    if not cameras:
        notices.append('No validated camera registration is available')
    notices.append('Registry metadata only; camera imagery is not delivered by this interface')
    public = {'cameras': [camera.model_dump(mode='json') for camera in cameras], 'notices': notices}
    version = hashlib.sha256(json.dumps(public, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return PublicCameraRegistry(version=version, cameras=cameras, notices=notices)
