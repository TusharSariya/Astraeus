import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import type { LayerItem } from '../types'
import { layerImagery, layerMapping, mapRunRefusals } from './layerIdentity'
import { sourceEvidence, useSourcesView } from './SourcesView'

const at = '2026-09-07T12:00:00Z'
const layer: LayerItem = { id: 'bundle', title: 'A misleading product title', kind: 'raster', field: 'bundle', product: 'Other product', units: 'mixed', semantics: 'Constructed test', times: [at], mapping_status: 'known', mapping_reason: 'Explicit bundle declaration', field_mappings: [
  { source_id: 'actual-source-a', field_key: 'temperature_2m', declared_field: 'TMP' },
  { source_id: 'actual-source-b', field_key: 'wind_speed_10m', declared_field: 'WIND' },
], imagery_availability: { status: 'known', checked_at: at, basis: 'provider_inventory', reason: 'Rendering can fail', times: ['2026-09-07T13:00:00Z'] } }

it('does not infer image coverage or source identity from a title and stored samples', () => {
  const legacy = { ...layer, mapping_status: undefined, field_mappings: undefined, imagery_availability: undefined }
  expect(layerMapping(legacy).fields).toEqual([])
  expect(layerMapping(legacy).status).toBe('unknown')
  expect(layerImagery(legacy).times).toEqual([])
  expect(layerImagery(legacy).status).toBe('unknown')
  expect(layerMapping({ ...layer, field_mappings: [] }).status).toBe('unknown')
  expect(layerImagery({ ...layer, imagery_availability: { ...layer.imagery_availability!, status: 'unknown' } }).status).toBe('unknown')
  expect(layerImagery({ ...layer, imagery_availability: { ...layer.imagery_availability!, status: 'unknown' } }).times).toEqual([])
})

it('joins each explicitly named source without turning the layer into a point reading', async () => {
  const inspect = vi.fn()
  function Harness() { return useSourcesView({ catalog: [], statuses: [], fields: [], layers: [layer], drawn: [], instant: Date.parse(at), catalogError: null, statusError: null, onInspect: inspect }) }
  render(<Harness />)
  await userEvent.click(screen.getByRole('button', { name: 'Inspect source actual-source-b' }))
  expect(inspect.mock.lastCall?.[0].details['Explicitly associated layers']).toHaveLength(1)
  expect(inspect.mock.lastCall?.[0].details['Returned evidence at Focus']).toEqual([])
  await userEvent.click(screen.getByRole('button', { name: 'Coverage lanes' }))
  expect(screen.getAllByText(/No point samples were returned/)).toHaveLength(2)
  await userEvent.click(screen.getByText(/Layer frame identities/))
  expect(screen.getByText(/Source mapping known/)).toBeInTheDocument()
  expect(screen.getByText(/Imagery availability: known/)).toHaveTextContent('Rendering can fail')
  await userEvent.click(screen.getByText(/Advertised image times/))
  expect(screen.getByText('2026-09-07T13:00:00Z')).toBeInTheDocument()
  expect(screen.getByText(/Listed native frames:/)).toHaveTextContent(at)
  expect(sourceEvidence('unnamed', [], [], [], [layer]).details?.['Explicitly associated layers']).toEqual([])
})


it('withholds only explicitly mapped source pins without inferring a source from a product', () => {
  expect(mapRunRefusals([layer], { unrelated: 'old' })).toEqual({})
  expect(mapRunRefusals([layer], { 'actual-source-a': 'old' }).bundle).toContain('actual-source-a: old')
  expect(mapRunRefusals([layer], { 'actual-source-a': 'latest' })).toEqual({})
  expect(mapRunRefusals([{ ...layer, field_mappings: undefined, mapping_status: undefined }], { 'Other product': 'old' })).toEqual({})
})
