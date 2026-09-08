"""Catalogue -> request consistency, with stale real-shaped WMS samples."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import importlib
import pytest
from fastapi.testclient import TestClient
from weather_api import wms
from weather_api.store import LayerCoverage

api = importlib.import_module('weather_api.app')
AT = datetime(2026, 9, 8, 12, tzinfo=UTC)
OLD = AT - timedelta(days=5)

@pytest.fixture
def stale_catalogue(monkeypatch):
    monkeypatch.setenv('WEATHER_DATA_MODE', 'live')
    monkeypatch.setattr(api, 'now', lambda: AT)
    monkeypatch.setattr(api, '_proxied_forecast_layers', lambda: ([], []))
    monkeypatch.setattr(api.grids, 'rendered_grid_layers', lambda *a, **k: ([], []))
    monkeypatch.setattr(api.goes_satellite, 'satellite_layers', lambda *a, **k: ([], []))
    artifacts = [SimpleNamespace(source_id=source, logical_name=logical, media_type='application/zarr+zip', provenance={'geomet_layer': binding}, revision_id='old') for source, logical, binding in [('eccc-radar','radar','RADAR_1KM_RRAI'), ('eccc-lightning','lightning','Lightning_2.5km_Density')]]
    coverage = {f'{a.source_id}-{a.logical_name}': LayerCoverage(layer_id=f'{a.source_id}-{a.logical_name}', source_id=a.source_id, logical_name=a.logical_name, times=[OLD], cadence_seconds=360, sites=[(47.5,-52.7)], gridded=False) for a in artifacts}
    monkeypatch.setattr(api, 'live_store', lambda: SimpleNamespace(current=lambda: artifacts, published_layer_times=lambda: coverage))
    monkeypatch.setattr(wms, 'forecast_coverage', lambda spec: wms.ForecastCoverage(spec, (AT-timedelta(minutes=6), AT), 'native', 360))
    return TestClient(api.app)


def test_stale_samples_do_not_advertise_unservable_times_but_current_wms_images_remain(stale_catalogue):
    response = stale_catalogue.get('/api/experiments/weather/v0/layers')
    assert response.status_code == 200
    body = response.json()
    for layer in body['layers']:
        if layer['id'] not in ('eccc-radar-radar','eccc-lightning-lightning'): continue
        assert layer['times'] == [], layer
        assert layer['imagery_availability']['status'] == 'known'
        assert layer['imagery_availability']['times'] == [(AT-timedelta(minutes=6)).isoformat().replace('+00:00','Z'), AT.isoformat().replace('+00:00','Z')]
        assert layer['raster_available'] is True
    assert any('outside the serving window' in notice for notice in body['notices'])


def test_unreadable_provider_inventory_never_borrows_sample_times(stale_catalogue, monkeypatch):
    monkeypatch.setattr(wms, 'forecast_coverage', lambda spec: wms.ForecastCoverage(spec, (), 'unknown', None, notice='Provider unavailable'))
    body = stale_catalogue.get('/api/experiments/weather/v0/layers').json()
    layer = next(row for row in body['layers'] if row['id']=='eccc-radar-radar')
    assert layer['times'] == []
    assert layer['imagery_availability']['times'] == []
    assert layer['imagery_availability']['status'] == 'unknown'
    assert 'Provider unavailable' in layer['imagery_availability']['reason']
    assert layer['raster_available'] is False

@pytest.mark.parametrize('product', [None, 'HRDPS', 'GFS', 'CAP', 'OVATION'])
def test_every_catalogue_branch_filters_all_axes_at_inclusive_window_boundaries(monkeypatch, product):
    from weather_api.layer_identity import imagery
    from weather_api.models import Layer, LayerFrame, LayerRunSummary, LayersResponse, DataMode
    stamps = [AT-timedelta(days=1,microseconds=1), AT-timedelta(days=1), AT, AT+timedelta(days=14), AT+timedelta(days=14,microseconds=1)]
    value = Layer(id='producer-output', title='Constructed producer', kind='raster', field='native', product='fixture', units='native', semantics='fixture', staleness_tolerance_seconds=60, times=stamps,
                  frames=[LayerFrame(valid_time=time, provider_run_id='run') for time in stamps],
                  runs=[LayerRunSummary(provider_run_id='run', frame_count=5)],
                  imagery_availability=imagery('known', AT, 'fixture', 'Constructed inventory', stamps))
    monkeypatch.setattr(api, 'now', lambda: AT)
    monkeypatch.setattr(api, '_layer_catalogue', lambda product: LayersResponse(data_mode=DataMode.FIXTURE, layers=[value]))
    body = TestClient(api.app).get('/api/experiments/weather/v0/layers', params={} if product is None else {'product':product}).json()
    layer = body['layers'][0]
    expected = [stamp.isoformat().replace('+00:00','Z') for stamp in stamps[1:4]]
    assert layer['times'] == layer['imagery_availability']['times'] == expected
    assert [frame['valid_time'] for frame in layer['frames']] == expected
    assert layer['runs'][0]['frame_count'] == 3
    monkeypatch.setattr(api, 'now', lambda: AT+timedelta(hours=1))
    rolled = TestClient(api.app).get('/api/experiments/weather/v0/layers').json()['layers'][0]
    assert expected[0] not in rolled['times']


def test_nested_catalogue_producers_cannot_reset_the_request_budget(monkeypatch):
    monkeypatch.setattr(wms, 'geomet_client', lambda: None)
    with wms.budgeted(limit=2) as outer:
        outer.spend()
        with wms.budgeted() as inner:
            assert inner is outer
            inner.spend()
        with pytest.raises(wms.UpstreamBudgetExhausted): outer.spend()


def test_one_malformed_image_inventory_does_not_hide_other_layers(stale_catalogue, monkeypatch):
    def coverage(spec):
        if spec.layer_id == 'eccc-radar-radar': raise ValueError('malformed time extent')
        return wms.ForecastCoverage(spec, (AT,), 'native', 600)
    monkeypatch.setattr(wms, 'forecast_coverage', coverage)
    body = stale_catalogue.get('/api/experiments/weather/v0/layers').json()
    layers = {layer['id']:layer for layer in body['layers']}
    assert layers['eccc-lightning-lightning']['imagery_availability']['times'] == ['2026-09-08T12:00:00Z']
    radar = layers['eccc-radar-radar']
    assert radar['imagery_availability']['status'] == 'unknown'
    assert radar['raster_available'] is False
    assert 'malformed time extent' in radar['imagery_availability']['reason']
