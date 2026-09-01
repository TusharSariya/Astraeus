import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./MapPanel', () => ({
  MapPanel: ({ label, onSelect, onJumpToTime }: { label: string; onSelect: (point: unknown) => void; onJumpToTime: (date: Date) => void }) => (
    <section aria-label={`${label} map pane`}>
      <button onClick={() => onSelect({ id: 'map-test', name: 'Map point 47.500°N, 52.600°W', latitude: 47.5, longitude: -52.6, kind: 'map' })}>Choose map point</button>
      <button onClick={() => onJumpToTime(new Date(Date.now() + 3 * 3600 * 1000))}>Jump to nearest frame</button>
      <button onClick={() => onJumpToTime(new Date(Date.now() - 10 * 60 * 1000))}>Jump ten minutes back</button>
      <button onClick={() => onJumpToTime(new Date(Date.now() + 80 * 60 * 1000))}>Jump eighty minutes ahead</button>
    </section>
  ),
}))

// dataMode uses `null` (never a default-triggering `undefined`) to mean
// "omit data_mode from the response entirely" — the fail-closed case.
const apiPoint = (fields: unknown[] = [], selection = { mode: 'fallback', badge: 'HRDPS primary - consensus unavailable', reason: 'test' }, dataMode: string | null = 'live') => {
  const body: Record<string, unknown> = { latitude: 47.6186, longitude: -52.7519, valid_time: '2026-08-29T15:00:00Z', selection, fields }
  if (dataMode !== null) body.data_mode = dataMode
  return body
}
const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })
const emptyLayers = { layers: [] }
const emptyCatalog = { sources: [] }
const emptyTimeline = { data_mode: 'live', start: '', end: '', items: [] }
/** Shaped as the running API returns it: CYYT's METAR/TAF feeds have a recorded
 *  retrieval, the SmartAtlantic buoy is catalogued with none. Cape Spear claims
 *  no source, so it never appears here. */
const sourceStatus = {
  data_mode: 'mixed',
  statuses: [
    { source_id: 'awc-metar-speci', state: 'implementing', data_mode: 'live', last_retrieval: '2026-08-30T04:23:44Z', detail: 'live retrieval recorded by the ingestion worker' },
    { source_id: 'awc-taf', state: 'implementing', data_mode: 'live', last_retrieval: '2026-08-30T04:28:46Z', detail: 'live retrieval recorded by the ingestion worker' },
    { source_id: 'smartatlantic-st-johns', state: 'implementing', data_mode: 'unavailable', last_retrieval: null, detail: 'no live retrieval recorded' },
  ],
  notices: [],
}

/** A URL-routed fetch mock. Unlike `mockResolvedValue`, each matched call gets
 *  its own fresh `Response` — the app fetches `/catalog`, `/layers` and
 *  `/timeline` before `/point`, and a shared Response body can only be
 *  consumed once. */
const liveAstronomy = {
  data_mode: 'live', operational: false, latitude: 47.5615, longitude: -52.7126,
  window_start: '2026-08-30T19:00:00Z', window_end: '2026-08-31T22:00:00Z', valid_time: '2026-08-30T22:00:00Z',
  sun_altitude_deg: 1.7, moon_altitude_deg: -9.9, core_altitude_deg: 12.8,
  twilight_bands: [
    { kind: 'day', start: '2026-08-30T19:00:00Z', end: '2026-08-30T22:16:00Z' },
    { kind: 'civil_twilight', start: '2026-08-30T22:16:00Z', end: '2026-08-30T22:48:00Z' },
    { kind: 'nautical_twilight', start: '2026-08-30T22:48:00Z', end: '2026-08-30T23:26:00Z' },
    { kind: 'astronomical_twilight', start: '2026-08-30T23:26:00Z', end: '2026-08-31T00:08:00Z' },
    { kind: 'night', start: '2026-08-31T00:08:00Z', end: '2026-08-31T06:56:00Z' },
    { kind: 'day', start: '2026-08-31T08:49:00Z', end: '2026-08-31T22:00:00Z' },
  ],
  moon: { rise: '2026-08-30T22:58:00Z', set: '2026-08-31T12:43:00Z', above_horizon: [{ kind: 'moon_up', start: '2026-08-30T22:58:00Z', end: '2026-08-31T12:43:00Z' }], phase_deg: 213.2, illuminated_fraction: 0.918 },
  milky_way_core: { windows: [], max_altitude_deg: 13.4, caption: 'Geometry only - says nothing about cloud, transparency, or light pollution; at this latitude the galactic core culminates low (about 10-15 degrees at 47.6 N).' },
  provenance: { source_id: 'nasa-jpl-de442', kernel_id: 'DE442', kernel_sha256: 'abc', derivation: 'skyfield 1.55 + JPL DE442', derivation_version: 'astronomy-de442-v1', operational: false },
  notices: [],
}

/** Shaped as the running API returns it: observed and forecast Kp separate,
 *  the forecast carrying the provider's own per-value status, and the latest
 *  Bz with the instant it was measured. */
const liveSpaceWeather = {
  data_mode: 'live', operational: false, generated_at: '2026-08-31T02:00:00Z',
  kp_observed: {
    available: true, source_id: 'noaa-swpc-kp', product: 'Planetary K index (observed)',
    readings: [
      { time: '2026-08-30T21:00:00Z', value: 3.67, status: null },
      { time: new Date(Date.now() - 30 * 60 * 1000).toISOString(), value: 4.33, status: null },
    ],
    freshness: { status: 'fresh', age_seconds: 1800, threshold_seconds: 21600 }, notices: [],
  },
  kp_forecast: {
    available: true, source_id: 'noaa-swpc-kp', product: 'Planetary K index (3-day outlook, per-value status)',
    readings: [
      { time: new Date(Date.now() + 3 * 3600 * 1000).toISOString(), value: 4.0, status: 'estimated' },
      { time: new Date(Date.now() + 6 * 3600 * 1000).toISOString(), value: 5.0, status: 'predicted' },
      { time: new Date(Date.now() + 48 * 3600 * 1000).toISOString(), value: 7.0, status: 'predicted' },
    ],
    freshness: { status: 'fresh', age_seconds: 1800, threshold_seconds: 21600 }, notices: [],
  },
  solar_wind: {
    available: true, source_id: 'noaa-swpc-rtsw', product: 'Real-time solar wind magnetic field (1-minute)',
    bz_gsm_nt: -4.1, bt_nt: 4.3, measured_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
    feed_declared_spacecraft: 'SOLAR1',
    freshness: { status: 'fresh', age_seconds: 120, threshold_seconds: 900 }, notices: [],
  },
  notices: [],
}

function routedFetch(routes: { point?: unknown; layers?: unknown; catalog?: unknown; timeline?: unknown; sources?: unknown; astronomy?: unknown; spaceWeather?: unknown }) {
  return vi.fn(async (url: string) => {
    if (url.includes('/space-weather')) return response(routes.spaceWeather ?? liveSpaceWeather)
    if (url.includes('/astronomy')) return response(routes.astronomy ?? liveAstronomy)
    if (url.includes('/sources/status')) return response(routes.sources ?? sourceStatus)
    if (url.includes('/point')) return response(routes.point ?? apiPoint())
    if (url.includes('/layers')) return response(routes.layers ?? emptyLayers)
    if (url.includes('/catalog')) return response(routes.catalog ?? emptyCatalog)
    if (url.includes('/timeline')) return response(routes.timeline ?? emptyTimeline)
    return response({})
  })
}

/** The story cards, coverage ribbon and sky bands live in the panel expanded
 *  from the timeline dock; tests about them open it the way a reader would. */
async function openStory() {
  await userEvent.click(await screen.findByRole('button', { name: /Weather story/ }))
}

