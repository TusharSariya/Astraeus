"""Unregistered #270 native identity, bounded demand and finite-cache evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from threading import Event
from time import sleep
import httpx
import pytest
from weather_api.ecmwf_query import (ECMWFQueryCoordinator, ECMWFQueryUnavailable, ECMWFHTTP,
    FIELDS, PRODUCTS, MAX_ENTRIES, MAX_MEMBER_BYTES, TTL_SECONDS, native_lead, select_records)
RUN = datetime(2026, 9, 7, 12, tzinfo=UTC)
BASE = "https://data.ecmwf.int/forecasts"

def rows(source="ecmwf-ifs", lead=0):
    return [{"param": param, "levtype": "sfc", "date": "20260907", "time": "1200", "step": str(lead),
        "model": PRODUCTS[source][0], "class": "od" if source == "ecmwf-ifs" else "ai", "stream": "oper", "type": "fc", "_offset": i * 4, "_length": 4}
        for i, param in enumerate(FIELDS)]

class Fixture:
    def __init__(self, source="ecmwf-ifs"):
        self.source, self.calls, self.fail = source, [], False
        self.directory = f"{BASE}/20260907/12z/{PRODUCTS[source][0]}/0p25/oper/"
        self.url = self.directory + "20260907120000-0h-oper-fc.grib2"
        self.client = httpx.Client(transport=httpx.MockTransport(self.handle))
    def handle(self, request):
        self.calls.append((str(request.url), request.headers.get("range")))
        if self.fail: return httpx.Response(503)
        if str(request.url) == self.directory:
            return httpx.Response(200, text='<a href="20260907120000-0h-oper-fc.grib2">native</a>')
        if str(request.url) == self.url.removesuffix(".grib2") + ".index":
            return httpx.Response(200, text="\n".join(map(json.dumps, rows(self.source))))
        if str(request.url) == self.url:
            value = request.headers["range"].removeprefix("bytes=")
            return httpx.Response(206, content=b"GRIB", headers={"Content-Range": f"bytes {value}/100", "Set-Cookie": "private=excluded"})
        return httpx.Response(404)

def decoded(request):
    return {"source_id": request["source_id"], "run_time": request["run_time"], "valid_time": request["valid_time"],
        "fields": [value[0] for value in FIELDS.values()], "complete": True, "qc_passed": True}, b"normalized"

def coordinator(fixture, clock=None, decoder=decoded):
    clock = clock or [0.0]
    return ECMWFQueryCoordinator(fixture.source, now=lambda: RUN, clock=lambda: clock[0], client=fixture.client, decoder=decoder)

@pytest.mark.parametrize("source", PRODUCTS)
def test_exact_native_product_cache_hit_and_safe_receipts(source):
    fixture = Fixture(source); service = coordinator(fixture); first = service.query(RUN)
    assert service.query(RUN) is first
    assert first.source_id == source and first.run_time == first.valid_time == RUN
    assert first.expires_at == RUN + timedelta(seconds=TTL_SECONDS)
    assert first.provenance["distributed_grid"] == "regular latitude-longitude 0.25 degrees"
    assert first.provenance["operational"] is False
    assert [row["param"] for row in first.provenance["index_records"]] == list(FIELDS)
    assert len(fixture.calls) == 12
    assert len([row for row in fixture.calls if row[1]]) == 4
    assert all("set-cookie" not in receipt["response_headers"] for receipt in first.provenance["transport_receipts"])

def test_expiry_failed_refresh_and_explicit_revalidation():
    fixture = Fixture(); clock = [0.0]; service = coordinator(fixture, clock)
    first = service.query(RUN); count = len(fixture.calls); clock[0] = 100
    second = service.query(RUN, refresh=True)
    assert second is not first and len(fixture.calls) == count * 2
    expiry = service._entries[(RUN, None)][0]; clock[0] = 110
    assert service.query(RUN) is second and service._entries[(RUN, None)][0] == expiry
    fixture.fail = True; clock[0] = expiry
    with pytest.raises(ECMWFQueryUnavailable, match="HTTPStatusError"): service.query(RUN)
    assert service._entries[(RUN, None)][0] == expiry

@pytest.mark.parametrize("source,selected", [("ecmwf-ifs", RUN + timedelta(hours=1)),
    ("ecmwf-aifs-single", RUN + timedelta(hours=3)), ("ecmwf-ifs", RUN + timedelta(minutes=1)),
    ("ecmwf-ifs", RUN + timedelta(hours=3))])
def test_non_native_or_unpublished_time_cannot_fetch_payload(source, selected):
    fixture = Fixture(source); service = coordinator(fixture)
    with pytest.raises(ECMWFQueryUnavailable): service.query(selected)
    assert not any(headers for _, headers in fixture.calls)

def test_named_run_does_not_substitute_latest():
    fixture = Fixture(); service = coordinator(fixture)
    with pytest.raises(ECMWFQueryUnavailable, match="no longer available"): service.query(RUN, run_id="removed")
    assert not any(headers for _, headers in fixture.calls)

@pytest.mark.parametrize("mutate", [lambda rows: rows[0].update(step="3"), lambda rows: rows[0].update(model="aifs-single"),
    lambda rows: rows[0].update(number="1"), lambda rows: rows[0].update(_length=MAX_MEMBER_BYTES + 1),
    lambda rows: rows.append(rows[0]), lambda rows: rows.pop(), lambda rows: rows[0].update(_offset=True)])
def test_native_index_rejects_ambiguous_or_incomplete_identity(mutate):
    records = rows(); mutate(records)
    with pytest.raises(ECMWFQueryUnavailable): select_records("\n".join(map(json.dumps, records)), "ecmwf-ifs", RUN, 0)

@pytest.mark.parametrize("fail", [False, True])
def test_identical_concurrent_misses_coalesce(fail):
    entered, release = Event(), Event(); calls = []
    def decode(request):
        calls.append(request); entered.set(); assert release.wait(2)
        if fail: raise ValueError("decoder unavailable")
        return decoded(request)
    fixture = Fixture(); service = coordinator(fixture, decoder=decode)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(service.query, RUN, refresh=True) for _ in range(8)]
        assert entered.wait(2); sleep(0.05); release.set()
        if fail:
            for future in futures:
                with pytest.raises(ECMWFQueryUnavailable, match="ValueError"): future.result()
        else:
            results = [future.result() for future in futures]
            assert all(result is results[0] for result in results)
    assert len(calls) == 1 and len(fixture.calls) == 12

def test_cache_and_concurrency_bounds():
    fixture = Fixture(); service = coordinator(fixture)
    with service._lock: service._inflight = {key: object() for key in range(MAX_ENTRIES)}
    with pytest.raises(ECMWFQueryUnavailable, match="concurrent selection bound"): service.query(RUN)
    assert not fixture.calls

@pytest.mark.parametrize("response", [httpx.Response(200, content=b"GRIB"),
    httpx.Response(206, content=b"GRIB", headers={"Content-Range": "bytes 1-4/100"}),
    httpx.Response(206, content=b"GRIBX", headers={"Content-Range": "bytes 0-3/100"}),
    httpx.Response(302, headers={"Location": "https://other.invalid/"})])
def test_range_transport_refuses_wrong_status_identity_size_and_redirect(response):
    transport = ECMWFHTTP(httpx.Client(transport=httpx.MockTransport(lambda _: response)))
    with pytest.raises((ECMWFQueryUnavailable, httpx.HTTPStatusError)): transport.read(BASE, limit=4, byte_range=(0, 3))
    assert not transport.receipts

def test_decoder_manifest_cannot_change_native_identity():
    fixture = Fixture()
    def invalid(request):
        manifest, payload = decoded(request); manifest["source_id"] = "ecmwf-aifs-single"; return manifest, payload
    with pytest.raises(ECMWFQueryUnavailable, match="decoder identity"): coordinator(fixture, decoder=invalid).query(RUN)

def test_native_horizon_is_cycle_and_product_specific():
    assert native_lead("ecmwf-ifs", RUN, RUN + timedelta(hours=360)) == 360
    short = RUN + timedelta(hours=6)
    with pytest.raises(ECMWFQueryUnavailable): native_lead("ecmwf-ifs", short, short + timedelta(hours=150))
    assert native_lead("ecmwf-aifs-single", short, short + timedelta(hours=360)) == 360

def test_unselected_interval_product_does_not_change_instantaneous_field_identity():
    records = rows(); records.append({**records[0], "param": "10fg", "step": "3"})
    assert len(select_records("\n".join(map(json.dumps, records)), "ecmwf-ifs", RUN, 0)) == 4


def test_default_decoder_command_and_bundle_are_bounded(tmp_path, monkeypatch):
    import zipfile
    from weather_api import ecmwf_query
    calls = []
    def child(**kwargs):
        calls.append(kwargs)
        with zipfile.ZipFile(kwargs["destination"], "w") as bundle:
            bundle.writestr("manifest.json", "{}")
            bundle.writestr("surface.zarr.zip", b"normalized")
    monkeypatch.setattr(ecmwf_query, "run_bounded_process", child)
    service = coordinator(Fixture())
    assert service._decode({"directory": str(tmp_path)}) == ({}, b"normalized")
    assert calls[0]["command"][-1] == "{output}"
    assert calls[0]["limits"].address_space_bytes == 1024**3
    assert calls[0]["limits"].output_bytes == 16 * 1024 * 1024
    assert calls[0]["timeout_seconds"] == 120


def test_decoder_elapsed_time_cannot_extend_advertised_expiry():
    fixture = Fixture(); elapsed = [0.0]; reference = [RUN]
    def delayed(request):
        elapsed[0] = 120.0; reference[0] = RUN + timedelta(seconds=120)
        return decoded(request)
    service = ECMWFQueryCoordinator(fixture.source, now=lambda: reference[0], clock=lambda: elapsed[0], client=fixture.client, decoder=delayed)
    result = service.query(RUN)
    assert result.expires_at == RUN + timedelta(seconds=600)
    assert service._entries[(RUN, None)][0] == 600.0


def test_clock_rollback_cannot_extend_final_byte_expiry():
    fixture = Fixture(); elapsed = [0.0]; reference = [RUN]
    def delayed(request):
        elapsed[0] = 120.0
        reference[0] = RUN - timedelta(hours=1)
        return decoded(request)
    service = ECMWFQueryCoordinator(fixture.source, now=lambda: reference[0], clock=lambda: elapsed[0],
        client=fixture.client, decoder=delayed)
    service.query(RUN)
    assert service._entries[(RUN, None)][0] == 600.0
    fixture.fail = True
    elapsed[0] = 600.0
    with pytest.raises(ECMWFQueryUnavailable):
        service.query(RUN)


def test_failed_refresh_keeps_unexpired_prior_evidence_without_renewing():
    fixture = Fixture(); elapsed = [0.0]; service = coordinator(fixture, elapsed)
    first = service.query(RUN)
    fixture.fail = True; elapsed[0] = 100.0
    with pytest.raises(ECMWFQueryUnavailable):
        service.query(RUN, refresh=True)
    calls = len(fixture.calls)
    assert service.query(RUN) is first and len(fixture.calls) == calls
    assert service._entries[(RUN, None)][0] == 600.0


def test_oversized_decoder_result_is_not_cached():
    from weather_api.ecmwf_query import MAX_OUTPUT_BYTES
    fixture = Fixture()
    def huge(request):
        manifest, _ = decoded(request); return manifest, b"x" * MAX_OUTPUT_BYTES
    service = coordinator(fixture, decoder=huge)
    with pytest.raises(ECMWFQueryUnavailable, match="cache entry exceeds bound"): service.query(RUN)
    assert not service._entries


def test_acquisition_deadline_refuses_more_network_work():
    fixture = Fixture(); transport = ECMWFHTTP(fixture.client)
    transport.deadline = 0
    with pytest.raises(ECMWFQueryUnavailable, match="deadline exceeded"):
        transport.get_text(fixture.directory)
    assert not fixture.calls


def test_older_run_cannot_be_assigned_current_version_basis():
    old = datetime(2026, 5, 1, tzinfo=UTC)
    for source in PRODUCTS:
        with pytest.raises(ECMWFQueryUnavailable, match="predates"):
            native_lead(source, old, old)


def test_ifs_native_index_can_omit_model_but_must_preserve_od_class():
    records = rows()
    for row in records: row.pop("model")
    assert len(select_records("\n".join(map(json.dumps, records)), "ecmwf-ifs", RUN, 0)) == 4
    records[0]["class"] = "ai"
    with pytest.raises(ECMWFQueryUnavailable): select_records("\n".join(map(json.dumps, records)), "ecmwf-ifs", RUN, 0)


def test_unsupported_product_and_geography_fail_before_transport():
    fixture = Fixture()
    with pytest.raises(ValueError): ECMWFQueryCoordinator("ecmwf-ens", client=fixture.client)
    with pytest.raises(ECMWFQueryUnavailable, match="outside"):
        coordinator(fixture).point_fields(0, 0, RUN)
    assert not fixture.calls


@pytest.mark.parametrize("source,cloud_units,cloud_native", [
    ("ecmwf-ifs", "(0 - 1)", 0.5),
    ("ecmwf-aifs-single", "%", 50.0),
])
def test_point_sampler_preserves_verified_native_units(source, cloud_units, cloud_native, tmp_path, monkeypatch):
    """Native unit tokens match retained September 5 IFS/AIFS GRIB metadata.

    Values/grid are synthetic; this exercises existing normalization and the
    real point sampler without reading provider data or admitting the source.
    """
    import xarray
    from ingest.grib import normalize_units, write_zarr
    from ingest.manifest import RequiredField, RunManifest
    from weather_api.ecmwf_query import ECMWFQueryEntry

    dataset = xarray.Dataset({
        name: (("valid_time", "latitude", "longitude"), [[[value]]], {"units": units})
        for name, value, units in (("t2m", 280.15, "K"), ("d2m", 278.15, "K"),
                                  ("msl", 101325.0, "Pa"), ("tcc", cloud_native, cloud_units))
    }, coords={"valid_time": [RUN.replace(tzinfo=None)], "latitude": [47.5], "longitude": [-52.75]})
    normalized = normalize_units(dataset).rename({"t2m": "temperature_2m", "d2m": "dew_point_2m",
        "msl": "mean_sea_level_pressure", "tcc": "total_cloud_geometric"})
    payload_path = write_zarr(normalized, tmp_path / "surface.zarr.zip")
    manifest = RunManifest(source, tuple(RequiredField(name, units) for name, units in FIELDS.values()))
    provenance = {"source_id": source, "product": PRODUCTS[source][1], "run_time": RUN.isoformat(),
        "quality": {"status": "passed", "flags": []}, "coverage": {"status": "complete", "fraction": 1.0},
        **manifest.as_manifest_block()}
    cached = ECMWFQueryEntry(source, RUN, RUN, RUN, RUN + timedelta(seconds=TTL_SECONDS),
        "a" * 64, provenance, payload_path.read_bytes())
    fixture = Fixture(source); service = coordinator(fixture)
    monkeypatch.setattr(service, "query", lambda *args, **kwargs: cached)
    fields, _, sources = service.point_fields(47.5, -52.75, RUN)
    by_key = {field.key: field for field in fields}
    for key, original, normalized_unit, expected in (
        ("temperature_2m", "K", "degC", 7.0), ("dew_point_2m", "K", "degC", 5.0),
        ("mean_sea_level_pressure", "Pa", "hPa", 1013.25),
        ("total_cloud_geometric", cloud_units, "percent", 50.0),
    ):
        field = by_key[key]
        assert field.value == pytest.approx(expected)
        assert field.provenance.original_units == original
        assert field.provenance.normalized_units == normalized_unit
        assert field.provenance.source_id == source
    assert sources == [source] and not fixture.calls
    assert "original_units" not in cached.provenance  # sampling must not mutate the cached entry
