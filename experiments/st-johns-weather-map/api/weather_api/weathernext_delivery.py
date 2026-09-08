"""Scoped WeatherNext temperature mean point delivery, isolated experiment.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006. Canonical temperature_2m,
provider ensemble_mean, no member fabrication, no production registration.
"""
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
import threading
import time
from urllib.parse import quote, urlencode

from ingest.adapters.weathernext3_statistics import PRODUCT, SOURCE_ID
from ingest.derive.registry import ENSEMBLE_MEAN
from registry.weathernext import SURFACE_FIELDS, BY_KEY, BY_NATIVE
from .models import Coverage, EnsembleProvenance, EvidenceField, Freshness, Provenance, Quality
from .source_contract import SourceAcquisition, SourceCapability, SourceConfiguration, SourceTransferReceipt, SourceVariant
from .weathernext_gcs import GcloudProfileToken, runtime_token_provider
from .weathernext_gcs_bridge import AccountedGCSTransport, read_historical_point
from .weathernext_native import BUCKET, ObjectIdentity
from .weathernext_query import HISTORICAL_DELAY, WeatherNextSelection

NATIVE_FIELD='temperature_2m_mean'
FIELD='temperature_2m'
TTL=60
MAX_ENTRIES=8
MAX_CACHE_BYTES=256*1024
MAX_ACQUISITION_BYTES=64*1024**2


class WeatherNextDeliveryUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class HistoricalConfiguration:
    initialization: datetime
    root_identity: ObjectIdentity
    gcloud_profile: str

    def __post_init__(self):
        GcloudProfileToken(self.gcloud_profile)  # Validate name without authentication.
        if self.initialization.tzinfo is None:
            raise ValueError('WeatherNext initialization requires UTC offset')
        stamp=self.initialization.astimezone(UTC)
        expected=f'{PRODUCT}/zarr/2026_to_present/{stamp:%Y%m%d_%H}hr_01_preds/predictions.zarr/zarr.json'
        if (stamp.minute or stamp.second or stamp.microsecond or self.root_identity.bucket!=BUCKET
                or self.root_identity.name!=expected or not self.root_identity.generation.isdecimal()
                or not self.root_identity.etag or not 0<self.root_identity.size<=256*1024):
            raise ValueError('WeatherNext explicit root identity')
        object.__setattr__(self,'initialization',stamp)

    @property
    def run_id(self):
        return self.root_identity.name.split('/')[-3]


@dataclass(frozen=True)
class LocalExperimentalConfiguration(HistoricalConfiguration):
    """Explicit pinned run/profile for the separately authorized internal scope."""


