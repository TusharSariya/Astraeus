// Maps api-first-source-delivery: declarative capability, complete native identity,
// safe independent configuration, and one generated backend/frontend contract.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import fixture from '../../../contracts/fixtures/source-delivery.json'
import { loadCatalog, loadSourceStatus } from '../api'
import { readNativeSeriesResponse, useNativeSeries } from './NativeSeries'
import { useSourcesView } from './SourcesView'
import { capabilityOptions } from './sourceCapabilities'
import type { CatalogSource } from '../types'

const at = fixture.series.selection.start
const inspected = vi.fn()
let requested: unknown
function routeFixture() {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(at)
  vi.stubGlobal('fetch', vi.fn(async (url, init) => {
    if (String(url).endsWith('/catalog')) return Response.json(fixture.catalog)
    if (String(url).endsWith('/sources/status')) return Response.json(fixture.status)
    requested = JSON.parse(init.body)
    return Response.json(fixture.series)
  }))
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); inspected.mockClear() })
function Series({ catalog }: { catalog: CatalogSource[] }) {
  return useNativeSeries({ catalog, location: { id: 'fixture', name: 'Fixture', kind: 'map', latitude: fixture.series.selection.latitude, longitude: fixture.series.selection.longitude }, instant: Date.parse(at), enabled: true, fields: [], runs: {}, onLatest: vi.fn(), onInspect: inspected })
}
it('uses shared backend descriptors despite absent point data and keeps full native identity', async () => {
  routeFixture()
  const { sources } = await loadCatalog()
  const rendered = render(<Series catalog={sources} />)
  await screen.findAllByRole('img')
  expect(requested).toEqual({ ...fixture.series.selection, start: new Date(at).toISOString(), end: new Date(fixture.series.selection.end).toISOString() })
  const control = screen.getByRole('combobox', { name: 'Series A' })
  const choices = capabilityOptions(sources)
  expect(within(control).getAllByRole('option').length).toBeGreaterThan(2)
  const chosen = choices.find((choice) => choice.selection.source_id === 'eccc-hrdps' && choice.selection.field === 'temperature_2m')!
  await userEvent.selectOptions(control, chosen.key)
  rendered.rerender(<Series catalog={[]} />)
  expect(screen.getByRole('combobox', { name: 'Series A' })).toBe(control)
  expect(control).toHaveValue(chosen.key)
  expect(within(control).getByRole('option', { name: /hrdps.*temperature_2m.*Retained selection/ })).toBeInTheDocument()
  expect(screen.getByText(/Native Series support is not declared for this retained selection/)).toBeInTheDocument()
})
it('rejects a backend response that changes a selected variant or level', () => {
  expect(() => readNativeSeriesResponse(fixture.series)).not.toThrow()
  const badLevel = structuredClone(fixture.series)
  badLevel.series[0].level = 'other level'
  expect(() => readNativeSeriesResponse(badLevel)).toThrow('Series identity is unreadable')
  const badVariant = structuredClone(fixture.series)
  badVariant.series[0].variant.kind = 'observation'
  expect(() => readNativeSeriesResponse(badVariant)).toThrow('Series identity is unreadable')
})
it('renders backend configuration dispositions separately from acquisition and coverage', async () => {
  routeFixture()
  const [{ sources }, { statuses }] = await Promise.all([loadCatalog(), loadSourceStatus()])
  function Sources() { return useSourcesView({ catalog: sources, statuses, fields: [], layers: [], drawn: [], instant: Date.parse(at), catalogError: null, statusError: null, onInspect: inspected }) }
  render(<Sources />)
  for (const status of fixture.status.statuses) {
    const row = screen.getByRole('button', { name: `Inspect source ${status.source_id}` }).closest('tr')!
    expect(row).toHaveTextContent(`Configuration: ${status.configuration.state}`)
    expect(row).toHaveTextContent(status.configuration.reason)
    expect(row).toHaveTextContent('No readings returned at Focus; coverage unestablished')
  }
  await userEvent.click(screen.getByRole('button', { name: 'Inspect source eccc-hrdps' }))
  expect(inspected.mock.lastCall?.[0].details['Returned evidence at Focus']).toEqual([])
  expect(inspected.mock.lastCall?.[0].details['Delivery capabilities']).toEqual(fixture.catalog.sources.find((source) => source.id === 'eccc-hrdps')?.capabilities)
})
it('preserves valid backend descriptors and withholds malformed additions without granting access', async () => {
  routeFixture()
  const malformed = structuredClone(fixture.catalog)
  malformed.sources[0].capabilities[0].source_id = 'unrelated-source'
  vi.stubGlobal('fetch', vi.fn(async (url) => String(url).endsWith('/catalog') ? Response.json(malformed) : Response.json({ ...fixture.status, statuses: fixture.status.statuses.map((status) => ({ ...status, configuration: { ...status.configuration, state: 'success' } })) })))
  const [{ sources }, { statuses }] = await Promise.all([loadCatalog(), loadSourceStatus()])
  expect(sources[0].capabilities?.some((capability) => capability.source_id === 'unrelated-source')).toBe(false)
  expect(statuses?.every((status) => status.configuration === undefined)).toBe(true)
})
it('keeps members, provider statistics, derived statistics and levels as separate selection identities', async () => {
  routeFixture()
  const { sources } = await loadCatalog()
  const source = sources[0], capability = source.capabilities![0]
  const choices = capabilityOptions([{ ...source, capabilities: [{ ...capability, levels: ['2 m', '10 m'], variants: [
    { kind: 'member', member: '00' }, { kind: 'provider_statistic', statistic: 'probability', threshold: 0, comparison: 'greater_than' },
    { kind: 'derived_statistic', statistic: 'percentile', quantile: 0 },
  ] }] }])
  expect(choices).toHaveLength(6)
  expect(new Set(choices.map((choice) => choice.key)).size).toBe(6)
  expect(choices[0].selection.variant?.member).toBe('00')
  expect(choices[2].label).toContain('provider statistic · probability · greater_than 0')
  expect(choices[4].label).toContain('derived statistic · percentile · quantile 0')
})

