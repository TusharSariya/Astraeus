from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import sleep

import pytest
import xarray
import json
import zipfile

from weather_api.gfs_query import GFS_TIMELINE_LISTING_MAX_BYTES, GFSQueryCoordinator, GFSQueryEntry, GFSQueryService, GFSRequestKey
from ingest.contract import Artifact, RunCandidate, RunResult
from ingest.adapters.noaa_s3 import MAX_IDX_BYTES
from ingest.grib import write_zarr
from ingest.grib import RH_PHASE_MIXED_LINEAR_253K_273K

UTC = timezone.utc
KEY = GFSRequestKey(
    index_url="https://example/gfs.f003.idx",
    grib_url="https://example/gfs.f003",
    ranges=((10, 19),),
    fields=("TMP:2 m above ground",),
    bounds=(("north", 50.5), ("south", 45.0), ("west", -58.0), ("east", -46.0)),
)


def entry(key=KEY):
    instant = datetime(2026, 9, 6, 15, tzinfo=UTC)
    return GFSQueryEntry(
        key=key, run_time=datetime(2026, 9, 6, 12, tzinfo=UTC), valid_time=instant,
        fetched_at=instant, content_digest="a" * 64, values={"temperature_2m": 12.0},
        provenance={"source_id": "noaa-gfs"}, payloads=(b"x" * 1024,),
    )


def test_fresh_hit_issues_zero_additional_provider_loads():
    calls = []
    service = GFSQueryService(lambda key: calls.append(key) or entry(), ttl_seconds=60)

    assert service.query(KEY) is service.query(KEY)
    assert calls == [KEY]


def test_expired_entry_is_not_used_when_replacement_fails():
    now = [0.0]
    calls = [0]

    def load(key):
        calls[0] += 1
        if calls[0] == 2:
            raise OSError("provider unavailable")
        return entry(key)

    service = GFSQueryService(load, ttl_seconds=60, clock=lambda: now[0])
    service.query(KEY)
    now[0] = 60.0

    with pytest.raises(OSError, match="unavailable"):
        service.query(KEY)
    assert calls[0] == 2


def test_concurrent_identical_misses_coalesce_to_one_provider_load():
    calls = []

    def load(key):
        calls.append(key)
        return entry(key)

    service = GFSQueryService(load)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.query(KEY), range(8)))

    assert len(calls) == 1
    assert all(result is results[0] for result in results)


def test_concurrent_failure_is_one_generation_and_one_provider_load():
    started = Event()
    release = Event()
    calls = []

    def fail(key):
        calls.append(key)
        started.set()
        release.wait(timeout=2)
        raise OSError("provider unavailable")

    service = GFSQueryService(fail)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(service.query, KEY) for _ in range(8)]
        assert started.wait(timeout=1)
        sleep(0.05)
        release.set()
        for future in futures:
            with pytest.raises(OSError, match="unavailable"):
                future.result()

    assert calls == [KEY]


def test_loader_cannot_replace_canonical_request_identity():
    other = GFSRequestKey("other", KEY.grib_url, KEY.ranges, KEY.fields, KEY.bounds)
    service = GFSQueryService(lambda _key: entry(other))

    with pytest.raises(ValueError, match="different provider request identity"):
        service.query(KEY)


def test_cache_evicts_lru_entries_under_count_bound():
    calls = []
    service = GFSQueryService(lambda key: calls.append(key) or entry(key), max_entries=1)
    other = GFSRequestKey("other", KEY.grib_url, KEY.ranges, KEY.fields, KEY.bounds)

    service.query(KEY)
    service.query(other)
    service.query(KEY)

    assert calls == [KEY, other, KEY]


def test_cache_refuses_oversize_normalized_entry():
    oversized = GFSQueryEntry(**{**entry().__dict__, "payloads": (b"x" * 2048,)})
    service = GFSQueryService(lambda _key: oversized, max_bytes=1024)

    with pytest.raises(ValueError, match="finite byte ceiling"):
        service.query(KEY)


