"""Four catalogued GEPS provider reductions; full five-coverage acquisition.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
The fifth raw gust probability has no accepted catalogue mapping. It remains
in the underlying artifact, never silently becomes a 10 m gust field.
"""
from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import threading
import time
import zipfile
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr
import zarr
from registry import fields as catalogue
from ingest.adapters.eccc_geomet import GeoMetClient
from ingest.adapters.eccc_geomet_reductions import SELECTED_REDUCTIONS
from ingest.derive.registry import ENSEMBLE_MEAN, ENSEMBLE_SPREAD, ENSEMBLE_QUANTILE
from ingest.isolation import run_bounded_process
from ingest.http import PoliteClient
from ingest.adapters.eccc_geomet_ensemble import REPS_EVIDENCE_BOX
from ingest.registry import get_config

from .geps_query import (GEPSRequestKey, GEPSQueryEntry, GEPSSelectedLoader,
    GEPS_CHILD_LIMITS, GEPS_OUTPUT_BYTES, _ReceiptClient, exact_advertised,
    validate_normalized_payload)
from .grids import _cell_indices
from .models import Coverage, EnsembleProvenance, EvidenceField, Freshness, Provenance, Quality
from .native_runs import RunUnavailable
from .source_contract import SourceAcquisition, SourceCapability, SourceTransferReceipt, SourceVariant
from .source_status import observed_read

SOURCE_ID = 'eccc-geps'
PRODUCT_ID = 'geomet-provider-reductions'
POINT_PRODUCT = 'GEPS reductions'
TTL_SECONDS = 300
MAPPED = tuple(zip(SELECTED_REDUCTIONS[:4], (ENSEMBLE_MEAN, ENSEMBLE_SPREAD, ENSEMBLE_QUANTILE, ENSEMBLE_QUANTILE), strict=True))
RESIDUAL = ('Five verified coverages acquired; raw gust-threshold probability lacks an accepted catalogue/level/window mapping; '
            '527 other advertised reductions remain unresolved; no member or native Series capability')


def validate_selection(selected):
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError('GEPS selection must be offset-aware')
    selected = selected.astimezone(UTC)
    if selected.minute or selected.second or selected.microsecond:
        raise ValueError('GEPS requires exact whole-hour provider time')
    return selected


class GEPSDeliveryHTTP(PoliteClient):
    """Retain actual response status alongside the existing bounded receipt."""
    def _request(self, *args, **kwargs):
        response = super()._request(*args, **kwargs)
        self._geps_status = response.status_code
        return response

    def get_bytes_with_receipt(self, *args, **kwargs):
        payload, receipt = super().get_bytes_with_receipt(*args, **kwargs)
        return payload, {**receipt, 'http_status': self._geps_status}


class _CompletedTransport:
    def __init__(self, client, clock, utcnow):
        self.client, self.clock, self.utcnow = client, clock, utcnow
        self.completed_monotonic = None

    def get_bytes_with_receipt(self, *args, **kwargs):
        payload, receipt = self.client.get_bytes_with_receipt(*args, **kwargs)
        if receipt.get('http_status') != 200:
            raise ValueError('GEPS delivery requires HTTP200 response identity')
        completed = datetime.fromisoformat(receipt['completed_at'])
        if completed.utcoffset() is None:
            raise ValueError('GEPS transport completion must be aware')
        self.completed_monotonic = self.clock() - max(0., (self.utcnow() - completed).total_seconds())
        return payload, receipt


def acquire_latest(selected, client, workspace, *, clock=time.monotonic, utcnow=lambda: datetime.now(UTC)):
    """One advertised reference request, then existing all-five exact-time reader.

    Selection is a WCS request parameter, not proof that the resulting TIFFs
    independently identify a producer run. Other coverages must advertise the
    same reference/valid time; no fallback reference is substituted.
    """
    selected = validate_selection(selected)
    transport = _CompletedTransport(client, clock, utcnow)
    discovery = _ReceiptClient(transport)
    with tempfile.TemporaryDirectory(prefix='geps-discover-', dir=workspace) as directory:
        layer = GeoMetClient(client=discovery, scratch_dir=Path(directory)).capabilities(SELECTED_REDUCTIONS[0].coverage_id)
        if not exact_advertised(layer.time, selected) or layer.reference_time is None:
            raise RunUnavailable('GEPS exact valid/reference time is not advertised')
        extent = layer.reference_time
        if extent.period is not None and extent.period.total_seconds() <= 0:
            raise RunUnavailable('GEPS reference extent cadence is invalid')
        references = extent.steps(limit=4097)
        if len(references) > 4096:
            raise RunUnavailable('GEPS reference inventory exceeds bound')
        eligible = [stamp for stamp in references if stamp <= selected]
        if not eligible:
            raise RunUnavailable('GEPS has no advertised reference at or before selection')
        key = GEPSRequestKey(max(eligible).astimezone(UTC), selected)
        entry = GEPSSelectedLoader(Path(directory), transport)(key)
        provenance = {**entry.provenance, 'discovery_receipts': discovery.receipts,
            'final_byte_monotonic': transport.completed_monotonic,
            'reference_selection': 'latest advertised reference of first supported coverage; revalidated for all five; requested_unverified'}
        return GEPSQueryEntry(key, entry.payload, provenance)


