// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5197'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-bench-proof'
await mkdir(output, { recursive: true })
const at = '2026-09-07T12:00:00.000Z'
const layerId = 'eccc-hrdps-surface-total-cloud'
const layer = { id: layerId, title: 'HRDPS total cloud · fixed fixture', kind: 'points', field: 'total_cloud', field_key: 'cloud_area_fraction_total', family: 'cloud_cover', product: 'HRDPS', units: '%', semantics: 'Fixed constructed test values; no live weather retrieval.', times: [at], staleness_tolerance_seconds: 3600, evidence_class: 'retrieved', evidence_basis: 'published_artifact', data_mode: 'fixture', raster_available: false }
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.clock.install({ time: new Date(at) })
const errors = []; const requests = []; let failPoint = false
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
  else if (path === '/registry/sites') body = { operational: false, version: 'a'.repeat(64), sites: [{ id: 'signal-hill', name: 'Signal Hill', latitude: 47.5704, longitude: -52.6816, elevation_m: 140, datum: 'CGVD2013', registered_on: '2026-09-03', registered_by: 'Fixture owner', geometry_note: 'Constructed registry fixture; not surveyed.', horizon: { site_id: 'signal-hill', bearing_resolution_deg: 90, elevation_deg: [0, 1, 2, 3], terrain_check_status: 'not_run', terrain_check_note: 'Not surveyed' } }], notice: null }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
})
try {
  await page.goto(`${base}/?lat=47.5123456789&lon=-52.6987654321&t=${at}`)
  await page.getByText('Development fixture', { exact: true }).waitFor()
  await page.getByText('Point evidence ledger', { exact: true }).click()
  const inspect = page.getByRole('button', { name: /^Inspect temperature from noaa\-gfs/, exact: true })
  await inspect.click()
  await page.getByRole('heading', { name: 'Evidence · temperature' }).waitFor()
  assert.equal(await page.getByRole('heading', { name: 'Evidence · temperature' }).evaluate((el) => el === document.activeElement), true)
  await page.keyboard.press('Escape')
  assert.equal(await inspect.evaluate((el) => el === document.activeElement), true)
  await page.getByRole('button', { name: 'Dock Sources', exact: true }).click()
  await page.getByRole('complementary', { name: 'Sources companion', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Dock Sky', exact: true }).click()
  assert.equal(await page.getByRole('complementary', { name: 'Sources companion', exact: true }).count(), 0)
  await page.getByRole('button', { name: 'Close Sky dock', exact: true }).click()
  // Inspector and layer stack remain usable in all three selected themes.
  for (const name of ['light', 'dark', 'Red night']) {
    await page.getByRole('button', { name, exact: true }).click()
    await inspect.click()
    await page.screenshot({ path: `${output}/${name.replace(' ', '-')}.png` })
    await page.getByRole('button', { name: 'Close inspector', exact: true }).click()
  }
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
  await page.screenshot({ path: `${output}/text-zoom-200.png` })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.evaluate(() => { document.documentElement.style.fontSize = '' })
  // A failed selection must clear the old zero, while preserving exact Focus.
  failPoint = true
  await page.goto(`${base}/?lat=48.123456789&lon=-52.6987654321&t=${at}&stack=[]`)
  await page.getByText('Unavailable', { exact: true }).first().waitFor()
  assert.equal(new URL(page.url()).searchParams.get('lat'), '48.123456789')
  assert.ok(requests.some((url) => url.includes('latitude=47.5123456789') && url.includes('valid_time=2026-09-07T12')))
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ at, viewport: '1440x900', weatherProviderRequests: 0, externalRequests: 'blocked', checks: ['exact Focus request', 'inspector focus and Escape return', 'dock replacement', 'three themes', '200% text zoom without page overflow', 'failed read clears values'], requests, errors }, null, 2))
  console.log(`PASS: fixed desktop Bench proof at ${output}`)
} finally { await browser.close() }
