from concurrent.futures import ThreadPoolExecutor
from datetime import UTC,datetime,timedelta
import pytest
from ingest.adapters.noaa_s3 import MAX_GEFS_MEMBER_BYTES
from weather_api.gefs_query import *
RUN=datetime(2026,9,6,12,tzinfo=UTC)
def key(lead=6):return GEFSRequestKey("2026090612",RUN,lead,"pgrb2ap5",declared_members(),GEFS_FIELDS,(("east",-46.0),))
def entry(k,**kw):return GEFSQueryEntry(k,RUN+timedelta(hours=k.lead),RUN,kw.get("present",k.members),kw.get("mandatory",{}),kw.get("optional",{}),b"zarr",{},kw.get("interval",6))
def test_bounds_charge_all_member_fields_indices_and_output():
 b=demand_operation_bounds(); raw=31*7*MAX_GEFS_MEMBER_BYTES; idx=31*GEFS_IDX_BYTES
 assert b.received_bytes==raw+idx and b.filesystem_bytes==raw+idx+GEFS_OUTPUT_ALLOWANCE_BYTES; b.validate()
def test_identity_and_cadence_refuse_before_loader():
 calls=[]; s=GEFSQueryService(lambda k:calls.append(k) or entry(k))
 with pytest.raises(ValueError,match="31 declared"):s.query(GEFSRequestKey("r",RUN,6,"p",declared_members()[:-1],GEFS_FIELDS,()))
 with pytest.raises(ValueError,match="three-hour"):s.query(key(5))
 assert calls==[]
def test_coalesced_miss_and_hit_load_once():
 calls=[]; s=GEFSQueryService(lambda k:calls.append(k) or entry(k))
 with ThreadPoolExecutor(max_workers=4) as p: results=list(p.map(lambda _:s.query(key()),range(4)))
 assert calls==[key()] and all(x is results[0] for x in results); assert s.query(key()) is results[0] and calls==[key()]
def test_mandatory_temperature_failure_incomplete_but_optional_absence_is_not():
 missing=declared_members()[-1]
 assert not entry(key(),present=declared_members()[:-1],mandatory={missing:"temperature unavailable"}).complete
 optional=entry(key(),optional={missing:("dew_point_2m",)})
 assert optional.complete and optional.optional_absences[missing]==("dew_point_2m",)
def test_cloud_interval_cannot_be_relabelled():
 with pytest.raises(ValueError,match="native cloud interval"):GEFSQueryService(lambda k:entry(k,interval=0)).query(key())
