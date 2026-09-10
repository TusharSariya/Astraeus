import { useEffect, useRef, useState } from 'react'
import type { components } from '../generated/source-api'
import type { LocationPoint } from '../types'
import type { TimeRow } from './sourceTimes'
import { wn3Request } from './sourceGrid'
import './weatherNext.css'

type S = components['schemas']
export type WeatherPage = S['WeatherNextPage']
type Summary = S['WeatherNextSummary']
type Sample = S['WeatherNextSample']
type Threshold = S['Threshold']
type Bounds = S['ProbabilityBounds']
type Section = S['WeatherNextSelectionRequest']['section']
const ENDPOINT = '/api/experiments/weather/v0/weathernext/selection'
const sections = [['clouds','Clouds'],['temperature','Temperature'],['wind','Wind'],['precipitation','Precipitation'],['solar','Solar'],['pressure_sea','Pressure & sea']] as const
const statistics = ['p10','p25','p50','p75','p90','mean']
const names: Record<string,string> = {total_cloud_cover:'Total',low_cloud_cover:'Low',medium_cloud_cover:'Middle',high_cloud_cover:'High',temperature_2m:'Air temperature',dewpoint_temperature_2m:'Dew point',station_head_temperature_2m:'Air temperature · station-trained',station_head_dewpoint_temperature_2m:'Dew point · station-trained',wind_speed_10m:'Wind speed · 10 m',wind_speed_100m:'Wind speed · 100 m',total_precipitation_1hr:'Precipitation · model-native',imerg_tp_1hr:'Precipitation · IMERG',experimental_tp_1hr:'Precipitation · experimental',surface_solar_radiation_downwards_1hr:'Downward solar energy',total_sky_direct_solar_radiation_at_surface_1hr:'Direct solar energy',mean_sea_level_pressure:'Sea-level pressure',sea_surface_temperature:'Sea-surface temperature'}
const fields = {clouds:['total_cloud_cover','low_cloud_cover','medium_cloud_cover','high_cloud_cover'],temperature:['temperature_2m','dewpoint_temperature_2m'],wind:['wind_speed_10m','wind_speed_100m'],precipitation:['total_precipitation_1hr'],solar:['surface_solar_radiation_downwards_1hr','total_sky_direct_solar_radiation_at_surface_1hr'],pressure_sea:['mean_sea_level_pressure','sea_surface_temperature']}
const unitFor = (q:string) => q.includes('cloud')?'percent':q.includes('temperature')?'degC':q.includes('wind')?'m/s':q.includes('pressure')?'hPa':q.includes('solar')?'J/m2':'mm'
const unitLabel = (u:string) => ({percent:'%',degC:'°C','J/m2':'J/m²'}[u] ?? u)
const stamp = (t:string|number) => new Date(t).toISOString().replace('T',' ').slice(0,16)+' UTC'
const fresh = (s:Sample,now:number) => !s.expires_at || Date.parse(s.expires_at)>now
const number = (v:unknown):v is number => typeof v==='number' && Number.isFinite(v)
const format = (v:unknown) => number(v)?v.toLocaleString(undefined,{maximumFractionDigits:2}):'Missing'
export function appendWeatherPage(old:WeatherPage|null,page:WeatherPage):WeatherPage {
 if(!old)return page
 if(old.id!==page.id || old.run_id!==page.run_id || old.run_time!==page.run_time || JSON.stringify(old.selection)!==JSON.stringify(page.selection))throw new Error('Pinned WeatherNext selection changed')
 const samples=new Map(old.samples.map(s=>[s.time,s]))
 for(const sample of page.samples){
   const previous=samples.get(sample.time)
   samples.set(sample.time,previous?{...sample,summaries:[...new Map([...previous.summaries,...sample.summaries].map(s=>[s.quantity,s])).values()]}:sample)
 }
 return {...page,samples:[...samples.values()].sort((a,b)=>Date.parse(a.time)-Date.parse(b.time))}
}
interface Props {location:LocationPoint;start:number;end:number;instant:number;enabled:boolean;onInstant:(time:number)=>void;focusReady?:boolean;onTimes?:(rows:TimeRow[])=>void}
export function useWeatherNext(props:Props) {
 const [section,setSection]=useState<Section>('clouds')
 const [products,setProducts]=useState<Record<string,string>>({temperature:'gridded',precipitation:'model'})
 const [run,setRun]=useState(''),[revision,setRevision]=useState(0),[mean,setMean]=useState(false)
 const [data,setData]=useState<WeatherPage|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const [now,setNow]=useState(Date.now()),[cursor,setCursor]=useState(props.instant),[details,setDetails]=useState(false)
 const [thresholds,setThresholds]=useState<Record<string,{value:string;event:'above'|'below'}>>({clouds:{value:'80',event:'above'}})
 const [estimates,setEstimates]=useState<Record<string,Record<string,Bounds>>>({})
 const cache=useRef(new Map<string,WeatherPage>()),pins=useRef(new Map<string,string>())
 const product=products[section??'clouds']??'default'
 const group=JSON.stringify([props.location.latitude,props.location.longitude,props.start,props.end,run,revision])
 const signature=JSON.stringify([group,section,product])
 const qs=(fields[section??'clouds']??fields.clouds).map(q=>section==='temperature'&&product==='station'?'station_head_'+q:section==='precipitation'?product==='imerg'?'imerg_tp_1hr':product==='experimental'?'experimental_tp_1hr':q:q)
 const thresholdKey=(q:string)=>section==='clouds'?'clouds':q+':'+unitFor(q)
 useEffect(()=>setCursor(props.instant),[props.instant])
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer)},[])
 useEffect(()=>{
   const controller=new AbortController(); let current:WeatherPage|null=cache.current.get(signature)??null
   setError('');setBusy(false)
   if(current&&Date.parse(current.expires_at)<=Date.now()){cache.current.delete(signature);current=null}
   setData(current)
   if(!props.enabled||props.focusReady===false)return()=>controller.abort()
   if(current&&current.next_offset===null)return()=>controller.abort()
   setBusy(true)
   void (async()=>{
     try {
       for(;;){
         controller.signal.throwIfAborted()
         const response=await wn3Request(controller.signal,()=>current?fetch(`${ENDPOINT}/${current.id}?offset=${current.next_offset??0}`,{signal:controller.signal}):fetch(ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({latitude:props.location.latitude,longitude:props.location.longitude,start:new Date(props.start).toISOString(),end:new Date(props.end).toISOString(),run_time:run?new Date(run+'Z').toISOString():pins.current.get(group)??null,section,product})}))
         const page=await response.json() as WeatherPage
         if(!response.ok){const failure=page as unknown as {detail?:{code?:string;message?:string}};throw new Error(`${failure.detail?.code??'failed'} · ${failure.detail?.message??'WeatherNext selection unavailable; refresh to retry'}`)}
         controller.signal.throwIfAborted()
         if(!Array.isArray(page.samples)||!Array.isArray(page.native_times)||page.selection.latitude!==props.location.latitude||page.selection.longitude!==props.location.longitude||Date.parse(page.selection.start)!==props.start||Date.parse(page.selection.end)!==props.end||page.selection.section!==section||page.selection.product!==product)throw new Error('WeatherNext response identity changed')
         current=appendWeatherPage(current,page)
         if(page.run_time)pins.current.set(group,page.run_time)
         cache.current.set(signature,current)
         // Client retention has the same finite 8 MiB ceiling as the shared backend budget.
         while(cache.current.size>12||[...cache.current.values()].reduce((n,p)=>n+JSON.stringify(p).length,0)>8*1024*1024){const key=cache.current.keys().next().value!;const old=cache.current.get(key)!;cache.current.delete(key);if(key!==signature)void fetch(`${ENDPOINT}/${old.id}`,{method:'DELETE'}).catch(()=>{})}
         setData(current)
         if(page.next_offset===null)break
       }
     }catch(e){if(!controller.signal.aborted)setError(String(e))}
     finally{if(!controller.signal.aborted)setBusy(false)}
   })()
   return()=>controller.abort()
 },[signature,props.enabled,props.focusReady])
 useEffect(()=>{
   const current=props.enabled && data && data.selection.latitude===props.location.latitude && data.selection.longitude===props.location.longitude && Date.parse(data.selection.start)===props.start && Date.parse(data.selection.end)===props.end && Date.parse(data.expires_at)>now
   props.onTimes?.(current && data.run_time ? [{id:'weathernext-workspace',title:'WeatherNext pinned run',inventory:{frames:data.native_times.map(valid_time=>({valid_time,run_time:data.run_time!})),notices:[],expires_at:data.expires_at}}] : [])
 },[data,props.enabled,props.start,props.end,props.location.latitude,props.location.longitude,props.onTimes,!!data&&Date.parse(data.expires_at)<=now])
 const thSignature=JSON.stringify(qs.map(q=>[q,thresholds[thresholdKey(q)]]))
 useEffect(()=>{
   setEstimates({})
   if(!props.enabled||!data?.samples.length||Date.parse(data.expires_at)<=Date.now())return
   const controller=new AbortController()
   const timer=setTimeout(()=>{void Promise.all(qs.map(async q=>{
     const t=thresholds[thresholdKey(q)]
     if(!t||t.value.trim()===''||!Number.isFinite(Number(t.value)))return
     const threshold:Threshold={quantity:q,unit:unitFor(q),value:Number(t.value),event:t.event}
     try{
       const r=await fetch(`${ENDPOINT}/${data.id}/threshold`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(threshold),signal:controller.signal})
       if(!r.ok)return
       const body=await r.json() as S['WeatherNextEstimates']
       if(body.id!==data.id||body.run_time!==data.run_time)throw new Error('Threshold identity changed')
       if(!controller.signal.aborted)setEstimates(old=>({...old,[q]:Object.fromEntries(Object.entries(body.estimates).map(([t,b])=>[String(Date.parse(t)),b]))}))
     }catch{/* Missing estimates remain absent. */}
   }))},150)
   return()=>{clearTimeout(timer);controller.abort()}
 },[data,thSignature,props.enabled])
 const selected=data?.samples.find(s=>Date.parse(s.time)===Math.ceil(cursor/3600000)*3600000)
 const selectedFresh=selected&&fresh(selected,now)&&Date.parse(data!.expires_at)>now
 const thresholdControls=(q:string)=>{const key=thresholdKey(q),t=thresholds[key]??{value:'',event:'above' as const};return <fieldset key={key} className="wn-threshold"><legend>{section==='clouds'?'All cloud levels':names[q]} · estimate chance</legend><label>Event<select value={t.event} onChange={e=>setThresholds(old=>({...old,[key]:{...t,event:e.target.value as 'above'|'below'}}))}><option value="above">above</option><option value="below">below</option></select></label><label>Threshold ({unitLabel(unitFor(q))})<input type="number" step="any" value={t.value} onChange={e=>setThresholds(old=>({...old,[key]:{...t,value:e.target.value}}))}/></label>{t.value===''&&<span>Choose a threshold</span>}</fieldset>}
 return <section className="wn-workspace" aria-label="WeatherNext forecast workspace">
   <header className="wn-context"><h2>WeatherNext <small>3 · published ensemble statistics</small></h2><p>{props.location.name} · {props.location.latitude.toFixed(3)}, {props.location.longitude.toFixed(3)}</p><p>Range {stamp(props.start)} → {stamp(props.end)} · selected {stamp(props.instant)}</p><label>Forecast run (UTC)<input aria-label="Forecast run (UTC)" type="datetime-local" step="3600" value={run} onChange={e=>setRun(e.target.value)}/></label><button onClick={()=>{setRevision(n=>n+1)}}>Refresh selection</button><p>Sampled grid: {selected?.summaries[0]?.sampled_latitude??'pending'}, {selected?.summaries[0]?.sampled_longitude??'pending'}</p><p>Pinned run: {data?.run_time?stamp(data.run_time):'Awaiting published run'} · {data?.run_id??'No run selected'}</p>{data&&<p>Snapshot retained until {stamp(data.expires_at)} · refresh explicitly for a new selection</p>}</header>
   <nav aria-label="Weather sections">{sections.map(([s,label])=><button key={s} aria-pressed={section===s} onClick={()=>setSection(s)}>{label}</button>)}</nav>
   {(section==='temperature'||section==='precipitation')&&<label>Product<select value={product} onChange={e=>setProducts(old=>({...old,[section]:e.target.value}))}>{(section==='temperature'?[['gridded','Gridded'],['station','Station-trained']]:[['model','Model-native'],['imerg','IMERG'],['experimental','Experimental']]).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>}
   <div className="wn-controls">{(section==='clouds'?qs.slice(0,1):qs).map(thresholdControls)}<label><input type="checkbox" checked={mean} onChange={e=>setMean(e.target.checked)}/>Show mean</label></div>
   <p className="wn-explanation">Median (P50): typical forecast. Dark band: P25–P75; light band: P10–P90 ensemble percentiles. These are not confidence intervals or guaranteed limits. Published summaries cannot fully resolve separate clusters of outcomes.</p>
   <p role="status">{busy?`Loading · ${data?.completed_pages??0} / ${data?.total_pages||'…'} quantity/time pages`:'Loading complete'}{error&&` · ${error}`}{data?.reason&&` · ${data.reason}`}{data&&Date.parse(data.expires_at)<=now&&' · Selection expired; refresh explicitly'}</p>
   <div className="wn-layout"><div>{qs.map(q=><WeatherChart key={q} quantity={q} start={props.start} end={props.end} cursor={cursor} onHover={setCursor} onLeave={()=>setCursor(props.instant)} onSelect={t=>{props.onInstant(t);setDetails(true)}} samples={data?.samples??[]} times={data?.native_times??[]} now={now} selectionExpired={!!data&&Date.parse(data.expires_at)<=now} showMean={mean} estimates={estimates[q]??{}} threshold={thresholds[thresholdKey(q)]} busy={busy}/>)}</div>
   <aside className="wn-details"><button aria-expanded={details} onClick={()=>setDetails(v=>!v)}>Selected-time details</button>{details&&<><h3>{stamp(cursor)}</h3>{!selected?<p>Unavailable forecast period or pending page.</p>:!selectedFresh?<p>Expired source evidence; values withheld.</p>:<><p>Forecast run {data?.run_time&&stamp(data.run_time)}</p><table><caption>Visible quantities · median and mean</caption><thead><tr><th>Quantity</th><th>P50</th><th>Mean</th></tr></thead><tbody>{selected.summaries.filter(s=>qs.includes(s.quantity)).map(s=><tr key={s.quantity}><th>{names[s.quantity]}</th><td>{format(s.values.p50)} {unitLabel(s.unit)}</td><td>{format(s.values.mean)} {unitLabel(s.unit)}</td></tr>)}</tbody></table>{selected.summaries.map(s=><details key={s.quantity}><summary>{names[s.quantity]??s.quantity} · {s.state}</summary><p>Native grid {s.grid} · {s.level} · {s.original_unit}</p><p>Sampled grid {s.sampled_latitude??'unknown'}, {s.sampled_longitude??'unknown'}</p>{s.reason&&<p>{s.reason}</p>}{s.interval_start&&<p>One-hour interval {stamp(s.interval_start)} → {stamp(s.interval_end!)}</p>}<dl>{statistics.map(stat=><div key={stat}><dt>{stat.toUpperCase()}</dt><dd>{format(s.values[stat])} {unitLabel(s.unit)}</dd></div>)}</dl><p>{(()=>{const estimate=estimates[s.quantity]?.[String(Date.parse(selected.time))],threshold=thresholds[thresholdKey(s.quantity)];return number(estimate?.lower)&&number(estimate?.upper)&&threshold?`Approximately ${estimate.lower}–${estimate.upper}% chance ${threshold.event} ${threshold.value} ${unitLabel(s.unit)}`:'Threshold estimate unavailable'})()}</p><p>{estimates[s.quantity]?.[String(Date.parse(selected.time))]?.basis}</p><details><summary>Quantity acquisition provenance</summary><pre>{JSON.stringify(s.provenance,null,2)}</pre></details></details>)}<details><summary>Source, run, time and acquisition provenance</summary><p>Reference reading and shared batch receipt. Each quantity above retains its own native field, grid and units.</p><pre>{JSON.stringify(selected.provenance,null,2)}</pre></details></>}</>}</aside></div>
 </section>
}

