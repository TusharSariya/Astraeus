"""Opt-in bounded published root discovery for internal WN3 point requests.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006 (experiment).
Only successful native root metadata establishes a run; no guessed science URL
is returned as evidence. The existing decoder checks actual hourly coordinates.
"""
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
import threading
import time
from .weathernext_native import BUCKET
from .weathernext_delivery import HistoricalConfiguration, LocalExperimentalConfiguration
from .weathernext_gcs import runtime_token_provider
from .weathernext_gcs_bridge import AccountedGCSTransport

_lock=threading.Lock()
_cache=OrderedDict()


def discover_configuration(selected, profile, *, internal, now=None, transport=None):
    now=now or datetime.now(UTC)
    if selected.tzinfo is None or now.tzinfo is None:
        raise ValueError('Aware selected and current time required')
    # Main cycles supply the complete surface inventory through 360 hours.
    anchor=min(selected-timedelta(hours=1),now).astimezone(UTC)
    anchor=anchor.replace(hour=(anchor.hour//6)*6,minute=0,second=0,microsecond=0)
    key=(anchor,profile,internal)
    with _lock:
        cached=_cache.get(key)
        if transport is None and cached and cached[0]>time.monotonic():
            _cache.move_to_end(key)
            return cached[1]
        client=transport or AccountedGCSTransport(token_provider=runtime_token_provider(profile),max_received_bytes=64*1024)
        deadline=time.monotonic()+15
        for offset in range(4):
            stamp=anchor-timedelta(hours=6*offset)
            if stamp.year<2026 or selected>stamp+timedelta(hours=360):
                continue
            name=f'weathernext_3_0_0_statistics/zarr/2026_to_present/{stamp:%Y%m%d_%H}hr_01_preds/predictions.zarr/zarr.json'
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            try:
                identity=client.describe(BUCKET,name,timeout=remaining)
                cls=LocalExperimentalConfiguration if internal else HistoricalConfiguration
                result=cls(stamp,identity,profile)
            except Exception as error:
                if getattr(error,'http_status',None) in (401,403):raise
                continue
            if transport is None:
                _cache[key]=(time.monotonic()+300,result)
                _cache.move_to_end(key)
                while len(_cache)>16:_cache.popitem(last=False)
            return result
    raise ValueError('No published WeatherNext 3 main-cycle root within bounded discovery')
