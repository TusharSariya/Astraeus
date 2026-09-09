import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from '../App'
vi.mock('../MapPanel', () => ({ MapPanel: () => <p>Map renderer seam</p> }))
const at = '2026-09-07T12:00:00.000Z'
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(at)
  window.history.replaceState(null, '', `/?lat=47.5123456789&lon=-52.6987654321&t=${at}&stack=[]`)
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    const data = url.pathname.endsWith('/point') ? { data_mode: 'live', valid_time: url.searchParams.get('valid_time'), selection: { mode: 'evidence_only', badge: 'Evidence only' }, fields: [{ field: 'temperature', value: 0, provenance: { source_id: 'noaa-gfs', provider: 'NOAA', normalized_units: 'degC', evidence_class: 'retrieved', data_mode: 'live', valid_time: at } }] }
      : url.pathname.endsWith('/catalog') ? { sources: [] }
      : url.pathname.endsWith('/layers') ? { layers: [], data_mode: 'live' }
      : url.pathname.endsWith('/timeline') ? { data_mode: 'live', start: at, end: '2026-09-08T12:00:00Z', items: [] }
      : { data_mode: 'unavailable', notices: ['Fixed unsupported'] }
    return new Response(JSON.stringify(data))
  }))
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); window.history.replaceState(null, '', '/') })
it('keeps an explicitly fixed instant equal to Now fixed, then makes Now links session-relative', async () => {
  render(<App />)
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Live API'))
  expect(new URLSearchParams(window.location.search).get('t')).toBe(at)
  expect(new URLSearchParams(window.location.search).get('lat')).toBe('47.5123456789')
  expect(String(vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes('/point?'))?.[0])).toContain('valid_time=2026-09-07T12')
  fireEvent.click(screen.getByText(/Fixed instant/))
  await userEvent.click(screen.getByRole('button', { name: 'Use session Now' }))
  await waitFor(() => expect(new URLSearchParams(window.location.search).has('t')).toBe(false))
})
it('keeps keyboard inspection coherent across a response and theme change', async () => {
  render(<App />)
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Live API'))
  fireEvent.click(screen.getByRole('button', { name: 'Evidence' }))
  fireEvent.click(screen.getByText('Point evidence ledger'))
  const opener = await screen.findByRole('button', { name: /^Inspect temperature from noaa\-gfs/ })
  await userEvent.click(opener)
  expect(screen.getByRole('heading', { name: 'Evidence · temperature' })).toHaveFocus()
  await userEvent.click(screen.getByRole('button', { name: 'Red night' }))
  expect(screen.getByRole('complementary', { name: 'Evidence inspector' })).toHaveTextContent('noaa-gfs')
  await userEvent.click(screen.getByRole('button', { name: 'Close inspector' }))
  await waitFor(() => expect(opener).toHaveFocus())
})
it('does not query a default Series point while a named site awaits registered geometry', async () => {
  window.history.replaceState(null, '', `/?site=signal-hill&view=Series&t=${at}&stack=[]`)
  render(<App />)
  await screen.findByRole('heading', { name: 'Series' })
  await waitFor(() => expect(screen.getByText(/Registered site signal-hill awaits registry metadata/)).toBeInTheDocument())
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/point/comparison'))).toBe(false)
})

it('reads a same-second Focus change exactly and clears old point evidence on failure', async () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Evidence' }))
  fireEvent.click(screen.getByText('Point evidence ledger'))
  await screen.findByRole('button', { name: /^Inspect temperature from noaa\-gfs/ })
  const original = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (...args) => String(args[0]).includes('/point?') ? new Response('{}', { status: 503 }) : original(...args))
  fireEvent.click(screen.getByText(/Fixed instant/))
  fireEvent.change(screen.getByLabelText('Instant (ISO, with timezone)'), { target: { value: '2026-09-07T12:00:00.123Z' } })
  fireEvent.click(screen.getByRole('button', { name: 'Use instant' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: /^Inspect temperature from noaa\-gfs/ })).not.toBeInTheDocument())
  const urls = vi.mocked(fetch).mock.calls.map(([input]) => new URL(String(input), 'http://localhost')).filter((url) => url.pathname.endsWith('/point'))
  expect(urls.at(-1)?.searchParams.get('valid_time')).toBe('2026-09-07T12:00:00.123Z')
})


