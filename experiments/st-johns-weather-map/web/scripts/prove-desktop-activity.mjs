// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5251'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-desktop-activity-proof'
await mkdir(output, { recursive: true })
const at = '2026-09-07T12:00:00.000Z'
const layerId = 'eccc-hrdps-surface-total-cloud'
const layer = { id: layerId, title: 'HRDPS total cloud · fixed fixture', kind: 'points', field: 'total_cloud', field_key: 'cloud_area_fraction_total', family: 'cloud_cover', product: 'HRDPS', units: '%', semantics: 'Fixed constructed test values; no live weather retrieval.', times: [at], staleness_tolerance_seconds: 3600, evidence_class: 'retrieved', evidence_basis: 'published_artifact', data_mode: 'fixture', raster_available: false }
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.clock.install({ time: new Date(at) })
const fixture = JSON.parse(await readFile(process.env.ACTIVITY_FIXTURE ?? '/tmp/activity-browser-fixture.json', 'utf8'));
let failActivity = false;
const errors = []; const requests = []; let failPoint = false; let failAstronomy = false; let failSeries = false; let seriesSnapshot = null; let seriesReads = 0
page.on('pageerror', (error) => errors.push(String(error)))
await page.route('**/*', async (route) => {
  const url = new URL(route.request().url())
  if (url.origin !== new URL(base).origin) return route.abort()
  if (!url.pathname.startsWith('/api/')) return route.continue()
  requests.push(url.pathname + url.search)
  const path = url.pathname.split('/v0')[1]
  let body = { data_mode: 'unavailable', notices: ['Fixed proof: capability not supplied'] }
  if (path === '/verdicts' || path === '/verdicts/series') {
    if (failActivity) return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{code:'activity_unavailable',message:'Constructed Activity refresh failure'}})})
    const stamp=url.searchParams.get('valid_time')
    const value=JSON.parse(JSON.stringify(fixture).replaceAll('2026-09-07T12:00:00Z',stamp))
    value.focus={latitude:Number(url.searchParams.get('latitude')),longitude:Number(url.searchParams.get('longitude')),valid_time:stamp,site_id:url.searchParams.get('site_id')}
    value.notices=['CONSTRUCTED EVALUATOR BROWSER PROOF: actual v2 profiles and evaluator, synthetic native inputs; no live acquisition']
    if(path.endsWith('/series')) body={...value,cells:[value,{...value,focus:{...value.focus,valid_time:new Date(Date.parse(stamp)+7200000).toISOString()}}],end:url.searchParams.get('end'),resolution_seconds:3600,queried_times:[stamp,new Date(Date.parse(stamp)+7200000).toISOString()],complete:true,next_start:null}
    else body=value
  }
  else if (path === '/point') {
    if (failPoint) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Fixed failure' }) })
    body = { latitude: Number(url.searchParams.get('latitude')), longitude: Number(url.searchParams.get('longitude')), valid_time: url.searchParams.get('valid_time'), data_mode: 'fixture', selection: { mode: 'evidence_only', badge: 'Fixed browser fixture', reason: 'Constructed values, no provider retrieval' }, fields: [
      { field: 'temperature', value: 0, key: 'air_temperature_2m', family: 'temperature', provenance: { source_id: 'noaa-gfs', provider: 'NOAA', product: 'GFS', normalized_units: 'degC', evidence_class: 'retrieved', data_mode: 'fixture', valid_time: at, quality: { status: 'unknown', flags: [] }, artifact_revision: 'fixed-proof', sample: { latitude: 47.5, longitude: -52.6 } } },
      { field: 'cloud_low', key: 'cloud_low', family: 'cloud_cover', value: 0, provenance: { source_id: 'noaa-gfs', normalized_units: '%', evidence_class: 'retrieved', data_mode: 'fixture', valid_time: at, quality: { status: 'unknown', flags: [] } } },
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
  else if (path === '/astronomy') {
    if (failAstronomy) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Constructed geometry failure' }) })
    body = { data_mode: 'live', operational: false, latitude: Number(url.searchParams.get('latitude')), longitude: Number(url.searchParams.get('longitude')), valid_time: url.searchParams.get('valid_time'), window_start: at, window_end: '2026-09-08T12:00:00Z', sun_altitude_deg: 0, moon_altitude_deg: -2, core_altitude_deg: 15, twilight_bands: [], moon: { rise: null, set: null, above_horizon: [], phase_deg: 30, illuminated_fraction: .5 }, milky_way_core: { windows: [], max_altitude_deg: 15, caption: 'Constructed geometry, no visibility claim' }, provenance: { source_id: 'nasa-jpl-de442', kernel_id: 'constructed-test-contract', kernel_sha256: 'a'.repeat(64), derivation: 'Constructed browser response', derivation_version: 'fixed-proof', operational: false }, notices: ['CONSTRUCTED GEOMETRY CONTRACT FIXTURE · not an ephemeris calculation'] }
  }
  else if (path === '/registry/cameras') body = { operational: false, version: 'b'.repeat(64), cameras: [{ id: 'fixture-camera', name: 'Fixture sky camera', source_id: 'fixture-camera-source', operator: 'Fixture operator', status: 'partnership-only', latitude: null, longitude: null, position_surveyed: false, bearing_deg: null, horizontal_fov_deg: null, vertical_fov_deg: null, geometry_validation: 'not_run', registration_complete: false, missing_registration: ['position.latitude', 'orientation.bearing_deg'], declared_retrieval_eligible: false, refusal_code: 'partnership_only', image_delivery_implemented: false }], notices: ['Constructed camera metadata; no imagery'] }
  else if (path === '/registry/sites') body = { operational: false, version: 'a'.repeat(64), sites: [{ id: 'signal-hill', name: 'Signal Hill', latitude: 47.5704, longitude: -52.6816, elevation_m: 140, datum: 'CGVD2013', registered_on: '2026-09-03', registered_by: 'Fixture owner', geometry_note: 'Constructed registry fixture; not surveyed.', horizon: { site_id: 'signal-hill', bearing_resolution_deg: 90, elevation_deg: [0, 1, 2, 3], terrain_check_status: 'not_run', terrain_check_note: 'Not surveyed' } }], notice: null }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
})

const checks=[]
try {
  await page.goto(`${base}/?view=activity&lat=47.5615&lon=-52.7126&t=${at}`)
  await page.getByText(/Computed .*Cache miss/).waitFor()
  assert.equal(await page.locator('.activity-lane').count(),4)
  assert.equal(await page.locator('.activity-summary button[aria-expanded=true]').count(),0)
  assert.equal(await page.locator('.activity-lane[data-state=unchecked]').count(),2)
  assert.equal(await page.locator('.activity-lane[data-state=scored]').count(),2)
  checks.push('Actual v2 evaluator fixture: Running/Landscape unchecked; Astronomy/Aurora scored')
  await page.getByRole('button',{name:'Read native strip',exact:true}).click()
  await page.getByRole('button',{name:`Running at ${at}: unchecked`,exact:true}).waitFor()
  const gap=page.getByRole('button',{name:'Running at 2026-09-07T14:00:00.000Z: unchecked',exact:true})
  assert.equal(await gap.evaluate(el=>el.style.gridColumn),'3')
  checks.push('Aligned strips preserve the unissued middle hour')
  for(const theme of ['light','dark','Red night']) {
    await page.getByRole('button',{name:theme,exact:true}).click()
    await page.screenshot({path:`${output}/activity-${theme.replace(' ','-')}.png`})
  }
  await page.getByRole('button',{name:'Expand Activity',exact:true}).click()
  await page.setViewportSize({width:1440,height:1400})
  await page.getByRole('button',{name:'light',exact:true}).click()
  await page.screenshot({path:`${output}/activity-fullscreen-overview.png`})
  await page.setViewportSize({width:1440,height:900})
  await page.keyboard.press('Escape')
  await page.getByRole('button',{name:'Running',exact:true}).click()
  const opener=page.getByRole('button',{name:'Inspect running thermal',exact:true})
  await page.getByRole('button',{name:'Expand Activity',exact:true}).click()
  await opener.focus();await page.keyboard.press('Enter')
  const inspector=page.getByRole('complementary',{name:'Evidence inspector',exact:true})
  await inspector.getByRole('heading').waitFor()
  assert.equal(await inspector.getByRole('heading').evaluate(el=>el===document.activeElement),true)
  await page.screenshot({path:`output/inspector.png`.replace('output',output)})
  await page.keyboard.press('Escape')
  assert.equal(await opener.evaluate(el=>el===document.activeElement),true)
  await page.keyboard.press('Escape')
  checks.push('Activity fullscreen keyboard inspection and both Escape focus returns')
  await page.getByRole('button',{name:'Map',exact:true}).click()
  await page.getByRole('button',{name:'Dock Activity',exact:true}).click()
  await page.getByRole('button',{name:'Inspect running thermal',exact:true}).click()
  await page.keyboard.press('Escape')
  await page.waitForFunction(el=>el===document.activeElement,await page.getByRole('button',{name:'Inspect running thermal',exact:true}).elementHandle())
  checks.push('Activity dock remount restores criterion opener')
  await page.getByRole('button',{name:'Close Activity dock',exact:true}).click()
  await page.getByRole('button',{name:'Activity',exact:true}).click()
  await page.getByRole('button',{name:'Open running thermal in Series',exact:true}).click()
  await page.getByRole('heading',{name:'Series',exact:true}).waitFor()
  assert.match(await page.locator('.native-series select').first().inputValue(),/temperature_2m/)
  await page.getByRole('button',{name:'Activity',exact:true}).click()
  await page.getByRole('button',{name:'Load Running Map stack',exact:true}).click()
  await page.getByRole('heading',{name:'Map',exact:true}).waitFor()
  assert.equal(await page.locator('.bench-stack ol > li').count(),8)
  assert.equal(await page.locator('.bench-stack ol > li').first().getByText('eccc-lightning-lightning',{exact:true}).count(),1)
  checks.push('Activity criterion jumps to Series; selected top-first stack replaces Map with unavailable entries retained')
  await page.getByRole('button',{name:'Activity',exact:true}).click()
  await page.getByRole('button',{name:'Inspect running thermal',exact:true}).click()
  failActivity=true
  await page.getByRole('button',{name:'Refresh Activity',exact:true}).click()
  await page.getByText(/Constructed Activity refresh failure/).first().waitFor()
  assert.equal(await page.locator('.activity-lane[data-state=scored]').count(),0)
  await inspector.getByText(/old values are withheld/).waitFor()
  await page.keyboard.press('Escape')
  failActivity=false
  await page.getByRole('button',{name:'Refresh Activity',exact:true}).click()
  await page.getByText(/Computed .*Cache miss/).waitFor()
  checks.push('Failed replacement clears scores and current inspector; explicit retry recovers')
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.evaluate(()=>document.documentElement.style.fontSize='200%')
  for(const view of ['Map','Series','Sources','Sky','Activity']) {
    await page.getByRole('button',{name:view,exact:true}).click()
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true)
  }
  await page.screenshot({path:`${output}/activity-zoom-200.png`})
  await page.evaluate(()=>document.documentElement.style.fontSize='')
  const cdp=await page.context().newCDPSession(page)
  const ax=await cdp.send('Accessibility.getFullAXTree')
  const unnamed=ax.nodes.filter(node=>!node.ignored&&['button','combobox','textbox','searchbox','slider','link','checkbox'].includes(node.role?.value)&&!node.name?.value?.trim())
  assert.deepEqual(unnamed,[])
  checks.push('Five assembled views at 200% text zoom; Activity accessibility tree has no unnamed controls (not a screen-reader session)')
  await page.clock.runFor(301000)
  await page.getByText('Activity expired. Refresh explicitly to read current evidence.',{exact:true}).waitFor()
  assert.equal(await page.locator('.activity-lane[data-state=scored]').count(),0)
  checks.push('Fixed expiry withholds scores without automatic retrieval')
  assert.deepEqual(errors,[])
  await writeFile(`${output}/receipt.json`,JSON.stringify({checks,requests,errors,live_provider_evidence:false},null,2))
  console.log(JSON.stringify({output,checks,errors},null,2))
} finally { await browser.close() }