describe('weather workbench fail-closed behavior', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('API offline'))))

  it('shows unavailable unknown evidence on API outage instead of fixtures', async () => {
    render(<App />)
    expect(screen.getByText('Checking API')).toBeInTheDocument()
    expect(screen.getByText('Forecast unavailable · evidence only')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Unavailable')).toBeInTheDocument())
    expect(screen.queryByText('Experimental consensus')).not.toBeInTheDocument()
    expect(screen.getAllByText('Unknown').length).toBeGreaterThan(1)
    expect(screen.getByText(/No previous point evidence is being shown/i)).toBeInTheDocument()
  })

  it('clears previous point evidence while a new point is loading', async () => {
    let resolveSecond!: (value: Response) => void
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('/point')) {
        return new Promise<Response>((resolve) => { resolveSecond = resolve })
      }
      if (url.includes('/layers')) return response(emptyLayers)
      if (url.includes('/catalog')) return response(emptyCatalog)
      if (url.includes('/timeline')) return response(emptyTimeline)
      return response({})
    })
    // First /point call resolves immediately with evidence; every subsequent
    // /point call hangs until the test resolves it explicitly.
    let firstPointCall = true
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/point')) {
        if (firstPointCall) {
          firstPointCall = false
          return response(apiPoint([{ field: 'temperature', value: 16, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } }]))
        }
        return new Promise<Response>((resolve) => { resolveSecond = resolve })
      }
      if (url.includes('/layers')) return response(emptyLayers)
      if (url.includes('/catalog')) return response(emptyCatalog)
      if (url.includes('/timeline')) return response(emptyTimeline)
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await screen.findByText('16')
    await userEvent.click(screen.getByRole('button', { name: 'Choose map point' }))
    await waitFor(() => expect(screen.getByText('Checking API')).toBeInTheDocument())
    expect(screen.queryByText('16')).not.toBeInTheDocument()
    resolveSecond(response(apiPoint()))
  })

  it('converts response wind m/s to km/h and preserves fog enum semantics', async () => {
    vi.stubGlobal('fetch', routedFetch({
      point: apiPoint([
        { field: 'wind_speed', value: 10, provenance: { provider: 'ECCC', product: 'HRDPS', normalized_units: 'm/s', data_mode: 'live' } },
        { field: 'wind_gust', value: 12.5, provenance: { provider: 'ECCC', product: 'HRDPS', original_units: 'm/s', data_mode: 'live' } },
        { field: 'fog_state', value: 'not_indicated', provenance: { provider: 'CYYT', product: 'METAR', data_mode: 'live' } },
      ]),
    }))
    render(<App />)
    expect(await screen.findByText('36 / 45')).toBeInTheDocument()
    expect(screen.getByText('Fog not indicated by available evidence')).toBeInTheDocument()
    // No direction field came back, so none is claimed — and the old literal
    // "direction unavailable", which was printed even when one had, is gone.
    expect(screen.getByText(/km\/h · direction Unknown/)).toBeInTheDocument()
    expect(screen.queryByText(/direction unavailable/)).not.toBeInTheDocument()
  })

  it('shows jet-level wind and precipitable water as evidence with interpretation as caption, never a seeing verdict', async () => {
    vi.stubGlobal('fetch', routedFetch({
      point: apiPoint([
        { field: 'wind_speed_200hPa', value: 40, provenance: { provider: 'NOAA / NCEP', product: 'GFS', normalized_units: 'm s-1', data_mode: 'live', vertical_level: '200 hPa' } },
        { field: 'wind_speed_300hPa', value: 30, provenance: { provider: 'NOAA / NCEP', product: 'GFS', normalized_units: 'm s-1', data_mode: 'live', vertical_level: '300 hPa' } },
        { field: 'precipitable_water', value: 12.5, provenance: { provider: 'NOAA / NCEP', product: 'GFS', normalized_units: 'kg m-2', data_mode: 'live' } },
      ]),
    }))
    render(<App />)
    // 40 and 30 m/s convert to 144 and 108 km/h; the caption interprets, the
    // value never becomes a "seeing" category.
    expect(await screen.findByText('144 km/h · 108 km/h')).toBeInTheDocument()
    expect(screen.getByText(/strong jet flow degrades astronomical seeing/)).toBeInTheDocument()
    expect(screen.getByText('12.5 kg/m²')).toBeInTheDocument()
    expect(screen.getByText(/more degrades sky transparency/)).toBeInTheDocument()
    expect(screen.queryByText(/seeing: (good|poor|fair)/i)).not.toBeInTheDocument()
  })

  it('requests GPS only after action and reports denial with retained location', async () => {
    const getCurrentPosition = vi.fn((_success, failure) => failure({ code: 1, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 }))
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } })
    render(<App />)
    expect(getCurrentPosition).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Use my location' }))
    expect(await screen.findByText(/permission was denied.*CYYT.*remains selected/i)).toBeInTheDocument()
  })

  it('reports unavailable GPS separately', async () => {
    const getCurrentPosition = vi.fn((_success, failure) => failure({ code: 2, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 }))
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } })
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Use my location' }))
    expect(await screen.findByText(/position could not be determined/i)).toBeInTheDocument()
  })

  it('supports keyboard coordinate entry and validates bounds', async () => {
    render(<App />)
    await userEvent.clear(screen.getByLabelText('Latitude'))
    await userEvent.type(screen.getByLabelText('Latitude'), '47.55')
    await userEvent.clear(screen.getByLabelText('Longitude'))
    await userEvent.type(screen.getByLabelText('Longitude'), '-52.7')
    await userEvent.click(screen.getByRole('button', { name: 'Go' }))
    expect(screen.getByRole('heading', { name: 'Coordinates 47.550, -52.700' })).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Latitude'))
    await userEvent.type(screen.getByLabelText('Latitude'), '100')
    await userEvent.click(screen.getByRole('button', { name: 'Go' }))
    expect(screen.getByRole('alert')).toHaveTextContent('latitude from -90 to 90')
  })

  it('labels expert controls and comparison honestly, and never accepts a run/member/level it would discard', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Workbench' }))
    expect(screen.getByText(/Every option below comes from a response\. A selector with no returned options stays disabled and says why\./i)).toBeInTheDocument()
    expect(screen.getByText('No run time in returned provenance')).toBeInTheDocument()
    expect(screen.getByText('No ensemble member in returned provenance')).toBeInTheDocument()
    expect(screen.getByText('No vertical level in returned provenance')).toBeInTheDocument()
    expect(screen.getByText('Pane B unavailable')).toBeInTheDocument()
    expect(screen.queryByText(/ECMWF|2.4°C|moderate/i)).not.toBeInTheDocument()
    expect(screen.getByRole('table')).toHaveAccessibleName('Provenance returned for the selected point')

    // The API's /point takes latitude, longitude, valid_time and product only.
    // Run, member and level therefore must not present themselves as choices:
    // each is disabled and each says, in its own accessible description, that
    // it cannot change what is fetched.
    for (const name of ['Run', 'Member', 'Level']) {
      const control = screen.getByRole('combobox', { name })
      expect(control).toBeDisabled()
      expect(control).toHaveAccessibleDescription(/could not change what is fetched/i)
    }
    // Provider, product and variable genuinely do reach the request, so they
    // must not have been swept into the same read-only treatment.
    expect(screen.getByRole('combobox', { name: 'Provider' })).not.toHaveAccessibleDescription(/could not change what is fetched/i)
  })

  it('never sends a run, member or level parameter on any request', async () => {
    const fetchMock = routedFetch({
      point: apiPoint([{ field: 'temperature', value: 11, provenance: { provider: 'ECCC', product: 'HRDPS', run_time: '2026-08-30 06Z', member: 'control', vertical_level: '2 m above ground', data_mode: 'live' } }]),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await screen.findByText('11')
    await userEvent.click(screen.getByRole('button', { name: 'Workbench' }))
    // The provenance values are on screen to read...
    expect(await screen.findByRole('option', { name: '2026-08-30 06Z' })).toBeInTheDocument()
    // ...but no request carries them, because no such parameter exists.
    const urls = fetchMock.mock.calls.map(([url]) => String(url))
    expect(urls.length).toBeGreaterThan(0)
    expect(urls.some((url) => /[?&](run|member|level)=/.test(url))).toBe(false)
  })

  it('renders the fixture banner for a data_mode:"fixture" response and never claims Live API', async () => {
    vi.stubGlobal('fetch', routedFetch({
      point: apiPoint([{ field: 'temperature', value: 9, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'fixture' } }], undefined, 'fixture'),
    }))
    render(<App />)
    expect(await screen.findByText('9')).toBeInTheDocument()
    expect(screen.getByText('Development fixture')).toBeInTheDocument()
    expect(screen.getByText('DEVELOPMENT FIXTURE · NOT LIVE EVIDENCE')).toBeInTheDocument()
    expect(screen.queryByText('Live API')).not.toBeInTheDocument()
  })

  it('fails closed to unavailable when the response declares no data_mode at all', async () => {
    vi.stubGlobal('fetch', routedFetch({
      point: apiPoint([{ field: 'temperature', value: 9, provenance: { provider: 'ECCC', product: 'HRDPS' } }], undefined, null),
    }))
    render(<App />)
    await waitFor(() => expect(screen.getByText('Unavailable', { selector: '.source-state strong' })).toBeInTheDocument())
    expect(screen.queryByText('Live API')).not.toBeInTheDocument()
    expect(screen.getByText('NO LIVE EVIDENCE RETRIEVED')).toBeInTheDocument()
    expect(screen.getByText(/Response declared no data_mode/i)).toBeInTheDocument()
  })

  it('renders Unknown/Unavailable for a response with null fields and shows no numeric value anywhere', async () => {
    vi.stubGlobal('fetch', routedFetch({
      point: apiPoint([
        { field: 'temperature', value: null, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } },
        { field: 'wind_speed', value: null, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } },
      ]),
    }))
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0))
    expect(screen.getByText('Unavailable', { selector: '.marine-rule strong' })).toBeInTheDocument()
    // No digit should appear anywhere in the rendered evidence values (the
    // "01" section-head index is decorative chrome, not a data value).
    const evidenceValues = ['.hero-reading', '.metric-grid', '.marine-rule', '.warning']
      .map((selector) => document.querySelector(selector)?.textContent ?? '')
      .join(' ')
    expect(evidenceValues).not.toMatch(/\d/)
  })

  it('renders the empty-story state for a single-point response, with no fabricated narrative', async () => {
    vi.stubGlobal('fetch', routedFetch({
      point: apiPoint([{ field: 'temperature', value: 12, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } }]),
      timeline: emptyTimeline,
    }))
    render(<App />)
    await screen.findByText('12')
    await openStory()
    expect(screen.getByText(/24-hour narrative unavailable from this point response\. No forecast story has been inferred\./i)).toBeInTheDocument()
  })

  it('shows the marine section as Unavailable, never a number, when marine fields are absent', async () => {
    vi.stubGlobal('fetch', routedFetch({
      point: apiPoint([{ field: 'temperature', value: 5, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } }]),
    }))
    render(<App />)
    await screen.findByText('5')
    const marineRule = document.querySelector('.marine-rule')
    expect(marineRule?.textContent ?? '').toMatch(/Unavailable/)
    expect(marineRule?.textContent ?? '').not.toMatch(/\d/)
  })
})

