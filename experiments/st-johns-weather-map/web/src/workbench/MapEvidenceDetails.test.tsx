import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { MapSamplesLink, MapEvidenceDetails, openMapFeature, mapLayerEvidence, featureEvidenceKey } from './MapEvidenceDetails'
import type { DrawEvidence } from './MapStack'
import type { LayerItem } from '../types'
const at = '2026-09-07T12:00:00Z'
const layer: LayerItem = { id: 'station-layer', title: 'Station reports', kind: 'points', field: 'observations', product: 'SWOB', units: 'mixed', semantics: 'Fixture', evidence_class: 'retrieved', mapping_status: 'partial', field_mappings: [{ source_id: 'eccc-swob', field_key: null, declared_field: 'observations' }] }
const draw: DrawEvidence = { id: layer.id, drawn: true, description: 'One native station report', times: [at], evidenceClass: 'retrieved', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-52.7, 47.5] }, properties: { station_id: 'FIXTURE', temperature: 0, visibility: null, units: { temperature: 'degC' }, quality: 'unknown' } }] }

it('uses one visible keyboard action for canvas feature and semantic report inspection', async () => {
  const inspect = vi.fn(), select = vi.fn()
  render(<MapEvidenceDetails layers={[layer]} drawn={[draw]} location={{ id: 'point', name: 'Point', kind: 'map', latitude: 47.51, longitude: -52.69 }} instant={Date.parse(at)} statuses={[]} responseSourceIds={new Set()} onSelect={select} onInspect={inspect} />)
  openMapFeature(layer.id, 0)
  expect(document.querySelector('details')?.open).toBe(true)
  expect(inspect.mock.lastCall?.[0].details['Returned feature properties']).toEqual(draw.features?.[0].properties)
  expect(inspect.mock.lastCall?.[0].key).toMatch(/^map-feature:/)
  const opener = screen.getByRole('button', { name: 'Inspect FIXTURE from Station reports' })
  expect(inspect.mock.lastCall?.[1]).toBe(opener)
  expect(screen.getByRole('table')).toHaveTextContent('temperature0')
  expect(screen.getByRole('table')).toHaveTextContent('visibilityNot supplied (null)')
  expect(select).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Use Cape Spear as Focus' }))
  expect(select.mock.lastCall?.[0].id).toBe('cape-spear')
  await userEvent.click(screen.getByRole('button', { name: 'Inspect reference location Cape Spear' }))
  expect(inspect.mock.lastCall?.[0].text).toContain('not as an observing station')
})

it('preserves actual inputs, declared source mapping and missing capture/version explicitly', () => {
  const details = mapLayerEvidence(layer.id, layer, draw).details
  expect(details?.['Actual frame times']).toEqual([at])
  expect(details?.['Source/field mapping']).toMatchObject({ status: 'partial' })
  expect(details?.['Capture identity']).toBeNull()
  expect(details?.['Method version']).toBeNull()
  expect(mapLayerEvidence('removed', undefined, undefined).text).toContain('No current draw receipt')
})


it('distinguishes identical reports inspected under different exact Focus selections', () => {
  const first = { ...draw, selection: { latitude: 47.5, longitude: -52.7, instant: Date.parse(at) } }
  expect(featureEvidenceKey(first, 0)).not.toBe(featureEvidenceKey({ ...first, selection: { ...first.selection, latitude: 47.6 } }, 0))
  expect(featureEvidenceKey(first, 0)).not.toBe(featureEvidenceKey({ ...first, selection: { ...first.selection, instant: first.selection.instant + 1 } }, 0))
})


it('jumps past Map controls into samples without changing Focus or inspecting a value', async () => {
  const user = userEvent.setup(), inspect = vi.fn(), select = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
  render(<><MapSamplesLink /><button>Map control to bypass</button><MapEvidenceDetails layers={[layer]} drawn={[draw]} location={{ id: 'point', name: 'Point', kind: 'map', latitude: 47.51, longitude: -52.69 }} instant={Date.parse(at)} statuses={[]} responseSourceIds={new Set()} onSelect={select} onInspect={inspect} /></>)
  const href = window.location.href
  await user.tab()
  expect(screen.getByRole('link', { name: 'Skip to Map samples' })).toHaveFocus()
  await user.keyboard('{Enter}')
  expect(document.querySelector('details')?.open).toBe(true)
  expect(screen.getByRole('heading', { name: 'Map samples and display provenance' })).toHaveFocus()
  expect(window.location.href).toBe(href)
  expect(select).not.toHaveBeenCalled()
  expect(inspect).not.toHaveBeenCalled()
  await user.tab()
  expect(screen.getByRole('button', { name: 'Inspect FIXTURE from Station reports' })).toHaveFocus()
})


it('opens a lazily constructed native cell inspector without expanding the whole frame', () => {
  const inspect = vi.fn()
  const nativeGrid = { region: [-70,40,-40,55], latitudes: [47.5], longitudes: [-52.7, -52.6], latitude_edges: [47.55, 47.45], longitude_edges: [-52.75, -52.65, -52.55], percentages: [[0, 50]], native_time: at, provenance: { run: at } } as unknown as NonNullable<DrawEvidence['nativeGrid']>
  render(<MapEvidenceDetails layers={[]} drawn={[{...draw,features:undefined,nativeGrid}]} location={{id:'p',name:'Point',kind:'map',latitude:47.5,longitude:-52.7}} instant={Date.parse(at)} statuses={[]} responseSourceIds={new Set()} onSelect={vi.fn()} onInspect={inspect} />)
  expect(screen.queryByText('percentage')).not.toBeInTheDocument()
  act(() => openMapFeature(draw.id, 1))
  expect(document.querySelector('details')?.open).toBe(true)
  expect(inspect).toHaveBeenCalledTimes(1)
  expect(inspect.mock.lastCall?.[0].details['Returned feature properties'].percentage).toBe(50)
  expect(screen.getAllByRole('row')).toHaveLength(2)
})
