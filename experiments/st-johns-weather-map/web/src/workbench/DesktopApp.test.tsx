import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  fireEvent.click(screen.getByText('Point evidence ledger'))
  const opener = await screen.findByRole('button', { name: 'Inspect temperature from noaa-gfs' })
  await userEvent.click(opener)
  expect(screen.getByRole('heading', { name: 'Evidence · temperature' })).toHaveFocus()
  await userEvent.click(screen.getByRole('button', { name: 'Red night' }))
  expect(screen.getByRole('complementary', { name: 'Evidence inspector' })).toHaveTextContent('noaa-gfs')
  await userEvent.click(screen.getByRole('button', { name: 'Close inspector' }))
  expect(opener).toHaveFocus()
})
it('does not query a default Series point while a named site awaits registered geometry', async () => {
  window.history.replaceState(null, '', `/?site=signal-hill&view=Series&t=${at}&stack=[]`)
  render(<App />)
  await screen.findByRole('heading', { name: 'Series' })
  await waitFor(() => expect(screen.getByText(/Registered site signal-hill awaits registry metadata/)).toBeInTheDocument())
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/point/series'))).toBe(false)
})

it('reads a same-second Focus change exactly and clears old point evidence on failure', async () => {
  render(<App />)
  fireEvent.click(screen.getByText('Point evidence ledger'))
  await screen.findByRole('button', { name: 'Inspect temperature from noaa-gfs' })
  const original = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (...args) => String(args[0]).includes('/point?') ? new Response('{}', { status: 503 }) : original(...args))
  fireEvent.click(screen.getByText(/Fixed instant/))
  fireEvent.change(screen.getByLabelText('Instant (ISO, with timezone)'), { target: { value: '2026-09-07T12:00:00.123Z' } })
  fireEvent.click(screen.getByRole('button', { name: 'Use instant' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Inspect temperature from noaa-gfs' })).not.toBeInTheDocument())
  const urls = vi.mocked(fetch).mock.calls.map(([input]) => new URL(String(input), 'http://localhost')).filter((url) => url.pathname.endsWith('/point'))
  expect(urls.at(-1)?.searchParams.get('valid_time')).toBe('2026-09-07T12:00:00.123Z')
})
