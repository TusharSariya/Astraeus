import fixture from '../../contracts/fixtures/source-delivery.json'
import { afterEach, expect, it, vi } from 'vitest'
import { loadCatalog, normalizePoint, pointProductFor } from './api'
import type { SourceCapability } from './types'
import { isSourceCapability } from './sourceContract'
import { capabilityOptions } from './workbench/sourceCapabilities'

// Contract example only: descriptor availability never establishes a live reading.
const cams: SourceCapability = { source_id: 'openmeteo-cams-aod', product_id: 'cams-global-aod', field: 'aerosol_optical_depth_550nm',
  point_product: 'CAMS AOD', point: true, native_series: false, variants: [{ kind: 'deterministic' }], levels: ['column'],
  run_selection: 'not_applicable', time_semantics: 'Exact intermediary hourly labels; not producer-native timestamps', coverage_description: 'Retrieval establishes applicable point evidence' }
afterEach(() => vi.unstubAllGlobals())
it('offers the declared CAMS point token without adding a native Series path', () => {
  expect(pointProductFor({ id: cams.source_id, capabilities: [cams] })).toBe('CAMS AOD')
  expect(capabilityOptions([{ ...fixture.catalog.sources[0], fields: [], id: cams.source_id, capabilities: [cams] }])).toEqual([])
  expect(cams.time_semantics).toContain('intermediary hourly')
})
it('prefers one declared point token, deduplicates field declarations and retains legacy fallback', () => {
  const declared = { ...cams, source_id: 'eccc-hrdps', point_product: 'Declared point product' }
  expect(pointProductFor({ id: 'eccc-hrdps', capabilities: [declared, { ...declared, field: 'another_field' }] })).toBe('Declared point product')
  expect(pointProductFor({ id: 'eccc-hrdps', capabilities: [] })).toBe('HRDPS')
  expect(pointProductFor({ id: 'eccc-hrdps', capabilities: [{ ...declared, point_product: null }] })).toBe('HRDPS')
})
it('refuses ambiguous declarations and does not infer point support from source or product text', () => {
  expect(pointProductFor({ id: cams.source_id, capabilities: [cams, { ...cams, point_product: 'Other product' }] })).toBeNull()
  expect(pointProductFor({ id: cams.source_id, capabilities: [{ ...cams, point: false }] })).toBeNull()
  expect(pointProductFor({ id: cams.source_id, capabilities: [{ ...cams, point_product: null }] })).toBeNull()
  expect(pointProductFor({ id: 'other-source', capabilities: [cams] })).toBeNull()
})
it('filters unsafe optional point tokens at the catalog boundary', async () => {
  for (const point_product of ['', ' ', ' CAMS AOD', 'CAMS AOD\n', 'x'.repeat(101), 42, {}]) expect(isSourceCapability({ ...cams, point_product }, cams.source_id)).toBe(false)
  expect(isSourceCapability({ ...cams, point_product: undefined }, cams.source_id)).toBe(true)
  const source = { id: cams.source_id, producer: 'CAMS via Open-Meteo', product: 'CAMS AOD', state: 'implemented-unverified', capabilities: [{ ...cams, point_product: 'bad\u0000token' }] }
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ sources: [source], data_mode: 'fixture' })))
  const result = await loadCatalog()
  expect(result.sources[0].capabilities).toEqual([])
  expect(pointProductFor(result.sources[0])).toBeNull()
})

// Source-delivery contract: preserve exact returned AOD, native time and gaps.
it.each([0.15, 0.07, 0.004, 0, null])('retains CAMS AOD %s in the evidence ledger without decimal truncation', (value) => {
  const point = fixture.point_cams_aod
  const snapshot = normalizePoint({ ...point, selection: { ...point.selection, mode: 'evidence_only' }, fields: [{ ...point.fields[0], value }] })
  const row = snapshot.servedFields[0]
  expect(row.text).toBe(value === null ? 'no value' : `${value} 1`)
  expect(row.hasValue).toBe(value !== null)
  expect(row.attribution.evidenceClass).toBe('reprocessed')
  expect(row.attribution.runTime).toBeNull()
  expect(row.attribution.validTime).toBe(point.valid_time)
})
