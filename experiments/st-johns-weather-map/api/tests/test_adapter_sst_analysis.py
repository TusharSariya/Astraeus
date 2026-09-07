from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy
import pytest
import xarray
import zarr
from numcodecs import get_codec

from ingest.captures.sst_analysis import EVIDENCE_BOUNDS, OISSTAdapter, OSTIAAdapter
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc


def _client(handler) -> PoliteClient:
    client = PoliteClient(min_host_interval_seconds=0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return client


def _compressed(values: numpy.ndarray, spec: dict) -> bytes:
    return get_codec(spec["compressor"]).encode(values.astype(spec["dtype"]).tobytes())


def _ostia_metadata() -> dict:
    compressor = {"id": "blosc", "cname": "lz4", "clevel": 5, "shuffle": 1, "blocksize": 0}
    one = lambda shape, chunks, dtype, fill=None: {"shape": shape, "chunks": chunks, "dtype": dtype, "compressor": compressor, "filters": None, "fill_value": fill, "order": "C", "zarr_format": 2}
    return {"metadata": {
        "time/.zarray": one([1], [1], "<i4"),
        "latitude/.zarray": one([4], [4], "<f4"),
        "longitude/.zarray": one([4], [4], "<f4"),
        "analysed_sst/.zarray": one([1, 4, 4], [1, 4, 4], "<i2", -32768),
        "analysis_error/.zarray": one([1, 4, 4], [1, 4, 4], "<i2", -32768),
        "mask/.zarray": one([1, 4, 4], [1, 4, 4], "|i1", -128),
        "time/.zattrs": {"units": "seconds since 1981-01-01", "calendar": "proleptic_gregorian"},
        "latitude/.zattrs": {"units": "degrees_north"}, "longitude/.zattrs": {"units": "degrees_east"},
        "analysed_sst/.zattrs": {"scale_factor": 0.01, "add_offset": 273.15, "units": "kelvin"},
        "analysis_error/.zattrs": {"scale_factor": 0.01, "add_offset": 0.0, "units": "kelvin"},
        "mask/.zattrs": {"flag_masks": [1, 2, 4, 8, 16], "flag_meanings": "water land optional_lake_surface sea_ice optional_river_surface"},
    }}


@pytest.mark.parametrize(("chunk_size", "missing_chunk"), [(4, False), (2, False), (2, True)])
def test_ostia_fetch_preserves_uncertainty_mask_and_masks_land(tmp_path: Path, chunk_size, missing_chunk):
    metadata = _ostia_metadata(); specs = metadata["metadata"]
    for name in ("analysed_sst", "analysis_error", "mask"):
        specs[f"{name}/.zarray"]["chunks"] = [1, chunk_size, chunk_size]
    sst_raw = 1000 + numpy.arange(16).reshape(4, 4); sst_raw[2, 2] = -32768
    error_raw = numpy.full((4, 4), 25); error_raw[2, 2] = -32768
    seconds = int((datetime(2026, 9, 4, tzinfo=UTC) - datetime(1981, 1, 1, tzinfo=UTC)).total_seconds())
    payloads = {
        "/.zmetadata": json.dumps(metadata).encode(),
        "/time/0": _compressed(numpy.array([seconds]), specs["time/.zarray"]),
        "/latitude/0": _compressed(numpy.array([44.95, 45.05, 50.45, 50.55]), specs["latitude/.zarray"]),
        "/longitude/0": _compressed(numpy.array([-58.05, -57.95, -46.05, -45.95]), specs["longitude/.zarray"]),
    }
    mask_raw = numpy.ones((4, 4), dtype="int8"); mask_raw[1, 1] = 2
    for name, values in (("analysed_sst", sst_raw), ("analysis_error", error_raw), ("mask", mask_raw)):
        for y in range(4 // chunk_size):
            for x in range(4 // chunk_size):
                payloads[f"/{name}/0.{y}.{x}"] = _compressed(values[y*chunk_size:(y+1)*chunk_size, x*chunk_size:(x+1)*chunk_size], specs[f"{name}/.zarray"])
    if missing_chunk:
        del payloads["/analysed_sst/0.1.1"]
    requested = []
    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path.removeprefix("/ostia")
        requested.append(key)
        return httpx.Response(200, content=payloads[key]) if key in payloads else httpx.Response(404)
    adapter = OSTIAAdapter(_client(handler), "https://example.test/ostia")
    window = FetchWindow(datetime(2026, 9, 5, tzinfo=UTC), back_hours=48, forward_hours=0)
    candidate = adapter.discover(window)[0]
    if missing_chunk:
        with pytest.raises(httpx.HTTPStatusError):
            adapter.fetch(candidate, window, tmp_path)
        assert not list(tmp_path.glob("*.zarr.zip"))
        return
    result = adapter.fetch(candidate, window, tmp_path)
    assert len(requested) == len(set(requested)) == 4 + 3 * (4 // chunk_size) ** 2
    assert set(requested) == set(payloads)

    assert result.complete and result.qc_passed
    with zarr.storage.ZipStore(result.artifacts[0].payload_path, mode="r") as store:
        ds = xarray.open_zarr(store, consolidated=False).load()
    assert ds.sizes == {"valid_time": 1, "latitude": 2, "longitude": 2}
    assert ds.sea_surface_temperature.values[0, 0, 1] == pytest.approx(10.06, abs=0.0001)
    assert ds.sea_surface_temperature.values[0, 1, 0] == pytest.approx(10.09, abs=0.0001)
    assert numpy.isnan(ds.sea_surface_temperature.values[0, 0, 0])
    assert ds.sea_surface_temperature_uncertainty.values[0, 1, 0] == pytest.approx(0.25)
    assert numpy.isnan(ds.sea_surface_temperature.values[0, 1, 1]), "a water-cell fill value must not scale into a plausible temperature"
    assert numpy.isnan(ds.sea_surface_temperature_uncertainty.values[0, 1, 1])
    assert ds.sea_surface_temperature_mask.values[0, 0, 0] == 2
    assert result.artifacts[0].provenance["product_identity"] == "near-real-time Level 4 daily foundation SST analysis"


def test_oisst_discovers_preliminary_and_crops_native_grid(tmp_path: Path):
    day = datetime(2026, 9, 4, 12, tzinfo=UTC)
    dataset = xarray.Dataset(
        {"sst": (("time", "zlev", "lat", "lon"), numpy.array([[[[12.0, numpy.nan], [11.5, 11.0]]]], dtype="float32"), {"units": "Celsius"}),
         "err": (("time", "zlev", "lat", "lon"), numpy.array([[[[0.2, numpy.nan], [0.3, 0.4]]]], dtype="float32"), {"units": "Celsius"})},
        coords={"time": [numpy.datetime64(day.replace(tzinfo=None), "ns")], "zlev": [0.0], "lat": [45.125, 50.375], "lon": [302.125, 313.875]},
        attrs={"id": "oisst-avhrr-v02r01.20260904_preliminary.nc", "title": "NOAA Daily OISST Analysis"},
    )
    upstream = tmp_path / "upstream.nc"; dataset.to_netcdf(upstream)
    listing = '<a href="oisst-avhrr-v02r01.20260904_preliminary.nc">file</a>'
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/"):
            return httpx.Response(200, text=listing)
        return httpx.Response(200, content=upstream.read_bytes())
    adapter = OISSTAdapter(_client(handler), "https://example.test/oisst")
    window = FetchWindow(datetime(2026, 9, 5, tzinfo=UTC), back_hours=48, forward_hours=0)
    candidate = adapter.discover(window)[0]
    result = adapter.fetch(candidate, window, tmp_path / "fetch")
    assert candidate.provider_run_id.endswith("-preliminary")
    assert result.complete and result.qc_passed
    with zarr.storage.ZipStore(result.artifacts[0].payload_path, mode="r") as store:
        ds = xarray.open_zarr(store, consolidated=False).load()
    assert list(ds.longitude.values) == pytest.approx([-57.875, -46.125])
    assert numpy.isnan(ds.sea_surface_temperature.values[0, 0, 1])
    assert result.artifacts[0].provenance["product_identity"].endswith("_preliminary.nc")


def test_oisst_missing_uncertainty_fails_closed(tmp_path: Path):
    dataset = xarray.Dataset({"sst": (("time", "zlev", "lat", "lon"), numpy.ones((1, 1, 1, 1)))}, coords={"time": [numpy.datetime64("2026-09-04T12:00")], "zlev": [0], "lat": [47], "lon": [307]})
    upstream = tmp_path / "bad.nc"; dataset.to_netcdf(upstream)
    adapter = OISSTAdapter(_client(lambda request: httpx.Response(200, content=upstream.read_bytes())), "https://example.test")
    candidate = type("Candidate", (), {"urls": ["https://example.test/bad.nc"], "detail": {"filename": "bad.nc", "identity": "preliminary"}})()
    with pytest.raises(AdapterUnavailable, match="missing required fields"):
        adapter.fetch(candidate, FetchWindow(datetime(2026, 9, 5, tzinfo=UTC)), tmp_path / "fetch")


def test_ostia_stale_analysis_is_unavailable():
    metadata = _ostia_metadata(); spec = metadata["metadata"]["time/.zarray"]
    seconds = int((datetime(2026, 8, 1, tzinfo=UTC) - datetime(1981, 1, 1, tzinfo=UTC)).total_seconds())
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=metadata) if request.url.path.endswith(".zmetadata") else httpx.Response(200, content=_compressed(numpy.array([seconds]), spec))
    with pytest.raises(AdapterUnavailable, match="outside the evidence window"):
        OSTIAAdapter(_client(handler), "https://example.test/ostia").discover(FetchWindow(datetime(2026, 9, 5, tzinfo=UTC)))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda m: m["time/.zattrs"].update(units="days since 1981-01-01"), "time units/calendar changed"),
        (lambda m: m["analysed_sst/.zattrs"].update(units="Celsius"), "native SST/error units changed"),
        (lambda m: m["latitude/.zarray"].update(chunks=[2]), "single native coordinate chunk"),
        (lambda m: m["mask/.zattrs"].update(flag_meanings="water land"), "surface-mask declaration changed"),
    ],
)
def test_ostia_changed_native_metadata_is_refused(mutate, message):
    metadata = _ostia_metadata(); mutate(metadata["metadata"])
    client = _client(lambda request: httpx.Response(200, json=metadata))
    with pytest.raises(AdapterUnavailable, match=message):
        OSTIAAdapter(client, "https://example.test/ostia").discover(FetchWindow(datetime(2026, 9, 5, tzinfo=UTC)))


