from datetime import UTC, datetime
import json
import httpx
import numpy as np
import pytest

from test_adapter_sst_analysis import _ostia_metadata, _compressed, _client
from weather_api.ostia_query import OSTIAQueryService, OSTIAUnavailable
from ingest.http import PoliteClient as NativePoliteClient

DAY = datetime(2026, 9, 4, tzinfo=UTC)


def service():
    metadata = _ostia_metadata()
    m = metadata['metadata']
    seconds = int((DAY-datetime(1981, 1, 1, tzinfo=UTC)).total_seconds())
    payloads = {'/.zmetadata': json.dumps(metadata).encode()}
    values = {'time': np.array([seconds]), 'latitude': np.array([44.95,45.05,50.45,50.55]),
              'longitude': np.array([-58.05,-57.95,-46.05,-45.95]),
              'analysed_sst': np.full((4,4),1000), 'analysis_error': np.full((4,4),25), 'mask': np.ones((4,4))}
    values['mask'][1,1] = 2
    values['mask'][2,1] = 9  # Water + sea ice remains the native bitmask.
    values['analysed_sst'][2,2] = -32768
    values['analysis_error'][2,2] = -32768
    for name, arr in values.items():
        payloads[f'/{name}/'+('0' if arr.ndim == 1 else '0.0.0')] = _compressed(arr,m[f'{name}/.zarray'])
    requests = []
    def handler(request):
        key = '/' + str(request.url).split('.zarr/',1)[1]
        requests.append(key)
        return httpx.Response(200, content=payloads[key])
    clock = [0.0]
    client = _client(handler)
    real_download = client.download_with_receipt
    def fixture_download(*args, **kwargs):
        from datetime import timedelta
        receipt = real_download(*args, **kwargs)
        receipt['completed_at'] = DAY + timedelta(seconds=clock[0])
        return receipt
    client.download_with_receipt = fixture_download
    return OSTIAQueryService(client=client, clock=lambda: clock[0], utcnow=lambda: DAY), requests, clock


def test_actual_native_adapter_point_masks_identity_and_shared_cache():
    query, requests, _ = service()
    land = query.point_fields(45.05, -57.95, DAY)
    assert [f.value for f in land] == [None,None,2]
    count = len(requests)
    sea = query.point_fields(50.45,-57.95,DAY)
    assert len(requests) == count == 7
    assert [f.value for f in sea] == pytest.approx([10,.25,9],abs=.0001)
    assert sea[0].provenance.valid_time == DAY
    assert sea[0].provenance.run_time is None
    assert sea[0].provenance.original_units == 'kelvin'
    assert sea[0].provenance.normalized_units == 'degC'
    assert sea[0].provenance.operational is False
    missing = query.point_fields(50.45,-46.05,DAY)
    assert [f.value for f in missing] == [None,None,1]


def test_nonexact_analysis_does_not_fetch_native_fields():
    query, requests, _ = service()
    with pytest.raises(OSTIAUnavailable):
        query.query(DAY.replace(hour=1))
    assert requests == ['/.zmetadata','/time/0']


def test_expiry_failed_refresh_and_defensive_copy():
    query, requests, clock = service()
    data = query.query(DAY)
    data['valid_time'] = 'invalid'
    assert query.query(DAY)['valid_time'] == DAY.isoformat()
    query.client = _client(lambda request: httpx.Response(404))
    with pytest.raises(OSTIAUnavailable):
        query.query(DAY, refresh=True)
    assert query.query(DAY)['valid_time'] == DAY.isoformat()
    clock[0] = 301
    with pytest.raises(OSTIAUnavailable):
        query.query(DAY)


@pytest.mark.parametrize('lat,lon',[(44,-53),(47,float('nan')),(True,-53)])
def test_invalid_point_performs_no_io(lat,lon):
    query, requests, _ = service()
    with pytest.raises(ValueError):
        query.point_fields(lat,lon,DAY)
    assert not requests


