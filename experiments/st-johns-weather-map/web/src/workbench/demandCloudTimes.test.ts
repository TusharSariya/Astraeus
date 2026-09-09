import {renderHook,waitFor,act} from '@testing-library/react'
import {it,expect,vi} from 'vitest'
import {useDemandCloudTimes,GOES_CLOUD} from './demandCloudTimes'
import {timeMarkers} from './sourceTimes'
import {resolveLayerFrame} from '../api'
import type {LayerItem} from '../types'
it('loads only metadata, contributes real observed markers and ignores opacity',async()=>{
 const end=Date.now(),start=end-3600000,t=new Date(end-600000).toISOString()
 const fetcher=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({layer_id:GOES_CLOUD,basis:'advertised_native_times',start:new Date(start).toISOString(),end:new Date(end).toISOString(),expires_at:new Date(end+60000).toISOString(),frames:[{valid_time:t,run_time:t}],notices:['Advertised only']})))
 const stack=[{id:GOES_CLOUD,visible:true,opacity:.8}]
 const {result,rerender,unmount}=renderHook(({stack})=>useDemandCloudTimes(stack,start,end),{initialProps:{stack}})
 await waitFor(()=>expect(result.current[0].inventory?.frames).toHaveLength(1))
 expect(String(fetcher.mock.calls[0][0])).toContain('/times?')
 const markers=timeMarkers({markers:[],axisless:[]},result.current)
 expect(markers.markers[0].time).toBe(t);expect(markers.markers[0].layers[0].title).toContain('observed scan')
 rerender({stack:[{...stack[0],opacity:.2}]});expect(fetcher).toHaveBeenCalledTimes(1)
 unmount();fetcher.mockRestore()
})
it('ignores obsolete inventory and refuses future observed stamps',async()=>{
 let release!:(r:Response)=>void
 const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(()=>new Promise(r=>release=r))
 const end=Date.now(),start=end-3600000,stack=[{id:GOES_CLOUD,visible:true,opacity:1}]
 const {result,rerender,unmount}=renderHook(({stack})=>useDemandCloudTimes(stack,start,end),{initialProps:{stack}})
 rerender({stack:[]})
 await act(async()=>release(new Response('{}')))
 expect(result.current).toEqual([]);unmount();fetcher.mockRestore()
 const layer={id:GOES_CLOUD,evidence_basis:'demand_query',raster_available:true,times:[]} as unknown as LayerItem
 expect(resolveLayerFrame(layer,new Date(end+3600000),{interpolate:true,reference:new Date(end)}).kind).toBe('none')
 expect(resolveLayerFrame(layer,new Date(end-600000),{interpolate:true,reference:new Date(end)}).kind).toBe('exact')
})
