import {renderHook,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {useIFSGrids,ifsColor,ifsPolygon,type IFSGrid} from './IFSLayers'
import type {LayerSelection} from '../types'
const now=Date.parse('2026-09-09T00:00:00Z')
const frame={product:'atmosphere-control',selection_product:'atmosphere-control',field:'2t:sfc',level:0,member:'0',statistic:null,native_time:new Date(now).toISOString(),expires_at:new Date(now+600000).toISOString(),digest:'fixture',latitudes:[55,54.75],longitudes:[-70,-69.75],latitude_edges:[55.125,54.875,54.625],longitude_edges:[-70.125,-69.875,-69.625],values:[[280,281],[null,0]]} as IFSGrid
const layer=(id='one'):LayerSelection=>({id,visible:true,opacity:.7,ifs:{product:'atmosphere-control',field:'2t:sfc',level:0,run:'latest',member:'0',statistic:'',rendering:'scalar',title:'Temperature'}})
let calls:string[]
beforeEach(()=>{vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(now);calls=[];let n=0
 vi.stubGlobal('fetch',vi.fn(async(url:string,init?:RequestInit)=>{calls.push(`${init?.method??'GET'} ${url}`)
  if(init?.method==='DELETE')return new Response(null,{status:204})
  if(url.includes('/runs/'))return new Response(JSON.stringify([{id:'run',run_time:new Date(now).toISOString(),files:{0:'fixture'}}]))
  if(init?.method==='POST')return new Response(JSON.stringify({id:`job-${++n}`,next_cursor:null,completed:1,total:1,items:[]}))
  if(url.includes('/grid?'))return new Response(JSON.stringify(frame))
  throw new Error(`Unexpected ${url}`)
 }))
})
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()})
it('clips native cell edges and distinguishes zero from missing',()=>{
 expect(ifsPolygon(frame,0)).toEqual([[-70,54.875],[-69.875,54.875],[-69.875,55],[-70,55]])
 expect(ifsColor(null,1,0,1,'scalar')).not.toEqual(ifsColor(0,1,0,1,'scalar'))
 expect(ifsColor(0,1,0,1,'cloud')[3]).toBe(0)
})
it('opacity and visibility reuse the loaded selection',async()=>{
 const {result,rerender}=renderHook(({stack})=>useIFSGrids(stack,now),{initialProps:{stack:[layer()]}})
 await waitFor(()=>expect(result.current[0].frame).toBeDefined())
 const n=calls.length
 rerender({stack:[{...layer(),opacity:.2}]});await waitFor(()=>expect(result.current[0].frame).toBeDefined())
 expect(calls).toHaveLength(n)
 rerender({stack:[{...layer(),ifs:{...layer().ifs!,rendering:'cloud'}}]});expect(calls).toHaveLength(n)
 rerender({stack:[{...layer(),visible:false}]});expect(result.current).toEqual([])
 rerender({stack:[layer()]});expect(result.current[0].frame).toBeDefined();expect(calls).toHaveLength(n)
})
it('adding a layer starts only its own acquisition',async()=>{
 const {result,rerender}=renderHook(({stack})=>useIFSGrids(stack,now),{initialProps:{stack:[layer()]}})
 await waitFor(()=>expect(result.current[0].frame).toBeDefined())
 rerender({stack:[layer(),layer('two')]})
 await waitFor(()=>expect(result.current.filter(r=>r.frame)).toHaveLength(2))
 expect(calls.filter(c=>c.startsWith('POST'))).toHaveLength(2)
 expect(calls.filter(c=>c.startsWith('DELETE'))).toHaveLength(0)
})
it('exposes a hidden temperature to display consumers without reacquisition',async()=>{
 const {result,rerender}=renderHook(({stack})=>useIFSGrids(stack,now,true),{initialProps:{stack:[layer()]}})
 await waitFor(()=>expect(result.current[0].frame).toBeDefined())
 const n=calls.length
 rerender({stack:[{...layer(),visible:false,opacity:.1}]})
 expect(result.current[0].frame).toBeDefined();expect(calls).toHaveLength(n)
})
it('withholds the previous time immediately while a new selection is pending',async()=>{
 const {result,rerender}=renderHook(({instant})=>useIFSGrids([layer()],instant,true),{initialProps:{instant:now}})
 await waitFor(()=>expect(result.current[0].frame).toBeDefined())
 rerender({instant:now+3600000})
 expect(result.current.some(r=>r.frame)).toBe(false)
})
