import gzip
from datetime import datetime,timezone
from pathlib import Path
import httpx,pytest
from ingest.contract import AdapterUnavailable,FetchWindow
from ingest.experimental.awc_aviation import AWCAviationNativeAdapter,URLS,MAX_DECODED
from ingest.http import PoliteClient,USER_AGENT
UTC=timezone.utc; W=FetchWindow(datetime(2026,9,6,tzinfo=UTC))
def client(data):
 c=PoliteClient(min_host_interval_seconds=0,attempts=1)
 c._client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=data[r.url.path.rsplit('/',1)[-1]])),headers={'User-Agent':USER_AGENT});return c
def good(header='a,a,time',row='1,2,2026-09-06T00:00:00Z'):
 return gzip.compress((header+'\n'+row+'\n').encode())
def test_positional_headers_and_completion(tmp_path):
 d={'aircraftreports.cache.csv.gz':good(),'airsigmets.cache.csv.gz':good('raw_text,valid_time_from','x,2026-09-06T00:00:00Z')}; c=client(d); done=datetime(2026,9,6,1,tzinfo=UTC); old=c.get_bytes_with_headers_completed;c.get_bytes_with_headers_completed=lambda u,*,max_bytes:(*old(u,max_bytes=max_bytes)[:2],done)
 r=AWCAviationNativeAdapter(c).fetch(AWCAviationNativeAdapter(c).discover(W)[0],W,tmp_path); assert r.retrieved_at==done and r.artifacts[0].provenance['csv_header_positions']==['a','a','time']
@pytest.mark.parametrize('body',[b'bad',gzip.compress(b'a,b\n1\n'),gzip.compress(b'a,b\n'+b'x'* (MAX_DECODED+1))])
def test_bad_inputs_fail_and_clean(tmp_path,body):
 d={'aircraftreports.cache.csv.gz':body,'airsigmets.cache.csv.gz':good('raw_text,valid_time_from','x,z')}
 a=AWCAviationNativeAdapter(client(d))
 with pytest.raises(AdapterUnavailable):a.fetch(a.discover(W)[0],W,tmp_path)
 assert list(tmp_path.iterdir())==[]
def test_partial_write_cleanup(tmp_path,monkeypatch):
 d={'aircraftreports.cache.csv.gz':good(),'airsigmets.cache.csv.gz':good('raw_text,valid_time_from','x,z')};a=AWCAviationNativeAdapter(client(d));old=Path.write_bytes
 def bad(p,b):
  if p.name=='sigmet.csv.gz':old(p,b'partial');raise OSError('partial')
  return old(p,b)
 monkeypatch.setattr(Path,'write_bytes',bad)
 with pytest.raises(OSError):a.fetch(a.discover(W)[0],W,tmp_path)
 assert list(tmp_path.iterdir())==[]
