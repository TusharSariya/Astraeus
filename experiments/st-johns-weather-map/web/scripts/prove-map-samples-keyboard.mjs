// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5247'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-app69-fixed-proof'
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
  else if (path.endsWith('/features')) body = { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-52.6, 47.5] }, properties: { station_id: 'FIXTURE-STATION', value: 0, absent: null, units: '%', quality: 'unknown' } }] }
  else if (path === '/catalog') body = { data_mode: 'fixture', sources: [{ id: 'declared-only', producer: 'Fixture producer', product: 'Declared product', state: 'enabled', status_reason: 'Declaration only', role: 'model', may_enter_consensus: false, cadence: 'hourly', forecast_horizon: '48 hours', geographic_coverage: 'Global declaration', licence: 'Fixture terms', attribution: 'Fixture producer', fields: [{ key: 'temperature_2m', family: 'temperature', storage: 'available-not-stored', upstream: 'TMP', note: 'No acquisition claimed' }] }] }
  else if (path === '/sources/status') body = { data_mode: 'fixture', statuses: [], notices: [] }
  else if (path === '/methods') body = { data_mode: 'fixture', methods: [], notices: [] }
  else if (path === '/timeline') body = { data_mode: 'fixture', start: '2026-09-07T09:00:00Z', end: '2026-09-08T12:00:00Z', items: [] }
  else if (path === '/registry/sites') body = { operational: false, version: 'a'.repeat(64), sites: [{ id: 'signal-hill', name: 'Signal Hill', latitude: 47.5704, longitude: -52.6816, elevation_m: 140, datum: 'CGVD2013', registered_on: '2026-09-03', registered_by: 'Fixture owner', geometry_note: 'Constructed registry fixture; not surveyed.', horizon: { site_id: 'signal-hill', bearing_resolution_deg: 90, elevation_deg: [0, 1, 2, 3], terrain_check_status: 'not_run', terrain_check_note: 'Not surveyed' } }], notice: null }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
})
try {
  await page.goto(`${base}/?lat=47.5123456789&lon=-52.6987654321&t=${at}&stack=${encodeURIComponent(JSON.stringify([{ id: layerId, visible: true, opacity: 0.85 }]))}`)
  await page.locator('.bench-map-evidence summary').filter({hasText:'1 returned features'}).waitFor()
  await page.evaluate(() => document.fonts.ready)
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  const trail = []
  let reached = false
  for (let i=0;i<150;i++) {
    await page.keyboard.press('Tab')
    const el = await page.evaluate(() => { const e=document.activeElement; const r=e.getBoundingClientRect(); return {tag:e.tagName,text:e.getAttribute('aria-label')||e.textContent?.trim().slice(0,150),visible:r.width>0&&r.height>0,top:r.top,bottom:r.bottom} })
    trail.push(el)
    if (el.tag==='A' && el.text==='Skip to Map samples') { reached=true; break }
  }
  assert.equal(reached,true)
  assert.equal(trail.length,2)
  const focusUrl = page.url()
  await page.keyboard.press('Enter')
  assert.equal(await page.getByRole('heading', {name:'Map samples and display provenance', exact:true}).evaluate(e=>e===document.activeElement),true)
  assert.equal(page.url(),focusUrl)
  await page.keyboard.press('Tab')
  const opener = page.locator(':focus')
  const openerId = await opener.getAttribute('id')
  assert.match(openerId,/map-feature/)
  await page.screenshot({path:`${output}/01-keyboard-reading.png`})
  await page.keyboard.press('Enter')
  const inspector = page.getByRole('complementary',{name:'Evidence inspector',exact:true})
  assert.equal(await inspector.getByRole('heading').evaluate(e=>e===document.activeElement),true)
  const tree = await inspector.ariaSnapshot()
  await page.screenshot({path:`${output}/02-keyboard-inspector.png`})
  await page.keyboard.press('Tab')
  assert.equal(await page.locator(':focus').textContent(),'Close inspector')
  await page.keyboard.press('Enter')
  assert.equal(await page.locator(':focus').getAttribute('id'),openerId)
  await page.keyboard.press('Space')
  await inspector.waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await page.locator(':focus').getAttribute('id'),openerId)
  await writeFile(`${output}/keyboard-audit.json`,JSON.stringify({trail,tabsToSkipLink:trail.length,tree,checks:['Tab-only discovery','Enter open','heading focus','one Tab to Close','Enter Close returns','Space open','Escape returns'],errors},null,2))
  console.log(JSON.stringify({tabsToSkipLink:trail.length,trail,tree,errors},null,2))
} finally { await browser.close() }
