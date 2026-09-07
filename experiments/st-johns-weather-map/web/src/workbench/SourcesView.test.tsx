import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { normalizePoint } from '../api'
import type { CatalogSource } from '../types'
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
  expect(screen.getByRole('table')).toHaveTextContent('Global declaration')
  expect(screen.getByRole('table')).toHaveTextContent('No readings returned at Focus; coverage unestablished')
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