describe('story card keyboard activation', () => {
  const storyPoint = (temperature: number) => apiPoint([
    { field: 'temperature', value: temperature, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } },
  ])

  /** A timeline publishing now and now+3h, so the story builds two real cards
   *  and activating the second is observably different from doing nothing. */
  const publishedTimeline = () => {
    const hour = new Date()
    hour.setUTCMinutes(0, 0, 0)
    const at = (offset: number) => new Date(hour.getTime() + offset * 3600 * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z')
    return {
      // Declared live: an undeclared timeline fails closed and publishes no hour,
      // which is asserted separately below.
      data_mode: 'live',
      start: '', end: '',
      items: [0, 3].map((offset) => ({ valid_time_utc: at(offset), valid_time_newfoundland: '', available_products: ['HRDPS'] })),
    }
  }

  it('activates a story card from the keyboard alone, with the readings in its accessible name', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: storyPoint(7), timeline: publishedTimeline() }))
    render(<App />)
    await openStory()

    // A real <button>, so it is reachable by Tab and fires on Enter without the
    // panel hand-rolling a key handler that could drift from the click path.
    const card = await screen.findByRole('button', { name: /^Scrub to \+3h\./ })
    expect(card).toHaveAccessibleName(/temperature 7 \u00b0C/)
    expect(card).toHaveAccessibleName(/dew point unknown/)
    expect(card).toHaveAttribute('aria-pressed', 'false')

    card.focus()
    expect(card).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    expect(card).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/\+3h \(Forecast\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
  })

  it('activates a story card with Space as well, having been tabbed to', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: storyPoint(7), timeline: publishedTimeline() }))
    render(<App />)
    await openStory()
    const card = await screen.findByRole('button', { name: /^Scrub to \+3h\./ })
    // Tab there rather than calling focus(): the point is that the card sits in
    // the natural focus order, which a div with tabIndex could fake but a
    // keyboard user could still never activate.
    for (let step = 0; step < 40 && document.activeElement !== card; step += 1) await userEvent.tab()
    expect(card).toHaveFocus()
    await userEvent.keyboard(' ')
    expect(card).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('station markers and live-source coverage', () => {
  it('says in the picker which stations have a live ingested source and which do not', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    expect(await screen.findByRole('option', { name: /CYYT.*live source/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /SmartAtlantic.*no live retrieval/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Cape Spear.*no ingested source/i })).toBeInTheDocument()
    expect(await screen.findByText(/A live ingested source stands behind 1 of 3 stations/i)).toBeInTheDocument()
  })

  it('shows coverage as unknown, never as live, when the status endpoint fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/sources/status')) return new Response('nope', { status: 503 })
      if (url.includes('/point')) return response(apiPoint())
      if (url.includes('/layers')) return response(emptyLayers)
      if (url.includes('/catalog')) return response(emptyCatalog)
      if (url.includes('/timeline')) return response(emptyTimeline)
      return response({})
    }))
    render(<App />)
    expect(await screen.findByText(/Live-source coverage unknown: source status returned 503/i)).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /live source/i })).not.toBeInTheDocument()
    expect(screen.getAllByRole('option', { name: /coverage unknown/i }).length).toBe(2)
  })
})

/** Two catalogue rows shaped as `/catalog` really returns them: no source is
 *  `active`, because the registry state is a ceiling that never reads active. */
const catalogWithModels = {
  data_mode: 'live',
  sources: [
    {
      id: 'eccc-hrdps', producer: 'Environment and Climate Change Canada', product: 'HRDPS raw', state: 'implementing',
      status_reason: 'Official product is catalogued; ingestion is not implemented yet.', role: 'Primary deterministic forecast',
      may_enter_consensus: true, cadence: '4 runs/day', forecast_horizon: 'approximately 48 h',
      geographic_coverage: 'Published native domain', licence: 'MSC Open Data licence', attribution: 'Credit ECCC',
    },
    {
      id: 'eccc-radar', producer: 'Environment and Climate Change Canada', product: 'Weather radar composite', state: 'implementing',
      status_reason: 'Catalogued; not yet ingested.', role: 'Observation',
      may_enter_consensus: false, cadence: '6 min', forecast_horizon: 'nowcast',
      geographic_coverage: 'Composite', licence: 'MSC Open Data licence', attribution: 'Credit ECCC',
    },
  ],
}

describe('product selection is reachable, not permanently disabled', () => {
  it('offers a model the point endpoint accepts even though no catalogue source is ever active', async () => {
    const fetchMock = routedFetch({ catalog: catalogWithModels })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const hrdps = await screen.findByRole('button', { name: /HRDPS/ })
    expect(hrdps).not.toBeDisabled()
    expect(hrdps).not.toHaveAttribute('aria-disabled', 'true')

    await userEvent.click(hrdps)
    // The token sent is the one `/point` declares, not the catalogue's prose
    // product name ("HRDPS raw"), which the endpoint answers 422 to.
    await waitFor(() => expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes('/point') && url.includes('product=HRDPS'))).toBe(true))
    expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes('product=HRDPS+raw'))).toBe(false)
  })

  it('renders no control for a catalogue source the endpoint has no product value for', async () => {
    vi.stubGlobal('fetch', routedFetch({ catalog: catalogWithModels }))
    render(<App />)
    await screen.findByRole('button', { name: /HRDPS/ })
    // A radar button could never be enabled by any response, so it is not an
    // affordance at all rather than a permanently disabled one.
    expect(screen.queryByRole('button', { name: /Weather radar composite/ })).not.toBeInTheDocument()
  })

  it('shows the API’s own reason when a selected product has nothing published', async () => {
    const noArtifact = {
      data_mode: 'unavailable',
      valid_time: '2026-08-29T15:00:00Z',
      selection: { mode: 'evidence_only', badge: 'evidence unavailable', reason: 'HRDPS has no published artifact covering this coordinate and time' },
      fields: [],
    }
    vi.stubGlobal('fetch', routedFetch({ catalog: catalogWithModels, point: noArtifact }))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: /HRDPS/ }))
    expect(await screen.findByText(/HRDPS has no published artifact covering this coordinate and time/i)).toBeInTheDocument()
  })
})

describe('timeline mode is applied like every other fetch', () => {
  const undeclaredTimeline = () => {
    const hour = new Date()
    hour.setUTCMinutes(0, 0, 0)
    const at = (offset: number) => new Date(hour.getTime() + offset * 3600 * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z')
    // No data_mode at all: the fail-closed case.
    return { start: '', end: '', items: [0, 3].map((offset) => ({ valid_time_utc: at(offset), valid_time_newfoundland: '', available_products: ['HRDPS'] })) }
  }

  it('does not present an undeclared timeline’s hours as published coverage', async () => {
    const fetchMock = routedFetch({
      point: apiPoint([{ field: 'temperature', value: 7, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } }]),
      timeline: undeclaredTimeline(),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await openStory()

    expect(await screen.findByText(/timeline declared no data_mode/i)).toBeInTheDocument()
    // No story card is built from hours the response never claimed.
    expect(screen.queryByRole('button', { name: /^Scrub to \+3h\./ })).not.toBeInTheDocument()
  })
})

/** The blended response as `/point` really returns it: the same field name
 *  once per contributing source, the METAR observation listed first, and a
 *  `selection` that names the source the API answered with. */
const blendedPoint = () => ({
  data_mode: 'live',
  latitude: 47.5615, longitude: -52.7126, valid_time: '2026-08-30T13:00:00Z',
  selection: { mode: 'fallback', selected_source_id: 'eccc-hrdps', selected_product_id: 'hrdps', badge: 'HRDPS primary - consensus unavailable', reason: 'minimum consensus evidence not met' },
  fields: [
    { field: 'temperature', value: 17.0, provenance: { source_id: 'awc-metar-speci', product: 'METAR/SPECI', provider: 'NOAA/NWS Aviation Weather Center', normalized_units: 'degC', data_mode: 'live' } },
    { field: 'visibility', value: 24140.16, provenance: { source_id: 'awc-metar-speci', product: 'METAR/SPECI', provider: 'NOAA/NWS Aviation Weather Center', normalized_units: 'm', data_mode: 'live' } },
    { field: 'total_cloud', value: 75, provenance: { source_id: 'awc-metar-speci', product: 'METAR/SPECI', provider: 'NOAA/NWS Aviation Weather Center', normalized_units: 'percent', data_mode: 'live' } },
    { field: 'mean_sea_level_pressure', value: 1013.7, provenance: { source_id: 'awc-metar-speci', product: 'METAR/SPECI', provider: 'NOAA/NWS Aviation Weather Center', normalized_units: 'hPa', data_mode: 'live' } },
    { field: 'temperature', value: 18.053, provenance: { source_id: 'eccc-hrdps', product: 'HRDPS raw', provider: 'Environment and Climate Change Canada', normalized_units: 'degC', data_mode: 'live' } },
    { field: 'wind_speed', value: 10, provenance: { source_id: 'eccc-hrdps', product: 'HRDPS raw', provider: 'Environment and Climate Change Canada', normalized_units: 'm s-1', derivation: 'MetPy wind_speed from u/v components', derivation_version: 'metpy-1.7.1-wind-v1', data_mode: 'live' } },
    { field: 'wind_direction', value: 240, provenance: { source_id: 'eccc-hrdps', product: 'HRDPS raw', provider: 'Environment and Climate Change Canada', normalized_units: 'degree', derivation: 'MetPy wind_direction from u/v components, meteorological convention (from)', derivation_version: 'metpy-1.7.1-wind-v1', data_mode: 'live' } },
    { field: 'mean_sea_level_pressure', value: 101383, provenance: { source_id: 'eccc-hrdps', product: 'HRDPS raw', provider: 'Environment and Climate Change Canada', normalized_units: 'Pa', data_mode: 'live' } },
    { field: 'relative_humidity', value: 79.5, provenance: { source_id: 'eccc-rdps', product: 'RDPS', provider: 'Environment and Climate Change Canada', normalized_units: 'percent', derivation: 'MetPy relative_humidity_from_dewpoint with explicit liquid-water phase', derivation_version: 'metpy-1.7.1-liquid-v1', data_mode: 'live' } },
  ],
})

const gfsStrataPoint = () => {
  const base = blendedPoint()
  const gfs = (field: string, value: number) => ({
    field, value,
    provenance: { source_id: 'noaa-gfs', product: 'GFS', provider: 'NOAA/NCEP', normalized_units: 'percent', data_mode: 'live' },
  })
  return { ...base, fields: [...base.fields, gfs('cloud_low', 0), gfs('cloud_middle', 33.70000076293945), gfs('cloud_high', 45.20000076293945)] }
}

describe('provider cloud strata render as whole percentages', () => {
  it('rounds each stratum and tags the metric with its source', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: gfsStrataPoint() }))
    render(<App />)
    const strata = () => screen.getByText('Cloud L / M / H').closest('.metric') as HTMLElement
    await screen.findByText('0% · 34% · 45%')
    expect(within(strata()).getByText('0% · 34% · 45%')).toBeInTheDocument()
    expect(within(strata()).queryByText(/33\.70000076293945/)).not.toBeInTheDocument()
    expect(within(strata()).getByText('noaa-gfs')).toBeInTheDocument()
  })
})

