"""Optional Atlantic cloud layers; no scheduled or sequence acquisition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006 (experiment).
"""
from collections import OrderedDict
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
import hashlib
import json
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET

import httpx
from pydantic import AwareDatetime, Field
from ingest.adapters.goes_abi import GOES_S3_BASE, _KEY, parse_scan_stamp, MAX_ACMF_BYTES, MAX_ACHAF_BYTES
from ingest.contract import ATLANTIC_CONTEXT_BOUNDS
from ingest.isolation import ProcessAllocationLimits, run_bounded_process
from . import satellite, grids
from .source_contract import ContractModel

GOES = 'noaa-goes19-demand-cloud-mask'
RDPS = 'eccc-rdps-demand-total-cloud'
LayerId = Literal['noaa-goes19-demand-cloud-mask', 'eccc-rdps-demand-total-cloud']
ACQUISITIONS = threading.BoundedSemaphore(2)
COVERAGE = 'Actual source coverage only within 40-55 N, 70-40 W including water; outside native coverage is uncovered, not clear; no extrapolation.'
WHITE = 'Valid RGB white; alpha = native cloud percentage / 100 times layer opacity. Display mapping, not physical optical opacity. Missing RGBA (128,96,128,128), distinct from transparent zero.'
LIMITS = ProcessAllocationLimits(2*1024**3,16*1024**2,16384,16384,65536)

class DemandTimeFrame(ContractModel):
    valid_time: AwareDatetime
    run_time: AwareDatetime

class DemandLayerTimes(ContractModel):
    layer_id: LayerId
    start: AwareDatetime
    end: AwareDatetime
    expires_at: AwareDatetime
    frames: list[DemandTimeFrame] = Field(max_length=1200)
    basis: Literal['advertised_native_times'] = 'advertised_native_times'
    notices: list[str]

@dataclass(frozen=True)
class MaskFrame:
    payload: bytes
    native_time: datetime
    retrieved_at: datetime
    digest: str
    receipts: tuple

