import { useState } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { WorkbenchShell } from './WorkbenchShell'
import type { View } from './focusUrl'

function Harness() {
  const [view, setView] = useState<View>('Map'); const [dock, setDock] = useState<View | null>(null)
  return <WorkbenchShell view={view} dock={dock} onView={setView} onDock={setDock} focus="47.5, -52.6 · 2026-09-07T12:00:00Z" status="Unavailable" statusLabel="Unavailable" timeline={<input aria-label="Shared timeline" type="range" />} views={{WeatherNext:"WeatherNext", Map: <p>Map content</p>, Series: <p>Series content</p>, Sources: <p>Source content</p>, Sky: <p>Sky content</p>, Activity: <p>Activity content</p> }} />
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

it('keeps provenance available in fullscreen and returns expansion focus to its opener', async () => {
  const user = userEvent.setup()
  render(<WorkbenchShell view="Map" dock={null} onView={() => {}} onDock={() => {}} focus="Focus" status="Status" timeline="Time" views={{WeatherNext:"WeatherNext",Map:'Map',Sources:'Sources',Series:'Series',Sky:'Sky',Activity:'Activity'}} inspector={<aside aria-label="Evidence inspector"><h2>Inspected reading</h2><button>Close inspector</button></aside>} />)
  await user.click(screen.getByText('View · Map'))
  await user.click(screen.getByRole('button', {name:'Expand Map'}))
  expect(screen.getByRole('complementary', {name:'Evidence inspector'})).toBeInTheDocument()
  await user.click(screen.getByRole('button', {name:'Return to Bench'}))
  await new Promise(resolve => requestAnimationFrame(resolve))
  expect(screen.getByRole('button', {name:'Expand Map'})).toHaveFocus()
})

it('starts views on demand and retains their DOM and local state when switching or docking', async () => {
  const user = userEvent.setup()
  function StatefulMap() { const [camera, setCamera] = useState('original'); return <input aria-label="Map camera state" value={camera} onChange={event => setCamera(event.target.value)} /> }
  function RetainedHarness() {
    const [view, setView] = useState<View>('Series'); const [dock, setDock] = useState<View | null>(null)
    return <WorkbenchShell view={view} dock={dock} onView={setView} onDock={setDock} focus="Focus" status="Status" timeline="Time" views={{WeatherNext:"WeatherNext",Map:<StatefulMap />, Series:'Series', Sky:'Sky', Activity:'Activity', Sources:'Sources'}} />
  }
  render(<RetainedHarness />)
  expect(screen.queryByLabelText('Map camera state')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', {name:'Map'}))
  const camera = screen.getByRole('textbox', {name:'Map camera state'})
  await user.clear(camera); await user.type(camera, 'panned camera')
  await user.click(screen.getByRole('button', {name:'Series'}))
  expect(screen.queryByRole('textbox', {name:'Map camera state'})).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', {name:'Dock Map'}))
  expect(screen.getByRole('textbox', {name:'Map camera state'})).toBe(camera)
  expect(camera).toHaveValue('panned camera')
})

it('replaces provenance with Layers without losing its search or Escape return', async () => {
  const user = userEvent.setup()
  function OverlayHarness() {
    const [inspected, setInspected] = useState(false)
    return <WorkbenchShell view="Map" dock={null} onView={() => {}} onDock={() => {}} focus="Focus" status="Status" timeline="Time" views={{WeatherNext:"WeatherNext",Map:'Map',Series:'Series',Sky:'Sky',Activity:'Activity',Sources:'Sources'}} layers={<><input aria-label="Layer search" /><button onClick={() => setInspected(true)}>Inspect layer</button></>} inspector={inspected ? <aside aria-label="Evidence inspector">Provenance</aside> : undefined} onDismissInspector={() => setInspected(false)} />
  }
  render(<OverlayHarness />)
  const opener = screen.getByRole('button', {name:'Layers'})
  expect(screen.queryByRole('textbox', {name:'Layer search'})).not.toBeInTheDocument()
  await user.click(opener)
  await user.type(screen.getByRole('textbox', {name:'Layer search'}), 'ECCC')
  await user.click(screen.getByRole('button', {name:'Inspect layer'}))
  expect(screen.queryByRole('textbox', {name:'Layer search'})).not.toBeInTheDocument()
  await user.click(opener)
  expect(screen.queryByLabelText('Evidence inspector')).not.toBeInTheDocument()
  expect(screen.getByRole('textbox', {name:'Layer search'})).toHaveValue('ECCC')
  await user.keyboard('{Escape}')
  expect(opener).toHaveFocus()
})
