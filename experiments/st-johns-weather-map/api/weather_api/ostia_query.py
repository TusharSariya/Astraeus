"""Isolated exact-analysis OSTIA query; never registered or operational.

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

from ingest.captures.sst_analysis import OSTIAAdapter, EVIDENCE_BOUNDS
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient
from ingest.isolation import ProcessAllocationLimits, run_bounded_process
from .models import Coverage, DataMode, EvidenceField, Freshness, Provenance, Quality

TTL_SECONDS = 300
TIMEOUT_SECONDS = 90
MAX_RESULT_BYTES = 8 * 1024**2
LIMITS = ProcessAllocationLimits(2 * 1024**3, 1024**3, 4096, MAX_RESULT_BYTES, 32768)
FIELDS = ('sea_surface_temperature', 'sea_surface_temperature_uncertainty', 'sea_surface_temperature_mask')


class OSTIAUnavailable(RuntimeError):
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
            raise AdapterUnavailable('OSTIA download has no aware completion receipt')
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
    adapter = OSTIAAdapter(completion)
    candidate = adapter.discover(window)[0]
    # Refuse changed native layouts before downloading field chunks. The
    # compressed-response ceiling alone does not bound decompression memory.
    metadata = candidate.detail['metadata']['metadata']
    for name in ('time', 'latitude', 'longitude', 'analysed_sst', 'analysis_error', 'mask'):
        spec = metadata[f'{name}/.zarray']
        chunks = spec['chunks']
        if (any(type(v) is not int or v <= 0 for v in chunks)
                or math.prod(chunks) * np.dtype(spec['dtype']).itemsize > 64 * 1024**2):
            raise AdapterUnavailable('OSTIA decoded native chunk exceeds ceiling')
    if candidate.run_time != selected:
        raise AdapterUnavailable('OSTIA requires the exact published daily analysis timestamp')
    # Production leaf always supplies its parent-owned workspace. SIGKILL
    # cleanup therefore does not depend on this child running its finally.
    with tempfile.TemporaryDirectory(prefix='astraeus-ostia-', dir=workspace) as directory:
        result = adapter.fetch(candidate, window, Path(directory))
        if not result.complete or not result.qc_passed:
            raise AdapterUnavailable('OSTIA required-field completeness/QC refused')
        artifact = result.artifacts[0]
        with zarr.storage.ZipStore(artifact.payload_path, mode='r') as store:
            with xr.open_zarr(store, consolidated=False) as ds:
                if ds.sizes.get('valid_time') != 1 or ds.sizes['latitude'] * ds.sizes['longitude'] > 100000:
                    raise AdapterUnavailable('OSTIA crop shape exceeds query ceiling')
                data = {name: ds[name].values[0].tolist() for name in FIELDS}
                # JSON carries native missingness as null, never NaN.
                data = {name: [[float(v) if math.isfinite(float(v)) else None for v in row] for row in rows] for name, rows in data.items()}
                data.update(latitude=ds.latitude.values.tolist(), longitude=ds.longitude.values.tolist())
        if completion.completed_at is None or completion.completed_monotonic is None:
            raise AdapterUnavailable('OSTIA has no completed upstream retrieval')
        provenance = dict(artifact.provenance, retrieval_time=completion.completed_at.isoformat())
        data.update(valid_time=candidate.run_time.isoformat(), provenance=provenance,
                    completed_monotonic=completion.completed_monotonic)
    return data


def _native_axis_cell(value, centres):
    """Choose one published centre despite native FP32 coordinate rounding.

    OSTIA's 0.05-degree axis arrives as FP32, whose rounding is larger than
    the raster helper's generic uniform-step tolerance. Keep original centres
    and permit only their quantization error; never interpolate the SST.
    """
    axis = np.asarray(centres, dtype=float)
    gaps = np.diff(axis)
    step = float(np.median(gaps))
    tolerance = 2 * np.finfo(np.float32).eps * float(np.max(np.abs(axis)))
    if step <= 0 or not np.allclose(gaps, step, rtol=0, atol=max(step * 1e-6, tolerance)):
        raise OSTIAUnavailable('OSTIA native axis spacing changed beyond FP32 precision')
    if value < axis[0] - gaps[0] / 2 or value > axis[-1] + gaps[-1] / 2:
        return -1
    return int(np.argmin(np.abs(axis - value)))


class OSTIAQueryService:
    def __init__(self, *, client=None, clock=time.monotonic, utcnow=lambda: datetime.now(UTC)):
        self.client, self.clock, self.utcnow = client, clock, utcnow
        self.lock = threading.Lock()
        self.entry = None
        self.inflight = {}

    def query(self, selected: datetime, *, refresh=False):
        if selected.tzinfo is None:
            raise ValueError('OSTIA selection needs a timezone')
        selected = selected.astimezone(UTC)
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
                    raise OSTIAUnavailable('OSTIA concurrent acquisition ceiling reached')
                future = self.inflight[selected] = Future()
        if not owner:
            try:
                return json.loads(future.result(timeout=TIMEOUT_SECONDS + 5))
            except TimeoutError as error:
                raise OSTIAUnavailable('OSTIA coalesced wait expired') from error
        try:
            started = self.clock()
            if self.client is not None:
                raw = json.dumps(acquire(selected, self.client, self.clock, self.utcnow), allow_nan=False).encode()
            else:
                result = run_bounded_process(
                    command=[sys.executable, str(Path(__file__).with_name('ostia_query_worker.py')), '{output}'],
                    stdin=selected.isoformat().encode(), destination=None,
                    limits=LIMITS, timeout_seconds=TIMEOUT_SECONDS, require_output=False)
                raw = result.stdout
                if isinstance(raw, str):
                    raw = raw.encode()
            if len(raw) > MAX_RESULT_BYTES or self.clock() - started >= TIMEOUT_SECONDS:
                raise OSTIAUnavailable('OSTIA query exceeds byte/time ceiling')
            data = json.loads(raw)
            self._validate(data, selected)
            # Validation cannot renew the upstream completion-based deadline.
            completed = data['completed_monotonic']
            if (isinstance(completed, bool) or not math.isfinite(completed)
                    or not started <= completed <= self.clock()):
                raise OSTIAUnavailable('OSTIA upstream completion clock is invalid')
            expires = completed + TTL_SECONDS
            if self.clock() >= expires:
                raise OSTIAUnavailable('OSTIA result expired during validation')
            with self.lock:
                self.entry = (selected, expires, raw)
            future.set_result(raw)
            return json.loads(raw)
        except Exception as error:
            failure = OSTIAUnavailable(f'OSTIA acquisition refused: {type(error).__name__}')
            future.set_exception(failure)
            raise failure from error
        finally:
            with self.lock:
                self.inflight.pop(selected, None)

    @staticmethod
    def _validate(data, selected):
        if datetime.fromisoformat(data['valid_time']) != selected:
            raise ValueError('OSTIA analysis identity changed')
        p = data['provenance']
        if p['source_id'] != 'metoffice-ostia-sst' or p['product'] != 'METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2':
            raise ValueError('OSTIA source/product mismatch')
        lat, lon = np.asarray(data['latitude']), np.asarray(data['longitude'])
        for axis in (lat, lon):
            if axis.ndim != 1 or axis.size < 2 or not np.isfinite(axis).all() or not (np.diff(axis) > 0).all():
                raise ValueError('OSTIA invalid native coordinates')
        if lat.size * lon.size > 100000:
            raise ValueError('OSTIA crop exceeds cell ceiling')
        for name in FIELDS:
            if np.asarray(data[name], dtype=float).shape != (lat.size, lon.size):
                raise ValueError('OSTIA required field shape mismatch')

    def point_fields(self, latitude, longitude, selected, *, refresh=False):
        if (isinstance(latitude, bool) or isinstance(longitude, bool)
                or not math.isfinite(latitude) or not math.isfinite(longitude)
                or not EVIDENCE_BOUNDS['south'] <= latitude <= EVIDENCE_BOUNDS['north']
                or not EVIDENCE_BOUNDS['west'] <= longitude <= EVIDENCE_BOUNDS['east']):
            raise ValueError('OSTIA point outside fixed evidence box')
        data = self.query(selected, refresh=refresh)
        y = _native_axis_cell(latitude, data['latitude'])
        x = _native_axis_cell(longitude, data['longitude'])
        if x < 0 or y < 0:
            raise OSTIAUnavailable('OSTIA point outside native cell support')
        p = data['provenance']
        retrieved = datetime.fromisoformat(p['retrieval_time'])
        fields = []
        for name in FIELDS:
            value = data[name][y][x]
            fields.append(EvidenceField(field=name, key=name, value=value, storage='available-not-stored', provenance=Provenance(
                data_mode=DataMode.LIVE, evidence_class='retrieved', source_id=p['source_id'], artifact_revision=p['artifact_revision'],
                provider=p['producer'], product=p['product'], forecast_centre='Met Office', run_time=None,
                valid_time=datetime.fromisoformat(data['valid_time']), retrieval_time=retrieved,
                vertical_level='sea surface foundation', original_units=p['original_units'][name],
                normalized_units='flag' if name.endswith('_mask') else 'degC', native_resolution=p['native_resolution'], native_crs=p['native_crs'],
                quality=Quality(status='unknown' if value is None or (name.endswith('_mask') and value == -128) else 'passed', flags=[*p['quality'].get('flags', []), 'daily_analysis', 'native_surface_mask_retained']),
                coverage=Coverage(**p['coverage']), freshness=Freshness.evaluate(max(0, int((self.utcnow()-retrieved).total_seconds())), TTL_SECONDS),
                licence='Copernicus Marine Service terms', attribution='Met Office OSTIA via Copernicus Marine',
                delivery_kind='published_cell', source_display_primary=False, adapter_version='ostia-query-v1',
                sampled_latitude=data['latitude'][y], sampled_longitude=data['longitude'][x], sample_method='rectilinear')))
        return fields


_service = None
_service_lock = threading.Lock()


def ostia_query_service():
    global _service
    with _service_lock:
        if _service is None:
            _service = OSTIAQueryService()
        return _service
