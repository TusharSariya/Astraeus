// Replay real native point receipts against current catalogue. No weather acquisition.
import { chromium } from 'playwright'
import { readFile, mkdir, writeFile, mkdtemp } from 'node:fs/promises'
import assert from 'node:assert/strict'
const dir=process.env.WN3_PROOF_DIR ?? '/private/tmp/astraeus-wn3-surface-proof'
const base=process.env.BENCH_URL ?? 'http://127.0.0.1:5323'
const catalog=await (await fetch(`${base}/api/experiments/weather/v0/catalog`)).json()
let point=JSON.parse(await readFile(`${dir}/live-cloud.json`,'utf8'))
const source=catalog.sources.find(s=>s.id==='google-weathernext-3-statistics')
assert.equal(source.capabilities.length,252)
let cap=source.capabilities.find(c=>c.field==='weathernext3_total_cloud_cover_mean'&&c.point_product==='WeatherNext 3 local')
const p={sourceId:source.id,productId:cap.product_id,product:cap.point_product,field:cap.field,variant:cap.variants[0],level:cap.levels[0]}
const id=`point:${encodeURIComponent(JSON.stringify([p.sourceId,p.productId,p.product,p.field]))}`
const stack=[{id,visible:false,opacity:.85,pointOnly:true,points:[p]}]
const browser=await chromium.launchPersistentContext(await mkdtemp('/tmp/wn3-browser-'),{channel:'chrome',headless:true,viewport:{width:1440,height:900}})
const page=await browser.newPage()
const requests=[],errors=[]
page.on('pageerror',e=>errors.push(String(e)))
await page.route('**/api/experiments/weather/v0/**',async route=>{
  const u=new URL(route.request().url()),path=u.pathname.split('/v0')[1]
  if(path==='/catalog')return route.fulfill({json:catalog})
  if(path==='/layers')return route.fulfill({json:{data_mode:'live',layers:[],notices:[]}})
  if(path==='/point'&&u.searchParams.get('product')===cap.point_product){
    requests.push(Object.fromEntries(u.searchParams))
    assert.equal(u.searchParams.get('field'),cap.field)
    return route.fulfill({json:point})
  }
  return route.fulfill({status:503,json:{detail:'Provider network blocked in browser replay'}})
})
try{
  await page.goto(`${base}/?lat=47.5615&lon=-52.7126&t=${encodeURIComponent(point.valid_time)}&stack=${encodeURIComponent(JSON.stringify(stack))}`,{waitUntil:'domcontentloaded'})
  const panel=page.getByRole('complementary',{name:'Point data',exact:true})
  const reading=panel.getByRole('button',{name:/Details for point reading WN3 forecast/})
  await reading.waitFor()
  await page.waitForFunction(()=>document.querySelector('.point-data-value')?.textContent?.includes('%'))
  await page.getByRole('button',{name:'Layers',exact:true}).click()
  await page.getByRole('button',{name:'Browse',exact:true}).click()
  const search=page.getByRole('searchbox').last()
  await search.fill('weathernext 2')
  assert.equal(await page.getByRole('button',{name:/WeatherNext 2/}).count(),0)
  await search.fill('weathernext3')
  await mkdir(`${dir}/browser`,{recursive:true})
  for(const zoom of [1,2]){
    const settings=await browser.newPage()
    await settings.goto('chrome://settings/appearance')
    await settings.locator('#zoomLevel').selectOption({label:`${zoom*100}%`})
    await settings.close()
    await page.waitForFunction(expected=>innerWidth===expected,1440/zoom)
    await page.screenshot({path:`${dir}/browser/surface-${zoom*100}.png`})
  }
  const settings=await browser.newPage()
  await settings.goto('chrome://settings/appearance')
  await settings.locator('#zoomLevel').selectOption({label:'100%'})
  await settings.close()
  await reading.click()
  await page.getByRole('heading',{name:/Evidence ·/}).waitFor()
  await page.screenshot({path:`${dir}/browser/provenance.png`})
  point=JSON.parse(await readFile(`${dir}/live-historical-precipitation.json`,'utf8'))
  cap=source.capabilities.find(c=>c.field===point.fields[0].key&&c.point_product==='WeatherNext 3 historical')
  const historical={sourceId:source.id,productId:cap.product_id,product:cap.point_product,field:cap.field,variant:cap.variants[0],level:cap.levels[0]}
  const hid=`point:${encodeURIComponent(JSON.stringify([historical.sourceId,historical.productId,historical.product,historical.field]))}`
  const hs=[{id:hid,visible:false,opacity:.85,pointOnly:true,points:[historical]}]
  await page.goto(`${base}/?lat=47.5615&lon=-52.7126&t=${encodeURIComponent(point.valid_time)}&stack=${encodeURIComponent(JSON.stringify(hs))}`,{waitUntil:'domcontentloaded'})
  await page.waitForFunction(()=>document.querySelector('.point-data-value')?.textContent?.includes('mm'))
  await page.screenshot({path:`${dir}/browser/historical-percentile.png`})
  assert.equal(errors.length,0,errors.join('\n'))
  await writeFile(`${dir}/browser/result.json`,JSON.stringify({requests,errors,providerWeatherRequests:0,catalogueCapabilities:source.capabilities.length},null,2))
  console.log('WN3 browser replay passed: field query, numeric cloud %, hidden WN2, 252 paths, provenance, 100/200% zoom; zero provider weather requests.')
}finally{await browser.close()}