class GEPSLatestLoader:
    def __init__(self, workspace: Path, runner=run_bounded_process):
        self.workspace, self.runner = workspace, runner

    def __call__(self, selected):
        selected = validate_selection(selected)
        with tempfile.TemporaryDirectory(prefix='geps-latest-', dir=self.workspace) as directory:
            path = Path(directory) / 'result.zip'
            self.runner(command=[sys.executable, '-m', 'weather_api.geps_delivery_worker', '{output}'],
                stdin=selected.isoformat().encode(), destination=path, limits=GEPS_CHILD_LIMITS, timeout_seconds=180)
            with zipfile.ZipFile(path) as bundle:
                files = bundle.infolist()
                if len(files) != 2 or {f.filename for f in files} != {'result.json', 'artifact.zip'} or any(f.flag_bits & 1 or f.compress_type != zipfile.ZIP_STORED for f in files) or sum(f.file_size for f in files) > GEPS_OUTPUT_BYTES:
                    raise ValueError('GEPS delivery bundle violates bounded shape')
                metadata = json.loads(bundle.read('result.json'))
                entry = GEPSQueryEntry(GEPSRequestKey.from_dict(metadata['request']), bundle.read('artifact.zip'), metadata['provenance'])
            if entry.key.valid_time != selected:
                raise ValueError('GEPS child changed selected native time')
            entry.validate()
            validate_normalized_payload(entry, Path(directory))
            return entry


