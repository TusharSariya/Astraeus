import { StrictMode } from 'react'
import { describe,it,expect,vi } from 'vitest'
import { renderHook,waitFor,act } from '@testing-library/react'
import { cloudColor,gridKey,GRID_FIELDS,gridFeatures,validateGrid,useSourceGrids,wn3Request,GRID_FIELD,type SourceGrid } from './sourceGrid'
import { cycleSelection,parseSelection,pointSelectionId } from './pointSelections'
import type { PointFieldSelection } from '../types'
const point:PointFieldSelection={sourceId:'google-weathernext-3-statistics',productId:'weathernext_3_0_0_statistics',product:'WeatherNext 3 local',field:GRID_FIELD,variant:{kind:'provider_statistic',statistic:'ensemble_mean'},level:'column'}
const instant=Date.parse('2026-09-08T12:00:00Z')
function frame():SourceGrid {
  const lats=Array.from({length:151},(_,i)=>55-i*.1),lons=Array.from({length:301},(_,i)=>-70+i*.1)
  return {source_id:point.sourceId,product:point.product,field:GRID_FIELD,statistic:'ensemble_mean',selected_time:new Date(instant).toISOString(),native_time:new Date(instant).toISOString(),region:[-70,40,-40,55],latitudes:lats,longitudes:lons,latitude_edges:Array.from({length:152},(_,i)=>55.05-i*.1),longitude_edges:Array.from({length:302},(_,i)=>-70.05+i*.1),percentages:lats.map(()=>lons.map(()=>50)),provenance:{native_variable:'total_cloud_cover_mean',source_acquisition:{expires_at:new Date(Date.now()+60000).toISOString()},valid_time:new Date(instant).toISOString()}} as SourceGrid
}
describe('native WN3 grid display',()=>{
  it('maps valid zero, 50 and 100 percent without gamma or opacity exponent',()=>{
    expect(cloudColor(0,.8)[3]).toBe(0);expect(cloudColor(50,.8)[3]).toBe(102);expect(cloudColor(100,.8)[3]).toBe(204)
    expect(cloudColor(null,.8)).not.toEqual(cloudColor(0,.8))
  })
  it('retains 45451 adjoining clipped native polygons and inspectable clear/missing cells',()=>{
    const g=frame();g.percentages[0][0]=0;g.percentages[0][1]=null
    const features=gridFeatures(g)
    expect(features).toHaveLength(45451)
    expect(features[0].properties?.percentage).toBe(0);expect(features[1].properties?.percentage).toBeNull()
    const a=features[0].geometry as {coordinates:number[][][]},b=features[1].geometry as {coordinates:number[][][]}
    expect(a.coordinates[0][1]).toEqual(b.coordinates[0][0])
    expect(a.coordinates[0][2][1]).toBe(55);expect(a.coordinates[0][0][0]).toBe(-70)
    expect(features[0].properties?.native_centre).toEqual({latitude:55,longitude:-70})
  })
  it('cycles Map + data, Data only, Off while preserving saved point-only state',()=>{
    const id=pointSelectionId(point)
    let stack=cycleSelection([],id,point,undefined,true)
    expect(stack[0].visible).toBe(true);expect(stack[0].pointOnly).toBeUndefined()
    stack=cycleSelection(stack,id,point,undefined,true);expect(stack[0].visible).toBe(false)
    expect(parseSelection(stack[0]).points).toEqual([point])
    expect(cycleSelection(stack,id,point,undefined,true)).toEqual([])
    const old=cycleSelection([],id,point)[0];expect(parseSelection(old).pointOnly).toBe(true);expect(old.visible).toBe(false)
  })
  it('refuses wrong scope, native time, masks and stale evidence',()=>{
    expect(validateGrid(frame(),point.product,instant)).toBeTruthy()
    expect(()=>validateGrid(frame(),'WeatherNext 3 historical',instant)).toThrow()
    expect(()=>validateGrid(frame(),point.product,instant+1)).toThrow()
    const g=frame();g.percentages[0][0]=101;expect(()=>validateGrid(g,point.product,instant)).toThrow()
  })
  it('bounds point and grid requests to two even when cancellation is ignored',async()=>{
    const releases:Array<()=>void>=[];let active=0,maximum=0
    const jobs=Array.from({length:5},()=>wn3Request(undefined,async()=>{active++;maximum=Math.max(maximum,active);await new Promise<void>(r=>releases.push(r));active--}))
    await waitFor(()=>expect(releases.length).toBe(2));releases.shift()!();await waitFor(()=>expect(releases.length).toBe(2))
    while(releases.length){releases.shift()!();await act(async()=>{await Promise.resolve()})}
    await Promise.all(jobs);expect(maximum).toBe(2)
  })
  it('does not acquire Data only; removes obsolete frames even if fetch ignores abort',async()=>{
    let release:((v:Response)=>void)|undefined
    const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(()=>new Promise(r=>{release=r}))
    const id=pointSelectionId(point),map=cycleSelection([],id,point,undefined,true),data=cycleSelection(map,id,point,undefined,true)
    const {result,rerender,unmount}=renderHook(({stack,time})=>useSourceGrids(stack,time),{initialProps:{stack:data,time:instant}})
    expect(fetcher).not.toHaveBeenCalled()
    rerender({stack:map,time:instant});await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(1))
    rerender({stack:data,time:instant+3600000});expect(result.current).toEqual([])
    await act(async()=>release!(new Response(JSON.stringify(frame()))))
    expect(result.current).toEqual([]);unmount();fetcher.mockRestore()
  })
})


it('survives StrictMode and clears a failed replacement without viewport reacquisition',async()=>{
  const nextInstant=instant+86400000, g=frame()
  g.native_time=g.selected_time=new Date(nextInstant).toISOString()
  const fetcher=vi.spyOn(globalThis,'fetch').mockResolvedValueOnce(new Response(JSON.stringify(g))).mockResolvedValue(new Response('{}',{status:503}))
  const map=cycleSelection([],pointSelectionId(point),point,undefined,true)
  const {result,rerender,unmount}=renderHook(({stack,time})=>useSourceGrids(stack,time),{wrapper:StrictMode,initialProps:{stack:map,time:nextInstant}})
  await waitFor(()=>expect(result.current[0]?.frame).toBeTruthy())
  expect(fetcher).toHaveBeenCalledTimes(1)
  rerender({stack:map.map(s=>({...s,opacity:.2})),time:nextInstant})
  expect(result.current[0].frame).toBeTruthy();expect(fetcher).toHaveBeenCalledTimes(1)
  rerender({stack:map,time:nextInstant+3600000})
  expect(result.current[0].frame).toBeUndefined()
  await waitFor(()=>expect(result.current[0].error).toContain('unavailable'))
  expect(result.current[0].frame).toBeUndefined();unmount();fetcher.mockRestore()
})

it('keeps each of the four mean fields in grid and point cache identity',()=>{
 expect(new Set(GRID_FIELDS.map(field=>gridKey(point.product,instant,field))).size).toBe(4)
 for(const field of GRID_FIELDS){const g=frame();g.field=field as SourceGrid['field'];g.provenance.native_variable=field.replace('weathernext3_','');expect(validateGrid(g,point.product,instant,field)).toBe(g)}
 const wrong=frame();wrong.field='weathernext3_low_cloud_cover_mean';expect(()=>validateGrid(wrong,point.product,instant,wrong.field)).toThrow()
})
