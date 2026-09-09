import { StrictMode, useState } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { appendComparison, linePath, useForecastComparison, validatePage, type ComparisonPage } from './ForecastComparison'

const start=Date.parse('2026-09-09T12:00:00Z')
const location={id:'point',name:'Point',latitude:47.5,longitude:-52.7,kind:'map' as const}
let calls: {body:Record<string,unknown>;signal:AbortSignal}[]
let first:ComparisonPage
function Harness({enabled=true,lat=47.5,moving=false}:{enabled?:boolean;lat?:number;moving?:boolean}) {
  const [instant,setInstant]=useState(start)
  const view=useForecastComparison({location:{...location,latitude:lat},instant,enabled,selectionMoving:moving,onInstant:setInstant})
  return <><output data-testid="map-time">{instant}</output><button onClick={()=>setInstant(start+3600000)}>Bottom timeline test step</button>{enabled?view:null}</>
}
function page(body:Record<string,unknown>):ComparisonPage {
  return {id:'fixed',selection:body,selected_at:new Date(start).toISOString(),expires_at:new Date(start+900000).toISOString(),complete:true,next_cursor:null,completed_positions:2,total_positions:2,
    coverage:[],curves:[{id:'eccc-hrdps:temperature_2m',source_id:'eccc-hrdps',product_id:'hrdps',group:'temperature',field:'temperature_2m',definition:'temperature',units:'degC',samples:[0,3600000].map((offset,i)=>({time:new Date(start+offset).toISOString(),run_id:'native',evidence:{key:'temperature_2m',field:'temperature_2m',value:i,provenance:{source_id:'eccc-hrdps',valid_time:new Date(start+offset).toISOString(),run_time:new Date(start).toISOString(),normalized_units:'degC'}}}))}]} as unknown as ComparisonPage
}
beforeEach(()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(start);calls=[]
  vi.stubGlobal('fetch',vi.fn(async (_url,init)=>{
    if(String(_url).includes('/ifs/runs/'))return new Response('[]')
    if(String(_url).endsWith('/ifs/catalogue'))return new Response(JSON.stringify({fields:[]}))
    if(init.method==='DELETE')return new Response(null,{status:204})
    const body=JSON.parse(init.body);calls.push({body,signal:init.signal});first=page(body)
    return new Response(JSON.stringify(first))
  }))
})
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals()})

it('defaults to five models and five groups; map clicks, shared cursor, visibility and view switches preserve the window',async()=>{
  const view=render(<Harness/>);await waitFor(()=>expect(calls).toHaveLength(1))
  await screen.findByText(/HRDPS/, {selector:'.comparison-values b'})
  expect(calls[0].body.sources).toHaveLength(5);expect(calls[0].body.variables).toHaveLength(5)
  expect(Date.parse(String(calls[0].body.end))-Date.parse(String(calls[0].body.start))).toBe(86400000)
  expect(screen.getByText('Cloud cover · opacity-weighted')).toBeInTheDocument()
  expect(screen.getByText('Cloud cover · geometric')).toBeInTheDocument()
  expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Use cursor as map time'})).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button',{name:'Bottom timeline test step'}))
  const cursor=screen.getByRole('img',{name:/Temperature/}).querySelector('.comparison-shared-cursor')
  expect(cursor?.getAttribute('d')).toContain('M101.33333333333333')
  expect(screen.getByTestId('map-time')).toHaveTextContent(String(start+3600000))
  await userEvent.click(screen.getByRole('button',{name:'HRDPS'}))
  expect(screen.getByRole('button',{name:'HRDPS (hidden)'})).toHaveAttribute('aria-pressed','false')
  view.rerender(<Harness enabled={false}/>);view.rerender(<Harness/>)
  expect(calls).toHaveLength(1)
  expect(screen.getByLabelText('Start (UTC)')).toHaveValue('2026-09-09T12:00')
})

