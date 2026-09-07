from concurrent.futures import ThreadPoolExecutor
from datetime import UTC,datetime,timedelta
import pytest
from ingest.adapters.noaa_s3 import MAX_GEFS_MEMBER_BYTES, _gefs_keys_by_upstream
from weather_api.gefs_query import *
import numpy as np
import xarray as xr
RUN=datetime(2026,9,6,12,tzinfo=UTC)
BOX=(("east",-46.0),("north",50.5),("south",45.0),("west",-58.0))
def key(lead=6):return GEFSRequestKey("2026090612",RUN,lead,"pgrb2ap5",declared_members(),GEFS_FIELDS,BOX)
def entry(k,**kw):
 present=kw.get("present",k.members); optional=kw.get("optional",{}); by_field={field:upstream for upstream,field in _gefs_keys_by_upstream("noaa-gefs").items()}; receipts=[]
 for member in k.members:
  stem=gefs_member_url(date_str=k.run_time.strftime("%Y%m%d"),cycle=k.run_time.strftime("%H"),lead=k.lead,member=member)
  receipts.append({"kind":"index","member":member,"http_status":200,"url":stem+".idx","request_headers":{},"response_headers":{},"completed_at":RUN.isoformat(),"byte_size":1,"sha256":k.availability_sha256 if member=="gec00" and k.availability_sha256 else "a"*64})
  if member in present:
   for field in GEFS_FIELDS:
    if field=="temperature_2m" or field not in optional.get(member,()): receipts.append({"kind":"range","member":member,"field":by_field[field],"range_start":0,"range_end":0,"http_status":206,"url":stem,"effective_url":stem,"request_headers":{"range":"bytes=0-0"},"response_headers":{"Content-Range":"bytes 0-0/12345"},"completed_at":RUN.isoformat(),"byte_size":1,"sha256":"b"*64})
 return GEFSQueryEntry(k,k.run_time+timedelta(hours=k.lead),RUN,present,kw.get("mandatory",{}),optional,b"zarr",{"transport_receipts":receipts},kw.get("intervals",{m:(k.run_time+timedelta(hours=max(0,k.lead-(3 if k.lead==3 else 6))),k.run_time+timedelta(hours=k.lead)) for m in present if "total_cloud_mean_6h" not in optional.get(m,())}))
def test_bounds_charge_all_member_fields_indices_and_output():
 b=demand_operation_bounds(); raw=31*7*MAX_GEFS_MEMBER_BYTES; idx=31*GEFS_IDX_BYTES
 assert b.received_bytes==raw+idx+GEFS_DISCOVERY_BYTES and b.filesystem_bytes==raw+idx+GEFS_DISCOVERY_BYTES+GEFS_OUTPUT_ALLOWANCE_BYTES; b.validate()
def test_identity_and_cadence_refuse_before_loader():
 calls=[]; s=GEFSQueryService(lambda k:calls.append(k) or entry(k),preflight=lambda _workspace:demand_operation_bounds())
 with pytest.raises(ValueError,match="31 declared"):s.query(GEFSRequestKey("2026090612",RUN,6,"pgrb2ap5",declared_members()[:-1],GEFS_FIELDS,BOX))
 with pytest.raises(ValueError,match="three-hour"):s.query(key(5))
 assert calls==[]
def test_canonical_control_and_perturbed_member_urls_use_native_filename_token():
 assert gefs_member_url(date_str="20260906",cycle="12",lead=6,member="gec00")=="https://noaa-gefs-pds.s3.amazonaws.com/gefs.20260906/12/atmos/pgrb2ap5/gec00.t12z.pgrb2a.0p50.f006"
 assert gefs_member_url(date_str="20260906",cycle="12",lead=6,member="gep30").endswith("/gep30.t12z.pgrb2a.0p50.f006")
def test_coalesced_miss_and_hit_load_once():
 calls=[]; s=GEFSQueryService(lambda k:calls.append(k) or entry(k),preflight=lambda _workspace:demand_operation_bounds())
 with ThreadPoolExecutor(max_workers=4) as p: results=list(p.map(lambda _:s.query(key()),range(4)))
 assert calls==[key()] and all(x is results[0] for x in results); assert s.query(key()) is results[0] and calls==[key()]
