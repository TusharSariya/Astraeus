"""Unified discovery contract: declarations do not acquire or imply imagery."""
from weather_api.store import registry_source_records
from weather_api import wms
from weather_api.discovery import discovery_metadata


def test_every_source_is_classified_without_provider_io(monkeypatch):
    monkeypatch.setattr(wms, 'forecast_coverage', lambda *_: (_ for _ in ()).throw(AssertionError('network metadata requested')))
    sources = registry_source_records()
    assert len(sources) >= 125
    assert len({s.id for s in sources}) == len(sources)
    for source in sources:
        assert source.discovery is not None
        assert all([source.discovery.subjects, source.discovery.kinds, source.discovery.methods, source.discovery.ensemble_forms])
    wn = next(s for s in sources if s.id == 'google-weathernext-3-statistics')
    assert wn.discovery.subjects == ['Temperature']
    assert wn.discovery.methods == ['Machine learning']
    assert wn.discovery.map_capabilities == []
    assert {c.point_product for c in wn.capabilities} == {'WeatherNext 3 local', 'WeatherNext 3 historical'}
    assert not any(c.native_series for c in wn.capabilities)


def test_goes_and_solar_imagery_keep_distinct_subjects():
    sources = {s.id:s for s in registry_source_records()}
    goes = sources['noaa-goes-east'].discovery
    assert {'Clouds', 'Satellite imagery'} <= set(goes.subjects)
    assert len(goes.map_capabilities) == len(wms.SATELLITE_LAYERS)
    assert all(s.source_id == 'noaa-goes-east' for s in wms.SATELLITE_LAYERS)
    solar = sources['nasa-soho-sdo-goes-suvi-imagery'].discovery
    assert {'Space weather','Satellite imagery'} <= set(solar.subjects)
    assert 'Clouds' not in solar.subjects


def test_map_declarations_include_empty_cache_paths():
    sources = {s.id:s for s in registry_source_records()}
    assert len(sources['noaa-gfs'].discovery.map_capabilities) == 4
    assert {c.product for c in sources['noaa-gfs'].discovery.map_capabilities} == {'GFS'}
    assert sources['eccc-cap-alerts'].discovery.map_capabilities[0].product == 'CAP'
    ids=[c.layer_id for s in sources.values() for c in s.discovery.map_capabilities]
    assert len(ids)==len(set(ids))


def test_unclassified_source_stays_unknown():
    meta=discovery_metadata({'id':'future-source','category':'new'},[],[])
    assert meta.subjects == meta.kinds == meta.methods == meta.ensemble_forms == ['Unknown']


def test_empty_gfs_cache_still_offers_implemented_raster_paths(monkeypatch):
    from types import SimpleNamespace
    import importlib
    api = importlib.import_module('weather_api.app')
    from weather_api import gfs_query
    monkeypatch.setattr(api, 'fixture_mode', lambda: False)
    monkeypatch.setattr(api, 'response_mode', lambda: api.DataMode.LIVE)
    monkeypatch.setattr(gfs_query, 'gfs_query_coordinator', lambda: SimpleNamespace(
        cached_cloud_availability=lambda: {key: [] for key in ['total_cloud_geometric', 'cloud_low', 'cloud_middle', 'cloud_high']}))
    response=api.get_layers('GFS')
    assert len(response.layers)==4
    assert all(layer.raster_available and not layer.times and layer.imagery_availability.status=='unknown' for layer in response.layers)


def test_synthetic_fixture_values_are_independent_of_wall_clock(monkeypatch):
    from datetime import UTC, datetime
    from scripts.generate_source_contract import fixtures
    from weather_api import fixtures as fixture_module
    monkeypatch.setattr(fixture_module, 'now', lambda: datetime(2026, 9, 8, 13, tzinfo=UTC))
    first=fixtures()
    monkeypatch.setattr(fixture_module, 'now', lambda: datetime(2026, 9, 9, 14, tzinfo=UTC))
    second=fixtures()
    for key in ['series', 'point_aqhi', 'point_aqhi_unavailable']:
        assert second[key]==first[key]


def test_declared_unimplemented_variables_are_searchable_without_new_capabilities():
    sources = {s.id:s for s in registry_source_records()}
    assert 'Precipitation' in sources['eccc-hrepa'].discovery.subjects
    assert 'Humidity' in sources['google-weathernext-2'].discovery.subjects
    assert not sources['google-weathernext-2'].capabilities
    assert not sources['google-weathernext-2'].discovery.map_capabilities
    assert 'Clouds' in sources['openmeteo-graphcast'].discovery.subjects
