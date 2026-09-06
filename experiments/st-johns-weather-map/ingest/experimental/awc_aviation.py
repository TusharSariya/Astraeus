"""Bounded, nonpublishable native AWC aviation cache retention."""
from __future__ import annotations
import csv,gzip,hashlib
from datetime import datetime,timezone
from io import BytesIO,StringIO
from pathlib import Path
from typing import Any,Mapping
from ingest.contract import AdapterUnavailable,Artifact,DiscoveryBounds,FetchWindow,ResourceBounds,RunCandidate,RunResult
from ingest.http import MaxBytesExceeded,PoliteClient,RetriesExhausted
from ingest.manifest import declared_classes,unresolved_manifest_validation
UTC=timezone.utc; MAX_GZIP=2*1024*1024; MAX_DECODED=16*1024*1024; URLS={"pirep_airep":"https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz","sigmet":"https://aviationweather.gov/data/cache/airsigmets.cache.csv.gz"}
def _read(body:bytes)->tuple[list[str],int,int]:
 try:
  stream=gzip.GzipFile(fileobj=BytesIO(body)); chunks=[]; total=0
  while chunk:=stream.read(65536):
   total+=len(chunk)
   if total>MAX_DECODED: raise ValueError('decoded ceiling')
   chunks.append(chunk)
  raw=b''.join(chunks); rows=csv.reader(StringIO(raw.decode('utf-8'))); header=next(rows); count=0
  for row in rows:
   if len(row)!=len(header): raise ValueError('CSV row width')
   count+=1
 except Exception as e: raise AdapterUnavailable(f'awc aviation: invalid bounded gzip CSV: {e}') from e
 if not header: raise AdapterUnavailable('awc aviation: empty CSV header')
 return header,count,len(raw)
class AWCAviationNativeAdapter:
 source_id='awc-aviation-native'; adapter_version='awc-aviation-native-v1'
 def __init__(self,client:PoliteClient|None=None): self._client=client or PoliteClient()
 def discovery_bounds(self,_): return DiscoveryBounds(1)
 def resource_bounds(self,_,__): return ResourceBounds(2*MAX_GZIP,2*MAX_GZIP,2*MAX_GZIP,2*MAX_GZIP)
 def discover(self,_): return [RunCandidate('awc-current-cache',None,list(URLS.values()),{})]
 def fetch(self,candidate,window,workdir):
  gate=unresolved_manifest_validation(self.source_id,'native aviation fields have no accepted field, safety, manifest, or API contract'); paths=[]; artifacts=[]; completed=[];workdir.mkdir(parents=True,exist_ok=True)
  try:
   for kind,url in URLS.items():
    getattr_completion=getattr(self._client,'get_bytes_with_headers_completed',None)
    if callable(getattr_completion): body,h,done=getattr_completion(url,max_bytes=MAX_GZIP)
    else: body,h=self._client.get_bytes_with_headers(url,max_bytes=MAX_GZIP); done=datetime.now(UTC)
    header,n,decoded=_read(body);path=workdir/f'{kind}.csv.gz';paths.append(path);path.write_bytes(body);sha=hashlib.sha256(body).hexdigest(); artifacts.append(Artifact(kind,'application/gzip',path,{'source_id':self.source_id,'source_uri':url,'upstream_sha256':sha,'artifact_sha256':sha,'encoded_bytes':len(body),'decoded_bytes':decoded,'encoded_sha256':sha,'transport_completed_at':done.isoformat(),'response_headers':dict(h),'csv_header_positions':header,'record_count':n,'source_qc':{'status':'unknown'},'quality':gate.as_quality(),'operational':False,**declared_classes(['retrieved'])}));completed.append(done)
  except BaseException:
   for p in paths:p.unlink(missing_ok=True)
   raise
  return RunResult(self.source_id,candidate.provider_run_id,None,max(completed),gate.complete,gate.qc_passed,artifacts,None,'native CSV cache only; publication blocked')