def test_cache_configuration_cannot_exceed_source_ceiling():
    with pytest.raises(ValueError, match="source-local ceiling"):
        GFSQueryService(entry, max_entries=5)
    with pytest.raises(ValueError, match="source-local ceiling"):
        GFSQueryService(entry, max_bytes=256 * 1024 * 1024 + 1)


def test_coordinator_fetches_one_native_lead_then_serves_exact_cache_hit(tmp_path, monkeypatch):
    run_time = datetime(2026, 9, 6, 12, tzinfo=UTC)
    idx = "1:0:d=2026090612:TMP:2 m above ground:3 hour fcst:\n2:4:d=2026090612:HGT:surface:3 hour fcst:\n"

    class Client:
        def __init__(self):
            self.calls = []
        def get_bytes(self, url, *, max_bytes):
            self.calls.append((url, max_bytes))
            return idx.encode()

    class Adapter:
        _base_url = "https://example"
        _bounds = {"north": 50.5, "south": 45.0, "west": -58.0, "east": -46.0}
        def __init__(self):
            self.client = Client()
            self.discoveries = 0
            self.fetches = []
        def _get_client(self): return self.client
        def discover(self, window):
            self.discoveries += 1
            return [RunCandidate("gfs-2026090612", run_time, detail={"date_str": "20260906", "cycle": "12"})]
        def fetch_selected(self, candidate, selected, workdir):
            self.fetches.append(selected)
            path = workdir / "surface.zip"
            path.write_bytes(b"normalized")
            return RunResult("noaa-gfs", candidate.provider_run_id, run_time, selected, True, True,
                             [Artifact("surface", "application/zarr+zip", path, {"source_id": "noaa-gfs"})])

    adapter = Adapter()
    def fetch(key, candidate, selected):
        result = adapter.fetch_selected(candidate, selected, tmp_path)
        payloads = tuple(artifact.payload_path.read_bytes() for artifact in result.artifacts)
        return GFSQueryEntry(
            key, run_time, selected, selected, "c" * 64,
            {"logical_names": [artifact.logical_name for artifact in result.artifacts]},
            {artifact.logical_name: artifact.provenance for artifact in result.artifacts}, payloads,
        )

    coordinator = GFSQueryCoordinator(adapter, now=lambda: run_time, bounded_fetch=fetch)
    selected = run_time + timedelta(hours=3, minutes=17)

    first = coordinator.query(selected)
    second = coordinator.query(selected)

    assert first is second
    assert first.valid_time == run_time + timedelta(hours=3)
    assert first.payloads == (b"normalized",)
    assert adapter.discoveries == 1
    assert adapter.fetches == [run_time + timedelta(hours=3)]
    assert len(adapter.client.calls) == 1
    assert adapter.client.calls[0][1] == MAX_IDX_BYTES


def test_cached_native_payload_uses_existing_point_evidence_builder(tmp_path):
    run_time = datetime(2026, 9, 6, 12, tzinfo=UTC)
    valid_time = run_time + timedelta(hours=3)
    path = tmp_path / "surface.zarr.zip"
    dataset = xarray.Dataset(
        {"temperature_2m": (("valid_time", "latitude", "longitude"), [[[14.25]]], {"units": "degC"})},
        coords={"valid_time": [valid_time.replace(tzinfo=None)], "latitude": [47.56], "longitude": [-52.71]},
    )
    write_zarr(dataset, path)
    provenance = {
        "source_id": "noaa-gfs", "producer": "NOAA / NCEP", "product": "Global Forecast System",
        "native_resolution": "0.25 deg", "native_crs": "EPSG:4326", "adapter_version": "test",
        "quality": {"status": "passed", "flags": []},
        "coverage": {"status": "complete", "expected": 1, "present": 1},
        "evidence_classes": ["retrieved"],
    }
    cached = GFSQueryEntry(
        KEY, run_time, valid_time, valid_time + timedelta(minutes=2), "b" * 64,
        {"logical_names": ["surface"]}, {"surface": provenance}, (path.read_bytes(),),
    )
    coordinator = object.__new__(GFSQueryCoordinator)
    coordinator.query = lambda _selected: cached

    fields, _consensus, sources = coordinator.point_fields(47.5615, -52.7126, valid_time)

    temperature = next(item for item in fields if item.field == "temperature")
    assert temperature.value == 14.25
    assert temperature.provenance.source_id == "noaa-gfs"
    assert temperature.provenance.valid_time == valid_time
    assert temperature.provenance.run_time == run_time
    assert temperature.provenance.run_stale is False
    assert temperature.provenance.run_stale_reason is None
    assert sources == ["noaa-gfs"]


