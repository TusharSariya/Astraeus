import { useEffect, useId, useRef, useState } from 'react'
import type { components } from '../generated/source-api'
import type { FrameMarkers } from '../api'
import type { LocationPoint } from '../types'
import type { SharedSeriesSelection } from './NativeSeries'
import './forecastComparison.css'

type Schema = components['schemas']
export type ComparisonPage = Schema['ComparisonPage']
export type Curve = Schema['ComparisonCurve']
type Sample = Schema['ComparisonSample']
type Selection = Schema['ComparisonSelection-Input']
type Group = NonNullable<Selection['variables']>[number]
const endpoint = '/api/experiments/weather/v0/point/comparison'
export const MODELS = [
  ['eccc-hrdps', 'HRDPS', '#009e73'], ['eccc-rdps', 'RDPS', '#e69f00'],
  ['google-weathernext-3-statistics', 'WeatherNext 3', '#b56ce2'], ['noaa-gfs', 'GFS', '#56b4e9'],
  ['ecmwf-ifs', 'IFS', '#aaaaff'], ['eccc-gdps', 'GDPS', '#e76f8a'],
] as const
const GROUPS: [Group, string][] = [['temperature','Temperature'], ['humidity','Relative humidity'], ['cloud','Cloud cover'], ['wind','Wind'], ['precipitation','Precipitation'], ['dew_point','Dew point'], ['pressure','Pressure'], ['wind_direction','Wind direction']]
const defaults: Group[] = ['temperature','humidity','cloud','wind','precipitation']
const name = (id: string) => MODELS.find(m => m[0] === id)?.[1] ?? id
const colour = (id: string) => `var(--comparison-model-${Math.max(0,MODELS.findIndex(m => m[0] === id))})`
const stamp = (time: number | string) => new Date(time).toISOString().replace('T',' ').slice(0,16) + ' UTC'
const numeric = (s: Sample) => typeof s.evidence?.value === 'number' && Number.isFinite(s.evidence.value)
const value = (s: Sample) => Number(s.evidence?.value)

/** Bottom timeline uses only successfully loaded native sample identities. */
export function comparisonMarkers(evidence: SharedSeriesSelection | null): FrameMarkers {
  const markers = new Map<number, FrameMarkers['markers'][number]>()
  if (evidence && !evidence.expired) for (const row of evidence.series) for (const sample of row.samples) {
    const time = sample.provenance.valid_time
    if (!time || typeof sample.value !== 'number' || !Number.isFinite(sample.value)) continue
    const ms = Date.parse(time)
    if (!Number.isFinite(ms)) continue
    const marker = markers.get(ms) ?? {ms,time,layers:[]}
    if (!marker.layers.some(layer => layer.id === row.source_id)) marker.layers.push({id:row.source_id,
      title:`${name(row.source_id)} native forecast time`, color:MODELS.find(model => model[0] === row.source_id)?.[2] ?? '#aaaaff', runTime:sample.provenance.run_time})
    markers.set(ms,marker)
  }
  return {markers:[...markers.values()].sort((a,b)=>a.ms-b.ms),axisless:[]}
}

