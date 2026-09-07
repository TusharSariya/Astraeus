import { StrictMode, useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useActivity, type ActivityResponse } from './ActivityView'

const at = '2026-09-07T12:00:00Z'
const point = { id: 'point', name: 'Point', latitude: 47.5615, longitude: -52.7126, kind: 'map' as const }
const inspect = vi.fn(), jump = vi.fn(), stack = vi.fn(), instant = vi.fn()
let calls: URL[], failed: boolean
const sample = { field: 'temperature_2m', key: 'temperature_2m', value: 0, provenance: { source_id: 'eccc-hrdps', valid_time: at, normalized_units: 'degC' } }
const row = { name: 'thermal', field: 'temperature_2m', outcome: 'evaluated', reason: null, loss: 0, weight_declared: 1, evaluated_weight: 1, weight_held: 1, input: { evidence: sample, reason: null, skipped: [], fell_to_next_source: false }, threshold_defaults: {}, thresholds_in_force: {} }
function body(url: URL): ActivityResponse {
  return { focus: { latitude: point.latitude, longitude: point.longitude, valid_time: url.searchParams.get('valid_time')!, site_id: null },
    cache: { state: 'miss', computed_at: at, expires_at: '2026-09-07T12:05:00Z', key: 'fixed' }, input_identity: 'fixture', notices: ['Constructed fixture'],
    verdicts: ['running','astronomy','aurora','landscape_photography'].map(profile_id => ({ profile_id, profile_version: 2, state: 'scored', score: 100, tier: 'core', limiting_criterion: 'thermal',
      hard_stops: [{ ...row, name: 'rain', outcome: 'unknown', reason: 'field_not_returned' }], criteria: [row], coverage: { declared:1, reachable:1, evaluated:1, floor:.6 }, window: { intervals:[] }, saved_stack: [{ id:'top', opacity:.8 }, { id:'bottom', opacity:.9 }], thresholds: { running_thermal_start: { default:20, units:'degC' } } })) }
}
function Harness({ selected = Date.parse(at), enabled = true }: { selected?: number; enabled?: boolean }) {
  const [, setEvidence] = useState<ActivityResponse | null>(null)
  const view = useActivity({ location:point, instant:selected, siteId:null, enabled, onEvidence:setEvidence, onInspect:inspect, onSeries:jump, onStack:stack, onInstant:instant })
  return enabled ? view : <p>Another view</p>
}
beforeEach(() => {
  vi.useFakeTimers({ toFake:['Date'] });vi.setSystemTime(at);localStorage.clear();calls=[];failed=false
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    const url = new URL(input, 'http://localhost'); calls.push(url)
    if (failed) return new Response(JSON.stringify({ detail:{ code:'activity_unavailable', message:'Fixed failure' } }), { status:503 })
    const response=body(url)
    if (url.pathname.endsWith('/series')) return new Response(JSON.stringify({ ...response, cells:[{ focus:response.focus, verdicts:response.verdicts, notices:[] }, { focus:{ ...response.focus,valid_time:'2026-09-07T14:00:00Z' }, verdicts:response.verdicts,notices:[] }], end:url.searchParams.get('end'), resolution_seconds:3600, next_start:null,complete:true,queried_times:[at,'2026-09-07T14:00:00Z'] }))
    return new Response(JSON.stringify(response))
  }))
})
afterEach(() => { vi.useRealTimers();vi.unstubAllGlobals();vi.clearAllMocks() })
it('renders four fixed lanes, one expansion and shared inspector/stack/Series actions', async () => {
  render(<Harness />);await screen.findByText(/Computed/)
  await userEvent.click(screen.getByRole('button',{name:'Running'}))
  expect(screen.getAllByRole('button', { expanded:true })).toHaveLength(1)
  await userEvent.click(screen.getByRole('button',{name:'Inspect running thermal'}))
  expect(inspect.mock.calls[0][0].details['Selected criterion'].input.evidence.value).toBe(0)
  await userEvent.click(screen.getByRole('button',{name:'Open running thermal in Series'}))
  expect(jump).toHaveBeenCalledWith('temperature_2m','eccc-hrdps')
  await userEvent.click(screen.getByRole('button',{name:'Load Running Map stack'}))
  expect(stack).toHaveBeenCalledWith([{id:'bottom',opacity:.9,visible:true},{id:'top',opacity:.8,visible:true}])
  await userEvent.click(screen.getByRole('button',{name:'Aurora'}))
  expect(screen.queryByRole('button',{name:'Inspect running thermal'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Inspect aurora thermal'})).toBeInTheDocument()
})
it('does not refetch on stage changes and withholds previous Focus and failed refresh scores', async () => {
  const view=render(<Harness />);await screen.findByText(/Computed/)
  view.rerender(<Harness enabled={false} />);view.rerender(<Harness />)
  expect(calls).toHaveLength(1)
  failed=true;await userEvent.click(screen.getByRole('button',{name:'Refresh Activity'}))
  await screen.findAllByText(/Fixed failure/);expect(screen.queryByText('100 / 100')).not.toBeInTheDocument()
  view.rerender(<Harness selected={Date.parse(at)+3600000} />)
  await waitFor(()=>expect(calls).toHaveLength(3))
  expect(screen.queryByRole('button',{name:'Inspect running thermal'})).not.toBeInTheDocument()
})
it('reads only issued strip cells, preserves gap columns and moves shared Focus', async () => {
  render(<Harness />);await screen.findByText(/Computed/)
  await userEvent.click(screen.getByRole('button',{name:'Read native strip'}))
  const cell=await screen.findByRole('button',{name:'Running at 2026-09-07T14:00:00Z: scored'})
  expect(cell).toHaveStyle({gridColumn:'3'})
  await userEvent.click(cell);expect(instant).toHaveBeenCalledWith(Date.parse('2026-09-07T14:00:00Z'))
  expect(screen.queryByRole('button',{name:/Running at .*13:00/})).not.toBeInTheDocument()
})

it('survives StrictMode setup and cleanup without leaving a cancelled initial read', async () => {
  render(<StrictMode><Harness /></StrictMode>); await screen.findByText(/Computed/)
  expect(screen.getAllByText('100 / 100')).toHaveLength(4)
})

it('keeps editable profile defaults after failed overrides and removes ordinary URL sharing state', async () => {
  render(<Harness />);await screen.findByText(/Computed/)
  await userEvent.click(screen.getByRole('button',{name:'Running'}))
  await userEvent.click(screen.getByText('Running threshold overrides'))
  failed=true
  await userEvent.type(screen.getByLabelText(/running_thermal_start/),'30')
  await userEvent.click(screen.getByRole('button',{name:'Apply Running overrides'}))
  await screen.findAllByText(/Fixed failure/)
  expect(screen.getByLabelText(/running_thermal_start/)).toHaveValue(30)
  expect(calls.at(-1)?.searchParams.getAll('override')).toEqual(['running_thermal_start:30'])
  failed=false
  await userEvent.click(screen.getByRole('button',{name:'Restore all profile defaults'}))
  await screen.findByText(/Computed/)
  expect(calls.at(-1)?.searchParams.has('override')).toBe(false)
})
it('renders planning as a band without a printed precise score', async () => {
  const original=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (...args) => {
    const response=await original(...args);const value=await response.json()
    value.verdicts=value.verdicts.map((row: object)=>({...row,tier:'planning',score:73}))
    return new Response(JSON.stringify(value))
  })
  render(<Harness />);await screen.findByText(/Computed/)
  expect(screen.queryByText(/73/)).not.toBeInTheDocument()
  expect(screen.getAllByRole('meter')).toHaveLength(4)
})
