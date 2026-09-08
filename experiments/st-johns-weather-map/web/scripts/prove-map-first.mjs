// Fixed-response browser proof. No live weather or reference-map provider calls.
import { chromium } from 'playwright'
import { mkdir, writeFile, mkdtemp } from 'node:fs/promises'
import assert from 'node:assert/strict'
import { tmpdir } from 'node:os'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5197'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-map-first-proof'
const before = process.env.BENCH_BEFORE === '1'
await mkdir(output, { recursive: true })
const at = '2026-09-07T12:00:00.000Z'
const layerId = 'eccc-hrdps-surface-total-cloud'
const layer = { id: layerId, title: 'HRDPS total cloud · fixed fixture with a deliberately long provider and layer label for truncation verification', kind: 'points', field: 'total_cloud', field_key: 'cloud_area_fraction_total', family: 'cloud_cover', product: 'HRDPS', units: '%', semantics: 'Fixed constructed test values; no live weather retrieval.', times: [at], staleness_tolerance_seconds: 3600, evidence_class: 'retrieved', evidence_basis: 'published_artifact', data_mode: 'fixture', raster_available: false }
const browser = await chromium.launchPersistentContext(await mkdtemp(`${tmpdir()}/map-first-chrome-`), { channel: 'chrome', headless: true, viewport: { width: 1440, height: 900 } })
const page = await browser.newPage()
await page.clock.install({ time: new Date(at) })
const errors = []; const requests = []; let failPoint = false; let releasePoint = null; let holdPoint = false; let failLayers = false
page.on('pageerror', (error) => errors.push(String(error)))
await page.route('**/*', async (route) => {
  const url = new URL(route.request().url())
  if (url.hostname === 'tiles.openfreemap.org') return route.continue()
  if (url.origin !== new URL(base).origin) return route.abort()
  if (!url.pathname.startsWith('/api/')) return route.continue()
  requests.push(url.pathname + url.search)
  const path = url.pathname.split('/v0')[1]
  let body = { data_mode: 'unavailable', notices: ['Fixed proof: capability not supplied'] }
  if (path === '/layers' && failLayers) return route.fulfill({status:503,contentType:'application/json',body:'{}'})
  if (path === '/point') {
    if (holdPoint) await new Promise(resolve => { releasePoint = resolve })
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
const chooseTheme = async name => {
  if (!before) await page.locator('.bench-settings > summary').click()
  await page.getByRole('button', { name, exact: true }).click()
  if (!before) await page.locator('.bench-settings > summary').click()
}
const measure = () => page.evaluate(() => {
  const box = document.querySelector('.map-pane').getBoundingClientRect()
  return { width: innerWidth, height: innerHeight, mapWidth: box.width, mapHeight: box.height, mapFraction: box.width * box.height / (innerWidth * innerHeight), header: document.querySelector('.bench-focus').getBoundingClientRect().height, timeline: document.querySelector('.bench-timeline').getBoundingClientRect().height, pageScrollX: document.documentElement.scrollWidth > innerWidth, pageScrollY: document.documentElement.scrollHeight > innerHeight }
})
const measurements = []
const controlsClear = async () => {
  const blocked = await page.evaluate(() => [...document.querySelectorAll('.bench-focus > button, .bench-focus > details > summary, .bench-time-slim > button, .bench-map .maplibregl-ctrl-group button, .bench-map-tools > button, .bench-overlay:not([hidden]) > .bench-view-heading > button')].filter(el => {
    const r=el.getBoundingClientRect(); if (!r.width || !r.height) return false
    const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)
    return !top || !(el===top || el.contains(top))
  }).map(el=>el.getAttribute('aria-label')||el.textContent))
  assert.deepEqual(blocked,[])
} 
try {
  await page.goto(`${base}/?lat=47.5123456789&lon=-52.6987654321&t=${at}`)
  await page.getByText('Development fixture', { exact: true }).first().waitFor()
  await page.waitForTimeout(2500)
  for (const [width,height] of [[1280,800],[1440,900],[1920,1080]]) {
    await page.setViewportSize({width,height})
    for (const theme of ['dark','light','Red night']) {
      await chooseTheme(theme)
      await page.waitForTimeout(350)
      const result = await measure(); measurements.push({theme, ...result})
      if (!before) { assert.ok(result.mapFraction >= .80, JSON.stringify(result)); assert.equal(result.header,56); assert.ok(result.timeline <= 80); assert.equal(result.pageScrollX,false); assert.equal(result.pageScrollY,false) }
      await page.screenshot({path:`${output}/${before ? 'before' : 'after'}-${width}x${height}-${theme.replace(' ','-')}-closed.png`})
      if (!before) await page.getByRole('button',{name:'Layers',exact:true}).click()
      await page.screenshot({path:`${output}/${before ? 'before' : 'after'}-${width}x${height}-${theme.replace(' ','-')}-open.png`})
      if (!before) { await controlsClear(); assert.equal((await measure()).mapWidth,result.mapWidth); assert.equal((await measure()).mapHeight,result.mapHeight); await page.getByRole('button',{name:'Close Layers',exact:true}).click() }
    }
  }
  if (!before) {
    await page.setViewportSize({width:1280,height:800}); await chooseTheme('dark')
    await page.getByRole('button',{name:'Layers',exact:true}).click()
    await page.getByRole('button',{name:'Browse',exact:true}).click()
    await page.getByRole('searchbox',{name:'Search layers'}).fill('no matches')
    await page.getByText('No matching published layers.').waitFor()
    await page.getByRole('searchbox',{name:'Search layers'}).fill('HRDPS')
    assert.equal(await page.locator('.bench-browse-list > li').count(),1)
    await page.screenshot({path:`${output}/browse-search.png`})
    await page.getByRole('button',{name:/Active ·/}).click()
    const row = page.locator('.bench-stack ol > li').filter({has:page.locator(`strong[title^="HRDPS total cloud"]`)})
    await row.locator('summary').click()
    const opacity = row.getByRole('slider'); await opacity.focus(); await page.keyboard.press('ArrowLeft')
    const opacityValue = await opacity.inputValue(); assert.equal(opacityValue,'0.8')
    await row.getByRole('checkbox').uncheck(); assert.equal(await row.getByRole('checkbox').isChecked(),false)
    await row.getByRole('button',{name:/Raise /}).click()
    const editedStack = new URL(page.url()).searchParams.get('stack')
    assert.ok(editedStack.includes('0.8'))
    await page.getByText('Stacks',{exact:true}).click()
    await page.getByRole('textbox',{name:'Stack name'}).fill('Browser proof')
    await page.getByRole('button',{name:'Save stack',exact:true}).click()
    await row.getByRole('button',{name:/Remove /}).click()
    await page.getByRole('button',{name:'Browse',exact:true}).click()
    await page.getByRole('button',{name:/^Add HRDPS/}).click()
    assert.ok(new URL(page.url()).searchParams.get('stack').includes(layerId))
    await page.getByRole('button',{name:/Active ·/}).click()
    await page.getByRole('combobox',{name:'Saved stacks'}).selectOption('Browser proof')
    assert.equal(new URL(page.url()).searchParams.get('stack'),editedStack)
    await page.getByText('Stacks',{exact:true}).click()
    await row.locator('summary').click()
    await row.getByRole('button',{name:/Inspect layer/}).click()
    await page.getByRole('complementary',{name:'Evidence inspector',exact:true}).waitFor()
    await page.waitForFunction(()=>document.activeElement?.textContent?.startsWith('Evidence ·'))
    await page.screenshot({path:`${output}/provenance-open.png`})
    await page.keyboard.press('Escape')
    await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')?.startsWith('Inspect layer'))
    assert.equal(await row.getByRole('button',{name:/Inspect layer/}).evaluate(el=>el===document.activeElement),true)
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('button',{name:'Layers',exact:true}).evaluate(el=>el===document.activeElement),true)
    await page.getByRole('button',{name:'Evidence',exact:true}).click()
    await page.getByText('Point evidence ledger',{exact:true}).click()
    const inspect = page.getByRole('button',{name:/^Inspect temperature from noaa\-gfs/})
    await page.screenshot({path:`${output}/evidence-open.png`})
    await inspect.click(); await page.waitForFunction(()=>document.activeElement?.textContent?.startsWith('Evidence ·')); await page.keyboard.press('Escape')
    await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')?.startsWith('Inspect temperature'))
    assert.equal(await inspect.evaluate(el=>el===document.activeElement),true)
    await page.keyboard.press('Escape')
    const restoreUrl = page.url()
    await page.reload(); await page.getByText('Development fixture',{exact:true}).first().waitFor()
    assert.equal(page.url(),restoreUrl)
    assert.equal(await page.getByRole('button',{name:'Layers',exact:true}).getAttribute('aria-expanded'),'false')
    await page.locator('.bench-view-menu > summary').click()
    await page.getByRole('button',{name:'Dock Series',exact:true}).click()
    await page.getByRole('button',{name:'Dock Sky',exact:true}).click()
    assert.equal(await page.getByRole('complementary',{name:'Series companion',exact:true}).count(),0)
    await page.getByRole('button',{name:'Close Sky dock',exact:true}).click()
    const canvas = page.locator('.maplibregl-canvas'); const handle = await canvas.elementHandle()
    await canvas.focus(); await page.keyboard.press('ArrowRight'); await page.waitForTimeout(500)
    await page.mouse.move(500,250); await page.mouse.down(); await page.mouse.move(740,250,{steps:10}); await page.mouse.up(); await page.waitForTimeout(600)
    const scale = await page.locator('.maplibregl-ctrl-scale').textContent()
    await canvas.click({position:{x:640,y:336}})
    await page.waitForFunction(()=>new URL(location.href).searchParams.get('lat')!=='47.5123456789')
    const pointBefore = ['lat','lon'].map(key=>new URL(page.url()).searchParams.get(key))
    for (const view of ['Series','Sky','Activity','Sources','Map']) {
      await page.locator('.bench-view-menu > summary').click()
      await page.getByRole('navigation',{name:'Evidence views'}).getByRole('button',{name:view,exact:true}).click()
      await page.getByRole('heading',{name:view,exact:true}).waitFor()
      for (const theme of ['dark','light','Red night']) { await chooseTheme(theme); await page.screenshot({path:`${output}/view-${view}-${theme.replace(' ','-')}.png`}) }
      await chooseTheme('dark')
    }
    assert.equal(await handle.evaluate(el=>el===document.querySelector('.maplibregl-canvas')),true)
    assert.equal(await page.locator('.maplibregl-ctrl-scale').textContent(),scale)
    assert.deepEqual(['lat','lon'].map(key=>new URL(page.url()).searchParams.get(key)),pointBefore)
    await canvas.click({position:{x:640,y:336}})
    await page.waitForTimeout(100)
    const pointAfter = ['lat','lon'].map(key=>new URL(page.url()).searchParams.get(key))
    pointAfter.forEach((value,index)=>assert.ok(Math.abs(Number(value)-Number(pointBefore[index]))<1e-8, `Camera changed: ${pointBefore} -> ${pointAfter}`))
    await page.getByRole('button',{name:'Timeline details',exact:true}).click()
    const openMeasure = await measure(); assert.ok(openMeasure.mapFraction>=.80)
    await page.screenshot({path:`${output}/timeline-open.png`})
    await page.getByRole('button',{name:'Close timeline details',exact:true}).click()
    await page.getByRole('button',{name:'Weather story',exact:true}).click()
    assert.equal((await measure()).mapHeight,openMeasure.mapHeight)
    await page.screenshot({path:`${output}/weather-story-open.png`})
    await page.getByRole('button',{name:'Weather story',exact:true}).click()
    // Set real Chrome page zoom, then verify the CSS viewport and device pixel ratio.
    const settings = await browser.newPage(); await settings.goto('chrome://settings/appearance'); await settings.locator('#zoomLevel').selectOption({label:'200%'}); await settings.close()
    for (const [width,height] of [[1280,800],[1440,900],[1920,1080]]) {
      await page.setViewportSize({width,height})
      assert.equal(await page.evaluate(()=>innerWidth),width/2)
      assert.equal(await page.evaluate(()=>devicePixelRatio),2)
      for (const theme of ['dark','light','Red night']) {
        await chooseTheme(theme)
        const result=await measure(); assert.equal(result.pageScrollX,false); assert.equal(result.pageScrollY,false)
        await page.screenshot({path:`${output}/zoom200-${width}x${height}-${theme.replace(' ','-')}-closed.png`})
        await page.getByRole('button',{name:'Layers',exact:true}).click()
        await controlsClear()
        await page.screenshot({path:`${output}/zoom200-${width}x${height}-${theme.replace(' ','-')}-open.png`})
        await page.getByRole('button',{name:'Close Layers',exact:true}).click()
        if (width === 1280) for (const view of ['Series','Sky','Activity','Sources','Map']) {
          await page.locator('.bench-view-menu > summary').click()
          await page.getByRole('navigation',{name:'Evidence views'}).getByRole('button',{name:view,exact:true}).click()
          const result=await measure(); assert.equal(result.pageScrollX,false); assert.equal(result.pageScrollY,false)
          await page.screenshot({path:`${output}/zoom200-view-${view}-${theme.replace(' ','-')}.png`})
        }
      }
    }
    holdPoint=true; failLayers=true
    await page.goto(`${base}/?t=${at}`)
    await page.getByText('Loading point evidence',{exact:true}).waitFor()
    await page.screenshot({path:`${output}/loading-point.png`})
    await page.getByRole('button',{name:'Layers',exact:true}).click()
    await page.getByText(/Layers unavailable:/).waitFor()
    await page.screenshot({path:`${output}/failed-layers.png`})
    holdPoint=false; releasePoint?.(); await page.getByText('Development fixture',{exact:true}).waitFor()
    failPoint=true
    await page.goto(`${base}/?lat=48.123456789&lon=-52.6987654321&t=${at}&stack=[]`)
    await page.getByText('Unavailable',{exact:true}).first().waitFor()
    assert.equal(new URL(page.url()).searchParams.get('lat'),'48.123456789')
    await page.screenshot({path:`${output}/failed-request.png`})
  }
  assert.deepEqual(errors,[])
  await writeFile(`${output}/${before?'before':'after'}-receipt.json`,JSON.stringify({at,measurements,weather:'constructed fixtures; no live weather requests',referenceMap:'OpenFreeMap tiles allowed',zoom:'Native Chrome page zoom 200%; verified innerWidth is half physical viewport and devicePixelRatio is 2',requests,errors},null,2))
  console.log(`PASS: ${output}`)
} finally { await browser.close() }
