import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { loadPoint, normalizePoint } from '../api'
import { stations, unavailableSnapshot } from '../fixtures'
import type { CatalogSource, LayerSelection, SourceCapability } from '../types'
import { PointDataPanel, openPointData, relativeValidTime, compactValue, concisePointReason } from './PointDataPanel'
import { pointDefault, pointSelectionId } from './pointSelections'

vi.mock('../api', async original => ({...await original<typeof import('../api')>(),loadPoint:vi.fn()}))
const cap=(source_id='s',field='temperature_2m'):SourceCapability=>({source_id,product_id:source_id,point_product:source_id,field,variants:[{kind:'deterministic'}],levels:['2 m'],point:true,native_series:false,directional_time_selection:false,run_selection:'latest',time_semantics:'Native',coverage_description:'Declared'})
const sources=['s','other'].map(id=>({id,capabilities:[cap(id),cap(id,'dew_point_2m')],fields:[{key:'temperature_2m',family:'temperature'},{key:'dew_point_2m',family:'temperature'}]} as CatalogSource))
const selected=(source='s',field='temperature_2m'):LayerSelection=>{const p=pointDefault(cap(source,field));return {id:pointSelectionId(p),visible:false,opacity:.85,pointOnly:true,points:[p]}}
const instant=Date.parse('2026-09-08T12:00:00Z')
const response=(source='s')=>({source:'live' as const,snapshot:normalizePoint({selection:{mode:'evidence_only',badge:'Evidence'},data_mode:'live',valid_time:'2026-09-08T12:00:00Z',fields:[
  ...['temperature_2m','dew_point_2m'].map((key,index)=>({field:index?'dew_point':'temperature',key,family:'temperature',value:index?1234:17,provenance:{source_id:source,provider:source,product:source,normalized_units:'degC',data_mode:'live',evidence_class:'retrieved',valid_time:'2026-09-08T11:00:00Z',quality:{status:'passed',flags:[]}}})),
]})})
beforeEach(()=>{vi.mocked(loadPoint).mockReset();localStorage.clear();vi.useFakeTimers();vi.mocked(loadPoint).mockImplementation(async(_l,_t,product)=>response(product))})
afterEach(()=>vi.useRealTimers())
const settle=async()=>act(async()=>{await vi.advanceTimersByTimeAsync(250)})
const props={layers:[],catalog:sources,location:stations[0],instant,drawn:[]}
it('groups only selected fields and keeps two sources separate, with native times and details return', async()=>{
  render(<PointDataPanel {...props} stack={[selected(),selected('other')]} />)
  await settle()
  expect(loadPoint).toHaveBeenCalledTimes(2)
  expect(screen.queryByText(/1234/)).not.toBeInTheDocument()
  const panel=screen.getByRole('complementary',{name:'Point data'})
  expect(within(panel).getAllByText('17 degC')).toHaveLength(2)
  const opener=screen.getByRole('button',{name:'Details for point reading s · temperature 2m'})
  const contents=panel.querySelector('.point-data-contents')!;contents.scrollTop=72
  fireEvent.click(opener)
  expect(screen.getByText('Offset seconds').nextSibling).toHaveTextContent('-3600')
  fireEvent.keyDown(screen.getByRole('heading',{name:'Evidence · s · temperature 2m'}),{key:'Escape'})
  await act(async()=>{await vi.advanceTimersByTimeAsync(20)})
  expect(opener).toHaveFocus();expect(contents.scrollTop).toBe(72)
  fireEvent.keyDown(opener,{key:'Escape'})
  expect(screen.getByRole('button',{name:'Expand Point data'})).toBeInTheDocument()
})
it('refreshes minimized data, immediately withholds old Focus values and restores the preference', async()=>{
  const {rerender,unmount}=render(<PointDataPanel {...props} stack={[selected()]} />)
  await settle();expect(screen.getByText('17 degC')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Minimize Point data'}))
  rerender(<PointDataPanel {...props} instant={instant+60000} stack={[selected(),selected('s','dew_point_2m')]} />)
  expect(screen.queryByText('17 degC')).not.toBeInTheDocument()
  await settle();expect(loadPoint).toHaveBeenCalledTimes(2)
  expect(screen.getByRole('button',{name:'Expand Point data'})).toBeInTheDocument()
  expect(screen.getByText('2 selected fields')).toBeInTheDocument()
  unmount();render(<PointDataPanel {...props} stack={[]} />)
  expect(screen.getByRole('button',{name:'Expand Point data'})).toBeInTheDocument()
})
it('expands and focuses a selected layer reading without removing other fields', async()=>{
  const first=selected()
  render(<PointDataPanel {...props} stack={[first,selected('other')]} />)
  fireEvent.click(screen.getByRole('button',{name:/Temperature/}))
  fireEvent.click(screen.getByRole('button',{name:'Minimize Point data'}))
  act(()=>openPointData(first.id))
  expect(screen.getByRole('button',{name:'Details for point reading s · temperature 2m'})).toHaveFocus()
  expect(screen.getByRole('button',{name:'Details for point reading other · temperature 2m'})).toBeVisible()
})
it('keeps image-only, credentials refusal and partial readings independent', async()=>{
  vi.mocked(loadPoint).mockImplementation(async(_l,_t,product)=>product==='other'?{source:'unavailable',snapshot:unavailableSnapshot,error:'Credentials required'}:response())
  render(<PointDataPanel {...props} stack={[selected(),selected('other'),{id:'image-only',visible:true,opacity:1}]} />)
  await settle()
  expect(screen.getByText('17 degC')).toBeInTheDocument()
  expect(screen.getByText('Credentials required')).toBeInTheDocument()
  expect(screen.getByText('Point unsupported')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:/Point data not available \(2\)/})).toHaveAttribute('aria-expanded','true')
  expect(screen.queryByText('Frame: None drawn')).not.toBeInTheDocument()
})
it('withholds an unavailable field and a removed capability instead of displaying another response field', async()=>{
  vi.mocked(loadPoint).mockResolvedValue({source:'live',snapshot:{...response().snapshot,servedFields:[]}})
  const {rerender}=render(<PointDataPanel {...props} stack={[selected()]} />)
  await settle();expect(screen.getByText('No reading at selected time')).toBeInTheDocument()
  rerender(<PointDataPanel {...props} catalog={[]} stack={[selected()]} />)
  expect(screen.getByText('Point unsupported')).toBeInTheDocument()
})
it('does not present an explicitly enabled development fallback as current evidence', async()=>{
  vi.mocked(loadPoint).mockResolvedValue({...response(),source:'fixture'})
  render(<PointDataPanel {...props} stack={[selected()]} />)
  await settle()
  expect(screen.queryByText('17 degC')).not.toBeInTheDocument()
  expect(screen.getByTitle('Development fixture is not current point evidence.')).toBeInTheDocument()
})

