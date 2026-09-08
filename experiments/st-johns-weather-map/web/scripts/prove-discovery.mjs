// Real catalogue declarations; deliberately unavailable weather responses. No source acquisition.
import { chromium } from 'playwright'
import { mkdir, writeFile, mkdtemp, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'
const output=process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-discovery-proof', base=process.env.BENCH_URL ?? 'http://127.0.0.1:5197'
await mkdir(output,{recursive:true})
const catalog=await (await fetch('http://127.0.0.1:8197/api/experiments/weather/v0/catalog')).json()
assert.ok(catalog.sources.length>=125)
assert.equal(catalog.sources.find(s=>s.id==='google-weathernext-3-statistics').discovery.map_capabilities.length,0)
const browser=await chromium.launchPersistentContext(await mkdtemp(`${tmpdir()}/discovery-chrome-`),{channel:'chrome',headless:true,viewport:{width:1440,height:900}})
const page=await browser.newPage(), requests=[], errors=[], measures=[]
page.on('pageerror',e=>errors.push(String(e)))
await page.route('**/api/experiments/weather/v0/**',async route=>{
 const url=new URL(route.request().url()), path=url.pathname.split('/v0')[1];requests.push({path,query:url.search,method:route.request().method()})
 if(path==='/catalog')return route.fulfill({json:catalog})
 if(path==='/layers')return route.fulfill({json:{data_mode:'live',layers:[],notices:['Constructed empty frame cache; catalogue declarations are real']}})
 return route.fulfill({status:503,json:{detail:'Browser verification deliberately withheld weather acquisition'}})
})
const browse=page.getByRole('region',{name:'Unified source discovery'})
const search=()=>browse.getByRole('searchbox')
const open=async()=>{await page.getByRole('button',{name:'Layers',exact:true}).click();await page.getByRole('button',{name:'Browse',exact:true}).click()}
const theme=async name=>{await page.locator('.bench-settings > summary').click();await page.getByRole('button',{name,exact:true}).click();await page.locator('.bench-settings > summary').click()}
const measure=async()=>page.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,scrollX:document.documentElement.scrollWidth>innerWidth,scrollY:document.documentElement.scrollHeight>innerHeight,overlay:document.querySelector('.bench-overlay:not([hidden])')?.getBoundingClientRect().toJSON()}))
try{
 await page.goto(`${base}/?lat=47.5&lon=-52.7&t=2026-09-08T14:00:00Z&stack=${encodeURIComponent('[]')}`)
 await open();await search().waitFor();await page.waitForTimeout(1200)
 const beforeRequests=requests.length
 const focusUrl=page.url(), canvas=await page.locator('.maplibregl-canvas').elementHandle()
 await search().fill('WeatherNext 3')
 await browse.getByText('Capabilities · 2',{exact:true}).click()
 await browse.getByRole('button',{name:'Open point · WeatherNext 3 local',exact:true}).waitFor(); assert.equal(await browse.getByRole('button',{name:/Open point/}).count(),2)
 assert.equal(await browse.getByRole('button',{name:/Add /}).count(),0)
 await page.screenshot({path:`${output}/weathernext-paths.png`})
 await browse.getByRole('button',{name:'Source details',exact:true}).click()
 await page.keyboard.press('Escape')
 await browse.getByRole('button',{name:'Source details',exact:true}).waitFor()
 assert.equal(await browse.getByRole('button',{name:'Source details',exact:true}).evaluate(e=>e===document.activeElement),true)
 assert.equal(requests.length,beforeRequests,'browsing or provenance started API work')
 await browse.getByRole('button',{name:'Open point · WeatherNext 3 local',exact:true}).click()
 await page.getByText('Point product: WeatherNext 3 local',{exact:false}).waitFor()
 await page.waitForTimeout(500)
 assert.ok(requests.some(r=>r.path==='/point'&&new URLSearchParams(r.query).get('product')==='WeatherNext 3 local'))
 assert.equal(page.url(),focusUrl)
 await page.keyboard.press('Escape')
 await search().waitFor()
 assert.equal(await search().inputValue(),'WeatherNext 3')
 await page.waitForFunction(()=>document.activeElement?.textContent==='Open point · WeatherNext 3 local')
 assert.equal(await browse.getByRole('button',{name:'Open point · WeatherNext 3 local',exact:true}).evaluate(e=>e===document.activeElement),true)
 assert.equal(await canvas.evaluate(el=>el===document.querySelector('.maplibregl-canvas')),true)
 await page.keyboard.press('Escape'); assert.equal(await page.getByRole('button',{name:'Layers',exact:true}).evaluate(el=>el===document.activeElement),true); await open()
 const seriesSource=catalog.sources.find(s=>s.capabilities.some(c=>c.native_series))
 await browse.getByRole('combobox',{name:'Group by'}).selectOption('Ungrouped')
 await search().fill(seriesSource.id)
 await browse.locator(`[data-source-id="${seriesSource.id}"] > details > summary`).click()
 await browse.locator(`[data-source-id="${seriesSource.id}"]`).getByRole('button',{name:/Open series/}).first().click()
 await page.getByRole('heading',{name:'Series',exact:true}).waitFor()
 assert.ok((await page.getByRole('combobox',{name:'Series A',exact:true}).inputValue()).includes(seriesSource.id))
 await page.screenshot({path:`${output}/series-navigation.png`})
 await page.locator('.bench-view-menu > summary').click();await page.getByRole('navigation',{name:'Evidence views'}).getByRole('button',{name:'Map',exact:true}).click();await open()
 assert.equal(await canvas.evaluate(el=>el===document.querySelector('.maplibregl-canvas')),true)
 await browse.getByRole('combobox',{name:'Group by'}).selectOption('Subject')
 await search().fill('GOES-East ABI')
 // Use exact registry id as search to avoid guessing product display text.
 await search().fill('noaa-goes-east')
 assert.equal(await browse.locator('[data-source-id="noaa-goes-east"]').count(),catalog.sources.find(s=>s.id==='noaa-goes-east').discovery.subjects.length)
 await search().fill('')
 await browse.getByRole('combobox',{name:'Group by'}).selectOption('Provider')
 await browse.getByText('Filters',{exact:true}).click()
 await browse.getByRole('group',{name:'Subject',exact:true}).getByRole('checkbox',{name:'Humidity',exact:true}).check()
 await browse.getByRole('group',{name:'Kind',exact:true}).getByRole('checkbox',{name:'Forecast',exact:true}).check()
 await page.screenshot({path:`${output}/combined-filters.png`})
 await browse.getByRole('button',{name:'Clear filters'}).click()
 await browse.getByText('Filters',{exact:true}).click()
 await browse.getByRole('combobox',{name:'Group by'}).selectOption('Subject')
 for(const zoom of [100,200]){
  if(zoom===200){const settings=await browser.newPage();await settings.goto('chrome://settings/appearance');await settings.locator('#zoomLevel').selectOption({label:'200%'});await settings.close()}
  for(const [width,height] of [[1280,800],[1440,900],[1920,1080]]){
   await page.setViewportSize({width,height})
   for(const name of ['dark','light','Red night']){
    await theme(name);await search().fill('WeatherNext 3');await page.waitForTimeout(100)
    await page.locator('.bench-overlay:not([hidden])').evaluate(el=>el.scrollTop=0)
    const m=await measure();assert.equal(m.scrollX,false);assert.equal(m.scrollY,false);if(zoom===200)assert.equal(m.width,width/2)
    measures.push({zoom,theme:name,...m})
    await page.screenshot({path:`${output}/${width}x${height}-${name.replace(' ','-')}-${zoom}-open.png`})
    await page.getByRole('button',{name:'Close Layers',exact:true}).click()
    await page.screenshot({path:`${output}/${width}x${height}-${name.replace(' ','-')}-${zoom}-closed.png`})
    await open()
   }
  }
 }
 assert.deepEqual(errors,[])
 await writeFile(`${output}/receipt.json`,JSON.stringify({catalogueSources:catalog.sources.length,weather:'Unavailable constructed responses; zero real weather acquisition',measures,requests,errors},null,2))
 console.log(JSON.stringify({sources:catalog.sources.length,screenshots:(await readdir(output)).filter(name=>name.endsWith('.png')).length,errors,output}))
}finally{await browser.close()}