def test_mandatory_temperature_failure_incomplete_but_optional_absence_is_not():
 missing=declared_members()[-1]
 assert not entry(key(),present=declared_members()[:-1],mandatory={missing:"temperature unavailable"}).complete
 optional=entry(key(),optional={missing:("dew_point_2m",)})
 assert optional.complete and optional.optional_absences[missing]==("dew_point_2m",)
def test_f003_cloud_interval_is_three_hours_and_malformed_interval_refuses():
 assert entry(key(3)).cloud_intervals[declared_members()[0]]==(RUN,RUN+timedelta(hours=3))
 with pytest.raises(ValueError,match="cloud interval"):GEFSQueryService(lambda k:entry(k,intervals={k.members[0]:(RUN,RUN)}),preflight=lambda _workspace:demand_operation_bounds()).query(key())

def test_failure_is_cached_until_backoff_deadline():
 now=[0.0]; calls=[]
 def fail(k): calls.append(k); raise OSError("provider unavailable")
 service=GEFSQueryService(fail,preflight=lambda _workspace:demand_operation_bounds(),clock=lambda:now[0])
 for _ in range(2):
  with pytest.raises(OSError,match="unavailable"):service.query(key())
 assert calls==[key()]
 now[0]=61
 with pytest.raises(OSError):service.query(key())
 assert calls==[key(),key()]

@pytest.mark.parametrize("bad",[
 GEFSRequestKey("wrong",RUN,6,"pgrb2ap5",declared_members(),GEFS_FIELDS,BOX),
 GEFSRequestKey("2026090612",RUN,6,"other",declared_members(),GEFS_FIELDS,BOX),
 GEFSRequestKey("2026090612",RUN,6,"pgrb2ap5",declared_members(),GEFS_FIELDS,(("east",-46.0),)),
])
def test_noncanonical_request_refuses_before_loader(bad):
 calls=[]; service=GEFSQueryService(lambda k:calls.append(k) or entry(k),preflight=lambda _workspace:demand_operation_bounds())
 with pytest.raises(ValueError):service.query(bad)
 assert calls==[]

def test_entry_rejects_member_and_absence_metadata_inconsistency():
 missing=declared_members()[-1]
 with pytest.raises(ValueError,match="mandatory failures"):
  GEFSQueryService(lambda k:entry(k,present=k.members[:-1]),preflight=lambda _workspace:demand_operation_bounds()).query(key())
 with pytest.raises(ValueError,match="optional absences"):
  GEFSQueryService(lambda k:entry(k,optional={missing:("temperature_2m",)}),preflight=lambda _workspace:demand_operation_bounds()).query(key())

def test_cloud_interval_keys_exactly_match_members_with_cloud():
 member=declared_members()[-1]
 missing=dict(entry(key()).cloud_intervals); missing.pop(member)
 with pytest.raises(ValueError,match="exactly match"):
  GEFSQueryService(lambda k:entry(k,intervals=missing),preflight=lambda _:demand_operation_bounds()).query(key())
 accepted=entry(key(),optional={member:("total_cloud_mean_6h",)},intervals=missing)
 GEFSQueryService(lambda _k:accepted,preflight=lambda _:demand_operation_bounds()).query(key())

def test_f006_one_hour_cloud_window_is_refused():
 intervals=dict(entry(key(6)).cloud_intervals); member=declared_members()[0]
 intervals[member]=(RUN+timedelta(hours=5),RUN+timedelta(hours=6))
 with pytest.raises(ValueError,match="f006"):
  GEFSQueryService(lambda k:entry(k,intervals=intervals),preflight=lambda _:demand_operation_bounds()).query(key(6))


def test_f012_cloud_interval_requires_exact_six_hours():
 intervals=dict(entry(key(12)).cloud_intervals); member=declared_members()[0]
 intervals[member]=(RUN+timedelta(hours=7),RUN+timedelta(hours=12))
 with pytest.raises(ValueError,match="exactly six"):
  GEFSQueryService(lambda k:entry(k,intervals=intervals),preflight=lambda _:demand_operation_bounds()).query(key(12))

