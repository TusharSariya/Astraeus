// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5248'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-sources-keyboard-proof'
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
async function tabTo(locator, reverse = false) {
  for (let i = 0; i < 120; i++) {
    if (await locator.evaluate(el => el === document.activeElement)) return i
    await page.keyboard.press(reverse ? 'Shift+Tab' : 'Tab')
  }
  throw new Error('Keyboard target was not reached')
}
try {
  await page.goto(`${base}/?view=Sources&lat=47.5123456789&lon=-52.6987654321&t=${at}`)
  const sources = page.getByRole('region', {name:'Source evidence catalogue'})
  const search = sources.getByRole('searchbox', {name:'Find source or field'})
  await sources.getByRole('button', {name:'Inspect source noaa-gfs',exact:true}).waitFor()
  await page.clock.runFor(2000)
  await page.waitForLoadState('networkidle')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  await tabTo(sources.getByRole('button', {name:'Coverage lanes',exact:true}))
  await page.keyboard.press('Enter')
  await tabTo(search)
  await page.keyboard.type('noaa-gfs')
  await tabTo(sources.locator('.source-coverage-lane summary'))
  await page.keyboard.press('Enter')
  await page.keyboard.press('Tab')
  const reading = sources.getByRole('button',{name: /^Inspect temperature from noaa\-gfs/,exact:true})
  assert.equal(await reading.evaluate(el=>el===document.activeElement),true)
  await page.keyboard.press('Enter')
  const inspector = page.getByRole('complementary',{name:'Evidence inspector',exact:true})
  assert.equal(await inspector.getByRole('heading').evaluate(el=>el===document.activeElement),true)
  const beforeFilter = requests.length
  const focusUrl = page.url()
  await tabTo(search,true)
  await page.keyboard.press('ControlOrMeta+A')
  await page.keyboard.type('declared-only')
  assert.equal(await reading.count(),0)
  assert.equal(await inspector.getByRole('heading').textContent(),'Evidence · temperature')
  assert.equal(page.url(),focusUrl)
  await tabTo(inspector.getByRole('button',{name:'Close inspector'}))
  await page.keyboard.press('Enter')
  assert.equal(await search.evaluate(el=>el===document.activeElement),true)
  assert.equal(requests.length,beforeFilter)
  // An unchanged opener wins; after a second filter removal, scoped Escape uses search.
  await page.keyboard.press('ControlOrMeta+A')
  await page.keyboard.type('noaa-gfs')
  await tabTo(sources.locator('.source-coverage-lane summary'))
  await page.keyboard.press('Enter')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  await inspector.waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await reading.evaluate(el=>el===document.activeElement),true)
  await page.keyboard.press('Enter')
  await tabTo(search,true)
  await page.keyboard.press('ControlOrMeta+A')
  await page.keyboard.type('no-matching-source')
  assert.equal(await reading.count(),0)
  await tabTo(inspector.getByRole('button',{name:'Close inspector'}))
  await page.keyboard.press('Escape')
  assert.equal(await search.evaluate(el=>el===document.activeElement),true)
  assert.equal(requests.length,beforeFilter)
  const focus = await page.evaluate(()=>({id:document.activeElement.id,tag:document.activeElement.tagName,name:document.activeElement.getAttribute('aria-label')}))
  await page.screenshot({path:`${output}/filter-close.png`})
  console.log(JSON.stringify({focus,returnedToSearch:await search.evaluate(el=>el===document.activeElement),requests,errors},null,2))
  await writeFile(`${output}/receipt.json`,JSON.stringify({focus,returnedToSearch:await search.evaluate(el=>el===document.activeElement),requests,errors},null,2))
} catch(error) { await page.screenshot({path:`${output}/failure.png`}); throw error } finally {await browser.close()}