export function validatePage(raw: unknown, selection: Selection): ComparisonPage {
  if (!raw || typeof raw !== 'object') throw new Error('Unreadable comparison')
  const p = raw as ComparisonPage
  if (!p.selection || p.selection.latitude !== selection.latitude || p.selection.longitude !== selection.longitude
    || Date.parse(p.selection.start) !== Date.parse(selection.start) || Date.parse(p.selection.end) !== Date.parse(selection.end)
    || !Array.isArray(p.selection.sources) || p.selection.sources.length !== selection.sources?.length
    || p.selection.sources.some((source, index) => {
      const expected = selection.sources?.[index]
      return source.source_id !== expected?.source_id || (source.product_id ?? null) !== (expected?.product_id ?? null) || (source.run ?? 'latest') !== (expected?.run ?? 'latest') || (source.level ?? null)!==(expected?.level ?? null) || JSON.stringify(source.variant??null)!==JSON.stringify(expected?.variant??null)
    })
    || JSON.stringify(p.selection.variables) !== JSON.stringify(selection.variables) || p.selection.ensemble_spread !== selection.ensemble_spread
    || typeof p.id !== 'string' || !Number.isFinite(Date.parse(p.expires_at)) || !Array.isArray(p.curves) || !Array.isArray(p.coverage)
    || typeof p.complete !== 'boolean' || !(p.next_cursor === null || typeof p.next_cursor === 'string')
    || p.total_positions > 144 || p.completed_positions > p.total_positions) throw new Error('Comparison selection changed or is unreadable')
  for (const c of p.curves) {
    if (!selection.sources?.some(s => s.source_id === c.source_id) || !selection.variables?.includes(c.group) || !Array.isArray(c.samples)) throw new Error('Comparison curve identity changed')
    for (const s of c.samples) {
      const time = Date.parse(s.time)
      if (!Number.isFinite(time) || time < Date.parse(selection.start) || time >= Date.parse(selection.end)) throw new Error('Native time is outside the selected window')
      for (const evidence of [s.evidence,s.lower,s.upper]) if (evidence && (evidence.provenance?.source_id !== c.source_id || Date.parse(evidence.provenance.valid_time ?? '') !== time
        || (evidence.value !== null && (typeof evidence.value !== 'number' || !Number.isFinite(evidence.value))))) throw new Error('Native sample identity is unreadable')
      if (s.evidence && s.evidence.key !== c.field) throw new Error('Native field changed')
    }
  }
  return p
}
export function appendComparison(old: ComparisonPage | null, page: ComparisonPage): ComparisonPage {
  if (!old) return page
  if (old.id !== page.id || old.expires_at !== page.expires_at || page.completed_positions < old.completed_positions) throw new Error('Comparison continuation changed')
  const curves = page.curves.map(c => {
    const previous = old.curves.find(v => v.id === c.id)
    const samples = new Map((previous?.samples ?? []).map(s => [`${s.run_id}:${s.time}`, s]))
    for (const sample of c.samples ?? []) samples.set(`${sample.run_id}:${sample.time}`, sample)
    return { ...c, units: c.units ?? previous?.units, samples: [...samples.values()].sort((a,b) => Date.parse(a.time)-Date.parse(b.time)) }
  })
  const coverage = page.coverage.map(c => {
    const previous = old.coverage.find(v => v.source_id === c.source_id)
    return c.state === 'available' && previous && previous.state !== 'available' ? previous : c
  })
  return {...page, curves, coverage}
}
interface Props {
  location: LocationPoint; instant: number; enabled: boolean; focusReady?: boolean; selectionMoving?: boolean
  onWindow?: (window: {start:number;end:number}) => void
  onInstant: (time: number) => void
  onLocation?: (location: LocationPoint) => void
  onEvidence?: (selection: SharedSeriesSelection | null) => void
  jumpTo?: { field: string; source: string; revision: number } | null
}

