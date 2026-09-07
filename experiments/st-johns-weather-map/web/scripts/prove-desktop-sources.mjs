// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5239'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-sources-proof'
await mkdir(output, { recursive: true })
const at = '2026-09-07T12:00:00.000Z'
const layerId = 'eccc-hrdps-surface-total-cloud'
const layer = { id: layerId, title: 'HRDPS total cloud · fixed fixture', kind: 'points', field: 'total_cloud', field_key: 'cloud_area_fraction_total', family: 'cloud_cover', product: 'HRDPS', units: '%', semantics: 'Fixed constructed test values; no live weather retrieval.', times: [at], staleness_tolerance_seconds: 3600, evidence_class: 'retrieved', evidence_basis: 'published_artifact', data_mode: 'fixture', raster_available: false }
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
  else if (path === '/catalog') body = { data_mode: 'fixture', sources: [{ id: 'declared-only', producer: 'Fixture producer', product: 'Declared product', state: 'enabled', status_reason: 'Declaration only', role: 'model', may_enter_consensus: false, cadence: 'hourly', forecast_horizon: '48 hours', geographic_coverage: 'Global declaration', licence: 'Fixture terms', attribution: 'Fixture producer', fields: [{ key: 'temperature_2m', family: 'temperature', storage: 'available-not-stored', upstream: 'TMP', note: 'No acquisition claimed' }] }] }
  else if (path === '/sources/status') body = { data_mode: 'fixture', statuses: [], notices: [] }
  else if (path === '/methods') body = { data_mode: 'fixture', methods: [], notices: [] }
  else if (path === '/timeline') body = { data_mode: 'fixture', start: '2026-09-07T09:00:00Z', end: '2026-09-08T12:00:00Z', items: [] }
  else if (path === '/point/series') {
    if (failSeries) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'snapshot_unreadable', message: 'Constructed refresh failure' } }) })
    const selection = route.request().postDataJSON()
    seriesReads++
    seriesSnapshot = { id: `fixture-${seriesReads}`, selected_at: at, expires_at: '2026-09-07T12:05:00Z', change_token: 'fixed-check', identities: [] }
    body = { selection, snapshot: seriesSnapshot, complete: true, next_cursor: null, notices: ['Constructed native Series browser fixture; no provider acquisition'],
      series: selection.selectors.map((s) => ({ selector_id: s.id, source_id: s.source_id, field: s.field, requested_run: s.run, availability: 'available', reason: 'Native fixture times with an explicit missing sample',
        samples: [0, null, 2].map((value, index) => ({ field: s.field, key: s.field, value, provenance: { source_id: s.source_id, evidence_class: 'retrieved', data_mode: 'fixture', valid_time: new Date(Date.parse(selection.start) + [0, 54, 97][index] * 60000).toISOString(), run_time: '2026-09-07T06:00:00Z', normalized_units: s.field === 'temperature_2m' ? 'degC' : '1', quality: { status: value === null ? 'unknown' : 'good', flags: value === null ? ['native_sample_missing'] : [] } } })) })) }
  }
  else if (path === '/point/series/changes') body = { snapshot_id: seriesSnapshot.id, checked_at: at, state: 'changed', changed_selector_ids: ['0'], reason: 'Constructed selected revision update' }
  else if (path === '/registry/sites') body = { operational: false, version: 'a'.repeat(64), sites: [{ id: 'signal-hill', name: 'Signal Hill', latitude: 47.5704, longitude: -52.6816, elevation_m: 140, datum: 'CGVD2013', registered_on: '2026-09-03', registered_by: 'Fixture owner', geometry_note: 'Constructed registry fixture; not surveyed.', horizon: { site_id: 'signal-hill', bearing_resolution_deg: 90, elevation_deg: [0, 1, 2, 3], terrain_check_status: 'not_run', terrain_check_note: 'Not surveyed' } }], notice: null }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
})
try {
  await page.goto(`${base}/?lat=47.5123456789&lon=-52.6987654321&t=${at}`)
  await page.getByText('Development fixture', { exact: true }).waitFor()
  await page.getByText('Point evidence ledger', { exact: true }).click()
  const inspect = page.getByRole('button', { name: 'Inspect temperature from noaa-gfs', exact: true })
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
  await page.getByRole('button', { name: 'Series', exact: true }).click()
  await page.getByRole('img', { name: /temperature_2m native samples/ }).waitFor()
  assert.equal(await page.locator('.native-track circle').count(), 4)
  assert.equal(await page.getByText('native_sample_missing', { exact: true }).count(), 2)
  await page.screenshot({ path: `${output}/series-overview.png` })
  await page.locator('.native-track summary').first().click()
  const nativeInspect = page.getByRole('button', { name: 'Inspect temperature_2m at 2026-09-07T12:00:00.000Z', exact: true })
  await nativeInspect.click()
  await page.getByRole('heading', { name: 'Evidence · temperature_2m', exact: true }).waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await nativeInspect.evaluate((el) => el === document.activeElement), true)
  await page.locator('.native-track summary').first().click()
  const loadedReads = seriesReads
  await page.getByRole('button', { name: 'Temporary Compare', exact: true }).click()
  await page.getByRole('button', { name: 'Overview', exact: true }).click()
  assert.equal(seriesReads, loadedReads)
  await page.getByRole('button', { name: 'Check for changes', exact: true }).click()
  await page.getByText(/changed: Constructed selected revision update/).waitFor()
  failSeries = true
  await page.getByRole('button', { name: 'Refresh Series', exact: true }).click()
  await page.getByText(/Read failed; no replacement was applied/).waitFor()
  assert.equal(await page.locator('.native-track circle').count(), 4)
  for (const name of ['light', 'dark', 'Red night']) {
    await page.getByRole('button', { name, exact: true }).click()
    await page.screenshot({ path: `${output}/series-${name.replace(' ', '-')}.png` })
  }
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
  await page.screenshot({ path: `${output}/series-zoom-200.png` })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.evaluate(() => { document.documentElement.style.fontSize = '' })
  await page.clock.fastForward(300000)
  await page.getByText(/Selection expired/).waitFor()
  assert.equal(await page.locator('.native-track circle').count(), 0)
  await page.getByRole('button', { name: 'Sources', exact: true }).click()
  await page.getByRole('searchbox', { name: 'Find source or field' }).fill('declared-only')
  await page.getByRole('button', { name: 'Inspect source declared-only', exact: true }).click()
  await page.getByRole('heading', { name: 'Evidence · declared-only', exact: true }).waitFor()
  for (const [mode, theme] of [['Ledger', 'light'], ['Family finder', 'dark'], ['Coverage lanes', 'Red night']]) {
    await page.getByRole('button', { name: mode, exact: true }).click()
    await page.getByRole('button', { name: theme, exact: true }).click()
    assert.equal(await page.getByRole('searchbox').inputValue(), 'declared-only')
    await page.getByRole('heading', { name: 'Evidence · declared-only', exact: true }).waitFor()
    await page.screenshot({ path: `${output}/sources-${mode.replaceAll(' ', '-')}.png` })
  }
  assert.equal(await page.locator('.source-coverage-marks circle').count(), 0)
  await page.getByText('No point samples were returned. Declared horizon and retrieval status do not fill this lane.', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Close inspector', exact: true }).focus()
  await page.keyboard.press('Escape')
  assert.equal(await page.getByRole('searchbox', { name: 'Find source or field' }).evaluate((el) => el === document.activeElement), true)
  await page.getByRole('button', { name: 'Map', exact: true }).click()
  await page.getByRole('button', { name: 'Sources', exact: true }).click()
  assert.equal(await page.getByRole('searchbox').inputValue(), 'declared-only')
  // A failed selection must clear the old zero, while preserving exact Focus.
  failPoint = true
  await page.goto(`${base}/?lat=48.123456789&lon=-52.6987654321&t=${at}&stack=[]`)
  await page.getByText('Unavailable', { exact: true }).first().waitFor()
  assert.equal(new URL(page.url()).searchParams.get('lat'), '48.123456789')
  assert.ok(requests.some((url) => url.includes('latitude=47.5123456789') && url.includes('valid_time=2026-09-07T12')))
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ at, viewport: '1440x900', weatherProviderRequests: 0, externalRequests: 'blocked', checks: ['exact Focus request', 'inspector focus and Escape return', 'dock replacement', 'three themes', '200% text zoom without page overflow', 'failed read clears values', 'native Series zero and missing sample', 'separate axes', 'Compare preserves pin', 'non-mutating change check', 'failed refresh preserves labelled selection', 'fixed expiry clears expired Series', 'Sources filters and inspector persist across perspectives', 'declaration does not populate a coverage lane', 'removed Sources opener returns to search'], requests, errors }, null, 2))
  console.log(`PASS: fixed desktop Bench, Series and Sources proof at ${output}`)
} catch (error) { await page.screenshot({ path: `${output}/failure.png` }); console.error(errors); throw error } finally { await browser.close() }
