import { readFileSync } from 'node:fs'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { normalizePoint } from '../api'
import { EvidenceInspector } from './EvidenceInspector'
import { isNativeImagePair, NativeImages } from './NativeImages'

// Root's shared generator imports source-native-proof-fixture.py. The override
// runs the same consumption cases before that shared-file integration lands.
const fixture = JSON.parse(readFileSync(process.env.NATIVE_SOURCE_PROOF_FIXTURE ?? new URL('../../../contracts/fixtures/source-delivery.json', import.meta.url), 'utf8'))
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
it.each([['point_ifs', 'ecmwf-ifs', '(0 - 1)'], ['point_aifs_single', 'ecmwf-aifs-single', '%']])('consumes exact %s source acquisition and native cloud units', (key, source, units) => {
  const body = fixture[key]
  expect(body.data_mode).toBe('fixture')
  const snapshot = normalizePoint(body)
  const cloud = snapshot.servedFields.find((row) => row.field === 'total_cloud_geometric')!
  expect(cloud.hasValue).toBe(true)
  expect(cloud.attribution.sourceId).toBe(source)
  expect(cloud.attribution.responseProvenance?.original_units).toBe(units)
  const acquisition = body.fields.find((field: { key: string }) => field.key === 'total_cloud_geometric').provenance.source_acquisition
  expect(acquisition.transport_receipts).toHaveLength(6)
  expect(cloud.attribution.responseProvenance?.source_acquisition).toEqual(acquisition)
  render(<EvidenceInspector evidence={{ key, label: cloud.field, text: cloud.text, attribution: cloud.attribution }} onClose={vi.fn()} />)
  const summary = screen.getByText('Source acquisition receipt').nextSibling
  expect(summary).toHaveTextContent(source)
  expect(summary).toHaveTextContent(acquisition.normalized_sha256)
  expect(summary).toHaveTextContent('"transfer_count": 6')
})
it('consumes the exact constructed Holyrood API pair and image bodies only after an explicit read', async () => {
  const pair = fixture.native_images_holyrood
  const selection = { sourceId: pair.source_id, instant: Date.parse(pair.valid_time), endpoint: pair.images[0].image_url.split(`/${pair.pair_revision}/`)[0] }
  expect(isNativeImagePair(pair, selection)).toBe(true)
  for (const image of pair.images) expect(Buffer.from(fixture.native_image_bodies_base64[image.image_url], 'base64').subarray(0, 6).toString()).toBe('GIF89a')
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse(pair.retained_until) - 1000)
  const fetch = vi.fn(async () => Response.json(pair)); vi.stubGlobal('fetch', fetch)
  render(<NativeImages selection={selection} />)
  expect(fetch).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Read native images' }))
  expect(screen.getAllByRole('img')).toHaveLength(2)
  expect(screen.getAllByRole('img')[0]).toHaveAttribute('src', pair.images[0].image_url)
  expect(screen.getByRole('region')).toHaveTextContent('Scientific freshness unknown')
  expect(fixture.native_fixture_proof.provider_requests).toBe(0)
})
it('consumes SWOB as its own station observation with no model run or companion substitution', () => {
  const body = fixture.point_swob
  expect(body.data_mode).toBe('fixture')
  const snapshot = normalizePoint(body)
  expect(snapshot.servedFields).toHaveLength(6)
  for (const row of snapshot.servedFields) {
    expect(row.attribution.sourceId).toBe('eccc-swob')
    expect(row.attribution.runTime).toBeNull()
    expect(row.attribution.responseProvenance?.native_report).toMatchObject({ station_id: '71801', provider_report_id: 'CAJW' })
  }
  expect(body.observation_unavailable).toEqual([])
})
