import { expect, it } from 'vitest'
import type { CatalogSource, LayerItem, LayerSelection, SourceCapability } from '../types'
import { capabilityFor, cycleSelection, layerPoints, parseSelection, pointDefault, pointSelectionId, pointUnavailable, selectionState } from './pointSelections'
import { parseFocusUrl, serializeFocusUrl } from './focusUrl'
import { stations } from '../fixtures'

const cap: SourceCapability = {source_id:'s',product_id:'p',point_product:'Point product',field:'temperature_2m',variants:[{kind:'deterministic'}],levels:['2 m'],point:true,native_series:false,directional_time_selection:false,run_selection:'latest',time_semantics:'Exact',coverage_description:'Declared'}
const source = {id:'s',capabilities:[cap]} as CatalogSource
const layer = {id:'map',mapping_status:'known',field_mappings:[{source_id:'s',field_key:'temperature_2m',declared_field:'temperature'}]} as LayerItem
it('cycles three states and retains order and opacity while data-only', () => {
  let stack:LayerSelection[]=[{id:'base',opacity:.3,visible:true}]
  stack=cycleSelection(stack,'map');expect(selectionState(stack[1])).toBe('Map + data')
  stack[1].opacity=.45;stack=cycleSelection(stack,'map')
  expect(stack).toEqual([{id:'base',opacity:.3,visible:true},{id:'map',opacity:.45,visible:false}])
  expect(selectionState(stack[1])).toBe('Data only')
  stack=cycleSelection(stack,'map');expect(stack).toHaveLength(1)
})
it('point-only entries never select map imagery and round-trip with legacy selections', () => {
  const point=pointDefault(cap),id=pointSelectionId(point)
  const stack=cycleSelection([{id:'legacy',opacity:.2,visible:false}],id,point)
  expect(stack[1].visible).toBe(false);expect(stack[1].pointOnly).toBe(true)
  const state={location:stations[0],site:null,instant:0,view:'Map' as const,dock:null,stack,runs:{}}
  expect(parseFocusUrl(serializeFocusUrl(state),stations[0]).stack).toEqual(stack)
  expect(cycleSelection(stack,id,point)).toHaveLength(1)
  expect(()=>parseSelection({...stack[1],visible:true})).toThrow()
})
it('joins explicit field capabilities only and does not choose between delivery products', () => {
  expect(layerPoints(layer,[source])).toEqual([pointDefault(cap)])
  expect(layerPoints({...layer,field_mappings:undefined},[source])).toEqual([])
  expect(layerPoints(layer,[{...source,capabilities:[cap,{...cap,point_product:'Other point product'}]}])).toEqual([])
})
it('merges declared variant choices and requires ambiguous selections instead of guessing', () => {
  const catalog=[{...source,capabilities:[{...cap,variants:[{kind:'provider_statistic' as const,statistic:'ensemble_mean'}]},{...cap,variants:[{kind:'provider_statistic' as const,statistic:'ensemble_spread'}]}]}]
  const merged=capabilityFor(pointDefault(cap),catalog)!
  expect(merged.variants).toHaveLength(2)
  expect(pointUnavailable(pointDefault(merged),catalog)).toMatch(/Choose.*member or statistic/)
  expect(pointUnavailable({...pointDefault(merged),variant:merged.variants[1]},catalog)).toBeNull()
  expect(pointUnavailable(pointDefault(cap),[],{})).toMatch(/retained/)
  expect(pointUnavailable(pointDefault(cap),[source],{s:'old-run'})).toMatch(/named run/)
})


it('toggles map-only imagery directly off without retaining a data-only selection', () => {
  const stack=cycleSelection([], 'mask', undefined, [], false, true)
  expect(selectionState(stack[0],true)).toBe('Map')
  expect(cycleSelection(stack,'mask',undefined,[],false,true)).toEqual([])
})

it('retains a passive temperature source through stack parsing',()=>{
 const entry={id:'radar',visible:true,opacity:.6,temperatureSource:'eccc-hrdps'}
 expect(parseSelection(entry)).toEqual(entry)
 expect(()=>parseSelection({...entry,temperatureSource:42})).toThrow()
})
