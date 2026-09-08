import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { MapStack, MapLegends, NOWCAST_STACK } from './MapStack'
import type { LayerSelection } from '../types'
function Harness() {
  const [stack, setStack] = useState<LayerSelection[]>([{ id: 'first', opacity: .5, visible: true }, { id: 'second', opacity: 1, visible: true }])
  return <><output aria-label="Stack state">{JSON.stringify(stack)}</output><MapStack layers={[]} stack={stack} onChange={setStack} drawn={[]} onInspect={vi.fn()} /></>
}
it('keeps absent layers in top-first order, hides without removing, and replaces Saved stacks', async () => {
  const user = userEvent.setup(); render(<Harness />)
  expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('second')
  await user.click(screen.getByRole('button', { name: 'Details for first' }))
  await user.click(screen.getByRole('button', { name: 'Raise first' }))
  await user.keyboard('{Escape}')
  await waitFor(() => expect(screen.getByRole('button', {name: 'first'})).toHaveFocus())
  expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('first')
  await user.click(screen.getByRole('button', { name: 'Show first' }))
  expect(screen.getByLabelText('Stack state')).toHaveTextContent('"visible":false')
  await user.type(screen.getByRole('textbox', { name: 'Stack name' }), 'My stack')
  await user.click(screen.getByRole('button', { name: 'Save stack' }))
  await user.click(screen.getByRole('button', { name: 'first' }))
  await user.selectOptions(screen.getByRole('combobox', { name: 'Saved stacks' }), 'My stack')
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  expect(screen.getByRole('button', { name: 'Show first' })).toHaveAttribute('aria-pressed', 'false')
})
it('shows one family legend with distinct provider scales and never relabels the newest index run as the drawn run', async () => {
  const layers = ['total_cloud_opacity', 'total_cloud_geometric'].map((field_key, index) => ({ id: `cloud-${index}`, title: `Cloud ${index}`, field: field_key, field_key, family: 'cloud_cover', kind: 'raster', product: 'Declared product', units: '%', semantics: 'Declared cloud quantity', raster_available: true, legend_available: true, evidence_class: 'retrieved', run_time: '2026-09-07T12:00:00Z', frames: [{ valid_time: '2026-09-07T13:00:00Z', run_time: '2026-09-07T06:00:00Z', provider_run_id: 'older', run_stale: false }] }))
  render(<><MapLegends layers={layers} stack={layers.map(layer => ({ id: layer.id, visible: true, opacity: 1 }))} /><MapStack layers={layers} stack={layers.map((layer) => ({ id: layer.id, visible: true, opacity: 1 }))} onChange={vi.fn()} drawn={layers.map((layer) => ({ id: layer.id, drawn: true, description: 'Returned frame', times: ['2026-09-07T13:00:00Z'] }))} onInspect={vi.fn()} /></>)
  await userEvent.click(screen.getByRole('button', { name: 'Details for Cloud 0' }))
  expect(screen.getByText(/Drawn frame run: 2026-09-07T06:00:00Z/)).toBeInTheDocument()
  expect(screen.getAllByTestId('legend-families')).toHaveLength(1)
  expect(screen.getByText(/Their colour scales are separate/)).toBeInTheDocument()
  expect(screen.getAllByRole('img')).toHaveLength(2)
})

