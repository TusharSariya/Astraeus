"""Bounded opt-in live catalogue/frame contract check. No point acquisition."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', default='http://127.0.0.1:8197/api/experiments/weather/v0')
parser.add_argument('--fetch-images', action='store_true')
parser.add_argument('--output', default='/tmp/astraeus-layer-inventory-live.json')
args = parser.parse_args()

def read(path):
    with urlopen(args.base+path, timeout=45) as response:
        return json.load(response)

def instant(text):
    return datetime.fromisoformat(text.replace('Z','+00:00'))

reference = instant(read('/health')['time']).replace(minute=0,second=0,microsecond=0)
start,end=reference-timedelta(days=1),reference+timedelta(days=14)
catalogues=[]
violations=[]
images={}
for product in [None,'HRDPS','GFS','CAP','OVATION']:
    body=read('/layers'+('' if product is None else '?'+urlencode({'product':product})))
    rows=[]
    for layer in body.get('layers',[]):
        inventory=layer.get('imagery_availability',{})
        axes={'samples':layer.get('times',[]),'frames':[frame['valid_time'] for frame in layer.get('frames',[])],'images':inventory.get('times',[])}
        for name,times in axes.items():
            for time in times:
                if not start <= instant(time) <= end: violations.append({'layer':layer['id'],'axis':name,'time':time})
        rows.append({'id':layer['id'],'axes':axes,'imagery_status':inventory.get('status'),'imagery_reason':inventory.get('reason')})
        if inventory.get('status')=='known' and axes['images'] and layer.get('raster_available'):
            images[layer['id']]=max(axes['images'],key=instant)
    catalogues.append({'product':product,'data_mode':body.get('data_mode'),'layers':rows,'notices':body.get('notices',[])})

def image_check(item):
    identifier,time=item
    path='/layers/'+identifier+'/raster?'+urlencode({'valid_time':time,'width':256,'height':256,'south':46.6,'north':48.2,'west':-54.3,'east':-52.4,'crs':'EPSG:3857'})
    try:
        with urlopen(args.base+path,timeout=30) as response:
            payload=response.read(2_000_001)
            return {'id':identifier,'requested_time':time,'status':response.status,'bytes':len(payload),'content_type':response.headers.get('Content-Type'),'served_time':response.headers.get('X-Weather-Valid-Time'),'retrieval_status':response.headers.get('X-Weather-Retrieval-Status')}
    except HTTPError as error:
        return {'id':identifier,'requested_time':time,'status':error.code,'reason':error.read(2048).decode(errors='replace')}
    except Exception as error:
        return {'id':identifier,'requested_time':time,'error':str(error)}

checks=[]
if args.fetch_images:
    assert len(images)<=32, 'Refusing more than 32 image probes'
    with ThreadPoolExecutor(max_workers=2) as pool: checks=list(pool.map(image_check,images.items()))
report={'checked_at':datetime.now(UTC).isoformat(),'window_start':start.isoformat(),'window_end':end.isoformat(),'catalogues':catalogues,'violations':violations,'image_checks':checks}
Path(args.output).write_text(json.dumps(report,indent=2))
print(json.dumps({'catalogues':len(catalogues),'violations':violations,'image_checks':checks},indent=2))
assert not violations, 'Catalogue advertised frames outside the serving window'
assert not any(row.get('status')==422 and 'outside the available window' in row.get('reason','') for row in checks), 'Advertised image rejected by serving-window validation'
