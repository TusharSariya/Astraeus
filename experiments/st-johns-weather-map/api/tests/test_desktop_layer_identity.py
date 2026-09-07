from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

import importlib
api = importlib.import_module('weather_api.app')
from weather_api import wms
from weather_api.layer_identity import imagery, mappings
from weather_api.models import Layer

AT = datetime(2026, 9, 7, 12, tzinfo=UTC)


def layer(**kwargs):
    return Layer(id='misleading-title', title='GFS temperature', field='surface_bundle', product='HRDPS',
                 kind='raster', units='mixed', semantics='Constructed fixture', staleness_tolerance_seconds=1, **kwargs)


def test_unknown_source_and_imagery_are_explicit_without_using_title_or_sample_times():
    value = layer(times=[AT])
    assert value.mapping_status == 'unknown' and value.field_mappings == []
    assert value.imagery_availability.status == 'unknown'
    assert value.imagery_availability.times == [] and value.imagery_availability.reason
    assert value.times == [AT]


def test_multi_source_bundle_preserves_every_explicit_association_and_unknown_declared_field():
    value = layer(**mappings([('eccc-hrdps', 'temperature'), ('noaa-gfs', 'wind_speed'), ('noaa-gfs', 'unmapped-native'), ('eccc-hrdps', 'temperature')]))
    assert value.mapping_status == 'partial'
    assert [(row.source_id, row.field_key) for row in value.field_mappings] == [('eccc-hrdps', 'temperature_2m'), ('noaa-gfs', 'wind_speed_10m'), ('noaa-gfs', None)]
    assert value.field_mappings[-1].declared_field == 'unmapped-native'
    with pytest.raises(ValidationError, match='disagrees'): layer(mapping_status='known')


def test_imagery_inventory_can_differ_from_samples_and_never_promises_render_success():
    value = layer(times=[AT], imagery_availability=imagery('known', AT, 'provider_inventory', 'Rendering may fail', [AT + timedelta(hours=1)]))
    assert value.times == [AT]
    assert value.imagery_availability.times == [AT + timedelta(hours=1)]
    with pytest.raises(ValidationError, match='advertise'): imagery('unknown', AT, 'unreadable', 'No inventory', [AT])


def test_proxy_mapping_comes_from_explicit_spec_and_preserves_native_times(monkeypatch):
    spec = wms.FORECAST_LAYERS[0]
    monkeypatch.setattr(api, 'now', lambda: AT)
    monkeypatch.setattr(wms, 'PROXIED_LAYERS', (spec,))
    monkeypatch.setattr(wms, 'forecast_coverage', lambda value: wms.ForecastCoverage(value, (AT,), 'degC', None))
    monkeypatch.setattr(wms.budgeted, '__enter__', lambda self: None)
    monkeypatch.setattr(wms.budgeted, '__exit__', lambda *args: None)
    values, _ = api._proxied_forecast_layers()
    value = values[0]
    assert value.field_mappings[0].source_id == 'eccc-hrdps'
    assert value.field_mappings[0].field_key == 'temperature_2m'
    assert value.times == [AT] == value.imagery_availability.times
    assert value.imagery_availability.checked_at == AT
    assert value.evidence_class is None  # source association is not class promotion


def test_gfs_index_uses_existing_cached_inventory_without_new_point_reads(monkeypatch):
    import weather_api.gfs_query as gfs
    class Cached:
        def cached_cloud_availability(self):
            return {'total_cloud_geometric': [AT], 'cloud_low': [], 'cloud_middle': [], 'cloud_high': []}
    monkeypatch.setenv('WEATHER_DATA_MODE', 'live')
    monkeypatch.setattr(gfs, 'gfs_query_coordinator', lambda: Cached())
    body = TestClient(api.app).get('/api/experiments/weather/v0/layers?product=GFS').json()
    value = body['layers'][0]
    assert value['field_mappings'] == [{'source_id': 'noaa-gfs', 'field_key': 'total_cloud_geometric', 'declared_field': 'total_cloud_geometric'}]
    assert value['imagery_availability']['basis'] == 'cached_native_inventory'
    assert value['times'] == value['imagery_availability']['times']
