"""Finite request-time Activity API. No archive, scheduler or general snapshot store."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field, field_validator

from ingest.derive.registry import ACTIVITY_VERDICT, resolve
from registry.profile_audit import ProfileError, audit_profile, load_profiles
from .config import in_window
from .desktop_series import fail
from .models import StrictModel
from .profiles.acquisition import ActivityReader, tier
from .profiles.evaluator import PROFILE_ORDER, evaluate, validate_overrides

TTL_SECONDS = 300
MAX_ENTRIES = 16
MAX_CACHE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
READ_SECONDS = 45
MAX_STRIP_CELLS = 3  # at most 12 weather source/time reads per strip page


class Focus(StrictModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    valid_time: datetime
    site_id: str | None = Field(default=None, max_length=100)

    @field_validator('valid_time')
    @classmethod
    def utc(cls, value):
        if value.tzinfo is None:
            raise ValueError('time must include a UTC offset')
        return value.astimezone(UTC)


def profiles():
    available, unavailable = {}, {}
    for pid, profile in load_profiles().items():
        if pid not in PROFILE_ORDER:
            continue
        if isinstance(profile, ProfileError):
            unavailable[pid] = str(profile)
        elif errors := audit_profile(profile):
            unavailable[pid] = '; '.join(errors)
        elif profile.version < 2:
            unavailable[pid] = 'Profile delivery metadata unavailable'
        else:
            available[pid] = profile.data
    return available, unavailable


class ActivityService:
    def __init__(self, reader=None, *, clock=time.monotonic, utcnow=lambda: datetime.now(UTC), read_seconds=READ_SECONDS, loader=profiles):
        self.reader = reader or ActivityReader()
        self.clock, self.utcnow, self.read_seconds, self.loader = clock, utcnow, read_seconds, loader
        self.lock = threading.Lock()
        self.entries = {}
        self.inflight = {}
        self.slots = threading.BoundedSemaphore(2)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='activity')

    def _expire(self):
        for key, (expires, _, _) in list(self.entries.items()):
            if self.clock() >= expires:
                del self.entries[key]

    def _bounded(self, work):
        if not self.slots.acquire(blocking=False):
            fail('activity_capacity_unavailable', 'Two Activity acquisitions are already in flight', status=503)
        stopped = threading.Event()
        deadline = self.clock() + self.read_seconds
        def run():
            try:
                return work(lambda: stopped.is_set() or self.clock() >= deadline)
            finally:
                self.slots.release()
        future = self.executor.submit(run)
        try:
            return future.result(timeout=self.read_seconds)
        except TimeoutError:
            stopped.set()
            fail('activity_unavailable', 'Activity acquisition deadline exceeded', status=503)

    def _validate(self, focus, reference):
        from .fixtures import AVALON_CORE_BOUNDS as b
        if not (b['south'] <= focus.latitude <= b['north'] and b['west'] <= focus.longitude <= b['east']):
            fail('outside_supported_area', 'Coordinate is outside the Avalon core coverage')
        if not in_window(focus.valid_time, reference):
            fail('outside_window', 'Activity instant is outside the existing evidence window')
        if focus.site_id:
            from .sites import load_site_registry
            site = next((site for site in load_site_registry().sites if site.id == focus.site_id), None)
            if site is None or (site.latitude, site.longitude) != (focus.latitude, focus.longitude):
                fail('invalid_site', 'Site id must match the exact registered coordinate')

    def read(self, focus: Focus, overrides=None, *, refresh=False, end=None, disabled_method=None):
        reference = self.utcnow()
        self._validate(focus, reference)
        if end is not None and (end.tzinfo is None or not timedelta(0) < end-focus.valid_time <= timedelta(hours=24) or not in_window(end, reference)):
            fail('invalid_selection', 'Strip window must be offset-aware, positive, at most 24 hours and inside the evidence window')
        available, unavailable = self.loader()
        try:
            validate_overrides(available, overrides or {})
        except ValueError as error:
            fail('invalid_override', str(error))
        refusal = resolve(ACTIVITY_VERDICT, reader_disabled=[disabled_method] if disabled_method else [])
        if refusal:
            return {'focus': focus.model_dump(mode='json'), 'refusal': refusal.as_dict(), 'verdicts': []}
        # Full profile content covers versions, admission paths and geometry rules.
        # Each stored body also names the hash of its actual input identities.
        from .store import configured_mode
        key = hashlib.sha256(json.dumps([focus.model_dump(mode='json'), available, unavailable, overrides or {},
            tier(focus.valid_time, reference), end.isoformat() if end else None, configured_mode(), str(resolve('de442_sun_moon_geometry')), 'activity_verdict:1'], sort_keys=True).encode()).hexdigest()
        with self.lock:
            self._expire()
            pending = self.inflight.get(key)
            if not pending and not refresh and key in self.entries:
                result = json.loads(self.entries[key][2])
                result['cache']['state'] = 'hit'
                return result
            owner = pending is None
            if owner:
                self.entries.pop(key, None)  # failed explicit replacement cannot retain an old score
                if len(self.entries) + len(self.inflight) >= MAX_ENTRIES:
                    fail('activity_capacity_unavailable', 'Finite Activity cache is full', status=503)
                pending = Future()
                self.inflight[key] = pending
        if not owner:
            try:
                return json.loads(pending.result(timeout=self.read_seconds+1))
            except TimeoutError:
                fail('activity_unavailable', 'Concurrent Activity acquisition deadline exceeded', status=503)
        started = self.clock()
        def compute(stop):
            def instant(selected):
                acquired = self.reader(selected, available, reference, stop)
                readings, windows, notices = acquired[:3]
                resolutions = acquired[3] if len(acquired) == 4 else {}
                values = []
                for pid in PROFILE_ORDER:
                    if pid not in available:
                        values.append({'profile_id': pid, 'unavailable': unavailable.get(pid, 'Profile file missing')})
                    else:
                        values.append(evaluate(available[pid], at=selected.valid_time, tier=tier(selected.valid_time, reference),
                            readings=readings, window=windows[pid], overrides=overrides or {}, site_id=selected.site_id, resolutions=resolutions))
                return {'focus': selected.model_dump(mode='json'), 'verdicts': values, 'notices': notices}, readings
            if end is None:
                result, readings = instant(focus)
                result['resolution_seconds'] = None  # exact instant, never represented as a full native cell
            else:
                stamps, source_steps, notices = self.reader.native_times(focus, end, reference, stop)
                resolution = 3600 if source_steps else None
                stamps = sorted(set(stamp for stamp in stamps if focus.valid_time <= stamp < end))
                chosen = stamps[:MAX_STRIP_CELLS]
                cells, readings = [], []
                for stamp in chosen:
                    if stop():
                        raise TimeoutError('Activity strip deadline exceeded')
                    cell, inputs = instant(focus.model_copy(update={'valid_time': stamp}))
                    # Inventory is a declaration. A cell exists only when a driving
                    # native weather/index input was actually returned at its time.
                    issued = any(row.provenance.source_id != 'nasa-jpl-de442' and row.provenance.valid_time == stamp for row in inputs)
                    if issued:
                        for value in cell['verdicts']:
                            profile = available.get(value['profile_id'])
                            if profile is None:
                                value['issued'] = False
                                continue
                            relevant = [row['input']['evidence'] for row in [*value['criteria'], *value['hard_stops']]
                                if row['input']['evidence'] is not None and row['input']['evidence']['provenance']['source_id'] != 'nasa-jpl-de442']
                            step = value['resolution_seconds']
                            value['issued'] = bool(relevant) and step is not None and stamp.timestamp() % step == 0
                        cells.append(cell)
                    readings.extend(inputs)
                result = {'focus': focus.model_dump(mode='json'), 'end': end.isoformat(), 'cells': cells,
                    'resolution_seconds': resolution, 'notices': notices,
                    'queried_times': [stamp.isoformat() for stamp in chosen],
                    'next_start': stamps[MAX_STRIP_CELLS].isoformat() if len(stamps) > MAX_STRIP_CELLS else None,
                    'complete': len(stamps) <= MAX_STRIP_CELLS,
                    'absence': 'Missing issued times remain gaps; spans beyond next_start have not been acquired'}
            identities = sorted({(row.provenance.source_id, row.key, str(row.provenance.run_time), str(row.provenance.valid_time), row.provenance.artifact_revision) for row in readings}, key=str)
            result['input_identity'] = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
            return result
        try:
            result = self._bounded(compute)
            completed = self.utcnow()
            result['cache'] = {'state': 'miss', 'computed_at': completed.isoformat(), 'expires_at': (completed+timedelta(seconds=TTL_SECONDS)).isoformat(),
                'computation_seconds': max(0, self.clock()-started), 'ttl_seconds': TTL_SECONDS,
                'key': f'{key}:{result["input_identity"]}', 'provider_revalidation': 'Existing finite source caches; cache hit does not revalidate providers'}
            result['operational'] = False
            encoded = json.dumps(result, allow_nan=False)
            size = len(encoded.encode())
            if size > MAX_RESPONSE_BYTES:
                fail('query_limit_exceeded', 'Activity response exceeds 512 KiB; shorten the strip window')
            with self.lock:
                self._expire()
                if sum(entry[1] for entry in self.entries.values()) + size > MAX_CACHE_BYTES:
                    fail('activity_capacity_unavailable', 'Activity cache byte budget is full', status=503)
                self.entries[key] = (self.clock()+TTL_SECONDS, size, encoded)
            pending.set_result(encoded)
            return json.loads(encoded)
        except Exception as error:
            if not isinstance(error, HTTPException):
                error = HTTPException(status_code=503, detail={'code': 'activity_unavailable', 'message': 'Selected-time Activity acquisition unavailable', 'retryable': True, 'restart_required': False, 'details': {}})
            pending.set_exception(error)
            raise error
        finally:
            with self.lock:
                self.inflight.pop(key, None)


@lru_cache(maxsize=1)
def activity_service():
    return ActivityService()


router = APIRouter()


def _request(latitude, longitude, valid_time, site_id, override, refresh, end=None, disabled_method=None):
    try:
        values = {}
        for item in override or []:
            name, value = item.split(':')
            if name in values:
                raise ValueError('Duplicate override')
            values[name] = float(value)
        focus = Focus(latitude=latitude, longitude=longitude, valid_time=valid_time, site_id=site_id)
    except ValueError:
        fail('invalid_selection', 'Invalid Focus or threshold override')
    return activity_service().read(focus, values, refresh=refresh, end=end, disabled_method=disabled_method)


@router.get('/verdicts')
def verdicts(latitude: float, longitude: float, valid_time: datetime, site_id: str | None = None,
             override: list[str] | None = Query(default=None, max_length=100), refresh: bool = False, disabled_method: Literal["activity_verdict"] | None = None):
    return _request(latitude, longitude, valid_time, site_id, override, refresh, disabled_method=disabled_method)


@router.get('/verdicts/series')
def verdict_series(latitude: float, longitude: float, valid_time: datetime, end: datetime,
                   site_id: str | None = None, override: list[str] | None = Query(default=None, max_length=100), refresh: bool = False, disabled_method: Literal["activity_verdict"] | None = None):
    return _request(latitude, longitude, valid_time, site_id, override, refresh, end, disabled_method=disabled_method)
