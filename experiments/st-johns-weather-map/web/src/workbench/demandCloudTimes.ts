/** Advertised native times; never science sequence prefetch. Spec-Refs: GOV-SPEC-004, GOV-SPEC-006. */
import {useEffect,useState} from 'react'
import type {LayerSelection} from '../types'
import type {components} from '../generated/source-api'
import type {TimeRow} from './sourceTimes'
export const GOES_CLOUD='noaa-goes19-demand-cloud-mask'
export const RDPS_CLOUD='eccc-rdps-demand-total-cloud'
export function useDemandCloudTimes(stack:LayerSelection[],start:number,end:number):TimeRow[] {
  const wanted=stack.filter(s=>s.visible && [GOES_CLOUD,RDPS_CLOUD].includes(s.id)).map(s=>({id:s.id,title:s.id===GOES_CLOUD?'GOES-19 observed cloud mask':'RDPS total cloud · white opacity'}))
  const signature=JSON.stringify([wanted,start,end])
  const [state,setState]=useState<{signature:string;rows:TimeRow[]}>({signature:'',rows:[]})
  const [revision,setRevision]=useState(0)
  useEffect(()=>{
    const controller=new AbortController(),timers:ReturnType<typeof setTimeout>[]=[]
    const rows:TimeRow[]=wanted.map(r=>({...r,error:'Loading advertised native times'}))
    const publish=()=>{if(!controller.signal.aborted)setState({signature,rows:[...rows]})}
    publish()
    for(const row of wanted) {
      const params=new URLSearchParams({start:new Date(start).toISOString(),end:new Date(end).toISOString()})
      fetch(`/api/experiments/weather/v0/layers/${row.id}/times?${params}`,{signal:controller.signal}).then(async response=>{
        if(!response.ok)throw new Error(`Inventory unavailable (${response.status})`)
        const text=await response.text();if(text.length>1024*1024)throw new Error('Inventory size bound')
        const body=JSON.parse(text) as components["schemas"]["DemandLayerTimes"]
        if(body.layer_id!==row.id || body.basis!=='advertised_native_times' || !Array.isArray(body.frames) || body.frames.length>1200 || Date.parse(body.start)!==start || Date.parse(body.end)!==end || Date.parse(body.expires_at)<=Date.now())throw new Error('Invalid cloud inventory identity')
        let previous=-Infinity
        for(const frame of body.frames){const t=Date.parse(frame.valid_time),r=Date.parse(frame.run_time);if(!Number.isFinite(t)||!Number.isFinite(r)||r>t||t<=previous||t<start||t>end||(row.id===GOES_CLOUD&&(t>Date.now()||r!==t)))throw new Error('Invalid cloud native time');previous=t}
        rows[rows.findIndex(r=>r.id===row.id)]={...row,inventory:body,error:body.frames.length?undefined:body.notices.join(' ')};publish()
        if(!controller.signal.aborted)timers.push(setTimeout(()=>setRevision(v=>v+1),Math.max(0,Date.parse(body.expires_at)-Date.now())))
      }).catch(error=>{rows[rows.findIndex(r=>r.id===row.id)]={...row,error:String(error.message)};publish()})
    }
    return()=>{controller.abort();timers.forEach(clearTimeout)}
    // Presentation changes do not change the acquisition identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[signature,revision])
  return state.signature===signature?state.rows:wanted.map(row=>({...row,error:'Loading advertised native times'}))
}