def test_f000_cannot_advertise_averaged_cloud_without_native_label():
 with pytest.raises(ValueError,match="f000"):
  GEFSQueryService(lambda k:entry(k,intervals={m:(RUN-timedelta(hours=6),RUN) for m in k.members}),preflight=lambda _:demand_operation_bounds()).query(key(0))

def test_member_presence_uses_finite_native_cells_not_aligned_coordinate():
 values=np.array([[[1.0,np.nan]],[[np.nan,np.nan]],[[2.0,3.0]]])
 field=xr.DataArray(values,dims=("member","latitude","longitude"),coords={"member":["gec00","gep01","gep02"]})
 assert members_with_values(field)==("gec00","gep02")

def test_member_presence_treats_masked_and_all_nan_as_absent():
 field=xr.DataArray(np.ma.array([[1.0],[2.0]],mask=[[True],[False]]),dims=("member","cell"),coords={"member":["gec00","gep01"]})
 assert members_with_values(field)==("gep01",)

def test_bounded_loader_validates_child_bundle_identity_and_shape(tmp_path):
 import json,zipfile
 def runner(**kwargs):
  request=json.loads(kwargs["stdin"]); output=kwargs["destination"]
  intervals={m:[(RUN+timedelta(hours=18)).isoformat(),(RUN+timedelta(hours=24)).isoformat()] for m in request["members"]}
  info={"run_id":request["run_id"],"run_time":request["run_time"],"lead":request["lead"],"valid_time": (RUN+timedelta(hours=24)).isoformat(),"fetched_at":RUN.isoformat(),"members_present":request["members"],"mandatory_failures":{},"optional_absences":{},"cloud_intervals":intervals,"provenance":{"source_id":"noaa-gefs",**entry(key(24)).provenance}}
  with zipfile.ZipFile(output,"w") as bundle:
   bundle.writestr("result.json",json.dumps(info)); bundle.writestr("artifacts/noaa_gefs_members.zarr.zip",b"zip")
 loaded=GEFSBoundedLoader(tmp_path,runner=runner,validator=lambda *_:None)(key(24)); loaded.validate()
 assert loaded.members_present==declared_members() and loaded.valid_time==RUN+timedelta(hours=24)

def test_bounded_loader_refuses_wrong_child_identity(tmp_path):
 import json,zipfile
 def runner(**kwargs):
  request=json.loads(kwargs["stdin"]); output=kwargs["destination"]
  info={"run_id":"wrong","run_time":request["run_time"],"lead":request["lead"],"valid_time":RUN.isoformat(),"fetched_at":RUN.isoformat(),"members_present":[],"mandatory_failures":{},"optional_absences":{},"cloud_intervals":{},"provenance":{}}
  with zipfile.ZipFile(output,"w") as bundle:
   bundle.writestr("result.json",json.dumps(info)); bundle.writestr("artifacts/noaa_gefs_members.zarr.zip",b"zip")
 with pytest.raises(ValueError,match="different run identity"):GEFSBoundedLoader(tmp_path,runner=runner,validator=lambda *_:None)(key())

def test_selected_loader_refuses_receiptless_adapter_before_provider_io(tmp_path):
 from ingest.adapters.noaa_s3 import NOAAGEFSEnsembleAdapter
 class Client:
  def get_text(self,*_args): pytest.fail("provider I/O occurred")
 with pytest.raises(ValueError,match="receipt capture"):
  GEFSSelectedLoader(NOAAGEFSEnsembleAdapter(client=Client()),tmp_path)

def test_bounded_loader_refuses_compressed_bundle_before_read(tmp_path):
 import json,zipfile
 def runner(**kwargs):
  output=kwargs["destination"]
  with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as bundle:
   bundle.writestr("result.json",json.dumps({})); bundle.writestr("artifacts/noaa_gefs_members.zarr.zip",b"zip")
 with pytest.raises(ValueError,match="unencrypted stored"):
  GEFSBoundedLoader(tmp_path,runner=runner,validator=lambda *_:None)(key())

