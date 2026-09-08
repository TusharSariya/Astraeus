"""Mapped fixtures: API-first capability/identity; METAR demand; TAF native groups."""
from datetime import UTC, datetime, timedelta
import hashlib
import sys

import httpx
import pytest

from weather_api.aviation_delivery import METARSource, TAFDelivery
from weather_api.metar_query import MetarQueryService
from weather_api.native_runs import RunUnavailable
from weather_api.taf_query import TafQueryService, TafQueryUnavailable

AT = datetime(2026, 9, 6, 12, 30, tzinfo=UTC)


class Clock:
    value = 100.0

    def __call__(self):
        return self.value


def taf_report():
    start = int(AT.replace(minute=0).timestamp())
    return [{"icaoId": "CYYT", "issueTime": "2026-09-06T11:41:00Z",
             "bulletinTime": "2026-09-06T11:00:00Z", "dbPopTime": "2026-09-06T11:41:27Z",
             "lat": 47.627, "lon": -52.748, "elev": 128,
             "mostRecent": 1, "prior": 3, "name": "St Johns Intl", "remarks": "",
             "validTimeFrom": start, "validTimeTo": start + 86400,
             "rawTAF": "TAF CYYT 061141Z 0612/0712",
             "fcsts": [
                 {"timeFrom": start, "timeTo": start + 18000, "wspd": 12,
                  "wdir": "VRB", "visib": "6", "clouds": [{"cover": "OVX", "base": None}],
                  "wxString": "FG"},
                 {"timeFrom": start, "timeTo": start + 3600, "fcstChange": "PROB",
                  "visib": "2", "probability": 30},
             ]}]


def test_descriptors_and_absent_series_never_create_clients():
    def forbidden():
        pytest.fail("catalogue must not instantiate a source service")

    metar, taf = METARSource(forbidden), TAFDelivery(forbidden)
    descriptors = metar.descriptors()
    assert descriptors and all(item.point_product == "METAR" for item in descriptors)
    assert all(item.product_id == "metar" and item.source_id == "awc-metar-speci" for item in descriptors)
    assert all(item.variants[0].kind == "observation" and not item.native_series for item in descriptors)
    native = taf.descriptors()[0]
    assert native.source_id == "awc-taf" and native.product_id == "taf"
    assert native.point is False and native.point_product is None
    assert metar.plan_series(AT, AT + timedelta(hours=1)) is None
    assert taf.plan_series(AT, AT + timedelta(hours=1)) is None


@pytest.mark.parametrize("reader", [METARSource, TAFDelivery])
@pytest.mark.parametrize("options", [{"run": "previous"}, {"refresh": True}])
def test_unsupported_selection_is_refused_before_factory(reader, options):
    def forbidden():
        pytest.fail("unsupported selector must fail before source creation")

    source = reader(forbidden)
    with pytest.raises(RunUnavailable):
        if isinstance(source, METARSource):
            source.read_point(47.627, -52.748, AT, **options)
        else:
            source.read_report("CYYT", AT, **options)


def test_taf_real_query_preserves_intervals_sparse_groups_and_fixed_cache():
    calls = []
    clock = Clock()

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=taf_report(), headers={"Cache-Control": "max-age=60"})

    service = TafQueryService(client=httpx.Client(transport=httpx.MockTransport(handler)), clock=clock)
    reader = TAFDelivery(lambda: service)
    first = reader.read_report("CYYT", AT)
    second = reader.read_report("CYYT", AT + timedelta(minutes=1))
    assert len(calls) == 1
    assert first["acquisition"] == second["acquisition"]
    assert first["revision_id"] == second["revision_id"]
    assert first["station"] == "CYYT" and first["source_id"] == "awc-taf"
    assert first["run_time"] == "2026-09-06T11:41:00Z"
    assert [group["index"] for group in first["groups"]] == [0, 1]
    assert first["groups"][1]["change"] == "PROB"
    assert first["groups"][1]["probability"] == 30
    assert first["groups"][1]["presence"]["wind_u_10m"] == "not_stated_in_change_group"
    assert first["groups"][0]["values"]["wind_u_10m"] is None
    assert first["groups"][0]["native"]["wind_variable"] is True
    # Returned native metadata cannot mutate the cached report through the wrapper.
    first["groups"][0]["native"]["clouds"][0]["cover"] = "MUTATED"
    assert reader.read_report("CYYT", AT)["groups"][0]["native"]["clouds"][0]["cover"] == "OVX"
    end = reader.read_report("CYYT", AT.replace(hour=13, minute=0))
    assert [group["index"] for group in end["groups"]] == [0]
    assert len(calls) == 1


def test_taf_expired_failure_keeps_withheld_identity():
    calls = []
    clock = Clock()

    def handler(request):
        calls.append(request)
        return (httpx.Response(200, json=taf_report(), headers={"Cache-Control": "max-age=1"})
                if len(calls) == 1 else httpx.Response(503))

    reader = TAFDelivery(lambda: service)
    service = TafQueryService(client=httpx.Client(transport=httpx.MockTransport(handler)), clock=clock)
    first = reader.read_report("CYYT", AT)
    clock.value += 2
    with pytest.raises(TafQueryUnavailable) as caught:
        reader.read_report("CYYT", AT)
    assert caught.value.detail["values_withheld"] is True
    assert caught.value.detail["cached_identity"] == first["revision_id"]


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS rejects required child RLIMIT_AS")
def test_metar_real_adapter_composition_preserves_observation_qc_and_cache():
    observed = AT.replace(minute=0)
    rows = [{"icaoId": "CYYT", "obsTime": int(observed.timestamp()), "temp": 10, "dewp": 8,
             "slp": 1012.3, "wspd": 10, "wdir": 180, "visib": "6+", "wgst": 20,
             "clouds": [{"cover": "BKN", "base": 20}], "wxString": "BR",
             "metarId": 42, "metarType": "METAR", "rawOb": "METAR CYYT TEST",
             "reportTime": "2026-09-06T12:00:00Z", "receiptTime": "2026-09-06T12:01:00Z",
             "name": "St Johns Intl", "lat": 47.627, "lon": -52.748,
             "elev": 128, "fltCat": "MVFR", "qcField": 0}]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=rows, headers={"Cache-Control": "max-age=60"})

    service = MetarQueryService(client=httpx.Client(transport=httpx.MockTransport(handler)), clock=Clock())
    reader = METARSource(lambda: service)
    first = reader.read_point(47.627, -52.748, AT)
    second = reader.read_point(47.627, -52.748, AT + timedelta(minutes=1))
    assert len(calls) == 1
    assert {field.key: (field.value, field.provenance.artifact_revision, field.provenance.valid_time, field.provenance.retrieval_time, field.provenance.native_report) for field in first} == {field.key: (field.value, field.provenance.artifact_revision, field.provenance.valid_time, field.provenance.retrieval_time, field.provenance.native_report) for field in second}
    fields = {field.key: field for field in first}
    assert fields["temperature_2m"].value == 10
    assert fields["wind_gust_10m"].value == pytest.approx(10.28888)
    report = fields["temperature_2m"].provenance.native_report
    assert report.station_id == "CYYT" and report.provider_report_id == 42
    assert report.quality_code == 0 and report.flight_category == "MVFR"
    assert report.raw_report_sha256 == hashlib.sha256(b"METAR CYYT TEST").hexdigest()
    assert all(field.provenance.valid_time == observed for field in first)
    assert all(field.provenance.source_id == "awc-metar-speci" for field in first)
