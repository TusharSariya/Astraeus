import { fireEvent, render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import type { CatalogSource } from '../types'
import { discoveryEntries, matchesDiscovery, groupDiscovery, readDiscovery } from './discovery'
import { useState } from 'react'
import { MapStack } from './MapStack'
import { discoveryRows } from './discovery'
import { DiscoveryBrowser } from './DiscoveryBrowser'
import { pointSelectionId } from './pointSelections'
import type { LayerSelection } from '../types'

const source: CatalogSource = { id: 'google-weathernext-3-statistics', producer: 'Google', product: 'WeatherNext 3', state: 'catalogued', status_reason: 'Explicit local configuration required', role: 'Comparison', may_enter_consensus: false, cadence: 'hourly', forecast_horizon: 'Pinned run', geographic_coverage: 'Native point', licence: 'Internal', attribution: 'Google', fields: [{ key: 'temperature_2m', family: 'temperature', storage: 'available-not-stored', upstream: 'temperature_2m_mean', note: 'Constructed declaration' }],
  discovery: { subjects: ['Temperature'], kinds: ['Forecast'], methods: ['Machine learning'], ensemble_forms: ['Provider statistics'], map_capabilities: [] },
  capabilities: ['WeatherNext 3 local', 'WeatherNext 3 historical'].map(point_product => ({ source_id: 'google-weathernext-3-statistics', product_id: 'wn3', field: 'temperature_2m', variants: [{ kind: 'provider_statistic', statistic: 'ensemble_mean' }], levels: ['2 m'], point: true, point_product, native_series: false, directional_time_selection: false, run_selection: 'not_applicable', time_semantics: 'Exact time only', coverage_description: 'One native cell' })) }
const goes: CatalogSource = { ...source, id: 'goes', producer: 'NOAA', product: 'GOES', capabilities: [], fields: [], discovery: { subjects: ['Clouds', 'Satellite imagery'], kinds: ['Observation'], methods: ['Remote sensing'], ensemble_forms: ['Not applicable'], map_capabilities: [{ layer_id: 'goes-image', title: 'GOES natural colour', product: null, subjects: ['Clouds','Satellite imagery'] }] } }
it('cycles shared map rows through all three states and point-only fields through two', async () => {
  function SelectedHarness() {
    const [stack,setStack]=useState<LayerSelection[]>([])
    return <><output aria-label="Selections">{JSON.stringify(stack)}</output><MapStack catalog={[source,goes]} layers={[]} stack={stack} onChange={setStack} drawn={[]} onInspect={vi.fn()} /></>
  }
  render(<SelectedHarness />)
  const user=userEvent.setup()
  await user.click(screen.getByRole('button',{name:'Browse'}))
  const rows=()=>screen.getAllByRole('button',{name:'GOES natural colour'})
  await user.click(rows()[0])
  for(const row of rows())expect(row).toHaveAttribute('aria-description','Map + data. Activate to cycle selection.')
  await user.click(rows()[1])
  for(const row of rows())expect(row).toHaveAttribute('aria-description','Data only. Activate to cycle selection.')
  rows()[0].focus();await user.keyboard(' ')
  for(const row of rows())expect(row).toHaveAttribute('aria-description','Off. Activate to cycle selection.')
  const point=screen.getByRole('button',{name:'WeatherNext 3 local · temperature 2m'})
  await user.click(point)
  const selected=JSON.parse(screen.getByLabelText('Selections').textContent!)[0]
  expect(selected.visible).toBe(false);expect(selected.pointOnly).toBe(true)
  expect(selected.id).toBe(pointSelectionId(selected.points[0]))
  expect(point).toHaveAttribute('aria-description','Data only. Activate to cycle selection.')
  await user.click(point);expect(screen.getByLabelText('Selections')).toHaveTextContent('[]')
})
it('searches the individual point field instead of every field published by its source', () => {
  const withDew={...source,capabilities:[...source.capabilities!,{...source.capabilities![0],field:'dew_point_2m'}]}
  const rows=discoveryRows([withDew],[]).filter(row=>matchesDiscovery(row,'dew point',{}))
  expect(rows).toHaveLength(1)
  expect(rows[0].point?.field).toBe('dew_point_2m')
})
it('discovers point-only WeatherNext and invokes the explicit path without adding imagery', async () => {
  const point = vi.fn(), add = vi.fn(), series = vi.fn(), user = userEvent.setup()
  render(<MapStack catalog={[source]} layers={[]} stack={[]} onChange={add} drawn={[]} onInspect={vi.fn()} onPoint={point} onSeries={series} />)
  await user.click(screen.getByRole('button', { name: 'Browse' }))
  await user.type(screen.getByPlaceholderText('Name, provider, model or field'), 'weathernext 3')
  await user.click(screen.getByRole('button', {name: 'Details for WeatherNext 3 local · temperature 2m'}))
  await user.click(screen.getByRole('button', { name: 'Open point · WeatherNext 3 local' }))
  expect(point).toHaveBeenCalledWith('WeatherNext 3 local', expect.any(HTMLButtonElement))
  expect(screen.queryByRole('button', { name: /Add / })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Open series/ })).not.toBeInTheDocument()
  expect(add).not.toHaveBeenCalled(); expect(series).not.toHaveBeenCalled()
})
it('uses OR within facets, AND across facets and deduplicates repeated subjects', () => {
  const entries = discoveryEntries([source, goes], [])
  const cloud = entries.find(e => e.id === 'goes')!
  expect(groupDiscovery([cloud], 'Subject')).toHaveLength(2)
  expect(matchesDiscovery(cloud,'', { Subject: ['Clouds','Temperature'], Provider: ['NOAA'] })).toBe(true)
  expect(matchesDiscovery(cloud,'', { Subject: ['Clouds'], Provider: ['Google'] })).toBe(false)
  expect(matchesDiscovery(entries.find(e => e.id === source.id)!, 'machine learning temperature', {})).toBe(true)
  expect(matchesDiscovery(entries.find(e => e.id === source.id)!, 'weathernext3', {})).toBe(true)
})
it('shows unavailable sources and preserves their reasons through filtering', async () => {
  const user = userEvent.setup(), info = { ...source, id:'future', product:'Future sensor', capabilities: [], discovery: undefined }
  render(<DiscoveryBrowser catalog={[info,source]} layers={[]} onToggle={vi.fn()} onDetails={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Future sensor' })).toHaveTextContent('catalogued')
  await user.click(screen.getByText('Filters', { exact: true }))
  const facets = screen.getByRole('group',{name:'Interface'})
  await user.click(within(facets).getByRole('checkbox',{name:'Information only'}))
  expect(screen.getByRole('status')).toHaveTextContent('1 unique entries')
  await user.click(screen.getByRole('button',{name:'Clear'}))
  expect(screen.getByRole('status')).toHaveTextContent('3 unique entries')
})
it('repeated map appearances share Added state and malformed metadata is discarded', async () => {
  const user=userEvent.setup(), add=vi.fn()
  render(<DiscoveryBrowser catalog={[goes]} layers={[]} stack={[{id:'goes-image',opacity:.5,visible:false}]} onToggle={add} onDetails={vi.fn()} />)
  expect(screen.getAllByRole('button',{name:'GOES natural colour'})).toHaveLength(2)
  for (const button of screen.getAllByRole('button',{name:'GOES natural colour'})) expect(button).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('status')).toHaveTextContent('1 unique entries')
  expect(readDiscovery({subjects:'not an array'})).toBeUndefined()
  expect(readDiscovery(goes.discovery)).toEqual(goes.discovery)
})

it('flattens subjects per layer while retaining source facets and point-only entries', () => {
  const mixed = {...goes, discovery: {...goes.discovery!, map_capabilities: [...goes.discovery!.map_capabilities, {layer_id: 'snow', title: 'Snow / fog', product: null, subjects: ['Snow/ice', 'Visibility/fog']}]}}
  const rows = discoveryRows([source, mixed], [])
  expect(rows).toHaveLength(4)
  expect(rows.filter(row => matchesDiscovery(row, '', {Subject: ['Clouds']})).map(row => row.layerId)).toEqual(['goes-image'])
  expect(rows.filter(row => matchesDiscovery(row, '', {Provider: ['NOAA']}))).toHaveLength(2)
  expect(rows.find(row => row.point?.sourceId === source.id)?.layerId).toBeUndefined()
})
it('toggles exact membership across groups and all details gestures preserve membership', async () => {
  const user = userEvent.setup(), details = vi.fn()
  function Harness() {
    const [stack, setStack] = useState([{id: 'goes-image', opacity: .35, visible: false}])
    return <DiscoveryBrowser catalog={[goes]} layers={[]} stack={stack} onDetails={details} onToggle={id => setStack(stack.some(s => s.id === id) ? [] : [{id, opacity: .85, visible: true}])} />
  }
  render(<Harness />)
  const rows = () => screen.getAllByRole('button', {name: 'GOES natural colour'})
  fireEvent.contextMenu(rows()[0]); expect(details).toHaveBeenCalledTimes(1)
  fireEvent.keyDown(rows()[0], {key: 'F10', shiftKey: true})
  fireEvent.keyDown(rows()[0], {key: 'ContextMenu'})
  await user.click(screen.getAllByRole('button', {name: 'Details for GOES natural colour'})[0])
  expect(details).toHaveBeenCalledTimes(4)
  for (const row of rows()) expect(row).toHaveAttribute('aria-pressed', 'true')
  await user.click(rows()[1])
  for (const row of rows()) expect(row).toHaveAttribute('aria-pressed', 'false')
  rows()[0].focus(); await user.keyboard(' ')
  for (const row of rows()) expect(row).toHaveAttribute('aria-pressed', 'true')
  await user.keyboard('{Enter}')
  for (const row of rows()) expect(row).toHaveAttribute('aria-pressed', 'false')
})

it('information-only primary actions open their full unavailable reason without selection', async () => {
  const user = userEvent.setup(), change = vi.fn()
  render(<MapStack catalog={[{...source, product:'Future sensor', capabilities:[], discovery:undefined}]} layers={[]} stack={[]} drawn={[]} onChange={change} onInspect={vi.fn()} />)
  await user.click(screen.getByRole('button', {name:'Browse'}))
  await user.click(screen.getByRole('button', {name:'Future sensor'}))
  expect(screen.getByText(source.status_reason)).toBeInTheDocument()
  expect(change).not.toHaveBeenCalled()
})

it('details return to Browse search if a catalogue refresh removes the originating source', async () => {
  const props = {layers:[], stack:[], drawn:[], onChange:vi.fn(), onInspect:vi.fn()}
  const {rerender} = render(<MapStack {...props} catalog={[source]} />)
  await userEvent.click(screen.getByRole('button', {name:'Browse'}))
  await userEvent.click(screen.getByRole('button', {name:'Details for WeatherNext 3 local · temperature 2m'}))
  rerender(<MapStack {...props} catalog={[]} catalogError="HTTP 503" />)
  await userEvent.keyboard('{Escape}')
  await waitFor(() => expect(screen.getByPlaceholderText('Name, provider, model or field')).toHaveFocus())
})

it('hides both WeatherNext 2 sources while retaining WeatherNext 3 discovery', () => {
  const old = ['google-weathernext-2', 'open-meteo-weathernext-2'].map(id => ({...source,id,product:'WeatherNext 2',capabilities:[]}))
  expect(discoveryEntries([...old,source],[]).map(entry => entry.id)).toEqual([source.id])
  expect(discoveryRows([...old,source],[]).every(row => row.source?.id === source.id)).toBe(true)
})


it('labels demand imagery as a map and shows current draw state instead of unknown', () => {
  const layer={id:'noaa-goes19-demand-cloud-mask',title:'GOES-19 observed cloud mask',kind:'raster',raster_available:true,evidence_basis:'demand_query',field:'cloud_mask'} as import('../types').LayerItem
  const props={catalog:[],layers:[layer],stack:[{id:layer.id,visible:true,opacity:1}],onToggle:vi.fn(),onDetails:vi.fn()}
  const {rerender}=render(<DiscoveryBrowser {...props} />)
  const button=screen.getByRole('button',{name:layer.title})
  expect(button).toHaveAccessibleDescription('Map on demand')
  expect(button).toHaveAttribute('aria-description','Map. Activate to cycle selection.')
  rerender(<DiscoveryBrowser {...props} drawn={[{id:layer.id,drawn:false,status:'loading',description:'Loading selected scan',times:[]}]} />)
  expect(button).toHaveAccessibleDescription('Loading frame')
  rerender(<DiscoveryBrowser {...props} drawn={[{id:layer.id,drawn:true,description:'Selected scan',times:[]}]} />)
  expect(button).toHaveAccessibleDescription('Drawn')
})
