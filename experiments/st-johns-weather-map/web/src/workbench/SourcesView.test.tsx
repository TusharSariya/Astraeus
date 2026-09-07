import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { normalizePoint } from '../api'
import type { CatalogSource } from '../types'
import { readNativeSeriesResponse, type SharedSeriesSelection } from './NativeSeries'
import fixture from '../../../contracts/fixtures/source-delivery.json'
import { sourceEvidence, useSourcesView } from './SourcesView'
const at = '2026-09-07T12:00:00Z'
const catalog: CatalogSource[] = [{ id: 'declared-only', producer: 'Producer', product: 'Model', state: 'enabled', status_reason: 'Declared eligibility only', role: 'model', may_enter_consensus: false, cadence: 'hourly', forecast_horizon: '48 hours', geographic_coverage: 'Global declaration', licence: 'Declared terms', attribution: 'Producer', fields: [{ key: 'temperature_2m', family: 'temperature', storage: 'available-not-stored', upstream: 'TMP', note: 'No retrieval claim' }] }]
const fields = normalizePoint({ selection: { mode: 'evidence_only', badge: 'Evidence' }, data_mode: 'live', valid_time: at, fields: [0, null].map((value, index) => ({ field: 'temperature', key: 'temperature_2m', family: 'temperature', value, provenance: { source_id: 'observed-source', normalized_units: 'degC', quality: { status: 'unknown', flags: value === null ? ['not_available'] : [] }, valid_time: index ? '2026-09-07T11:43:00Z' : at, evidence_class: 'retrieved', data_mode: 'live' } })) }).servedFields
const inspect = vi.fn()
function Harness({ enabled = true }: { enabled?: boolean }) {
  const view = useSourcesView({ catalog, statuses: [], fields, layers: [], drawn: [], instant: Date.parse(at), catalogError: null, statusError: null, onInspect: inspect })
  return enabled ? view : <p>Map stage</p>
}
it('keeps declared geography and acquisition separate from point coverage across perspectives', async () => {
  const rendered = render(<Harness />)
  await userEvent.type(screen.getByRole('searchbox'), 'declared-only')
  expect(screen.getByRole('status')).toHaveTextContent('1 sources match')
  expect(screen.getByRole('table')).toHaveTextContent('Global declaration')
  expect(screen.getByRole('table', { name: 'Source Ledger at the shared Focus' })).toHaveTextContent('No readings returned at Focus; coverage unestablished')
  await userEvent.click(screen.getByRole('button', { name: 'Inspect source declared-only' }))
  expect(inspect.mock.lastCall?.[0].details['Returned evidence at Focus']).toEqual([])
  await userEvent.click(screen.getByRole('button', { name: 'Family finder' }))
  expect(screen.getByText(/Declared storage: available-not-stored/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Coverage lanes' }))
  expect(screen.getByText(/No point samples were returned/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Inspect source declared-only' })).toHaveAttribute('aria-pressed', 'true')
  rendered.rerender(<Harness enabled={false} />); rendered.rerender(<Harness />)
  expect(screen.getByRole('searchbox')).toHaveValue('declared-only')
  expect(screen.getByRole('button', { name: 'Coverage lanes' })).toHaveAttribute('aria-pressed', 'true')
})
it('keeps native zero and absence distinct and never turns a sparse report into a coverage band', async () => {
  const { container } = render(<Harness />)
  await userEvent.type(screen.getByRole('searchbox'), 'observed-source')
  await userEvent.click(screen.getByRole('button', { name: 'Coverage lanes' }))
  expect(container.querySelectorAll('.source-coverage-marks circle')).toHaveLength(1)
  expect(container.querySelectorAll('.source-coverage-marks rect')).toHaveLength(0)
  await userEvent.click(screen.getByText(/Native values and absence states/))
  expect(screen.getByRole('table')).toHaveTextContent('0')
  expect(screen.getByRole('table')).toHaveTextContent('not_available')
})
it('retains source identity while distinguishing missing catalogue and acquisition records', () => {
  const evidence = sourceEvidence('removed', catalog, null, fields)
  expect(evidence.key).toBe('source:removed')
  expect(evidence.details?.['Registry declaration']).toBe('Not present in the returned catalogue')
  expect(evidence.details?.['Returned evidence at Focus']).toEqual([])
})

it('keeps finite native selection scope, loaded-page limits and expiry separate from point coverage', async () => {
  const native: SharedSeriesSelection = {
    selection: { latitude: 47.56, longitude: -52.71, start: at, end: '2026-09-07T15:00:00Z', selectors: [{ id: 'a', source_id: 'native-only', field: 'temperature_2m', run: 'latest' }], page_size: 12 },
    snapshot: { id: 'finite', selected_at: at, expires_at: '2026-09-07T12:05:00Z', change_token: 'opaque', identities: [] },
    complete: false, expired: false, families: { a: ['temperature'] }, series: [{ selector_id: 'a', source_id: 'native-only', field: 'temperature_2m', requested_run: 'latest', availability: 'available' as const, reason: 'Constructed sparse readings', run_inventory_reason: 'Fixture has no run inventory', samples: [
      { ...readNativeSeriesResponse(fixture.series).series[0].samples[0], field: 'temperature', key: 'temperature_2m', value: 1234, provenance: { ...readNativeSeriesResponse(fixture.series).series[0].samples[0].provenance, source_id: 'native-only', normalized_units: 'degC', evidence_class: 'retrieved', valid_time: at, quality: { status: 'passed', flags: [] } } },
      { ...readNativeSeriesResponse(fixture.series).series[0].samples[0], field: 'temperature', key: 'temperature_2m', value: null, provenance: { ...readNativeSeriesResponse(fixture.series).series[0].samples[0].provenance, source_id: 'native-only', normalized_units: 'degC', evidence_class: 'retrieved', valid_time: '2026-09-07T13:37:00Z', quality: { status: 'unknown', flags: ['checked_absent'] } } },
    ] }],
  }
  function NativeHarness({ expired = false }) { return useSourcesView({ catalog, statuses: [], fields: [], layers: [], drawn: [], instant: Date.parse(at), nativeSelection: { ...native, expired }, catalogError: null, statusError: null, onInspect: inspect }) }
  const rendered = render(<NativeHarness />)
  await userEvent.type(screen.getByRole('searchbox'), 'native-only')
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Field family' }), 'temperature')
  expect(screen.getByRole('table', { name: 'Source Ledger at the shared Focus' })).toHaveTextContent('No readings returned at Focus; coverage unestablished')
  expect(screen.getByText(/Partial selection: only loaded pages/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Inspect source native-only' }))
  expect(inspect.mock.lastCall?.[0].details['Returned evidence at Focus']).toEqual([])
  expect(inspect.mock.lastCall?.[0].details['Finite native Series selection'].rows[0].samples).toHaveLength(2)
  await userEvent.click(screen.getByRole('button', { name: 'Coverage lanes' }))
  expect(screen.getByText(/No point samples were returned/)).toBeInTheDocument()
  await userEvent.click(screen.getByText(/Native values, gaps and run identity/))
  await userEvent.click(screen.getByRole('button', { name: /^Inspect temperature_2m at 2026\-09\-07T12:00:00Z/ }))
  expect(inspect.mock.lastCall?.[0].key).toMatch(/^native:finite:/)
  rendered.rerender(<NativeHarness expired />)
  expect(screen.getByText(/Native selection expired/)).toBeInTheDocument()
  expect(screen.queryByText(/1234/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Inspect temperature_2m/ })).not.toBeInTheDocument()
  expect(screen.getByRole('searchbox')).toHaveValue('native-only')
  expect(screen.getByRole('combobox', { name: 'Field family' })).toHaveValue('temperature')
  await userEvent.click(screen.getByRole('button', { name: 'Inspect source native-only' }))
  expect(inspect.mock.lastCall?.[0].details['Finite native Series selection'].rows[0].samples).toEqual([])
})
