from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
import threading

import httpx
import numpy
import pytest
import xarray

from weather_api import goes_phase_query as query
from test_adapter_goes_abi_l2 import _granule

KEY = "ABI-L2-ACTPF/2026/248/20/OR_ABI-L2-ACTPF-M6_G19_s20262482010207_e20262482019515_c20262482020528.nc"
NOW = datetime(2026, 9, 5, 20, 30, tzinfo=UTC)


class Clock:
    now = NOW
    mono = 10.0
    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.mono += seconds


def service(*, decoder=lambda body, key: (b"artifact", '{}')):
    clock = Clock()
    calls = []
    state = {"fail": False, "key": KEY}
    def handle(request):
        calls.append(request)
        if state["fail"]:
            return httpx.Response(503)
        if request.url.path == "/":
            key = state["key"] if request.url.params["prefix"] == "ABI-L2-ACTPF/2026/248/20/" else ""
            return httpx.Response(200, text=f"<ListBucketResult><Contents><Key>{key}</Key></Contents></ListBucketResult>")
        return httpx.Response(200, content=b"native")
    client = httpx.Client(transport=httpx.MockTransport(handle))
    return query.GOESPhaseQueryService(client=client, clock=lambda: clock.now,
        monotonic=lambda: clock.mono, decoder=decoder), clock, calls, state


def test_cache_hit_uses_zero_requests_and_does_not_extend_expiry():
    reader, clock, calls, _ = service()
    first = reader.read_native()
    assert len(calls) == 7
    clock.advance(10)
    second = reader.read_native()
    assert second.cache_status == "hit"
    assert second.retained_until == first.retained_until
    assert second.artifact is first.artifact
    assert len(calls) == 7
    assert first.product_id == "ABI-L2-ACTPF" and not first.operational
    assert first.receipt.body_bytes == 6
    assert len(first.listing_receipts) == 6
    clock.advance(290)
    assert reader.read_native().cache_status == "miss"
    assert len(calls) == 14


def test_failed_refresh_preserves_only_unexpired_prior_revision():
    reader, clock, calls, state = service()
    first = reader.read_native()
    state["fail"] = True
    with pytest.raises(query.GOESPhaseUnavailable):
        reader.read_native(refresh=True)
    assert reader.read_native().artifact_sha256 == first.artifact_sha256
    clock.advance(300)
    with pytest.raises(query.GOESPhaseUnavailable):
        reader.read_native()


def test_explicit_refresh_reacquires_and_has_fixed_deadline():
    reader, clock, calls, _ = service()
    reader.read_native()
    clock.advance(20)
    refreshed = reader.read_native(refresh=True)
    assert refreshed.cache_status == "refresh"
    assert refreshed.retained_until == clock.now + timedelta(seconds=300)
    assert len(calls) == 14


@pytest.mark.parametrize("key", [KEY.replace("G19", "G18"), KEY.replace("ACTPF", "CCLF"),
                                    KEY.replace("s20262482010207", "s20262482110207"), "../" + KEY])
def test_wrong_product_future_and_unsafe_keys_never_download(key):
    reader, _, calls, state = service()
    state["key"] = key
    with pytest.raises(query.GOESPhaseUnavailable):
        reader.read_native()
    assert len(calls) == 6
    assert all(call.url.path == "/" for call in calls)


def test_oversized_encoded_and_redirect_responses_are_refused(monkeypatch):
    for response in (httpx.Response(200, content=b"x" * 11),
                     httpx.Response(302, headers={"location": "https://example.com"}),
                     httpx.Response(200, headers={"content-encoding": "unexpected"}, content=b"x")):
        reader = query.GOESPhaseQueryService(client=httpx.Client(transport=httpx.MockTransport(lambda request: response)))
        with pytest.raises(query.GOESPhaseUnavailable):
            reader._fetch(query.GOES_S3_BASE, 10)


def test_slow_decode_cannot_publish_expired_evidence():
    reader, clock, _, _ = service()
    def decode(body, key):
        clock.advance(300)
        return b"artifact", '{}'
    reader._decoder = decode
    with pytest.raises(query.GOESPhaseUnavailable, match="retention"):
        reader.read_native()
    assert reader._cached is None


def test_monotonic_expiry_survives_wall_clock_rollback():
    reader, clock, calls, state = service()
    reader.read_native()
    clock.mono += 300
    clock.now -= timedelta(hours=1)
    state["fail"] = True
    with pytest.raises(query.GOESPhaseUnavailable):
        reader.read_native()


def test_concurrent_misses_share_one_acquisition():
    entered, release = threading.Event(), threading.Event()
    def decode(body, key):
        entered.set()
        assert release.wait(10)
        return b"artifact", '{}'
    reader, _, calls, _ = service(decoder=decode)
    with ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(reader.read_native)
        assert entered.wait(10)
        others = [pool.submit(reader.read_native) for _ in range(3)]
        release.set()
        results = [first.result(), *(future.result() for future in others)]
    assert len(calls) == 7
    assert {result.artifact_sha256 for result in results} == {results[0].artifact_sha256}


@pytest.mark.skipif(sys.platform != "linux", reason="kernel-limited scientific decoder proof runs in Linux")
def test_actual_bounded_decoder_preserves_native_phase_quality_coordinates_and_time(tmp_path):
    raw = _granule(tmp_path / "native.nc", "ABI-L2-ACTPF")
    artifact, metadata_text = query.decode_phase(raw.read_bytes(), KEY)
    metadata = json.loads(metadata_text)
    output = tmp_path / "result.nc"
    output.write_bytes(artifact)
    with xarray.open_dataset(output) as dataset:
        assert dataset.cloud_top_phase.attrs["units"] == "code"
        assert dataset.latitude.ndim == 2  # native curvilinear coordinates
        assert dataset.longitude.shape == dataset.latitude.shape
        bad = dataset.quality_flag.values == 1
        assert bad.any()
        assert numpy.isnan(dataset.cloud_top_phase.values[bad]).all()
        assert set(numpy.unique(dataset.cloud_top_phase.values[numpy.isfinite(dataset.cloud_top_phase)])) == {2.0}
        assert str(dataset.valid_time.values[0]).startswith("2026-09-05T20:10:20.700")
    assert metadata["source_dataset_name"] == KEY.rsplit("/", 1)[-1]
    assert metadata["source_attrs"]["time_coverage_end"] == "2026-09-05T20:19:51.5Z"


@pytest.mark.skipif(sys.platform != "linux", reason="kernel-limited scientific decoder proof runs in Linux")
def test_actual_bounded_decoder_refuses_wrong_identity_and_units(tmp_path):
    native = _granule(tmp_path / "native.nc", "ABI-L2-ACTPF")
    with pytest.raises(Exception):
        query.decode_phase(native.read_bytes(), KEY.replace("e20262482019515", "e20262482019516"))
    wrong = _granule(tmp_path / "wrong.nc", "ABI-L2-ACTPF", bad_units=True)
    with pytest.raises(Exception):
        query.decode_phase(wrong.read_bytes(), KEY)


@pytest.mark.skipif(sys.platform != "linux", reason="kernel-limited scientific decoder proof runs in Linux")
def test_all_bad_native_quality_cannot_publish_a_complete_revision(tmp_path):
    native = _granule(tmp_path / "bad-quality.nc", "ABI-L2-ACTPF")
    with xarray.open_dataset(native) as opened:
        changed = opened.load()
    changed["DQF"].values[:] = 1
    changed.to_netcdf(native, mode="w")
    with pytest.raises(Exception):
        query.decode_phase(native.read_bytes(), KEY)