/** State belongs to App so changing views never renews the finite comparison. */
export function useForecastComparison(props: Props) {
  const id = useId()
  const [start, setStart] = useState(props.instant)
  const [end, setEnd] = useState(props.instant + 86400000)
  const [sources, setSources] = useState<string[]>(MODELS.slice(0,5).map(m => m[0]))
  const [ifsCatalogue,setIFSCatalogue] = useState<Array<{id:string;name:string;levels:number[];products:string[]}>>([])
  const [ifsProduct,setIFSProduct] = useState('atmosphere-control')
  const [ifsLevel,setIFSLevel] = useState(0)
  const [ifsRun,setIFSRun]=useState('latest'),[ifsRuns,setIFSRuns]=useState<Array<{id:string;run_time:string}>>([])
  useEffect(()=>{const c=new AbortController();setIFSRun('latest');setIFSRuns([]);fetch(`/api/experiments/weather/v0/ifs/runs/${ifsProduct}`,{signal:c.signal}).then(r=>r.json()).then(r=>{if(Array.isArray(r))setIFSRuns(r)}).catch(()=>{});return()=>c.abort()},[ifsProduct])
  useEffect(()=>{const c=new AbortController();fetch('/api/experiments/weather/v0/ifs/catalogue',{signal:c.signal}).then(r=>r.json()).then(c=>setIFSCatalogue(Array.isArray(c?.fields)?c.fields:[])).catch(()=>{});return()=>c.abort()},[])
  const [variables, setVariables] = useState<Group[]>(defaults)
  const [spread, setSpread] = useState(false)
  const [hidden, setHidden] = useState<string[]>([])
  const [cursor, setCursor] = useState(props.instant)
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState<ComparisonPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [expired, setExpired] = useState(false)
  const active = useRef<AbortController | null>(null)
  const version = useRef(0)
  const currentId = useRef<string | null>(null)
  const started = useRef<string | null>(null)
  const selection: Selection = { latitude: props.location.latitude, longitude: props.location.longitude, start: new Date(start).toISOString(), end: new Date(end).toISOString(), sources: sources.map(source_id => ({source_id, run:source_id==='ecmwf-ifs'?ifsRun:'latest', product_id:source_id==='ecmwf-ifs'&&ifsProduct!=='atmosphere-control'?ifsProduct:null,...(source_id==='ecmwf-ifs'?{level:ifsLevel}: {})})), variables, ensemble_spread:spread }
  const signature = JSON.stringify(selection)
  const valid = start < end && end-start <= 86400000 && sources.length > 0 && sources.length <= 6 && variables.length > 0 && variables.length <= 8
  const ready = props.focusReady !== false
  useEffect(() => { if (valid) props.onWindow?.({start,end}) }, [start,end,valid,props.onWindow])
  useEffect(() => { setCursor(props.instant) }, [props.instant])
  useEffect(() => { if (props.jumpTo) { setSources(s => s.includes(props.jumpTo!.source) ? s : [...s.slice(0,5), props.jumpTo!.source]); } }, [props.jumpTo])
  useEffect(() => {
    const key = `${signature}:${revision}`
    if (!ready || started.current !== key) {
      active.current?.abort(); version.current++
      if (currentId.current) void fetch(`${endpoint}/${currentId.current}`, {method:'DELETE'}).catch(() => {})
      currentId.current = null; setData(null); setExpired(false); setError(null); setBusy(false)
      started.current = null
    }
    if (!ready || !valid || !props.enabled || started.current === key) return
    started.current = key
    const controller = new AbortController(); active.current = controller
    const generation = ++version.current
    const requested = JSON.parse(signature) as Selection
    setBusy(true)
    void (async () => {
      let body: unknown = requested, loaded: ComparisonPage | null = null
      try {
        for (;;) {
          const response = await fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), signal:controller.signal})
          const raw = await response.json()
          if (generation !== version.current || controller.signal.aborted) return
          if (!response.ok) throw new Error(raw.detail?.message ?? 'Comparison request failed')
          const page = validatePage(raw, requested)
          loaded = appendComparison(loaded,page)
          currentId.current = page.id
          setData(loaded)
          if (Date.parse(page.expires_at) <= Date.now()) {setExpired(true); break}
          if (!page.next_cursor) break
          body = {cursor:page.next_cursor}
        }
      } catch (failure) {
        if (generation === version.current && !controller.signal.aborted) setError(String(failure))
      } finally { if (generation === version.current) setBusy(false) }
    })()
  }, [signature,revision,ready,props.enabled,valid])
  useEffect(() => () => {active.current?.abort(); version.current++; started.current=null}, [])
  useEffect(() => {
    if (!data) return
    const timer = setTimeout(() => {setExpired(true); active.current?.abort(); version.current++; setBusy(false)}, Math.max(0,Date.parse(data.expires_at)-Date.now()))
    return () => clearTimeout(timer)
  }, [data?.id,data?.expires_at])
  useEffect(() => {
    if (!data) { props.onEvidence?.(null); return }
    props.onEvidence?.({selection:{latitude:data.selection.latitude,longitude:data.selection.longitude,start:data.selection.start,end:data.selection.end,
      selectors:data.curves.map(c => ({id:c.id,source_id:c.source_id,field:c.field,run:'latest',product_id:c.product_id})),page_size:12},
      snapshot:{id:data.id,selected_at:data.selected_at,expires_at:data.expires_at,change_token:'',identities:[]},complete:data.complete,expired,
      series:data.curves.map(c => ({selector_id:c.id,source_id:c.source_id,field:c.field,requested_run:'latest',product_id:c.product_id,
        run_inventory_reason:'Pinned comparison runs',availability:c.reason ? 'unavailable':'available',reason:c.reason,samples:expired ? [] : (c.samples ?? []).flatMap(s => s.evidence ? [s.evidence] : [])}))})
  }, [data,expired,props.onEvidence])
  const toggle = <T extends string,>(item: T, selected: T[], update: (v:T[]) => void) => update(selected.includes(item) ? selected.filter(v => v !== item) : [...selected,item])
  const available = data?.coverage.find(c => c.available_start && c.available_end && Date.parse(c.available_end) > Date.parse(c.available_start))
  const noSamples = data?.complete && !data.curves.some(c => c.samples?.some(numeric))
  const charts = variables.flatMap<{group:Group;definition:string|null;label:string}>(group => group === 'cloud' ? [{group,definition:'opacity-weighted cover',label:'Cloud cover · opacity-weighted'}, {group,definition:'geometric cover',label:'Cloud cover · geometric'}] : [{group,definition:null,label:GROUPS.find(g => g[0] === group)?.[1] ?? ifsCatalogue.find(f=>'ifs_'+f.id.replace(':','_')===group)?.name ?? group}])
  return <section className="forecast-comparison" aria-label="Forecast comparison">
    <div className="comparison-toolbar">
      <details><summary>Location · {props.location.latitude.toFixed(3)}, {props.location.longitude.toFixed(3)}</summary>
        <form key={`${props.location.latitude}:${props.location.longitude}`} onSubmit={event => {event.preventDefault(); const form=new FormData(event.currentTarget); props.onLocation?.({id:'point',name:'Selected point',kind:'map',sourceIds:[],latitude:Number(form.get('latitude')),longitude:Number(form.get('longitude'))})}}>
          <label>Latitude<input name="latitude" type="number" step="any" min="-90" max="90" required defaultValue={props.location.latitude}/></label>
          <label>Longitude<input name="longitude" type="number" step="any" min="-180" max="180" required defaultValue={props.location.longitude}/></label><button>Apply location</button>
        </form>
      </details>
      <label htmlFor={`${id}-start`}>Start (UTC)<input id={`${id}-start`} type="datetime-local" value={new Date(start).toISOString().slice(0,16)} onChange={e => {const t=Date.parse(e.target.value+'Z'); if(Number.isFinite(t)){setStart(t);setEnd(t+Math.min(86400000,end-start))}}}/></label>
      <label htmlFor={`${id}-end`}>End (UTC)<input id={`${id}-end`} type="datetime-local" value={new Date(end).toISOString().slice(0,16)} onChange={e => {const t=Date.parse(e.target.value+'Z'); if(Number.isFinite(t))setEnd(t)}}/></label>
      <details><summary>Sources · {sources.length}</summary><fieldset><legend>Models (up to six)</legend>{MODELS.map(([key,label]) => <label key={key}><input type="checkbox" checked={sources.includes(key)} onChange={() => toggle(key,sources,setSources)}/>{label}</label>)}</fieldset></details>
      <details><summary>Variables · {variables.length}</summary><fieldset><legend>Variable groups (up to eight)</legend>{GROUPS.map(([key,label]) => <label key={key}><input type="checkbox" checked={variables.includes(key)} onChange={() => toggle(key,variables,setVariables)}/>{label}</label>)}<label><input type="checkbox" checked={spread} onChange={e => setSpread(e.target.checked)}/>P10–P90 ensemble band</label></fieldset></details>
      {sources.includes('ecmwf-ifs')&&<details><summary>IFS fields and levels</summary>
       <label>IFS product<select value={ifsProduct} onChange={e=>setIFSProduct(e.target.value)}>{['atmosphere-control','atmosphere-ensemble','wave-control','wave-ensemble','ensemble-mean','ensemble-standard-deviation','daily-probability','temperature-probability','wave-probability'].map(p=><option key={p}>{p}</option>)}</select></label>
       <label>IFS run<select value={ifsRun} onChange={e=>setIFSRun(e.target.value)}><option value="latest">Latest advertised product run</option>{ifsRuns.map(r=><option key={r.id} value={r.id}>{r.run_time}</option>)}</select></label>
       <label>IFS native level<input type="number" min="0" max="1000" value={ifsLevel} onChange={e=>setIFSLevel(Number(e.target.value))}/></label>
       <label>Additional native quantity<select value="" onChange={e=>{if(e.target.value&&!variables.includes(e.target.value)&&variables.length<8)setVariables(v=>[...v,e.target.value])}}><option value="">Select a numeric field</option>{ifsCatalogue.filter(f=>f.products.includes(ifsProduct)).map(f=><option key={f.id} value={'ifs_'+f.id.replace(':','_')}>{f.name} · {f.id}</option>)}</select></label>
       {variables.filter(v=>!GROUPS.some(g=>g[0]===v)).map(v=><button key={v} onClick={()=>setVariables(a=>a.filter(k=>k!==v))}>Remove {v}</button>)}
      </details>}
      <button disabled={!valid || !ready} onClick={() => setRevision(r => r+1)}>Refresh</button>
    </div>
    <div className="comparison-legend" aria-label="Model visibility">{sources.map(source => <button key={source} style={{borderColor:colour(source)}} aria-pressed={!hidden.includes(source)} onClick={() => toggle(source,hidden,setHidden)}><span style={{background:colour(source)}}/>{name(source)}{hidden.includes(source) ? ' (hidden)' : ''}</button>)}</div>
    <div role="status">{!valid && <p>Select at least one model and variable, and a window of up to 24 hours.</p>}{!ready && <p>Select a location to compare forecasts.</p>}{busy && <p>Loading · {data?.completed_positions ?? 0} / {data?.total_positions ?? '…'} native positions</p>}{error && <p>{error} · Refresh to retry.</p>}{expired && <p className="comparison-expired">Expired comparison · retained charts are no longer current. Refresh to read again.</p>}</div>
    {noSamples && <p>No samples in this window. {available && <button onClick={() => {const t=Date.parse(available.available_start!);setStart(t);setEnd(Math.min(t+86400000,Date.parse(available.available_end!)))}}>Show available window</button>}</p>}
    <div className={expired ? 'comparison-charts expired' : 'comparison-charts'}>{charts.map(chart => <ComparisonChart key={chart.label} label={chart.label} group={chart.group} start={start} end={end} cursor={cursor} onCursor={setCursor} onLeave={() => setCursor(props.instant)} onInstant={props.onInstant} loading={busy}
      curves={(data?.curves ?? []).filter(c => c.group === chart.group && (!chart.definition || c.definition === chart.definition) && !hidden.includes(c.source_id))} />)}</div>
    {data && <><ul className="comparison-notices">{data.coverage.filter(c => c.state !== 'available').map(c => <li key={c.source_id}>{name(c.source_id)} · {c.state === 'credentials_required' ? 'Credentials required' : c.state === 'empty' ? 'No native timestamps in this window' : 'Source unavailable'}</li>)}</ul>
      <details className="comparison-details"><summary>Details · native values, runs and provenance</summary><p>Selected {stamp(data.selected_at)} · Expires {stamp(data.expires_at)}</p>
        {data.coverage.map(c => <p key={c.source_id}>{name(c.source_id)}: {c.reason}{c.failure_kind ? ` (${c.failure_kind})` : ''}</p>)}
        {data.curves.map(c => <details key={c.id}><summary>{name(c.source_id)} · {c.field} · {c.units ?? 'No units available'}</summary><table><caption>Exact native samples for {c.field}</caption><thead><tr><th scope="col">Time (UTC)</th><th scope="col">Value</th><th scope="col">Run</th><th scope="col">Provenance</th></tr></thead><tbody>{c.samples?.map(s => <tr key={`${s.run_id}:${s.time}`}><th scope="row"><button onClick={() => props.onInstant(Date.parse(s.time))}>{stamp(s.time)}</button></th><td>{numeric(s) ? value(s).toFixed(2) : s.reason ?? 'Missing'} {c.units}</td><td>{s.run_id}</td><td><details><summary>Reading details</summary><pre>{JSON.stringify(s,null,2)}</pre></details></td></tr>)}</tbody></table></details>)}
      </details></>}
  </section>
}