def test_bounded_loader_refuses_untyped_manifest(tmp_path):
 import json,zipfile
 def runner(**kwargs):
  output=kwargs["destination"]
  with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_STORED) as bundle:
   bundle.writestr("result.json",json.dumps({"members_present":"all"})); bundle.writestr("artifacts/noaa_gefs_members.zarr.zip",b"zip")
 with pytest.raises(ValueError,match="invalid types"):
  GEFSBoundedLoader(tmp_path,runner=runner,validator=lambda *_:None)(key())

def test_unapproved_endpoint_refuses_before_loader():
 bad=GEFSRequestKey(key().run_id,RUN,6,"pgrb2ap5",declared_members(),GEFS_FIELDS,BOX,"https://evil.invalid")
 calls=[]; service=GEFSQueryService(lambda k:calls.append(k) or entry(k),preflight=lambda _:demand_operation_bounds())
 with pytest.raises(ValueError,match="approved NOAA origin"):service.query(bad)
 assert calls==[]

def test_receipt_accepts_numeric_content_range_total_and_rejects_invalid_total():
 accepted=entry(key())
 GEFSQueryService(lambda _k:accepted,preflight=lambda _:demand_operation_bounds()).query(key())
 receipts=[dict(item) for item in accepted.provenance["transport_receipts"]]
 target=next(item for item in receipts if item["kind"]=="range")
 target["response_headers"]={"Content-Range":"bytes 0-0/0"}
 bad=GEFSQueryEntry(accepted.key,accepted.valid_time,accepted.fetched_at,accepted.members_present,accepted.mandatory_failures,accepted.optional_absences,accepted.payload,{**accepted.provenance,"transport_receipts":receipts},accepted.cloud_intervals)
 with pytest.raises(ValueError,match="Content-Range"):
  bad.validate()
 target["response_headers"]={"Content-Range":"bytes 1-1/12345"}
 with pytest.raises(ValueError,match="Content-Range"):
  bad.validate()

def test_last_record_open_range_uses_returned_numeric_end_and_cap():
 accepted=entry(key()); receipts=[dict(item) for item in accepted.provenance["transport_receipts"]]
 target=next(item for item in receipts if item.get("field")=="PRMSL:mean sea level")
 target.update(range_end=None,byte_size=10,sha256="c"*64)
 target["request_headers"]={"range":"bytes=0-"}; target["response_headers"]={"Content-Range":"bytes 0-9/10"}
 value=GEFSQueryEntry(accepted.key,accepted.valid_time,accepted.fetched_at,accepted.members_present,accepted.mandatory_failures,accepted.optional_absences,accepted.payload,{**accepted.provenance,"transport_receipts":receipts},accepted.cloud_intervals)
 value.validate()
 target["response_headers"]={"Content-Range":"bytes 0-10/11"}
 with pytest.raises(ValueError,match="byte count"):
  value.validate()


def discovery_body(url):
 import hashlib
 body=b"1:0:d=2026090612:TMP:2 m above ground:6 hour fcst:\n"
 return body,{"url":url,"effective_url":url,"http_status":200,"request_headers":{},"response_headers":{},"completed_at":RUN.isoformat(),"byte_size":len(body),"sha256":hashlib.sha256(body).hexdigest()}

@pytest.mark.parametrize("offset,expected_run,expected_lead", [
 (0,"2026090618",0),(-24,"2026090518",0),(14*24,"2026090618",336),
])
def test_discovery_anchors_future_to_now_and_preserves_native_lead(offset,expected_run,expected_lead):
 calls=[]; selected=RUN+timedelta(hours=6+offset)
 service=GEFSQueryService(lambda k:entry(k),preflight=lambda _:demand_operation_bounds())
 coordinator=GEFSQueryCoordinator(service,now=lambda:RUN+timedelta(hours=6),discover_index=lambda url:calls.append(url) or discovery_body(url))
 resolved=coordinator.request_key(selected)
 assert (resolved.run_id,resolved.lead)==(expected_run,expected_lead)
 assert timedelta(0)<=selected-(resolved.run_time+timedelta(hours=resolved.lead))<timedelta(hours=3)
 assert coordinator.request_key(selected)==resolved and len(calls)==1


