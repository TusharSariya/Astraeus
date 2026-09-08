// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5198'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-series-proof'
await mkdir(output, { recursive: true })
const sharedFixture = process.env.SOURCE_DELIVERY_FIXTURE === '1' ? JSON.parse(await readFile(new URL('../../contracts/fixtures/source-delivery.json', import.meta.url), 'utf8')) : null
const companionFixture = process.env.SOURCE_COMPANION_FIXTURE ? JSON.parse(await readFile(process.env.SOURCE_COMPANION_FIXTURE, 'utf8')) : null
let companionMode = null
const sharedRequests = []
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
    if (sharedFixture && url.searchParams.get('product') === 'CAMS AOD') return route.fulfill({ contentType: 'application/json', body: JSON.stringify(sharedFixture.point_cams_aod) })
    if (companionMode) return route.fulfill({ contentType: 'application/json', body: JSON.stringify(companionFixture[companionMode]) })
    if (failPoint) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Fixed failure' }) })
    body = { latitude: Number(url.searchParams.get('latitude')), longitude: Number(url.searchParams.get('longitude')), valid_time: url.searchParams.get('valid_time'), data_mode: 'fixture', selection: { mode: 'evidence_only', badge: 'Fixed browser fixture', reason: 'Constructed values, no provider retrieval' }, fields: [
      { field: 'temperature', value: 0, key: 'air_temperature_2m', family: 'temperature', provenance: { source_id: 'noaa-gfs', provider: 'NOAA', product: 'GFS', normalized_units: 'degC', evidence_class: 'retrieved', data_mode: 'fixture', valid_time: at, quality: { status: 'unknown', flags: [] }, artifact_revision: 'fixed-proof', sample: { latitude: 47.5, longitude: -52.6 } } },
      { field: 'total_cloud', value: 65, family: 'cloud_cover', provenance: { source_id: 'eccc-hrdps', provider: 'ECCC', product: 'HRDPS', normalized_units: '%', evidence_class: 'retrieved', data_mode: 'fixture', valid_time: at, quality: { status: 'unknown', flags: [] } } },
    ], notices: ['FIXED CONSTRUCTED BROWSER PROOF · not live evidence'] }
  } else if (path === '/layers') body = { data_mode: 'fixture', layers: url.searchParams.get('product') === 'CAP' ? [] : [layer], notices: [] }
  else if (path.endsWith('/features')) body = { type: 'FeatureCollection', data_mode: 'fixture', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-52.6, 47.5] }, properties: { value: 65 } }] }
  else if (path === '/catalog') body = sharedFixture?.catalog ?? { data_mode: 'fixture', sources: [] }
  else if (path === '/sources/status') body = sharedFixture?.status ?? { data_mode: 'fixture', statuses: [], notices: [] }
  else if (path === '/methods') body = { data_mode: 'fixture', methods: [], notices: [] }
  else if (path === '/timeline') body = { data_mode: 'fixture', start: '2026-09-07T09:00:00Z', end: '2026-09-08T12:00:00Z', items: [] }
  else if (path === '/point/series') {
    if (sharedFixture) { sharedRequests.push(route.request().postDataJSON()); return route.fulfill({ contentType: 'application/json', body: JSON.stringify(sharedFixture.series) }) }
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
if (sharedFixture) {
  try {
    if (companionFixture) {
      for (const mode of ['success', 'failure']) {
        companionMode = mode
        const point = companionFixture[mode]
        await page.goto(`${base}/?view=sources&lat=${point.latitude}&lon=${point.longitude}&t=${point.valid_time}`)
        const row = page.getByRole('row').filter({ has: page.getByRole('button', { name: 'Inspect source eccc-aqhi', exact: true }) })
        await row.waitFor()
        if (mode === 'success') {
          await page.getByRole('button', { name: 'Map', exact: true }).click()
          await page.getByText('Point evidence ledger', { exact: true }).click()
          const inspect = page.getByRole('button', { name: /^Inspect aqhi from eccc-aqhi/ })
          await inspect.click()
          const inspector = page.getByRole('complementary', { name: 'Evidence inspector' })
          await inspector.getByRole('heading', { name: 'Evidence · aqhi', exact: true }).waitFor()
          assert.ok((await inspector.innerText()).includes('ABEFS'))
          assert.ok((await inspector.innerText()).includes('2.7'))
          assert.ok((await inspector.innerText()).includes('eccc-aqhi'))
          assert.equal(await inspector.locator('dt', { hasText: /^Product$/ }).locator('..').innerText().then((text) => text.includes('HRDPS')), false)
          await page.screenshot({ path: `${output}/assembled-aqhi-native-identity.png` })
        } else {
          await row.getByText('Observation refresh_failed · HTTPStatusError. Values withheld; selected model unchanged.', { exact: true }).waitFor()
          await row.getByRole('button', { name: 'Inspect source eccc-aqhi', exact: true }).click()
          const inspector = page.getByRole('complementary', { name: 'Evidence inspector' })
          assert.ok((await inspector.innerText()).includes('refresh_failed'))
          assert.equal((await page.locator('body').innerText()).includes('private-provider-exception'), false)
          await page.screenshot({ path: `${output}/assembled-aqhi-failure.png` })
        }
      }
      companionMode = null
    }
    // Select the declared point token in the assembled app; consume the exact
    // backend fixture without turning intermediary hourly labels into Series.
    const cams = sharedFixture.point_cams_aod
    await page.goto(`${base}/?view=map&lat=${cams.latitude}&lon=${cams.longitude}&t=${cams.valid_time}`)
    await page.getByRole('button', { name: 'Existing evidence panels', exact: true }).click()
    await page.locator('summary').filter({ hasText: /^Forecast model/ }).click()
    await page.locator('.model-buttons button').filter({ hasText: 'CAMS AOD' }).click()
    await page.getByText('CAMS AOD via Open-Meteo', { exact: true }).first().waitFor()
    assert.ok(requests.some((request) => {
      const url = new URL(request, base)
      return url.pathname.endsWith('/point') && url.searchParams.get('product') === 'CAMS AOD'
        && Number(url.searchParams.get('latitude')) === cams.latitude
        && Number(url.searchParams.get('longitude')) === cams.longitude
        && Date.parse(url.searchParams.get('valid_time')) === Date.parse(cams.valid_time)
    }))
    await page.getByRole('button', { name: 'Return to desktop Bench', exact: true }).click()
    await page.getByText('Point evidence ledger', { exact: true }).click()
    const camsOpener = page.getByRole('button', { name: /^Inspect aerosol_optical_depth_550nm from openmeteo-cams-aod/ })
    await camsOpener.click()
    const camsInspector = page.getByRole('complementary', { name: 'Evidence inspector' })
    const detail = async (name) => camsInspector.locator('dt').filter({ hasText: new RegExp(`^${name}$`) }).locator('..').locator('dd').innerText()
    assert.equal(await detail('Source'), 'openmeteo-cams-aod')
    assert.equal(await detail('Intermediary'), 'Open-Meteo')
    assert.equal(await detail('Run'), 'Not supplied')
    assert.equal(await detail('Delivery kind'), 'reprocessed')
    assert.equal(Date.parse(await detail('Native valid time')), Date.parse(cams.valid_time))
    const returned = JSON.parse(await detail('Complete returned provenance'))
    assert.equal(returned.display_primary_eligible, false)
    assert.equal(returned.operational, false)
    assert.equal(returned.run_time, null)
    assert.equal(returned.data_mode, 'fixture')
    assert.ok((await camsInspector.innerText()).includes('0.15'))
    await page.screenshot({ path: `${output}/cams-aod-exact-point-provenance.png` })
    await page.keyboard.press('Escape')
    assert.equal(await camsOpener.evaluate((element) => element === document.activeElement), true)
    await page.getByRole('button', { name: 'Series', exact: true }).click()
    const seriesOptions = await page.getByRole('combobox', { name: 'Series A', exact: true }).locator('option').allTextContents()
    assert.equal(seriesOptions.some((option) => /cams|aerosol_optical_depth/i.test(option)), false)
    await page.screenshot({ path: `${output}/cams-aod-no-native-series.png` })
    const selection = sharedFixture.series.selection
    await page.goto(`${base}/?view=series&lat=${selection.latitude}&lon=${selection.longitude}&t=${at}`)
    await page.getByRole('img', { name: /temperature_2m native samples/ }).waitFor()
    assert.deepEqual(sharedRequests.at(-1), { ...selection, start: new Date(selection.start).toISOString(), end: new Date(selection.end).toISOString() })
    const selector = page.getByRole('combobox', { name: 'Series A', exact: true })
    assert.ok(await selector.locator('option').count() > 2)
    await selector.scrollIntoViewIfNeeded()
    await page.screenshot({ path: `${output}/source-delivery-selectors.png` })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    await selector.focus()
    await page.keyboard.press('Tab')
    assert.equal(await page.locator('.native-track').count(), 2)
    await page.getByText(/Native values, gaps and run identity/).first().click()
    const opener = page.getByRole('button', { name: /^Inspect temperature_2m at/ }).first()
    await opener.click()
    await page.getByRole('heading', { name: 'Evidence · temperature_2m', exact: true }).waitFor()
    await page.keyboard.press('Escape')
    assert.equal(await opener.evaluate((el) => el === document.activeElement), true)
    await page.screenshot({ path: `${output}/source-delivery-series.png` })
    await page.getByRole('button', { name: 'Sources', exact: true }).click()
    for (const status of sharedFixture.status.statuses) {
      const row = page.getByRole('row').filter({ has: page.getByRole('button', { name: `Inspect source ${status.source_id}`, exact: true }) })
      assert.ok((await row.innerText()).includes(`Configuration: ${status.configuration.state}`))
      assert.ok((await row.innerText()).includes(status.configuration.reason))
    }
    await page.screenshot({ path: `${output}/source-delivery-sources.png` })
    await page.getByRole('button', { name: 'Series', exact: true }).click()
    await page.clock.runFor(300001)
    await page.getByText('Selection expired. Refresh Series to read again.', { exact: true }).waitFor()
    assert.equal(await page.locator('.native-track').count(), 0)
    assert.equal(await page.getByRole('button', { name: 'Check for changes', exact: true }).isDisabled(), true)
    assert.deepEqual(errors, [])
    await writeFile(`${output}/source-delivery-checks.json`, JSON.stringify({ fixture: 'contracts/fixtures/source-delivery.json', exactBackendResponses: ['catalog', 'status', 'series', 'point_cams_aod', ...(companionFixture ? ['selected-model AQHI success', 'selected-model AQHI failure'] : [])], companionProof: companionFixture?.proof ?? null, nativeRequests: sharedRequests, checks: ['declarative choices without point samples', 'exact native request identity', 'configuration dispositions', 'inspector focus return', 'finite expiry', 'CAMS exact point selection and provenance', 'CAMS non-primary no native Series'], pointRequests: requests.filter((request) => request.includes('/point?')), weatherProviderRequests: 0, externalRequests: 'blocked', errors }, null, 2))
    console.log('Source delivery shared backend fixture proof passed')
  } catch (error) {
    await page.screenshot({ path: `${output}/failure.png` })
    await writeFile(`${output}/failure.txt`, await page.locator('body').innerText())
    throw error
  } finally { await browser.close() }
  process.exit(0)
}
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
  await page.getByRole('button', { name: 'Series', exact: true }).click()
  await page.getByRole('img', { name: /temperature_2m native samples/ }).waitFor()
  assert.equal(await page.locator('.native-track circle').count(), 4)
  assert.equal(await page.getByText('native_sample_missing', { exact: true }).count(), 2)
  await page.screenshot({ path: `${output}/series-overview.png` })
  await page.locator('.native-track summary').first().click()
  const nativeInspect = page.getByRole('button', { name: /^Inspect temperature_2m at 2026\-09\-07T12:00:00\.000Z/, exact: true })
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
  // A failed selection must clear the old zero, while preserving exact Focus.
  failPoint = true
  await page.goto(`${base}/?lat=48.123456789&lon=-52.6987654321&t=${at}&stack=[]`)
  await page.getByText('Unavailable', { exact: true }).first().waitFor()
  assert.equal(new URL(page.url()).searchParams.get('lat'), '48.123456789')
  assert.ok(requests.some((url) => url.includes('latitude=47.5123456789') && url.includes('valid_time=2026-09-07T12')))
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ at, viewport: '1440x900', weatherProviderRequests: 0, externalRequests: 'blocked', checks: ['exact Focus request', 'inspector focus and Escape return', 'dock replacement', 'three themes', '200% text zoom without page overflow', 'failed read clears values', 'native Series zero and missing sample', 'separate axes', 'Compare preserves pin', 'non-mutating change check', 'failed refresh preserves labelled selection', 'fixed expiry clears expired Series'], requests, errors }, null, 2))
  console.log(`PASS: fixed desktop Bench and Series proof at ${output}`)
} finally { await browser.close() }