def test_cached_native_payload_uses_existing_profile_evidence_builder(tmp_path, monkeypatch):
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    run_time = datetime(2026, 9, 6, 12, tzinfo=UTC)
    valid_time = run_time + timedelta(hours=3)
    path = tmp_path / "surface.zarr.zip"
    variables = {}
    for pressure, temperature, humidity in ((850, 8.0, 81.0), (700, -3.0, 76.0), (500, -18.5, 72.0)):
        variables[f"temperature_{pressure}hPa"] = (("valid_time", "latitude", "longitude"), [[[temperature]]], {"units": "degC"})
        variables[f"relative_humidity_{pressure}hPa"] = (("valid_time", "latitude", "longitude"), [[[humidity]]], {"units": "percent", "rh_phase_convention": RH_PHASE_MIXED_LINEAR_253K_273K})
        variables[f"wind_u_{pressure}hPa"] = (("valid_time", "latitude", "longitude"), [[[3.0]]], {"units": "m s-1"})
        variables[f"wind_v_{pressure}hPa"] = (("valid_time", "latitude", "longitude"), [[[4.0]]], {"units": "m s-1"})
    variables["wind_u_300hPa"] = (("valid_time", "latitude", "longitude"), [[[3.0]]], {"units": "m s-1"})
    variables["wind_v_300hPa"] = (("valid_time", "latitude", "longitude"), [[[4.0]]], {"units": "m s-1"})
    dataset = xarray.Dataset(
        variables,
        coords={"valid_time": [valid_time.replace(tzinfo=None)], "latitude": [47.56], "longitude": [-52.71]},
    )
    write_zarr(dataset, path)
    provenance = {
        "source_id": "noaa-gfs", "producer": "NOAA / NCEP", "product": "Global Forecast System",
        "native_resolution": "0.25 deg", "native_crs": "EPSG:4326", "adapter_version": "test",
        "quality": {"status": "passed", "flags": []},
        "coverage": {"status": "complete", "expected": len(variables), "present": len(variables)},
        "evidence_classes": ["retrieved"],
    }
    cached = GFSQueryEntry(
        KEY, run_time, valid_time, valid_time + timedelta(minutes=2), "b" * 64,
        {"logical_names": ["surface"]}, {"surface": provenance}, (path.read_bytes(),),
    )
    coordinator = object.__new__(GFSQueryCoordinator)
    coordinator.query = lambda _selected: cached

    levels = coordinator.profile_levels(47.5615, -52.7126, valid_time, (1000, 850, 700, 500, 300))

    assert [level.pressure_hpa for level in levels] == [850, 700, 500, 300]
    assert 1000 not in [level.pressure_hpa for level in levels]
    fields = {field.field: field for field in levels[2].fields}
    assert fields["temperature"].value == -18.5
    assert fields["relative_humidity"].value == 72.0
    assert fields["relative_humidity"].phase == "mixed"
    assert fields["wind_speed"].value == 5.0
    assert fields["wind_speed"].provenance.evidence_class == "derived_here"
    assert fields["temperature"].provenance.valid_time == valid_time
    assert fields["temperature"].provenance.run_time == run_time
    wind_300 = {field.field: field for field in levels[-1].fields}
    assert wind_300["wind_speed"].value == 5.0
    assert wind_300["wind_speed"].provenance.derivation_version
    assert {item.field for item in wind_300["wind_speed"].provenance.derivation_inputs} == {"wind_u_300hPa", "wind_v_300hPa"}
    assert not {"wind_u_300hPa", "wind_v_300hPa"} & set(wind_300)

    import weather_api.gfs_query as gfs_query
    from weather_api.app import get_profile

    monkeypatch.setattr(gfs_query, "gfs_query_coordinator", lambda: coordinator)
    response = get_profile(47.5615, -52.7126, valid_time, "GFS")
    assert response.data_mode.value == "live"
    assert [level.pressure_hpa for level in response.levels] == [850, 700, 500, 300]
    assert response.valid_time == valid_time
    assert "native timestep" in response.notices[0]