def test_discovery_tries_only_two_indices_and_caches_failure_without_loading():
 calls=[]; loads=[]; clock=[0.0]
 def absent(url): calls.append(url); raise OSError("no such run")
 service=GEFSQueryService(lambda k:loads.append(k),preflight=lambda _:demand_operation_bounds())
 coordinator=GEFSQueryCoordinator(service,now=lambda:RUN+timedelta(hours=6),clock=lambda:clock[0],discover_index=absent)
 for _ in range(2):
  with pytest.raises(ValueError):coordinator.query(RUN+timedelta(hours=6))
 assert len(calls)==2 and loads==[]
 assert calls[0].endswith("gec00.t18z.pgrb2a.0p50.f000.idx")
 assert calls[1].endswith("gec00.t12z.pgrb2a.0p50.f006.idx")
 clock[0]=61
 with pytest.raises(ValueError):coordinator.query(RUN+timedelta(hours=6))
 assert len(calls)==4


def test_discovery_failure_falls_back_to_confirmed_index_and_repeat_has_zero_io():
 calls=[]; loads=[]
 def discover(url):
  calls.append(url)
  if len(calls)==1:raise OSError("publication pending")
  return discovery_body(url)
 service=GEFSQueryService(lambda k:loads.append(k) or entry(k),preflight=lambda _:demand_operation_bounds())
 coordinator=GEFSQueryCoordinator(service,now=lambda:RUN+timedelta(hours=6),discover_index=discover)
 first=coordinator.query(RUN+timedelta(hours=6))
 assert first.key.run_id=="2026090612" and first.key.lead==6
 assert coordinator.query(RUN+timedelta(hours=6)) is first
 assert len(calls)==2 and len(loads)==1
 assert first.provenance["availability_receipt"]["sha256"] == first.key.availability_sha256


def test_discovery_is_refused_before_any_io_when_platform_bound_is_unavailable():
 def refuse(_):raise RuntimeError("platform unavailable")
 service=GEFSQueryService(lambda _:pytest.fail("load"),preflight=refuse)
 coordinator=GEFSQueryCoordinator(service,discover_index=lambda _:pytest.fail("discovery"))
 with pytest.raises(RuntimeError,match="platform unavailable"):coordinator.query(RUN)


def test_refresh_reacquires_discovery_and_family_without_renewing_hits():
 clock=[0.0]; discoveries=[]; loads=[]
 service=GEFSQueryService(lambda k:loads.append(k) or entry(k),clock=lambda:clock[0],preflight=lambda _:demand_operation_bounds())
 coordinator=GEFSQueryCoordinator(service,now=lambda:RUN,clock=lambda:clock[0],discover_index=lambda url:discoveries.append(url) or discovery_body(url))
 selected=RUN+timedelta(hours=6)
 first=coordinator.query(selected)
 clock[0]=100
 assert coordinator.query(selected) is first
 assert service.entries[first.key][0]==600 and coordinator._discovery[1]==600
 refreshed=coordinator.query(selected,refresh=True)
 assert refreshed is not first and len(discoveries)==len(loads)==2
 assert service.entries[first.key][0]==700 and coordinator._discovery[1]==700
 clock[0]=699
 assert coordinator.query(selected) is refreshed
 clock[0]=700
 assert coordinator.query(selected) is not refreshed
 assert len(discoveries)==len(loads)==3


def test_failed_family_refresh_preserves_unexpired_entry_and_original_deadline():
 clock=[0.0]; loads=[]
 def loader(k):
  loads.append(k)
  if len(loads)>1: raise OSError("refresh failed")
  return entry(k)
 service=GEFSQueryService(loader,clock=lambda:clock[0],preflight=lambda _:demand_operation_bounds())
 coordinator=GEFSQueryCoordinator(service,now=lambda:RUN,clock=lambda:clock[0],discover_index=discovery_body)
 selected=RUN+timedelta(hours=6); first=coordinator.query(selected)
 clock[0]=590
 with pytest.raises(OSError,match="refresh failed"):coordinator.query(selected,refresh=True)
 assert coordinator.query(selected) is first
 assert service.entries[first.key][0]==600
 clock[0]=600
 with pytest.raises(OSError,match="refresh failed"):coordinator.query(selected)
 assert len(loads)==2


