import { StrictMode, useState } from 'react'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useNativeSeries, type NativeSeriesResponse } from './NativeSeries'

const at = '2026-09-07T12:00:00.000Z'
const location = { id: 'point', name: 'Point', latitude: 47.51234567, longitude: -52.69876543, kind: 'map' as const }
let initial: NativeSeriesResponse
let calls: Array<{ path: string; body: Record<string, unknown> }>
let failRefresh: boolean
function Harness({ instant = Date.parse(at), enabled = true, moving = false }: { instant?: number; enabled?: boolean; moving?: boolean }) {
  const [runs, setRuns] = useState<Record<string, string>>({})
  const view = useNativeSeries({ location, instant, enabled, selectionMoving: moving, fields: [], runs, onRun: (source, run) => setRuns({ [source]: run }), onLatest: () => setRuns({}), onInspect: vi.fn() })
  return enabled ? view : <p>Another view</p>
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(at)
  calls = []; failRefresh = false
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input), body = JSON.parse(String(init?.body))
    calls.push({ path, body })
    if (path.endsWith('/changes')) return new Response(JSON.stringify({ snapshot_id: 'fixed', state: 'changed', reason: 'Selected revision changed' }))
    if (failRefresh) return new Response(JSON.stringify({ detail: { code: 'snapshot_unreadable', message: 'Fixed failure' } }), { status: 503 })
    if (body.cursor) return new Response(JSON.stringify({ ...initial, next_cursor: null, complete: true,
      series: [{ ...initial.series[0], samples: [{ ...initial.series[0].samples[0], value: 2, provenance: { ...initial.series[0].samples[0].provenance, valid_time: '2026-09-07T13:37:00Z' } }] }] }))
    initial = { selection: { ...body, start: String(body.start).replace('.000Z', 'Z'), end: String(body.end).replace('.000Z', 'Z') },
      snapshot: { id: 'fixed', selected_at: at, expires_at: '2026-09-07T12:05:00Z', change_token: 'check', identities: [] }, next_cursor: 'next', complete: false, notices: ['Constructed fixture'],
      series: body.selectors.map((s: { id: string; source_id: string; field: string; run: string }) => ({ selector_id: s.id, source_id: s.source_id, field: s.field, requested_run: s.run, availability: 'available', reason: 'Native rows', selectable_runs: [{ id: 'new', run_time: at }, { id: 'old', run_time: '2026-09-07T06:00:00Z' }], run_inventory_reason: 'Constructed two-run inventory',
        samples: [{ field: s.field, key: s.field, value: 0, provenance: { source_id: s.source_id, evidence_class: 'retrieved', data_mode: 'fixture', valid_time: String(body.start), run_time: s.run === 'old' ? '2026-09-07T06:00:00Z' : at, normalized_units: s.field === 'temperature_2m' ? 'degC' : '1', quality: { status: 'good', flags: [] } } }] })) }
    return new Response(JSON.stringify(initial))
  }))
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('retains native samples, separate axes and a finite selection across view and Compare switches', async () => {
  const rendered = render(<Harness />)
  expect(await screen.findAllByRole('img')).toHaveLength(2)
  expect(screen.getAllByText(/0 degC/)).toHaveLength(1)
  expect(calls[0].body.latitude).toBe(location.latitude)
  await userEvent.click(screen.getByRole('button', { name: 'Temporary Compare' }))
  await userEvent.click(screen.getByRole('button', { name: 'Overview' }))
  expect(calls).toHaveLength(1)
  rendered.rerender(<Harness enabled={false} />)
  rendered.rerender(<Harness />)
  expect(calls).toHaveLength(1)
  await userEvent.click(screen.getByRole('button', { name: 'Load next native samples' }))
  await userEvent.click(screen.getAllByText(/Native values, gaps and run identity/)[0])
  await screen.findByRole('button', { name: /Inspect temperature_2m at 2026-09-07T13:37:00Z/ })
  expect(calls[1].body).toEqual({ cursor: 'next' })
  expect(screen.queryByRole('button', { name: 'Load next native samples' })).not.toBeInTheDocument()
})

it('checks without replacing values; failed explicit refresh retains labelled original evidence', async () => {
  render(<Harness />)
  await screen.findAllByRole('img')
  await userEvent.click(screen.getByRole('button', { name: 'Check for changes' }))
  await screen.findByText(/changed: Selected revision changed/)
  expect(screen.getByText(/0 degC/)).toBeInTheDocument()
  failRefresh = true
  await userEvent.click(screen.getByRole('button', { name: 'Refresh Series' }))
  await screen.findByText(/Read failed; no replacement was applied/)
  expect(screen.getByText(/0 degC/)).toBeInTheDocument()
})

it('clears old Focus values when the new Focus cannot be read', async () => {
  const rendered = render(<Harness />)
  await screen.findAllByRole('img')
  failRefresh = true
  rendered.rerender(<Harness instant={Date.parse(at) + 3600000} />)
  await screen.findByText(/Read failed/)
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})

