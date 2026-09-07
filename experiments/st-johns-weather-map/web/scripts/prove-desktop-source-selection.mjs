// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5243'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-source-selection-proof'
await mkdir(output, { recursive: true })
const at = '2026-09-07T12:00:00.000Z'
const layerId = 'eccc-hrdps-surface-total-cloud'
const layer = { id: layerId, title: 'HRDPS total cloud · fixed fixture', kind: 'points', field: 'total_cloud', field_key: 'cloud_area_fraction_total', family: 'cloud_cover', product: 'HRDPS', units: '%', semantics: 'Fixed constructed test values; no live weather retrieval.', times: [at], staleness_tolerance_seconds: 3600, evidence_class: 'retrieved', evidence_basis: 'published_artifact', data_mode: 'fixture', raster_available: false, mapping_status: 'known', mapping_reason: 'Constructed source declaration', field_mappings: [{ source_id: 'eccc-hrdps', field_key: 'total_cloud_opacity', declared_field: 'total_cloud' }] }
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.clock.install({ time: new Date(at) })
const errors = []; const requests = []; let failPoint = false; let failSeries = false; let seriesSnapshot = null; let seriesReads = 0
page.on('pageerror', (error) => errors.push(String(error)))
await page.route('**/*', async (route) => {
  const url = new URL(route.request().url())
  if (url.origin !== new URL(base).origin) return route.abort()
  if (!url.pathname.startsWith('/api/')) return route.continue()
  requests.push(url.pathname + url.search)
  const path = url.pathname.split('/v0')[1]
  let body = { data_mode: 'unavailable', notices: ['Fixed proof: capability not supplied'] }
  if (path === '/point') {
    if (failPoint) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Fixed failure' }) })
    body = { latitude: Number(url.searchParams.get('latitude')), longitude: Number(url.searchParams.get('longitude')), valid_time: url.searchParams.get('valid_time'), data_mode: 'fixture', selection: { mode: 'evidence_only', badge: 'Fixed browser fixture', reason: 'Constructed values, no provider retrieval' }, fields: [
      { field: 'temperature', value: 0, key: 'air_temperature_2m', family: 'temperature', provenance: { source_id: 'noaa-gfs', provider: 'NOAA', product: 'GFS', normalized_units: 'degC', evidence_class: 'retrieved', data_mode: 'fixture', valid_time: at, quality: { status: 'unknown', flags: [] }, artifact_revision: 'fixed-proof', sample: { latitude: 47.5, longitude: -52.6 } } },
      { field: 'total_cloud', value: 65, family: 'cloud_cover', provenance: { source_id: 'eccc-hrdps', provider: 'ECCC', product: 'HRDPS', normalized_units: '%', evidence_class: 'retrieved', data_mode: 'fixture', valid_time: at, quality: { status: 'unknown', flags: [] } } },
    ], notices: ['FIXED CONSTRUCTED BROWSER PROOF · not live evidence'] }
  } else if (path === '/layers') body = { data_mode: 'fixture', layers: url.searchParams.get('product') === 'CAP' ? [] : [layer], notices: [] }
  else if (path.endsWith('/features')) body = { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-52.6, 47.5] }, properties: { value: 65 } }] }
  else if (path === '/catalog') body = { data_mode: 'fixture', sources: [] }
  else if (path === '/sources/status') body = { data_mode: 'fixture', statuses: [], notices: [] }
  else if (path === '/methods') body = { data_mode: 'fixture', methods: [], notices: [] }
  else if (path === '/timeline') body = { data_mode: 'fixture', start: '2026-09-07T09:00:00Z', end: '2026-09-08T12:00:00Z', items: [] }
  else if (path === '/point/series') {
    if (failSeries) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'snapshot_unreadable', message: 'Constructed refresh failure' } }) })
    const selection = route.request().postDataJSON()
    seriesReads++
    seriesSnapshot = { id: `fixture-${seriesReads}`, selected_at: at, expires_at: '2026-09-07T12:05:00Z', change_token: 'fixed-check', identities: [] }
    body = { selection, snapshot: seriesSnapshot, complete: true, next_cursor: null, notices: ['Constructed native Series browser fixture; no provider acquisition'],
      series: selection.selectors.map((s) => ({ selector_id: s.id, source_id: s.source_id, field: s.field, requested_run: s.run, availability: 'available', reason: 'Native fixture times with an explicit missing sample', selectable_runs: [{ id: 'new', run_time: at }, { id: 'old', run_time: '2026-09-07T06:00:00Z' }], run_inventory_reason: 'Constructed latest/previous inventory',
        samples: [0, null, 2].map((value, index) => ({ field: s.field, key: s.field, value, provenance: { source_id: s.source_id, evidence_class: 'retrieved', data_mode: 'fixture', valid_time: new Date(Date.parse(selection.start) + [0, 54, 97][index] * 60000).toISOString(), run_time: s.run === 'old' ? '2026-09-07T06:00:00Z' : at, normalized_units: s.field === 'temperature_2m' ? 'degC' : '1', quality: { status: value === null ? 'unknown' : 'good', flags: value === null ? ['native_sample_missing'] : [] } } })) })) }
  }
  else if (path === '/point/series/changes') body = { snapshot_id: seriesSnapshot.id, checked_at: at, state: 'changed', changed_selector_ids: ['0'], reason: 'Constructed selected revision update' }
  else if (path === '/registry/sites') body = { operational: false, version: 'a'.repeat(64), sites: [{ id: 'signal-hill', name: 'Signal Hill', latitude: 47.5704, longitude: -52.6816, elevation_m: 140, datum: 'CGVD2013', registered_on: '2026-09-03', registered_by: 'Fixture owner', geometry_note: 'Constructed registry fixture; not surveyed.', horizon: { site_id: 'signal-hill', bearing_resolution_deg: 90, elevation_deg: [0, 1, 2, 3], terrain_check_status: 'not_run', terrain_check_note: 'Not surveyed' } }], notice: null }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
})
try {
  await page.goto(`${base}/?lat=47.5123456789&lon=-52.6987654321&t=${at}&view=Series&stack=[]`)
  await page.getByRole('img', { name: /temperature_2m native samples/ }).waitFor()
  const readCount = seriesReads
  await page.getByRole('button', { name: 'Sources', exact: true }).click()
  await page.getByRole('region', { name: 'Finite native Series evidence' }).waitFor()
  await page.getByRole('searchbox', { name: 'Find source or field' }).fill('eccc-hrdps')
  await page.getByRole('button', { name: 'Inspect source eccc-hrdps', exact: true }).click()
  await page.getByText('Finite native Series selection', { exact: true }).last().waitFor()
  await page.getByRole('button', { name: 'Close inspector', exact: true }).click()
  await page.getByRole('button', { name: 'Coverage lanes', exact: true }).click()
  await page.locator('.native-track summary').first().click()
  await page.getByRole('button', { name: /^Inspect temperature_2m at 2026\-09\-07T12:00:00\.000Z/, exact: true }).click()
  await page.getByText('Finite native selection', { exact: true }).waitFor()
  for (const name of ['light', 'dark', 'Red night']) {
    await page.getByRole('button', { name, exact: true }).click()
    await page.getByRole('region', { name: 'Finite native Series evidence' }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: `${output}/native-sources-${name.replace(' ', '-')}.png` })
  }
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.screenshot({ path: `${output}/native-sources-text-zoom.png` })
  await page.evaluate(() => { document.documentElement.style.fontSize = '' })
  assert.equal(seriesReads, readCount)
  await page.clock.fastForward(300000)
  await page.getByText(/Native selection expired. Values are withheld/).waitFor()
  await page.getByRole('complementary', { name: 'Evidence inspector' }).getByText(/Native selection expired or changed/).waitFor()
  assert.equal(await page.locator('.native-track').count(), 0)
  assert.equal(await page.getByRole('searchbox', { name: 'Find source or field' }).inputValue(), 'eccc-hrdps')
  await page.screenshot({ path: `${output}/native-sources-expired-inspector.png` })
  assert.equal(seriesReads, readCount)
  await page.getByRole('button', { name: 'Close inspector', exact: true }).click()
  await page.getByRole('button', { name: 'Series', exact: true }).click()
  await page.getByText(/Selection expired/).waitFor()
  assert.equal(seriesReads, readCount)
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ at, viewport: '1440x900', weatherProviderRequests: 0, externalRequests: 'blocked', checks: ['Sources shares loaded native selection without acquisition', 'point and selected-window evidence retain separate scopes', 'source and value inspection', 'three themes', '200% text zoom without page overflow', 'fixed expiry removes native values and open inspector provenance', 'filters and selection survive expiry', 'return to Series does not renew'], requests, errors }, null, 2))
  console.log(`PASS: fixed Sources/native selection proof at ${output}`)
} finally { await browser.close() }