class MaskService:
    def __init__(self, client=None, *, clock=time.monotonic, now=lambda:datetime.now(UTC), decoder=None):
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)
        self.clock, self.now = clock, now
        self.decoder = decoder or self.decode
        self.lock = threading.Lock()
        self.pages, self.frames, self.pending = OrderedDict(), OrderedDict(), {}
        self.page_pending = {}

    def fetch(self, url, cap, deadline):
        if self.clock()>=deadline:raise ValueError('GOES deadline exceeded')
        body=bytearray()
        with self.client.stream('GET',url,headers={'Accept-Encoding':'identity'},follow_redirects=False,timeout=max(.1,min(20,deadline-self.clock()))) as response:
            response.raise_for_status()
            if response.status_code != 200 or response.headers.get('content-encoding','identity')!='identity': raise ValueError('GOES transport refused')
            for chunk in response.iter_bytes():
                if self.clock()>=deadline or len(body)+len(chunk)>cap: raise ValueError('GOES transfer bound')
                body.extend(chunk)
        payload=bytes(body)
        return payload, {'url':url,'byte_size':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'completed_at':self.now().isoformat()}

    def listing(self, product, day, deadline):
        identity=(product,day.date())
        with self.lock:
            future=self.page_pending.get(identity);owner=future is None
            if owner:
                if len(self.page_pending)>=2:raise ValueError('GOES inventory concurrency bound')
                future=Future();self.page_pending[identity]=future
        if not owner:return future.result()
        try:
            value=self._listing(product,day,deadline);future.set_result(value);return value
        except Exception as error:
            future.set_exception(error);raise
        finally:
            with self.lock:self.page_pending.pop(identity,None)

    def _listing(self, product, day, deadline):
        prefix=f'{product}/{day.year}/{day.timetuple().tm_yday:03d}/'
        with self.lock:
            old=self.pages.get(prefix)
            if old and old[0]>self.clock(): return old[1]
        from urllib.parse import urlencode
        url=GOES_S3_BASE+'/?'+urlencode({'list-type':2,'max-keys':1000,'prefix':prefix})
        body,_=self.fetch(url,1024**2,deadline)
        root=ET.fromstring(body)
        def local(tag):return tag.rsplit('}',1)[-1]
        if any(local(n.tag)=='IsTruncated' and n.text=='true' for n in root.iter()): raise ValueError('GOES daily listing truncated')
        keys={}
        for node in root.iter():
            if local(node.tag)!='Key' or not node.text or not node.text.startswith(prefix):continue
            match=_KEY.search(node.text)
            if match and 'ABI-L2-'+match[1]==product:
                stamp=parse_scan_stamp(match[2])
                if stamp<=self.now(): keys[stamp]=max(keys.get(stamp,''),node.text)
        with self.lock:
            self.pages[prefix]=(self.clock()+60,keys)
            self.pages.move_to_end(prefix)
            while len(self.pages)>16:self.pages.popitem(last=False)
        return keys

    def inventory(self,start,end):
        with ACQUISITIONS:return self._inventory(start,end)

    def _inventory(self,start,end):
        deadline=self.clock()+30
        end=min(end,self.now());start=max(start,self.now()-timedelta(days=7))
        keys={};day=start.replace(hour=0,minute=0,second=0,microsecond=0)
        while day<=end:
            keys.update(self.listing('ABI-L2-ACMF',day,deadline))
            day+=timedelta(days=1)
        return {t:k for t,k in keys.items() if start<=t<=end}

    def selected(self,selected):
        if selected.tzinfo is None:raise ValueError('GOES aware time required')
        deadline=self.clock()+90
        keys=self.inventory(selected-timedelta(seconds=300), selected+timedelta(seconds=300))
        if not keys:raise grids.FrameNotStored('No actual GOES scan within 300 seconds; choose Latest available scan')
        stamp=min(keys,key=lambda t:(abs((t-selected).total_seconds()),t))
        key=keys[stamp]
        with self.lock:
            old=self.frames.get(key)
            if old and old[0]>self.clock():
                self.frames.move_to_end(key);return old[1]
            self.frames.pop(key,None)
            future=self.pending.get(key);owner=future is None
            if owner:
                if len(self.pending)>=2:raise ValueError('GOES concurrent acquisition bound')
                future=Future();self.pending[key]=future
        if not owner:return future.result()
        try:
            with ACQUISITIONS:
                try:height_keys=self.listing('ABI-L2-ACHAF',stamp,deadline)
                except (httpx.HTTPError,ValueError):height_keys={}
                # Exact native scan start pairing, never nearest unrelated height.
                height_key=height_keys.get(stamp)
                body,receipt=self.fetch(GOES_S3_BASE+'/'+key,MAX_ACMF_BYTES,deadline)
                height=None;receipts=[receipt]
                if height_key:
                    try:
                        height,hr=self.fetch(GOES_S3_BASE+'/'+height_key,MAX_ACHAF_BYTES,deadline);receipts.append(hr)
                    except (httpx.HTTPError,ValueError):height=None
                payload=self.decoder(body,height,_KEY.search(key)[2],max(.1,deadline-self.clock()))
                if self.clock()>deadline or not payload or len(payload)>16*1024**2:raise ValueError('GOES cropped output/deadline bound')
                frame=MaskFrame(payload,stamp,self.now(),hashlib.sha256(payload).hexdigest(),tuple(receipts))
            with self.lock:
                self.frames[key]=(self.clock()+60,frame)
                while len(self.frames)>4 or sum(len(v[1].payload) for v in self.frames.values())>64*1024**2:self.frames.popitem(last=False)
            future.set_result(frame);return frame
        except Exception as error:
            future.set_exception(error);raise
        finally:
            with self.lock:self.pending.pop(key,None)

    @staticmethod
    def decode(body,height,stamp,timeout):
        with tempfile.TemporaryDirectory(prefix='goes-mask-demand-') as directory:
            root=Path(directory);mask=root/'mask.nc';mask.write_bytes(body)
            hp=root/'height.nc'
            if height is not None:hp.write_bytes(height)
            output=root/'crop.zip'
            run_bounded_process(command=[sys.executable,str(Path(__file__).with_name('cloud_mask_worker.py')),'{output}'],
                stdin=json.dumps({'mask':str(mask),'height':str(hp) if height is not None else None,'stamp':stamp}).encode(),
                destination=output,limits=LIMITS,timeout_seconds=timeout)
            return output.read_bytes()

@lru_cache(maxsize=1)
def mask_service():return MaskService()

def layers(model):
    from .layer_identity import imagery,mappings
    return [model(**mappings([(source,field)]),id=id,title=title,kind='raster',field=field,product=product,
        units=units,evidence_class='retrieved',family='cloud_cover',semantics=semantics+' '+COVERAGE,times=[],cadence_seconds=cadence,
        staleness_tolerance_seconds=cadence//2,z_index=0,evidence_basis='demand_query',group=group,
        raster_available=True,legend_available=True,
        imagery_availability=imagery('unknown',datetime.now(UTC),'on_demand','Selected native frame only; metadata inventory does not establish downloaded values'))
        for id,source,field,title,product,units,semantics,cadence,group in (
            (GOES,'noaa-goes-east','cloud_mask','GOES-19 observed cloud mask','GOES-19','cloud-mask class / probability 0-1',satellite.semantics(),600,'satellite'),
            (RDPS,'eccc-rdps','total_cloud_opacity','RDPS total cloud · white opacity','RDPS','percent',WHITE,3600,'rendered_grid'))]

