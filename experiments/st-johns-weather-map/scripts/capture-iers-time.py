#!/usr/bin/env python3
"""Replay retained exact IERS/NAIF HTTP bodies into immutable API artifacts."""
from __future__ import annotations
import argparse, hashlib, importlib, json, math, os, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"api")]
from ingest.contract import FetchWindow
from ingest.experimental.iers_time import IERSBulletinAAdapter,IERSLeapSecondAdapter,NAIFLeapSecondsKernelAdapter

UTC=timezone.utc
class FileClient:
 def __init__(self,path,identity_path=None): self.path,self.identity_path=path,identity_path
 def download(self,url,path,*,max_bytes):
  selected=self.identity_path if url.endswith("aareadme.txt") and self.identity_path is not None else self.path
  body=selected.read_bytes()
  if len(body)>max_bytes: raise RuntimeError(f"retained payload exceeds {max_bytes} bytes")
  path.write_bytes(body)
def stamp(value): return datetime.fromisoformat(value.strip().replace("Z","+00:00")).astimezone(UTC)

def main():
 p=argparse.ArgumentParser();p.add_argument("capture",type=Path);p.add_argument("output",type=Path);args=p.parse_args()
 window=FetchWindow(datetime(2026,9,6,tzinfo=UTC),back_hours=5*24,forward_hours=2*24)
 specs=[(IERSBulletinAAdapter,"finals2000A.all",None),(IERSLeapSecondAdapter,"Leap_Second.dat",None),(NAIFLeapSecondsKernelAdapter,"naif0012.tls","naif-lsk-aareadme.txt")]
 args.output.mkdir(parents=True,exist_ok=True); receipt=[]; records=[]; raw_rows={}
 for cls,name,identity_name in specs:
  raw=args.capture/name; identity=args.capture/identity_name if identity_name else None
  capture_name=identity_name or name
  captured=stamp((args.capture/f"{capture_name}.captured_at").read_text())
  adapter=cls(client=FileClient(raw,identity),clock=lambda captured=captured:captured)
  candidate=adapter.discover(window)[0]; result=adapter.fetch(candidate,window,args.output); artifact=result.artifacts[0]
  raw_rows[adapter.source_id]=candidate.detail["rows"]
  records.append(SimpleNamespace(revision_id=f"live-{artifact.provenance['sha256'][:16]}",source_id=adapter.source_id,logical_name=artifact.logical_name,media_type=artifact.media_type,object_key=f"proof/{artifact.payload_path.name}",byte_size=artifact.byte_size,provenance=artifact.provenance,run_time=None,retrieved_at=result.retrieved_at,provider_run_id=result.provider_run_id,native_crs="not_applicable",payload_path=artifact.payload_path))
  entry={"source_id":adapter.source_id,"url":candidate.urls[0],"parameters":{},"raw_bytes":raw.stat().st_size,"raw_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),"raw_captured_at":stamp((args.capture/f"{name}.captured_at").read_text()).isoformat().replace("+00:00","Z"),"retrieval_completed_at":captured.isoformat().replace("+00:00","Z"),"provider_run_id":candidate.provider_run_id,"logical_name":artifact.logical_name,"artifact_bytes":artifact.byte_size,"artifact_sha256":artifact.provenance["sha256"],"valid_times":artifact.provenance["valid_times"],"field_disposition":artifact.provenance["field_disposition"],"publishable":result.complete and result.qc_passed}
  if identity is not None: entry["identity"]={"url":candidate.urls[1],"bytes":identity.stat().st_size,"sha256":hashlib.sha256(identity.read_bytes()).hexdigest(),"captured_at":captured.isoformat().replace("+00:00","Z")}
  receipt.append(entry)
 (args.output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
 from fastapi.testclient import TestClient
 api_module=importlib.import_module("weather_api.app")
 from weather_api.store import LiveStore
 class S3:
  def head_bucket(self,**_kwargs): return {}
  def download_fileobj(self,_bucket,key,handle):
   record=next(item for item in records if item.object_key==key)
   with record.payload_path.open("rb") as source: shutil.copyfileobj(source,handle)
 class Store:
  s3=S3();config=SimpleNamespace(bucket="capture")
  def current_artifacts(self): return records
  def source_activity(self): return {item.source_id:item.retrieved_at for item in records}
 os.environ["WEATHER_DATA_MODE"]="live"
 api_module.live_store=lambda:LiveStore(Store(),args.output/"api-cache")
 response=TestClient(api_module.app).get(f"{api_module.PREFIX}/experimental/time-inputs")
 response.raise_for_status()
 payload=response.json()
 (args.output/"api-readback.json").write_text(json.dumps(payload,indent=2)+"\n")
 comparisons=[]
 for product in payload["products"]:
  expected=raw_rows[product["source_id"]]; checked=0; mismatches=[]
  for name,variable in product["variables"].items():
   for index,actual in enumerate(variable["values"]):
    wanted=expected[index][name]
    if isinstance(wanted,float) and math.isnan(wanted): wanted=None
    if actual!=wanted: mismatches.append({"field":name,"index":index,"raw":wanted,"api":actual})
    checked+=1
  comparisons.append({"source_id":product["source_id"],"raw_to_api_values_checked":checked,"mismatches":mismatches})
 if any(item["mismatches"] for item in comparisons): raise RuntimeError("raw-to-API comparison failed")
 (args.output/"comparisons.json").write_text(json.dumps(comparisons,indent=2)+"\n")
 print(args.output/"receipt.json")
if __name__=="__main__": main()
