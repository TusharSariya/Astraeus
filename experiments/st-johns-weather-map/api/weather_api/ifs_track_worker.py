"""Bounded ECMWF tropical-cyclone BUFR decoding, retaining native member tracks.

Uses ECMWF's documented ranked tropical-cyclone descriptor layout; unknown
layouts are refused, not interpreted as grid fields.
"""
from datetime import UTC,datetime,timedelta
import json
from pathlib import Path
import sys


def decode(request):
    import eccodes as ec
    run=datetime.fromisoformat(request['run_time']);tracks=[];decoded=set()
    with open(request['path'],'rb') as stream:
        for message in range(256):
            g=ec.codes_bufr_new_from_file(stream)
            if g is None:break
            try:
                ec.codes_set(g,'unpack',1)
                origin=datetime(*(int(ec.codes_get(g,k)) for k in ('year','month','day','hour','minute')),tzinfo=UTC)
                if origin!=run or ec.codes_get(g,'bufrHeaderCentre')!=98:raise ValueError('track_run_or_producer_mismatch')
                storm=str(ec.codes_get(g,'stormIdentifier'))
                members=[str(int(n)) for n in ec.codes_get_array(g,'ensembleMemberNumber')]
                if not members or len(members)>256 or any(n not in map(str,range(256)) for n in members):raise ValueError(f'track_members_invalid: count={len(members)} values={members[:8]}')
                decoded.update(members)
                by_member={n:[] for n in members}
                first=int(ec.codes_get_array(g,'#1#meteorologicalAttributeSignificance')[0])
                analysis_rank=2 if first==1 else 1 if first in (4,5) else None
                if analysis_rank is None:raise ValueError(f'track_initial_layout:{first}')
                for step in range(122):
                    if step==0:lead=0;rank=analysis_rank;significance=4
                    else:
                        try:period=ec.codes_get_array(g,f'#{step}#timePeriod')
                        except ec.CodesInternalError:break
                        periods={int(n) for n in period if n!=ec.CODES_MISSING_LONG}
                        if len(periods)!=1:raise ValueError('track_time_ambiguous')
                        lead=periods.pop();rank=2*step+analysis_rank;significance=1
                    if not 0<=lead<=360:raise ValueError('track_time_bound')
                    sig=ec.codes_get_array(g,f'#{rank}#meteorologicalAttributeSignificance')
                    if len(sig) not in (1,len(members)):raise ValueError('track_significance_shape')
                    for i,member in enumerate(members):
                        code=int(sig[i if len(sig)>1 else 0])
                        expected=(significance,5) if member in ('51','52') else (significance,)
                        if code not in (*expected,ec.CODES_MISSING_LONG):raise ValueError('track_layout_unrecognized')
                    lat=ec.codes_get_array(g,f'#{rank}#latitude');lon=ec.codes_get_array(g,f'#{rank}#longitude')
                    if len(lat) not in (1,len(members)) or len(lon) not in (1,len(members)):raise ValueError('track_coordinate_shape')
                    for i,member in enumerate(members):
                        y=float(lat[i if len(lat)>1 else 0]);x=float(lon[i if len(lon)>1 else 0])
                        if y==ec.CODES_MISSING_DOUBLE or x==ec.CODES_MISSING_DOUBLE:continue
                        if not -90<=y<=90 or not -180<=x<=360:raise ValueError('track_coordinate_invalid')
                        x=(x+180)%360-180
                        by_member[member].append({'time':(run+timedelta(hours=lead)).isoformat(),'latitude':y,'longitude':x})
                else:raise ValueError('track_step_bound')
                for member,points in by_member.items():
                    # Keep whole paths that intersect the Atlantic so native times and
                    # dissipation remain intelligible. Rendering clips at the map.
                    if any(40<=p['latitude']<=55 and -70<=p['longitude']<=-40 for p in points):
                        tracks.append({'storm_id':storm,'member':member,'points':points})
            finally:ec.codes_release(g)
        else:raise ValueError('track_message_bound')
    return {'run_time':run.isoformat(),'tracks':tracks,'decoded_members':sorted(decoded,key=int)}


if __name__=='__main__':
    body=json.dumps(decode(json.loads(sys.stdin.buffer.read())),allow_nan=False).encode()
    if len(body)>16*1024**2:raise ValueError('track_output_bound')
    Path(sys.argv[1]).write_bytes(body)
