// Constructed weather responses; live OpenFreeMap reference tiles.
import { chromium } from 'playwright'
import { mkdir, writeFile, mkdtemp } from 'node:fs/promises'
import assert from 'node:assert/strict'
import { tmpdir } from 'node:os'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5197'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-timeline-proof'
const before = process.env.BENCH_BEFORE === '1'
await mkdir(output, { recursive: true })
const at = '2026-09-07T12:00:00.000Z'
const layerId = 'eccc-hrdps-surface-total-cloud'
const layer = { id: layerId, title: 'HRDPS total cloud · fixed fixture with a deliberately long provider and layer label for truncation verification', kind: 'points', field: 'total_cloud', field_key: 'cloud_area_fraction_total', family: 'cloud_cover', product: 'HRDPS', units: '%', semantics: 'Fixed constructed test values; no live weather retrieval.', times: [at], staleness_tolerance_seconds: 3600, evidence_class: 'retrieved', evidence_basis: 'published_artifact', data_mode: 'fixture', raster_available: false }
const reference = Date.parse(at)
const iso = minutes => new Date(reference + minutes * 60000).toISOString()
const frames = (first,last,step) => Array.from({length:Math.floor((last-first)/step)+1},(_,index)=>iso(first+index*step))
const fixtureLayers = [
  {...layer, group:'published_model', times:frames(-1440,1440,60), cadence_seconds:3600, frames:frames(-1440,1440,60).map((time,index)=>({valid_time:time,run_time:iso(index<30?-360:-720),run_stale:index>=30,provider_run_id:'fixture'}))},
  {...layer,id:'eccc-radar-radar',title:'Radar precipitation · 6 minute observations', group:'observation', times:frames(-1440,0,6),cadence_seconds:360},
  {...layer,id:'geomet-live-goes-east-naturalcolor',title:'GOES satellite · 10 minute observations',group:'satellite',times:frames(-1440,0,10),cadence_seconds:600},
  {...layer,id:'six-hour-forecast',title:'Long range model · 6 hour forecast',group:'published_model',times:frames(1440,20160,360),cadence_seconds:21600},
  {...layer,id:'missing-history',title:'Unavailable historical imagery with a deliberately long source label',times:[],group:'observation',raster_available:false},
]
const stack = fixtureLayers.map(layer=>({id:layer.id,visible:true,opacity:.85}))
const browser = await chromium.launchPersistentContext(await mkdtemp(`${tmpdir()}/map-first-chrome-`), { channel: 'chrome', headless: true, viewport: { width: 1440, height: 900 } })
const page = await browser.newPage()
await page.clock.install({ time: new Date(at) })
await page.clock.pauseAt(new Date(at))
const errors = []; const requests = []; let failPoint = false; let releasePoint = null; let holdPoint = false; let failLayers = false; let failTimeline = false
page.on('pageerror', (error) => errors.push(String(error)))
await page.route('**/*', async (route) => {
  const url = new URL(route.request().url())
  if (url.hostname === 'tiles.openfreemap.org') return route.continue()
  if (url.origin !== new URL(base).origin) return route.abort()
  if (!url.pathname.startsWith('/api/')) return route.continue()
  requests.push(url.pathname + url.search)
  const path = url.pathname.split('/v0')[1]
  let body = { data_mode: 'unavailable', notices: ['Fixed proof: capability not supplied'] }
  if (path === '/timeline' && failTimeline) return route.fulfill({status:503,contentType:'application/json',body:'{}'})
  if (path === '/layers' && failLayers) return route.fulfill({status:503,contentType:'application/json',body:'{}'})
  if (path === '/point') {
    if (holdPoint) await new Promise(resolve => { releasePoint = resolve })
    if (failPoint) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Fixed failure' }) })
    body = { latitude: Number(url.searchParams.get('latitude')), longitude: Number(url.searchParams.get('longitude')), valid_time: url.searchParams.get('valid_time'), data_mode: 'fixture', selection: { mode: 'evidence_only', badge: 'Fixed browser fixture', reason: 'Constructed values, no provider retrieval' }, fields: [
      { field: 'temperature', value: 0, key: 'air_temperature_2m', family: 'temperature', provenance: { source_id: 'noaa-gfs', provider: 'NOAA', product: 'GFS', normalized_units: 'degC', evidence_class: 'retrieved', data_mode: 'fixture', valid_time: at, quality: { status: 'unknown', flags: [] }, artifact_revision: 'fixed-proof', sample: { latitude: 47.5, longitude: -52.6 } } },
      { field: 'total_cloud', value: 65, family: 'cloud_cover', provenance: { source_id: 'eccc-hrdps', provider: 'ECCC', product: 'HRDPS', normalized_units: '%', evidence_class: 'retrieved', data_mode: 'fixture', valid_time: at, quality: { status: 'unknown', flags: [] } } },
    ], notices: ['FIXED CONSTRUCTED BROWSER PROOF · not live evidence'] }
  } else if (path === '/layers') body = { data_mode: 'fixture', layers: url.searchParams.get('product') === 'CAP' ? [] : fixtureLayers, notices: [] }
  else if (path.endsWith('/features')) body = { type: 'FeatureCollection', data_mode: 'fixture', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-52.6, 47.5] }, properties: { value: 65 } }] }
  else if (path === '/catalog') body = { data_mode: 'fixture', sources: [] }
  else if (path === '/sources/status') body = { data_mode: 'fixture', statuses: [], notices: [] }
  else if (path === '/methods') body = { data_mode: 'fixture', methods: [], notices: [] }
  else if (path === '/timeline') body = { data_mode: 'fixture', start: iso(-1440), end: iso(20160), boundary:iso(1440), items: [] }
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
const selected = () => page.locator('.bench-time-selected time').getAttribute('datetime')
const measurements=[]
try {
  await page.goto(`${base}/?lat=47.5123456789&lon=-52.6987654321&t=${at}&stack=${encodeURIComponent(JSON.stringify(stack))}`)
  await page.getByRole('button',{name:'Tracks',exact:true}).waitFor()
  await page.waitForTimeout(2000)
  assert.equal(await page.getByRole('combobox',{name:'Timeline range'}).inputValue(),'near')
  for (const interval of [1,2,4,8,15,30]) {
    await page.getByRole('button',{name:'Now',exact:true}).click()
    await page.getByRole('combobox',{name:'Step and playback interval'}).selectOption(String(interval))
    await page.getByRole('button',{name:`Step forward ${interval} minutes`,exact:true}).click()
    assert.equal(await selected(),iso(interval))
    await page.getByRole('button',{name:`Step backward ${interval} minutes`,exact:true}).click()
    assert.equal(await selected(),at)
    await page.getByRole('button',{name:'Play',exact:true}).click()
    await page.clock.runFor(1000)
    assert.equal(await selected(),iso(interval))
    await page.getByRole('button',{name:'Pause',exact:true}).click()
  }
  await page.getByRole('button',{name:'Now',exact:true}).click()
  await page.getByRole('combobox',{name:'Step and playback interval'}).selectOption('2')
  await page.getByRole('button',{name:'Reverse',exact:true}).click()
  await page.getByRole('button',{name:'Play',exact:true}).click(); await page.clock.runFor(1000)
  assert.equal(await selected(),iso(-2))
  await page.getByRole('button',{name:'Next frame',exact:true}).click()
  assert.equal(await selected(),at)
  assert.equal(await page.getByRole('button',{name:'Play',exact:true}).count(),1)
  await page.getByRole('button',{name:'Reverse',exact:true}).click()
  const scrubber=page.getByRole('slider',{name:'Valid timeline scrubber'})
  const scrubBox=await scrubber.boundingBox()
  await page.getByRole('button',{name:'Play',exact:true}).click()
  await page.mouse.move(scrubBox.x+scrubBox.width/2,scrubBox.y+scrubBox.height/2)
  await page.mouse.down(); await page.mouse.move(scrubBox.x+scrubBox.width*.7,scrubBox.y+scrubBox.height/2,{steps:6}); await page.mouse.up()
  assert.equal(await page.getByRole('button',{name:'Play',exact:true}).count(),1)
  assert.ok(fixtureLayers.flatMap(layer=>layer.times).includes(await selected()))
  await page.getByRole('button',{name:'Now',exact:true}).click()
  for (const [width,height] of [[1280,800],[1440,900],[1920,1080]]) {
    await page.setViewportSize({width,height})
    for (const theme of ['dark','light','Red night']) {
      await chooseTheme(theme)
      await page.clock.runFor(100)
      const result=await measure(); measurements.push({theme,...result})
      assert.ok(result.mapFraction>=.8,JSON.stringify(result)); assert.equal(result.timeline,80)
      if(result.pageScrollX || result.pageScrollY) { await page.screenshot({path:`${output}/overflow.png`}); console.log(JSON.stringify(await page.evaluate(()=>[...document.querySelectorAll('.bench-timeline *')].map(el=>({name:el.className,top:el.getBoundingClientRect().top,bottom:el.getBoundingClientRect().bottom,height:el.getBoundingClientRect().height})).filter(el=>el.bottom>innerHeight)))) }
      assert.equal(result.pageScrollX,false); assert.equal(result.pageScrollY,false)
      await page.screenshot({path:`${output}/after-${width}x${height}-${theme.replace(' ','-')}-closed.png`})
      await page.getByRole('button',{name:'Tracks',exact:true}).click()
      await page.clock.runFor(100)
      assert.equal((await measure()).mapHeight,result.mapHeight)
      await page.screenshot({path:`${output}/after-${width}x${height}-${theme.replace(' ','-')}-tracks.png`})
      await page.getByRole('button',{name:'Close tracks',exact:true}).click()
      assert.equal(await page.getByRole('button',{name:'Tracks',exact:true}).evaluate(el=>el===document.activeElement),true)
    }
  }
  await chooseTheme('dark')
  await page.getByRole('combobox',{name:'Timeline range'}).selectOption('outlook')
  await page.clock.runFor(100)
  const cluster=page.getByRole('group',{name:'Published frames',exact:true}).getByRole('button',{name:/frame times/}).first()
  await cluster.click()
  await page.getByRole('dialog',{name:'Choose a native frame'}).waitFor()
  await page.screenshot({path:`${output}/outlook-frame-chooser.png`})
  const native=page.locator('.timeline-frame-chooser .timeline-frame-list button').first()
  const nativeText=await native.textContent(); const exact=nativeText.match(/UTC (\S+)/)[1]
  await native.click(); assert.equal(await selected(),exact)
  assert.equal(await cluster.evaluate(el=>el===document.activeElement),true)
  await page.getByRole('combobox',{name:'Timeline range'}).selectOption('near')
  assert.equal(await selected(),exact)
  await page.getByRole('button',{name:/Selected time .* range/}).click()
  assert.equal(await page.getByRole('combobox',{name:'Timeline range'}).inputValue(),'outlook')
  await page.getByRole('button',{name:'Tracks',exact:true}).click()
  await page.getByText('Frame timestamp list',{exact:true}).click()
  await page.getByRole('searchbox').fill('Radar')
  assert.ok(await page.locator('.timeline-frame-list button').count()>0)
  await page.getByRole('searchbox').fill('no-such-native-frame')
  await page.getByText('No matching published frames.',{exact:true}).waitFor()
  await page.keyboard.press('Escape')
  const restoredUrl=page.url(); await page.reload(); await page.getByRole('button',{name:'Tracks',exact:true}).waitFor()
  assert.equal(await selected(),exact)
  assert.equal(await page.getByRole('combobox',{name:'Timeline range'}).inputValue(),'outlook')
  assert.equal(await page.getByRole('button',{name:'Tracks',exact:true}).getAttribute('aria-expanded'),'false')
  assert.equal(new URL(page.url()).searchParams.get('t'),new URL(restoredUrl).searchParams.get('t'))
  await page.getByRole('button',{name:'Now',exact:true}).click()
  await page.getByRole('combobox',{name:'Timeline range'}).selectOption('near')
  for (const [width,height] of [[1280,800],[1440,900],[1920,1080]]) {
    await page.setViewportSize({width,height})
    const cdp=await browser.newCDPSession(page)
    // Native browser zoom via the same Chrome settings API as the map-first proof.
    const settings=await browser.newPage(); await settings.goto('chrome://settings/')
    await settings.evaluate(()=>chrome.settingsPrivate.setDefaultZoom(2))
    await settings.close(); await cdp.detach()
    assert.equal(await page.evaluate(()=>innerWidth),width/2)
    for(const theme of ['dark','light','Red night']) {
      await chooseTheme(theme); await page.clock.runFor(100)
      const result=await measure(); if(result.pageScrollX || result.pageScrollY) { await page.screenshot({path:`${output}/overflow.png`}); console.log(JSON.stringify(await page.evaluate(()=>[...document.querySelectorAll('.bench-timeline *')].map(el=>({name:el.className,top:el.getBoundingClientRect().top,bottom:el.getBoundingClientRect().bottom,height:el.getBoundingClientRect().height})).filter(el=>el.bottom>innerHeight)))) }
      assert.equal(result.pageScrollX,false); assert.equal(result.pageScrollY,false)
      await page.screenshot({path:`${output}/zoom200-${width}x${height}-${theme.replace(' ','-')}-closed.png`})
      await page.getByRole('button',{name:'Tracks',exact:true}).click(); await page.clock.runFor(100)
      await page.screenshot({path:`${output}/zoom200-${width}x${height}-${theme.replace(' ','-')}-tracks.png`})
      await page.getByRole('button',{name:'Close tracks',exact:true}).click()
    }
  }
  failTimeline=true
  await page.goto(`${base}/?t=${at}&stack=[]`)
  await page.getByRole('button',{name:'Tracks',exact:true}).waitFor()
  await page.getByRole('button',{name:'Tracks',exact:true}).click()
  await page.getByText('Coverage and display settings',{exact:true}).click()
  await page.getByText(/Coverage unavailable:/).waitFor()
  await page.screenshot({path:`${output}/timeline-request-failed.png`})
  await writeFile(`${output}/results.json`,JSON.stringify({measurements,errors,requests,checks:'Pointer scrubbing; timeline request failure; all interval steps/playback; reverse; manual pause; exact clustered frame; focus return; search; range preservation; URL restoration; themes, sizes and native 200% zoom'},null,2))
  assert.deepEqual(errors,[])
  console.log(JSON.stringify({output,screenshots:38,measurements,errors}))
} finally { await browser.close() }
