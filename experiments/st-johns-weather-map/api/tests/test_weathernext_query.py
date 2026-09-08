"""Fixed retained-manifest proof; zero authenticated or provider requests."""
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import threading

import pytest

from ingest.adapters.weathernext3_statistics import CLOUD_FIELDS, EXPECTED_FIELDS
from weather_api.weathernext_query import (
    CACHE_MAX_ENTRIES, MANIFEST_MAX_BYTES, TTL_SECONDS,
    WeatherNextSelection, WeatherNextStatisticsQueryService, WeatherNextQueryUnavailable,
)

FIXTURES = Path(__file__).parent / "fixtures" / "weathernext3"
BODY = (FIXTURES / "all-fields-point-lead6.json").read_bytes()
RUN = datetime(2026, 8, 1, tzinfo=UTC)
NOW = datetime(2026, 9, 7, tzinfo=UTC)


def selection(**kwargs):
    return WeatherNextSelection(**({"initialization": RUN, "valid_time": RUN + timedelta(hours=6),
        "latitude": 47.5, "longitude": -52.7, "fields": CLOUD_FIELDS} | kwargs))


def service(acquire=lambda _: BODY, clock=lambda: 0, utcnow=lambda: NOW):
    return WeatherNextStatisticsQueryService(acquire=acquire, clock=clock, utcnow=utcnow)


def test_all_126_native_values_units_statistics_and_nulls_remain_distinct():
    reading = service().read_point(selection(fields=EXPECTED_FIELDS))
    expected = {item["field"]: item for item in json.loads(BODY)["sample"]["fields"]}
    assert len(reading.values) == 126
    assert sum(item.value is None for item in reading.values) == 6
    for item in reading.values:
        assert item.value == expected[item.field]["values"][0]
        assert item.unit == expected[item.field]["unit"]
        assert item.grid == expected[item.field]["grid"]
        assert item.statistic == item.field.rsplit("_", 1)[1]
        assert item.latitude == 47.5
        assert item.longitude == expected[item.field]["longitude"]
    assert reading.receipt.evidence_class == "retained_acquisition_manifest_replay"
    assert reading.receipt.manifest_bytes == len(BODY)
    assert reading.receipt.source_retrieved_at == datetime.fromisoformat(json.loads(BODY)["times"]["retrieval"])


def test_six_cloud_box_reuses_existing_native_decoder():
    body = (FIXTURES / "avalon-box-six-field-4x4.json").read_bytes()
    manifest = json.loads(body)
    chosen = tuple(manifest["request"]["selected_fields"])
    reading = service(lambda _: body).read_point(selection(fields=chosen))
    assert len(reading.values) == 6
    expected = {f["field"]: f["leads"][0]["values"][2][1] for f in manifest["avalon_box_sample"]["fields"]}
    assert {v.field: v.value for v in reading.values} == expected


def test_cache_hit_has_zero_acquisition_and_fixed_receipt_then_expiry_reacquires():
    calls, ticks = [], [0]
    query = service(lambda request: calls.append(request) or BODY, clock=lambda: ticks[0])
    first = query.read_point(selection())
    ticks[0] = 30
    assert query.read_point(selection()) is first
    assert len(calls) == 1
    assert first.receipt.expires_at == NOW + timedelta(seconds=TTL_SECONDS)
    ticks[0] = TTL_SECONDS
    assert query.read_point(selection()).receipt.identity == first.receipt.identity
    assert len(calls) == 2


def test_explicit_refresh_failure_preserves_unexpired_but_never_returns_stale():
    ticks, broken, calls = [0], [False], []
    def acquire(request):
        calls.append(request)
        if broken[0]:
            raise RuntimeError("secret provider exception must not escape")
        return BODY
    query = service(acquire, clock=lambda: ticks[0])
    first = query.read_point(selection())
    broken[0] = True
    with pytest.raises(WeatherNextQueryUnavailable, match="bounded acquisition") as error:
        query.read_point(selection(), refresh=True)
    assert "secret" not in str(error.value)
    assert query.read_point(selection()) is first
    ticks[0] = TTL_SECONDS
    with pytest.raises(WeatherNextQueryUnavailable):
        query.read_point(selection())
    assert len(calls) == 3


@pytest.mark.parametrize("refresh", [False, True])
def test_concurrent_identical_miss_or_refresh_coalesces(refresh, monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls = []
    waiting = threading.Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout)
    monkeypatch.setattr("weather_api.weathernext_query.Future", ObservedFuture)
    def acquire(request):
        calls.append(request)
        started.set()
        assert release.wait(5)
        return BODY
    query = service(acquire)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(query.read_point, selection(), refresh=refresh)
        assert started.wait(5)
        second = pool.submit(query.read_point, selection(), refresh=refresh)
        assert waiting.wait(5)
        release.set()
        assert first.result() == second.result()
    assert len(calls) == 1


@pytest.mark.parametrize("age", [timedelta(hours=48), timedelta(hours=1), timedelta(hours=-6)])
def test_terms_gate_uses_valid_time_not_old_initialization_before_acquisition(age):
    query = service(lambda _: pytest.fail("terms-blocked query acquired data"), utcnow=lambda: RUN + timedelta(hours=6) + age)
    with pytest.raises(WeatherNextQueryUnavailable, match="terms permission"):
        query.read_point(selection())


@pytest.mark.parametrize("mutation", [
    lambda m: m["identity"].update(product_version="2.0.0"),
    lambda m: m["identity"].update(member_id="0"),
    lambda m: m["request"].update(requester_billing_identity="project"),
    lambda m: m["objects"][0].update(generation=""),
    lambda m: m["sample"]["fields"][0].update(unit="C"),
])
def test_adapter_identity_validation_is_not_bypassed(mutation):
    manifest = json.loads(BODY)
    mutation(manifest)
    with pytest.raises(WeatherNextQueryUnavailable):
        service(lambda _: json.dumps(manifest).encode()).read_point(selection())


@pytest.mark.parametrize("kwargs", [
    {"latitude": 40}, {"valid_time": RUN + timedelta(hours=7)},
    {"initialization": RUN - timedelta(hours=6)},
])
def test_retained_data_cannot_substitute_location_time_or_run(kwargs):
    with pytest.raises(WeatherNextQueryUnavailable):
        service().read_point(selection(**kwargs))


def test_finite_entry_and_payload_bounds():
    query = service()
    for field in EXPECTED_FIELDS[:CACHE_MAX_ENTRIES + 2]:
        query.read_point(selection(fields=(field,)))
    assert len(query._entries) == CACHE_MAX_ENTRIES
    with pytest.raises(WeatherNextQueryUnavailable):
        service(lambda _: b" " * (MANIFEST_MAX_BYTES + 1)).read_point(selection())


def test_invalid_native_selection_fails_before_acquisition():
    with pytest.raises(ValueError):
        selection(fields=("fog",))
    with pytest.raises(ValueError):
        selection(valid_time=RUN + timedelta(hours=6, minutes=30))
    with pytest.raises(ValueError):
        selection(initialization=RUN.replace(tzinfo=None))


def test_successful_unchanged_refresh_does_not_extend_existing_lifetime():
    calls, ticks = [], [0]
    query = service(lambda request: calls.append(request) or BODY, clock=lambda: ticks[0])
    first = query.read_point(selection())
    ticks[0] = 30
    assert query.read_point(selection(), refresh=True) is first
    assert len(calls) == 2
    assert query._entries[selection()].expiry == TTL_SECONDS
