"""IFS point/Series bridge over shared native records, with registered methods."""
from datetime import datetime,timedelta
import hashlib
import json
from registry.ifs import FIELDS,PRODUCTS,BOUNDS
from .ifs_budget import SelectionBudget
from .ifs_native import native_service,IFSUnavailable
from .models import EvidenceField,Provenance,Quality,Coverage,Freshness,DataMode
from .source_contract import SourceCapability,SourceVariant,SourceAcquisition
from .source_delivery import NativeFrame,NativePlan,ComparisonReading

ALIASES={'temperature_2m':'2t:sfc','dew_point_2m':'2d:sfc','mean_sea_level_pressure':'msl:sfc',
         'total_cloud_geometric':'tcc:sfc','wind_u_10m':'10u:sfc','wind_v_10m':'10v:sfc',
         'precipitation_accumulation':'tp:sfc','wind_gust_10m':'10fg:sfc'}
NATIVE_KEYS={'ifs_'+key.replace(':','_'):key for key in FIELDS}
DERIVED={'relative_humidity_2m':('temperature_2m','dew_point_2m'),
         'wind_speed_10m':('wind_u_10m','wind_v_10m'),'wind_direction_10m':('wind_u_10m','wind_v_10m')}


def sample(grid,latitude,longitude):
    if not BOUNDS['south']<=latitude<=BOUNDS['north'] or not BOUNDS['west']<=longitude<=BOUNDS['east']:
        raise IFSUnavailable('outside_atlantic')
    # Match indexed native cell geometry, including a deterministic midpoint tie.
    yi=min(range(len(grid['latitudes'])),key=lambda i:abs(grid['latitudes'][i]-latitude))
    xi=min(range(len(grid['longitudes'])),key=lambda i:abs(grid['longitudes'][i]-longitude))
    return grid['values'][yi][xi],grid['latitudes'][yi],grid['longitudes'][xi]


def interval_amount(current,previous):
    keys=('product','run_time','field','level','member','units','latitudes','longitudes','interval_start')
    if current['temporal']!='accum':return current
    if previous is None:raise IFSUnavailable('precipitation_predecessor_missing')
    if previous['temporal']!='accum' or any(current[k]!=previous[k] for k in keys):raise IFSUnavailable('precipitation_interval_incompatible')
    if datetime.fromisoformat(previous['interval_end'])>=datetime.fromisoformat(current['interval_end']):raise IFSUnavailable('precipitation_interval_order')
    values=[]
    for row,prior in zip(current['values'],previous['values']):
        values.append([None if a is None or b is None or a<b else a-b for a,b in zip(row,prior)])
    return {**current,'digest':hashlib.sha256(json.dumps([current['digest'],previous['digest'],values]).encode()).hexdigest(),
            'expires_at':min(current['expires_at'],previous['expires_at']),'values':values,'interval_start':previous['interval_end'],'temporal':'interval_amount',
            'receipts':[*previous['receipts'],*current['receipts']]}


