import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { normalizePoint, loadAstronomy, loadPoint } from '../api'
import { SkyView } from './SkyView'
import type { RegisteredSite } from './registeredSites'
const at = '2026-09-07T12:00:00.000Z'
const registered: RegisteredSite = { id: 'signal-hill', name: 'Signal Hill', latitude: 47.5704, longitude: -52.6816, elevation_m: 140, datum: 'Registered datum', registered_on: '2026-09-03', registered_by: 'Fixture', geometry_note: 'Hand registered, not surveyed', horizon: { site_id: 'signal-hill', bearing_resolution_deg: 90, elevation_deg: [-1, 2, 0, 4], terrain_check_status: 'not_run', terrain_check_note: 'Awaiting terrain verification' } }
const fields = normalizePoint({ selection: { mode: 'evidence_only', badge: 'Evidence' }, data_mode: 'live', valid_time: at, fields: [{ field: 'cloud_low', key: 'cloud_low', family: 'cloud_cover', value: 0, provenance: { source_id: 'noaa-gfs', normalized_units: '%', evidence_class: 'retrieved', data_mode: 'live', valid_time: at } }] }).servedFields
function view(site: RegisteredSite | null = null) { return <SkyView site={site} registryVersion={'a'.repeat(64)} fields={fields} astronomy={null} astronomyNotice="Missing kernel" spaceWeather={null} spaceWeatherNotice="No feed" cameras={null} cameraNotice="No registry" onInspect={vi.fn()} /> }
it('uses only explicitly selected registered geometry and keeps a scalar zero separate from absent cloud layers', async () => {
  const rendered = render(view(registered))
  expect(rendered.container.querySelectorAll('.sky-registered-horizon')).toHaveLength(1)
  expect(screen.getByText('Hand registered, not surveyed')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: 'Low cloud: 0 %; scalar gauge, not direction' })).toBeInTheDocument()
  expect(screen.getAllByText('No layer fraction returned')).toHaveLength(2)
  await userEvent.click(screen.getByText('Registered bearing and elevation samples'))
  expect(screen.getByRole('table', { name: 'Signal Hill registered horizon' })).toHaveTextContent('-1°')
  rendered.rerender(view())
  expect(rendered.container.querySelectorAll('.sky-registered-horizon')).toHaveLength(0)
  expect(screen.getByText(/A nearby site is not borrowed/)).toBeInTheDocument()
  expect(screen.getByText(/This is not an empty night window/)).toBeInTheDocument()
  expect(rendered.container.querySelectorAll('.sky-horizon image')).toHaveLength(0)
})
it('preserves exact Focus in astronomy requests and refuses a different returned point', async () => {
  const focus = { latitude: 47.5123456789, longitude: -52.6987654321, instant: Date.parse(at) + 12345 }
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ data_mode: 'live', latitude: 47.5615, longitude: focus.longitude, valid_time: new Date(focus.instant).toISOString(), twilight_bands: [], moon: { above_horizon: [] }, milky_way_core: { windows: [] }, provenance: { source_id: 'nasa-jpl-de442' } })))
  try {
    const result = await loadAstronomy(undefined, focus)
    const request = new URL(String(fetcher.mock.calls[0][0]), 'http://localhost')
    expect(request.searchParams.get('latitude')).toBe('47.5123456789')
    expect(request.searchParams.get('valid_time')).toBe('2026-09-07T12:00:12.345Z')
    expect(result.astronomy).toBeNull()
    expect(result.error).toContain('does not match Focus')
  } finally { fetcher.mockRestore() }
})
it('distinguishes geographic refusal from transport failure without a prior-point fallback', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'outside_supported_area', message: 'Coordinate is outside the Avalon core coverage' } }), { status: 422 }))
  try {
    const result = await loadPoint({ id: 'outside', name: 'Outside', latitude: 10.123456789, longitude: -52.7, kind: 'map' }, at)
    expect(result.source).toBe('unavailable')
    expect(result.error).toContain('Outside supported area')
    expect(result.snapshot.servedFields).toHaveLength(0)
  } finally { fetcher.mockRestore() }
})
