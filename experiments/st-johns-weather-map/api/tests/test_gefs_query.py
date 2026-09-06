from concurrent.futures import ThreadPoolExecutor
from datetime import UTC,datetime,timedelta
import pytest
from ingest.adapters.noaa_s3 import MAX_GEFS_MEMBER_BYTES
from weather_api.gefs_query import *
RUN=datetime(2026,9,6,12,tzinfo=UTC)
BOX=(("east",-46.0),("north",50.5),("south",45.0),("west",-58.0))
def key(lead=6):return GEFSRequestKey("2026090612",RUN,lead,"pgrb2ap5",declared_members(),GEFS_FIELDS,BOX)
def entry(k,**kw):return GEFSQueryEntry(k,RUN+timedelta(hours=k.lead),RUN,kw.get("present",k.members),kw.get("mandatory",{}),kw.get("optional",{}),b"zarr",{},kw.get("intervals",{m:(RUN+timedelta(hours=max(0,k.lead-(3 if k.lead==3 else 6))),RUN+timedelta(hours=k.lead)) for m in kw.get("present",k.members)}))
def test_bounds_charge_all_member_fields_indices_and_output():
 b=demand_operation_bounds(); raw=31*7*MAX_GEFS_MEMBER_BYTES; idx=31*GEFS_IDX_BYTES
 assert b.received_bytes==raw+idx and b.filesystem_bytes==raw+idx+GEFS_OUTPUT_ALLOWANCE_BYTES; b.validate()
def test_identity_and_cadence_refuse_before_loader():
 calls=[]; s=GEFSQueryService(lambda k:calls.append(k) or entry(k),preflight=lambda _workspace:demand_operation_bounds())
 with pytest.raises(ValueError,match="31 declared"):s.query(GEFSRequestKey("2026090612",RUN,6,"pgrb2ap5",declared_members()[:-1],GEFS_FIELDS,BOX))
 with pytest.raises(ValueError,match="three-hour"):s.query(key(5))
 assert calls==[]
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