describe('point readings are attributed to the source that produced them', () => {
  it('shows the selected source\u2019s temperature on the blended response, tagged, with the API\u2019s own badge in the header', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: blendedPoint() }))
    render(<App />)
    // The hero is the HRDPS sample the selection names, not the METAR listed first.
    expect(await screen.findByText('18.1')).toBeInTheDocument()
    expect(screen.queryByText('17')).not.toBeInTheDocument()
    expect(within(document.querySelector('.hero-reading') as HTMLElement).getByText('eccc-hrdps')).toBeInTheDocument()
    expect(screen.getByText('HRDPS primary - consensus unavailable')).toBeInTheDocument()
  })

  it('converts visibility from the declared metres, and never prints the raw number under km', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: blendedPoint() }))
    render(<App />)
    expect(await screen.findByText('24.1 km')).toBeInTheDocument()
    expect(screen.queryByText(/24140/)).not.toBeInTheDocument()
  })

  it('gives total cloud its own metric and never fills the low stratum with it', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: blendedPoint() }))
    render(<App />)
    await screen.findByText('18.1')
    const total = screen.getByText('Total cloud').closest('.metric') as HTMLElement
    expect(within(total).getByText('75%')).toBeInTheDocument()
    expect(within(total).getByText('awc-metar-speci')).toBeInTheDocument()
    const strata = screen.getByText('Cloud L / M / H').closest('.metric') as HTMLElement
    expect(within(strata).getByText('Unknown')).toBeInTheDocument()
  })

  it('shows wind speed and the from-direction, disclosing the MetPy derivation', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: blendedPoint() }))
    render(<App />)
    const wind = (await screen.findByText('Wind / gust')).closest('.metric') as HTMLElement
    expect(within(wind).getByText('36 / Unknown')).toBeInTheDocument()
    expect(within(wind).getByText(/from 240°/)).toBeInTheDocument()
    expect(within(wind).getByText(/derived · MetPy/)).toBeInTheDocument()
    expect(within(wind).queryByText(/direction unavailable/)).not.toBeInTheDocument()
  })

  it('shows the derived-humidity chip and a pressure metric converted from the declared unit', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: blendedPoint() }))
    render(<App />)
    const humidity = (await screen.findByText('Humidity')).closest('.metric') as HTMLElement
    expect(within(humidity).getByText(/derived · MetPy/)).toBeInTheDocument()
    // The selected source (HRDPS) published Pa; it is shown as hPa, one decimal.
    const pressure = screen.getByText('MSLP').closest('.metric') as HTMLElement
    expect(within(pressure).getByText('1013.8 hPa')).toBeInTheDocument()
    expect(within(pressure).getByText('eccc-hrdps')).toBeInTheDocument()
  })

  it('lists each derivation in the provenance table', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: blendedPoint() }))
    render(<App />)
    await screen.findByText('18.1')
    await userEvent.click(screen.getByRole('button', { name: 'Workbench' }))
    const table = screen.getByRole('table', { name: 'Provenance returned for the selected point' })
    expect(within(table).getByRole('columnheader', { name: 'Derivation' })).toBeInTheDocument()
    expect(within(table).getByText(/relative_humidity_from_dewpoint/)).toBeInTheDocument()
  })

  it('moves the scrubber when a layer row asks to jump to its nearest frame', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    expect(screen.getByText(/^Now \(0h\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Jump to nearest frame' }))
    expect(screen.getByText(/\+3h \(Forecast\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
  })

  it('shows the true minute offset after a jump, and never rounds a nearby frame to Now', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    const badge = () => (document.querySelector('.story-scrubber-badge strong') as HTMLElement).textContent
    expect(badge()).toMatch(/^Now \(0h\) · .+ NT$/)
    // A radar frame ten minutes ago is not "Now": the badge used to round the
    // offset to the hour and claim an instant the reader had not chosen.
    await userEvent.click(screen.getByRole('button', { name: 'Jump ten minutes back' }))
    expect(badge()).toMatch(/^-10 min \(Past\)/)
    expect(screen.queryByText(/^Now \(0h\)/, { selector: '.story-scrubber-badge strong' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '10 min ago on the headland' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Jump eighty minutes ahead' }))
    expect(badge()).toMatch(/^\+1 h 20 min \(Forecast\)/)
  })
})

describe('model row states its own coverage', () => {
  const hour = new Date()
  hour.setUTCMinutes(0, 0, 0)
  const at = (offset: number) => new Date(hour.getTime() + offset * 3600 * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z')
  const catalogWithReps = {
    ...catalogWithModels,
    sources: [
      ...catalogWithModels.sources,
      {
        id: 'eccc-reps', producer: 'Environment and Climate Change Canada', product: 'REPS', state: 'implementing',
        status_reason: 'Official product is catalogued; ingestion is not implemented yet.', role: 'Regional ensemble',
        may_enter_consensus: true, cadence: '4 runs/day', forecast_horizon: '72 h',
        geographic_coverage: 'Published native domain', licence: 'MSC Open Data licence', attribution: 'Credit ECCC',
      },
    ],
  }
  const statusWithModels = {
    data_mode: 'mixed',
    statuses: [
      ...sourceStatus.statuses,
      { source_id: 'eccc-hrdps', state: 'implementing', data_mode: 'live', last_retrieval: '2026-08-30T12:13:06Z', detail: 'live retrieval recorded by the ingestion worker' },
      { source_id: 'eccc-reps', state: 'implementing', data_mode: 'unavailable', last_retrieval: null, detail: 'no live retrieval recorded' },
    ],
  }
  const timelineWithModels = {
    data_mode: 'live', start: '', end: '',
    items: [0, 3, 18].map((offset) => ({ valid_time_utc: at(offset), valid_time_newfoundland: '', available_products: ['eccc-hrdps'] })),
  }

  it('says how far this deployment\u2019s ingested hours reach, and that an unwired model has nothing ingested', async () => {
    vi.stubGlobal('fetch', routedFetch({ catalog: catalogWithReps, sources: statusWithModels, timeline: timelineWithModels }))
    render(<App />)
    // The newest published hour is +18 h from the top of the current hour, so
    // rounded from the session's real reference instant it reads +17 or +18.
    const hrdps = await screen.findByRole('button', { name: /HRDPS.*covers to \+1[78] h/ })
    expect(hrdps).toHaveAttribute('aria-pressed', 'false')
    // Registry prose moves to the tooltip, labelled for what it is.
    expect(hrdps).toHaveAttribute('title', expect.stringMatching(/approximately 48 h.*provider documentation, not verified here/))
    expect(within(hrdps).queryByText(/approximately 48 h/)).not.toBeInTheDocument()

    const reps = screen.getByRole('button', { name: /REPS.*nothing ingested/ })
    expect(reps).toHaveClass('model-unavailable')
    expect(reps).not.toBeDisabled()
    // No radiogroup any more: plain pressed buttons, no roving focus to hand-roll.
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    await userEvent.click(reps)
    expect(reps).toHaveAttribute('aria-pressed', 'true')
  })
})

/** The METAR fields `/point` serves for a two-layer report: the cover code is
 *  the retrieved meaning string, the base is metres (original feet), and the
 *  fog state is derived from the present-weather group and says so. */
const cloudLayerPoint = () => apiPoint([
  { field: 'cloud_layer_1_cover_code', value: 'BKN', provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'code', original_units: 'code', data_mode: 'live' } },
  { field: 'cloud_layer_1_cover', value: 75, provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'percent', data_mode: 'live' } },
  { field: 'cloud_layer_1_base', value: 4267.2, provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'm', original_units: 'ft', data_mode: 'live' } },
  { field: 'cloud_layer_2_cover_code', value: 'OVC', provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'code', data_mode: 'live' } },
  { field: 'cloud_layer_2_base', value: null, provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'm', original_units: 'ft', data_mode: 'live' } },
  { field: 'fog_state', value: 'evidence_present', provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'category', derivation: 'ingest.meteorology.fog_state from the METAR/TAF present-weather group', derivation_version: 'fog-state-present-weather-v1', data_mode: 'live' } },
])

