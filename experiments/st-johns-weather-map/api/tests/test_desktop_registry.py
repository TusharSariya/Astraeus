from fastapi.testclient import TestClient
from weather_api.app import app
from weather_api.registry_api import get_sites


def test_registry_serves_versioned_audited_geometry_without_writes():
    client = TestClient(app)
    url = '/api/experiments/weather/v0/registry/sites'
    body = client.get(url).json()
    assert len(body['version']) == 64
    assert body == client.get(url).json()
    signal = next(site for site in body['sites'] if site['id'] == 'signal-hill')
    assert signal['latitude'] == 47.5704
    assert len(signal['horizon']['elevation_deg']) == 36
    assert signal['horizon']['terrain_check_status'] == 'not_run'
    assert 'await a field survey' in signal['geometry_note']
    assert client.post(url, json=body).status_code == 405


def test_empty_registry_does_not_borrow_or_invent_geometry(monkeypatch):
    from weather_api.sites import SiteRegistry
    import weather_api.registry_api as api
    baseline = get_sites().version
    monkeypatch.setattr(api, 'load_site_registry', lambda: SiteRegistry([], 'No registered sites available'))
    response = get_sites()
    assert response.sites == []
    assert response.notice == 'No registered sites available'
    assert response.version != baseline


def test_camera_registry_is_versioned_public_metadata_without_delivery_or_writes():
    client = TestClient(app)
    url = '/api/experiments/weather/v0/registry/cameras'
    body = client.get(url).json()
    assert len(body['version']) == 64
    assert body == client.get(url).json()
    assert body['cameras']
    for camera in body['cameras']:
        assert camera['status'] == 'partnership-only'
        assert camera['declared_retrieval_eligible'] is False
        assert camera['image_delivery_implemented'] is False
        assert camera['refusal_code'] == 'partnership_only'
        assert 'endpoint' not in camera and 'terms' not in camera and 'privacy_masks' not in camera
    assert client.post(url, json={}).status_code == 405


def test_camera_private_configuration_cannot_change_public_version(monkeypatch):
    from copy import deepcopy
    from registry import camera_audit
    import weather_api.registry_api as api
    records = camera_audit.load_cameras()
    baseline = api.get_cameras()
    altered = {}
    for identity, entry in records.items():
        if isinstance(entry, camera_audit.Camera):
            record = deepcopy(entry.record)
            record['private_configuration_sentinel'] = 'Not part of the public allowlist'
            altered[identity] = camera_audit.Camera(record, entry.path)
        else:
            altered[identity] = entry
    monkeypatch.setattr(camera_audit, 'load_cameras', lambda: altered)
    assert api.get_cameras() == baseline
