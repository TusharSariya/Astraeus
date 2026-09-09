import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { ServedFieldValue } from '../types'
import type { IFSGrid } from './IFSLayers'

// Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006. Display only, no acquisition.
export interface TemperatureSample {
  latitude: number; longitude: number; source: string; product: string | null
  run: string | null; time: string; variant: string; celsius: number; expires?: number
}
export interface ColourTarget extends Omit<TemperatureSample, 'celsius' | 'expires'> {}
export function temperatureFor(target: ColourTarget, samples: TemperatureSample[], hrdpsRun?: string, now = Date.now(), choice = 'auto') {
  const eligible = samples.filter(t => Number.isFinite(t.celsius) && Number.isFinite(Date.parse(t.time)) &&
    Date.parse(t.time) === Date.parse(target.time) && t.latitude === target.latitude && t.longitude === target.longitude &&
    (t.expires === undefined || t.expires > now))
  const own = eligible.find(t => t.source === target.source && !!target.run && t.run === target.run && t.product === target.product && t.variant === target.variant)
  if(choice==='same-source' || choice===target.source)return own ?? null
  const fallback = eligible.find(t => target.source !== 'eccc-hrdps' && t.source === 'eccc-hrdps' && !!t.run && t.variant === '[null,null]' && (!hrdpsRun || hrdpsRun === 'latest' || t.run === hrdpsRun))
    ?? null
  if(choice==='auto')return own ?? fallback
  if(choice==='eccc-hrdps')return fallback
  return eligible.find(t=>t.source===choice && !!t.run && t.variant==='[null,null]') ?? null
}
export function valueTarget(value: ServedFieldValue, latitude: number, longitude: number): ColourTarget {
  const a = value.attribution
  return { latitude, longitude, source:a.sourceId ?? '', product:a.product, run:a.runTime, time:a.validTime ?? '', variant:JSON.stringify([a.member,a.ensemble]) }
}
export function temperatureSample(value: ServedFieldValue, latitude: number, longitude: number): TemperatureSample | null {
  const a=value.attribution
  if (a.responseProvenance?.run_stale === true || a.qualityFlags.some(f=>/stale|expired|aged_out/.test(f)) || a.fieldKey !== 'temperature_2m' || !value.hasValue || value.value === null || !Number.isFinite(value.value) || a.qualityStatus === 'failed' || a.uncatalogued || a.derivationRefused || a.provenanceUnmodelled || a.evidenceClass === 'unrecognised') return null
  const celsius = value.units === 'K' ? value.value-273.15 : ['degC','°C'].includes(value.units ?? '') ? value.value : NaN
  if (!Number.isFinite(celsius)) return null
  const acquisition=a.responseProvenance?.source_acquisition as {expires_at?:string} | undefined
  return {...valueTarget(value,latitude,longitude),celsius,...(acquisition ? {expires:Date.parse(acquisition.expires_at ?? '')}: {})}
}
export function precipitationScale(field: string, units: string | null) {
  if (['precipitation_rate','rain_rate'].includes(field) && ['mm/h','mm h-1'].includes(units ?? '')) return {label:'Precipitation rate',units:units!,max:20}
  if (field === 'snow_rate' && ['cm/h','cm h-1','mm/h','mm h-1'].includes(units ?? '')) return {label:'Snowfall depth rate',units:units!,max:units?.startsWith('cm')?2:20}
  if (['precipitation_accumulation','tp:sfc'].includes(field) && ['mm','m','kg m-2'].includes(units ?? '')) return {label:'Interval precipitation amount',units:units!,max:units==='m'?.05:50}
  if (['snowfall','snowfall_accumulation','snow_depth'].includes(field) && ['cm','m','mm'].includes(units ?? '')) return {label:'Snowfall depth',units:units!,max:units==='m'?.2:units==='mm'?200:20}
  return null
}
export type PrecipitationScale = NonNullable<ReturnType<typeof precipitationScale>>
export function precipitationColour(value: number | null, temperature: number | null, scale: PrecipitationScale, opacity=1): [number,number,number,number] {
  const alpha=Math.round(Math.max(0,Math.min(1,opacity))*255)
  if (value === null || !Number.isFinite(value) || value < 0) return [135,135,135,alpha*.4]
  if (value === 0) return [0,0,0,0]
  const ratio=Math.max(0,Math.min(1,value/scale.max))
  const stops=temperature !== null && Number.isFinite(temperature) && temperature<=0 ? [[190,225,255],[65,145,220],[8,48,130]] : [[40,170,70],[250,220,50],[220,35,35]]
  const index=ratio<.5?0:1, t=ratio<.5?ratio*2:(ratio-.5)*2
  const c=stops[index].map((v,i)=>Math.round(v+(stops[index+1][i]-v)*t))
  return [c[0],c[1],c[2],alpha]
}
export const temperatureDescription = (t: TemperatureSample | null) => t ? `${t.celsius.toFixed(1)}°C · ${t.source} · ${t.time} · run ${t.run}` : 'Temperature unavailable'
export function PrecipitationLegend({scale}: {scale:PrecipitationScale}) {
  return <div className="precipitation-legend"><strong>Temperature-based colours</strong><p>Same source → HRDPS · loaded data only. 0°C is a display cutoff.</p>
    {[{name:'Above 0°C',temperature:1},{name:'At or below 0°C',temperature:0}].map(({name,temperature})=><div key={name}>{name}<span style={{display:'block',height:10,background:`linear-gradient(to right,${[0,.5,1].map(r=>`rgb(${precipitationColour(Math.max(.000001,r*scale.max),temperature,scale).slice(0,3).join(',')})`).join(',')})`}}/></div>)}
    <p>{scale.label}: 0–{scale.max}+ {scale.units}. Missing: neutral grey; zero: transparent. Temperature unavailable: intensity colours (green–yellow–red).</p>
  </div>
}
interface LoadedTemperatures { latitude:number; longitude:number; instant:number; samples:TemperatureSample[] }
const TemperatureContext=createContext<{loaded:LoadedTemperatures|null;publish:(v:LoadedTemperatures)=>void}>({loaded:null,publish:()=>{}})
export function TemperatureProvider({children}:{children:ReactNode}) {
  const [loaded,publish]=useState<LoadedTemperatures|null>(null)
  useEffect(()=>{
    const expiry=loaded?.samples.reduce((n,t)=>Math.min(n,t.expires ?? Infinity),Infinity) ?? Infinity
    if(!Number.isFinite(expiry))return
    const timer=setTimeout(()=>publish(current=>current?{...current,samples:current.samples.filter(t=>t.expires===undefined||t.expires>Date.now())}:current),Math.max(0,expiry-Date.now()))
    return ()=>clearTimeout(timer)
  },[loaded])
  const value=useMemo(()=>({loaded,publish}),[loaded])
  return <TemperatureContext.Provider value={value}>{children}</TemperatureContext.Provider>
}
export const useLoadedTemperatures=()=>useContext(TemperatureContext)
/** Exact native centres only: no interpolation or nearest-cell invention. */
export function gridTemperature(frame:IFSGrid,index:number,grids:IFSGrid[]):TemperatureSample|null {
  if (!Number.isFinite(Date.parse(frame.expires_at)) || Date.parse(frame.expires_at)<=Date.now())return null
  const y=Math.floor(index/frame.longitudes.length), x=index%frame.longitudes.length
  for(const t of grids) {
    if(t.field!=='2t:sfc'||t.level!==0||t.run_id!==frame.run_id||t.selection_product!==frame.selection_product||t.native_time!==frame.native_time||t.member!==frame.member||t.statistic!==frame.statistic||Date.parse(t.expires_at)<=Date.now()||!Number.isFinite(Date.parse(t.expires_at)))continue
    const ty=t.latitudes.indexOf(frame.latitudes[y]),tx=t.longitudes.indexOf(frame.longitudes[x]),v=t.values[ty]?.[tx]
    if(v===null||v===undefined||!Number.isFinite(v))continue
    const celsius=t.units==='K'?v-273.15:['degC','°C'].includes(t.units)?v:NaN
    if(Number.isFinite(celsius))return {latitude:frame.latitudes[y],longitude:frame.longitudes[x],source:'ecmwf-ifs',product:t.selection_product,run:t.run_time,time:t.native_time,variant:JSON.stringify([t.member,t.statistic]),celsius,expires:Date.parse(t.expires_at)}
  }
  return null
}

