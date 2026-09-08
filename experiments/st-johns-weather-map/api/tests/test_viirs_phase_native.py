from hashlib import sha256
import sys
import numpy as np
import netCDF4
import pytest
from ingest.experimental.viirs_phase_native import PhaseObject, inspect_native_cell

KEY = 'VIIRS-JRR-CloudPhase/2026/09/07/JRR-CloudPhase_v3r2_j01_s202609072202258_e202609072203503_c202609072257324.nc'


def fixture(path, *, units='1', platform='NOAA-20'):
    with netCDF4.Dataset(path, 'w') as ds:
        for name, size in [('Rows', 2), ('Columns', 3), ('CloudPhaseFlagConst', 1), ('CloudPhasePackedConst', 6)]:
            ds.createDimension(name, size)
        ds.setncatts({'Metadata_Link': KEY.rsplit('/',1)[-1], 'satellite_name': platform,
                     'title':'JRR_CloudPhase','cdm_data_type':'swath','history_package':'Delivery Package v3r2',
                     'time_coverage_start':'2026-09-07T22:02:25Z','time_coverage_end':'2026-09-07T22:03:50Z'})
        for name, unit in [('Latitude','degrees_north'),('Longitude','degrees_east')]:
            v=ds.createVariable(name,'f4',('Rows','Columns'),fill_value=-999.)
            v.units=unit
            v[:]=np.array([[47,47.1,47.2],[48,48.1,48.2]]) if name=='Latitude' else -53
        for name, extra in [('CloudPhase',()),('CloudType',()),('CloudPhaseFlag',('CloudPhaseFlagConst',)),('CloudTypePacked',('CloudPhasePackedConst',))]:
            v=ds.createVariable(name,'i1',('Rows','Columns')+extra,fill_value=-128)
            v.units=units
            v[:]=0
            if name=='CloudPhase':v[:]=np.arange(6).reshape(2,3)
            if name=='CloudTypePacked':v[1,2,:]=[-128,-1,0,1,2,127]
        v=ds.createVariable('granule_level_quality_flag','i8',(),fill_value=-999)
        v[...]=1
        v.units='1'
    body=path.read_bytes()
    return body,PhaseObject(KEY,len(body),sha256(body).hexdigest())


@pytest.mark.skipif(sys.platform!='linux',reason='native leaf requires Linux kernel allocation limits')
def test_actual_leaf_preserves_codes_signed_flags_geometry_and_unknown_qc(tmp_path):
    body,source=fixture(tmp_path/'native.nc')
    result=inspect_native_cell(body,source,1,2)
    assert result['cell']['CloudPhase']['raw']==5
    assert result['cell']['CloudPhaseFlag']['raw']==[0]
    assert result['cell']['CloudTypePacked']['raw']==[-128,-1,0,1,2,127]
    assert result['cell']['CloudTypePacked']['is_fill']==[True,False,False,False,False,False]
    assert result['cell']['Latitude']['raw']==pytest.approx(48.2)
    assert result['cell']['Longitude']['raw']==-53
    assert result['granule_quality']['raw']==1
    assert result['quality_state']=='unknown' and not result['operational']
    assert result['source_sha256']==source.sha256
    assert result['metadata']['time_coverage_start']=='2026-09-07T22:02:25Z'


@pytest.mark.skipif(sys.platform!='linux',reason='native leaf requires Linux kernel allocation limits')
@pytest.mark.parametrize('kwargs',[{'units':'percent'},{'platform':'NOAA-21'}])
def test_native_field_or_product_substitution_refused(tmp_path,kwargs):
    body,source=fixture(tmp_path/'wrong.nc',**kwargs)
    with pytest.raises(Exception,match='mismatch'):
        inspect_native_cell(body,source,0,0)


@pytest.mark.parametrize('key',[KEY.replace('j01','n21'),KEY.replace('/09/07/','/09/06/'),KEY.replace('v3r2','v3r3'),KEY.replace('CloudPhase','CloudHeight')])
def test_explicit_product_identity_is_narrow(key):
    with pytest.raises(ValueError):PhaseObject(key,10,'a'*64)


def test_raw_digest_and_index_fail_before_native_decode(tmp_path):
    body,source=fixture(tmp_path/'native.nc')
    with pytest.raises(ValueError,match='digest'):inspect_native_cell(body+b'x',source,0,0)
    for row,column in [(-1,0),(0,3200),(True,0),(0,1.5)]:
        with pytest.raises(ValueError,match='bounds'):inspect_native_cell(body,source,row,column)
