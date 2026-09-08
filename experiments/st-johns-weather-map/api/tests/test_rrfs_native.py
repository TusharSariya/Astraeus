"""RRFSv1.0 parallel native request/decoder experiment; no API admission."""
from datetime import UTC, datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
import sys

import httpx
import numpy as np
import pytest

from weather_api.rrfs_native import GRID, RRFSRequest, temperature_range, bounded_decode, decode_temperature
from weather_api.rrfs_query import RRFSQueryService

RUN = datetime(2026, 9, 7, 12, tzinfo=UTC)
REQUEST = RRFSRequest(RUN, RUN + timedelta(hours=6), 47.56, -52.71)


@pytest.fixture
def message():
    import eccodes as ec
    handle = ec.codes_grib_new_from_samples("rotated_ll_sfc_grib2")
    try:
        for name, value in {**GRID, "centre": "kwbc", "subCentre": 0,
            "generatingProcessIdentifier": 134, "typeOfGeneratingProcess": 2,
            "productDefinitionTemplateNumber": 0, "significanceOfReferenceTime": 1,
            "dataDate": 20260907, "dataTime": 1200, "stepUnits": 1, "step": 6,
            "typeOfLevel": "heightAboveGround", "level": 2, "shortName": "2t"}.items():
            if name != "numberOfPoints":
                ec.codes_set(handle, name, value)
        ec.codes_set_values(handle, np.full(769741, 290.0))
        yield ec.codes_get_message(handle)
    finally:
        ec.codes_release(handle)


def index(length):
    return f"1:0:d=2026090712:TMP:2 m above ground:6 hour fcst:\n2:{length}:d=2026090712:RH:2 m above ground:6 hour fcst:\n".encode()


def test_exact_versioned_na_request_and_existing_index_parser(message):
    assert REQUEST.url.endswith("rrfs.20260907/12/rrfs.t12z.2dfld.13km.f006.na.grib2")
    assert temperature_range(index(len(message)), REQUEST).as_tuple() == (0, len(message)-1)
    with pytest.raises(ValueError, match="run/lead"):
        temperature_range(index(len(message)).replace(b"6 hour", b"9 hour"), REQUEST)
    with pytest.raises(ValueError, match="exactly one"):
        temperature_range(index(len(message)).replace(b"TMP", b"DPT"), REQUEST)


@pytest.mark.parametrize("change", [
    {"run_time": RUN.replace(tzinfo=None)},
    {"run_time": RUN.replace(tzinfo=timezone(timedelta(minutes=30)))}, {"valid_time": RUN - timedelta(hours=1)},
    {"valid_time": RUN + timedelta(hours=85)}, {"latitude": 20.},
    {"longitude": float("nan")}, {"valid_time": RUN + timedelta(minutes=1)},
])
def test_request_rejects_unsupported_identity(change):
    with pytest.raises(ValueError):
        replace(REQUEST, **change).validate()


def test_native_metadata_and_mask_are_preserved(message):
    result = decode_temperature(message, REQUEST)
    assert result["value"] == 290 and result["units"] == "K"
    assert result["variant"] == "deterministic" and result["producer_qc"] == "unknown"
    assert result["native_masked"] is False and result["operational"] is False
    assert result["sample_distance_km"] < 10


@pytest.mark.parametrize(("name", "value"), [("generatingProcessIdentifier", 96),
    ("level", 10), ("step", 9), ("latitudeOfSouthernPoleInDegrees", -30)])
def test_mismatched_native_identity_fails_closed(message, name, value):
    import eccodes as ec
    handle = ec.codes_new_from_message(message)
    try:
        ec.codes_set(handle, name, value)
        changed = ec.codes_get_message(handle)
    finally:
        ec.codes_release(handle)
    with pytest.raises(ValueError, match="native"):
        decode_temperature(changed, REQUEST)


@pytest.mark.skipif(sys.platform != "linux", reason="real bounded Linux decoder")
def test_real_bounded_native_decode_and_cache(tmp_path, message):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith(".idx"):
            return httpx.Response(200, stream=httpx.ByteStream(index(len(message))))
        assert request.headers["Range"] == f"bytes=0-{len(message)-1}"
        return httpx.Response(206, stream=httpx.ByteStream(message),
            headers={"Content-Range": f"bytes 0-{len(message)-1}/{len(message)+100}"})
    service = RRFSQueryService(tmp_path, transport=httpx.MockTransport(handler))
    first = service.query(REQUEST)
    assert first["value"] == 290 and len(calls) == 2
    first["producer_qc"] = "passed"
    assert service.query(REQUEST)["producer_qc"] == "unknown" and len(calls) == 2
    assert list(tmp_path.iterdir()) == []


