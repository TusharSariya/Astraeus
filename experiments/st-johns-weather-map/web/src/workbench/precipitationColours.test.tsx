import {describe,it,expect,vi} from 'vitest'
import {render,screen} from '@testing-library/react'
import {temperatureFor,precipitationColour,precipitationScale,PrecipitationLegend,featurePrecipitation,gridTemperature,type TemperatureSample} from './precipitationColours'
import type {IFSGrid} from './IFSLayers'
const sample:TemperatureSample={latitude:47,longitude:-53,source:'eccc-rdps',product:'RDPS',run:'2026-09-09T00:00:00Z',time:'2026-09-09T03:00:00Z',variant:'[null,null]',celsius:1}
const fallback={...sample,source:'eccc-hrdps',product:'HRDPS',celsius:-1}
const rate=precipitationScale('precipitation_rate','mm h-1')!
describe('GOV-SPEC-001/004/006 temperature display matching',()=>{
 it('prefers same source and selected run, then HRDPS',()=>{
  expect(temperatureFor(sample,[fallback,sample])).toEqual(sample)
  expect(temperatureFor(sample,[{...sample,run:'old'},fallback])).toEqual(fallback)
  expect(temperatureFor(sample,[])).toBeNull()
  expect(temperatureFor(fallback,[{...fallback,run:'old'}])).toBeNull()
 })
 it.each([{time:'2026-09-09T04:00:00Z'},{run:null},{product:'different'},{variant:'member 1'},{latitude:48},{longitude:-54},{expires:0},{expires:NaN},{celsius:NaN}])('rejects incompatible or expired temperature %j',patch=>{
  expect(temperatureFor(sample,[{...sample,...patch}])).toBeNull()
 })
 it('rejects stale or pinned-run mismatched HRDPS fallback',()=>{
  expect(temperatureFor(sample,[{...fallback,expires:0}])).toBeNull()
  expect(temperatureFor(sample,[fallback],'2026-09-08T12:00:00Z')).toBeNull()
 })
 it('has exact boundary, value-dependent palettes, neutral missing and transparent zero',()=>{
  expect(precipitationColour(10,0,rate)).toEqual(precipitationColour(10,-1,rate))
  expect(precipitationColour(10,.001,rate)).toEqual([250,220,50,255])
  expect(precipitationColour(20,1,rate)).toEqual([220,35,35,255])
  expect(precipitationColour(20,0,rate)).toEqual([8,48,130,255])
  expect(precipitationColour(1,0,rate)).not.toEqual(precipitationColour(20,0,rate))
  expect(precipitationColour(10,null,rate)).toEqual(precipitationColour(10,1,rate))
  expect(precipitationColour(null,0,rate)).not.toEqual(precipitationColour(0,0,rate))
  expect(precipitationColour(0,0,rate)[3]).toBe(0)
 })
 it('keeps native units and distinct scales',()=>{
  expect(rate).toEqual({label:'Precipitation rate',units:'mm h-1',max:20})
  expect(precipitationScale('snow_rate','cm h-1')).toEqual({label:'Snowfall depth rate',units:'cm h-1',max:2})
  expect(precipitationScale('tp:sfc','m')).toEqual({label:'Interval precipitation amount',units:'m',max:.05})
  expect(precipitationScale('precipitation_type','code')).toBeNull()
  expect(precipitationScale('precipitation_rate','dBZ')).toBeNull()
 })
 it('styles numeric features without mutation, requests or echo intensity inference',()=>{
  const feature={type:'Feature' as const,geometry:{type:'Point' as const,coordinates:[-53,47]},properties:{source_id:sample.source,product:sample.product,run_time:sample.run,valid_time:sample.time,precipitation_rate:10,precipitation_rate_units:'mm h-1'}}
  const original=JSON.stringify(feature),fetch=vi.spyOn(globalThis,'fetch')
  const reading=featurePrecipitation(feature,[sample])!
  expect(reading.temperature).toEqual(sample)
  for(const opacity of [0,.5,1])precipitationColour(reading.value,reading.temperature?.celsius??null,reading.scale,opacity)
  expect(fetch).not.toHaveBeenCalled();fetch.mockRestore()
  expect(JSON.stringify(feature)).toBe(original)
  expect(featurePrecipitation({...feature,properties:{radar_echo:0}},[sample])).toBeNull()
 })
 it('labels cutoff and unavailable fallback',()=>{
  render(<PrecipitationLegend scale={rate}/>)
  expect(screen.getByText('Temperature-based colours')).toBeVisible()
  expect(screen.getByText(/Temperature unavailable:/)).toHaveTextContent('mm h-1')
  expect(screen.getByText('At or below 0°C')).toBeVisible()
 })
 it('uses exact native grid centres, run, product, time and variant',()=>{
  const grid={field:'tp:sfc',level:0,run_id:'run',run_time:sample.run,selection_product:'atmosphere-control',native_time:sample.time,member:'0',statistic:null,expires_at:'2099-01-01T00:00:00Z',latitudes:[47,48],longitudes:[-53,-52],values:[[.01,null],[0,.05]],units:'m'} as IFSGrid
  const t={...grid,field:'2t:sfc',units:'K',values:[[273.15,null],[274.15,272.15]]}
  expect(gridTemperature(grid,0,[t])?.celsius).toBe(0)
  expect(gridTemperature(grid,1,[t])).toBeNull()
  for(const patch of [{run_id:'old'},{native_time:'old'},{member:'1'},{selection_product:'other'},{expires_at:'2000-01-01T00:00:00Z'},{latitudes:[47.1,48.1]}])expect(gridTemperature(grid,0,[{...t,...patch}])).toBeNull()
 })
})

it('honours explicit temperature choices without silently falling back',()=>{
 expect(temperatureFor(sample,[sample,fallback],undefined,Date.now(),'eccc-hrdps')).toEqual(fallback)
 expect(temperatureFor(sample,[fallback],undefined,Date.now(),'same-source')).toBeNull()
 expect(temperatureFor(sample,[sample,fallback],undefined,Date.now(),'noaa-gfs')).toBeNull()
 expect(temperatureFor(sample,[{...fallback,source:'noaa-gfs'}],undefined,Date.now(),'noaa-gfs')?.source).toBe('noaa-gfs')
})