it('rejects malformed finite snapshot identities before Sources or inspection can consume them', () => {
  const sample = fixture.series.snapshot.identities[0]
  for (const identities of [undefined, null, {}, [null], [false], [{}], [{ ...sample, source_id: '' }], [{ ...sample, field: 12 }],
    [{ ...sample, product_id: {} }], [{ ...sample, level: false }], [{ ...sample, native_level: [] }], [{ ...sample, station_id: 2 }],
    [{ ...sample, artifact_revision: {} }], [{ ...sample, run_time: 'invalid' }], [{ ...sample, valid_time: 123 }],
    [{ ...sample, sampled_latitude: 91 }], [{ ...sample, sampled_longitude: -181 }], [{ ...sample, sampled_latitude: NaN }],
    [{ ...sample, variant: { kind: 'member' } }], Array.from({ length: 49 }, () => sample)]) {
    expect(() => readNativeSeriesResponse({ ...fixture.series, snapshot: { ...fixture.series.snapshot, identities } })).toThrow('Series response is unreadable')
  }
  expect(() => readNativeSeriesResponse({ ...fixture.series, snapshot: { ...fixture.series.snapshot, identities: [] } })).not.toThrow()
  expect(() => readNativeSeriesResponse({ ...fixture.series, snapshot: { ...fixture.series.snapshot, identities: [{ ...sample, variant: { kind: 'unknown' } }] } })).not.toThrow()
})

it('shows each declared default selection once while preserving its complete wire identity', async () => {
  routeFixture()
  const { sources } = await loadCatalog()
  render(<Series catalog={sources} />)
  await screen.findAllByRole('img')
  const control = screen.getByRole('combobox', { name: 'Series A' })
  const labels = within(control).getAllByRole('option').map((option) => option.textContent)
  expect(new Set(labels).size).toBe(labels.length)
  expect(within(control).getAllByRole('option')).toHaveLength(capabilityOptions(sources).length)
})