def test_failed_refresh_retains_unexpired_point_then_refuses_expired(tmp_path, monkeypatch):
    now = [0.]
    service = RRFSQueryService(tmp_path, clock=lambda: now[0])
    monkeypatch.setattr(service, "_load", lambda _: {"value": 290})
    service.query(REQUEST)
    def failed(_):
        raise RuntimeError("fixture failure")
    monkeypatch.setattr(service, "_load", failed)
    now[0] = 1
    with pytest.raises(RuntimeError):
        service.query(REQUEST, refresh=True)
    assert service.query(REQUEST)["value"] == 290
    now[0] = 300
    with pytest.raises(RuntimeError):
        service.query(REQUEST)


def test_native_bitmap_missing_cell_remains_null(message):
    import eccodes as ec
    handle = ec.codes_new_from_message(message)
    try:
        sample = ec.codes_grib_find_nearest(handle, REQUEST.latitude, REQUEST.longitude)[0]
        ec.codes_set(handle, "bitmapPresent", 1)
        ec.codes_set(handle, "missingValue", 9999)
        values = np.full(769741, 290.)
        values[sample["index"]] = 9999
        ec.codes_set_values(handle, values)
        masked = ec.codes_get_message(handle)
    finally:
        ec.codes_release(handle)
    result = decode_temperature(masked, REQUEST)
    assert result["value"] is None and result["native_masked"] is True


@pytest.mark.parametrize("fail", [False, True])
def test_overlapping_refreshes_share_one_outcome(tmp_path, monkeypatch, fail):
    import threading
    from concurrent.futures import Future, ThreadPoolExecutor
    import weather_api.rrfs_query as module
    started, finish, joined = threading.Event(), threading.Event(), threading.Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            joined.set()
            return super().result(timeout)
    monkeypatch.setattr(module, "Future", ObservedFuture)
    service = RRFSQueryService(tmp_path)
    calls = []
    def load(_):
        calls.append(1)
        started.set()
        assert finish.wait(3)
        if fail:
            raise RuntimeError("fixture failure")
        return {"value": 290}
    monkeypatch.setattr(service, "_load", load)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.query, REQUEST, refresh=True)
        assert started.wait(3)
        second = executor.submit(service.query, REQUEST, refresh=True)
        assert joined.wait(3)
        finish.set()
        if fail:
            for future in (first, second):
                with pytest.raises(RuntimeError):
                    future.result()
        else:
            assert first.result() == second.result()
    assert len(calls) == 1


@pytest.mark.parametrize("status", [200, 302, 403])
def test_range_refusal_never_downloads_a_full_file(tmp_path, message, status):
    def handler(request):
        if request.url.path.endswith(".idx"):
            return httpx.Response(200, stream=httpx.ByteStream(index(len(message))))
        return httpx.Response(status, stream=httpx.ByteStream(b"refused"))
    service = RRFSQueryService(tmp_path, transport=httpx.MockTransport(handler),
        decoder=lambda *_: pytest.fail("invalid response reached decoder"))
    with pytest.raises(RuntimeError, match="request failed"):
        service.query(REQUEST)


def test_dst_repeated_hour_requests_do_not_share_cached_run(tmp_path, monkeypatch):
    from zoneinfo import ZoneInfo
    zone = ZoneInfo("America/New_York")
    valid = datetime(2026, 11, 1, 7, tzinfo=UTC)
    first = RRFSRequest(datetime(2026, 11, 1, 1, tzinfo=zone, fold=0), valid, 47.56, -52.71)
    second = RRFSRequest(datetime(2026, 11, 1, 1, tzinfo=zone, fold=1), valid, 47.56, -52.71)
    service = RRFSQueryService(tmp_path)
    loads = []
    def load(request):
        loads.append(request.run_time.astimezone(UTC))
        return {"run_time": request.run_time.astimezone(UTC).isoformat()}
    monkeypatch.setattr(service, "_load", load)
    assert service.query(first)["run_time"] == "2026-11-01T05:00:00+00:00"
    assert service.query(second)["run_time"] == "2026-11-01T06:00:00+00:00"
    assert first != second and len({first, second}) == 2
    assert len(loads) == 2


def test_dst_crossing_lead_uses_elapsed_utc_hours():
    from zoneinfo import ZoneInfo
    zone = ZoneInfo("America/New_York")
    request = RRFSRequest(datetime(2026, 11, 1, 0, tzinfo=zone),
                          datetime(2026, 11, 1, 2, tzinfo=zone), 47.56, -52.71)
    assert request.url.endswith("rrfs.t04z.2dfld.13km.f003.na.grib2")
    selected = b"1:0:d=2026110104:TMP:2 m above ground:3 hour fcst:\n2:100:d=2026110104:RH:2 m above ground:3 hour fcst:\n"
    assert temperature_range(selected, request).as_tuple() == (0, 99)
    assert request.run_time == datetime(2026, 11, 1, 4, tzinfo=UTC)
    assert request.valid_time == datetime(2026, 11, 1, 7, tzinfo=UTC)
