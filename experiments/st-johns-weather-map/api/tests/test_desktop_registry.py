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