it('updates relative ages from the real clock without refetching, including future and exact times', async()=>{
  vi.setSystemTime(Date.parse('2026-09-08T11:12:00Z'))
  render(<PointDataPanel {...props} stack={[selected()]} />)
  await settle();expect(screen.getByText('12 min ago')).toBeInTheDocument()
  await act(async()=>{await vi.advanceTimersByTimeAsync(60000)})
  expect(screen.getByText('13 min ago')).toBeInTheDocument()
  expect(loadPoint).toHaveBeenCalledTimes(1)
  expect(relativeValidTime('2026-09-08T14:00:00Z',instant)).toBe('in 2 h')
  expect(relativeValidTime('2026-09-08T12:00:00Z',instant)).toBe('now')
})
it('moves loading to unavailable, focuses its collapsed bottom section and recovers zero without losing context', async()=>{
  vi.mocked(loadPoint).mockResolvedValue({source:'live',snapshot:{...response().snapshot,servedFields:[]}})
  const entry=selected()
  const {rerender}=render(<PointDataPanel {...props} stack={[entry]} />)
  expect(screen.getByRole('button',{name:/Temperature/})).toBeInTheDocument()
  const reading=screen.getByRole('button',{name:'Details for point reading s · temperature 2m'})
  reading.focus()
  await settle()
  expect(screen.queryByRole('button',{name:/Temperature/})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Details for point reading s · temperature 2m'})).toHaveFocus()
  fireEvent.click(screen.getByRole('button',{name:/Point data not available/}))
  act(()=>openPointData(entry.id))
  const bottom=screen.getByRole('button',{name:'Details for point reading s · temperature 2m'})
  expect(bottom).toHaveFocus()
  fireEvent.click(bottom)
  fireEvent.keyDown(screen.getByRole('heading',{name:/Evidence ·/}),{key:'Escape'})
  await act(async()=>{await vi.advanceTimersByTimeAsync(20)})
  expect(bottom).toHaveFocus()
  const recovered=response();recovered.snapshot.servedFields[0]={...recovered.snapshot.servedFields[0],value:0,text:'0 degC'}
  vi.mocked(loadPoint).mockResolvedValue(recovered)
  rerender(<PointDataPanel {...props} instant={instant+60000} stack={[entry]} />)
  await settle()
  expect(screen.getByText('0 degC')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/Point data not available/})).not.toBeInTheDocument()
})
it('qualifies multiple fields from one source and formats percentages and explicit radar zero', async()=>{
  render(<PointDataPanel {...props} stack={[selected(),selected('s','dew_point_2m')]} />)
  await settle()
  expect(loadPoint).toHaveBeenCalledTimes(1)
  expect(screen.getByText('temperature 2m')).toBeInTheDocument()
  expect(screen.getByText('dew point 2m')).toBeInTheDocument()
  const value=response().snapshot.servedFields[0]
  expect(compactValue({...value,value:100,text:'100 percent',units:'percent'})).toBe('100%')
  expect(compactValue({...value,value:0,units:'flag',attribution:{...value.attribution,fieldKey:'radar_echo'}})).toBe('0 · no echo')
})

