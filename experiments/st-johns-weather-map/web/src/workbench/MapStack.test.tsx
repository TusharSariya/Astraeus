import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MapStack } from './MapStack'
import type { LayerSelection } from '../types'
function Harness() {
  const [stack, setStack] = useState<LayerSelection[]>([{ id: 'first', opacity: .5, visible: true }, { id: 'second', opacity: 1, visible: true }])
  return <><output aria-label="Stack state">{JSON.stringify(stack)}</output><MapStack layers={[]} stack={stack} onChange={setStack} drawn={[]} onInspect={vi.fn()} /></>
}
it('keeps absent layers in top-first order, hides without removing, and replaces Saved stacks', async () => {
  const user = userEvent.setup(); render(<Harness />)
  expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('second')
  await user.click(screen.getByRole('button', { name: 'Raise first' }))
  expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('first')
  await user.click(screen.getByRole('checkbox', { name: 'Show first' }))
  expect(screen.getByLabelText('Stack state')).toHaveTextContent('"visible":false')
  await user.type(screen.getByRole('textbox', { name: 'Stack name' }), 'My stack')
  await user.click(screen.getByRole('button', { name: 'Save stack' }))
  await user.click(screen.getByRole('button', { name: 'Remove first' }))
  await user.selectOptions(screen.getByRole('combobox', { name: 'Saved stacks' }), 'My stack')
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  expect(screen.getByRole('checkbox', { name: 'Show first' })).not.toBeChecked()
})
it('shows one family legend with distinct provider scales and never relabels the newest index run as the drawn run', async () => {
  const layers = ['total_cloud_opacity', 'total_cloud_geometric'].map((field_key, index) => ({ id: `cloud-${index}`, title: `Cloud ${index}`, field: field_key, field_key, family: 'cloud_cover', kind: 'raster', product: 'Declared product', units: '%', semantics: 'Declared cloud quantity', raster_available: true, legend_available: true, evidence_class: 'retrieved', run_time: '2026-09-07T12:00:00Z', frames: [{ valid_time: '2026-09-07T13:00:00Z', run_time: '2026-09-07T06:00:00Z', provider_run_id: 'older', run_stale: false }] }))
  render(<MapStack layers={layers} stack={layers.map((layer) => ({ id: layer.id, visible: true, opacity: 1 }))} onChange={vi.fn()} drawn={layers.map((layer) => ({ id: layer.id, drawn: true, description: 'Returned frame', times: ['2026-09-07T13:00:00Z'] }))} onInspect={vi.fn()} />)
  expect(screen.getAllByText(/Drawn frame run: 2026-09-07T06:00:00Z/)).toHaveLength(2)
  await userEvent.click(screen.getByText('Family legends'))
  expect(screen.getAllByTestId('legend-families')).toHaveLength(1)
  expect(screen.getByText(/Their colour scales are separate/)).toBeInTheDocument()
  expect(screen.getAllByRole('img')).toHaveLength(2)
})
