import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useWeatherNext, appendWeatherPage, type WeatherPage } from './WeatherNext'
import { parseFocusUrl, serializeFocusUrl } from './focusUrl'
const start=Date.UTC(2026,8,9),end=start+10*86400000
const location={id:'point',name:'Synthetic point',latitude:47.5,longitude:-52.7,kind:'map' as const}
const props={location,start,end,instant:start+3600000,enabled:true,onInstant:vi.fn()}
function Harness(p:Partial<typeof props>){return useWeatherNext({...props,...p})}
function page(selection:unknown):WeatherPage{return {completed_pages:4,total_pages:4,id:'fixed',selection,run_id:'fixed-run',run_time:new Date(start).toISOString(),expires_at:new Date(Date.now()+900000).toISOString(),native_times:[new Date(start+3600000).toISOString()],next_offset:null,state:'available',samples:[{time:new Date(start+3600000).toISOString(),expires_at:new Date(Date.now()+60000).toISOString(),provenance:null,summaries:['total','low','medium','high'].map(l=>({quantity:l+'_cloud_cover',unit:'percent',values:{p10:5,p25:10,p50:20,p75:40,p90:85,mean:25},state:'available',native_fields:[],grid:'0p1',level:'column',original_unit:'(0 - 1)',conversion_scale:100,conversion_offset:0,sampled_latitude:47.5,sampled_longitude:-52.7}))}]} as WeatherPage}
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()})
it('loads only the active section across the full range; inspection and thresholds do not acquire science',async()=>{
 const science=vi.fn(),threshold=vi.fn()
 vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
   const body=JSON.parse(String(options?.body??'{}'))
   if(url.endsWith('/threshold')){threshold(body);return {ok:true,json:async()=>({id:'fixed',run_time:new Date(start).toISOString(),estimates:{[new Date(start+3600000).toISOString()]:{lower:10,upper:25,basis:'Published percentiles'}}})}}
   science(body);return {ok:true,json:async()=>page(body)}
 }))
 const view=render(<Harness/>)
 await screen.findAllByText(/Median 20 %/)
 await waitFor(()=>expect(science).toHaveBeenCalledTimes(1))
 expect(science.mock.calls[0][0].end).toBe(new Date(end).toISOString())
 expect(science.mock.calls[0][0].section).toBe('clouds')
 fireEvent.click(screen.getByLabelText('Show mean'))
 fireEvent.change(screen.getByLabelText('Threshold (%)'),{target:{value:'40'}})
 fireEvent.click(screen.getByLabelText('Next Total time'))
 fireEvent.click(screen.getByText('Selected-time details'))
 view.rerender(<Harness instant={start+7200000}/>)
 await waitFor(()=>expect(threshold).toHaveBeenCalled())
 expect(science).toHaveBeenCalledTimes(1)
 view.rerender(<Harness enabled={false}/>)
 view.rerender(<Harness enabled={true}/>)
 expect(science).toHaveBeenCalledTimes(1)
})
it('does not load while hidden and keeps section and product explicit',async()=>{
 const requests:Record<string,unknown>[]=[]
 vi.stubGlobal('fetch',vi.fn(async(_url,options)=>{const body=JSON.parse(options.body);requests.push(body);return {ok:true,json:async()=>page(body)}}))
 const v=render(<Harness enabled={false}/>);await act(async()=>{})
 expect(requests).toHaveLength(0)
 fireEvent.click(screen.getByRole('button',{name:'Temperature'}))
 fireEvent.change(screen.getByLabelText('Product'),{target:{value:'station'}})
 v.rerender(<Harness enabled={true}/>)
 await waitFor(()=>expect(requests).toHaveLength(1))
 expect(requests[0]).toMatchObject({section:'temperature',product:'station'})
})
it('keeps completed pages and rejects a changed run',()=>{
 const first=page({}),second={...first,samples:[{...first.samples[0],time:new Date(start+7200000).toISOString()}]}
 expect(appendWeatherPage(first,second).samples).toHaveLength(2)
 expect(()=>appendWeatherPage(first,{...second,run_id:'different'})).toThrow(/Pinned/)
})
it('round trips WeatherNext navigation and docking without changing old stacks',()=>{
 const focus=parseFocusUrl('?view=weathernext&dock=map',location)
 expect(focus.view).toBe('WeatherNext');expect(focus.dock).toBe('Map')
 expect(parseFocusUrl(serializeFocusUrl(focus),location)).toMatchObject({view:'WeatherNext',dock:'Map',stack:null})
 expect(parseFocusUrl('?view=series',location).view).toBe('Series')
})

it('merges quantity pages for the same time without erasing completed or failed quantities',()=>{
 const full=page({})
 const first={...full,samples:[{...full.samples[0],summaries:full.samples[0].summaries.slice(0,1)}]}
 const later={...full,samples:[{...full.samples[0],summaries:[{...full.samples[0].summaries[1],state:'failed' as const}]}]}
 const merged=appendWeatherPage(first,later)
 expect(merged.samples).toHaveLength(1)
 expect(merged.samples[0].summaries.map(s=>s.quantity)).toEqual(['total_cloud_cover','low_cloud_cover'])
 expect(merged.samples[0].summaries[0].values.p50).toBe(20)
 expect(merged.samples[0].summaries[1].state).toBe('failed')
 expect(appendWeatherPage(merged,later).samples[0].summaries).toHaveLength(2)
})
