from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import httpx,pytest
from ingest.contract import AdapterUnavailable,FetchWindow
from ingest.experimental.eccc_local_products import ECCCPartnerSWOBNativeAdapter,ECCCCitypageNativeAdapter,PARTNER_STATIONS,MAX_XML,discover_metnotes
from ingest.http import PoliteClient,USER_AGENT
from ingest.registry import get_adapter
UTC=timezone.utc; NOW=datetime(2026,9,6,5,30,tzinfo=UTC); WINDOW=FetchWindow(NOW)

def client(handler):
 c=PoliteClient(min_host_interval_seconds=0,attempts=1);c._client=httpx.Client(transport=httpx.MockTransport(handler),headers={'User-Agent':USER_AGENT});return c

def listing(*names): return ('<html>'+''.join(f'<a href="{x}">{x}</a>' for x in names)+'</html>').encode()
def swob(station, extra=''):
 return f'''<om:ObservationCollection xmlns:om="http://www.opengis.net/om/1.0"><om:member><om:Observation><om:metadata><set><identification-elements><element name="stn_id" uom="unitless" value="{station.upper()}"/><element name="stn_nam" value="Station {station}"/><element name="msc_id" value="PROVIDER_{station}"/><element name="data_attrib_not" value="Partner. All rights reserved."/><element name="date_tm" uom="datetime" value="2026-09-06T05:00:00.000Z"/></identification-elements></set></om:metadata><om:result><elements><element name="air_temp" uom="°C" value="12.5"><qualifier name="qa_summary" value="100"/></element>{extra}</elements></om:result></om:Observation></om:member></om:ObservationCollection>'''.encode()
CITY=b'''<siteData><license>https://dd.weather.gc.ca/doc/LICENCE_GENERAL.txt</license><location><name code="s0000280">St. John's</name></location><currentConditions><temperature unitType="metric" units="C">12</temperature></currentConditions><forecastGroup><forecast><uv category="moderate"><index>5</index></uv></forecast></forecastGroup></siteData>'''

def test_partner_documents_are_complete_immutable_native_artifacts(tmp_path:Path):
 def h(req):
  parts=req.url.path.rstrip('/').split('/'); station=parts[-1]
  if req.url.path.endswith('/'): return httpx.Response(200,content=listing(f'2026-09-06-0500-provider-{station}-AUTO-swob.xml'))
  station=parts[-2]; return httpx.Response(200,content=swob(station,'<element name="rnfl_amt_pst1hr" uom="mm"/>'),headers={'etag':'x'})
 a=ECCCPartnerSWOBNativeAdapter(client(h),base_url='https://fixture.invalid/partners',day='20260906'); result=a.fetch(a.discover(WINDOW)[0],WINDOW,tmp_path)
 assert len(result.artifacts)==len(PARTNER_STATIONS)==6 and not result.complete
 for artifact in result.artifacts:
  assert artifact.payload_path.read_bytes().startswith(b'<om:ObservationCollection')
  assert artifact.provenance['upstream_sha256']==artifact.provenance['artifact_sha256']
  assert artifact.provenance['source_qc']['status']=='unknown'
  rows={r['name']:r for r in artifact.provenance['native_element_inventory']}
  assert rows['air_temp']['uom']=='°C' and rows['air_temp']['qualifiers']==['qa_summary']
  assert rows['rnfl_amt_pst1hr']['has_value'] is False
  assert 'All rights reserved' in artifact.provenance['provider_attribution']

def test_partner_missing_station_malformed_and_oversize_fail_closed(tmp_path:Path):
 def missing(req): return httpx.Response(200,content=listing())
 with pytest.raises(AdapterUnavailable,match='no SWOB XML'): ECCCPartnerSWOBNativeAdapter(client(missing),base_url='https://fixture.invalid',day='20260906').discover(WINDOW)
 def malformed(req):
  station=req.url.path.rstrip('/').split('/')[-1]
  if req.url.path.endswith('/'): return httpx.Response(200,content=listing(f'2026-09-06-0500-x-{station}-AUTO-swob.xml'))
  return httpx.Response(200,content=b'<broken>')
 a=ECCCPartnerSWOBNativeAdapter(client(malformed),base_url='https://fixture.invalid',day='20260906')
 with pytest.raises(AdapterUnavailable,match='malformed XML'): a.fetch(a.discover(WINDOW)[0],WINDOW,tmp_path)
 assert list(tmp_path.iterdir())==[]
 def oversized(req):
  station=req.url.path.rstrip('/').split('/')[-1]
  if req.url.path.endswith('/'): return httpx.Response(200,content=listing(f'2026-09-06-0500-x-{station}-AUTO-swob.xml'))
  return httpx.Response(200,content=b'x'*(MAX_XML+1))
 a=ECCCPartnerSWOBNativeAdapter(client(oversized),base_url='https://fixture.invalid',day='20260906')
 with pytest.raises(AdapterUnavailable,match='bounded request unavailable'): a.fetch(a.discover(WINDOW)[0],WINDOW,tmp_path)

def test_city_xml_is_native_and_unpublishable(tmp_path:Path):
 name='20260906T052448.467Z_MSC_CitypageWeather_s0000280_en.xml'
 def h(req): return httpx.Response(200,content=listing(name) if req.url.path.endswith('/') else CITY,headers={'last-modified':'x'})
 a=ECCCCitypageNativeAdapter(client(h),base_url='https://fixture.invalid/NL'); c=a.discover(WINDOW)[0]; result=a.fetch(c,WINDOW,tmp_path)
 assert c.run_time==datetime(2026,9,6,5,24,48,467000,tzinfo=UTC) and not result.complete
 p=result.artifacts[0].provenance; assert p['site_code']=='s0000280' and p['upstream_sha256']==p['artifact_sha256']
 rows=p['native_element_inventory']; tags={r['tag'] for r in rows}; assert {'license','name','temperature','uv','index'} <= tags
 temperature=next(r for r in rows if r['tag']=='temperature')
 uv=next(r for r in rows if r['tag']=='uv')
 index=next(r for r in rows if r['tag']=='index')
 assert temperature['path']=='/siteData[currentConditions:1]/currentConditions[temperature:1]/temperature'
 assert temperature['native_semantics']=={'unitType':'metric','units':'C'}
 assert uv['native_semantics']=={'category':'moderate'}
 assert index['native_code']=='5'
 assert result.artifacts[0].payload_path.read_bytes()==CITY

def test_city_identity_transport_and_metnotes_empty_fail_closed(tmp_path:Path):
 name='20260906T052448.467Z_MSC_CitypageWeather_s0000280_en.xml'
 def wrong(req): return httpx.Response(200,content=listing(name) if req.url.path.endswith('/') else b'<siteData><location><name code="other"/></location></siteData>')
 a=ECCCCitypageNativeAdapter(client(wrong),base_url='https://fixture.invalid/NL')
 with pytest.raises(AdapterUnavailable,match='identity mismatch'): a.fetch(a.discover(WINDOW)[0],WINDOW,tmp_path)
 def error(_req): return httpx.Response(503)
 with pytest.raises(AdapterUnavailable,match='bounded request unavailable'): ECCCCitypageNativeAdapter(client(error),base_url='https://fixture.invalid').discover(WINDOW)
 with pytest.raises(AdapterUnavailable,match='observed empty'): discover_metnotes(client(lambda _r:httpx.Response(200,content=listing())),url='https://fixture.invalid/metnotes/')
 assert get_adapter('eccc-swob-partners-native') is None
 assert get_adapter('eccc-citypage-st-johns-native') is None