def _time(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None: raise ValueError('native timestamp lacks offset')
    return result.astimezone(UTC)


def point_evidence(payload, selection, configuration, *, completed_at, data_mode='live', scope='historical'):
    """Validate bridge identity before canonical K-to-degC representation."""
    if scope not in ('historical', 'internal_experimental_forecast'):
        raise ValueError('WeatherNext evidence scope')
    local = scope == 'internal_experimental_forecast'
    raw=payload['reading']
    receipt=payload['receipt']
    if local and receipt.get('acquisition_scope') != 'internal_experimental_forecast':
        raise ValueError('WeatherNext local acquisition scope')
    if (_time(raw['initialization'])!=selection.initialization or _time(raw['valid_time'])!=selection.valid_time
            or raw.get('member') is not None or raw.get('pressure_level') is not None
            or len(raw['values'])!=1):
        raise ValueError('native point identity')
    native=raw['values'][0]
    mapping=BY_NATIVE[selection.fields[0]]
    if (native['field']!=mapping.native or native['statistic']!=mapping.native.rsplit('_',1)[1] or native['unit']!=mapping.native_unit or native['grid']!=mapping.grid):
        raise ValueError('native temperature statistic identity')
    lat,lon=native['latitude'],native['longitude']
    if (not all(isinstance(n,(int,float)) and math.isfinite(n) for n in (lat,lon)) or not -90<=lat<=90 or not -180<=lon<=180
            or abs(lat-selection.latitude)>(.02505 if mapping.grid=='0p05' else .05005) or abs((lon-selection.longitude+180)%360-180)>(.02505 if mapping.grid=='0p05' else .05005)):
        raise ValueError('native point footprint')
    value=native['value']
    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
        raise ValueError('native value')
    if value is not None and mapping.family == 'cloud_cover' and not 0 <= value <= 1:
        raise ValueError('native cloud fraction range')
    identities=[ObjectIdentity(**item) for item in raw['objects']]
    if not identities or identities[0]!=configuration.root_identity or len(identities)>7:
        raise ValueError('root receipt identity')
    by_name={item.name:item for item in identities}
    prefix=configuration.root_identity.name.rsplit('/',1)[0]+'/'
    if (len(by_name)!=len(identities) or any(item.bucket!=BUCKET or not item.name.startswith(prefix)
        or not item.generation.isdecimal() or not item.etag or type(item.size) is not int or item.size<=0 for item in identities)
        or not any(item.name.startswith(prefix+mapping.native+'/c/') for item in identities)):
        raise ValueError('native object receipt')
    if sum(item.size for item in identities)!=raw['received_bytes'] or raw['received_bytes']>MAX_ACQUISITION_BYTES:
        raise ValueError('native receipt byte bounds')
    operations=receipt['http_objects']
    if not 0<len(operations)<=12 or receipt['http_response_bytes']>MAX_ACQUISITION_BYTES:
        raise ValueError('HTTP receipt bounds')
    if any(o['kind'] not in ('media','metadata') for o in operations) or len({(o['kind'],o['name']) for o in operations})!=len(operations):
        raise ValueError('ambiguous HTTP operation receipt')
    media={o['name']:o for o in operations if o['kind']=='media'}
    if set(media)!=set(by_name): raise ValueError('incomplete media receipt')
    transfers=[]
    for item in operations:
        identity=by_name[item['name']]
        params={'alt':'media','generation':identity.generation} if item['kind']=='media' else {'fields':'bucket,name,generation,etag,size'}
        if item['kind']=='media' and (item['generation']!=identity.generation or item['bytes']!=identity.size):
            raise ValueError('HTTP media identity')
        url=f'https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{quote(identity.name,safe="")}?{urlencode(params)}'
        transfers.append(SourceTransferReceipt(url=url,effective_url=url,http_status=200,request_headers={'Accept-Encoding':'identity'},
             response_headers={},byte_size=item['bytes'],sha256=item['sha256'],completed_at=_time(item['completed_at'])))
    if sum(o.byte_size for o in transfers)!=receipt['http_response_bytes']:
        raise ValueError('HTTP total byte mismatch')
    digest=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    acquisition=SourceAcquisition(source_id=SOURCE_ID,product_id=PRODUCT,provider_run_id=configuration.run_id,
        run_time=selection.initialization,valid_time=selection.valid_time,retrieval_time=completed_at,
        expires_at=completed_at+timedelta(seconds=TTL),normalized_sha256=digest,transport_receipts=tuple(transfers))
    flags=[('internal_experimental_forecast' if local else 'historical_forecast'),'provider_qc_not_supplied']+(['native_fill_mask'] if value is None else [])
    return EvidenceField(field=mapping.key,key=mapping.key,value=None if value is None else value*mapping.scale+mapping.offset,storage='available-not-stored',
        provenance=Provenance(data_mode=data_mode,evidence_class='retrieved',source_id=SOURCE_ID,provider='Google',
            product=PRODUCT,native_variable=mapping.native,forecast_centre='Google',artifact_revision=digest,
            run_time=selection.initialization,valid_time=selection.valid_time,retrieval_time=completed_at,
            vertical_level=mapping.level,original_units=mapping.native_unit,normalized_units=mapping.unit,native_resolution='0.05 degree' if mapping.grid=='0p05' else '0.1 degree',native_crs='EPSG:4326',
            quality=Quality(status='unknown',flags=flags),coverage=Coverage(status='partial'),
            freshness=Freshness(status='unknown',age_seconds=0,threshold_seconds=None),
            licence=('GDM Real-Time Weather Forecasting Experimental Data Terms of Use (2026-09-03), '
                     'section 2(a) internal use; historical data transitions to CC BY 4.0 under the provider terms; '
                     'https://storage.googleapis.com/weathernext-public/terms-of-use.pdf' if local else
                     'WeatherNext historical data terms; conservative valid-time age greater than 48 hours'),
            attribution='WeatherNext data provided by Google',delivery_kind='published_cell',source_display_primary=False,
            adapter_version='weathernext-local-temperature-v1' if local else 'weathernext-historical-temperature-v1',source_acquisition=acquisition,
            sampled_latitude=lat,sampled_longitude=lon,sample_method='rectilinear',run_stale=None if local else True,
            run_stale_reason='Pinned experimental run; freshness is not established' if local else 'Explicit historical run; not a current forecast',
            ensemble=EnsembleProvenance(family='google-weathernext-3',statistic=mapping.statistic,quantile=mapping.quantile,computed_here=False,member_set=None)))


class WeatherNextHistoricalDelivery:
    source_id=SOURCE_ID
    product_id=PRODUCT
    _scope_label='historical'

    def __init__(self, configuration: HistoricalConfiguration, *, acquire=None, clock=time.monotonic,
                 utcnow=lambda:datetime.now(UTC), data_mode='live'):
        self.config=configuration
        self._clock,self._utcnow,self._data_mode=clock,utcnow,data_mode
        self._acquire=acquire or self._native_acquire
        self._lock=threading.Lock()
        self._entries=OrderedDict()
        self._inflight={}
        self._failures=OrderedDict()

    def _native_acquire(self,selection):
        transport=AccountedGCSTransport(token_provider=runtime_token_provider(self.config.gcloud_profile),max_received_bytes=MAX_ACQUISITION_BYTES)
        return read_historical_point(selection,root_identity=self.config.root_identity,now=self._utcnow(),transport=transport,
                                     max_received_bytes=MAX_ACQUISITION_BYTES)

    def descriptors(self):
        return surface_descriptors('WeatherNext 3 historical')

    def resolve_point_time(self, selected):
        # The source's hourly convention only proposes a candidate; the native
        # coordinate reader verifies its existence before returning evidence.
        native = selected.replace(minute=0, second=0, microsecond=0)
        if native < selected:
            native += timedelta(hours=1)
        WeatherNextSelection(self.config.initialization,native,0,0,(NATIVE_FIELD,))
        self._validate_time(WeatherNextSelection(self.config.initialization,native,0,0,(NATIVE_FIELD,)),self._utcnow())
        return native

    def configuration(self):
        return SourceConfiguration(state='ready',reason='Explicit historical root and existing gcloud profile selected; runtime authentication and object access are assessed on acquisition')

    def _validate_time(self, selection, now):
        if selection.valid_time >= now-HISTORICAL_DELAY:
            raise ValueError('historical gate')

    def _point_evidence(self, payload, selection, completed):
        return point_evidence(payload,selection,self.config,completed_at=completed,data_mode=self._data_mode)

    def plan_series(self,*args,**kwargs): return None

    def read_point(self,latitude,longitude,selected,*,run='latest',refresh=False,field=FIELD):
        if run not in ('latest',self.config.run_id): raise WeatherNextDeliveryUnavailable(f'WeatherNext configured {self._scope_label} run only')
        try:
            selection=WeatherNextSelection(self.config.initialization,selected,latitude,longitude,(BY_KEY[field].native,))
            self._validate_time(selection,self._utcnow())
        except Exception:
            raise WeatherNextDeliveryUnavailable(f'WeatherNext {self._scope_label} selection unavailable') from None
        with self._lock:
            entry=self._entries.get(selection)
            if entry and entry[1]<=self._clock():
                del self._entries[selection]
                entry=None
            if entry and not refresh:
                self._entries.move_to_end(selection)
                return (entry[0].model_copy(deep=True),)
            failed=self._failures.get(selection)
            if failed and failed[0]>self._clock():
                error=WeatherNextDeliveryUnavailable('WeatherNext acquisition retry cooldown')
                error.http_status=failed[1]
                raise error
            future=self._inflight.get(selection)
            owner=future is None
            if owner:
                if len(self._inflight)>=2: raise WeatherNextDeliveryUnavailable('WeatherNext acquisition concurrency bound')
                future=Future()
                self._inflight[selection]=future
        if not owner: return (future.result().model_copy(deep=True),)
        try:
            payload=self._acquire(selection)
            completed=self._utcnow()
            self._validate_time(selection,completed)
            evidence=self._point_evidence(payload,selection,completed)
            size=len(evidence.model_dump_json().encode())
            if size>MAX_CACHE_BYTES: raise ValueError('cache bytes')
            with self._lock:
                previous=self._entries.get(selection)
                if previous and previous[1]>self._clock() and previous[0].provenance.artifact_revision==evidence.provenance.artifact_revision:
                    evidence=previous[0]
                    self._entries[selection]=previous
                else:
                    self._entries[selection]=(evidence,self._clock()+TTL,size)
                self._entries.move_to_end(selection)
                while len(self._entries)>MAX_ENTRIES or sum(e[2] for e in self._entries.values())>MAX_CACHE_BYTES:
                    self._entries.popitem(last=False)
                self._failures.pop(selection,None)
            future.set_result(evidence)
            return (evidence.model_copy(deep=True),)
        except Exception as cause:
            error=WeatherNextDeliveryUnavailable(f'WeatherNext bounded {self._scope_label} acquisition failed')
            error.http_status=getattr(cause,'http_status',None) if getattr(cause,'http_status',None) in (401,403) else None
            with self._lock:
                self._failures[selection]=(self._clock()+5,error.http_status)
                self._failures.move_to_end(selection)
                while len(self._failures)>MAX_ENTRIES:self._failures.popitem(last=False)
            future.set_exception(error)
            raise error from None
        finally:
            with self._lock:self._inflight.pop(selection,None)


class WeatherNextLocalExperimentalDelivery(WeatherNextHistoricalDelivery):
    """Separate cache and explicit local scope; never changes historical defaults.

    This scope is authorized for internal use under the September 3, 2026
    provider terms. It does not authorize public redistribution or establish
    current-run freshness, scientific quality, or operational admission.
    """
    _scope_label='local experimental'

    def _validate_time(self, selection, now):
        if now.tzinfo is None or now.utcoffset() is None or selection.initialization > now:
            raise ValueError('local initialization must not be in the future')

    def _native_acquire(self, selection):
        # Lazy import leaves the historical path independent of this bridge.
        from .weathernext_gcs_bridge import read_local_experimental_point
        transport=AccountedGCSTransport(token_provider=runtime_token_provider(self.config.gcloud_profile),max_received_bytes=MAX_ACQUISITION_BYTES)
        return read_local_experimental_point(selection,root_identity=self.config.root_identity,
            now=self._utcnow(),transport=transport,max_received_bytes=MAX_ACQUISITION_BYTES)

    def _point_evidence(self, payload, selection, completed):
        return point_evidence(payload,selection,self.config,completed_at=completed,
            data_mode=self._data_mode,scope='internal_experimental_forecast')

    def descriptors(self):
        return surface_descriptors('WeatherNext 3 local')

    def configuration(self):
        return SourceConfiguration(state='ready',reason='Explicit local experimental root and existing gcloud profile selected; runtime authentication and object access are assessed on acquisition')


def surface_descriptors(product):
    return tuple(SourceCapability(source_id=SOURCE_ID,product_id=PRODUCT,field=m.key,
        variants=[SourceVariant(kind='provider_statistic',statistic=m.statistic,quantile=m.quantile)],
        levels=[m.level],point=True,point_product=product,native_series=False,
        point_time_kind='forecast',directional_time_selection=True,run_selection='not_applicable',
        time_semantics='Exact native hourly lead, or next native hour under directional selection, within configured run',
        coverage_description='Bounded internal surface statistics point; native coordinate and mask verified on read; no latest-run freshness promise')
        for m in SURFACE_FIELDS)


def directional_surface_point(latitude,longitude,selected,product,*,field=None,member=None,statistic=None,quantile=None,threshold=None,comparison=None):
    from fastapi import HTTPException
    from .app import configured_mode, LIVE_MODE
    from .models import PointResponse, Selection
    from .weathernext_configuration import weathernext_historical_service, weathernext_local_experimental_service
    mapping=BY_KEY.get(field or FIELD)
    if (mapping is None or member is not None or threshold is not None or comparison is not None
            or statistic not in (None,mapping.statistic) or quantile != mapping.quantile):
        raise HTTPException(status_code=422,detail='Select an exact published WeatherNext 3 surface field/statistic; raw members are unsupported')
    fields=[]
    reason='WeatherNext 3 requires live mode'
    if configured_mode()==LIVE_MODE:
        try:
            factory=weathernext_local_experimental_service if product.upper()=='WEATHERNEXT 3 LOCAL' else weathernext_historical_service
            import os
            if os.environ.get('WEATHER_WEATHERNEXT_AUTO_RUNS') == '1':
                from .weathernext_configuration import load_local_experimental_configuration, _service, _local_service
                from .weathernext_runs import discover_configuration
                configured=load_local_experimental_configuration()
                internal=product.upper()=='WEATHERNEXT 3 LOCAL'
                configuration=discover_configuration(selected,configured.gcloud_profile,internal=internal)
                service=(_local_service if internal else _service)(configuration)
            else:
                service=factory()
            native=service.resolve_point_time(selected)
            fields=list(service.read_point(latitude,longitude,native,field=mapping.key))
            if any(f.provenance.valid_time!=native or f.provenance.valid_time<selected for f in fields):
                raise ValueError('native time identity')
            reason='Native forecast at or after selection within the configured WeatherNext 3 run'
        except Exception as error:
            fields=[]
            reason='Credentials required for WeatherNext 3' if getattr(error,'http_status',None) in (401,403) else 'WeatherNext 3 source unavailable for selected native time; check configured run and runtime access'
    return PointResponse(data_mode='live' if any(f.value is not None for f in fields) else 'unavailable',
        latitude=latitude,longitude=longitude,valid_time=selected,time_selection='directional',fields=fields,
        selection=Selection(mode='evidence_only',selected_source_id=None,selected_product_id=None,
            badge='Point data' if fields else 'Point data unavailable',reason=reason),
        notices=['Internal experimental WeatherNext 3; selected instant and native valid time retained separately; provider statistics, no member reconstruction'])
