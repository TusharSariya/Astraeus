// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5244'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-map-inspection-proof'
await mkdir(output, { recursive: true })
const at = '2026-09-07T12:00:00.000Z'
const layerId = 'eccc-hrdps-surface-total-cloud'
const layer = { id: layerId, title: 'HRDPS total cloud · fixed fixture', kind: 'points', field: 'total_cloud', field_key: 'cloud_area_fraction_total', family: 'cloud_cover', product: 'HRDPS', units: '%', semantics: 'Fixed constructed test values; no live weather retrieval.', times: [at], staleness_tolerance_seconds: 3600, evidence_class: 'retrieved', evidence_basis: 'published_artifact', data_mode: 'fixture', raster_available: false }
layer.mapping_status = 'known'
layer.mapping_reason = 'Constructed explicit source association; not point coverage'
layer.field_mappings = [{ source_id: 'fixture-layer-source', field_key: 'total_cloud_opacity', declared_field: 'NT' }]
layer.imagery_availability = { status: 'known', checked_at: at, basis: 'constructed_inventory', times: ['2026-09-07T13:00:00Z'], reason: 'Advertised fixture image time; rendering is not guaranteed' }
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.clock.install({ time: new Date(at) })
const errors = []; const requests = []; const failPoint = false
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
  else if (path.endsWith('/features')) body = { type: 'FeatureCollection', data_mode: 'fixture', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-52.6, 47.5] }, properties: { station_id: 'FIXTURE-STATION', value: 0, absent: null, units: '%', quality: 'unknown' } }] }
  else if (path === '/catalog') body = { data_mode: 'fixture', sources: [{ id: 'declared-only', producer: 'Fixture producer', product: 'Declared product', state: 'enabled', status_reason: 'Declaration only', role: 'model', may_enter_consensus: false, cadence: 'hourly', forecast_horizon: '48 hours', geographic_coverage: 'Global declaration', licence: 'Fixture terms', attribution: 'Fixture producer', fields: [{ key: 'temperature_2m', family: 'temperature', storage: 'available-not-stored', upstream: 'TMP', note: 'No acquisition claimed' }] }] }
  else if (path === '/sources/status') body = { data_mode: 'fixture', statuses: [], notices: [] }
  else if (path === '/methods') body = { data_mode: 'fixture', methods: [], notices: [] }
  else if (path === '/timeline') body = { data_mode: 'fixture', start: '2026-09-07T09:00:00Z', end: '2026-09-08T12:00:00Z', items: [] }
  else if (path === '/registry/sites') body = { operational: false, version: 'a'.repeat(64), sites: [{ id: 'signal-hill', name: 'Signal Hill', latitude: 47.5704, longitude: -52.6816, elevation_m: 140, datum: 'CGVD2013', registered_on: '2026-09-03', registered_by: 'Fixture owner', geometry_note: 'Constructed registry fixture; not surveyed.', horizon: { site_id: 'signal-hill', bearing_resolution_deg: 90, elevation_deg: [0, 1, 2, 3], terrain_check_status: 'not_run', terrain_check_note: 'Not surveyed' } }], notice: null }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
})
try {
  await page.goto(`${base}/?lat=47.5123456789&lon=-52.6987654321&t=${at}&stack=${encodeURIComponent(JSON.stringify([{ id: layerId, visible: true, opacity: 0.85 }]))}`)
  const details = page.locator('.bench-map-evidence')
  await details.locator('summary').filter({ hasText: '1 returned features' }).waitFor()
  await details.locator('summary').click()
  const opener = details.getByRole('button', { name: 'Inspect FIXTURE-STATION from HRDPS total cloud · fixed fixture', exact: true })
  await opener.focus()
  await page.keyboard.press('Enter')
  const inspector = page.getByRole('complementary', { name: 'Evidence inspector', exact: true })
  assert.equal(await inspector.getByRole('heading').evaluate(el => el === document.activeElement), true)
  assert.match(await inspector.textContent(), /"value": 0/)
  assert.match(await inspector.textContent(), /"absent": null/)
  assert.match(await inspector.textContent(), /fixture-layer-source/)
  for (const theme of ['light', 'dark', 'Red night']) {
    await page.getByRole('button', { name: theme, exact: true }).click()
    await page.screenshot({ path: `${output}/station-${theme.replace(' ', '-')}.png` })
  }
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
  await page.screenshot({ path: `${output}/station-text-zoom-200.png` })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.evaluate(() => { document.documentElement.style.fontSize = '' })
  await inspector.getByRole('button', { name: 'Close inspector' }).focus()
  await page.keyboard.press('Escape')
  assert.equal(await opener.evaluate(el => el === document.activeElement), true)
  await opener.click()
  await page.getByRole('checkbox', { name: 'Show HRDPS total cloud · fixed fixture', exact: true }).uncheck()
  await inspector.getByText(/Its old values are withheld/).waitFor()
  assert.doesNotMatch(await inspector.textContent(), /"value": 0/)
  await details.locator('summary').filter({ hasText: '0 returned features' }).waitFor()
  await inspector.getByRole('button', { name: 'Close inspector' }).focus()
  await page.keyboard.press('Escape')
  assert.equal(await page.locator('#bench-stage').evaluate(el => el === document.activeElement), true)
  await page.getByRole('checkbox', { name: 'Show HRDPS total cloud · fixed fixture', exact: true }).check()
  await opener.waitFor()
  await opener.click()
  await details.getByRole('button', { name: 'Use Cape Spear as Focus', exact: true }).click()
  await inspector.getByText(/Its old values are withheld/).waitFor()
  assert.doesNotMatch(await inspector.textContent(), /"value": 0/)
  await inspector.getByRole('button', { name: 'Close inspector' }).click()
  await details.getByRole('button', { name: 'Inspect actual display HRDPS total cloud · fixed fixture', exact: true }).click()
  await inspector.getByText('Method version', { exact: true }).waitFor()
  assert.equal(await inspector.locator('dt').filter({ hasText: /^Capture identity$/ }).locator('..').locator('dd').textContent(), 'Not supplied')
  await page.screenshot({ path: `${output}/actual-display.png` })
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ at, viewport: '1440x900', externalRequests: 'blocked', weatherProviderRequests: 0, checks: ['actual feature table', 'native zero and null', 'explicit source mapping', 'keyboard inspector entry and Escape return', 'three themes', '200% text zoom', 'hidden feature clears open inspector', 'removed opener returns to stage', 'changed Focus clears old feature', 'missing method/capture remain missing'], requests, errors }, null, 2))
  console.log(`PASS: fixed Map inspection proof at ${output}`)
} catch (error) { await page.screenshot({ path: `${output}/failure.png` }); console.error(errors); throw error } finally { await browser.close() }
