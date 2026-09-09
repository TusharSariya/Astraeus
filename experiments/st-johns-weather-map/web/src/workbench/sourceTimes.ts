/** Native time coordinates, never a forecast sequence. Spec-Refs: GOV-SPEC-004, GOV-SPEC-006. */
import { useEffect, useState } from 'react'
import type { components } from '../generated/source-api'
import type { FrameMarkers } from '../api'
import type { LayerSelection } from '../types'
import { isGridPoint, GRID_FIELD, wn3Request } from './sourceGrid'
import { pointLabel } from './pointSelections'

type Inventory = components['schemas']['SourceTimesResponse']
export interface TimeRow { id: string; title: string; inventory?: Pick<Inventory,"frames"|"notices"|"expires_at">; error?: string }
export function validateTimes(body: Inventory, product: string, start: number, end: number): Inventory {
  if (body.source_id !== 'google-weathernext-3-statistics' || body.product !== product || body.field !== GRID_FIELD
    || Date.parse(body.start) !== start || Date.parse(body.end) !== end || !(Date.parse(body.expires_at)>Date.now())
    || !Array.isArray(body.frames) || body.frames.length>720) throw new Error('Invalid WN3 time inventory')
  let previous=-Infinity
  for (const frame of body.frames) {
    const stamp=Date.parse(frame.valid_time), run=Date.parse(frame.run_time)
    if (!Number.isFinite(stamp) || !Number.isFinite(run) || stamp<=previous || stamp<start || stamp>end || run>=stamp || stamp-run>360*3600000) throw new Error('Invalid native WN3 time')
    previous=stamp
  }
  return body
}
export function timeMarkers(base: FrameMarkers, rows: TimeRow[]): FrameMarkers {
  const byTime=new Map(base.markers.map(m=>[m.ms,{...m,layers:[...m.layers]}]))
  const axisless=[...base.axisless]
  for (const row of rows) {
    if (!row.inventory?.frames.length) axisless.push(`${row.title}: ${row.error ?? 'no available times in this range'}`)
    for (const frame of row.inventory?.frames ?? []) {
      const ms=Date.parse(frame.valid_time), layer={id:row.id,title:`${row.title} · ${row.id==='noaa-goes19-demand-cloud-mask'?'observed scan':'native forecast time'}`,color:'#c792ea',runTime:row.id==='noaa-goes19-demand-cloud-mask'?undefined:frame.run_time}
      const old=byTime.get(ms)
      if (old) old.layers.push(layer)
      else byTime.set(ms,{ms,time:frame.valid_time,layers:[layer]})
    }
  }
  return {markers:[...byTime.values()].sort((a,b)=>a.ms-b.ms),axisless}
}
export function useSourceTimes(stack: LayerSelection[], start: number, end: number): TimeRow[] {
  const wanted=stack.filter(s=>isGridPoint(s.points?.[0])).map(s=>({id:s.id,title:pointLabel(s.points![0]),product:s.points![0].product}))
  const signature=JSON.stringify([wanted,start,end])
  const [revision,setRevision]=useState(0)
  const [state,setState]=useState<{signature:string;rows:TimeRow[]}>({signature:'',rows:[]})
  useEffect(()=>{
    const controller=new AbortController(), timers: ReturnType<typeof setTimeout>[]=[]
    const rows:TimeRow[]=wanted.map(row=>({...row,error:'Loading available forecast times'}))
    const publish=()=>{if(!controller.signal.aborted)setState({signature,rows:[...rows]})}
    publish()
    // One inventory per scope; ignore opacity, point location and selected-frame changes.
    queueMicrotask(()=>{
      if(controller.signal.aborted)return
      for(const product of new Set(wanted.map(row=>row.product))) {
        wn3Request(controller.signal,async()=>{
          const params=new URLSearchParams({product,field:GRID_FIELD,start:new Date(start).toISOString(),end:new Date(end).toISOString()})
          const response=await fetch(`/api/experiments/weather/v0/sources/google-weathernext-3-statistics/times?${params}`,{signal:controller.signal})
          if(!response.ok)throw new Error(`Available times unavailable (${response.status})`)
          const body=await response.text()
          if(body.length>1024*1024)throw new Error('Time inventory response too large')
          return validateTimes(JSON.parse(body),product,start,end)
        }).then(inventory=>{
          if(controller.signal.aborted)return
          rows.forEach((row,i)=>{if(wanted[i].product===product)rows[i]={...row,inventory,error:undefined}})
          publish()
          timers.push(setTimeout(()=>{
            rows.forEach((row,i)=>{if(wanted[i].product===product)rows[i]={id:row.id,title:row.title,error:'Time inventory expired; reselect range to refresh'}})
            publish()
            setRevision(value=>value+1)
          },Math.max(0,Date.parse(inventory.expires_at)-Date.now())))
        }).catch(error=>{
          if(controller.signal.aborted)return
          rows.forEach((row,i)=>{if(wanted[i].product===product)rows[i]={id:row.id,title:row.title,error:String(error.message)}})
          publish()
        })
      }
    })
    return()=>{controller.abort();timers.forEach(clearTimeout)}
    // Signature contains only acquisition identity, not map presentation state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[signature,revision])
  return state.signature===signature?state.rows:wanted.map(row=>({...row,error:'Loading available forecast times'}))
}