def test_live_point_selected_gfs_uses_demand_payload_without_artifact_store(tmp_path, monkeypatch):
    from weather_api.app import _live_point
    import weather_api.gfs_query as gfs_query

    run_time = datetime(2026, 9, 6, 12, tzinfo=UTC)
    valid_time = run_time + timedelta(hours=3)
    path = tmp_path / "surface.zarr.zip"
    write_zarr(
        xarray.Dataset(
            {"temperature_2m": (("valid_time", "latitude", "longitude"), [[[14.25]]], {"units": "degC"})},
            coords={"valid_time": [valid_time.replace(tzinfo=None)], "latitude": [47.56], "longitude": [-52.71]},
        ),
        path,
    )
    provenance = {
        "source_id": "noaa-gfs", "producer": "NOAA / NCEP", "product": "Global Forecast System",
        "native_resolution": "0.25 deg", "native_crs": "EPSG:4326", "adapter_version": "test",
        "quality": {"status": "passed", "flags": []},
        "coverage": {"status": "complete", "expected": 1, "present": 1},
        "evidence_classes": ["retrieved"],
    }
    cached = GFSQueryEntry(
        KEY, run_time, valid_time, valid_time + timedelta(minutes=2), "b" * 64,
        {"logical_names": ["surface"]}, {"surface": provenance}, (path.read_bytes(),),
    )
    coordinator = object.__new__(GFSQueryCoordinator)
    coordinator.query = lambda _selected: cached
    monkeypatch.setattr(gfs_query, "gfs_query_coordinator", lambda: coordinator)

    response = _live_point(47.5615, -52.7126, valid_time + timedelta(minutes=17), "GFS")

    assert response.data_mode.value == "live"
    assert response.selection.selected_source_id == "noaa-gfs"
    assert response.fields[0].provenance.valid_time == valid_time
    assert response.fields[0].provenance.run_stale is False
    assert response.fields[0].provenance.run_stale_reason is None
    assert any("no temporal interpolation" in notice for notice in response.notices)


def test_timeline_lists_actual_native_keys_once_without_fetching_grib_payloads():
    run_time = datetime(2026, 9, 6, 12, tzinfo=UTC)
    keys = [0, 120, 121, 123, 342, 384, 385]
    xml = "<ListBucketResult><IsTruncated>false</IsTruncated>" + "".join(
        f"<Contents><Key>gfs.20260906/12/atmos/gfs.t12z.pgrb2.0p25.f{lead:03d}.idx</Key></Contents>" for lead in keys
    ) + "</ListBucketResult>"

    class Client:
        calls = []
        def get_bytes_with_receipt(self, url, *, max_bytes):
            self.calls.append((url, max_bytes))
            return xml.encode(), {"url": url, "bytes": len(xml), "completed_at": run_time.isoformat()}

    class Adapter:
        _base_url = "https://example.invalid"
        client = Client()
        def _get_client(self): return self.client
        def discover(self, _window):
            return [RunCandidate("gfs-2026090612", run_time, detail={"date_str": "20260906", "cycle": "12"})]

    coordinator = GFSQueryCoordinator(Adapter(), now=lambda: run_time + timedelta(hours=6))
    first, receipt = coordinator.timeline_times(run_time + timedelta(hours=6))
    second, repeated_receipt = coordinator.timeline_times(run_time + timedelta(hours=6))

    # f121 is not on the post-f120 native three-hour cadence. f384 is a real
    # provider lead but falls beyond 14 days from this six-hour-old request.
    assert first == tuple(run_time + timedelta(hours=lead) for lead in (0, 120, 123, 342))
    assert second == first
    assert repeated_receipt == receipt
    assert len(Adapter.client.calls) == 1
    assert Adapter.client.calls[0][1] == GFS_TIMELINE_LISTING_MAX_BYTES
    assert "list-type=2" in Adapter.client.calls[0][0]