it('loads pages progressively without a new selection and merges only matching snapshots',async()=>{
  let finish:((r:Response)=>void)|undefined
  vi.stubGlobal('fetch',vi.fn(async (_url,init)=>{
    const body=JSON.parse(init.body);calls.push({body,signal:init.signal})
    if(body.cursor)return new Promise<Response>(resolve=>{finish=resolve})
    first=page(body);return new Response(JSON.stringify({...first,complete:false,next_cursor:'next',completed_positions:1}))
  }))
  render(<Harness/>);await waitFor(()=>expect(calls).toHaveLength(2))
  expect(screen.getByText(/Loading · 1/)).toBeInTheDocument()
  expect(calls[1].body).toEqual({cursor:'next'})
  await act(async()=>finish!(new Response(JSON.stringify(first))))
  await waitFor(()=>expect(screen.queryByText(/Loading ·/)).not.toBeInTheDocument())
  expect(()=>appendComparison(first,{...first,id:'changed'})).toThrow('continuation changed')
})

it('expires retained charts without reacquiring and requires Refresh',async()=>{
  vi.useRealTimers();vi.useFakeTimers({toFake:['Date','setTimeout','clearTimeout']});vi.setSystemTime(start)
  render(<Harness/>);await vi.waitFor(()=>expect(screen.getByText(/HRDPS/, {selector:'.comparison-values b'})).toBeInTheDocument())
  await act(async()=>{await vi.advanceTimersByTimeAsync(900000)})
  expect(screen.getByText(/Expired comparison/)).toBeInTheDocument()
  expect(screen.getAllByRole('img')).toHaveLength(6)
  expect(calls).toHaveLength(1)
  fireEvent.click(screen.getByRole('button',{name:'Refresh'}))
  await act(async()=>{await vi.advanceTimersByTimeAsync(0)})
  expect(calls).toHaveLength(2)
})

it('cancels changed selections, rejects obsolete pages, and survives StrictMode',async()=>{
  const view=render(<StrictMode><Harness/></StrictMode>)
  await waitFor(()=>expect(screen.getByText(/HRDPS/, {selector:'.comparison-values b'})).toBeInTheDocument())
  const last=calls.at(-1)!
  view.rerender(<StrictMode><Harness lat={47.6}/></StrictMode>)
  await waitFor(()=>expect(calls.at(-1)!.body.latitude).toBe(47.6))
  expect(last.signal.aborted).toBe(true)
  expect(()=>validatePage(first,{...first.selection,latitude:40})).toThrow('selection changed')
})

it('breaks lines at missing values and run boundaries, preserving sparse times',()=>{
  const p=page({}),samples=p.curves[0].samples!
  const path=linePath([samples[0],{...samples[1],evidence:null},{...samples[1],run_id:'other'}],t=>t,v=>v)
  expect(path.match(/M/g)).toHaveLength(2);expect(path).not.toContain('L')
})

it('offers an explicit available-window action without shifting an empty request',async()=>{
  vi.stubGlobal('fetch',vi.fn(async (_url,init)=>{
    if(String(_url).includes('/ifs/runs/'))return new Response('[]')
    if(String(_url).endsWith('/ifs/catalogue'))return new Response(JSON.stringify({fields:[]}))
    if(init.method==='DELETE')return new Response(null,{status:204})
    const body=JSON.parse(init.body);calls.push({body,signal:init.signal})
    first=page(body);first.curves=first.curves.map(c=>({...c,samples:[]}))
    first.coverage=[{source_id:'eccc-hrdps',state:'empty',available_start:'2026-09-08T12:00:00Z',available_end:'2026-09-09T12:00:00Z'}]
    return new Response(JSON.stringify(first))
  }))
  render(<Harness/>);await screen.findByRole('button',{name:'Show available window'})
  expect(calls).toHaveLength(1)
  expect(screen.getByLabelText('Start (UTC)')).toHaveValue('2026-09-09T12:00')
  await userEvent.click(screen.getByRole('button',{name:'Show available window'}))
  await waitFor(()=>expect(calls).toHaveLength(2))
  expect(calls[1].body.start).toBe('2026-09-08T12:00:00.000Z')
})

