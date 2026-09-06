from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event
from time import sleep

import pytest

from weather_api.gfs_query import GFSQueryEntry, GFSQueryService, GFSRequestKey

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
