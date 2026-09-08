"""Isolated exact-analysis OISST query; never registered or operational.

The existing capture contract owns the fixed native evidence-box crop. A single
finite cache shares that crop across points; no archive or forecast is inferred.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import threading
import time
from concurrent.futures import Future, TimeoutError
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xarray as xr
import zarr

from ingest.captures.sst_analysis import OISSTAdapter, EVIDENCE_BOUNDS
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient
from ingest.isolation import ProcessAllocationLimits, run_bounded_process
from .grids import _cell_indices
from .models import Coverage, DataMode, EvidenceField, Freshness, Provenance, Quality

TTL_SECONDS = 300
TIMEOUT_SECONDS = 90
MAX_RESULT_BYTES = 512 * 1024
LIMITS = ProcessAllocationLimits(2 * 1024**3, 64 * 1024**2, 4096, MAX_RESULT_BYTES, 32768)
FIELDS = ('sea_surface_temperature', 'sea_surface_temperature_uncertainty')


class OISSTUnavailable(RuntimeError):
    pass


class _CompletionClient:
    """Capture upstream completion before native decode and QC can advance time."""
    def __init__(self, client, clock, utcnow):
        self.client, self.clock, self.utcnow = client, clock, utcnow
        self.completed_at = None
        self.completed_monotonic = None

    def _completed(self, result):
        self.completed_monotonic = self.clock()
        self.completed_at = self.utcnow()
        return result

    def get_bytes(self, *args, **kwargs):
        return self._completed(self.client.get_bytes(*args, **kwargs))

    def download(self, *args, **kwargs):
        receipt = self.client.download_with_receipt(*args, **kwargs)
        completed = receipt['completed_at']
        if not isinstance(completed, datetime) or completed.tzinfo is None:
            raise AdapterUnavailable('OISST download has no aware completion receipt')
        # The polite transport stamps final-byte completion before response
        # close/bookkeeping. Subtract that elapsed time from the observed
        # monotonic clock so closing cannot renew the cache deadline.
        observed = self.clock()
        elapsed = max(0.0, (self.utcnow() - completed).total_seconds())
        self.completed_monotonic = observed - elapsed
        self.completed_at = completed
        return int(receipt['byte_size'])


def acquire(selected: datetime, client, clock=time.monotonic,
            utcnow=lambda: datetime.now(UTC), *, workspace=None) -> dict:
    """Run only inside the bounded leaf (or with an offline injected client)."""
    window = FetchWindow(selected, back_hours=0, forward_hours=0)
    completion = _CompletionClient(client, clock, utcnow)
    adapter = OISSTAdapter(completion)
    candidate = adapter.discover(window)[0]
    if candidate.run_time != selected:
        raise AdapterUnavailable('OISST requires the exact published daily analysis timestamp')
    # Production leaf always supplies its parent-owned workspace. SIGKILL
    # cleanup therefore does not depend on this child running its finally.
    with tempfile.TemporaryDirectory(prefix='astraeus-oisst-', dir=workspace) as directory:
        result = adapter.fetch(candidate, window, Path(directory))
        if not result.complete or not result.qc_passed:
            raise AdapterUnavailable('OISST required-field completeness/QC refused')
        artifact = result.artifacts[0]
        with zarr.storage.ZipStore(artifact.payload_path, mode='r') as store:
            with xr.open_zarr(store, consolidated=False) as ds:
                if ds.sizes.get('valid_time') != 1 or ds.sizes['latitude'] * ds.sizes['longitude'] > 2048:
                    raise AdapterUnavailable('OISST crop shape exceeds query ceiling')
                data = {name: ds[name].values[0].tolist() for name in FIELDS}
                # JSON carries native missingness as null, never NaN.
                data = {name: [[float(v) if math.isfinite(float(v)) else None for v in row] for row in rows] for name, rows in data.items()}
                data.update(latitude=ds.latitude.values.tolist(), longitude=ds.longitude.values.tolist())
        if completion.completed_at is None or completion.completed_monotonic is None:
            raise AdapterUnavailable('OISST has no completed upstream retrieval')
        provenance = dict(artifact.provenance, retrieval_time=completion.completed_at.isoformat())
        data.update(valid_time=candidate.run_time.isoformat(), provenance=provenance, analysis_status=candidate.detail['identity'],
                    completed_monotonic=completion.completed_monotonic)
    return data


class OISSTQueryService:
    def __init__(self, *, client=None, clock=time.monotonic, utcnow=lambda: datetime.now(UTC)):
        self.client, self.clock, self.utcnow = client, clock, utcnow
        self.lock = threading.Lock()
        self.entry = None
        self.inflight = {}

    def query(self, selected: datetime, *, refresh=False):
        if selected.tzinfo is None:
            raise ValueError('OISST selection needs a timezone')
        selected = selected.astimezone(UTC)
        if selected.hour != 12 or selected.minute or selected.second or selected.microsecond:
            raise ValueError('OISST requires exact published 12:00 UTC daily analysis time')
        now = self.utcnow().astimezone(UTC)
        if not 0 <= (now.date() - selected.date()).days <= 4 or selected > now:
            raise ValueError('OISST query supports only current published daily analyses, not archives')
        # The adapter's current-only discovery is authoritative. No daily
        # interval applicability or neighbouring timestamp is invented here.
        with self.lock:
            if self.entry and self.clock() >= self.entry[1]:
                self.entry = None
            if not refresh and self.entry and self.entry[0] == selected:
                return json.loads(self.entry[2])
            future = self.inflight.get(selected)
            owner = future is None
            if owner:
                if self.inflight:
                    raise OISSTUnavailable('OISST concurrent acquisition ceiling reached')
                future = self.inflight[selected] = Future()
        if not owner:
            try:
                return json.loads(future.result(timeout=TIMEOUT_SECONDS + 5))
            except TimeoutError as error:
                raise OISSTUnavailable('OISST coalesced wait expired') from error
        try:
            started = self.clock()
            if self.client is not None:
                raw = json.dumps(acquire(selected, self.client, self.clock, self.utcnow), allow_nan=False).encode()
            else:
                result = run_bounded_process(
                    command=[sys.executable, str(Path(__file__).with_name('oisst_query_worker.py')), '{output}'],
                    stdin=selected.isoformat().encode(), destination=None,
                    limits=LIMITS, timeout_seconds=TIMEOUT_SECONDS, require_output=False)
                raw = result.stdout
                if isinstance(raw, str):
                    raw = raw.encode()
            if len(raw) > MAX_RESULT_BYTES or self.clock() - started >= TIMEOUT_SECONDS:
                raise OISSTUnavailable('OISST query exceeds byte/time ceiling')
            data = json.loads(raw)
            self._validate(data, selected)
            # Validation cannot renew the upstream completion-based deadline.
            completed = data['completed_monotonic']
            if (isinstance(completed, bool) or not math.isfinite(completed)
                    or not started <= completed <= self.clock()):
                raise OISSTUnavailable('OISST upstream completion clock is invalid')
            expires = completed + TTL_SECONDS
            if self.clock() >= expires:
                raise OISSTUnavailable('OISST result expired during validation')
            with self.lock:
                self.entry = (selected, expires, raw)
            future.set_result(raw)
            return json.loads(raw)
        except Exception as error:
            failure = OISSTUnavailable(f'OISST acquisition refused: {type(error).__name__}')
            future.set_exception(failure)
            raise failure from error
        finally:
            with self.lock:
                self.inflight.pop(selected, None)

    @staticmethod
    def _validate(data, selected):
        if datetime.fromisoformat(data['valid_time']) != selected:
            raise ValueError('OISST analysis identity changed')
        p = data['provenance']
        if data['analysis_status'] not in ('preliminary', 'final'):
            raise ValueError('OISST preliminary/final identity absent')
        if p['source_id'] != 'noaa-oisst-v2-1' or p['product'] != 'NOAA 0.25-degree Daily OISST AVHRR-only v2.1':
            raise ValueError('OISST source/product mismatch')
        lat, lon = np.asarray(data['latitude']), np.asarray(data['longitude'])
        for axis in (lat, lon):
            if axis.ndim != 1 or axis.size < 2 or not np.isfinite(axis).all() or not (np.diff(axis) > 0).all():
                raise ValueError('OISST invalid native coordinates')
        if lat.size * lon.size > 2048:
            raise ValueError('OISST crop exceeds cell ceiling')
        for name in FIELDS:
            if np.asarray(data[name], dtype=float).shape != (lat.size, lon.size):
                raise ValueError('OISST required field shape mismatch')

    def point_fields(self, latitude, longitude, selected, *, refresh=False):
        if (isinstance(latitude, bool) or isinstance(longitude, bool)
                or not math.isfinite(latitude) or not math.isfinite(longitude)
                or not EVIDENCE_BOUNDS['south'] <= latitude <= EVIDENCE_BOUNDS['north']
                or not EVIDENCE_BOUNDS['west'] <= longitude <= EVIDENCE_BOUNDS['east']):
            raise ValueError('OISST point outside fixed evidence box')
        data = self.query(selected, refresh=refresh)
        y = int(_cell_indices(np.array([latitude]), data['latitude'])[0])
        x = int(_cell_indices(np.array([longitude]), data['longitude'])[0])
        if x < 0 or y < 0:
            raise OISSTUnavailable('OISST point outside native cell support')
        p = data['provenance']
        retrieved = datetime.fromisoformat(p['retrieval_time'])
        fields = []
        for name in FIELDS:
            value = data[name][y][x]
            fields.append(EvidenceField(field=name, key=name, value=value, storage='available-not-stored', provenance=Provenance(
                data_mode=DataMode.LIVE, evidence_class='retrieved', source_id=p['source_id'], artifact_revision=p['artifact_revision'],
                provider=p['producer'], product=p['product'], forecast_centre='NOAA NCEI', run_time=None,
                valid_time=datetime.fromisoformat(data['valid_time']), retrieval_time=retrieved,
                vertical_level='sea surface', original_units=p['original_units'][name],
                normalized_units='degC', native_resolution=p['native_resolution'], native_crs=p['native_crs'],
                quality=Quality(status='unknown' if value is None else 'passed', flags=[*p['quality'].get('flags', []), 'daily_analysis', 'native_missingness_retained', p['product_identity']]),
                coverage=Coverage(**p['coverage']), freshness=Freshness.evaluate(max(0, int((self.utcnow()-retrieved).total_seconds())), TTL_SECONDS),
                licence='NOAA public data; cite OISST v2.1', attribution='NOAA NCEI daily OISST v2.1',
                delivery_kind='published_cell', source_display_primary=False, adapter_version='oisst-query-v1',
                sampled_latitude=data['latitude'][y], sampled_longitude=data['longitude'][x], sample_method='rectilinear')))
        return fields
