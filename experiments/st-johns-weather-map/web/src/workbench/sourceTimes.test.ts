import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { timeMarkers, useSourceTimes, validateTimes } from './sourceTimes'
import { GRID_FIELD } from './sourceGrid'
import type { LayerSelection } from '../types'
const start=Date.parse('2026-09-08T00:00:00Z'), end=start+6*3600000
const point={sourceId:'google-weathernext-3-statistics',productId:'weathernext_3_0_0_statistics',product:'WeatherNext 3 local',field:GRID_FIELD,variant:{kind:'provider_statistic' as const,member:null,statistic:'ensemble_mean',quantile:null,threshold:null,comparison:null},level:'column'}
const stack:LayerSelection[]=[{id:'wn3',visible:false,pointOnly:true,opacity:.85,points:[point]}]
function body(){return {source_id:'google-weathernext-3-statistics' as const,product:'WeatherNext 3 local' as const,field:GRID_FIELD as 'weathernext3_total_cloud_cover_mean',start:new Date(start).toISOString(),end:new Date(end).toISOString(),expires_at:new Date(Date.now()+60000).toISOString(),objects:[],notices:[],frames:[1,2,3,4,5,6].map(h=>({valid_time:new Date(start+h*3600000).toISOString(),run_time:new Date(start).toISOString()}))}}
afterEach(()=>{vi.unstubAllGlobals()})
it('merges actual native times with map times and keeps run identity',()=>{
 const rows=[{id:'wn3',title:'WN3',inventory:body()}]
 const result=timeMarkers({markers:[{ms:start+3600000,time:new Date(start+3600000).toISOString(),layers:[{id:'radar',title:'Radar',color:'blue'}]}],axisless:[]},rows)
 expect(result.markers).toHaveLength(6)
 expect(result.markers[0].layers).toHaveLength(2)
 expect(result.markers[0].layers[1].runTime).toBe(new Date(start).toISOString())
 expect(timeMarkers({markers:[],axisless:[]},[{id:'wn3',title:'WN3',error:'Unavailable'}]).axisless).toEqual(['WN3: Unavailable'])
})
it('rejects invalid axes and scope mismatch',()=>{
 expect(()=>validateTimes(body(),'WeatherNext 3 historical',start,end)).toThrow()
 const invalid=body();invalid.frames.reverse()
 expect(()=>validateTimes(invalid,point.product,start,end)).toThrow()
})
it('Data only requests one inventory and opacity changes do not reacquire',async()=>{
 const fetcher=vi.fn(async(_url?:unknown)=>new Response(JSON.stringify(body())))
 vi.stubGlobal('fetch',fetcher)
 const {result,rerender,unmount}=renderHook(({stack})=>useSourceTimes(stack,start,end),{initialProps:{stack}})
 await waitFor(()=>expect(result.current[0].inventory?.frames).toHaveLength(6))
 rerender({stack:[{...stack[0],opacity:.3}]})
 expect(fetcher).toHaveBeenCalledTimes(1)
 expect(String(fetcher.mock.calls[0]?.[0])).toContain('/times?')
 unmount()
})
it('obsolete inventory cannot restore removed selections',async()=>{
 let resolve!:(value:Response)=>void
 vi.stubGlobal('fetch',()=>new Promise<Response>(done=>{resolve=done}))
 const {result,rerender,unmount}=renderHook(({stack})=>useSourceTimes(stack,start,end),{initialProps:{stack}})
 await waitFor(()=>expect(resolve).toBeDefined())
 rerender({stack:[]})
 await act(async()=>resolve(new Response(JSON.stringify(body()))))
 expect(result.current).toEqual([])
 unmount()
})