class IFSSource:
    source_id='ecmwf-ifs'
    product_id='ifs'
    def __init__(self,native=None,product='atmosphere-control',level=0,variant=None):
        self.native=native or native_service();self.product=product;self.level=level;self.variant=variant
        self.product_id='ifs' if product=='atmosphere-control' else product

    def for_selection(self,selection):
        return IFSSource(self.native,selection.product_id if selection.product_id not in (None,'ifs') else 'atmosphere-control',selection.level or 0,selection.variant)


    def descriptors(self):
        capabilities=[]
        for key in (*ALIASES,*DERIVED):
            capabilities.append(SourceCapability(source_id=self.source_id,product_id=self.product_id,field=key,
                variants=[SourceVariant(kind='deterministic')],levels=['sfc'],point=True,grid=key in ALIASES,
                point_product='IFS',native_series=True,point_time_kind='forecast',directional_time_selection=True,
                run_selection='latest_previous',time_semantics='Pinned advertised IFS native times; exact intervals preserved',
                coverage_description='Atlantic native cells: 70 W to 40 W, 40 N to 55 N'))
        for key,native in NATIVE_KEYS.items():
            definition=FIELDS[native]
            for product in definition['products']:
                members=PRODUCTS[product]['members']
                variants=[SourceVariant(kind='member',member=m) for m in members] if members else [SourceVariant(kind='deterministic')]
                if members and definition['rendering'] not in ('direction','categorical'):
                    variants.insert(0,SourceVariant(kind='derived_statistic',statistic='ensemble_mean'))
                capabilities.append(SourceCapability(source_id=self.source_id,product_id=product,field=key,
                    variants=variants,levels=[str(n) for n in definition.get('product_levels',{}).get(product,definition['levels'])],
                    point=False,grid=True,point_product=product,native_series=True,point_time_kind='forecast',
                    directional_time_selection=True,run_selection='latest_previous',
                    time_semantics='Use IFS selection delivery for native fields, levels and variants',
                    coverage_description='Atlantic native cells: 70 W to 40 W, 40 N to 55 N'))
        return tuple(capabilities)

    def plan_series(self,start,end,*,run='latest',budget=None):
        budget=budget or SelectionBudget();runs=self.native.inventory(self.product,budget)
        selected=next((r for r in runs if run in ('latest',r['id'])),None)
        if selected is None:raise IFSUnavailable('run_expired' if run!='latest' else 'product_unpublished')
        origin=datetime.fromisoformat(selected['run_time'])
        available=tuple(origin+timedelta(hours=lead) for lead in sorted(selected['files']) if lead>=0)
        return NativePlan(tuple(NativeFrame(t,selected['id'],origin) for t in available if start<=t<end),
            reason='Actual advertised IFS control run; fields are verified on acquisition',available_times=available)

    def resolve_point_time(self,selected):
        plan=self.plan_series(selected,selected+timedelta(days=16))
        if not plan.frames:raise IFSUnavailable('time_unpublished')
        return plan.frames[0].valid_time

    def read_point(self,latitude,longitude,selected,*,run='latest',refresh=False):
        budget=SelectionBudget();runs=self.native.inventory(self.product,budget,refresh=refresh)
        chosen=next((r for r in runs if run in ('latest',r['id'])),None)
        if chosen is None:raise IFSUnavailable('run_expired')
        return self.read_comparison(latitude,longitude,NativeFrame(selected,chosen['id'],datetime.fromisoformat(chosen['run_time'])),
            tuple((*ALIASES,*DERIVED)),budget=budget).fields

    def read_comparison(self,latitude,longitude,frame,fields,*,spread=False,budget=None):
        budget=budget or SelectionBudget();runs=self.native.inventory(self.product,budget)
        run=next((r for r in runs if r['id']==frame.run_id),None)
        if run is None:raise IFSUnavailable('run_expired')
        origin=datetime.fromisoformat(run['run_time']);hours=(frame.valid_time-origin).total_seconds()/3600
        if not hours.is_integer():raise IFSUnavailable('non_native_time')
        lead=int(hours);needed=set(fields)
        for key in fields:needed.update(DERIVED.get(key,()))
        results={};failures={};member_inputs={};intervals={};member_values={};member_units={}
        for key in sorted(needed):
            if key not in ALIASES and key not in NATIVE_KEYS:continue
            try:
                native_field=ALIASES.get(key) or NATIVE_KEYS[key]
                level=self.level if FIELDS[native_field]['level_type']!='sfc' else 0
                members=PRODUCTS[self.product]['members'] or ['0']
                acquired={}
                for member in members:
                    try:acquired[member]=self.native.record(self.product,run,lead,native_field,level,member,budget)
                    except Exception:
                        if len(members)==1:raise
                member_inputs[key]=acquired
                if not acquired:raise IFSUnavailable('no_member_resolved')
                if key=='precipitation_accumulation':
                    previous_lead=max((n for n in run['files'] if 0<=n<lead),default=None)
                    amounts={}
                    for member,g in acquired.items():
                        try:
                            previous=self.native.record(self.product,run,previous_lead,native_field,level,member,budget) if previous_lead is not None else None
                            amounts[member]=interval_amount(g,previous)
                        except Exception:continue
                    acquired=amounts
                    if not acquired:raise IFSUnavailable('precipitation_predecessor_missing')
                grid=next(iter(acquired.values()))
                if len(members)>1:
                    from .ifs_statistics import summarize
                    # Point reduction invokes the same registered method on one native cell.
                    cells={m:{**g,'values':[[sample(g,latitude,longitude)[0]]]} for m,g in acquired.items()}
                    requested_member=getattr(self.variant,'member',None)
                    if requested_member is not None:
                        grid=acquired.get(requested_member)
                        if grid is None:raise IFSUnavailable('selected_member_missing')
                    else:
                        summary=summarize(cells,self.product,native_field,getattr(self.variant,'statistic',None) or 'ensemble_mean',
                            quantile=getattr(self.variant,'quantile',None),threshold=getattr(self.variant,'threshold',None),comparison=getattr(self.variant,'comparison',None))
                        value=summary['values'][0][0]
                        _,lat,lon=sample(grid,latitude,longitude)
                        # Preserve the native geometry for the public point; no grid is fabricated.

                if len(members)==1 or getattr(self.variant,'member',None) is not None:value,lat,lon=sample(grid,latitude,longitude)
                if grid['interval_start']!=grid['interval_end']:intervals[key]=(datetime.fromisoformat(grid['interval_start']),datetime.fromisoformat(grid['interval_end']))
                if len(members)>1:member_values[key]={m:sample(acquired[m],latitude,longitude)[0] if m in acquired else None for m in members}
                member_units[key]=grid['units']
                is_summary=len(members)>1 and getattr(self.variant,'member',None) is None
                statistic=summary['statistic'] if is_summary else None
                units=summary['units'] if is_summary else grid['units']
                if value is not None:
                    if key in NATIVE_KEYS or statistic in ('ensemble_member_count','ensemble_threshold_probability'):pass
                    elif units=='K':
                        if statistic!='ensemble_spread' and self.product!='ensemble-standard-deviation':value-=273.15
                        units='degC'
                    elif units=='Pa':value/=100;units='hPa'
                    elif key=='total_cloud_geometric':value*=100;units='percent'
                    elif key=='precipitation_accumulation':value*=1000;units='mm'
                receipt=SourceAcquisition(source_id=self.source_id,product_id=self.product_id,provider_run_id=run['id'],run_time=origin,
                    valid_time=frame.valid_time,retrieval_time=grid['retrieved_at'],expires_at=grid['expires_at'],
                    normalized_sha256=grid['digest'],transport_receipts=grid['receipts'])
                p=Provenance(data_mode=DataMode.LIVE,evidence_class='retrieved',source_id=self.source_id,provider='ECMWF',product=self.product,forecast_centre='ECMWF',
                    run_time=origin,valid_time=frame.valid_time,retrieval_time=grid['retrieved_at'],vertical_level=str(level)+' '+FIELDS[native_field]['level_type'],
                    original_units=grid['units'],normalized_units=units,native_resolution='0.25 degrees',native_crs='EPSG:4326',
                    quality=Quality(status='passed' if value is not None else 'unknown',flags=[] if value is not None else ['native_fill_mask']),
                    coverage=Coverage(status='complete'),freshness=Freshness(status='unknown'),licence='CC BY 4.0',attribution='ECMWF',
                    adapter_version='ifs-atlantic-v1',source_display_primary=False,sampled_latitude=lat,sampled_longitude=lon,
                    sample_method='rectilinear',source_acquisition=receipt,native_variable=FIELDS[native_field]['parameter'])
                from .ifs_budget import register_receipts
                p.source_receipt_manifest=register_receipts(budget,[r for g in acquired.values() for r in g['receipts']])
                if len(members)>1:
                    if getattr(self.variant,'member',None) is not None:
                        p.member=self.variant.member;p.member_control=self.variant.member=='0'
                    else:
                        self.summary_provenance(p,summary,cells,native_field)
                if self.product in ('ensemble-mean','ensemble-standard-deviation','daily-probability','temperature-probability','wave-probability'):
                    from .models import EnsembleProvenance
                    statistic='ensemble_mean' if self.product=='ensemble-mean' else 'ensemble_spread' if self.product=='ensemble-standard-deviation' else 'ensemble_threshold_probability'
                    p.ensemble=EnsembleProvenance(family=self.product,statistic=statistic,computed_here=False,member_set=None)
                results[key]=EvidenceField(field=key,key=key,value=value,provenance=p,storage='available-not-stored')
            except Exception as error:failures[key]=str(error) if isinstance(error,IFSUnavailable) else type(error).__name__
        from ingest.derive.registry import derive_relative_humidity,derive_wind
        for key in fields:
            if key not in DERIVED:continue
            inputs=[results.get(k) for k in DERIVED[key]]
            if not all(inputs):failures[key]='matching_native_dependencies_missing';continue
            if any((p.provenance.sampled_latitude,p.provenance.sampled_longitude)!=(inputs[0].provenance.sampled_latitude,inputs[0].provenance.sampled_longitude) for p in inputs):
                failures[key]='native_dependency_cell_mismatch';continue
            if PRODUCTS[self.product]['members'] and getattr(self.variant,'member',None) is None:
                derived_cells={}
                for member in PRODUCTS[self.product]['members']:
                    pair=[member_inputs.get(k,{}).get(member) for k in DERIVED[key]]
                    if not all(pair):continue
                    a,lat1,lon1=sample(pair[0],latitude,longitude);b,lat2,lon2=sample(pair[1],latitude,longitude)
                    if (lat1,lon1)!=(lat2,lon2):continue
                    if key=='relative_humidity_2m':
                        derived=derive_relative_humidity(a-273.15 if a is not None else None,b-273.15 if b is not None else None);v=derived.value
                    else:
                        derived=derive_wind(a,b);v=derived.speed if key=='wind_speed_10m' else derived.direction
                    derived_cells[member]={**pair[0],'field':key,'units':'percent' if key=='relative_humidity_2m' else 'm/s',
                        'values':[[v]],'digest':hashlib.sha256(json.dumps([key,[g['digest'] for g in pair],v]).encode()).hexdigest(),
                        'expires_at':min(g['expires_at'] for g in pair),'receipts':[r for g in pair for r in g['receipts']]}
                if key=='wind_direction_10m':failures[key]='scalar_statistics_not_applicable';continue
                if not derived_cells:failures[key]='matching_native_dependencies_missing';continue
                from .ifs_statistics import summarize
                basis=ALIASES[DERIVED[key][0]]
                summary=summarize(derived_cells,self.product,basis,getattr(self.variant,'statistic',None) or 'ensemble_mean',
                    quantile=getattr(self.variant,'quantile',None),threshold=getattr(self.variant,'threshold',None),comparison=getattr(self.variant,'comparison',None))
                member_values[key]={m:g['values'][0][0] for m,g in derived_cells.items()}
                member_units[key]='percent' if key=='relative_humidity_2m' else 'm/s'
                p=inputs[0].provenance.model_copy(deep=True)
                p.normalized_units=summary['units']
                self.summary_provenance(p,summary,derived_cells,key)
                from .models import DerivationStep,DerivedInput
                if derived.method:p.derivation_steps=[DerivationStep(name=derived.method.name,version=derived.method.version,citation=derived.method.citation),DerivationStep(**summary['method'])]
                p.derivation_inputs=[DerivedInput(field=f.key,source_id=f.provenance.source_id,product=f.provenance.product,
                    valid_time=f.provenance.valid_time,run_time=f.provenance.run_time,units=f.provenance.original_units,
                    evidence_class=f.provenance.evidence_class,quality=f.provenance.quality) for f in inputs]
                results[key]=EvidenceField(field=key,key=key,value=summary['values'][0][0],provenance=p,storage='available-not-stored',phase='liquid' if key=='relative_humidity_2m' else None)
                continue
            a,b=(f.value for f in inputs)
            derived=derive_relative_humidity(a,b) if key=='relative_humidity_2m' else derive_wind(a,b)
            if key=='relative_humidity_2m':value=derived.value
            else:value=derived.speed if key=='wind_speed_10m' else derived.direction
            p=inputs[0].provenance.model_copy(deep=True)
            p.evidence_class='derived_here';p.normalized_units='percent' if key=='relative_humidity_2m' else 'm/s' if key=='wind_speed_10m' else 'degrees'
            if derived.method:
                p.derivation=derived.method.name;p.derivation_version=derived.method.version;p.derivation_citation=derived.method.citation
            p.quality.flags=list(derived.flags if key=="relative_humidity_2m" else derived.speed_flags if key=="wind_speed_10m" else derived.direction_flags)
            from .models import DerivedInput
            p.derivation_inputs=[DerivedInput(field=f.key,source_id=f.provenance.source_id,product=f.provenance.product,
                valid_time=f.provenance.valid_time,run_time=f.provenance.run_time,units=f.provenance.normalized_units,
                evidence_class=f.provenance.evidence_class,quality=f.provenance.quality) for f in inputs]
            results[key]=EvidenceField(field=key,key=key,value=value,provenance=p,storage='available-not-stored',phase='liquid' if key=='relative_humidity_2m' else None)
        bands={}
        if spread and PRODUCTS[self.product]['members']:
            from ingest.derive.registry import MemberSet,MemberValue,derive_ensemble_statistic
            for key in fields:
                if key not in results or key not in member_values or key=='wind_direction_10m':continue
                native=ALIASES.get(key) or NATIVE_KEYS.get(key)
                if native and FIELDS[native]['rendering'] in ('direction','categorical'):continue
                values=member_values[key]
                ms=MemberSet(self.product,self.source_id,origin,key,51,tuple(MemberValue(m,m=='0',values.get(m),'passed') for m in PRODUCTS[self.product]['members']))
                bounds=[]
                for quantile in (.1,.9):
                    stat=derive_ensemble_statistic('ensemble_quantile',[ms],quantile=quantile)
                    value=stat.value
                    if value is not None:
                        if member_units.get(key)=='K' and results[key].provenance.normalized_units=='degC':value-=273.15
                        elif member_units.get(key)=='Pa' and results[key].provenance.normalized_units=='hPa':value/=100
                        elif member_units.get(key)=='m' and results[key].provenance.normalized_units=='mm':value*=1000
                        elif member_units.get(key)=='(0 - 1)' and results[key].provenance.normalized_units=='percent':value*=100
                    bound=results[key].model_copy(deep=True);bound.value=value
                    bound.provenance.derivation=stat.method.name;bound.provenance.derivation_version=stat.method.version;bound.provenance.derivation_citation=stat.method.citation
                    if bound.provenance.ensemble:bound.provenance.ensemble.statistic='ensemble_quantile';bound.provenance.ensemble.quantile=quantile
                    bounds.append(bound)
                bands[key]=tuple(bounds)
        return ComparisonReading(tuple(results[k] for k in sorted(needed) if k in results),failures,intervals,member_values,member_units,bands)


    def summary_provenance(self,p,summary,cells,field):
        from .models import EnsembleProvenance,EnsembleMemberSet
        expected=PRODUCTS[self.product]['members']
        used=[m for m,g in cells.items() if g['values'][0][0] is not None]
        p.evidence_class='derived_here';p.quality.flags=['derived']+(['partial_member_set'] if len(used)<len(expected) else [])
        p.artifact_revision=summary['digest']
        p.source_acquisition=None  # All-member receipts live in source-selection manifests, not a single member receipt.
        p.derivation=summary['method']['name'];p.derivation_version=summary['method']['version'];p.derivation_citation=summary['method']['citation']
        p.ensemble=EnsembleProvenance(family=self.product,statistic=summary['statistic'],computed_here=True,
            quantile=summary.get('quantile'),threshold=summary.get('threshold'),comparison=summary.get('comparison'),
            threshold_units=next(iter(cells.values()))['units'] if summary.get('threshold') is not None else None,
            member_set=EnsembleMemberSet(family=self.product,source_id=self.source_id,run_time=p.run_time,
                members_declared=len(expected),members_used=len(used),members_missing=[m for m in expected if m not in used],
                control_included='0' in used,partial=len(used)<len(expected)))