describe('cloud layers and fog are shown as reported', () => {
  it('renders each reported layer in provider order with its base in metres, and leaves the strata Unknown', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: cloudLayerPoint() }))
    render(<App />)
    const layers = (await screen.findByText('Cloud layers')).closest('.metric') as HTMLElement
    expect(within(layers).getByText(/BKN · 4267 m/)).toBeInTheDocument()
    expect(within(layers).getByText(/OVC · base Unknown/)).toBeInTheDocument()
    expect(within(layers).getByText(/not bucketed into strata/)).toBeInTheDocument()
    expect(within(layers).getByText('awc-metar-speci')).toBeInTheDocument()
    // The layers never fill a stratum: no low/middle/high is derived from them.
    const strata = screen.getByText('Cloud L / M / H').closest('.metric') as HTMLElement
    expect(within(strata).getByText('Unknown')).toBeInTheDocument()
  })

  it('shows Unknown for the layers when no layer field was returned', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: apiPoint([{ field: 'temperature', value: 8, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } }]) }))
    render(<App />)
    await screen.findByText('8')
    const layers = screen.getByText('Cloud layers').closest('.metric') as HTMLElement
    expect(within(layers).getByText('Unknown')).toBeInTheDocument()
    expect(within(layers).getByText('No cloud layer returned')).toBeInTheDocument()
    expect(within(layers).queryByText(/awc-metar-speci/)).not.toBeInTheDocument()
  })

  it('gives fog its own metric, credited to the source that derived it', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: cloudLayerPoint() }))
    render(<App />)
    const fog = (await screen.findByText('Fog', { selector: '.metric > span' })).closest('.metric') as HTMLElement
    expect(within(fog).getByText('Fog evidence present')).toBeInTheDocument()
    expect(within(fog).getByText('awc-metar-speci')).toBeInTheDocument()
    expect(within(fog).getByText('derived from the present-weather group')).toBeInTheDocument()
  })

  it('credits no source for an unknown fog state', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: apiPoint([{ field: 'temperature', value: 8, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } }]) }))
    render(<App />)
    await screen.findByText('8')
    const fog = screen.getByText('Fog', { selector: '.metric > span' }).closest('.metric') as HTMLElement
    expect(within(fog).getByText('Fog evidence unknown')).toBeInTheDocument()
    expect(within(fog).queryByText(/HRDPS|ECCC/)).not.toBeInTheDocument()
  })
})

/** Four GOES-East proxies shaped as Agent A's `/layers` publishes them:
 *  `group: satellite`, ten-minute frames, all of them in the past. */
const satelliteLayers = () => {
  const now = Date.now()
  const past = (minutesAgo: number) => new Date(Math.floor((now - minutesAgo * 60_000) / 600_000) * 600_000).toISOString().replace(/\.\d{3}Z$/, 'Z')
  const times = [120, 60, 30, 20].map(past)
  const base = { kind: 'raster', product: 'GOES-East', units: 'unknown', cadence_seconds: 600, staleness_tolerance_seconds: 300, evidence_basis: 'live_proxy', raster_available: true, legend_available: false, group: 'satellite', times }
  return [
    { ...base, id: 'geomet-live-goes-east-dayvis-nightir', title: 'GOES-East day visible / night IR (1 km, live proxy)', field: 'satellite_day_visible_night_ir', semantics: 'observed imagery; frames exist only for the past; never forecast' },
    { ...base, id: 'geomet-live-goes-east-snowfog-nightmicro', title: 'GOES-East snow-fog / night microphysics (1 km, live proxy)', field: 'satellite_snow_fog_night_microphysics', semantics: 'observed imagery; never forecast' },
    { ...base, id: 'geomet-live-goes-east-naturalcolor', title: 'GOES-East natural color (1 km, live proxy)', field: 'satellite_natural_color', semantics: 'observed imagery; never forecast' },
    { ...base, id: 'geomet-live-goes-east-nightir-2km', title: 'GOES-East night IR (2 km, live proxy)', field: 'satellite_night_ir', semantics: 'observed imagery; never forecast' },
  ]
}

