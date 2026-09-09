import { useEffect, useMemo, useState } from 'react'
import type { components } from '../generated/source-api'
import type { GeoJsonFeature, LayerSelection, PointFieldSelection } from '../types'

export type SourceGrid = components['schemas']['SourceGridResponse']
export const GRID_FIELD = 'weathernext3_total_cloud_cover_mean'
export const isGridPoint = (p?: PointFieldSelection) => p?.sourceId === 'google-weathernext-3-statistics' && p.field === GRID_FIELD && ['WeatherNext 3 local','WeatherNext 3 historical'].includes(p.product)
export const gridKey = (product: string, instant: number) => `${product}:${Math.ceil(instant / 3600000) * 3600000}`
let active = 0
const waiting: Array<() => void> = []
/** All WN3 point and grid HTTP requests share these two slots. */
export async function wn3Request<T>(signal: AbortSignal | undefined, action: () => Promise<T>): Promise<T> {
  if (active >= 2) await new Promise<void>(resolve => waiting.push(resolve))
  else active++
  try { signal?.throwIfAborted(); return await action() }
  finally { const next=waiting.shift(); if(next) next(); else active-- }
}
const pending = new Map<string, {promise:Promise<SourceGrid>;signal:AbortSignal}>()
const cache = new Map<string, SourceGrid>()
export async function waitForGrid(product: string, instant: number) {
  await pending.get(gridKey(product,instant))?.promise
}
export function validateGrid(value: SourceGrid, product: string, instant: number): SourceGrid {
  const n = Date.parse(value.native_time), acquisition = value.provenance?.source_acquisition
  if (value.source_id !== 'google-weathernext-3-statistics' || value.field !== GRID_FIELD || value.product !== product || value.statistic !== 'ensemble_mean' || n !== Math.ceil(instant/3600000)*3600000 || !acquisition || Date.parse(acquisition.expires_at) <= Date.now() || value.region.join(',') !== '-70,40,-40,55') throw new Error('Grid identity or evidence expiry invalid')
  for (const [axis,edges] of [[value.latitudes,value.latitude_edges],[value.longitudes,value.longitude_edges]]) {
    if (axis.length < 2 || axis.length > 302 || edges.length !== axis.length + 1 || [...axis,...edges].some(v => !Number.isFinite(v))) throw new Error('Invalid grid axes')
    const direction = Math.sign(axis[1]-axis[0])
    if (axis.slice(1).some((v,i) => Math.abs((v-axis[i])*direction-.1) > .00005 || Math.abs(edges[i+1]-(v+axis[i])/2)>1e-8)) throw new Error('Invalid native boundaries')
  }
  if (value.percentages.length !== value.latitudes.length || value.percentages.some(row => row.length !== value.longitudes.length || row.some(v => v !== null && (!Number.isFinite(v) || v < 0 || v > 100)))) throw new Error('Invalid cloud cells')
  return value
}
async function acquire(product: string, instant: number, signal: AbortSignal): Promise<SourceGrid> {
  const key = gridKey(product,instant), old = cache.get(key)
  if (old && Date.parse(old.provenance.source_acquisition!.expires_at)>Date.now()) return old
  cache.delete(key)
  const existing = pending.get(key)
  if (existing && !existing.signal.aborted) return existing.promise
  const promise = wn3Request(signal, async () => {
    const params = new URLSearchParams({ product, region:"atlantic", field:GRID_FIELD, selected_time:new Date(instant).toISOString() })
    const response = await fetch(`/api/experiments/weather/v0/sources/google-weathernext-3-statistics/grid?${params}`, { signal })
    if (!response.ok) throw new Error(response.status === 403 ? 'WeatherNext credentials required' : `WeatherNext grid unavailable (${response.status})`)
    const reader = response.body?.getReader()
    if (!reader) throw new Error('Grid response body unavailable')
    const chunks: Uint8Array[] = []; let size = 0
    try { for (;;) { const {done,value} = await reader.read(); if (done) break; size += value.byteLength; if (size>2*1024*1024) throw new Error('Grid response exceeds 2 MiB'); chunks.push(value) } }
    finally { await reader.cancel(); reader.releaseLock() }
    const bytes = new Uint8Array(size); let offset=0
    for (const chunk of chunks) { bytes.set(chunk,offset); offset+=chunk.byteLength }
    const grid = validateGrid(JSON.parse(new TextDecoder().decode(bytes)),product,instant)
    signal.throwIfAborted(); cache.set(key,grid)
    while (cache.size>4 || [...cache.values()].reduce((n,g)=>n+JSON.stringify(g).length,0)>8*1024*1024) cache.delete(cache.keys().next().value!)
    return grid
  })
  pending.set(key,{promise,signal})
  try { return await promise } finally { if (pending.get(key)?.promise===promise) pending.delete(key) }
}
export interface GridState { id: string; product: string; frame?: SourceGrid; error?: string }
export function useSourceGrids(stack: LayerSelection[], instant: number) {
  const wanted: GridState[] = stack.filter(s => s.visible && !s.pointOnly && isGridPoint(s.points?.[0])).map(s => ({id:s.id,product:s.points![0].product}))
  const signature=JSON.stringify([wanted,instant])
  const [state,setState]=useState<{signature:string;rows:GridState[]}>({signature:'',rows:[]})
  useEffect(() => {
    const controller=new AbortController(), timers: ReturnType<typeof setTimeout>[]=[]
    setState({signature,rows:wanted})
    queueMicrotask(() => {
    if (controller.signal.aborted) return
    for (const item of wanted) acquire(item.product,instant,controller.signal).then(frame => {
      if (controller.signal.aborted) return
      setState(s=>s.signature===signature?{...s,rows:s.rows.map(row=>row.id===item.id?{...item,frame}:row)}:s)
      timers.push(setTimeout(()=>setState(s=>s.signature===signature?{...s,rows:s.rows.map(row=>row.id===item.id?{...item,error:'WeatherNext grid evidence expired'}:row)}:s),Math.max(0,Date.parse(frame.provenance.source_acquisition!.expires_at)-Date.now())))
    }).catch(error=>{if(!controller.signal.aborted)setState(s=>s.signature===signature?{...s,rows:s.rows.map(row=>row.id===item.id?{...item,error:String(error.message ?? error)}:row)}:s)})
    })
    return ()=>{controller.abort();timers.forEach(clearTimeout)}
  },[signature])
  return useMemo(()=>state.signature===signature?state.rows:wanted,[state,signature])
}
export function gridCell(frame: SourceGrid, index: number): GeoJsonFeature {
  const y=Math.floor(index/frame.longitudes.length),x=index%frame.longitudes.length
  return {type:'Feature',geometry:{type:'Polygon',coordinates:[gridPolygon(frame,index)]},properties:{
    name:`${frame.percentages[y][x]===null?'Missing':`${frame.percentages[y][x]}%`} ensemble-mean cloud cover`,
    percentage:frame.percentages[y][x],native_centre:{latitude:frame.latitudes[y],longitude:frame.longitudes[x]},
    native_footprint:{latitude:frame.latitude_edges.slice(y,y+2),longitude:frame.longitude_edges.slice(x,x+2)},
    statistic:frame.statistic,valid_time:frame.native_time,run:frame.provenance.run_time}}
}
export function gridPolygon(frame: SourceGrid, index: number): [number,number][] {
  const y=Math.floor(index/frame.longitudes.length),x=index%frame.longitudes.length
  const south=Math.max(frame.region[1],Math.min(frame.latitude_edges[y],frame.latitude_edges[y+1]))
  const north=Math.min(frame.region[3],Math.max(frame.latitude_edges[y],frame.latitude_edges[y+1]))
  const west=Math.max(frame.region[0],Math.min(frame.longitude_edges[x],frame.longitude_edges[x+1]))
  const east=Math.min(frame.region[2],Math.max(frame.longitude_edges[x],frame.longitude_edges[x+1]))
  return [[west,south],[east,south],[east,north],[west,north],[west,south]]
}
export const gridIndices = (frame: SourceGrid) => Array.from({length:frame.latitudes.length*frame.longitudes.length},(_,i)=>i)
// Compatibility helper for small fixture callers; map geometry uses indices.
export const gridFeatures = (frame: SourceGrid) => gridIndices(frame).map(i=>gridCell(frame,i))
export const cloudColor = (percentage: number | null, opacity: number): [number,number,number,number] => percentage === null ? [130,130,130,45*opacity] : [222,231,242,255*percentage/100*opacity]
