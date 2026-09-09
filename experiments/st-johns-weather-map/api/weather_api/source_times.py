"""Bounded native time inventory, no cloud-value acquisition.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006 (local experiment).
"""
from collections import OrderedDict
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
import threading
import time
from typing import Literal

from pydantic import AwareDatetime, Field
from .source_contract import ContractModel
from .source_grid import SOURCE, FIELD, ACQUISITIONS, selected_service

class TimeFrame(ContractModel):
    valid_time: AwareDatetime
    run_time: AwareDatetime

class TimeObject(ContractModel):
    bucket: str
    name: str
    generation: str
    etag: str
    size: int

class SourceTimesResponse(ContractModel):
    source_id: Literal['google-weathernext-3-statistics'] = SOURCE
    product: Literal['WeatherNext 3 local', 'WeatherNext 3 historical']
    field: Literal['weathernext3_total_cloud_cover_mean'] = FIELD
    start: AwareDatetime
    end: AwareDatetime
    expires_at: AwareDatetime
    frames: list[TimeFrame] = Field(max_length=720)
    objects: list[TimeObject] = Field(max_length=6)
    notices: list[str]

_lock = threading.Lock()
_cache = OrderedDict()
_pending = {}


def run_axis(service, *, acquire=None):
    config = service.config
    key = (service._scope_label, config.root_identity, FIELD)
    with _lock:
        old = _cache.get(key)
        if old and old[0] > time.monotonic():
            _cache.move_to_end(key)
            return old[1]
        future = _pending.get(key)
        owner = future is None
        if owner:
            if len(_pending) >= 2:
                raise ValueError('WN3 inventory concurrency bound')
            future = Future()
            _pending[key] = future
    try:
        if not owner:
            return future.result()
        from .weathernext_query import WeatherNextSelection
        from .weathernext_gcs import runtime_token_provider
        from .weathernext_gcs_bridge import AccountedGCSTransport, read_historical_point, read_local_experimental_point
        selection = WeatherNextSelection(config.initialization, config.initialization + timedelta(hours=1),
                                         47.5, -53, ('total_cloud_cover_mean',))
        reader = acquire or (read_historical_point if service._scope_label == 'historical' else read_local_experimental_point)
        with ACQUISITIONS:
            payload = reader(selection, root_identity=config.root_identity, now=service._utcnow(),
                transport=AccountedGCSTransport(token_provider=runtime_token_provider(config.gcloud_profile), max_received_bytes=1024**2),
                max_received_bytes=1024**2, timeout=30, inventory=True)
        reading = payload['reading']
        times = tuple(datetime.fromisoformat(t) for t in reading['native_times'])
        if (not times or len(times) > 360 or len(set(times)) != len(times)
                or any(t.tzinfo is None or not config.initialization < t <= config.initialization + timedelta(hours=360) for t in times)
                or list(times) != sorted(times)):
            raise ValueError('WN3 native axis identity')
        result = (times, reading['objects'], datetime.now(UTC) + timedelta(seconds=60))
        with _lock:
            _cache[key] = (time.monotonic() + 60, result)
            while len(_cache) > 4:
                _cache.popitem(last=False)
        future.set_result(result)
        return result
    except Exception as error:
        if owner:
            future.set_exception(error)
        raise
    finally:
        if owner:
            with _lock:
                _pending.pop(key, None)


def inventory(product, start, end, *, now=None, service_for=selected_service, axis_for=run_axis):
    now = now or datetime.now(UTC)
    if start.tzinfo is None or end.tzinfo is None or not start < end <= start + timedelta(days=15):
        raise ValueError('WN3 inventory window must be aware and at most 15 days')
    historical = product == 'WeatherNext 3 historical'
    cutoff = now - timedelta(hours=48)
    eligible_end = min(end, cutoff - timedelta(microseconds=1)) if historical else end
    frames, objects, notices, roots = {}, {}, [], set()
    expiry = now + timedelta(seconds=60)
    if start <= eligible_end:
        for anchor in dict.fromkeys((start, eligible_end)):
            try:
                service = service_for(product, anchor)
                if service.config.root_identity in roots:
                    continue
                roots.add(service.config.root_identity)
                times, identities, expires = axis_for(service)
                expiry = min(expiry, expires)
                for stamp in times:
                    if start <= stamp <= end and (not historical or stamp < cutoff):
                        previous = frames.get(stamp)
                        run = service.config.initialization
                        if previous is None or previous.run_time < run:
                            frames[stamp] = TimeFrame(valid_time=stamp, run_time=run)
                for item in identities:
                    objects[(item['name'], item['generation'])] = TimeObject(**item)
            except Exception as error:
                if getattr(error, 'http_status', None) in (401,403):
                    raise
                notices.append(f'WN3 native time inventory unavailable near {anchor.isoformat()}; archive coverage is not inferred')
    if historical:
        notices.append('Historical forecast times must be older than 48 hours; these are forecasts, not observations')
    notices.append('Native forecast time coordinates only; cloud values are fetched when a time is selected. Inventory covers at most two published main-cycle runs, not an exhaustive archive listing.')
    return SourceTimesResponse(product=product, start=start, end=end, expires_at=expiry,
        frames=[frames[t] for t in sorted(frames)], objects=list(objects.values()), notices=notices)
