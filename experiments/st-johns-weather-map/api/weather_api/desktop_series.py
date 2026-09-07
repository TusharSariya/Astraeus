"""Bounded native Series selections. Accepted desktop-evidence-api-contract.

Only response selections live here, for five minutes. Provider acquisition and
its finite cache remain owned by each existing source coordinator.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Callable, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import Field, ValidationError, field_validator, model_validator

from .models import EvidenceField, StrictModel, catalogue_key_for

TTL_SECONDS = 300
MAX_SELECTIONS = 16
MAX_CACHE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
MAX_NATIVE_READS = 12
READ_SECONDS = 45


class Selector(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    source_id: str = Field(min_length=1, max_length=100)
    field: str = Field(min_length=1, max_length=100)
    run: str = Field(default='latest', max_length=100)

    @field_validator('field')
    @classmethod
    def known_field(cls, value: str) -> str:
        if catalogue_key_for(value) != value:
            raise ValueError('field must be a canonical catalogue key')
        return value


class SeriesSelection(StrictModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    start: datetime
    end: datetime
    selectors: list[Selector] = Field(min_length=1, max_length=2)
    page_size: int = Field(default=12, ge=1, le=24, strict=True)

    @field_validator('start', 'end')
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError('time must include a UTC offset')
        return value.astimezone(UTC)

    @model_validator(mode='after')
    def bounds(self):
        if not timedelta(0) < self.end - self.start <= timedelta(hours=24):
            raise ValueError('window must be positive and at most 24 hours')
        if len({item.id for item in self.selectors}) != len(self.selectors):
            raise ValueError('selector ids must be unique')
        return self


class Continuation(StrictModel):
    cursor: str = Field(min_length=1, max_length=160)


class ChangeRequest(StrictModel):
    change_token: str = Field(min_length=1, max_length=160)


class SelectableRun(StrictModel):
    id: str
    run_time: datetime


class SeriesRow(StrictModel):
    selector_id: str
    source_id: str
    field: str
    requested_run: str
    selectable_runs: list[SelectableRun] = Field(default_factory=list, max_length=2)
    run_inventory_reason: str = "This native reader does not expose a selectable run inventory"
    availability: Literal['available', 'checked_empty', 'unknown', 'unavailable']
    reason: str | None = None
    samples: list[EvidenceField] = Field(default_factory=list)


class ReadingIdentity(StrictModel):
    source_id: str
    field: str
    run_time: datetime | None
    artifact_revision: str | None


class Snapshot(StrictModel):
    id: str
    selected_at: datetime
    expires_at: datetime
    change_token: str
    identities: list[ReadingIdentity]


class SeriesResponse(StrictModel):
    selection: SeriesSelection
    snapshot: Snapshot
    series: list[SeriesRow]
    next_cursor: str | None
    complete: bool
    notices: list[str]


class ChangeResponse(StrictModel):
    snapshot_id: str
    checked_at: datetime
    state: Literal['unchanged', 'changed', 'unknown']
    changed_selector_ids: list[str]
    reason: str


def fail(code: str, message: str, *, status: int = 422, restart: bool = False):
    raise HTTPException(status_code=status, detail={
        'code': code, 'message': message, 'retryable': status == 503,
        'restart_required': restart, 'details': {},
    })


def _row(selector: Selector, availability: str, reason: str, samples=None) -> SeriesRow:
    return SeriesRow(selector_id=selector.id, source_id=selector.source_id,
                     field=selector.field, requested_run=selector.run,
                     availability=availability, reason=reason, samples=samples or [])


class NativeForecastReader:
    """Discover native inventory, then use the existing exact-time point seam.

    No /point fanout (which would query unrelated observations), hourly timeline,
    persistent store, or invented samples. Missing advertised fields are unknown,
    not proof that the provider published an absence.
    """
    def __call__(self, selection: SeriesSelection, stop: Callable[[], bool]) -> list[SeriesRow]:
        from .store import configured_mode, LIVE_MODE
        if configured_mode() != LIVE_MODE:
            return [_row(s, 'unavailable', 'Native Series requires live source queries; no fixture fallback') for s in selection.selectors]
        from .hrdps_query import hrdps_query_coordinator
        from .rdps_query import rdps_query_coordinator
        from .gdps_query import gdps_query_coordinator
        from .gfs_query import gfs_query_coordinator
        factories = {'eccc-hrdps': hrdps_query_coordinator, 'eccc-rdps': rdps_query_coordinator,
                     'eccc-gdps': gdps_query_coordinator, 'noaa-gfs': gfs_query_coordinator}
        rows: list[SeriesRow] = []
        inventory = {}
        runs = {}
        queried = {}
        reads = 0
        from .native_runs import RunUnavailable
        for selector in selection.selectors:
            if stop():
                fail('snapshot_unreadable', 'Native Series acquisition deadline exceeded', status=503)
            factory = factories.get(selector.source_id)
            if factory is None:
                rows.append(_row(selector, 'unavailable', 'Native Series acquisition is not implemented for this source'))
                continue
            selectable = []
            run_reason = 'This native reader does not expose a selectable run inventory'
            def result(availability, reason, samples=()):
                row = _row(selector, availability, reason, samples)
                row.selectable_runs = selectable
                row.run_inventory_reason = run_reason
                return row
            try:
                coordinator = factory()
                supports_runs = callable(getattr(coordinator, 'run_inventory', None))
                if selector.run != 'latest' and not supports_runs:
                    rows.append(result('unavailable', 'This delivery path cannot pin that named run; choose Latest available explicitly'))
                    continue
                if supports_runs:
                    if selector.source_id not in runs:
                        runs[selector.source_id] = coordinator.run_inventory()
                    declared = runs[selector.source_id]
                    selectable = [SelectableRun(id=run.provider_run_id, run_time=run.run_time) for run in declared]
                    run_reason = 'Latest/previous from the existing bounded source directory listing; listed paths are validated on acquisition. Missing older dated roots are not inferred.'
                    if selector.run != 'latest' and selector.run not in {run.id for run in selectable}:
                        raise RunUnavailable('Run no longer available in the bounded latest/previous inventory')
                    times_to_run = {}
                    # Walk newest first: older-run segments fill only the times
                    # the newer inventory does not cover, with actual runs kept.
                    for run in selectable:
                        if selector.run not in ('latest', run.id):
                            continue
                        key = (selector.source_id, run.id)
                        if key not in inventory:
                            inventory[key] = coordinator.run_times(run.id)
                        for stamp in inventory[key]:
                            if selection.start <= stamp < selection.end:
                                times_to_run.setdefault(stamp, run)
                    stamps = sorted(times_to_run)
                else:
                    key = (selector.source_id, 'latest')
                    if key not in inventory:
                        stamps = coordinator.timeline_times(selection.start)
                        if selector.source_id == 'noaa-gfs':
                            stamps, _receipt = stamps
                        inventory[key] = sorted({stamp for stamp in stamps if selection.start <= stamp < selection.end})
                    stamps = inventory[key]
                    times_to_run = {}
                keys = [(selector.source_id, times_to_run[stamp].id if stamp in times_to_run else 'latest', stamp) for stamp in stamps]
                if reads + sum(key not in queried for key in keys) > MAX_NATIVE_READS:
                    fail('query_limit_exceeded', 'Selection exceeds 12 native source/run/timestamp reads; shorten the window')
                if not stamps:
                    rows.append(result('unknown', 'No native timestamps in the consulted run listing for this window; a pinned run is not substituted'))
                    continue
                samples = []
                incomplete = False
                for stamp, key in zip(stamps, keys):
                    if stop():
                        fail('snapshot_unreadable', 'Native Series acquisition deadline exceeded', status=503)
                    if key not in queried:
                        reads += 1
                        options = {'run_id': key[1]} if supports_runs else {}
                        queried[key], _, _ = coordinator.point_fields(selection.latitude, selection.longitude, stamp, **options)
                    matching = [field for field in queried[key] if field.key == selector.field
                                and field.provenance.source_id == selector.source_id
                                and field.provenance.valid_time == stamp
                                and (not supports_runs or field.provenance.run_time == times_to_run[stamp].run_time)]
                    samples.extend(matching)
                    incomplete |= not bool(matching)
                rows.append(result('unknown' if incomplete else 'available',
                                   'Some advertised timestamps did not return the selected field/run; these intervals are unknown' if incomplete else 'Native provider timestamps and actual run segments only', samples))
            except RunUnavailable as error:
                rows.append(result('unavailable', str(error)))
            except HTTPException:
                raise
            except Exception:
                rows.append(result('unknown', 'The native source inventory or selected-time acquisition could not be read'))

        return rows


def baseline(row: SeriesRow) -> str:
    """Compare selected evidence, not its elapsed age or HTTP revalidation time."""
    value = row.model_dump(mode='json', exclude={'selectable_runs', 'run_inventory_reason'})
    for sample in value['samples']:
        provenance = sample['provenance']
        for name in ('retrieval_time', 'freshness', 'demand_acquisition', 'aqhi_acquisition', 'swob_acquisition'):
            provenance.pop(name, None)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass
class CachedSelection:
    selection: SeriesSelection
    snapshot: Snapshot
    rows: list[SeriesRow]
    expires: float
    size: int
    cursors: dict[str, int]


class SeriesService:
    def __init__(self, reader=None, *, clock=time.monotonic, utcnow=lambda: datetime.now(UTC),
                 read_seconds=READ_SECONDS):
        self.reader = reader or NativeForecastReader()
        self.clock, self.utcnow, self.read_seconds = clock, utcnow, read_seconds
        self.lock = threading.Lock()
        self.entries: dict[str, CachedSelection] = {}
        self.cursor_key = secrets.token_bytes(32)
        self.inflight: dict[str, Future] = {}
        # Reject excess work instead of queuing unbounded provider operations.
        # A timed-out worker holds its slot until the existing bounded provider
        # operation ends, then stops before starting another native read.
        self.slots = threading.BoundedSemaphore(2)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='native-series')

    def _read(self, selection):
        if not self.slots.acquire(blocking=False):
            fail('snapshot_capacity_unavailable', 'Two native reads are already in flight', status=503)
        stopped = threading.Event()
        deadline = self.clock() + self.read_seconds
        def work():
            try:
                return self.reader(selection, lambda: stopped.is_set() or self.clock() >= deadline)
            finally:
                self.slots.release()
        future = self.executor.submit(work)
        try:
            return future.result(timeout=self.read_seconds)
        except TimeoutError:
            stopped.set()
            fail('snapshot_unreadable', 'Native Series acquisition deadline exceeded', status=503)

    def _expire(self):
        for key, entry in list(self.entries.items()):
            if self.clock() >= entry.expires:
                del self.entries[key]

    def initial(self, selection: SeriesSelection) -> SeriesResponse:
        from .fixtures import AVALON_CORE_BOUNDS as bounds
        if not (bounds['south'] <= selection.latitude <= bounds['north'] and bounds['west'] <= selection.longitude <= bounds['east']):
            fail('outside_supported_area', 'Coordinate is outside the Avalon core coverage')
        key = selection.model_dump_json()
        with self.lock:
            self._expire()
            future = self.inflight.get(key)
            owner = future is None
            if owner:
                if len(self.entries) + len(self.inflight) >= MAX_SELECTIONS:
                    fail('snapshot_capacity_unavailable', 'Finite selection cache is full; existing selections remain readable', status=503)
                future = Future()
                self.inflight[key] = future
        if not owner:
            try:
                return future.result(timeout=self.read_seconds + 1).model_copy(deep=True)
            except TimeoutError:
                fail('snapshot_unreadable', 'Concurrent selection acquisition deadline exceeded', status=503)
        try:
            rows = [row.model_copy(deep=True) for row in self._read(selection)]
            size = len(json.dumps([row.model_dump(mode='json') for row in rows]).encode())
            if size > MAX_RESPONSE_BYTES or sum(len(row.samples) for row in rows) > 48:
                fail('query_limit_exceeded', 'Selection exceeds 48 samples or 512 KiB')
            selected_at = self.utcnow()
            identities = {(sample.provenance.source_id, sample.key, sample.provenance.run_time, sample.provenance.artifact_revision)
                          for row in rows for sample in row.samples}
            snapshot = Snapshot(id=uuid4().hex, selected_at=selected_at,
                expires_at=selected_at + timedelta(seconds=TTL_SECONDS), change_token='',
                identities=[ReadingIdentity(source_id=s, field=f, run_time=r, artifact_revision=a)
                            for s, f, r, a in sorted(identities, key=str)])
            count = sum(max(1, len(row.samples)) for row in rows)
            snapshot.change_token = self._token(snapshot, -1)
            cursors = {self._token(snapshot, offset): offset for offset in range(selection.page_size, count, selection.page_size)}
            size += len(selection.model_dump_json().encode()) + len(snapshot.model_dump_json().encode()) + len(json.dumps(cursors).encode()) + 1024
            if size > MAX_RESPONSE_BYTES:
                fail('query_limit_exceeded', 'Selection and its metadata exceed 512 KiB')
            entry = CachedSelection(selection.model_copy(deep=True), snapshot, rows, self.clock() + TTL_SECONDS, size, cursors)
            with self.lock:
                self._expire()
                if sum(item.size for item in self.entries.values()) + size > MAX_CACHE_BYTES:
                    fail('snapshot_capacity_unavailable', 'Finite selection byte budget is full', status=503)
                self.entries[snapshot.id] = entry
            result = self._page(entry, 0)
            future.set_result(result)
            return result.model_copy(deep=True)
        except Exception as error:
            if not isinstance(error, HTTPException):
                error = HTTPException(status_code=503, detail={'code': 'snapshot_unreadable',
                    'message': 'Native Series could not be acquired', 'retryable': True,
                    'restart_required': False, 'details': {}})
            future.set_exception(error)
            raise error
        finally:
            with self.lock:
                del self.inflight[key]

    def _page(self, entry, offset):
        units = [(row, sample) for row in entry.rows for sample in (row.samples or [None])]
        selected = units[offset:offset + entry.selection.page_size]
        rows = []
        for row, sample in selected:
            if not rows or rows[-1].selector_id != row.selector_id:
                rows.append(row.model_copy(update={'samples': []}, deep=True))
            if sample is not None:
                rows[-1].samples.append(sample.model_copy(deep=True))
        next_offset = offset + len(selected)
        cursor = next((token for token, position in entry.cursors.items() if position == next_offset), None)
        return SeriesResponse(selection=entry.selection, snapshot=entry.snapshot, series=rows,
            next_cursor=cursor, complete=cursor is None, notices=[
                'Selection expires without renewal after five minutes. Refresh is a new read.',
                'Native reads use existing finite source caches; change checks do not force provider revalidation.',
            ])

    def _token(self, snapshot, offset):
        payload = f'{snapshot.id}:{offset}:{snapshot.expires_at.timestamp()}'.encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip('=')
        signature = hmac.new(self.cursor_key, encoded.encode(), hashlib.sha256).hexdigest()[:32]
        return f'{encoded}.{signature}'

    def _lookup(self, token, *, change=False):
        try:
            encoded, signature = token.split('.')
            expected = hmac.new(self.cursor_key, encoded.encode(), hashlib.sha256).hexdigest()[:32]
            if not hmac.compare_digest(signature, expected):
                raise ValueError('signature')
            identity, position, expiry = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode().split(':')
            if (int(position) == -1) != change:
                raise ValueError('token purpose')
        except (ValueError, UnicodeError):
            fail('invalid_cursor', 'Invalid selection token')
        with self.lock:
            entry = self.entries.get(identity)
            if self.utcnow().timestamp() >= float(expiry) or (entry and self.clock() >= entry.expires):
                fail('snapshot_expired', 'Selection expired; start a new read', status=410, restart=True)
            if entry is None:
                fail('snapshot_unreadable', 'Selection backing is unavailable; start a new read', status=410, restart=True)
            if not change and token not in entry.cursors:
                fail('invalid_cursor', 'Invalid continuation position')
            return entry

    def continuation(self, cursor):
        entry = self._lookup(cursor)
        return self._page(entry, entry.cursors[cursor]).model_copy(deep=True)

    def changes(self, token):
        entry = self._lookup(token, change=True)
        changed = []
        state = 'unknown'
        reason = 'Relevant evidence could not be compared'
        try:
            rows = self._read(entry.selection)
            if all(row.availability in ('available', 'checked_empty') for row in rows + entry.rows):
                current = {row.selector_id: baseline(row) for row in rows}
                changed = [row.selector_id for row in entry.rows if current.get(row.selector_id) != baseline(row)]
                state = 'changed' if changed else 'unchanged'
                reason = 'Compared the original selected evidence with current finite source-cache reads; displayed values were not replaced'
        except Exception:
            pass
        self._lookup(token, change=True)  # a slow comparison cannot outlive its pin
        return ChangeResponse(snapshot_id=entry.snapshot.id, checked_at=self.utcnow(), state=state,
                              changed_selector_ids=changed, reason=reason)


@lru_cache(maxsize=1)
def series_service():
    return SeriesService()


router = APIRouter()


@router.post('/point/series', response_model=SeriesResponse)
def read_series(body: dict):
    try:
        if 'cursor' in body:
            request = Continuation.model_validate(body)
            return series_service().continuation(request.cursor)
        selection = SeriesSelection.model_validate(body)
    except ValidationError:
        fail('invalid_cursor' if 'cursor' in body else 'invalid_selection', 'Invalid Series selection or altered continuation')
    return series_service().initial(selection)


@router.post('/point/series/changes', response_model=ChangeResponse)
def check_series_changes(body: ChangeRequest):
    return series_service().changes(body.change_token)
