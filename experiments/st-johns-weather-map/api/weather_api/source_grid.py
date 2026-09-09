"""Selected native WN3 frame delivery. Experiment; Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006."""
from collections import OrderedDict
from concurrent.futures import Future
from typing import Literal
import threading

from pydantic import AwareDatetime, Field, model_validator
from .models import Provenance
from .source_contract import ContractModel

SOURCE = 'google-weathernext-3-statistics'
FIELD = 'weathernext3_total_cloud_cover_mean'
REGION = (-55.,46.5,-51.,48.5)
REGIONS = {"avalon": REGION, "atlantic": (-70.,40.,-40.,55.)}
ACQUISITIONS = threading.BoundedSemaphore(2)

class SourceGridResponse(ContractModel):
    source_id: Literal['google-weathernext-3-statistics'] = SOURCE
    product: Literal['WeatherNext 3 local','WeatherNext 3 historical']
    field: Literal['weathernext3_total_cloud_cover_mean'] = FIELD
    selected_time: AwareDatetime
    native_time: AwareDatetime
    region: tuple[float,float,float,float] = REGION
    latitudes: list[float] = Field(min_length=2,max_length=302)
    longitudes: list[float] = Field(min_length=2,max_length=302)
    latitude_edges: list[float] = Field(min_length=3,max_length=303)
    longitude_edges: list[float] = Field(min_length=3,max_length=303)
    percentages: list[list[float | None]] = Field(max_length=302)
    statistic: Literal['ensemble_mean'] = 'ensemble_mean'
    provenance: Provenance

    @model_validator(mode='after')
    def native_frame(self):
        import math
        if self.region not in REGIONS.values() or self.native_time < self.selected_time:
            raise ValueError('grid selection identity')
        for axis,edges,lo,hi in ((self.latitudes,self.latitude_edges,self.region[1],self.region[3]),(self.longitudes,self.longitude_edges,self.region[0],self.region[2])):
            if len(edges)!=len(axis)+1 or not all(math.isfinite(n) for n in axis+edges):
                raise ValueError('grid coordinates')
            direction=1 if axis[1]>axis[0] else -1
            if any(abs((b-a)*direction-.1)>.00005 for a,b in zip(axis,axis[1:])):
                raise ValueError('grid spacing')
            if min(edges)>lo or max(edges)<hi or any((b-a)*direction<=0 for a,b in zip(edges,edges[1:])):
                raise ValueError('grid coverage')
            if any(abs(edges[i]-(axis[i-1]+axis[i])/2)>1e-9 for i in range(1,len(axis))):
                raise ValueError('grid shared boundaries')
            if any(not min(edges[i:i+2]) <= a <= max(edges[i:i+2]) for i,a in enumerate(axis)):
                raise ValueError('grid centres')
        if len(self.percentages)!=len(self.latitudes) or any(len(row)!=len(self.longitudes) for row in self.percentages):
            raise ValueError('grid shape')
        if any(v is not None and (not math.isfinite(v) or not 0<=v<=100) for row in self.percentages for v in row):
            raise ValueError('cloud percent')
        p=self.provenance
        if p.valid_time!=self.native_time or p.source_id!=SOURCE or not p.source_acquisition or p.source_acquisition.valid_time!=self.native_time:
            raise ValueError('grid provenance')
        if len(self.model_dump_json().encode())>2*1024**2:
            raise ValueError('grid response bound')
        return self

_lock=threading.Lock()
_entries=OrderedDict()
_inflight={}

def key(service,native,region="avalon"):
    return (service._scope_label,service.config.initialization,service.config.root_identity,native,FIELD,REGIONS[region])

def frame(service, selected, region="avalon"):
    if region not in REGIONS: raise ValueError("unsupported grid region")
    native=service.resolve_point_time(selected)
    identity=key(service,native,region)
    with _lock:
        entry=_entries.get(identity)
        if entry and entry[1] <= service._clock():
            del _entries[identity]; entry=None
        if entry:
            _entries.move_to_end(identity)
            return entry[0].model_copy(update={'selected_time':selected},deep=True)
        future=_inflight.get(identity)
        owner=future is None
        if owner:
            if len(_inflight)>=2: raise ValueError('grid acquisition concurrency bound')
            future=Future(); _inflight[identity]=future
    if not owner:
        return future.result().model_copy(update={'selected_time':selected},deep=True)
    try:
        from .weathernext_query import WeatherNextSelection
        selection=WeatherNextSelection(service.config.initialization,native,47.5,-53.,('total_cloud_cover_mean',))
        with ACQUISITIONS:
            payload=service._native_acquire(selection,regional=True if region=="avalon" else region)
        completed=service._utcnow()
        service._validate_time(selection,completed)
        evidence=service._point_evidence(payload,selection,completed,regional=True)
        grid=SourceGridResponse(product='WeatherNext 3 historical' if service._scope_label=='historical' else 'WeatherNext 3 local',
            selected_time=selected,native_time=native,provenance=evidence.provenance,**{**payload['reading']['grid'], 'region':REGIONS[region]})
        size=len(grid.model_dump_json().encode())
        with _lock:
            _entries[identity]=(grid,service._clock()+60,size)
            while len(_entries)>4 or sum(e[2] for e in _entries.values())>8*1024**2:
                _entries.popitem(last=False)
        future.set_result(grid)
        return grid.model_copy(deep=True)
    except Exception as error:
        future.set_exception(error)
        raise
    finally:
        with _lock: _inflight.pop(identity,None)

def cached_point(service,selection):
    if selection.fields!=('total_cloud_cover_mean',): return None
    grid = None
    for region,(west,south,east,north) in REGIONS.items():
        if not (south<=selection.latitude<=north and west<=selection.longitude<=east): continue
        with _lock:
            identity=key(service,selection.valid_time,region)
            entry=_entries.get(identity)
            future=_inflight.get(identity)
            grid=entry[0] if entry and entry[1]>service._clock() else None
        if grid is None and future is not None: grid=future.result()
        if grid is not None: break
    if grid is None: return None
    from .models import EvidenceField
    yi=min(range(len(grid.latitudes)),key=lambda i:abs(grid.latitudes[i]-selection.latitude))
    xi=min(range(len(grid.longitudes)),key=lambda i:abs(grid.longitudes[i]-selection.longitude))
    provenance=grid.provenance.model_copy(deep=True)
    provenance.sampled_latitude=grid.latitudes[yi]; provenance.sampled_longitude=grid.longitudes[xi]
    if grid.percentages[yi][xi] is None:
        provenance.quality.flags=list(set(provenance.quality.flags+['native_fill_mask']))
    else:
        provenance.quality.flags=[f for f in provenance.quality.flags if f!='native_fill_mask']
    return (EvidenceField(field=FIELD,key=FIELD,value=grid.percentages[yi][xi],storage='available-not-stored',provenance=provenance),)

def selected_service(product,selected):
    import os
    from .weathernext_configuration import weathernext_historical_service, weathernext_local_experimental_service
    internal=product=='WeatherNext 3 local'
    if os.environ.get('WEATHER_WEATHERNEXT_AUTO_RUNS')=='1':
        from .weathernext_configuration import load_local_experimental_configuration, _service, _local_service
        from .weathernext_runs import discover_configuration
        configured=load_local_experimental_configuration()
        with ACQUISITIONS:
            config=discover_configuration(selected,configured.gcloud_profile,internal=internal)
        return (_local_service if internal else _service)(config)
    return (weathernext_local_experimental_service if internal else weathernext_historical_service)()