it('shares loaded native pages with Sources and clears its open inspector on fixed expiry without fetching again', async () => {
  vi.useRealTimers()
  vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] }); vi.setSystemTime(at)
  const original = vi.mocked(fetch).getMockImplementation()!
  let nativeReads = 0
  vi.mocked(fetch).mockImplementation(async (...args) => {
    if (!String(args[0]).endsWith('/point/comparison')) return original(...args)
    nativeReads++
    const selection = JSON.parse(String(args[1]?.body))
    return Response.json({id:'shared-fixed',selection,selected_at:at,expires_at:'2026-09-07T12:05:00Z',complete:true,next_cursor:null,completed_positions:1,total_positions:1,coverage:[],curves:[{id:'eccc-hrdps:temperature_2m',source_id:'eccc-hrdps',product_id:'hrdps',group:'temperature',field:'temperature_2m',definition:'temperature',units:'degC',samples:[{time:at,run_id:'native',evidence:{key:'temperature_2m',field:'temperature_2m',value:1234,provenance:{source_id:'eccc-hrdps',evidence_class:'retrieved',data_mode:'fixture',valid_time:at,normalized_units:'degC',quality:{status:'good',flags:[]}}}}]}]})
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Series' }))
  await vi.waitFor(() => expect(screen.getByRole('img', {name:/Temperature; native timestamps/})).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Sources' }))
  await vi.waitFor(() => expect(screen.getByRole('region', { name: 'Finite native Series evidence' })).toBeInTheDocument())
  fireEvent.click(screen.getAllByText(/Native values, gaps and run identity/)[0])
  fireEvent.click(screen.getByRole('button', { name: /^Inspect temperature_2m at 2026\-09\-07T12:00:00\.000Z/ }))
  expect(screen.getByRole('complementary', { name: 'Evidence inspector' })).toHaveTextContent('1234')
  expect(screen.getByRole('complementary', { name: 'Evidence inspector' })).toHaveTextContent('Finite native selection')
  await act(async () => { vi.advanceTimersByTime(300000) })
  expect(screen.getByRole('complementary', { name: 'Evidence inspector' })).not.toHaveTextContent('1234')
  expect(screen.getByRole('complementary', { name: 'Evidence inspector' })).toHaveTextContent('Native selection expired or changed')
  expect(screen.getByRole('complementary', { name: 'Evidence inspector' })).toHaveTextContent('shared-fixed')
  expect(screen.getByText(/Native selection expired. Values are withheld/)).toBeInTheDocument()
  expect(nativeReads).toBe(1)
})

function timelineFixtures() {
  const reference = Date.parse(at)
  const stamp = (minutes: number) => new Date(reference + minutes * 60_000).toISOString()
  const layers = [{ id: 'radar', title: 'Radar native observations', kind: 'points', field: 'rain', product: 'Radar', units: 'mm', semantics: 'Constructed test', group: 'observation', times: [stamp(-6), stamp(0), stamp(6)], cadence_seconds: 360 }, { id: 'forecast', title: 'Hourly forecast', kind: 'raster', field: 'cloud', product: 'Model', units: '%', semantics: 'Constructed test', group: 'published_model', times: [stamp(0), stamp(60), stamp(120)], cadence_seconds: 3600 }]
  const stack = layers.map(layer => ({ id: layer.id, visible: true, opacity: .85 }))
  window.history.replaceState(null, '', `/?t=${at}&stack=${encodeURIComponent(JSON.stringify(stack))}`)
  const original = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (...args) => {
    const url = new URL(String(args[0]), 'http://localhost')
    if (url.pathname.endsWith('/layers')) return new Response(JSON.stringify({ data_mode:'fixture', layers: url.searchParams.get('product') === 'CAP' ? [] : layers }))
    if (url.pathname.endsWith('/timeline')) return new Response(JSON.stringify({ data_mode:'fixture', start:stamp(-1440), end:stamp(20160), boundary:stamp(1440), items:[] }))
    return original(...args)
  })
  return { reference, stamp }
}
it('keeps exact minute steps separate from native frame navigation and preserves instant across range changes', async () => {
  const { stamp } = timelineFixtures()
  render(<App />)
  await screen.findByRole('button', { name:'Next frame' })
  await waitFor(() => expect(screen.getByRole('button', { name:'Next frame' })).toBeEnabled())
  fireEvent.change(screen.getByLabelText('Step and playback interval'), { target:{ value:'2' } })
  fireEvent.click(screen.getByRole('button', { name:'Step forward 2 minutes' }))
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',stamp(2))
  fireEvent.click(screen.getByRole('button', { name:'Next frame' }))
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',stamp(6))
  fireEvent.click(screen.getByRole('button', { name:'Previous frame' }))
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',at)
  fireEvent.change(screen.getByLabelText('Timeline range'), { target:{ value:'outlook' } })
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',at)
  expect(screen.getAllByRole('slider', { name:'Valid timeline scrubber' })).toHaveLength(1)
})
it('advances discrete intervals, pauses on scrubbing, and has no background catch-up', async () => {
  const { stamp } = timelineFixtures()
  render(<App />)
  await waitFor(() => expect(screen.getByRole('button', { name:'Next frame' })).toBeEnabled())
  vi.useRealTimers(); vi.useFakeTimers({ toFake:['Date','setInterval','clearInterval'] }); vi.setSystemTime(at)
  const visibility = vi.spyOn(document,'visibilityState','get').mockReturnValue('visible')
  fireEvent.change(screen.getByLabelText('Step and playback interval'), { target:{ value:'4' } })
  fireEvent.click(screen.getByRole('button', { name:'Play' }))
  await act(async () => { vi.advanceTimersByTime(999) })
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',at)
  await act(async () => { vi.advanceTimersByTime(1) })
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',stamp(4))
  visibility.mockReturnValue('hidden')
  fireEvent(document,new Event('visibilitychange'))
  await act(async () => { vi.advanceTimersByTime(60_000) })
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',stamp(4))
  visibility.mockReturnValue('visible'); fireEvent(document,new Event('visibilitychange'))
  await act(async () => { vi.advanceTimersByTime(1000) })
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',stamp(8))
  fireEvent.keyDown(screen.getByRole('slider',{ name:'Valid timeline scrubber' }), { key:'ArrowLeft' })
  expect(document.querySelector('.bench-time-selected time')).toHaveAttribute('datetime',stamp(6))
  expect(screen.getByRole('button',{ name:'Play' })).toBeInTheDocument()
  visibility.mockRestore()
})
it('expands one set of tracks, coordinates right overlays, and restores keyboard focus', async () => {
  timelineFixtures(); render(<App />)
  const tracks = screen.getByRole('button',{ name:'Tracks' })
  await waitFor(() => expect(screen.getByRole('button', { name:'Next frame' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{ name:'Layers' }))
  fireEvent.click(tracks)
  expect(screen.getByRole('heading',{ name:'Native frame tracks' })).toHaveFocus()
  expect(screen.getByRole('complementary',{ name:'Layers overlay' })).toBeInTheDocument()
  expect(screen.getByRole('complementary',{ name:'Point data' })).toBeInTheDocument()
  expect(screen.getByRole('group',{ name:'Radar native observations frames' })).toBeInTheDocument()
  expect(screen.getByRole('group',{ name:'Hourly forecast frames' })).toBeInTheDocument()
  fireEvent.keyDown(screen.getByRole('heading',{ name:'Native frame tracks' }), { key:'Escape' })
  expect(tracks).toHaveFocus()
  expect(screen.queryByRole('region',{ name:'Layer timeline tracks' })).not.toBeInTheDocument()
})