describe('timeline coverage rows are grouped like the drawer', () => {
  it('heads each non-empty group in the shared order, satellite first with its past-only note', async () => {
    const hrdps = { id: 'geomet-live-hrdps-tt', title: 'HRDPS air temperature (live proxy)', kind: 'raster', field: 'air_temperature', product: 'HRDPS', units: 'degC', semantics: 'live-proxied imagery', times: [], evidence_basis: 'live_proxy', raster_available: true, group: 'forecast_proxy' }
    const radar = { id: 'eccc-radar-radar', title: 'eccc-radar radar', kind: 'point', field: 'radar', product: 'radar', units: 'mixed', semantics: 'No echo means no detected precipitating echo, not clear sky.', times: [], group: 'observation' }
    vi.stubGlobal('fetch', routedFetch({ layers: { data_mode: 'live', layers: [hrdps, radar, ...satelliteLayers()], notices: [] } }))
    render(<App />)
    await openStory()

    const ribbon = await screen.findByLabelText('Published frames per layer across the window')
    const headings = within(ribbon).getAllByRole('heading', { level: 4 }).map((heading) => heading.textContent)
    expect(headings).toEqual(['Satellite (observed, past only) · 4 layers', 'Observations · 1 layer', 'Forecast · live proxy · 1 layer'])
    const satellite = within(ribbon).getByRole('group', { name: 'Satellite (observed, past only) · 4 layers' })
    expect(within(satellite).getAllByRole('button')).toHaveLength(4)
    expect(within(satellite).getByRole('button', { name: 'GOES-East natural color (1 km, live proxy)' })).toHaveAttribute('aria-pressed', 'false')
    expect(within(satellite).getByText('observed imagery: frames exist only for the past')).toBeInTheDocument()
    // The note is a claim about satellite imagery only; no other group makes it.
    expect(within(ribbon).getAllByText('observed imagery: frames exist only for the past')).toHaveLength(1)
    // Row semantics are untouched: the label still toggles the layer.
    await userEvent.click(within(satellite).getByRole('button', { name: 'GOES-East natural color (1 km, live proxy)' }))
    expect(within(satellite).getByRole('button', { name: 'GOES-East natural color (1 km, live proxy)' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('says a satellite row has no frame at a forward hour rather than reusing a past one', async () => {
    vi.stubGlobal('fetch', routedFetch({ layers: { data_mode: 'live', layers: satelliteLayers(), notices: [] } }))
    render(<App />)
    await openStory()
    const ribbon = await screen.findByLabelText('Published frames per layer across the window')
    await userEvent.click(screen.getByRole('button', { name: '+3h' }))
    const counts = within(ribbon).getAllByText('no frame here')
    expect(counts).toHaveLength(4)
  })

  it('files the rendered cloud mask beside the four proxies in the same satellite group', async () => {
    // The GOES-19 cloud mask this experiment renders itself: published
    // artifact, observed 10-minute scans, standing NEXT TO the untouched
    // provider composites so the two views can be compared side by side.
    const cloudMask = {
      id: 'noaa-goes19-cloud-mask',
      title: 'GOES-19 observed clouds (cloud mask)',
      kind: 'raster',
      field: 'cloud_mask',
      product: 'GOES-19 ABI L2 Enterprise Cloud Mask (ACMF Full Disk) + Cloud Top Height (ACHAF)',
      units: 'cloud-mask class / probability 0-1',
      semantics: 'rendered by this experiment from the retrieved NOAA GOES-19 Enterprise Cloud Mask; opacity encodes detection confidence, never a definitive statement of clear sky',
      times: satelliteLayers()[0].times,
      cadence_seconds: 600,
      staleness_tolerance_seconds: 1800,
      evidence_basis: 'published_artifact',
      raster_available: true,
      legend_available: true,
      group: 'satellite',
    }
    vi.stubGlobal('fetch', routedFetch({ layers: { data_mode: 'live', layers: [...satelliteLayers(), cloudMask], notices: [] } }))
    render(<App />)
    await openStory()
    const ribbon = await screen.findByLabelText('Published frames per layer across the window')
    const satellite = within(ribbon).getByRole('group', { name: 'Satellite (observed, past only) · 5 layers' })
    expect(within(satellite).getAllByRole('button')).toHaveLength(5)
    expect(within(satellite).getByRole('button', { name: 'GOES-19 observed clouds (cloud mask)' })).toBeInTheDocument()
    expect(within(satellite).getByRole('button', { name: 'GOES-East natural color (1 km, live proxy)' })).toBeInTheDocument()
  })
})

describe('rendered-grid coverage rows', () => {
  it('heads the three GFS strata layers under the rendered-grid group in the ribbon', async () => {
    const times = ['2026-08-30T13:00:00Z', '2026-08-30T14:00:00Z']
    const base = { kind: 'raster', product: 'Global Forecast System (GFS 0.25 deg)', units: 'percent', semantics: 'rendered by this experiment from retrieved NOAA GFS GRIB2 fields; never smoothed', cadence_seconds: 3600, staleness_tolerance_seconds: 1800, evidence_basis: 'published_artifact', raster_available: true, legend_available: true, group: 'rendered_grid', times }
    const strata = [
      { ...base, id: 'noaa-gfs-surface-cloud-low', title: 'Global Forecast System (GFS 0.25 deg) low cloud cover (rendered grid)', field: 'cloud_low' },
      { ...base, id: 'noaa-gfs-surface-cloud-middle', title: 'Global Forecast System (GFS 0.25 deg) middle cloud cover (rendered grid)', field: 'cloud_middle' },
      { ...base, id: 'noaa-gfs-surface-cloud-high', title: 'Global Forecast System (GFS 0.25 deg) high cloud cover (rendered grid)', field: 'cloud_high' },
    ]
    vi.stubGlobal('fetch', routedFetch({ layers: { data_mode: 'live', layers: strata, notices: [] } }))
    render(<App />)
    await openStory()

    const ribbon = await screen.findByLabelText('Published frames per layer across the window')
    const group = within(ribbon).getByRole('group', { name: 'Rendered grids (drawn here from stored model data) · 3 layers' })
    expect(within(group).getAllByRole('button')).toHaveLength(3)
    // The rows toggle like any other layer.
    await userEvent.click(within(group).getByRole('button', { name: /low cloud cover/ }))
    expect(within(group).getByRole('button', { name: /low cloud cover/ })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('model row is grouped by producer', () => {
  const catalogTwoProducers = {
    data_mode: 'live',
    sources: [
      ...catalogWithModels.sources,
      {
        id: 'noaa-gfs', producer: 'NOAA', product: 'GFS', state: 'implementing',
        status_reason: 'Catalogued.', role: 'Global deterministic forecast',
        may_enter_consensus: true, cadence: '4 runs/day', forecast_horizon: '384 h',
        geographic_coverage: 'Global', licence: 'US public domain', attribution: 'Credit NOAA',
      },
      {
        id: 'eccc-reps', producer: 'Environment and Climate Change Canada', product: 'REPS', state: 'implementing',
        status_reason: 'Catalogued.', role: 'Regional ensemble',
        may_enter_consensus: true, cadence: '4 runs/day', forecast_horizon: '72 h',
        geographic_coverage: 'Published native domain', licence: 'MSC Open Data licence', attribution: 'Credit ECCC',
      },
    ],
  }

  it('labels each producer once, keeps BLEND first and ungrouped, and keeps catalogue order inside a group', async () => {
    vi.stubGlobal('fetch', routedFetch({ catalog: catalogTwoProducers }))
    render(<App />)
    await screen.findByRole('button', { name: /GFS/ })
    const strip = screen.getByLabelText('Select forecast model')
    const buttons = within(strip).getAllByRole('button').map((button) => button.textContent)
    expect(buttons[0]).toMatch(/^BLENDConsensus/)
    expect(buttons.map((text) => text?.replace(/^.*?(HRDPS|REPS|GFS|Consensus).*$/, '$1'))).toEqual(['Consensus', 'HRDPS', 'REPS', 'GFS'])
    // One label per producer, in catalogue order.
    const labels = [...strip.querySelectorAll('.model-group-label')].map((label) => label.textContent)
    expect(labels).toEqual(['Environment and Climate Change Canada', 'NOAA'])
    const eccc = within(strip).getByRole('group', { name: 'Environment and Climate Change Canada' })
    expect(within(eccc).getAllByRole('button')).toHaveLength(2)
    expect(within(within(strip).getByRole('group', { name: 'NOAA' })).getByRole('button', { name: /GFS/ })).toBeInTheDocument()
    // BLEND is outside every producer group.
    expect(screen.getByRole('button', { name: /BLEND/ }).closest('.model-group')).toBeNull()
    // Selection still works through the group.
    await userEvent.click(within(eccc).getByRole('button', { name: /REPS/ }))
    expect(within(eccc).getByRole('button', { name: /REPS/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /BLEND/ })).toHaveAttribute('aria-pressed', 'false')
  })
})

describe('station picker is grouped by live-source coverage', () => {
  const picker = () => document.querySelector('.station-picker select') as HTMLSelectElement

  it('puts live stations under one optgroup and places to query under another', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    await screen.findByRole('option', { name: /CYYT.*live source/i })
    const groups = within(picker()).getAllByRole('group').map((group) => (group as HTMLOptGroupElement).label)
    expect(groups).toEqual(['Live ingested source', 'No ingested source (place to query)'])
    const live = within(picker()).getByRole('group', { name: 'Live ingested source' })
    expect(within(live).getAllByRole('option')).toHaveLength(1)
    expect(within(live).getByRole('option', { name: /CYYT/ })).toBeInTheDocument()
    const query = within(picker()).getByRole('group', { name: 'No ingested source (place to query)' })
    expect(within(query).getByRole('option', { name: /SmartAtlantic.*no live retrieval/i })).toBeInTheDocument()
    expect(within(query).getByRole('option', { name: /Cape Spear.*no ingested source/i })).toBeInTheDocument()
    // The placeholder stays outside every group and stays disabled.
    expect(screen.getByRole('option', { name: 'Custom map point' }).closest('optgroup')).toBeNull()
    expect(screen.getByRole('option', { name: 'Custom map point' })).toBeDisabled()
    // Choosing through a group still selects the station.
    await userEvent.selectOptions(picker(), 'cape-spear')
    expect(screen.getByRole('heading', { name: 'Cape Spear' })).toBeInTheDocument()
  })

  it('never files an unknown-coverage station under the live group when status cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/sources/status')) return new Response('nope', { status: 503 })
      if (url.includes('/point')) return response(apiPoint())
      if (url.includes('/layers')) return response(emptyLayers)
      if (url.includes('/catalog')) return response(emptyCatalog)
      if (url.includes('/timeline')) return response(emptyTimeline)
      return response({})
    }))
    render(<App />)
    await screen.findByText(/Live-source coverage unknown: source status returned 503/i)
    const groups = within(picker()).getAllByRole('group').map((group) => (group as HTMLOptGroupElement).label)
    expect(groups).toEqual(['Live-source coverage unknown', 'No ingested source (place to query)'])
    expect(within(picker()).queryByRole('group', { name: 'Live ingested source' })).not.toBeInTheDocument()
  })
})

/** Today's CYYT report as `/point` serves it (FEW020 BKN130): FEW at 609.6 m
 *  and BKN at 3,962.4 m, both declared in metres. */
const fewBknPoint = (extra: unknown[] = []) => apiPoint([
  { field: 'cloud_layer_1_cover_code', value: 'FEW', provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'code', data_mode: 'live' } },
  { field: 'cloud_layer_1_cover', value: 25, provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'percent', data_mode: 'live' } },
  { field: 'cloud_layer_1_base', value: 609.6, provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'm', original_units: 'ft', data_mode: 'live' } },
  { field: 'cloud_layer_2_cover_code', value: 'BKN', provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'code', data_mode: 'live' } },
  { field: 'cloud_layer_2_cover', value: 75, provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'percent', data_mode: 'live' } },
  { field: 'cloud_layer_2_base', value: 3962.4, provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'm', original_units: 'ft', data_mode: 'live' } },
  ...extra,
])