export function featurePrecipitation(feature: import('../types').GeoJsonFeature, samples:TemperatureSample[], choice='auto') {
  const p=feature.properties ?? {}, coordinates=feature.geometry?.type==='Point'?feature.geometry.coordinates:null
  if(!coordinates || !Array.isArray(coordinates) || typeof coordinates[0]!=='number' || typeof coordinates[1]!=='number')return null
  for(const field of ['precipitation_rate','snow_rate','precipitation_accumulation','snowfall_accumulation','snow_depth']) {
    const scale=precipitationScale(field,typeof p[`${field}_units`]==='string'?p[`${field}_units`] as string:null)
    if(!scale)continue
    const target:ColourTarget={longitude:coordinates[0],latitude:coordinates[1],source:typeof p.source_id==='string'?p.source_id:'',product:typeof p.product==='string'?p.product:null,run:typeof p.run_time==='string'?p.run_time:null,time:typeof p.valid_time==='string'?p.valid_time:'',variant:'[null,null]'}
    const own=typeof p.temperature_2m==='number' && ['degC','°C'].includes(String(p.temperature_2m_units)) ? [{...target,celsius:p.temperature_2m}] : []
    const temperature=temperatureFor(target,[...own,...samples],undefined,Date.now(),choice)
    return {field,scale,sourceChoice:choice as string | undefined,value:typeof p[field]==='number'?p[field] as number:null,temperature}
  }
  return null
}

export const ifsPrecipitationScale = (frame:IFSGrid) => !frame.statistic || frame.statistic==='ensemble_mean' ? precipitationScale(frame.field,frame.units) : null

export function TemperatureSourceControl({value='auto',onChange,catalog=[],providerImage=false}:{value?:string;onChange:(source:string)=>void;catalog?:import('../types').CatalogSource[];providerImage?:boolean}) {
  const {loaded}=useLoadedTemperatures()
  const sources=[...new Set([...catalog.filter(s=>s.fields?.some(f=>f.key==='temperature_2m')).map(s=>s.id),...(loaded?.samples.map(t=>t.source)??[]),...(!['auto','same-source','eccc-hrdps'].includes(value)?[value]:[])])].filter(id=>id!=='eccc-hrdps').sort()
  return <div className="precipitation-controls">
    <strong>{providerImage?'Provider colours':'Temperature-based colours'}</strong>
    <label>Temperature source<select value={value} onChange={e=>onChange(e.target.value)}><option value="auto">Auto · same source → HRDPS</option><option value="same-source">Same source only</option><option value="eccc-hrdps">HRDPS</option>{sources.map(id=><option key={id} value={id}>{id}</option>)}</select></label>
    <small>{providerImage?'Radar image keeps the provider palette. Temperature selection applies to numeric samples.':'Uses already loaded temperature at matching time and location.'} No extra temperature downloads.</small>
  </div>
}