@pytest.mark.parametrize(
    ("sst_units", "identity", "valid_time", "message"),
    [
        ("kelvin", "oisst-avhrr-v02r01.20260904_preliminary.nc", "2026-09-04T12:00", "native SST/error units changed"),
        ("Celsius", "different-product.nc", "2026-09-04T12:00", "file id does not match"),
        ("Celsius", "oisst-avhrr-v02r01.20260904_preliminary.nc", "2026-09-03T12:00", "native analysis time differs"),
    ],
)
def test_oisst_changed_native_identity_is_refused(tmp_path: Path, sst_units, identity, valid_time, message):
    dataset = xarray.Dataset(
        {"sst": (("time", "zlev", "lat", "lon"), numpy.ones((1, 1, 1, 1)), {"units": sst_units}),
         "err": (("time", "zlev", "lat", "lon"), numpy.ones((1, 1, 1, 1)), {"units": "Celsius"})},
        coords={"time": [numpy.datetime64(valid_time)], "zlev": [0], "lat": [47], "lon": [307]},
        attrs={"id": identity, "title": "NOAA Daily OISST Analysis"},
    )
    upstream = tmp_path / "native.nc"; dataset.to_netcdf(upstream)
    adapter = OISSTAdapter(_client(lambda request: httpx.Response(200, content=upstream.read_bytes())), "https://example.test")
    candidate = type("Candidate", (), {"urls": ["https://example.test/native.nc"], "detail": {"filename": "oisst-avhrr-v02r01.20260904_preliminary.nc"}, "run_time": datetime(2026, 9, 4, 12, tzinfo=UTC), "provider_run_id": "oisst-test"})()
    with pytest.raises(AdapterUnavailable, match=message):
        adapter.fetch(candidate, FetchWindow(datetime(2026, 9, 5, tzinfo=UTC), back_hours=48), tmp_path / "fetch")


