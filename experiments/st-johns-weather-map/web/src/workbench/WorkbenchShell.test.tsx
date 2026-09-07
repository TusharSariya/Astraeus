import { useState } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { WorkbenchShell } from './WorkbenchShell'
import type { View } from './focusUrl'

function Harness() {
  const [view, setView] = useState<View>('Map'); const [dock, setDock] = useState<View | null>(null)
  return <WorkbenchShell view={view} dock={dock} onView={setView} onDock={setDock} focus="47.5, -52.6 · 2026-09-07T12:00:00Z" status="Unavailable" timeline={<input aria-label="Shared timeline" type="range" />} views={{ Map: <p>Map content</p>, Series: <p>Series content</p>, Sources: <p>Source content</p>, Sky: <p>Sky content</p>, Activity: <p>Activity content</p> }} />
}
describe('Bench composition', () => {
  it('replaces a companion and moves a docked view to the stage without duplication', async () => {
    const user = userEvent.setup(); render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Dock Series' }))
    await user.click(screen.getByRole('button', { name: 'Dock Sky' }))
    expect(screen.queryByLabelText('Series companion')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Sky companion')).toBeInTheDocument()
    await user.click(within(screen.getByRole('navigation', { name: 'Evidence views' })).getByRole('button', { name: 'Sky' }))
    expect(screen.queryByLabelText('Sky companion')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Sky' })).toHaveFocus()
    expect(screen.getAllByRole('slider')).toHaveLength(1)
    expect(screen.getByRole('status')).toHaveTextContent('Unavailable')
  })
  it('returns from expansion and leaves native input Escape alone', async () => {
    const user = userEvent.setup(); render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Expand Map' }))
    screen.getByRole('slider').focus(); await user.keyboard('{Escape}')
    expect(screen.getByRole('button', { name: 'Return to Bench' })).toBeInTheDocument()
    screen.getByRole('heading', { name: 'Map' }).focus(); await user.keyboard('{Escape}')
    expect(screen.getByRole('button', { name: 'Expand Map' })).toBeInTheDocument()
  })
})
