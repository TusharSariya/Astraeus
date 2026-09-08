import { afterEach, expect, it, vi } from 'vitest'
import { loadCatalog, loadSourceStatus } from './api'
import { discoveryRows } from './workbench/discovery'

afterEach(() => vi.unstubAllGlobals())
it('omits only proven geographic exclusions across UI catalogue and status consumers', async () => {
  const ids = ['openmeteo-pollen-ammonia', 'meteosource', 'space-track', 'google-weathernext-3-statistics',
    'dwd-icon-eps', 'noaa-rap', 'openmeteo-graphcast', 'unknown-future-source', 'openmeteo-cams-aod']
  const sources = ids.map(id => ({ id, producer: id, product: id, state: 'unavailable',
    status_reason: 'credentials, agreement, payment or unverified coverage' }))
  const statuses = ids.map(source_id => ({ source_id, state: 'unavailable', data_mode: 'live' }))
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ sources, statuses, data_mode: 'live' })))
  const catalog = await loadCatalog()
  const status = await loadSourceStatus()
  expect(catalog.sources.map(s => s.id)).toEqual(ids.slice(1))
  expect(status.statuses?.map(s => s.source_id)).toEqual(ids.slice(1))
  expect(discoveryRows(catalog.sources, []).map(s => s.id).sort()).toEqual(ids.slice(1).sort())
  expect(catalog.error).toBeNull()
  expect(status.error).toBeNull()
})

it('hides declared superseded sources while retaining their replacement and dated usable records', async () => {
  const sources = [
    { id: 'eccc-raqdps-firework', state: 'superseded' },
    { id: 'future-retired-feed', state: 'superseded' },
    { id: 'eccc-raqdps', state: 'catalogued' },
    { id: 'historical-dataset', state: 'catalogued' },
    { id: 'temporarily-stale-feed', state: 'unavailable' },
    { id: 'agreement-gated-feed', state: 'partnership-only' },
  ].map(row => ({ ...row, producer: row.id, product: row.id }))
  const statuses = sources.map(row => ({ source_id: row.id, state: row.state }))
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ sources, statuses, data_mode: 'live' })))
  const catalog = await loadCatalog()
  const status = await loadSourceStatus()
  const expected = sources.slice(2).map(row => row.id)
  expect(catalog.sources.map(row => row.id)).toEqual(expected)
  expect(status.statuses?.map(row => row.source_id)).toEqual(expected)
  expect(discoveryRows(catalog.sources, []).map(row => row.id).sort()).toEqual([...expected].sort())
  expect(sources).toHaveLength(6)
  expect(statuses).toHaveLength(6)
})