@pytest.mark.parametrize("xml", [
    "<ListBucketResult><IsTruncated>true</IsTruncated></ListBucketResult>",
    "<!DOCTYPE x [<!ENTITY y 'z'>]><ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>",
])
def test_timeline_refuses_incomplete_or_declared_xml(xml):
    run_time = datetime(2026, 9, 6, 12, tzinfo=UTC)
    class Client:
        def get_bytes_with_receipt(self, _url, *, max_bytes):
            assert max_bytes == GFS_TIMELINE_LISTING_MAX_BYTES
            return xml.encode(), {}
    class Adapter:
        _base_url = "https://example.invalid"
        def _get_client(self): return Client()
        def discover(self, _window): return [RunCandidate("gfs-2026090612", run_time, detail={"date_str": "20260906", "cycle": "12"})]
    with pytest.raises(ValueError):
        GFSQueryCoordinator(Adapter(), now=lambda: run_time).timeline_times(run_time)


def test_production_loader_invokes_locked_child_and_refuses_failed_validation(tmp_path, monkeypatch):
    run_time = datetime(2026, 9, 6, 12, tzinfo=UTC)
    idx = "1:0:d=2026090612:TMP:2 m above ground:3 hour fcst:\n2:4:d=2026090612:HGT:surface:3 hour fcst:\n"

    class Client:
        def get_bytes(self, _url, *, max_bytes):
            assert max_bytes == MAX_IDX_BYTES
            return idx.encode()

    class Adapter:
        _base_url = "https://example"
        _bounds = {"north": 50.5, "south": 45.0, "west": -58.0, "east": -46.0}
        def _get_client(self): return Client()
        def discover(self, _window):
            return [RunCandidate("gfs-2026090612", run_time, detail={"date_str": "20260906", "cycle": "12"})]

    calls = []
    def child(*, command, stdin, destination, limits, timeout_seconds):
        calls.append((command, json.loads(stdin), limits, timeout_seconds))
        manifest = {
            "source_id": "noaa-gfs", "provider_run_id": "gfs-2026090612",
            "run_time": run_time.isoformat(), "retrieved_at": (run_time + timedelta(minutes=1)).isoformat(),
            "valid_time": (run_time + timedelta(hours=3)).isoformat(),
            "complete": False, "qc_passed": True,
            "artifacts": [{"logical_name": "surface", "name": "surface.zip", "provenance": {}}],
        }
        with zipfile.ZipFile(destination, "w") as bundle:
            bundle.writestr("result.json", json.dumps(manifest))
            bundle.writestr("artifacts/surface.zip", b"payload")

    monkeypatch.setattr("weather_api.gfs_query.run_bounded_process", child)
    coordinator = GFSQueryCoordinator(Adapter(), now=lambda: run_time)
    with pytest.raises(ValueError, match="incomplete or failed-QC"):
        coordinator.query(run_time + timedelta(hours=3))
    assert len(calls) == 1
    assert calls[0][2].address_space_bytes == 1024**3
    assert calls[0][2].output_bytes == 64 * 1024**2
    escaped = json.dumps({"idx_text_by_lead": {3: "\x00" * MAX_IDX_BYTES}}).encode()
    assert len(escaped) <= calls[0][2].stdin_bytes