const retiredCloud = 'eccc-hrdps-surface-total-cloud'
const liveCloud = { id: 'geomet-live-hrdps-nt', title: 'HRDPS total cloud (live proxy)', field: 'total_cloud', kind: 'raster', product: 'HRDPS', units: '%', semantics: 'Provider total cloud image', evidence_basis: 'live_proxy' }
it('uses current delivery paths for all five Nowcast roles', () => {
  expect(NOWCAST_STACK.map(row => row.id)).toEqual([
    'geomet-live-goes-east-naturalcolor', 'geomet-live-hrdps-nt',
    'eccc-cap-alerts-current', 'eccc-radar-radar', 'eccc-lightning-lightning',
  ])
})
it('repairs a retired selection only on request, preserving its position and settings and returning focus', async () => {
  const user = userEvent.setup()
  const initial = [{ id: 'first', opacity: 1, visible: true }, { id: retiredCloud, opacity: .35, visible: false }, { id: 'last', opacity: .8, visible: true }]
  function RepairHarness() {
    const [stack, setStack] = useState(initial)
    return <><output aria-label="Stack state">{JSON.stringify(stack)}</output><MapStack layers={[liveCloud]} stack={stack} onChange={setStack} drawn={[]} onInspect={vi.fn()} /></>
  }
  render(<RepairHarness />)
  expect(screen.getByLabelText('Stack state').textContent).toBe(JSON.stringify(initial))
  await user.click(screen.getByRole('button', { name: `Details for ${retiredCloud}` }))
  expect(screen.getByText(/Stored HRDPS cloud delivery was retired/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Use HRDPS total cloud (live proxy)' }))
  expect(screen.getByLabelText('Stack state').textContent).toBe(JSON.stringify(initial.map(row => row.id === retiredCloud ? { ...row, id: liveCloud.id } : row)))
  expect(screen.getByRole('button', { name: 'Show HRDPS total cloud (live proxy)' })).toHaveFocus()
})
it.each([{ layers: [] }, { layers: [liveCloud] }])('does not offer an unpublished or already-selected replacement', ({ layers }) => {
  const onChange = vi.fn()
  render(<MapStack layers={layers} stack={[{ id: retiredCloud, opacity: 1, visible: true }, ...(layers.length ? [{ id: liveCloud.id, opacity: 1, visible: true }] : [])]} onChange={onChange} drawn={[]} onInspect={vi.fn()} />)
  expect(screen.queryByRole('button', { name: `Use ${liveCloud.title}` })).not.toBeInTheDocument()
  expect(onChange).not.toHaveBeenCalled()
})
it.each([
  { loading: true, error: null, message: 'Checking layer catalogue' },
  { loading: false, error: 'HTTP 503', message: 'Catalogue request failed · availability unknown' },
  { loading: false, error: null, message: 'Not in current catalogue · imagery not requested' },
])('distinguishes missing layer state: $message', ({ loading, error, message }) => {
  render(<MapStack layers={[]} stack={[{ id: 'unknown-layer', opacity: 1, visible: true }]} onChange={vi.fn()} drawn={[]} onInspect={vi.fn()} loading={loading} error={error} />)
  expect(screen.getByTitle(message)).toBeInTheDocument()
})
it('exposes catalogue notices and actual draw failure without claiming empty data or a cache hit', async () => {
  const user = userEvent.setup(), inspect = vi.fn()
  render(<MapStack layers={[liveCloud]} stack={[{ id: liveCloud.id, opacity: 1, visible: true }]} onChange={vi.fn()} drawn={[{ id: liveCloud.id, drawn: false, status: 'unavailable', times: [], description: 'Raster request failed: HTTP 502' }]} onInspect={inspect} notices={['Provider frame index unavailable']} />)
  await user.click(screen.getByRole('button', { name: `Details for ${liveCloud.title}` }))
  await user.click(screen.getByRole('button', { name: `Inspect layer ${liveCloud.title}` }))
  expect(inspect.mock.calls[0][0].details['Catalogue notices']).toEqual(['Provider frame index unavailable'])
  expect(inspect.mock.calls[0][0].text).toBe('Raster request failed: HTTP 502')
})
it('shows loading draw state instead of unavailable', () => {
  render(<MapStack layers={[liveCloud]} stack={[{ id: liveCloud.id, opacity: 1, visible: true }]} onChange={vi.fn()} drawn={[{ id: liveCloud.id, drawn: false, status: 'loading', times: [], description: 'Fetching frame' }]} onInspect={vi.fn()} />)
  expect(screen.getByTitle('Loading frame')).toBeInTheDocument()
  expect(screen.queryByText(/Unavailable · no frame drawn/)).not.toBeInTheDocument()
})

it('distinguishes a successful empty feature response from unavailable data', () => {
  render(<MapStack layers={[liveCloud]} stack={[{ id: liveCloud.id, opacity: 1, visible: true }]} onChange={vi.fn()} drawn={[{ id: liveCloud.id, drawn: false, status: 'empty', times: [], description: 'Response contained no features' }]} onInspect={vi.fn()} />)
  expect(screen.getByTitle('No features returned')).toBeInTheDocument()
  expect(screen.queryByText(/Unavailable · no frame drawn/)).not.toBeInTheDocument()
})

it('removing Active rows focuses next, previous, then the list heading', async () => {
  const user = userEvent.setup(); render(<Harness />)
  await user.click(screen.getByRole('button', {name:'second'}))
  expect(screen.getByRole('button', {name:'first'})).toHaveFocus()
  await user.click(screen.getByRole('button', {name:'first'}))
  expect(screen.getByText('Drawing order · top first')).toHaveFocus()
})
it('context details do not mutate membership and preserve opacity and ordering until explicit edits', async () => {
  const user = userEvent.setup(); render(<Harness />)
  const original = screen.getByLabelText('Stack state').textContent
  const opener = screen.getByRole('button', {name:'first'})
  fireEvent.contextMenu(opener)
  expect(screen.getByRole('heading', {name:'first'})).toHaveFocus()
  expect(screen.getByLabelText('Stack state').textContent).toBe(original)
  fireEvent.change(screen.getByRole('slider', {name:'Stack opacity first'}), {target:{value:'.25'}})
  expect(screen.getByLabelText('Stack state')).toHaveTextContent('"opacity":0.25')
  await user.keyboard('{Escape}')
  await waitFor(() => expect(opener).toHaveFocus())
  expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('second')
})

it('removing the last Active row falls back to the previous row', async () => {
  render(<Harness />)
  await userEvent.click(screen.getByRole('button', {name:'first'}))
  expect(screen.getByRole('button', {name:'second'})).toHaveFocus()
})
