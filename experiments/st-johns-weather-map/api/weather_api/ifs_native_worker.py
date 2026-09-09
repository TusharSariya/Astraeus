"""One exact GRIB message, validated and cropped before bounded JSON output."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys


def decode(request):
    import eccodes as ec
    import numpy as np
    from registry.ifs import PRODUCTS, field_selection
    definition=field_selection(request['product'],request['field'],request['level'])
    product=PRODUCTS[request['product']]
    path=Path(request['path'])
    if path.stat().st_size!=request['record']['_length'] or path.stat().st_size>8*1024**2:
        raise ValueError('record_size_mismatch')
    run=datetime.fromisoformat(request['run_time']);valid=run+timedelta(hours=request['lead'])
    with path.open('rb') as handle:
        gid=ec.codes_grib_new_from_file(handle)
        if gid is None:raise ValueError('missing_grib_message')
        try:
            keys=('paramId','shortName','units','stepType','startStep','endStep','dataDate','dataTime','validityDate','validityTime',
                  'marsClass','marsStream','dataType','typeOfLevel','level','gridType','iDirectionIncrementInDegrees','jDirectionIncrementInDegrees')
            metadata={k:ec.codes_get(gid,k) for k in keys}
            expected={'marsClass':'od','marsStream':product['stream'],'dataType':product['record_type'],
                      'dataDate':int(run.strftime('%Y%m%d')),'dataTime':int(run.strftime('%H%M')),
                      'validityDate':int(valid.strftime('%Y%m%d')),'validityTime':int(valid.strftime('%H%M')),
                      'endStep':request['lead'],'gridType':'regular_ll','iDirectionIncrementInDegrees':.25,'jDirectionIncrementInDegrees':.25}
            if metadata['paramId'] not in definition['param_ids'] or any(metadata[k]!=v for k,v in expected.items()):
                raise ValueError('native_record_identity_mismatch')
            if metadata['units']!=definition['units']:raise ValueError('native_units_mismatch')
            if definition['level_type']=='sfc' and (metadata['typeOfLevel']!=definition['native_level_type'] or metadata['level']!=definition['native_level']):
                raise ValueError('native_surface_level_mismatch')
            if definition['level_type']=='pl' and (metadata['typeOfLevel']!='isobaricInhPa' or metadata['level']!=request['level']):
                raise ValueError('native_pressure_level_mismatch')
            if definition['level_type']=='sol' and (metadata['typeOfLevel'] not in ('depthBelowLandLayer','soilLayer') or metadata['level']!=request['level']):
                raise ValueError('native_soil_level_mismatch')
            if product['record_type']=='pf' and str(ec.codes_get(gid,'perturbationNumber'))!=request['member']:
                raise ValueError('native_member_mismatch')
            if metadata['stepType'] not in ('instant','accum','avg','max','min','prob') or metadata['startStep']>metadata['endStep']:
                raise ValueError('native_interval_invalid')
            indexed=str(request['record']['step']).split('-')
            if len(indexed)==2 and metadata['startStep']!=int(indexed[0]):raise ValueError('native_interval_start_mismatch')
            if definition['temporal'] in ('instant','static') and metadata['stepType']!='instant':raise ValueError('native_instant_required')
            if definition['temporal']=='average' and metadata['stepType']!='avg':raise ValueError('native_average_required')
            if definition['temporal']=='accumulation' and metadata['stepType']!='accum':raise ValueError('native_accumulation_required')
            if definition['temporal']=='maximum' and metadata['stepType']!='max':raise ValueError('native_maximum_required')
            if definition['temporal']=='minimum' and metadata['stepType']!='min':raise ValueError('native_minimum_required')
            if definition['temporal']=='static' and request['lead']!=0:raise ValueError('static_field_step_mismatch')
            lat=ec.codes_get_array(gid,'latitudes');lon=ec.codes_get_array(gid,'longitudes');values=ec.codes_get_values(gid)
            lon=(lon+180)%360-180
            if len(lat)!=len(values) or len(lon)!=len(values):raise ValueError('native_geometry_invalid')
            bounds=request['bounds'];mask=(lat>=bounds['south'])&(lat<=bounds['north'])&(lon>=bounds['west'])&(lon<=bounds['east'])
            lat,lon,values=lat[mask],lon[mask],values[mask]
            ys=np.unique(lat)[::-1];xs=np.unique(lon)
            if len(ys)!=61 or len(xs)!=121 or len(values)!=len(ys)*len(xs) or not np.allclose(np.diff(xs),.25) or not np.allclose(np.diff(ys),-.25):
                raise ValueError('native_atlantic_geometry_mismatch')
            order=np.lexsort((lon,-lat));lat,lon,values=lat[order],lon[order],values[order]
            if not np.array_equal(lat,np.repeat(ys,len(xs))) or not np.array_equal(lon,np.tile(xs,len(ys))):raise ValueError('native_cells_ambiguous')
            missing=ec.codes_get(gid,'missingValue')
            finite=np.isfinite(values)&(values!=missing)
            if np.isinf(values).any():raise ValueError('native_infinite_value')
            vals=[float(v) if ok else None for v,ok in zip(values,finite)]
            rows=[vals[i:i+len(xs)] for i in range(0,len(vals),len(xs))]
        finally:ec.codes_release(gid)
        extra=ec.codes_grib_new_from_file(handle)
        if extra is not None:
            ec.codes_release(extra);raise ValueError('multiple_grib_messages')
    def edges(axis):return [float(axis[0]+(axis[0]-axis[1])/2)]+[float((a+b)/2) for a,b in zip(axis,axis[1:])]+[float(axis[-1]+(axis[-1]-axis[-2])/2)]
    return {'run_time':run.isoformat(),'native_time':valid.isoformat(),'units':metadata['units'],'temporal':metadata['stepType'],
            'interval_start':(run+timedelta(hours=metadata['startStep'])).isoformat(),'interval_end':valid.isoformat(),
            'latitudes':ys.tolist(),'longitudes':xs.tolist(),'latitude_edges':edges(ys),'longitude_edges':edges(xs),
            'values':rows,'native_metadata':metadata,'region':[-70,40,-40,55]}


if __name__=='__main__':
    result=decode(json.loads(sys.stdin.buffer.read()))
    body=json.dumps(result,allow_nan=False).encode()
    if len(body)>16*1024**2:raise ValueError('decoder_output_bound')
    Path(sys.argv[1]).write_bytes(body)