def inventory(layer_id,start,end):
    now=datetime.now(UTC)
    if start.tzinfo is None or end.tzinfo is None or not start<end<=start+timedelta(days=15):raise ValueError('Inventory requires aware window at most 15 days')
    notices=['Advertised native times only; science frames download only when selected. '+COVERAGE]
    frames=[]
    try:
        if layer_id==GOES:
            frames=[DemandTimeFrame(valid_time=t,run_time=t) for t in sorted(mask_service().inventory(start,end))]
            notices.append('Actual observed scans within the past week only; no future observations.')
        elif layer_id==RDPS:
            from .rdps_query import rdps_query_coordinator
            with ACQUISITIONS:
                candidates=rdps_query_coordinator().run_inventory()
            by_time={}
            for c in candidates:
                for lead in c.detail.get('available_hours',()):
                    t=c.run_time+timedelta(hours=int(lead))
                    if 0<=int(lead)<85 and start<=t<=end and (t not in by_time or c.run_time>by_time[t]):by_time[t]=c.run_time
            frames=[DemandTimeFrame(valid_time=t,run_time=r) for t,r in sorted(by_time.items())]
        else:raise ValueError('Unknown cloud layer')
    except Exception as error:
        notices.append(f'Native inventory unavailable: {type(error).__name__}; no times inferred.')
    return DemandLayerTimes(layer_id=layer_id,start=start,end=end,expires_at=now+timedelta(seconds=60),frames=frames,notices=notices)

def white_color(values,inside):
    import numpy as np
    valid=inside & np.isfinite(values) & (values>=0) & (values<=100)
    rgba=np.zeros((*values.shape,4),dtype='uint8')
    rgba[valid,:3]=255
    rgba[valid,3]=np.rint(values[valid]/100*255).astype('uint8')
    rgba[inside & ~valid]=satellite.INVALID_RGBA
    return rgba

def raster(layer_id,selected,*,bounds,width,height,crs):
    import xarray as xr
    import zarr
    with tempfile.TemporaryDirectory(prefix='cloud-render-') as directory:
        path=Path(directory)/'frame.zip'
        if layer_id==GOES:
            entry=mask_service().selected(selected)
            source,field='noaa-goes-east','cloud_class'
        else:
            from .rdps_query import rdps_query_coordinator
            with ACQUISITIONS:entry=rdps_query_coordinator().query(selected,fields=('total_cloud_opacity',),region='atlantic')
            source,field='eccc-rdps','total_cloud_opacity'
        path.write_bytes(entry.payload)
        with zarr.storage.ZipStore(str(path),mode='r') as store:
            with xr.open_zarr(store,consolidated=False) as ds:
                if layer_id==GOES:
                    artifact=SimpleNamespace(source_id=source,logical_name='cloud_mask',provenance=dict(ds.attrs))
                    shim=SimpleNamespace(current=lambda:[artifact],open=lambda _:ds)
                    image=satellite.render_satellite(shim,bounds=bounds,width=width,height=height,crs=crs,valid_time=entry.native_time)
                    headers=image.headers()
                else:
                    frame=ds[field].isel(valid_time=0)
                    lat,lon=ds.latitude,ds.longitude
                    sample=grids.sample_field_curvilinear if lat.ndim==2 else grids.sample_field
                    values,inside=sample(frame.values,lat.values,lon.values,bounds=bounds,width=width,height=height,crs=crs)
                    ys,xs=grids._pixel_centres(**bounds,width=width,height=height,crs=crs)
                    inside &= (ys[:,None]>=40)&(ys[:,None]<=55)&(xs[None,:]>=-70)&(xs[None,:]<=-40)
                    terms=grids._registry_terms(source)
                    image=grids.RenderedGridImage(grids.encode_png(white_color(values,inside)),'image/png',entry.valid_time,entry.run_time,crs,'percent',source,'RDPS',*terms,sample_method='curvilinear_nearest_cell' if lat.ndim==2 else 'rectilinear')
                    headers=image.headers(layer_id=layer_id)
                    headers['X-Weather-Colormap']=WHITE
                    headers['X-Weather-Derivation-Version']='rdps-white-opacity-v1'
                    headers['X-Weather-Render-Semantics']='Native nearest rotated-grid cell within half-cell diagonal; no interpolation. '+WHITE+' '+COVERAGE
                    headers['X-Weather-Derivation']='weather_api.grids native sampling; weather_api.demand_clouds white opacity v1. '+WHITE
        retrieved=entry.retrieved_at if layer_id==GOES else entry.fetched_at
        headers.update({'X-Weather-Layer-Id':layer_id,'X-Weather-Evidence-Basis':'demand_query','X-Weather-Coverage':COVERAGE,
            'X-Weather-Retrieval-Time':retrieved.isoformat(),'X-Weather-Content-Digest':entry.digest if layer_id==GOES else entry.content_digest})
        headers['X-Weather-Upstream-Completion-Time']=retrieved.isoformat()
        headers['X-Weather-Transport-Receipts']=json.dumps(entry.receipts if layer_id==GOES else entry.provenance.get('transport_receipts',()),separators=(',',':'),default=str)
        if layer_id==GOES:headers['X-Weather-Parallax']=str(ds.attrs.get('cloud_top_height_used','unknown'))+'; '+satellite.PARALLAX_SENTENCE
        return image.payload,headers


def white_legend():
    import numpy as np
    values=np.tile(np.linspace(0,100,220),(26,1))
    values[:,-26:]=np.nan
    rgba=white_color(values,np.ones(values.shape,dtype=bool))
    alpha=rgba[...,3:4]/255
    rgba[...,:3]=np.rint(rgba[...,:3]*alpha+176*(1-alpha)).astype('uint8')
    rgba[...,3]=255
    return grids.encode_png(rgba)
