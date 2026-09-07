import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EvidenceInspector, EvidenceLedger, evidenceKey } from './EvidenceInspector'
import { normalizePoint } from '../api'

const point = (value: number | null) => normalizePoint({ selection: { mode: 'evidence_only', badge: 'Evidence only' }, data_mode: 'live', valid_time: '2026-09-07T12:00:00Z', fields: [{ field: 'temperature', value, provenance: { normalized_units: 'degC', quality: { status: 'unknown', flags: value === null ? ['not_available'] : [] }, source_id: 'noaa-gfs', provider: 'NOAA', evidence_class: 'retrieved', data_mode: 'live', valid_time: '2026-09-07T12:00:00Z' } }] })
describe('response-owned evidence', () => {
  it('keeps numeric zero distinct from absence and names source-specific inspection', async () => {
    const inspect = vi.fn(); const rows = point(0).servedFields
    render(<EvidenceLedger rows={rows} onInspect={inspect} />)
    expect(screen.getByRole('table')).toHaveTextContent('0')
    await userEvent.click(screen.getByRole('button', { name: /^Inspect temperature from noaa\-gfs/ }))
    expect(inspect.mock.calls[0][0].attribution.sourceId).toBe('noaa-gfs')
  })
  it('focuses the inspector once and preserves focus on same-key response updates', () => {
    const close = vi.fn(); const { rerender } = render(<EvidenceInspector evidence={{ key: 'x', label: 'Temperature', text: '0', attribution: point(0).servedFields[0].attribution }} onClose={close} />)
    expect(screen.getByRole('heading')).toHaveFocus()
    screen.getByRole('button', { name: 'Close inspector' }).focus()
    rerender(<EvidenceInspector evidence={{ key: 'x', label: 'Temperature', text: 'Unavailable', attribution: point(null).servedFields[0].attribution }} onClose={close} />)
    expect(screen.getByRole('button', { name: 'Close inspector' })).toHaveFocus()
    expect(screen.getByText('Sample geometry').nextSibling).toHaveTextContent('Not supplied')
  })
})

it('distinguishes readings by native time, run and report while retaining actual sample geometry', () => {
  const a = point(0).servedFields[0]
  const b = { ...a, attribution: { ...a.attribution, validTime: '2026-09-07T11:43:00Z' } }
  expect(evidenceKey(a)).not.toBe(evidenceKey(b))
  const sampled = { ...a.attribution, responseProvenance: { ...a.attribution.responseProvenance, sampled_latitude: 47.5001, sampled_longitude: -52.6002, sample_distance_km: 0, sample_method: 'native cell' } }
  render(<EvidenceInspector evidence={{ key: 'sampled', label: 'Temperature', text: '0', attribution: sampled }} onClose={vi.fn()} />)
  expect(screen.getByText('Sample geometry').nextSibling).toHaveTextContent('47.5001')
  expect(screen.getByText('Sample geometry').nextSibling).toHaveTextContent('"distance_km": 0')
})

it('reads native Map values without JSON while retaining the complete record on demand', async () => {
  const details = { 'Returned feature geometry': { type: 'Point', coordinates: [-52.7, 47.5] }, 'Returned feature properties': { temperature: 0, visibility: null, usable: false, units: { temperature: 'degC' }, quality: 'unknown' } }
  const { rerender } = render(<EvidenceInspector evidence={{ key: 'map-feature:test', label: 'Station', text: 'Native report', details }} onClose={vi.fn()} />)
  expect(screen.getByText('Longitude').nextSibling).toHaveTextContent('-52.7')
  expect(screen.getByText('Latitude').nextSibling).toHaveTextContent('47.5')
  expect(screen.getByText('visibility').nextSibling).toHaveTextContent('Not supplied (null)')
  expect(screen.getByText('usable').nextSibling).toHaveTextContent('false')
  expect(screen.getByText('quality').nextSibling).toHaveTextContent('unknown')
  const disclosure = screen.getByText('Complete returned Map record · JSON').closest('details')
  expect(disclosure?.open).toBe(false)
  await userEvent.click(screen.getByText('Complete returned Map record · JSON'))
  expect(disclosure?.open).toBe(true)
  expect(disclosure?.querySelector('pre')?.textContent).toBe(JSON.stringify(details, null, 2))
  rerender(<EvidenceInspector evidence={{ key: 'map-feature:test', label: 'Station', text: 'Old values withheld', details: { 'Feature unavailable': true } }} onClose={vi.fn()} />)
  expect(screen.queryByText('Longitude')).not.toBeInTheDocument()
  expect(screen.queryByText('Complete returned Map record · JSON')).not.toBeInTheDocument()
})
