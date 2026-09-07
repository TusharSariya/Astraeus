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