class GEPSPointService:
    """One crop, fixed final-byte expiry, same-time miss/refresh coalescing."""
    def __init__(self, workspace: Path, *, loader=None, clock=time.monotonic, utcnow=lambda: datetime.now(UTC)):
        self.workspace, self.loader = workspace, loader or GEPSLatestLoader(workspace)
        self.clock, self.utcnow = clock, utcnow
        self.lock = threading.Lock()
        self.cached = None
        self.inflight = None

    def query(self, selected, *, refresh=False):
        selected = validate_selection(selected)
        with self.lock:
            now = self.clock()
            if self.cached and self.cached[0] <= now:
                self.cached = None
            if self.cached and not refresh and self.cached[1].key.valid_time == selected:
                return copy.deepcopy(self.cached[1])
            if self.inflight:
                active, future = self.inflight
                if active != selected:
                    raise RunUnavailable('GEPS acquisition capacity is occupied')
                owner = False
            else:
                future = Future()
                self.inflight = (selected, future)
                owner = True
        if not owner:
            return copy.deepcopy(future.result(timeout=185))
        try:
            started = self.clock()
            entry = self.loader(selected)
            entry.validate()
            completed = entry.provenance.get('final_byte_monotonic')
            if entry.key.valid_time != selected or type(completed) not in (int, float) or not math.isfinite(completed) or not started <= completed <= self.clock():
                raise ValueError('GEPS selected identity/completion clock invalid')
            if self.clock() >= completed + TTL_SECONDS:
                raise RunUnavailable('GEPS expired during decode')
            if len(entry.payload) + len(json.dumps(entry.provenance).encode()) > GEPS_OUTPUT_BYTES:
                raise ValueError('GEPS cache entry exceeds byte ceiling')
            retained = copy.deepcopy(entry)
            with self.lock:
                self.cached = (completed + TTL_SECONDS, retained)
            future.set_result(retained)
            return copy.deepcopy(retained)
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.inflight = None

    def point_fields(self, latitude, longitude, selected, *, refresh=False):
        bounds = REPS_EVIDENCE_BOX
        if type(latitude) not in (int, float) or type(longitude) not in (int, float) or not math.isfinite(latitude) or not math.isfinite(longitude) or not bounds['south'] <= latitude <= bounds['north'] or not bounds['west'] <= longitude <= bounds['east']:
            raise ValueError('GEPS point outside verified output box')
        entry = self.query(selected, refresh=refresh)
        p = entry.provenance
        receipts = [*p['discovery_receipts'], *p['transport_receipts']]
        transfers = tuple(SourceTransferReceipt(url=r['url'], effective_url=r['url'], http_status=r['http_status'],
            request_headers={k:v for k,v in r['request_headers'].items() if k.lower() in {'accept','accept-encoding','user-agent'}}, response_headers={k:v for k,v in r['response_headers'].items() if k.lower() in {'date','content-length','content-type','etag','last-modified','cache-control','age','expires'}}, byte_size=r['byte_size'],
            sha256=r['sha256'], completed_at=r['completed_at']) for r in receipts)
        retrieved = max(r.completed_at for r in transfers)
        acquisition = SourceAcquisition(source_id=SOURCE_ID, product_id=PRODUCT_ID, provider_run_id=None,
            run_time=None, valid_time=entry.key.valid_time, retrieval_time=retrieved,
            expires_at=retrieved + timedelta(seconds=TTL_SECONDS), normalized_sha256=p['sha256'], transport_receipts=transfers)
        with tempfile.TemporaryDirectory(prefix='geps-point-', dir=self.workspace) as directory:
            path = Path(directory) / 'artifact.zip'
            path.write_bytes(entry.payload)
            with zarr.storage.ZipStore(str(path), mode='r') as store, xr.open_zarr(store, consolidated=False) as dataset:
                y = int(_cell_indices(np.array([latitude]), dataset.latitude.values)[0])
                x = int(_cell_indices(np.array([longitude]), dataset.longitude.values)[0])
                if x < 0 or y < 0:
                    raise RunUnavailable('GEPS point outside returned cell support')
                fields = []
                for reduction, statistic in MAPPED:
                    value = float(dataset[reduction.variable].values[0, y, x])
                    value = value if math.isfinite(value) else None
                    fields.append(EvidenceField(field=reduction.field, key=reduction.field, value=value, storage='available-not-stored',
                        provenance=Provenance(data_mode='live', evidence_class='retrieved', source_id=SOURCE_ID,
                            artifact_revision=p['sha256'], provider=p['producer'], product=p['product'], forecast_centre='ECCC',
                            run_time=None, valid_time=entry.key.valid_time, retrieval_time=retrieved,
                            vertical_level=str(catalogue.field(reduction.field).level), original_units=reduction.units,
                            normalized_units=reduction.units, native_resolution='0.5 degree source; requested EPSG:4326 output', native_crs='EPSG:4326',
                            quality=Quality(status='unknown', flags=['experimental_source_contract_pending', 'requested_unverified_run',
                                'server_resampled_method_unknown', 'native_temporal_window_unresolved', 'fifth_reduction_uncatalogued', '527_reductions_unresolved',
                                *(['native_missing'] if value is None else [])]), coverage=Coverage(status='partial'),
                            freshness=Freshness(status='unknown', age_seconds=max(0, int((self.utcnow()-retrieved).total_seconds())), threshold_seconds=None),
                            licence=p['licence'], attribution=p['attribution'], delivery_kind='reprocessed', source_display_primary=False,
                            intermediary='ECCC GeoMet WCS', intermediary_method='server_resampled_method_unknown', adapter_version='geps-point-v1',
                            source_acquisition=acquisition, native_variable=reduction.coverage_id,
                            sampled_latitude=float(dataset.latitude.values[y]), sampled_longitude=float(dataset.longitude.values[x]),
                            sample_method='rectilinear', run_stale=None, run_stale_reason='Requested WCS reference time is not independently verified producer-run identity',
                            ensemble=EnsembleProvenance(family=get_config(SOURCE_ID).ensemble.family, statistic=statistic,
                                computed_here=False, member_set=None, quantile=reduction.quantile))))
                return tuple(fields)


class GEPSReductionSource:
    source_id = SOURCE_ID
    product_id = PRODUCT_ID

    def __init__(self, factory):
        self.factory = factory

    def descriptors(self):
        return tuple(SourceCapability(source_id=SOURCE_ID, product_id=PRODUCT_ID, field=reduction.field,
            variants=[SourceVariant(kind='provider_statistic', statistic=statistic, quantile=reduction.quantile)],
            levels=[str(catalogue.field(reduction.field).level)], point=True, point_product=POINT_PRODUCT,
            native_series=False, run_selection='not_applicable',
            time_semantics='Exact advertised valid time; requested reference time remains unverified; native temporal window unresolved',
            coverage_description=RESIDUAL) for reduction, statistic in MAPPED)

    @observed_read
    def read_point(self, latitude, longitude, selected, *, run='latest', refresh=False):
        if run != 'latest':
            raise RunUnavailable('GEPS WCS does not establish selectable producer runs')
        return self.factory().point_fields(latitude, longitude, selected, refresh=refresh)

    def plan_series(self, start, end, *, run='latest'):
        return None


_SERVICE = None
_SERVICE_LOCK = threading.Lock()


def geps_point_service():
    """One process-local bounded crop cache; construction performs no I/O."""
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = GEPSPointService(Path(tempfile.gettempdir()))
        return _SERVICE
