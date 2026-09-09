"""Registered IFS reductions over already acquired members; no source I/O."""
from datetime import datetime
import hashlib
import json
from ingest.derive.registry import MemberSet,MemberValue,derive_ensemble_statistic
from registry.ifs import FIELDS,PRODUCTS
from .ifs_native import IFSUnavailable


def summarize(grids,product,field,statistic='ensemble_mean',*,quantile=None,threshold=None,comparison=None):
    definition=FIELDS[field]
    if definition['rendering'] in ('direction','categorical'):
        raise IFSUnavailable('scalar_statistics_not_applicable')
    if not grids:raise IFSUnavailable('no_member_resolved')
    expected=PRODUCTS[product]['members']
    template=next(iter(grids.values()))
    keys=('run_time','native_time','field','level','units','temporal','interval_start','interval_end',
          'latitudes','longitudes','latitude_edges','longitude_edges')
    compatible={m:g for m,g in grids.items() if m in expected and all(g[k]==template[k] for k in keys)}
    values=[];counts=[];missing_bits=[];refusals=set();method=None
    for y,row in enumerate(template['values']):
        result_row=[];count_row=[];missing_row=[]
        for x in range(len(row)):
            members=tuple(MemberValue(m,m=='0',compatible[m]['values'][y][x] if m in compatible else None,'passed') for m in expected)
            ms=MemberSet('IFS ENS' if product=='atmosphere-ensemble' else 'IFS wave ENS','ecmwf-ifs',
                datetime.fromisoformat(template['run_time']),field,len(expected),members,template['temporal']=='avg')
            result=derive_ensemble_statistic(statistic,[ms],quantile=quantile,threshold=threshold,
                threshold_units=template['units'] if threshold is not None else None,comparison=comparison)
            method=result.method
            missing_row.append(sum(1<<int(m) for m in result.members_missing))
            if result.condition_failed:refusals.add(result.condition_failed)
            if result.refusal:refusals.add(str(result.refusal))
            result_row.append(result.value);count_row.append(result.members_used)
        values.append(result_row);counts.append(count_row);missing_bits.append(missing_row)
    result_grid = {**template,'values':values,'member':None,'statistic':statistic,
        'quantile':quantile,'threshold':threshold,'comparison':comparison,
        'member_counts':counts,'missing_member_bits':missing_bits,'refusal_reasons':sorted(refusals),'missing_members':[m for m in expected if m not in compatible],
        'method':{'name':method.name,'version':method.version,'citation':method.citation} if method else None,
        'units':'1' if statistic=='ensemble_threshold_probability' else 'members' if statistic=='ensemble_member_count' else template['units']}

    inputs=sorted((m,g['digest']) for m,g in compatible.items())
    result_grid['digest']=hashlib.sha256(json.dumps([inputs,statistic,quantile,threshold,comparison,values],sort_keys=True).encode()).hexdigest()
    result_grid['expires_at']=min(g['expires_at'] for g in compatible.values())
    result_grid['retrieved_at']=max(g['retrieved_at'] for g in compatible.values())
    result_grid['control_mapping']=None
    result_grid['receipts']=list({json.dumps(r,sort_keys=True):r for g in compatible.values() for r in g['receipts']}.values())
    return result_grid
