// Run against `npm run build` followed by `npx vite preview --port 5246`.
// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5246'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-provider-tokens-proof'
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
  else if (path.endsWith('/features')) body = { type: 'FeatureCollection', data_mode: 'fixture', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-52.6, 47.5] }, properties: { value: 65 } }] }
  else if (path === '/catalog') body = { data_mode: 'fixture', sources: ['eccc-hrdps', 'eccc-rdps', 'eccc-gdps', 'eccc-reps', 'unmapped-fixture'].map(id => ({ id, producer: 'Constructed catalogue', product: id, state: 'experimental', fields: [] })) }
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
  await page.goto(`${base}/?lat=47.51&lon=-52.69&t=${at}&view=Series&stack=[]`)
  await page.locator('.native-samples circle').first().waitFor()
  const checks = []
  for (const [theme, expected] of [['light', 'rgb(51, 139, 246)'], ['dark', 'rgb(68, 144, 238)'], ['Red night', 'rgb(253, 44, 41)']]) {
    await page.getByRole('button', { name: theme, exact: true }).click()
    assert.equal(await page.locator('.native-samples').first().evaluate(el => getComputedStyle(el).color), expected)
    assert.equal(await page.locator('.native-samples path').count(), 0)
    await page.screenshot({ path: `${output}/series-${theme.replace(' ', '-')}.png` })
  }
  await page.getByRole('button', { name: 'Sources', exact: true }).click()
  const filter = page.getByRole('searchbox', { name: 'Find source or field' })
  const rdps = page.locator('.sources-table .bench-source-tag').filter({ hasText: 'eccc-rdps' })
  await rdps.waitFor()
  assert.equal(await rdps.getAttribute('data-provider-slot'), '1')
  assert.equal(await rdps.getAttribute('data-model-style'), 'dashed')
  assert.equal(await rdps.locator('path').evaluate(el => getComputedStyle(el).strokeDasharray), '6px, 3px')
  await filter.fill('eccc-rdps')
  assert.equal(await rdps.getAttribute('data-provider-slot'), '1')
  assert.equal(await rdps.getAttribute('data-model-style'), 'dashed')
  await filter.fill('')
  assert.equal(await page.locator('.sources-table .bench-source-tag').filter({ hasText: 'unmapped-fixture' }).getAttribute('data-provider-slot'), '8')
  for (const theme of ['light', 'dark', 'Red night']) {
    await page.getByRole('button', { name: theme, exact: true }).click()
    await page.screenshot({ path: `${output}/sources-${theme.replace(' ', '-')}.png` })
  }
  await page.emulateMedia({ reducedMotion: 'reduce' })
  assert.equal(await page.getByRole('button', { name: 'Map', exact: true }).evaluate(el => getComputedStyle(el).transitionDuration), '0s')
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
  await page.screenshot({ path: `${output}/sources-text-zoom-200.png` })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.evaluate(() => { document.documentElement.style.fontSize = '' })
  assert.match(await page.locator('.timeline-dock .dock-toggle').first().evaluate(el => getComputedStyle(el).fontFamily), /Atkinson Hyperlegible Next Variable/)
  const fonts = await page.evaluate(() => Array.from(document.fonts).map(face => ({ family: face.family, status: face.status })))
  assert.ok(fonts.some(face => face.family.includes('Hyperlegible Next') && face.status === 'loaded'))
  assert.ok(fonts.some(face => face.family.includes('Hyperlegible Mono') && face.status === 'loaded'))
  assert.deepEqual(errors, [])
  checks.push('selected palette in three themes', 'native gaps remain unconnected', 'fixed provider slot and model style through filtering', 'unknown source uses Other', 'Hyperlegible timeline', 'reduced motion', '200% text zoom')
  await writeFile(`${output}/receipt.json`, JSON.stringify({ at, viewport: '1440x900', externalRequests: 'blocked', weatherProviderRequests: 0, checks, fonts, requests, errors }, null, 2))
  console.log(`PASS: selected provider token proof at ${output}`)
} catch (error) { await page.screenshot({ path: `${output}/failure.png` }); throw error } finally { await browser.close() }
