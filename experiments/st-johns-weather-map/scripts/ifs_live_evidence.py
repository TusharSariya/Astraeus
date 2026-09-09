"""Explicit bounded live proof; never scheduled and never retains provider bodies."""
import json
from pathlib import Path
import sys
from weather_api.ifs_native import IFSNative
from weather_api.ifs_budget import SelectionBudget
s=IFSNative();budget=SelectionBudget();evidence={'kind':'live','items':[],'receipts':[]}
for product,field,level,leads,members in [
    ('atmosphere-control','2t:sfc',0,range(0,24,3),['0']),
    ('atmosphere-control','t:pl',850,[0],['0']),
    ('atmosphere-control','sot:sol',1,[0],['0']),
    ('atmosphere-ensemble','2t:sfc',0,[0],list(map(str,range(51)))),
    ('wave-ensemble','swh:sfc',0,[0],list(map(str,range(51)))),
    ('daily-probability','tpg1:sfc',0,[24],['0']),
]:
    try:
        runs=s.inventory(product,budget)
        if not runs:raise ValueError('product_unpublished')
        run=runs[0]
        for lead in leads:
            for member in members:
                item=dict(product=product,field=field,level=level,run=run['id'],lead=lead,member=member)
                try:
                    grid=s.record(product,run,lead,field,level,member,budget)
                    item.update(state='decoded',digest=grid['digest'],cells=sum(map(len,grid['values'])))
                    evidence['receipts'].extend(grid['receipts'])
                except Exception as error:item.update(state='unavailable',reason=str(error)[:500])
                evidence['items'].append(item)
                print(json.dumps(item),flush=True)
    except Exception as error:evidence['items'].append(dict(product=product,state='unavailable',reason=str(error)[:500]))
    evidence.update(input_bytes=budget.bytes,record_acquisitions=budget.records)
    Path(sys.argv[1]).write_text(json.dumps(evidence,indent=2)+'\n')
