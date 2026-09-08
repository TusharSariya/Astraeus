"""GOV-SPEC-004/006: api-first-source-delivery/openmeteo-gfs-wave-demand."""
from datetime import timedelta

import httpx
import pytest

from test_openmeteo_gfs_wave_query import SELECTED, payload, service
from weather_api.gfs_wave_delivery import GFSWaveSource
from weather_api.native_runs import RunUnavailable
from weather_api.openmeteo_gfs_wave_query import OpenMeteoGfsWaveUnavailable


def test_descriptors_and_unsupported_selections_do_not_instantiate_provider():
    reader = GFSWaveSource(lambda: pytest.fail("descriptor or unsupported selection performed I/O"))
    descriptors = reader.descriptors()
    assert {item.field for item in descriptors} == {
        "significant_wave_height", "wave_period", "wave_direction", "swell_height",
        "swell_wave_period", "swell_wave_direction", "wind_wave_height", "wind_wave_period",
        "wind_wave_direction",
    }
    for item in descriptors:
        assert item.source_id == "openmeteo-gfs-wave" and item.product_id == "ncep_gfswave016"
        assert item.point and item.point_product == "GFS Wave"
        assert not item.native_series and item.run_selection == "not_applicable"
        assert item.levels == ["sea surface"]
        assert [variant.kind for variant in item.variants] == ["deterministic"]
    assert reader.plan_series(SELECTED, SELECTED + timedelta(days=1)) is None
    with pytest.raises(RunUnavailable):
        reader.read_point(47.5615, -52.7126, SELECTED, run="invented")
    with pytest.raises(ValueError, match="explicit refresh"):
        reader.read_point(47.5615, -52.7126, SELECTED, refresh=True)


def test_actual_query_preserves_hour_sea_cell_null_units_provenance_and_cache():
    calls = []
    body = payload()
    del body["hourly"]["swell_wave_period"]
    del body["hourly_units"]["swell_wave_period"]

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=body, headers={"cache-control": "max-age=120"}, request=request)

    query = service(handler)
    reader = GFSWaveSource(lambda: query)
    first = reader.read_point(47.5615, -52.7126, SELECTED)
    assert first == tuple(query.point_fields(47.5615, -52.7126, SELECTED))
    second = reader.read_point(47.5615, -52.7126, SELECTED)
    assert second == first and second[0] is not first[0]
    assert len(calls) == 1
    params = calls[0].url.params
    assert params["models"] == "ncep_gfswave016" and params["cell_selection"] == "sea"
    assert params["start_hour"] == params["end_hour"] == "2026-09-06T15:00"
    fields = {field.key: field for field in first}
    assert fields["significant_wave_height"].value == 1.0
    assert fields["swell_wave_period"].value is None
    assert "native_field_unavailable" in fields["swell_wave_period"].provenance.quality.flags
    for field in first:
        provenance = field.provenance
        assert provenance.run_time is None and provenance.run_stale is None
        assert provenance.valid_time == SELECTED and provenance.retrieval_time == SELECTED
        assert provenance.evidence_class == provenance.delivery_kind == "reprocessed"
        assert not provenance.source_display_primary
        assert provenance.intermediary == "Open-Meteo" and provenance.provider == "NOAA NCEP"
        assert (provenance.sampled_latitude, provenance.sampled_longitude) == (47.5, -52.75)
        assert "cell_selection:sea" in provenance.quality.flags
        assert provenance.normalized_units == ("m" if "height" in field.key else "s" if "period" in field.key else "degree")


@pytest.mark.parametrize("failure", ["non_hour", "neighbor", "all_null", "expired"])
def test_actual_query_refuses_missing_hour_empty_sea_and_failed_expired_replacement(failure):
    ticks = [0.0]
    calls = []
    body = payload(values={} if failure == "all_null" else None,
                   time="2026-09-06T14:00" if failure == "neighbor" else "2026-09-06T15:00")

    def handler(request):
        calls.append(request)
        if failure == "expired" and len(calls) > 1:
            raise httpx.ConnectError("fixture offline", request=request)
        return httpx.Response(200, json=body, headers={"cache-control": "max-age=1"}, request=request)

    query = service(handler, clock=lambda: ticks[0])
    reader = GFSWaveSource(lambda: query)
    if failure == "expired":
        reader.read_point(47.5615, -52.7126, SELECTED)
        ticks[0] = 1.0
    selected = SELECTED + timedelta(minutes=1) if failure == "non_hour" else SELECTED
    with pytest.raises(ValueError if failure == "non_hour" else OpenMeteoGfsWaveUnavailable):
        reader.read_point(47.5615, -52.7126, selected)
    assert len(calls) == (0 if failure == "non_hour" else 2 if failure == "expired" else 1)