it('keeps GOES natural colour image-only without requesting or deriving cloud percentage', async()=>{
  const layer={id:'goes-colour',field:'satellite_natural_color',title:'GOES-East natural colour'} as import('../types').LayerItem
  render(<PointDataPanel {...props} layers={[layer]} stack={[{id:layer.id,visible:true,opacity:1}]} />)
  await settle()
  expect(loadPoint).not.toHaveBeenCalled()
  expect(screen.getByText('Image only')).toBeInTheDocument()
  expect(screen.getByText('GOES-East natural colour')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/Cloud cover/})).not.toBeInTheDocument()
})

it('renders explicit radar no echo as usable while keeping missing rates in the bottom section', async()=>{
  const fields=['precipitation_rate','snow_rate','radar_echo']
  const caps=fields.map(field=>({...cap('eccc-radar',field),levels:['surface'],variants:[{kind:'observation' as const}]}))
  const catalog=[{id:'eccc-radar',capabilities:caps,fields:fields.map(key=>({key,family:'precipitation'}))} as CatalogSource]
  const stack=caps.map(c=>{const p=pointDefault(c);return {id:pointSelectionId(p),visible:false,opacity:1,pointOnly:true,points:[p]}})
  vi.mocked(loadPoint).mockResolvedValue({source:'live',snapshot:normalizePoint({data_mode:'live',valid_time:new Date(instant).toISOString(),selection:{mode:'evidence_only',badge:'Radar'},fields:fields.map(field=>({field,key:field,value:field==='radar_echo'?0:null,provenance:{source_id:'eccc-radar',provider:'ECCC',product:'Radar',data_mode:'live',evidence_class:'retrieved',valid_time:new Date(instant).toISOString(),normalized_units:field==='radar_echo'?'flag':field==='snow_rate'?'cm h-1':'mm h-1',quality:{status:'passed',flags:[]}}}))})})
  render(<PointDataPanel {...props} catalog={catalog} stack={stack} />)
  await settle()
  expect(loadPoint).toHaveBeenCalledTimes(1)
  expect(screen.getByText('0 · no echo')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:/Point data not available \(2\)/})).toBeInTheDocument()
  expect(screen.queryByText('0 mm h-1')).not.toBeInTheDocument()
})

it('does not steal focus when the reader leaves a loading row before it becomes unavailable', async()=>{
  vi.mocked(loadPoint).mockResolvedValue({source:'live',snapshot:{...response().snapshot,servedFields:[]}})
  render(<PointDataPanel {...props} stack={[selected()]} />)
  const row=screen.getByRole('button',{name:'Details for point reading s · temperature 2m'})
  row.focus();row.blur()
  await settle()
  expect(document.body).toHaveFocus()
})
it('keeps every returned ensemble member on a separate labelled line', async()=>{
  const c={...cap('noaa-gefs'),point_product:'GEFS',variants:[{kind:'member' as const,member:'p01'},{kind:'member' as const,member:'p02'}]}
  const point=pointDefault(c)
  const result=response('noaa-gefs')
  const value=result.snapshot.servedFields[0]
  result.snapshot.servedFields=['p01','p02'].map((member,index)=>({...value,value:index,text:`${index} degC`,attribution:{...value.attribution,member}}))
  vi.mocked(loadPoint).mockResolvedValue(result)
  render(<PointDataPanel {...props} catalog={[{id:'noaa-gefs',capabilities:[c]} as CatalogSource]} stack={[{id:pointSelectionId(point),visible:false,opacity:1,pointOnly:true,points:[point]}]} />)
  await settle()
  const panel=screen.getByRole('complementary',{name:'Point data'})
  expect(panel.querySelectorAll('.point-data-line')).toHaveLength(2)
  expect(screen.getByText('Member p01')).toBeInTheDocument()
  expect(screen.getByText('Member p02')).toBeInTheDocument()
  expect(screen.getByText('0 degC')).toBeInTheDocument()
})