export function linePath(samples: Sample[], x:(t:number)=>number, y:(v:number)=>number): string {
  let previous: Sample | null = null
  return samples.map(s => {
    if (!numeric(s)) {previous=null;return ''}
    const command=previous && previous.run_id===s.run_id ? 'L':'M';previous=s
    return `${command}${x(Date.parse(s.time))},${y(value(s))}`
  }).join(' ')
}
function ComparisonChart({label,group,curves:acquiredCurves,start,end,cursor,onCursor,onLeave,onInstant,loading}: {label:string;group:Group;curves:Curve[];start:number;end:number;cursor:number;onCursor:(t:number)=>void;onLeave:()=>void;onInstant:(t:number)=>void;loading:boolean}) {
  const directional=group==='wind_direction'||group==='ifs_mwd_sfc'
  const categorical=group==='ifs_ptype_sfc'
  const [member,setMember]=useState('summary')
  const members=[...new Set(acquiredCurves.filter(c=>c.source_id==='ecmwf-ifs').flatMap(c=>(c.samples??[]).flatMap(s=>Object.keys(s.member_values??{}))))].sort((a,b)=>Number(a)-Number(b))
  const curves=acquiredCurves.map(c=>member==='summary'||c.source_id!=='ecmwf-ifs'?c:{...c,samples:(c.samples??[]).map(s=>{
    let v=s.member_values?.[member]??null
    if(v!==null){if(s.member_units==='K'&&c.units==='degC')v-=273.15;else if(s.member_units==='Pa'&&c.units==='hPa')v/=100;else if(s.member_units==='m'&&c.units==='mm')v*=1000;else if(s.member_units==='(0 - 1)'&&c.units==='percent')v*=100}
    return {...s,evidence:s.evidence?{...s.evidence,value:v}:null,lower:null,upper:null}
  })})
  const svg=useRef<SVGSVGElement | null>(null)
  const [width,setWidth]=useState(1000)
  useEffect(()=>{
    if (!svg.current || typeof ResizeObserver==='undefined') return
    const observer=new ResizeObserver(entries=>setWidth(Math.max(280,entries[0].contentRect.width)))
    observer.observe(svg.current)
    return ()=>observer.disconnect()
  },[])
  const all=curves.flatMap(c => (c.samples ?? []).filter(numeric).flatMap(s => [value(s), ...[s.lower?.value,s.upper?.value].filter((v):v is number=>typeof v==='number' && Number.isFinite(v))]))
  const min=Math.min(...all, ...(group==='precipitation' || !all.length ? [0] : []))
  const max=Math.max(...all, ...(all.length ? (group==='precipitation' ? [0] : []) : [1]))
  const x=(t:number) => 64+Math.max(0,Math.min(1,(t-start)/(end-start)))*(width-104)
  const y=(v:number) => 142-(v-min)/(max-min || 1)*112
  const pointer=(event:React.PointerEvent<SVGSVGElement> | React.MouseEvent<SVGSVGElement>) => {
    const box=event.currentTarget.getBoundingClientRect()
    return Math.max(start,Math.min(end-1,start+((event.clientX-box.left)-64)/(width-104)*(end-start)))
  }
  const units=[...new Set(curves.flatMap(c => c.units ? [c.units] : []))]
  const incompatible=units.length>1
  return <section className="comparison-chart"><h3>{label} <small>{units.join(' / ') || (group==='temperature' || group==='dew_point' ? '°C' : group==='humidity' || group==='cloud' ? '%' : group==='wind' ? 'm/s' : group==='precipitation' ? 'mm' : group==='pressure' ? 'hPa' : '°')}</small></h3>
    {members.length>0&&<label>IFS displayed member<select value={member} onChange={e=>setMember(e.target.value)}><option value="summary">Ensemble summary</option>{members.map(m=><option key={m} value={m}>{m==='0'?'Control 0':`Member ${m}`}</option>)}</select></label>}
    {incompatible ? <p>Different native units; values remain available in Details.</p> : <svg ref={svg} viewBox={`0 0 ${width} 184`} role="img" aria-label={`${label}; native timestamps and values in Details`} onPointerLeave={onLeave} onPointerMove={e => onCursor(pointer(e))} onClick={e => onInstant(pointer(e))}>
      <title>{label} comparison</title>
      {[0,.25,.5,.75,1].map(f => <g key={f}><path d={`M${64+(width-104)*f} 18V150`} className="comparison-grid"/><text x={64+(width-104)*f} y="176" textAnchor={f===1?'end':'start'}>{new Date(start+(end-start)*f).toISOString().slice(11,16)}</text></g>)}
      <path d={`M64 18V150H${width-40}`} className="comparison-axis"/>{!directional && <><text x="4" y="35">{max.toFixed(1)}</text><text x="4" y="142">{min.toFixed(1)}</text></>}
      {curves.map((c,index) => <g key={c.id} stroke={colour(c.source_id)} fill={colour(c.source_id)}>
        {(c.samples ?? []).flatMap((s,i,ss) => {
          const next=ss[i+1]
          if (!next || s.run_id!==next.run_id || !numeric(s) || !numeric(next) || [s.lower,s.upper,next.lower,next.upper].some(e => typeof e?.value!=='number') || Number(s.lower?.value)>Number(s.upper?.value) || Number(next.lower?.value)>Number(next.upper?.value)) return []
          return [<path key={`band-${i}`} stroke="none" fillOpacity=".16" d={`M${x(Date.parse(s.time))},${y(Number(s.lower!.value))} L${x(Date.parse(next.time))},${y(Number(next.lower!.value))} L${x(Date.parse(next.time))},${y(Number(next.upper!.value))} L${x(Date.parse(s.time))},${y(Number(s.upper!.value))} Z`}/>]
        })}
        {group!=='precipitation' && !directional && !categorical && <path fill="none" strokeWidth="2" strokeDasharray={c.definition==='gust'?'5 3':undefined} d={linePath(c.samples ?? [],x,y)}/>}
        {group!=='precipitation'&&!directional&&(c.samples??[]).filter(s=>numeric(s)&&s.interval_start&&s.interval_end).map(s=><line key={`interval-${s.time}`} x1={x(Date.parse(s.interval_start!))} x2={x(Date.parse(s.interval_end!))} y1={y(value(s))} y2={y(value(s))} strokeWidth="4" opacity=".5"/>)}
        {(c.samples ?? []).filter(s => numeric(s) && (group!=='precipitation' || Boolean(s.interval_start && s.interval_end && Date.parse(s.interval_end)>start && Date.parse(s.interval_start)<end))).map(s => group==='precipitation' ? (s.interval_start && s.interval_end ? <rect key={s.time} x={x(Date.parse(s.interval_start))+index*2} y={Math.min(y(value(s)),y(0))} width={Math.max(1,x(Date.parse(s.interval_end))-x(Date.parse(s.interval_start))-3)} height={Math.abs(y(0)-y(value(s)))} fillOpacity=".35"/> : null) : directional ? <text key={s.time} x={x(Date.parse(s.time))} y="85" transform={`rotate(${value(s)},${x(Date.parse(s.time))},80)`}>↑</text> : <circle key={s.time} cx={x(Date.parse(s.time))} cy={y(value(s))} r="2.5"/>)}
      </g>)}
      {cursor>=start && cursor<end && <path d={`M${x(cursor)} 18V150`} className="comparison-shared-cursor"/>}
    </svg>}
    <div className="comparison-values">{curves.map(c => {
      const samples=c.samples ?? []
      const nearest=samples.reduce<Sample | null>((a,b) => !a || Math.abs(Date.parse(b.time)-cursor)<Math.abs(Date.parse(a.time)-cursor) ? b:a,null)
      return <span key={c.id}><b style={{color:colour(c.source_id)}}>{name(c.source_id)}{c.definition==='gust'?' gust':''}{member!=='summary'&&c.source_id==='ecmwf-ifs'?` member ${member}`:nearest?.evidence?.provenance.ensemble?.statistic==='ensemble_mean'?' mean':''}</b> {nearest && numeric(nearest) ? `${value(nearest).toFixed(1)} ${c.units ?? ''} · ${stamp(nearest.time)}` : c.reason ?? nearest?.reason ?? 'Awaiting samples'}{nearest && numeric(nearest) && nearest.reason ? ` · ${nearest.reason}` : ''}{typeof nearest?.lower?.value==='number' && typeof nearest?.upper?.value==='number' ? ` · P10–P90 ensemble spread: ${nearest.lower.value}–${nearest.upper.value}`:''}</span>
    })}{curves.length===0 && <span>{loading ? 'Loading native samples…' : 'No samples available'}</span>}</div>
  </section>
}
