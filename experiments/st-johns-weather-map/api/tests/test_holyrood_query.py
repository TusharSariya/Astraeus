from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import httpx
import pytest
from weather_api.holyrood_query import HolyroodQueryService, HolyroodUnavailable, decode_image
from ingest.experimental.holyrood_radar import BASE_URL, MAX_IMAGE_BYTES, _gif_metadata
from test_experimental_holyrood_radar import GIF, NOW, RAIN, SNOW, listing


def service(*, decoder=_gif_metadata):
    requests, clock = [], [NOW]
    responses = {BASE_URL + "/": listing(RAIN, SNOW), BASE_URL + "/" + RAIN: GIF, BASE_URL + "/" + SNOW: GIF}
    def handler(request):
        requests.append(str(request.url))
        result = responses[str(request.url)]
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, content=result, headers={"etag": "fixed", "set-cookie": "excluded"})
    query = HolyroodQueryService(client=httpx.Client(transport=httpx.MockTransport(handler)), clock=lambda: clock[0], decoder=decoder)
    return query, requests, clock, responses


def test_finite_image_revision_cache_refresh_expiry_and_failed_replacement():
    query, requests, clock, responses = service()
    first = query.read_images()
    assert len(requests) == 3
    assert [image.body for image in first.images] == [GIF, GIF]
    assert first.operational is False and first.semantics == "rendered-image-only"
    assert first.source_quality == "unknown"
    assert all(name != "set-cookie" for name, value in first.images[0].receipt.headers)
    assert query.read_images().cache_status == "hit"
    assert len(requests) == 3
    assert query.read_images(refresh=True).cache_status == "refresh"
    assert len(requests) == 6
    clock[0] += timedelta(seconds=60)
    responses[BASE_URL + "/" + SNOW] = b"broken"
    with pytest.raises(HolyroodUnavailable):
        query.read_images()
    assert query._cached is None
    responses[BASE_URL + "/" + SNOW] = GIF
    assert query.read_images().cache_status == "miss"
    assert len(requests) == 12


def test_concurrent_misses_request_one_pair():
    query, requests, _, _ = service()
    barrier = threading.Barrier(8)
    def read(_):
        barrier.wait()
        return query.read_images()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(read, range(8)))
    assert len(requests) == 3
    assert sum(result.cache_status == "miss" for result in results) == 1


@pytest.mark.parametrize("payload", [b"invalid", GIF + b"x" * MAX_IMAGE_BYTES, httpx.Response(302, headers={"location": "https://other.invalid/"}), httpx.Response(503)])
def test_safe_failures_publish_no_pair(payload):
    query, requests, _, responses = service()
    responses[BASE_URL + "/" + RAIN] = payload
    with pytest.raises(HolyroodUnavailable):
        query.read_images()
    assert len(requests) == 2 and query._cached is None


def test_contingency_future_and_incomplete_pairs_are_not_native_evidence():
    query, requests, _, responses = service()
    responses[BASE_URL + "/"] = listing(RAIN, SNOW.replace(".gif", "-Contingency.gif"), RAIN.replace("20260906", "20270906"), SNOW.replace("20260906", "20270906"))
    with pytest.raises(HolyroodUnavailable, match="no native paired"):
        query.read_images()
    assert len(requests) == 1


def test_default_bounded_worker_preserves_fixture_bytes_and_cache():
    query, requests, _, _ = service(decoder=decode_image)
    result = query.read_images()
    assert all(image.width == 1 and image.height == 1 and image.body == GIF for image in result.images)
    assert query.read_images().cache_status == "hit"
    assert len(requests) == 3


def test_slow_acquisition_cannot_extend_listing_retention():
    clock = [NOW]
    def slow_decoder(body):
        clock[0] += timedelta(seconds=31)
        return _gif_metadata(body)
    query, requests, _, _ = service(decoder=slow_decoder)
    query._clock = lambda: clock[0]
    with pytest.raises(HolyroodUnavailable, match="retention window"):
        query.read_images()
    assert len(requests) == 3 and query._cached is None


def test_explicit_refresh_failure_preserves_still_valid_image():
    query, requests, _, responses = service()
    query.read_images()
    responses[BASE_URL + "/"] = httpx.Response(503)
    with pytest.raises(HolyroodUnavailable):
        query.read_images(refresh=True)
    assert query.read_images().cache_status == "hit" and len(requests) == 4


def test_monotonic_deadline_withholds_image_after_wall_clock_rollback():
    query, requests, clock, responses = service()
    ticks = [100.0]
    query._monotonic = lambda: ticks[0]
    first = query.read_images()
    clock[0] -= timedelta(seconds=120)
    ticks[0] += 60
    responses[BASE_URL + "/"] = httpx.Response(503)
    with pytest.raises(HolyroodUnavailable):
        query.read_images()
    assert first.retained_until == NOW + timedelta(seconds=60)
    assert query._cached is None and len(requests) == 4


@pytest.mark.parametrize("refresh", [False, True])
def test_concurrent_failure_is_shared_without_serial_retries(monkeypatch, refresh):
    from concurrent.futures import Future
    import weather_api.holyrood_query as module
    arrived = threading.Event()
    class ObservedFuture(Future):
        waiters = 0
        guard = threading.Lock()
        def result(self, timeout=None):
            with self.guard:
                self.waiters += 1
                if self.waiters == 7:
                    arrived.set()
            return super().result(timeout)
    query, requests, _, responses = service()
    if refresh:
        query.read_images()
    initial = len(requests)
    original = query._fetch
    def blocked_fetch(url, cap):
        assert arrived.wait(5), "all followers must join the same flight"
        return original(url, cap)
    query._fetch = blocked_fetch
    responses[BASE_URL + "/"] = httpx.Response(503)
    monkeypatch.setattr(module, "Future", ObservedFuture)
    def read(_):
        try:
            query.read_images(refresh=refresh)
        except HolyroodUnavailable as error:
            return error
        raise AssertionError("failed refresh must not report success")
    with ThreadPoolExecutor(max_workers=8) as pool:
        errors = list(pool.map(read, range(8)))
    assert len(requests) == initial + 1
    assert all(error is errors[0] for error in errors)
    if refresh:
        assert query.read_images().cache_status == "hit"


@pytest.mark.parametrize("padding_bytes,available", [(128 * 1024, True), (512 * 1024 + 1, False)])
def test_daily_listing_capacity_is_finite_and_exceeds_old_ceiling(padding_bytes, available):
    from ingest.experimental.holyrood_radar import MAX_LISTING_BYTES
    assert MAX_LISTING_BYTES == 512 * 1024
    query, requests, _, responses = service()
    responses[BASE_URL + "/"] = b" " * padding_bytes + listing(RAIN, SNOW)
    if available:
        assert query.read_images().images[0].body == GIF
        assert len(requests) == 3
    else:
        with pytest.raises(HolyroodUnavailable, match="byte ceiling"):
            query.read_images()
        assert len(requests) == 1 and query._cached is None