function WeatherChart({quantity:q,start,end,cursor,onHover,onLeave,onSelect,samples,times,now,selectionExpired,showMean,estimates,threshold,busy}:{quantity:string;start:number;end:number;cursor:number;onHover:(t:number)=>void;onLeave:()=>void;onSelect:(t:number)=>void;samples:Sample[];times:string[];now:number;selectionExpired:boolean;showMean:boolean;estimates:Record<string,Bounds>;threshold?:{value:string;event:string};busy:boolean}) {
 const svg=useRef<SVGSVGElement|null>(null),[width,setWidth]=useState(700)
 useEffect(()=>{if(!svg.current||typeof ResizeObserver==='undefined')return;const observer=new ResizeObserver(e=>setWidth(Math.max(250,e[0].contentRect.width)));observer.observe(svg.current);return()=>observer.disconnect()},[])
 const rows=times.map(t=>{const sample=samples.find(s=>s.time===t);return {time:Date.parse(t),sample,summary:sample?.summaries.find(s=>s.quantity===q)}})
 const valid=(r:typeof rows[number])=>!!r.sample&&fresh(r.sample,now)&&!selectionExpired
 const values=rows.flatMap(r=>valid(r)?Object.values(r.summary?.values??{}).filter(number):[])
 const cloud=q.includes('cloud'),unit=unitLabel(unitFor(q)),interval=q.endsWith('1hr')
 const min=cloud?0:Math.min(...values,0),max=cloud?100:Math.max(...values,1)
 const x=(t:number)=>48+(t-start)/(end-start)*(width-65),y=(v:number)=>125-(v-min)/(max-min)*100
 const point=(e:React.MouseEvent<SVGSVGElement>|React.PointerEvent<SVGSVGElement>)=>{const box=e.currentTarget.getBoundingClientRect();return Math.max(start,Math.min(end-1,start+((e.clientX-box.left)*width/box.width-48)/(width-65)*(end-start)))}
 const inspected=rows.find(r=>r.time===Math.ceil(cursor/3600000)*3600000)
 const b=inspected&&valid(inspected)?estimates[String(inspected.time)]:undefined
 const state=inspected?inspected.sample?(valid(inspected)?inspected.summary?.state??(busy?'pending':'missing'):'expired'):'pending':'unavailable period'
 const pick=(t:number)=>onSelect(Math.max(start,Math.min(end-1,t)))
 const band=(lo:string,hi:string)=>rows.flatMap((r,i)=>{const next=rows[i+1];if(!next||!valid(r)||!valid(next)||next.time-r.time!==3600000)return [];const a=r.summary?.values[lo],b=r.summary?.values[hi],c=next.summary?.values[lo],d=next.summary?.values[hi];if(!number(a)||!number(b)||!number(c)||!number(d)||a>b||c>d)return [];return [<path key={r.time} d={`M${x(r.time)},${y(a)}L${x(next.time)},${y(c)}L${x(next.time)},${y(d)}L${x(r.time)},${y(b)}Z`}/>]})
 const line=(stat:string)=>{let previous:number|null=null;return rows.map(r=>{const v=r.summary?.values[stat];if(!valid(r)||!number(v)){previous=null;return ''};const command=previous!==null&&r.time-previous===3600000?'L':'M';previous=r.time;return `${command}${x(r.time)},${y(v)}`}).join(' ')}
 return <figure className="wn-chart"><figcaption><strong>{names[q]}</strong> · {unit}{interval?' in preceding 1 hour':''}</figcaption><svg ref={svg} viewBox={`0 0 ${width} 235`} role="img" aria-label={`${names[q]} weather amount and approximate probability; inspect with the time buttons or shared timeline`} onPointerMove={e=>onHover(point(e))} onPointerLeave={onLeave} onClick={e=>pick(Math.ceil(point(e)/3600000)*3600000)}><title>{names[q]} ensemble percentile bands and approximate threshold probability</title>
 {[0,.5,1].map(f=><g key={f}><path className="wn-grid" d={`M48 ${125-f*100}H${width-17}`}/><text x="1" y={129-f*100}>{format(min+(max-min)*f)}</text></g>)}
 <g className="wn-outer">{band('p10','p90')}</g><g className="wn-inner">{band('p25','p75')}</g><path className="wn-median" d={line('p50')}/>{showMean&&<path className="wn-mean" d={line('mean')}/>}
 {rows.filter(valid).map(r=>number(r.summary?.values.p50)?<circle key={r.time} cx={x(r.time)} cy={y(r.summary!.values.p50!)} r="2" className="wn-dot"/>:null)}
 <text x="1" y="165">100%</text><text x="1" y="208">0%</text><text x="50" y="155">Probability</text>
 {rows.flatMap(r=>{const p=valid(r)?estimates[String(r.time)]:null;if(!p||!number(p.lower)||!number(p.upper))return [];return [<rect key={r.time} className="wn-probability" x={Math.max(48,x(r.time-1800000))} y={205-p.upper*.4} width={Math.max(1,Math.min(width-17,x(r.time+1800000))-Math.max(48,x(r.time-1800000)))} height={Math.max(1,(p.upper-p.lower)*.4)}/>]})}
 {[0,.5,1].map(f=><text key={f} x={48+f*(width-65)} y="230" textAnchor={f===1?'end':f===0?'start':'middle'}>{new Date(start+(end-start)*f).toISOString().slice(5,16).replace('T',' ')}</text>)}
 {cursor>=start&&cursor<end&&<path className="wn-cursor" d={`M${x(cursor)} 20V210`}/>}</svg>
 <div className="wn-inspect"><button aria-label={`Previous ${names[q]} time`} onClick={()=>pick((Math.ceil(cursor/3600000)-1)*3600000)}>←</button><button aria-label={`Inspect ${names[q]} selected time`} onClick={()=>pick(cursor)}>Inspect {stamp(cursor)}</button><button aria-label={`Next ${names[q]} time`} onClick={()=>pick((Math.ceil(cursor/3600000)+1)*3600000)}>→</button></div>
 <p>{state==='available'?`Median ${format(inspected?.summary?.values.p50)} ${unit}`:state==='pending'&&busy?'Pending page':state} · {threshold?.value&&number(b?.lower)&&number(b?.upper)?`Approximately ${b.lower}–${b.upper}% chance ${threshold.event} ${threshold.value}${unit}`:threshold?.value?'Estimate unavailable':'Choose a threshold to estimate probability'}</p>{inspected&&valid(inspected)&&statistics.some(s=>!number(inspected.summary?.values[s]))&&<p>Unavailable statistics: {statistics.filter(s=>!number(inspected.summary?.values[s])).map(s=>s.toUpperCase()).join(', ')}</p>}{inspected?.summary?.reason&&<p>{inspected.summary.reason}</p>}{b?.basis&&<p className="wn-basis">{b.basis}</p>}
 </figure>
}
