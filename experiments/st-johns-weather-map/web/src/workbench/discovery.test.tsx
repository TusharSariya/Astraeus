import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import type { CatalogSource } from '../types'
import { discoveryEntries, matchesDiscovery, groupDiscovery, readDiscovery } from './discovery'
import { DiscoveryBrowser } from './DiscoveryBrowser'

const source: CatalogSource = { id: 'google-weathernext-3-statistics', producer: 'Google', product: 'WeatherNext 3', state: 'catalogued', status_reason: 'Explicit local configuration required', role: 'Comparison', may_enter_consensus: false, cadence: 'hourly', forecast_horizon: 'Pinned run', geographic_coverage: 'Native point', licence: 'Internal', attribution: 'Google', fields: [{ key: 'temperature_2m', family: 'temperature', storage: 'available-not-stored', upstream: 'temperature_2m_mean', note: 'Constructed declaration' }],
  discovery: { subjects: ['Temperature'], kinds: ['Forecast'], methods: ['Machine learning'], ensemble_forms: ['Provider statistics'], map_capabilities: [] },
  capabilities: ['WeatherNext 3 local', 'WeatherNext 3 historical'].map(point_product => ({ source_id: 'google-weathernext-3-statistics', product_id: 'wn3', field: 'temperature_2m', variants: [{ kind: 'provider_statistic', statistic: 'ensemble_mean' }], levels: ['2 m'], point: true, point_product, native_series: false, run_selection: 'not_applicable', time_semantics: 'Exact time only', coverage_description: 'One native cell' })) }
const goes: CatalogSource = { ...source, id: 'goes', producer: 'NOAA', product: 'GOES', capabilities: [], fields: [], discovery: { subjects: ['Clouds', 'Satellite imagery'], kinds: ['Observation'], methods: ['Remote sensing'], ensemble_forms: ['Not applicable'], map_capabilities: [{ layer_id: 'goes-image', title: 'GOES natural colour', product: null, subjects: ['Clouds','Satellite imagery'] }] } }
it('discovers point-only WeatherNext and invokes the explicit path without adding imagery', async () => {
  const point = vi.fn(), add = vi.fn(), series = vi.fn(), user = userEvent.setup()
  render(<DiscoveryBrowser catalog={[source]} layers={[]} onPoint={point} onAdd={add} onSeries={series} />)
  await user.type(screen.getByRole('searchbox'), 'weathernext 3')
  await user.click(screen.getByText('Capabilities · 2'))
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
  render(<DiscoveryBrowser catalog={[info,source]} layers={[]} />)
  expect(screen.getByText(info.status_reason)).toBeInTheDocument()
  await user.click(screen.getByText('Filters', { exact: true }))
  const facets = screen.getByRole('group',{name:'Interface'})
  await user.click(within(facets).getByRole('checkbox',{name:'Information only'}))
  expect(screen.getByRole('status')).toHaveTextContent('1 unique entries')
  await user.click(screen.getByRole('button',{name:'Clear filters'}))
  expect(screen.getByRole('status')).toHaveTextContent('2 unique entries')
})
it('repeated map appearances share Added state and malformed metadata is discarded', async () => {
  const user=userEvent.setup(), add=vi.fn()
  render(<DiscoveryBrowser catalog={[goes]} layers={[]} stack={[{id:'goes-image',opacity:.5,visible:false}]} onAdd={add} />)
  for (const summary of screen.getAllByText('Capabilities · 1')) await user.click(summary)
  expect(screen.getAllByRole('button',{name:'Add GOES natural colour'})).toHaveLength(2)
  for (const button of screen.getAllByRole('button',{name:'Add GOES natural colour'})) expect(button).toBeDisabled()
  expect(screen.getByRole('status')).toHaveTextContent('1 unique entries')
  expect(readDiscovery({subjects:'not an array'})).toBeUndefined()
  expect(readDiscovery(goes.discovery)).toEqual(goes.discovery)
})