it('plots interval amounts from a true zero baseline and clips pre-window intervals',async()=>{
  vi.stubGlobal('fetch',vi.fn(async (_url,init)=>{
    const body=JSON.parse(init.body);first=page(body)
    const prototype=first.curves[0].samples![0]
    first.curves=[{...first.curves[0],group:'precipitation',field:'precipitation_amount',units:'mm',samples:[0,1,2].map((h)=>{
      const time=new Date(start+h*3600000).toISOString()
      return {...prototype,time,interval_start:new Date(start+(h-1)*3600000).toISOString(),interval_end:time,
        evidence:{...prototype.evidence!,key:'precipitation_amount',value:h===2?2:0,provenance:{...prototype.evidence!.provenance,valid_time:time}}}
    })}]
    return new Response(JSON.stringify(first))
  }))
  render(<Harness/>);await waitFor(()=>expect(screen.getByRole('img',{name:/Precipitation/}).querySelectorAll('rect')).toHaveLength(2))
  const bars=screen.getByRole('img',{name:/Precipitation/}).querySelectorAll('rect')
  expect(Number(bars[0].getAttribute('height'))).toBe(0)
  expect(Number(bars[1].getAttribute('height'))).toBeGreaterThan(0)
})

it('accepts API property order while rejecting actual source, run and product changes', async()=>{
  vi.stubGlobal('fetch',vi.fn(async (_url,init)=>{
    const body=JSON.parse(init.body);calls.push({body,signal:init.signal})
    first=page(body)
    first.selection.sources=first.selection.sources!.map(s=>({variant:s.variant,level:s.level,source_id:s.source_id,product_id:s.product_id,run:s.run}))
    return new Response(JSON.stringify(first))
  }))
  const view=render(<Harness/>)
  const chart=await screen.findByRole('img',{name:/Temperature/})
  await waitFor(()=>expect(chart.querySelectorAll('circle')).toHaveLength(2))
  expect(chart.querySelector('path[stroke-width="2"]')?.getAttribute('d')).toContain('L')
  for (const changed of [{source_id:'noaa-gfs'},{run:'previous'},{product_id:'wrong'}]) {
    const invalid={...first,selection:{...first.selection,sources:first.selection.sources!.map((s,i)=>i===0?{...s,...changed}:s)}}
    expect(()=>validatePage(invalid,first.selection)).toThrow('selection changed')
  }
  view.rerender(<Harness moving/>)
  expect(chart.querySelectorAll('circle')).toHaveLength(2)
  expect(calls).toHaveLength(1)
})

it('switches acquired IFS members without starting another selection',async()=>{
  vi.stubGlobal('fetch',vi.fn(async (url,init)=>{
    if(String(url).includes('/ifs/'))return new Response(JSON.stringify(String(url).endsWith('/catalogue')?{fields:[]}:[]))
    if(init.method==='DELETE')return new Response(null,{status:204})
    const body=JSON.parse(init.body);calls.push({body,signal:init.signal});const result=page(body)
    result.curves=[{...result.curves[0],id:'ifs-temperature',source_id:'ecmwf-ifs',samples:result.curves[0].samples!.map(s=>({...s,member_values:{'0':280,'1':290},member_units:'K',evidence:{...s.evidence!,provenance:{...s.evidence!.provenance,source_id:'ecmwf-ifs'}}}))}]
    return new Response(JSON.stringify(result))
  }))
  render(<Harness/>);const selector=await screen.findByLabelText('IFS displayed member')
  await userEvent.selectOptions(selector,'1')
  expect(screen.getByText(/IFS member 1/, {selector:'.comparison-values b'})).toBeInTheDocument()
  expect(calls).toHaveLength(1)
})
