"""Spec-Refs: GOV-SPEC-004, GOV-SPEC-006; experiment api-first-source-delivery
(native identity/source-local implementation), swob-demand-query (exact-time
MSC report, finite expiry, unknown native QC). Synthetic fixed evidence only.
"""
from datetime import timedelta
import sys

import httpx
import pytest

from weather_api.native_runs import RunUnavailable
from weather_api.swob_delivery import SWOBPointReader
from weather_api.swob_query import SWOBQueryService, SwobQueryUnavailable
from test_swob_query import Clocks, feature, fixture_document, query_service


LOCATION = (47.5615, -52.7126)


def test_unsupported_run_and_series_do_not_construct_a_client():
    def forbidden():
        pytest.fail("Unsupported delivery must not construct a SWOB client")

    reader = SWOBPointReader(forbidden)
    selected = Clocks().wall
    with pytest.raises(RunUnavailable, match="no forecast run"):
        reader.read_point(*LOCATION, selected, run="20260907T00Z")
    assert reader.plan_series(selected, selected + timedelta(days=1)) is None
    assert reader.plan_series(selected, selected + timedelta(days=1), run="previous") is None


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS rejects the decoder's required locked RLIMIT_AS")
def test_point_reader_actual_linux_decoder_preserves_native_identity_nulls_qc_and_age():
    clocks, calls = Clocks(), []
    selected = clocks.wall

    def handler(request):
        calls.append(request)
        item = feature(temperature=99.0, temperature_qa="failed")
        item["id"] = "report-71801-20260907T030000Z"
        item["properties"].pop("dwpt_temp")
        return httpx.Response(200, json=fixture_document(item), headers={"Cache-Control": "max-age=60"})

    service = SWOBQueryService(client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: clocks.monotonic, utcnow=lambda: clocks.wall)
    reader = SWOBPointReader(lambda: service)
    first = reader.read_point(*LOCATION, selected)
    clocks.tick(17)
    second = reader.read_point(*LOCATION, selected)
    assert len(calls) == 1
    assert [field.value for field in second] == [99.0, None, 76.0, 1013.4, 4.5, 210.0]
    assert [(field.key, field.provenance.original_units, field.provenance.vertical_level) for field in second] == [
        ("temperature_2m", "degC", "2 m"), ("dew_point_2m", "degC", "2 m"),
        ("relative_humidity_2m", "percent", "2 m"), ("mean_sea_level_pressure", "hPa", "mean sea level"),
        ("wind_speed_10m", "m s-1", "10 m"), ("wind_direction_10m", "degree", "10 m"),
    ]
    for field in second:
        provenance = field.provenance
        assert field.storage == "available-not-stored"
        assert provenance.source_id == reader.source_id
        assert provenance.run_time is None and provenance.valid_time == selected
        assert provenance.native_report.station_id == "71801"
        assert provenance.native_report.provider_report_id == "report-71801-20260907T030000Z"
        assert provenance.native_report.observation_time == selected
        assert (provenance.sampled_latitude, provenance.sampled_longitude) == (47.56, -52.72)
        assert provenance.quality.status == "unknown"
        assert provenance.freshness.age_seconds == 17
        assert provenance.swob_acquisition.expires_at == first[0].provenance.swob_acquisition.expires_at
    assert "provider_quality:failed" in second[0].provenance.quality.flags
    # Native cache snapshots remain useful to existing consumers without becoming Series.
    assert len(service.cached_entries_for(*LOCATION)) == 1
    assert reader.plan_series(selected, selected + timedelta(hours=3)) is None
    assert len(calls) == 1


def test_point_refresh_failure_never_retimes_or_renews_cached_evidence():
    clocks, calls, fail = Clocks(), [], False
    selected = clocks.wall

    def handler(request):
        calls.append(request)
        if fail:
            return httpx.Response(503)
        return httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=60"})

    reader = SWOBPointReader(lambda: service)
    service = query_service(handler, clocks)
    original = reader.read_point(*LOCATION, selected)[0].provenance.swob_acquisition
    clocks.tick(10)
    fail = True
    with pytest.raises(SwobQueryUnavailable) as fresh_failure:
        reader.read_point(*LOCATION, selected, refresh=True)
    assert fresh_failure.value.outcome.expired_acquisition is None
    retained = reader.read_point(*LOCATION, selected)[0]
    assert retained.provenance.swob_acquisition == original
    assert retained.provenance.valid_time == selected
    assert len(calls) == 2
    clocks.tick(50)
    with pytest.raises(SwobQueryUnavailable) as expired_failure:
        reader.read_point(*LOCATION, selected)
    assert expired_failure.value.outcome.expired_acquisition == original
    assert expired_failure.value.outcome.values_withheld is True
    assert service.cached_entries_for(*LOCATION) == ()


def test_point_does_not_substitute_an_adjacent_native_report():
    clocks, calls = Clocks(), []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=60"})

    service = query_service(handler, clocks)
    reader = SWOBPointReader(lambda: service)
    reader.read_point(*LOCATION, clocks.wall)
    with pytest.raises(SwobQueryUnavailable) as gap:
        reader.read_point(*LOCATION, clocks.wall + timedelta(minutes=1))
    assert gap.value.outcome.reason == "unsupported_time"
    assert len(calls) == 2