it('returns details focus when the reading has moved into a previously collapsed unavailable section', async()=>{
  vi.mocked(loadPoint).mockImplementation(async(_l,_t,product)=>product==='other'?{source:'unavailable',snapshot:unavailableSnapshot,error:'Source failed'}:response())
  const stack=[selected(),selected('other')]
  const {rerender}=render(<PointDataPanel {...props} stack={stack} />)
  await settle()
  fireEvent.click(screen.getByRole('button',{name:/Point data not available/}))
  fireEvent.click(screen.getByRole('button',{name:'Details for point reading s · temperature 2m'}))
  vi.mocked(loadPoint).mockResolvedValue({source:'unavailable',snapshot:unavailableSnapshot,error:'Source failed'})
  rerender(<PointDataPanel {...props} instant={instant+60000} stack={stack} />)
  await settle()
  fireEvent.keyDown(screen.getByRole('heading',{name:/Evidence ·/}),{key:'Escape'})
  await act(async()=>{await vi.advanceTimersByTimeAsync(20)})
  expect(screen.getByRole('button',{name:'Details for point reading s · temperature 2m'})).toHaveFocus()
  expect(screen.getByRole('button',{name:/Point data not available/})).toHaveAttribute('aria-expanded','true')
})

it('distinguishes source failure, quality refusal, coverage and unavailable native discovery',()=>{
  expect(concisePointReason('Response declared data_mode unavailable · Source unavailable for selected native point')).toBe('Source unavailable')
  expect(concisePointReason('weather API returned 503')).toBe('Source unavailable')
  expect(concisePointReason('Quality check failed')).toBe('Quality check failed')
  expect(concisePointReason('Outside supported area')).toBe('Outside coverage')
  expect(concisePointReason('Native time selection unavailable')).toBe('Native time unavailable')
})


it('keeps the GOES cloud-mask map out of point failures and never requests a point', async () => {
  const layer={id:'noaa-goes19-demand-cloud-mask',kind:'raster',raster_available:true,field:'cloud_mask',title:'GOES-19 observed cloud mask'} as import('../types').LayerItem
  render(<PointDataPanel {...props} layers={[layer]} stack={[{id:layer.id,visible:true,opacity:1}]} />)
  await settle()
  expect(loadPoint).not.toHaveBeenCalled()
  expect(screen.queryByText('Point unsupported')).not.toBeInTheDocument()
  expect(screen.queryByText('GOES-19 observed cloud mask')).not.toBeInTheDocument()
})

it('uses hidden loaded temperature without additional requests on styling', async()=>{
  const {TemperatureProvider}=await import('./precipitationColours')
  const pc=cap('s','precipitation_rate')
  const catalog=[{...sources[0],capabilities:[cap(),pc],fields:[...sources[0].fields!,{key:'precipitation_rate',family:'precipitation'}]}] as CatalogSource[]
  const data=response();const temperature=data.snapshot.servedFields[0]
  temperature.attribution.runTime='2026-09-08T00:00:00Z'
  const precipitation={...temperature,field:'precipitation_rate',value:10,text:'10 mm h-1',units:'mm h-1',attribution:{...temperature.attribution,fieldKey:'precipitation_rate',family:'precipitation'}}
  vi.mocked(loadPoint).mockResolvedValue({...data,snapshot:{...data.snapshot,servedFields:[temperature,precipitation]}})
  const stack=[selected(),selected('s','precipitation_rate')]
  const {rerender}=render(<TemperatureProvider><PointDataPanel {...props} catalog={catalog} stack={stack}/></TemperatureProvider>)
  await settle()
  expect(loadPoint).toHaveBeenCalledTimes(1)
  expect(screen.getByLabelText(/Temperature-based colours · 17.0°C/)).toBeInTheDocument()
  rerender(<TemperatureProvider><PointDataPanel {...props} catalog={catalog} stack={stack.map(s=>({...s,visible:true,opacity:.2}))}/></TemperatureProvider>)
  await settle()
  expect(loadPoint).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button',{name:'Details for point reading s · precipitation rate'}))
  expect(screen.getAllByText(/Same source → HRDPS/).length).toBeGreaterThan(0)
})
