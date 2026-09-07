// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5250'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-desktop-access-proof'
await mkdir(output, { recursive: true })
const at = '2026-09-07T12:00:00.000Z'
const layerId = 'eccc-hrdps-surface-total-cloud'
const layer = { id: layerId, title: 'HRDPS total cloud · fixed fixture', kind: 'points', field: 'total_cloud', field_key: 'cloud_area_fraction_total', family: 'cloud_cover', product: 'HRDPS', units: '%', semantics: 'Fixed constructed test values; no live weather retrieval.', times: [at], staleness_tolerance_seconds: 3600, evidence_class: 'retrieved', evidence_basis: 'published_artifact', data_mode: 'fixture', raster_available: false }
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.clock.install({ time: new Date(at) })
const errors = []; const requests = []; let failPoint = false; let failAstronomy = false; let failSeries = false; let seriesSnapshot = null; let seriesReads = 0
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
async function focused(locator) {
  await page.waitForFunction(el => el === document.activeElement, await locator.elementHandle())
}
async function openWithKeyboard(locator) {
  await locator.focus()
  await page.keyboard.press('Enter')
  await focused(page.getByRole('complementary',{name:'Evidence inspector',exact:true}).getByRole('heading'))
}
async function keyboardSweep() {
  const expected = await page.evaluate(() => {
    for(const detail of document.querySelectorAll('details')) { detail.dataset.auditOpen=String(detail.open); detail.open=true }
    const controls=[...document.querySelectorAll('button,input,select,textarea,a[href],summary,[tabindex]')].filter(el=>el.tabIndex>=0 && !el.disabled && el.getClientRects().length && getComputedStyle(el).visibility!=='hidden')
    controls.forEach((el,i)=>el.dataset.auditControl=String(i))
    return controls.map(el=>({id:el.dataset.auditControl,name:el.getAttribute('aria-label')||el.textContent?.trim().slice(0,100)||el.tagName}))
  })
  const visited = new Set()
  for(let i=0;i<expected.length*2+20;i++) {
    await page.keyboard.press('Tab')
    const id=await page.evaluate(()=>document.activeElement?.getAttribute('data-audit-control'))
    if(id!==null) visited.add(id)
    if(visited.size===expected.length) break
  }
  const missing=expected.filter(item=>!visited.has(item.id))
  await page.evaluate(()=>{
    for(const detail of document.querySelectorAll('details[data-audit-open]')) {detail.open=detail.dataset.auditOpen==='true';delete detail.dataset.auditOpen}
    for(const el of document.querySelectorAll('[data-audit-control]')) delete el.dataset.auditControl
  })
  assert.deepEqual(missing,[])
  return expected.length
}
const inspector = page.getByRole('complementary',{name:'Evidence inspector',exact:true})
const checks = []
const axResults = []
try {
  await page.goto(`${base}/?lat=47.5123456789&lon=-52.6987654321&t=${at}`)
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => document.fonts.ready)
  assert.equal(await page.evaluate(() => [...document.fonts].some(font=>font.family.includes('Atkinson Hyperlegible Next') && font.status==='loaded')),true)
  for (const view of ['Map','Series','Sources','Sky']) {
    await page.getByRole('button',{name:view,exact:true}).click()
    await page.getByRole('button',{name:`Expand ${view}`,exact:true}).click()
    let opener
    if(view==='Map') {
      await page.getByText('Point evidence ledger',{exact:true}).click()
      opener = page.getByRole('button',{name:/^Inspect temperature from noaa-gfs/})
    } else if(view==='Series') {
      await page.locator('.native-track summary').first().click()
      opener = page.getByRole('button',{name:/^Inspect temperature_2m at/}).first()
    } else if(view==='Sources') opener=page.getByRole('button',{name:'Inspect source declared-only',exact:true})
    else opener=page.getByRole('button',{name:'Inspect Sun altitude',exact:true})
    await openWithKeyboard(opener)
    await page.keyboard.press('Escape')
    await focused(opener)
    assert.equal(await page.getByRole('button',{name:'Return to Bench',exact:true}).count(),1)
    await page.keyboard.press('Escape')
    await focused(page.getByRole('button',{name:`Expand ${view}`,exact:true}))
    checks.push(`${view}: fullscreen inspector entry, scoped Escape and expansion return`)
    const keyboardControls=await keyboardSweep()
    const cdp=await page.context().newCDPSession(page)
    const tree=await cdp.send('Accessibility.getFullAXTree')
    const unnamed=tree.nodes.filter(node=>!node.ignored && ['button','combobox','textbox','searchbox','slider','link','checkbox'].includes(node.role?.value) && !node.name?.value).map(node=>({role:node.role.value,backendDOMNodeId:node.backendDOMNodeId}))
    assert.deepEqual(unnamed,[])
    axResults.push({view,keyboardControls,unnamedControls:unnamed})
    await cdp.detach()
  }
  // The companion is replaced by the inspector and remounts when it closes.
  await page.getByRole('button',{name:'Map',exact:true}).click()
  for (const view of ['Sources','Sky','Series']) {
    await page.getByRole('button',{name:`Dock ${view}`,exact:true}).click()
    const companion=page.getByRole('complementary',{name:`${view} companion`,exact:true})
    let opener
    if(view==='Sources') opener=companion.getByRole('button',{name:'Inspect source declared-only',exact:true})
    else if(view==='Sky') opener=companion.getByRole('button',{name:'Inspect Sun altitude',exact:true})
    else { await companion.locator('.native-track summary').first().click(); opener=companion.getByRole('button',{name:/^Inspect temperature_2m at/}).first() }
    await openWithKeyboard(opener)
    await page.keyboard.press('Tab')
    await focused(inspector.getByRole('button',{name:'Close inspector'}))
    await page.keyboard.press('Enter')
    await focused(opener)
    checks.push(`${view}: remounted dock returns to logical opener`)
    await companion.getByRole('button',{name:`Close ${view} dock`,exact:true}).click()
  }
  // Compare action names include source, run and track, even for duplicate field/time choices.
  await page.getByRole('button',{name:'Series',exact:true}).click()
  await page.getByRole('button',{name:'Temporary Compare',exact:true}).click()
  await page.getByRole('combobox',{name:'Series B',exact:true}).selectOption('eccc-hrdps|temperature_2m')
  await page.waitForLoadState('networkidle')
  for(const summary of await page.locator('.native-track summary').all()) if(!await summary.evaluate(el=>el.parentElement.open)) await summary.click()
  const names=await page.getByRole('button',{name:/^Inspect temperature_2m at/}).evaluateAll(items=>items.map(el=>el.getAttribute('aria-label')))
  assert.equal(names.length,6)
  assert.equal(new Set(names).size,names.length)
  checks.push('Series identical field/time choices have distinct source/run/track names')
  await page.getByRole('button',{name:'Sky',exact:true}).click()
  await openWithKeyboard(page.getByRole('button',{name:'Inspect Sun altitude',exact:true}))
  assert.match(await inspector.textContent(),/nasa-jpl-de442/)
  for(const theme of ['light','dark','Red night']) {
    await page.getByRole('button',{name:theme,exact:true}).click()
    await page.screenshot({path:`${output}/sky-inspector-${theme.replaceAll(' ','-')}.png`})
  }
  // Geometry replacement must update this same selection, not discard it as a point-field miss.
  failAstronomy=true
  await page.locator('.bench-instant summary').click()
  await page.getByRole('textbox',{name:'Instant (ISO, with timezone)'}).fill('2026-09-07T12:00:12.345Z')
  await page.getByRole('button',{name:'Use instant',exact:true}).click()
  await page.locator('.bench-instant summary').click()
  await inspector.getByText(/astronomy returned 503/).waitFor()
  assert.doesNotMatch(await inspector.textContent(),/nasa-jpl-de442/)
  failAstronomy=false
  await page.locator('.bench-instant summary').click()
  await page.getByRole('textbox',{name:'Instant (ISO, with timezone)'}).fill('2026-09-07T12:00:24.567Z')
  await page.getByRole('button',{name:'Use instant',exact:true}).click()
  await page.locator('.bench-instant summary').click()
  await inspector.getByText('2026-09-07T12:00:24.567Z',{exact:true}).waitFor()
  assert.match(await inspector.textContent(),/nasa-jpl-de442/)
  checks.push('Sky open inspection clears failed geometry and follows recovered exact Focus')
  await inspector.getByRole('button',{name:'Close inspector'}).click()
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.evaluate(()=>{document.documentElement.style.fontSize='200%'})
  for(const view of ['Map','Series','Sources','Sky','Activity']) {
    await page.getByRole('button',{name:view,exact:true}).click()
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true)
    await page.screenshot({path:`${output}/${view}-zoom200.png`})
  }
  assert.match(await page.locator('#bench-stage').textContent(),/Server profile verdicts are not wired/)
  checks.push('All five shells at 200% text zoom and reduced motion; Activity absence explicitly retained')
  assert.deepEqual(errors,[])
  await writeFile(`${output}/receipt.json`,JSON.stringify({checks,axResults,errors,externalRequests:'blocked',screenReader:'not tested',activity:'body not implemented',requests},null,2))
  console.log(JSON.stringify({checks,axResults,errors},null,2))
} catch(error) {await page.screenshot({path:`${output}/failure.png`});throw error} finally {await browser.close()}