def test_failed_discovery_refresh_preserves_unexpired_discovery():
 clock=[0.0]; calls=[]
 def discover(url):
  calls.append(url)
  if len(calls)>1: raise OSError("discovery failed")
  return discovery_body(url)
 service=GEFSQueryService(entry,clock=lambda:clock[0],preflight=lambda _:demand_operation_bounds())
 coordinator=GEFSQueryCoordinator(service,now=lambda:RUN,clock=lambda:clock[0],discover_index=discover)
 selected=RUN+timedelta(hours=6); first=coordinator.query(selected)
 clock[0]=590
 with pytest.raises(ValueError,match="no available"):coordinator.query(selected,refresh=True)
 assert len(calls)==3 and coordinator.query(selected) is first
 assert coordinator._discovery[1]==600
 clock[0]=600
 with pytest.raises(ValueError,match="backoff"):coordinator.query(selected)
 assert len(calls)==3


def test_concurrent_refreshes_share_one_complete_acquisition(monkeypatch):
 import threading
 import weather_api.gefs_query as module
 waiting=threading.Event(); entered=threading.Event(); release=threading.Event(); loads=[]; discoveries=[]
 class ObservedFuture(Future):
  def result(self,*args,**kwargs):
   waiting.set()
   return super().result(*args,**kwargs)
 monkeypatch.setattr(module,"Future",ObservedFuture)
 def loader(k):
  loads.append(k)
  if len(loads)==2:
   entered.set()
   assert release.wait(5)
  return entry(k)
 service=GEFSQueryService(loader,preflight=lambda _:demand_operation_bounds())
 coordinator=GEFSQueryCoordinator(service,now=lambda:RUN,discover_index=lambda url:discoveries.append(url) or discovery_body(url))
 selected=RUN+timedelta(hours=6); coordinator.query(selected)
 with ThreadPoolExecutor(max_workers=2) as pool:
  first=pool.submit(coordinator.query,selected,refresh=True)
  assert entered.wait(5)
  second=pool.submit(coordinator.query,selected,refresh=True)
  assert waiting.wait(5)
  release.set()
  assert first.result() is second.result()
 assert len(loads)==len(discoveries)==2
 assert coordinator._query_inflight is None


def test_point_fields_forwards_explicit_refresh_before_sampling(monkeypatch):
 coordinator=GEFSQueryCoordinator(now=lambda:RUN)
 def query(selected_time,*,refresh=False):
  assert selected_time==RUN and refresh is True
  raise OSError("fixture acquisition stop")
 monkeypatch.setattr(coordinator,"query",query)
 with pytest.raises(OSError,match="fixture acquisition stop"):
  coordinator.point_fields(47.5,-52.7,RUN,member="gec00",refresh=True)


def test_failed_refresh_with_changed_index_keeps_previous_family_reachable():
 import hashlib
 clock=[0.0]; calls=[]; loads=[]
 def discover(url):
  calls.append(url)
  body,receipt=discovery_body(url)
  if len(calls)>1:
   body+=b"2:20:d=2026090612:RH:2 m above ground:6 hour fcst:\n"
   receipt={**receipt,"byte_size":len(body),"sha256":hashlib.sha256(body).hexdigest()}
  return body,receipt
 def loader(k):
  loads.append(k)
  if len(loads)>1:raise OSError("new family failed")
  return entry(k)
 service=GEFSQueryService(loader,clock=lambda:clock[0],preflight=lambda _:demand_operation_bounds())
 coordinator=GEFSQueryCoordinator(service,now=lambda:RUN,clock=lambda:clock[0],discover_index=discover)
 selected=RUN+timedelta(hours=6); first=coordinator.query(selected)
 clock[0]=100
 with pytest.raises(OSError,match="new family failed"):coordinator.query(selected,refresh=True)
 assert loads[0].availability_sha256!=loads[1].availability_sha256
 assert coordinator.query(selected) is first
 assert coordinator._discovery[1]==service.entries[first.key][0]==600
 assert len(calls)==len(loads)==2