describe('cloud band filter is a view filter over the as-reported layers', () => {
  const bandButton = (name: RegExp) => screen.getByRole('button', { name })
  const cloudMetric = () => screen.getByText('Cloud layers').closest('.metric') as HTMLElement
  const strataMetric = () => screen.getByText('Cloud L / M / H').closest('.metric') as HTMLElement

  it('offers three pressed band buttons naming their bounds, all on, showing the full list', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: fewBknPoint() }))
    render(<App />)
    const metric = (await screen.findByText('Cloud layers')).closest('.metric') as HTMLElement
    const group = within(metric).getByRole('group', { name: 'Cloud layer bands' })
    const buttons = within(group).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual(['Low · <6,500 ft', 'Middle · 6,500–20,000 ft', 'High · ≥20,000 ft'])
    buttons.forEach((button) => expect(button).toHaveAttribute('aria-pressed', 'true'))
    expect(within(metric).getByText(/FEW · 610 m \| BKN · 3962 m/)).toBeInTheDocument()
    expect(within(metric).getByText(/not bucketed into strata/)).toBeInTheDocument()
    expect(within(metric).queryByText(/reported layers shown/)).not.toBeInTheDocument()
  })

  it('turning Low off leaves only BKN and says 1 of 2 reported layers shown, and back on restores the list', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: fewBknPoint() }))
    render(<App />)
    await screen.findByText(/FEW · 610 m/)
    await userEvent.click(bandButton(/^Low ·/))
    expect(bandButton(/^Low ·/)).toHaveAttribute('aria-pressed', 'false')
    expect(within(cloudMetric()).queryByText(/FEW/)).not.toBeInTheDocument()
    expect(within(cloudMetric()).getByText('BKN · 3962 m')).toBeInTheDocument()
    expect(within(cloudMetric()).getByText('1 of 2 reported layers shown · view filter, not a classification')).toBeInTheDocument()
    // The source tag stays on the metric: the list is still METAR's.
    expect(within(cloudMetric()).getByText('awc-metar-speci')).toBeInTheDocument()
    // The strata metric is untouched by the filter: nothing was derived.
    expect(within(strataMetric()).getByText('Unknown')).toBeInTheDocument()
    expect(within(strataMetric()).getByText('No cloud strata returned')).toBeInTheDocument()

    await userEvent.click(bandButton(/^Low ·/))
    expect(bandButton(/^Low ·/)).toHaveAttribute('aria-pressed', 'true')
    expect(within(cloudMetric()).getByText(/FEW · 610 m \| BKN · 3962 m/)).toBeInTheDocument()
    expect(within(cloudMetric()).getByText(/not bucketed into strata/)).toBeInTheDocument()
  })

  it('turning Middle off hides BKN instead, and every band off shows no layer without calling it Unknown', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: fewBknPoint() }))
    render(<App />)
    await screen.findByText(/FEW · 610 m/)
    await userEvent.click(bandButton(/^Middle ·/))
    expect(within(cloudMetric()).getByText('FEW · 610 m')).toBeInTheDocument()
    expect(within(cloudMetric()).queryByText(/BKN/)).not.toBeInTheDocument()
    await userEvent.click(bandButton(/^Low ·/))
    await userEvent.click(bandButton(/^High ·/))
    expect(within(cloudMetric()).getByText('No reported layer in the bands left on')).toBeInTheDocument()
    expect(within(cloudMetric()).getByText('0 of 2 reported layers shown · view filter, not a classification')).toBeInTheDocument()
    expect(within(cloudMetric()).queryByText('Unknown')).not.toBeInTheDocument()
  })

  it('never hides a layer whose base is unknown, and says it is not filterable', async () => {
    const ovcNoBase = [
      { field: 'cloud_layer_3_cover_code', value: 'OVC', provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'code', data_mode: 'live' } },
      { field: 'cloud_layer_3_base', value: null, provenance: { source_id: 'awc-metar-speci', product: 'CYYT METAR/SPECI', provider: 'Aviation Weather Center / NAV CANADA', normalized_units: 'm', original_units: 'ft', data_mode: 'live' } },
    ]
    vi.stubGlobal('fetch', routedFetch({ point: fewBknPoint(ovcNoBase) }))
    render(<App />)
    await screen.findByText(/FEW · 610 m/)
    expect(within(cloudMetric()).getByText(/OVC · base Unknown — not filterable/)).toBeInTheDocument()
    await userEvent.click(bandButton(/^Low ·/))
    await userEvent.click(bandButton(/^Middle ·/))
    await userEvent.click(bandButton(/^High ·/))
    expect(within(cloudMetric()).getByText('OVC · base Unknown — not filterable')).toBeInTheDocument()
    expect(within(cloudMetric()).getByText('1 of 3 reported layers shown · view filter, not a classification')).toBeInTheDocument()
  })

  it('offers no band buttons when no layer was returned', async () => {
    vi.stubGlobal('fetch', routedFetch({ point: apiPoint([{ field: 'temperature', value: 8, provenance: { provider: 'ECCC', product: 'HRDPS', data_mode: 'live' } }]) }))
    render(<App />)
    await screen.findByText('8')
    expect(screen.queryByRole('group', { name: 'Cloud layer bands' })).not.toBeInTheDocument()
    expect(within(cloudMetric()).getByText('Unknown')).toBeInTheDocument()
  })
})

describe('observations stay visible under a selected model', () => {
  it('shows METAR-tagged observation metrics beside HRDPS-tagged model metrics when HRDPS is selected', async () => {
    const hrdpsWithMetar = {
      data_mode: 'live',
      latitude: 47.5615, longitude: -52.7126, valid_time: '2026-08-30T13:00:00Z',
      selection: { mode: 'fallback', selected_source_id: 'eccc-hrdps', selected_product_id: 'hrdps', badge: 'HRDPS selected model', reason: 'product requested' },
      fields: [
        { field: 'temperature', value: 18.053, provenance: { source_id: 'eccc-hrdps', product: 'HRDPS raw', provider: 'Environment and Climate Change Canada', normalized_units: 'degC', data_mode: 'live' } },
        { field: 'relative_humidity', value: 79.5, provenance: { source_id: 'eccc-hrdps', product: 'HRDPS raw', provider: 'Environment and Climate Change Canada', normalized_units: 'percent', data_mode: 'live' } },
        { field: 'visibility', value: 24140.16, provenance: { source_id: 'awc-metar-speci', product: 'METAR/SPECI', provider: 'NOAA/NWS Aviation Weather Center', normalized_units: 'm', data_mode: 'live' } },
        { field: 'fog_state', value: 'not_indicated', provenance: { source_id: 'awc-metar-speci', product: 'METAR/SPECI', provider: 'NOAA/NWS Aviation Weather Center', normalized_units: 'category', data_mode: 'live' } },
        ...(fewBknPoint().fields as unknown[]),
      ],
    }
    const fetchMock = routedFetch({ catalog: catalogWithModels, point: hrdpsWithMetar })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /HRDPS/ }))
    await waitFor(() => expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes('product=HRDPS'))).toBe(true))

    // Header names the model; the hero and humidity are the model's.
    expect(await screen.findByText('HRDPS selected model')).toBeInTheDocument()
    expect(within(document.querySelector('.hero-reading') as HTMLElement).getByText('eccc-hrdps')).toBeInTheDocument()
    expect(within(screen.getByText('Humidity').closest('.metric') as HTMLElement).getByText('eccc-hrdps')).toBeInTheDocument()
    // The observations survive the selection, each under its own tag.
    const visibility = screen.getByText('Visibility').closest('.metric') as HTMLElement
    expect(within(visibility).getByText('24.1 km')).toBeInTheDocument()
    expect(within(visibility).getByText('awc-metar-speci')).toBeInTheDocument()
    const fog = screen.getByText('Fog', { selector: '.metric > span' }).closest('.metric') as HTMLElement
    expect(within(fog).getByText('Fog not indicated by available evidence')).toBeInTheDocument()
    expect(within(fog).getByText('awc-metar-speci')).toBeInTheDocument()
    const clouds = screen.getByText('Cloud layers').closest('.metric') as HTMLElement
    expect(within(clouds).getByText(/FEW · 610 m/)).toBeInTheDocument()
    expect(within(clouds).getByText('awc-metar-speci')).toBeInTheDocument()
    // Nothing is borrowed: no HRDPS tag lands on an observation metric.
    expect(within(visibility).queryByText('eccc-hrdps')).not.toBeInTheDocument()
    expect(within(clouds).queryByText('eccc-hrdps')).not.toBeInTheDocument()
  })
})

describe('computed astronomy bands and Tonight cards', () => {
  it('renders darkness and moon bands with text alternatives naming the intervals', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    await openStory()
    const darkness = await screen.findByRole('img', { name: /Darkness: .*night/ })
    expect(darkness).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Moon above the horizon: moon up/ })).toBeInTheDocument()
    // The Tonight cards state the computed facts and the geometry-only caption.
    expect(screen.getByText('Astronomical darkness')).toBeInTheDocument()
    expect(screen.getByText(/92% illuminated, waning/)).toBeInTheDocument()
    expect(screen.getByText('No geometric window')).toBeInTheDocument()
    expect(screen.getByText(/says nothing about cloud, transparency, or light pollution/)).toBeInTheDocument()
  })

  it('says the bands are unavailable instead of drawing an empty band when astronomy fails closed', async () => {
    vi.stubGlobal('fetch', routedFetch({
      astronomy: { data_mode: 'unavailable', twilight_bands: [], notices: ['Pinned ephemeris missing: /data/ephemeris/de442.bsp'], provenance: null },
    }))
    render(<App />)
    await openStory()
    expect(await screen.findByText(/Darkness and moon bands unavailable: Pinned ephemeris missing/)).toBeInTheDocument()
    expect(screen.getByText(/No band is drawn from a failure/)).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /Darkness:/ })).not.toBeInTheDocument()
  })
})