def test_actual_linux_bounded_worker_replays_native_fixture():
    import sys
    from ingest.isolation import run_bounded_process
    from weather_api.ostia_query import LIMITS
    code = "from test_ostia_query import worker_client; import runpy; from test_ostia_query import service; import ingest.http; ingest.http.PoliteClient=lambda **kwargs: worker_client(); runpy.run_module('weather_api.ostia_query_worker', run_name='__main__')"
    result = run_bounded_process(command=[sys.executable, '-c', code, '{output}'], stdin=DAY.isoformat().encode(), destination=None, limits=LIMITS, timeout_seconds=30, require_output=False)
    data = json.loads(result.stdout)
    assert data['valid_time'] == DAY.isoformat()
    assert data['sea_surface_temperature_mask'] == [[2, 1], [9, 1]]
    assert data['sea_surface_temperature'][1][1] is None


def test_identical_misses_coalesce(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import weather_api.ostia_query as module
    query, requests, _ = service()
    entered, release = threading.Event(), threading.Event()
    original = module.acquire
    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(module, 'acquire', delayed)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(query.query, DAY)
        assert entered.wait(5)
        second = pool.submit(query.query, DAY)
        release.set()
        assert first.result() == second.result()
    assert len(requests) == 7


def test_oversized_native_chunks_refused_before_field_payload(monkeypatch):
    import weather_api.ostia_query as module
    query, requests, _ = service()
    original = module.OSTIAAdapter.discover
    def changed(self, window):
        candidates = original(self, window)
        candidates[0].detail['metadata']['metadata']['analysed_sst/.zarray']['chunks'] = [1, 100000, 100000]
        return candidates
    monkeypatch.setattr(module.OSTIAAdapter, 'discover', changed)
    with pytest.raises(OSTIAUnavailable):
        query.query(DAY)
    assert requests == ['/.zmetadata', '/time/0']


def test_validation_does_not_retimestamp_retrieval_or_renew_expiry(monkeypatch):
    from datetime import timedelta
    import ingest.captures.sst_analysis as native
    query, _, clock = service()
    query.utcnow = lambda: DAY + timedelta(seconds=clock[0])
    original = native.validate_run
    def slow_validation(*args, **kwargs):
        clock[0] = 40
        return original(*args, **kwargs)
    monkeypatch.setattr(native, 'validate_run', slow_validation)
    data = query.query(DAY)
    assert data['provenance']['retrieval_time'] == DAY.isoformat()
    assert data['completed_monotonic'] == 0
    assert query.entry[1] == 300
    field = query.point_fields(50.45, -57.95, DAY)[0]
    assert field.provenance.retrieval_time == DAY
    assert field.provenance.freshness.age_seconds == 40


def test_forced_worker_termination_cleans_native_download_scratch(monkeypatch, tmp_path):
    import sys
    from pathlib import Path
    import ingest.isolation as isolation
    from weather_api.ostia_query import LIMITS
    # Capture the real parent-owned workspace; no child cleanup is trusted.
    directories = []
    original = isolation.tempfile.mkdtemp
    def record(*args, **kwargs):
        path = original(*args, **kwargs)
        directories.append(Path(path))
        return path
    monkeypatch.setattr(isolation.tempfile, 'mkdtemp', record)
    receipt = tmp_path / 'scratch-location.txt'
    code = f"""
import runpy, time
from pathlib import Path
from test_ostia_query import service
import ingest.http
from ingest.captures.sst_analysis import OSTIAAdapter
ingest.http.PoliteClient = lambda **kwargs: service()[0].client
def stalled(self, candidate, window, workdir):
    target = workdir / 'retained.chunk'
    target.write_bytes(b'native chunk bytes')
    Path({str(receipt)!r}).write_text(str(target))
    time.sleep(60)
OSTIAAdapter.fetch = stalled
runpy.run_module('weather_api.ostia_query_worker', run_name='__main__')
"""
    with pytest.raises(isolation.BoundedProcessError):
        isolation.run_bounded_process(command=[sys.executable, '-c', code, '{output}'],
            stdin=DAY.isoformat().encode(), destination=None, limits=LIMITS,
            timeout_seconds=5, require_output=False)
    scratch = Path(receipt.read_text())
    assert len(directories) == 1
    assert scratch.is_relative_to(directories[0])
    assert not scratch.exists()
    assert not directories[0].exists()


def worker_client():
    # Worker clocks are real; its fixture transport must supply real completion.
    client = service()[0].client
    client.download_with_receipt = NativePoliteClient.download_with_receipt.__get__(client)
    return client