it('expires without renewing on a change check', async () => {
  vi.useRealTimers()
  vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] })
  vi.setSystemTime(at)
  render(<Harness />)
  await vi.waitFor(() => expect(screen.getAllByRole('img')).toHaveLength(2))
  await act(async () => { vi.advanceTimersByTime(300000) })
  expect(screen.getByText(/Selection expired/)).toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Check for changes' })).toBeDisabled()
  expect(calls).toHaveLength(1)
})

it('finishes the initial read under StrictMode effect replay', async () => {
  render(<StrictMode><Harness /></StrictMode>)
  expect(await screen.findAllByRole('img')).toHaveLength(2)
  expect(screen.queryByText(/Reading selected native evidence/)).not.toBeInTheDocument()
})


it('withholds selection reads during playback and resumes once at the exact paused instant', async () => {
  const rendered = render(<Harness />)
  await screen.findAllByRole('img')
  rendered.rerender(<Harness moving instant={Date.parse(at) + 123} />)
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Refresh Series' })).toBeDisabled()
  rendered.rerender(<Harness moving instant={Date.parse(at) + 456} />)
  expect(calls).toHaveLength(1)
  rendered.rerender(<Harness instant={Date.parse(at) + 456} />)
  await screen.findAllByRole('img')
  expect(calls).toHaveLength(2)
  expect(calls[1].body.start).toBe('2026-09-07T12:00:00.456Z')
})


it('pins a named previous run and keeps temporary two-run comparison out of browsing state', async () => {
  render(<Harness />)
  await screen.findAllByRole('img')
  const runControl = screen.getByRole('combobox', { name: 'Browsing run for eccc-hrdps' })
  await userEvent.selectOptions(runControl, 'old')
  await screen.findAllByRole('img')
  expect(calls.at(-1)?.body.selectors).toEqual(expect.arrayContaining([expect.objectContaining({ run: 'old' })]))
  expect(screen.getByRole('combobox', { name: 'Browsing run for eccc-hrdps' })).toBe(runControl)
  await userEvent.click(screen.getByRole('button', { name: 'Temporary Compare' }))
  await userEvent.click(screen.getByRole('button', { name: 'Compare latest and previous runs of Series A' }))
  await screen.findByRole('img', { name: /Same-field run overlay/ })
  expect(calls.at(-1)?.body.selectors).toEqual([
    { id: '0', source_id: 'eccc-hrdps', field: 'temperature_2m', run: 'new', product_id: null, variant: null, level: null },
    { id: '1', source_id: 'eccc-hrdps', field: 'temperature_2m', run: 'old', product_id: null, variant: null, level: null },
  ])
  expect(runControl).toHaveValue('old')
  const count = calls.length
  await userEvent.click(screen.getByRole('button', { name: 'Overview' }))
  expect(calls).toHaveLength(count)
  await userEvent.click(screen.getByRole('button', { name: 'Stop run comparison' }))
  await screen.findAllByRole('img')
  expect(calls.at(-1)?.body.selectors).toEqual(expect.arrayContaining([expect.objectContaining({ run: 'old' })]))
})

it('retains a removed pin without substituting latest readings and permits explicit recovery', async () => {
  render(<Harness />)
  await screen.findAllByRole('img')
  vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
    const body = JSON.parse(init.body)
    return new Response(JSON.stringify({ ...initial, selection: body, series: body.selectors.map((s: { id: string; run: string }) => ({ ...initial.series[0], selector_id: s.id, field: s.id === '0' ? 'temperature_2m' : 'total_cloud_opacity', requested_run: s.run,
      availability: 'unavailable', reason: 'Run no longer available', samples: [], selectable_runs: [{ id: 'newer', run_time: at }, { id: 'new', run_time: at }] })) }))
  }))
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Browsing run for eccc-hrdps' }), 'old')
  await screen.findAllByText(/unavailable: Run no longer available/)
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: 'Browsing run for eccc-hrdps' })).toHaveValue('old')
  expect(screen.getByRole('option', { name: /Pinned · old · Run no longer available/ })).toBeInTheDocument()
  await userEvent.click(screen.getAllByRole('button', { name: 'Use Latest available for eccc-hrdps' })[0])
  expect(screen.getByRole('combobox', { name: 'Browsing run for eccc-hrdps' })).toHaveValue('latest')
})

it('distinguishes inspection names for the same field and native time on two runs', async () => {
  render(<Harness />)
  await screen.findAllByRole('img')
  await userEvent.click(screen.getByRole('button', {name:'Temporary Compare'}))
  await userEvent.click(screen.getByRole('button', {name:'Compare latest and previous runs of Series A'}))
  await screen.findByRole('img', {name:/Same-field run overlay/})
  for (const summary of screen.getAllByText(/Native values, gaps and run identity/)) await userEvent.click(summary)
  const actions = screen.getAllByRole('button', {name:/Inspect temperature_2m at/})
  expect(actions).toHaveLength(2)
  expect(actions[0].getAttribute('aria-label')).toContain('from eccc-hrdps')
  expect(actions[0].getAttribute('aria-label')).not.toBe(actions[1].getAttribute('aria-label'))
})