describe('space weather cards: Kp and Bz, fail-closed', () => {
  it('renders the latest observed Kp, the windowed forecast max with its provider status, and Bz with its instant', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    expect(await screen.findByText('Kp observed')).toBeInTheDocument()
    expect(screen.getByText('4.33')).toBeInTheDocument()
    // The forecast max is the largest value INSIDE the 28-hour window (5.0,
    // predicted) — the 7.0 two days out never stands in for it — and the
    // provider's own status label rides the caption.
    expect(screen.getByText('Kp forecast max')).toBeInTheDocument()
    expect(screen.getByText('5.00')).toBeInTheDocument()
    expect(screen.getByText(/provider status: predicted/)).toBeInTheDocument()
    expect(screen.getByText(/photographable at St. John's from about Kp 4-5/)).toBeInTheDocument()
    expect(screen.getByText('-4.1 nT')).toBeInTheDocument()
    expect(screen.getByText(/southward \(negative\) Bz is the aurora tripwire/)).toBeInTheDocument()
    // Planetary indices, never local readings: the section says so.
    expect(screen.getByText(/planetary indices, not local readings/)).toBeInTheDocument()
  })

  it('says space weather is unavailable, with the API reason, instead of showing a quiet zero', async () => {
    vi.stubGlobal('fetch', routedFetch({
      spaceWeather: {
        data_mode: 'unavailable', operational: false, generated_at: '2026-08-31T02:00:00Z',
        kp_observed: { available: false, source_id: 'noaa-swpc-kp', product: 'unavailable', readings: [], freshness: { status: 'unknown', age_seconds: null, threshold_seconds: 21600 }, notices: [] },
        kp_forecast: { available: false, source_id: 'noaa-swpc-kp', product: 'unavailable', readings: [], freshness: { status: 'unknown', age_seconds: null, threshold_seconds: 21600 }, notices: [] },
        solar_wind: { available: false, source_id: 'noaa-swpc-rtsw', product: 'unavailable', bz_gsm_nt: null, bt_nt: null, measured_at: null, feed_declared_spacecraft: null, freshness: { status: 'unknown', age_seconds: null, threshold_seconds: 900 }, notices: [] },
        notices: ['no fixture space weather exists; fixture mode answers unavailable rather than inventing planetary indices'],
      },
    }))
    render(<App />)
    expect(await screen.findByText(/Space weather unavailable: no fixture space weather exists/)).toBeInTheDocument()
    expect(screen.queryByText('Kp observed')).not.toBeInTheDocument()
    expect(screen.queryByText(/0\.0 nT/)).not.toBeInTheDocument()
  })

  it('marks a stale Bz as stale with its age rather than presenting it as current', async () => {
    const staleWind = {
      ...liveSpaceWeather,
      solar_wind: {
        ...liveSpaceWeather.solar_wind,
        measured_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
        freshness: { status: 'stale', age_seconds: 7200, threshold_seconds: 900 },
        notices: ['solar_wind: the newest Bz record is 7200 s old, past the 900 s freshness threshold; it is served stale, not as current'],
      },
    }
    vi.stubGlobal('fetch', routedFetch({ spaceWeather: staleWind }))
    render(<App />)
    expect(await screen.findByText('-4.1 nT')).toBeInTheDocument()
    expect(screen.getByText(/stale, 2\.0 h old/)).toBeInTheDocument()
  })
})

describe('timeline dock: interpolation setting and frame snapping', () => {
  // The playback tests replace requestAnimationFrame; restore it (and the
  // fetch stub each test sets for itself) so no stub leaks into the next.
  afterEach(() => vi.unstubAllGlobals())

  /** One toggleable layer with two published frames inside the past window,
   *  minute-aligned but at instants a 5-minute scrub could never land on. */
  const snappableLayers = () => {
    const at = (minutesAgo: number) => {
      const stamp = new Date(Date.now() - minutesAgo * 60_000)
      stamp.setUTCSeconds(0, 0)
      return stamp.toISOString().replace(/\.\d{3}Z$/, 'Z')
    }
    return {
      data_mode: 'live',
      layers: [{
        id: 'eccc-radar-radar', title: 'eccc-radar radar', kind: 'point', field: 'radar', product: 'radar',
        units: 'mixed', semantics: 'No echo means no detected precipitating echo, not clear sky.',
        times: [at(66), at(36)], cadence_seconds: 1800, staleness_tolerance_seconds: 900, group: 'observation',
      }],
      notices: [],
    }
  }

  it('offers interpolation off by default, worded as display-only', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    const toggle = await screen.findByRole('button', { name: /Interpolate forecast · display only/ })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    // The disclosure travels with the control itself.
    expect(toggle).toHaveAttribute('title', expect.stringMatching(/for display .*Never applied to observed layers; not evidence/))
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
  })

  it('snaps keyboard scrubbing to the exact published frame instants of the active layers', async () => {
    vi.stubGlobal('fetch', routedFetch({ layers: snappableLayers() }))
    render(<App />)
    await openStory()
    // Toggle the layer on through its coverage-ribbon row.
    await userEvent.click(await screen.findByRole('button', { name: 'eccc-radar radar' }))

    const slider = screen.getByLabelText('Valid timeline scrubber')
    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    // The selection lands on the newer frame's exact instant: ~36 minutes ago,
    // an offset no 5-minute step could produce.
    expect(screen.getByText(/-3[67] min \(Past\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
    expect(slider).toHaveAttribute('aria-valuetext', expect.stringMatching(/snapped to the nearest published frame/))

    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    expect(screen.getByText(/-1 h [67] min \(Past\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
    // At the axis end the selection stays put rather than inventing an instant.
    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    expect(screen.getByText(/-1 h [67] min \(Past\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
  })

  it('scrubs freely in five-minute steps when nothing active publishes frames', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    const slider = await screen.findByLabelText('Valid timeline scrubber')
    fireEvent.keyDown(slider, { key: 'ArrowRight' })
    expect(screen.getByText(/\+5 min \(Forecast\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
    expect(slider).toHaveAttribute('aria-valuetext', expect.not.stringMatching(/snapped/))
  })

  /** A hand-driven animation clock. The transport integrates the gap between
   *  successive frames, so the test decides how much wall time passed. */
  function driveFrames() {
    let pending: FrameRequestCallback | null = null
    let next = 0
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { pending = callback; return ++next })
    vi.stubGlobal('cancelAnimationFrame', () => { pending = null })
    return async (now: number) => {
      const callback = pending
      pending = null
      if (callback) await act(async () => { callback(now) })
    }
  }

  it('plays the timeline forward at the speed on the ladder, and pauses where it stopped', async () => {
    const frame = driveFrames()
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    const play = await screen.findByRole('button', { name: 'Play' })
    expect(screen.getByText('1 min/s')).toBeInTheDocument()
    await userEvent.click(play)

    // The first frame only establishes the clock; the second advances by the
    // two seconds between them: two weather minutes at the first speed.
    await frame(1000)
    await frame(3000)
    expect(screen.getByText(/\+2 min \(Forecast\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }))
    await frame(9000)
    expect(screen.getByText(/\+2 min \(Forecast\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
  })

  it('doubles and halves the speed within the ladder, clamping at both ends', async () => {
    const frame = driveFrames()
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    const faster = await screen.findByRole('button', { name: 'Faster' })
    const slower = screen.getByRole('button', { name: 'Slower' })
    expect(slower).toBeDisabled()

    await userEvent.click(faster)
    await userEvent.click(faster)
    expect(screen.getByText('4 min/s')).toBeInTheDocument()
    expect(slower).toBeEnabled()

    await userEvent.click(screen.getByRole('button', { name: 'Play' }))
    await frame(1000)
    await frame(2000)
    expect(screen.getByText(/\+4 min \(Forecast\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()

    for (let press = 0; press < 5; press += 1) await userEvent.click(faster)
    expect(screen.getByText('32 min/s')).toBeInTheDocument()
    expect(faster).toBeDisabled()
  })

  it('runs backwards under reverse without losing the chosen speed', async () => {
    const frame = driveFrames()
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    const reverse = await screen.findByRole('button', { name: 'Reverse' })
    await userEvent.click(screen.getByRole('button', { name: 'Faster' }))
    await userEvent.click(reverse)
    expect(reverse).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('◀ 2 min/s')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Play' }))
    await frame(1000)
    await frame(4000)
    expect(screen.getByText(/-6 min \(Past\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
  })

  it('stops playing the moment a hand touches the timeline', async () => {
    const frame = driveFrames()
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Play' }))
    await frame(1000)
    await frame(2000)

    fireEvent.keyDown(screen.getByLabelText('Valid timeline scrubber'), { key: 'ArrowRight' })
    expect(screen.getByRole('button', { name: 'Play' })).toHaveAttribute('aria-pressed', 'false')
    const badge = screen.getByText(/min \(Forecast\)/, { selector: '.story-scrubber-badge strong' }).textContent
    await frame(9000)
    expect(screen.getByText(/min \(Forecast\)/, { selector: '.story-scrubber-badge strong' })).toHaveTextContent(String(badge))
  })

  it('marks every published frame of the active layers and jumps to the one clicked', async () => {
    vi.stubGlobal('fetch', routedFetch({ layers: snappableLayers() }))
    render(<App />)
    await openStory()
    await userEvent.click(await screen.findByRole('button', { name: 'eccc-radar radar' }))

    // Two published frames, two ticks — and the key names the layer they
    // belong to. Nothing marks an instant the layer did not publish.
    const ticks = await screen.findAllByRole('button', { name: /^Published frame — eccc-radar radar,/ })
    expect(ticks).toHaveLength(2)
    expect(document.querySelectorAll('.marker-key-entry')).toHaveLength(1)

    await userEvent.click(ticks[1])
    expect(screen.getByText(/-3[67] min \(Past\)/, { selector: '.story-scrubber-badge strong' })).toBeInTheDocument()
  })

  it('says so plainly when the active layers publish no frame axis', async () => {
    const axisless = {
      data_mode: 'live',
      layers: [{
        id: 'eccc-alerts-alerts', title: 'eccc-alerts alerts', kind: 'point', field: 'alerts', product: 'alerts',
        units: 'mixed', semantics: 'Alerts as issued.', group: 'alert',
      }],
      notices: [],
    }
    vi.stubGlobal('fetch', routedFetch({ layers: axisless }))
    render(<App />)
    await openStory()
    await userEvent.click(await screen.findByRole('button', { name: 'eccc-alerts alerts' }))

    expect(screen.queryAllByRole('button', { name: /^Published frame/ })).toHaveLength(0)
    expect(screen.getByText(/No published frame axis: eccc-alerts alerts/)).toBeInTheDocument()
  })

  it('opens the story panel from the dock and returns focus to the toggle on Escape', async () => {
    vi.stubGlobal('fetch', routedFetch({}))
    render(<App />)
    const toggle = await screen.findByRole('button', { name: /Weather story/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const flyout = document.getElementById('story-flyout') as HTMLElement
    expect(flyout).toHaveFocus()
    fireEvent.keyDown(flyout, { key: 'Escape' })
    expect(document.getElementById('story-flyout')).toBeNull()
    expect(toggle).toHaveFocus()
  })
})
