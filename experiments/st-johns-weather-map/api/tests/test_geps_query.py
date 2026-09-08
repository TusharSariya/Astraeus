"""Offline GEPS experiment verification mapped to GOV-SPEC-004/005/006.

Provider statistic identity, bounded exact-time access and unverified QC remain
as specified by eccc-ensemble-experimental-integration and ensemble contracts.
"""
import hashlib
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest
from PIL import Image, TiffImagePlugin

from weather_api.geps_query import (
    GEPSBoundedLoader, GEPSRequestKey, GEPSSelectedLoader, GEPSQueryService,
    GEPS_COVERAGES, GEPS_CAPABILITY_BYTES, exact_advertised,
    validate_normalized_payload,
)
from ingest.adapters.eccc_geomet import parse_time_extent

RUN = datetime(2026, 9, 5, tzinfo=UTC)
VALID = RUN + timedelta(hours=12)


class FixtureClient:
    """Anonymous in-memory XML/GeoTIFF transport; never touches a socket."""
    def __init__(self, *, missing=False, masked=False, **kwargs):
        self.requests = []
        self.missing, self.masked = missing, masked

    def get_bytes_with_receipt(self, url, *, max_bytes):
        self.requests.append((url, max_bytes))
        query = {k.lower(): v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        if query["request"] == "GetCapabilities":
            name = query["layers"]
            valid = "2026-09-05T15:00:00Z" if self.missing else "2026-09-05T12:00:00Z"
            payload = f'''<WMS_Capabilities><Capability><Layer><Name>{name}</Name>
            <Title>Fixture</Title><Dimension name="time">{valid}</Dimension>
            <Dimension name="reference_time">2026-09-05T00:00:00Z</Dimension>
            </Layer></Capability></WMS_Capabilities>'''.encode()
        else:
            assert query["coverageid"] in GEPS_COVERAGES
            values = np.full((11, 24), 42, dtype=np.float32)
            values[0, 0] = -9999
            if self.masked:
                values[:] = -9999
            tags = TiffImagePlugin.ImageFileDirectory_v2()
            tags[33550] = (.5, .5, 0.)
            tags[33922] = (0., 0., 0., -58., 50.5, 0.)
            tags[34735] = (1, 1, 0, 2, 1025, 0, 1, 1, 2048, 0, 1, 4326)
            tags[42113] = "-9999"
            stream = io.BytesIO()
            Image.fromarray(values).save(stream, format="TIFF", tiffinfo=tags)
            payload = stream.getvalue()
        assert len(payload) < max_bytes
        return payload, {"url": url, "byte_size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "completed_at": "2026-09-05T12:01:00+00:00",
            "request_headers": {}, "response_headers": {"content-length": str(len(payload))}}

    def close(self):
        pass


@pytest.fixture
def key():
    return GEPSRequestKey(RUN, VALID)


@pytest.fixture
def entry(tmp_path, key):
    return GEPSSelectedLoader(tmp_path, FixtureClient())(key)


def test_exact_advertised_does_not_snap_or_truncate():
    extent = parse_time_extent("2026-09-01T00:00:00Z/2026-10-01T00:00:00Z/PT1M")
    assert exact_advertised(extent, VALID)
    assert not exact_advertised(extent, VALID + timedelta(seconds=1))
    assert not exact_advertised(None, VALID)


@pytest.mark.parametrize("change", [
    {"reference_time": RUN.replace(tzinfo=None)},
    {"valid_time": VALID + timedelta(minutes=1)},
    {"valid_time": RUN - timedelta(seconds=1)},
    {"coverages": GEPS_COVERAGES[:1]},
    {"bounds": (("west", -180.),)},
])
def test_request_rejects_unverified_shapes_before_io(key, tmp_path, change):
    client = FixtureClient()
    with pytest.raises(ValueError):
        GEPSSelectedLoader(tmp_path, client)(replace(key, **change))
    assert client.requests == []


def test_all_five_provider_reductions_exact_times_and_masks(tmp_path, key):
    import xarray as xr
    import zarr
    client = FixtureClient()
    entry = GEPSSelectedLoader(tmp_path, client)(key)
    assert len(client.requests) == 10
    assert all(ceiling == GEPS_CAPABILITY_BYTES for _, ceiling in client.requests[:5])
    p = entry.provenance
    assert p["quality"]["status"] == "unknown"
    assert p["run_identity_status"] == "requested_unverified"
    assert p["member_count"] is None and p["computed_here"] is False
    assert p["field_accounting"]["other_advertised_coverages_deferred"] == 527
    assert list(tmp_path.iterdir()) == []
    path = tmp_path / "readback.zip"
    path.write_bytes(entry.payload)
    with zarr.storage.ZipStore(str(path), mode="r") as store:
        with xr.open_zarr(store, consolidated=False) as ds:
            assert "member" not in ds.dims
            assert np.isnan(ds.temperature_2m__mean.values[0, 0, 0])
            assert ds.temperature_2m__mean.attrs["provider_statistic"] == "mean"
            assert ds.temperature_2m__spread.attrs["provider_statistic"] == "standard_deviation"
            assert ds.temperature_2m__p50.attrs["quantile"] == .5
            assert ds.raw__gust_over_15ms_probability.attrs["threshold"] == "gust > 15 m s-1"


def test_unadvertised_time_stops_before_any_coverage(key, tmp_path):
    client = FixtureClient(missing=True)
    with pytest.raises(ValueError, match="not advertised"):
        GEPSSelectedLoader(tmp_path, client)(key)
    assert len(client.requests) == 1
    assert list(tmp_path.iterdir()) == []


def test_no_finite_cells_is_absent_not_favourable(key, tmp_path):
    with pytest.raises(ValueError, match="no usable finite"):
        GEPSSelectedLoader(tmp_path, FixtureClient(masked=True))(key)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("change", [
    {"computed_here": True}, {"operational": True},
    {"quality": {"status": "passed"}}, {"run_time": VALID.isoformat()},
    {"transport_receipts": []}, {"sha256": "0" * 64},
])
def test_mutated_identity_and_accounting_refused(entry, change):
    with pytest.raises(ValueError):
        replace(entry, provenance={**entry.provenance, **change}).validate()


def test_cache_singleflight_expiry_refresh_and_failure_no_stale(key, entry):
    calls = []
    now = [0.]
    def loader(request):
        calls.append(request)
        if len(calls) > 3:
            raise RuntimeError("provider unavailable")
        return entry
    service = GEPSQueryService(loader, clock=lambda: now[0])
    with ThreadPoolExecutor(max_workers=4) as executor:
        result = list(executor.map(lambda _: service.query(key), range(4)))
    assert all(item == entry for item in result) and len(calls) == 1
    service.query(key, refresh=True)
    now[0] = 301
    service.query(key)
    now[0] = 602
    with pytest.raises(RuntimeError, match="unavailable"):
        service.query(key)


@pytest.mark.skipif(sys.platform != "linux", reason="real Linux bounded child proof")
def test_real_bounded_worker_with_anonymous_fixtures(tmp_path, key):
    from ingest.isolation import run_bounded_process
    tests = str(Path(__file__).parent)
    def runner(**kwargs):
        script = (
            "import sys; sys.path.insert(0, " + repr(tests) + "); "
            "from test_geps_query import FixtureClient; "
            "import weather_api.geps_query_worker as worker; "
            "worker.PoliteClient = FixtureClient; worker.main()"
        )
        kwargs["command"] = [sys.executable, "-c", script, "{output}"]
        return run_bounded_process(**kwargs)
    entry = GEPSBoundedLoader(tmp_path, runner=runner)(key)
    entry.validate()
    assert entry.provenance["operational"] is False
    assert list(tmp_path.iterdir()) == []


def test_provider_ogc_fault_never_becomes_numeric_artifact(key, tmp_path):
    class FaultClient(FixtureClient):
        def get_bytes_with_receipt(self, url, *, max_bytes):
            payload, receipt = super().get_bytes_with_receipt(url, max_bytes=max_bytes)
            if "GetCoverage" in url:
                payload = b'<ServiceException code="NoMatch">expired</ServiceException>'
                receipt.update(byte_size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
            return payload, receipt
    with pytest.raises(ValueError, match="NoMatch"):
        GEPSSelectedLoader(tmp_path, FaultClient())(key)
    assert list(tmp_path.iterdir()) == []


def test_forged_reduction_statistic_receipt_is_refused(entry):
    provenance = json.loads(json.dumps(entry.provenance))
    provenance["reductions"][0]["provider_statistic"] = "deterministic"
    with pytest.raises(ValueError, match="statistic identity"):
        replace(entry, provenance=provenance).validate()


def test_forged_request_geometry_receipt_is_refused(entry):
    provenance = json.loads(json.dumps(entry.provenance))
    provenance["transport_receipts"][5]["url"] = provenance["transport_receipts"][5]["url"].replace("long%2824%29", "long%281%29")
    with pytest.raises(ValueError, match="bounded geometry"):
        replace(entry, provenance=provenance).validate()


def test_cache_caller_mutation_cannot_promote_evidence(key, entry):
    service = GEPSQueryService(lambda _: entry)
    result = service.query(key)
    result.provenance["quality"]["status"] = "passed"
    entry.provenance["quality"]["status"] = "passed"
    assert service.query(key).provenance["quality"]["status"] == "unknown"


@pytest.mark.parametrize("fail", [False, True])
def test_concurrent_refresh_shares_success_and_failure(key, entry, fail, monkeypatch):
    import threading
    from concurrent.futures import Future
    import weather_api.geps_query as module
    started, finish, joined = threading.Event(), threading.Event(), threading.Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            joined.set()
            return super().result(timeout)
    monkeypatch.setattr(module, "Future", ObservedFuture)
    calls = []
    def loader(request):
        calls.append(request)
        started.set()
        assert finish.wait(3)
        if fail:
            raise RuntimeError("fixture failure")
        return entry
    service = GEPSQueryService(loader)
    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(service.query, key, refresh=True)
        assert started.wait(3)
        second = executor.submit(service.query, key, refresh=True)
        assert joined.wait(3)
        with pytest.raises(RuntimeError, match="capacity"):
            service.query(replace(key, valid_time=VALID + timedelta(hours=3)))
        finish.set()
        if fail:
            for future in (first, second):
                with pytest.raises(RuntimeError, match="fixture failure"):
                    future.result()
            with pytest.raises(RuntimeError, match="fixture failure"):
                service.query(key)
        else:
            assert first.result() == second.result()
    assert len(calls) == 1


def test_failed_refresh_preserves_original_unexpired_deadline(key, entry):
    now, calls = [0.], []
    def loader(request):
        calls.append(request)
        if len(calls) > 1:
            raise RuntimeError("refresh failed")
        return entry
    service = GEPSQueryService(loader, clock=lambda: now[0])
    service.query(key)
    now[0] = 1.
    with pytest.raises(RuntimeError, match="refresh failed"):
        service.query(key, refresh=True)
    assert service.query(key) == entry
    now[0] = 300.
    with pytest.raises(RuntimeError, match="refresh failed"):
        service.query(key)