def test_ostia_chunk_count_ceiling_stops_before_field_download(tmp_path: Path, monkeypatch):
    import ingest.captures.sst_analysis as source
    metadata = _ostia_metadata()
    specs = metadata['metadata']
    for name in ('analysed_sst', 'analysis_error', 'mask'):
        specs[f'{name}/.zarray']['chunks'] = [1, 2, 2]
    monkeypatch.setattr(source, 'MAX_OSTIA_CHUNKS_PER_FIELD', 3)
    requested = []
    def handler(request):
        requested.append(request.url.path)
        name = request.url.path.split('/')[-2]
        assert name in ('latitude', 'longitude'), 'chunk budget must be checked before field download'
        values = [44.95, 45.05, 50.45, 50.55] if name == 'latitude' else [-58.05, -57.95, -46.05, -45.95]
        return httpx.Response(200, content=_compressed(numpy.array(values), specs[f'{name}/.zarray']))
    from ingest.contract import RunCandidate
    moment = datetime(2026, 9, 4, tzinfo=UTC)
    candidate = RunCandidate('ostia-20260904', moment, [], {'metadata': metadata, 'time_index': 0})
    with pytest.raises(AdapterUnavailable, match='chunk-count ceiling'):
        OSTIAAdapter(_client(handler), 'https://example.test').fetch(candidate, FetchWindow(datetime(2026, 9, 5, tzinfo=UTC), back_hours=48), tmp_path)
    assert len(requested) == 2
    assert not list(tmp_path.glob('*.zarr.zip'))
