"""Progressive native forecast comparison, isolated experimental endpoint.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Owning contract: desktop-evidence-api-contract/specs/desktop-evidence-api/comparison.md.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
import secrets
import threading
import time
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, Field, model_validator
from .desktop_series import Continuation, fail
from .models import EvidenceField, StrictModel
from .source_delivery import NativeFrame
from .source_contract import SourceVariant
from .series_budget import reserve, release

TTL = 900
PAGE_POSITIONS = 12
MAX_POSITIONS = 144
PAGE_BYTES = 512 * 1024
DEADLINE = 45
Group = str
DEFAULT_SOURCES = ['eccc-hrdps', 'eccc-rdps', 'google-weathernext-3-statistics', 'noaa-gfs', 'ecmwf-ifs']
FIELDS = {
    'temperature': ('temperature_2m',), 'humidity': ('relative_humidity_2m',),
    'cloud': ('total_cloud_opacity', 'total_cloud_geometric'),
    'wind': ('wind_speed_10m', 'wind_gust_10m'), 'precipitation': ('precipitation_accumulation',),
    'dew_point': ('dew_point_2m',), 'pressure': ('mean_sea_level_pressure',),
    'wind_direction': ('wind_direction_10m',),
}
WN_BASES = {'temperature': 'temperature_2m', 'cloud': 'total_cloud_cover',
    'wind': 'wind_speed_10m', 'precipitation': 'total_precipitation_1hr',
    'dew_point': 'dewpoint_temperature_2m', 'pressure': 'mean_sea_level_pressure'}


class ComparisonSource(StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    product_id: str | None = Field(default=None, max_length=100)
    run: str = Field(default='latest', min_length=1, max_length=100)
    level: int | None = None
    variant: SourceVariant | None = None


class ComparisonSelection(StrictModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    start: AwareDatetime
    end: AwareDatetime
    sources: list[ComparisonSource] = Field(default_factory=lambda: [ComparisonSource(source_id=s) for s in DEFAULT_SOURCES], min_length=1, max_length=6)
    variables: list[Group] = Field(default_factory=lambda: ['temperature', 'humidity', 'cloud', 'wind', 'precipitation'], min_length=1, max_length=8)
    ensemble_spread: bool = False

    @model_validator(mode='after')
    def bounds(self):
        self.start, self.end = self.start.astimezone(UTC), self.end.astimezone(UTC)
        if not timedelta(0) < self.end-self.start <= timedelta(hours=24):
            raise ValueError('Window must be positive and at most 24 hours')
        if len({s.model_dump_json() for s in self.sources}) != len(self.sources) or len(set(self.variables)) != len(self.variables):
            raise ValueError('Sources and variable groups must be unique')
        from .ifs_delivery import NATIVE_KEYS
        if any(v not in FIELDS and v not in NATIVE_KEYS for v in self.variables):raise ValueError('Unsupported variable')
        return self


class ComparisonSample(StrictModel):
    time: AwareDatetime
    run_id: str
    evidence: EvidenceField | None = None
    lower: EvidenceField | None = None
    upper: EvidenceField | None = None
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None
    reason: str | None = None
    member_values: dict[str, float | None] = Field(default_factory=dict,max_length=51)
    member_units: str | None = None


class ComparisonCurve(StrictModel):
    id: str
    source_id: str
    product_id: str
    group: Group
    field: str
    units: str | None = None
    definition: str
    samples: list[ComparisonSample] = Field(default_factory=list)
    reason: str | None = None


class ComparisonCoverage(StrictModel):
    source_id: str
    failure_kind: str | None = None
    state: Literal['available', 'empty', 'unknown', 'unsupported', 'credentials_required']
    reason: str | None = None
    available_start: AwareDatetime | None = None
    available_end: AwareDatetime | None = None
    native_times: list[AwareDatetime] = Field(default_factory=list, max_length=144)


class ComparisonPage(StrictModel):
    id: str
    selection: ComparisonSelection
    selected_at: AwareDatetime
    expires_at: AwareDatetime
    curves: list[ComparisonCurve]
    coverage: list[ComparisonCoverage]
    next_cursor: str | None
    complete: bool
    completed_positions: int
    total_positions: int


@dataclass
class Position:
    reader: object
    source: ComparisonSource
    frame: NativeFrame
    curves: list[ComparisonCurve]


@dataclass
class Entry:
    id: str
    selection: ComparisonSelection
    selected_at: datetime
    expires_at: datetime
    expires: float
    positions: list[Position] = field(default_factory=list)
    curves: list[ComparisonCurve] = field(default_factory=list)
    coverage: list[ComparisonCoverage] = field(default_factory=list)
    pages: dict[int, ComparisonPage] = field(default_factory=dict)
    tokens: dict[int, str] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cancelled: threading.Event = field(default_factory=threading.Event)
    size: int = 0
    ends: dict[int, int] = field(default_factory=dict)
    ifs_budget: object = None
    ifs_pending: dict = field(default_factory=dict)


def source_failure(error):
    status = getattr(error, 'http_status', None) or getattr(getattr(error, 'response', None), 'status_code', None)
    return ('credentials_required', 'Credentials required; check the existing source account') if status in (401,403) else ('unknown', 'Native inventory or acquisition could not be read')


def curves_for(source, reader, selection):
    descriptors = reader.descriptors()
    supported = {d.field for d in descriptors if source.product_id in (None, d.product_id)}
    curves = []
    for group in selection.variables:
        if source.source_id == 'google-weathernext-3-statistics':
            from registry.weathernext import surface_key
            keys = (surface_key(WN_BASES[group], 'mean'),) if group in WN_BASES else FIELDS.get(group,(group,))
        else:
            keys = FIELDS.get(group,(group,))
        delivered = [key for key in keys if key in supported]
        for key in (keys if group == 'wind' else delivered or keys[:1]):
            definition = 'opacity-weighted cover' if key == 'total_cloud_opacity' else 'geometric cover' if group == 'cloud' else 'gust' if 'gust' in key else group
            curves.append(ComparisonCurve(id=f'{source.source_id}:{source.product_id or reader.product_id}:{source.run}:{source.level}:{source.variant}:{key}', source_id=source.source_id,
                product_id=reader.product_id, group=group, field=key, definition=definition,
                reason=None if key in supported else 'This source does not deliver this quantity'))
    return curves


class ComparisonService:
    def __init__(self, readers=None, *, utcnow=lambda: datetime.now(UTC), clock=time.monotonic, deadline=DEADLINE):
        self.readers, self.utcnow, self.clock, self.deadline = readers, utcnow, clock, deadline
        self.lock = threading.Lock()
        self.entries = {}
        self.tokens = {}
        self.pending = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='forecast-comparison')
        self.slots = threading.BoundedSemaphore(2)

    def _check(self, entry, stop):
        if entry.cancelled.is_set() or stop():
            fail('comparison_cancelled', 'Comparison was cancelled', status=409)
        if self.clock() >= entry.expires:
            fail('snapshot_expired', 'Comparison expired; Refresh to start again', status=410, restart=True)

    def _bounded(self, work, deadline, stop):
        remaining = deadline-self.clock()
        if remaining <= 0 or stop():
            raise TimeoutError()
        if not self.slots.acquire(timeout=remaining):
            raise TimeoutError()
        def run():
            try:
                if stop() or self.clock() >= deadline:
                    raise TimeoutError()
                return work()
            finally:
                self.slots.release()
        return self.executor.submit(run)

    def initial(self, selection, stop=lambda: False):
        key = selection.model_dump_json()
        with self.lock:
            pending = self.pending.get(key)
            owner = pending is None
            if owner:
                pending = (Future(), [stop])
                self.pending[key] = pending
            else:
                pending[1].append(stop)
        future, subscribers = pending
        if not owner:
            try:
                return future.result(timeout=self.deadline + 1).model_copy(deep=True)
            except Exception as error:
                # A StrictMode replacement may arrive just after the abandoned
                # owner's read stopped. An active subscriber can start afresh.
                if getattr(error, 'detail', {}).get('code') == 'comparison_cancelled' and not stop():
                    with self.lock:
                        if self.pending.get(key) is pending: self.pending.pop(key)
                    return self.initial(selection, stop)
                raise
        def abandoned():
            with self.lock: callbacks = list(subscribers)
            return all(callback() for callback in callbacks)
        try:
            page = self._initial(selection, abandoned)
            future.set_result(page)
            return page.model_copy(deep=True)
        except Exception as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                if self.pending.get(key) is pending: self.pending.pop(key)

    def _initial(self, selection, stop):
        now = self.utcnow()
        entry = Entry(secrets.token_urlsafe(18), selection, now, now+timedelta(seconds=TTL), self.clock()+TTL)
        deadline = self.clock()+self.deadline
        from .ifs_budget import SelectionBudget
        entry.ifs_budget = SelectionBudget(clock=self.clock)
        with self.lock:
            for key, old in list(self.entries.items()):
                if self.clock() >= old.expires:
                    self.entries.pop(key)
                    for token in old.tokens.values(): self.tokens.pop(token, None)
                    release(key)
            if len(self.entries) >= 16:
                fail('snapshot_capacity_unavailable', 'Finite comparison capacity is full', status=503)
            self.entries[entry.id] = entry
        try:
            from .source_delivery import source_readers
            from .store import configured_mode, LIVE_MODE
            readers = self.readers if self.readers is not None else source_readers() if configured_mode() == LIVE_MODE else {}
            for source in selection.sources:
                self._check(entry, stop)
                reader = readers.get(source.source_id)
                if reader is None:
                    entry.coverage.append(ComparisonCoverage(source_id=source.source_id, state='unsupported', reason='Native comparison is unavailable for this source in this mode'))
                    continue
                if callable(getattr(reader,"for_selection",None)):reader=reader.for_selection(source)
                curves = curves_for(source, reader, selection)
                entry.curves.extend(curves)
                try:
                    # Discovery is bounded and retains the actual advertised identity.
                    plan_future = self._bounded(lambda r=reader, s=source: r.plan_series(selection.start, selection.end, run=s.run, **({"budget":entry.ifs_budget} if s.source_id=="ecmwf-ifs" and r.__class__.__module__=="weather_api.ifs_delivery" else {})), deadline, stop)
                    plan = plan_future.result(timeout=max(.001, deadline-self.clock()))
                    if plan is None:
                        entry.coverage.append(ComparisonCoverage(source_id=source.source_id, state='unsupported', reason='This source has no native Series delivery'))
                        continue
                    if len(plan.frames) > MAX_POSITIONS:
                        fail('query_limit_exceeded', 'Native selection exceeds 144 positions')
                    frames = sorted({(f.run_id, f.valid_time): f for f in plan.frames if selection.start <= f.valid_time < selection.end}.values(), key=lambda f: f.valid_time)
                    available = getattr(plan, 'available_times', ())
                    entry.coverage.append(ComparisonCoverage(source_id=source.source_id, state='available' if frames else 'empty',
                        native_times=[f.valid_time for f in frames],
                        available_start=min(available) if available else None,
                        available_end=max(available)+timedelta(milliseconds=1) if available else None,
                        reason=plan.reason))
                    entry.positions.extend(Position(reader, source, frame, curves) for frame in frames if any(c.reason is None for c in curves))
                except Exception as error:
                    if getattr(error, 'status_code', None) == 422: raise
                    state, reason = source_failure(error)
                    entry.coverage.append(ComparisonCoverage(source_id=source.source_id, state=state, reason=reason, failure_kind=type(error).__name__))
            if len(entry.positions) > MAX_POSITIONS:
                fail('query_limit_exceeded', 'Comparison exceeds 144 source/run/time positions')
            # Rotate small source batches so one slow model cannot keep every
            # other model's first curve behind its entire 24-hour sequence.
            by_source = {s.model_dump_json(): [p for p in entry.positions if p.source == s]
                         for s in selection.sources}
            entry.positions = []
            while any(by_source.values()):
                for positions in by_source.values():
                    entry.positions.extend(positions[:2])
                    del positions[:2]
            offset = 0
            while offset < len(entry.positions):
                source = entry.positions[offset].source.source_id
                # Published quantiles carry full per-field provenance. Smaller
                # WeatherNext pages preserve the same 512 KiB wire ceiling.
                limit = (1 if selection.ensemble_spread else 2) if source == 'google-weathernext-3-statistics' else PAGE_POSITIONS
                end = offset
                while end < min(offset+limit, len(entry.positions)) and entry.positions[end].source.source_id == source:
                    end += 1
                entry.ends[offset] = end
                if offset:
                    token = secrets.token_urlsafe(32)
                    entry.tokens[offset] = token
                    with self.lock: self.tokens[token] = (entry.id, offset)
                offset = end
            entry.size = len(selection.model_dump_json().encode()) + sum(len(c.model_dump_json().encode()) for c in entry.curves) + sum(len(c.model_dump_json().encode()) for c in entry.coverage) + len(entry.positions)*1024
            if not reserve(entry.id, entry.size, time.monotonic()+TTL):
                fail('snapshot_capacity_unavailable', 'Shared Series cache byte budget is full', status=503)
            return self._page(entry, 0, stop, deadline=deadline)
        except Exception:
            self.cancel(entry.id)
            raise

    def _read_position(self, position, selection, ifs_budget=None):
        reader, frame = position.reader, position.frame
        fields = tuple(c.field for c in position.curves if c.reason is None)
        batch = getattr(reader, 'read_comparison', None)
        if batch:
            return batch(selection.latitude, selection.longitude, frame, fields, spread=selection.ensemble_spread,
                **({"budget":ifs_budget} if position.source.source_id=="ecmwf-ifs" else {}))
        return reader.read_point(selection.latitude, selection.longitude, frame.valid_time, run=frame.run_id)

    def _page(self, entry, offset, stop, *, deadline=None):
        deadline = deadline or self.clock()+self.deadline
        # Same cursor coalesces under one lock; all readers reuse immutable pages.
        if not entry.lock.acquire(timeout=max(.001, deadline-self.clock())):
            fail('snapshot_unreadable', 'Comparison page is busy', status=503)
        try:
            self._check(entry, stop)
            if offset in entry.pages:
                return entry.pages[offset].model_copy(deep=True)
            if offset and not any(p.completed_positions == offset for p in entry.pages.values()):
                fail('invalid_cursor', 'Previous page has not completed')
            curves = {c.id: c.model_copy(deep=True) for c in entry.curves}
            coverage = [c.model_copy(deep=True) for c in entry.coverage]
            positions = entry.positions[offset:entry.ends.get(offset, 0)]
            processed = 0
            paused = False
            for start in range(0, len(positions), 2):
                if paused or (processed and self.clock() >= deadline):
                    break
                self._check(entry, stop)
                pending = []
                for position in positions[start:start+2]:
                    try:
                        identity = (position.source.model_dump_json(), position.frame.run_id, position.frame.valid_time)
                        future = entry.ifs_pending.get(identity) if position.source.source_id == 'ecmwf-ifs' else None
                        if future is None:
                            future = self._bounded(lambda p=position: self._read_position(p, entry.selection, entry.ifs_budget), deadline,
                                lambda: stop() or entry.cancelled.is_set() or self.clock() >= entry.expires)
                            if position.source.source_id == 'ecmwf-ifs': entry.ifs_pending[identity] = future
                        pending.append((position, future))
                    except Exception:
                        pending.append((position, None))
                for position, future in pending:
                    processed += 1
                    self._check(entry, stop)
                    reason = None
                    field_failures = {}
                    intervals = {}
                    member_values = {}
                    member_units = {}
                    bands = {}
                    try:
                        if future is None: raise TimeoutError()
                        result = future.result(timeout=max(.001, deadline-self.clock()))
                        fields = getattr(result, "fields", result)
                        field_failures = getattr(result, "failures", {})
                        intervals = getattr(result,"intervals",{})
                        member_values = getattr(result,"member_values",{})
                        member_units = getattr(result,"member_units",{})
                        bands = getattr(result,"bands",{})
                    except Exception as error:
                        if isinstance(error, TimeoutError) and position.source.source_id == 'ecmwf-ifs' and future is not None and not future.done():
                            processed -= 1
                            paused = True
                            break
                        fields = []
                        state, reason = source_failure(error)
                        if isinstance(error, TimeoutError): reason = 'Page acquisition deadline exceeded'
                        for item in coverage:
                            if item.source_id == position.source.source_id:
                                item.state, item.reason = state, reason
                                item.failure_kind = type(error).__name__
                    for template in position.curves:
                        curve = curves[template.id]
                        if curve.reason: continue
                        frame = position.frame
                        matching = [f for f in fields if f.provenance.source_id == curve.source_id
                            and f.provenance.valid_time == frame.valid_time
                            and (frame.run_time is None or f.provenance.run_time == frame.run_time)]
                        central = next((f for f in matching if f.key == curve.field), None)
                        sample = ComparisonSample(time=frame.valid_time, run_id=frame.run_id, evidence=central,
                            reason=reason or field_failures.get(curve.field) or ('Selected native field is missing' if central is None else None))
                        sample.member_values=member_values.get(curve.field,{})
                        sample.member_units=member_units.get(curve.field)
                        if curve.field in bands:sample.lower,sample.upper=bands[curve.field]
                        if curve.field in intervals:sample.interval_start,sample.interval_end=intervals[curve.field]
                        if central:
                            curve.units = {'m s-1':'m/s', 'm s**-1':'m/s', '%':'percent', 'degree_Celsius':'degC'}.get(central.provenance.normalized_units, central.provenance.normalized_units)
                            if curve.group == 'precipitation' and curve.field == 'weathernext3_total_precipitation_1hr_mean':
                                sample.interval_start, sample.interval_end = frame.valid_time-timedelta(hours=1), frame.valid_time
                            if entry.selection.ensemble_spread and curve.source_id == 'google-weathernext-3-statistics':
                                from registry.weathernext import BY_KEY, BY_NATIVE
                                base = BY_KEY[curve.field].native.rsplit('_',1)[0]
                                for stat, attr in [('p10','lower'),('p90','upper')]:
                                    key = BY_NATIVE[f'{base}_{stat}'].key
                                    value = next((f for f in matching if f.key == key and f.provenance.normalized_units == curve.units), None)
                                    setattr(sample, attr, value)
                                if any(bound is None or not isinstance(bound.value, (int, float)) for bound in (sample.lower, sample.upper)):
                                    sample.reason = "Matching published P10–P90 unavailable for this native sample"
                        curve.samples.append(sample)
            self._check(entry, stop)
            end = offset+processed
            if end < offset+len(positions):
                entry.ends[end] = entry.ends[offset]
                if end not in entry.tokens:
                    token = secrets.token_urlsafe(32)
                    entry.tokens[end] = token
                    with self.lock: self.tokens[token] = (entry.id, end)
            page = ComparisonPage(id=entry.id, selection=entry.selection, selected_at=entry.selected_at,
                expires_at=entry.expires_at, curves=list(curves.values()), coverage=coverage,
                next_cursor=entry.tokens.get(end), complete=end == len(entry.positions),
                completed_positions=end, total_positions=len(entry.positions))
            size = len(page.model_dump_json().encode())
            if size > PAGE_BYTES:
                fail('query_limit_exceeded', 'Comparison page exceeds 512 KiB')
            if not reserve(entry.id, entry.size+size, time.monotonic()+max(0,entry.expires-self.clock())):
                fail('snapshot_capacity_unavailable', 'Shared Series cache byte budget is full', status=503)
            entry.size += size
            if processed or not positions: entry.pages[offset] = page
            return page.model_copy(deep=True)
        finally:
            entry.lock.release()

    def continuation(self, token, stop=lambda: False):
        with self.lock:
            selected = self.tokens.get(token)
            entry = self.entries.get(selected[0]) if selected else None
        if entry is None: fail('invalid_cursor', 'Comparison cursor is unavailable')
        return self._page(entry, selected[1], stop)

    def cancel(self, identity):
        with self.lock:
            entry = self.entries.pop(identity, None)
            if entry:
                entry.cancelled.set()
                if entry.ifs_budget is not None: entry.ifs_budget.cancelled.set()
                for token in entry.tokens.values(): self.tokens.pop(token, None)
                release(identity)


@lru_cache(maxsize=1)
def comparison_service():
    return ComparisonService()


router = APIRouter()


@router.post('/point/comparison', response_model=ComparisonPage)
async def comparison(body: ComparisonSelection | Continuation, request: Request):
    stopped = threading.Event()
    service = comparison_service()
    work = service.continuation if isinstance(body, Continuation) else service.initial
    arg = body.cursor if isinstance(body, Continuation) else body
    task = asyncio.create_task(asyncio.to_thread(work, arg, stopped.is_set))
    try:
        while not task.done():
            if await request.is_disconnected(): stopped.set()
            await asyncio.wait({task}, timeout=.1)
        return await task
    finally:
        stopped.set()


@router.delete('/point/comparison/{identity}', status_code=204)
def cancel_comparison(identity: str):
    comparison_service().cancel(identity)
