// Real catalogue declarations; deliberately unavailable weather responses. No source acquisition.
import { chromium } from 'playwright'
import { mkdir, writeFile, mkdtemp, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'
const output=process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-dense-proof', base=process.env.BENCH_URL ?? 'http://127.0.0.1:5197'
await mkdir(output,{recursive:true})
const catalog=await (await fetch('http://127.0.0.1:8197/api/experiments/weather/v0/catalog')).json()
assert.ok(catalog.sources.length>=125)
assert.equal(catalog.sources.find(s=>s.id==='google-weathernext-3-statistics').discovery.map_capabilities.length,0)
const browser=await chromium.launchPersistentContext(await mkdtemp(`${tmpdir()}/discovery-chrome-`),{channel:'chrome',headless:true,viewport:{width:1440,height:900}})
const page=await browser.newPage(), requests=[], errors=[], measures=[]
let failCatalog=false
page.on('pageerror',e=>errors.push(String(e)))
await page.route('**/api/experiments/weather/v0/**',async route=>{
 const url=new URL(route.request().url()), path=url.pathname.split('/v0')[1];requests.push({path,query:url.search,method:route.request().method()})
 if(path==='/catalog')return failCatalog ? route.fulfill({status:503,json:{detail:'Constructed registry failure'}}) : route.fulfill({json:catalog})
 if(path==='/layers')return route.fulfill({json:{data_mode:'live',layers:failCatalog?[{id:'proof-cloud',title:'HRDPS total cloud · deliberately long catalogue-failure proof label',kind:'raster',field:'total_cloud',product:'HRDPS',units:'%',semantics:'Constructed descriptor; no weather supplied',raster_available:false}]:[],notices:['Constructed empty frame cache; catalogue declarations are real']}})
 return route.fulfill({status:503,json:{detail:'Browser verification deliberately withheld weather acquisition'}})
})
const browse=page.getByRole('region',{name:'Unified source discovery'})
const search=()=>browse.getByRole('searchbox')
const open=async()=>{const button=page.getByRole('button',{name:'Layers',exact:true});if(await button.getAttribute('aria-expanded')!=='true')await button.click();await page.locator('.bench-overlay[aria-label="Layers overlay"]').waitFor();if(await details.isVisible())await details.getByRole('button',{name:/Back to/}).click();await page.getByRole('button',{name:'Browse',exact:true}).click()}
const theme=async name=>{await page.locator('.bench-settings > summary').click();await page.getByRole('button',{name,exact:true}).click();await page.locator('.bench-settings > summary').click()}
const measure=async()=>page.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,scrollX:document.documentElement.scrollWidth>innerWidth,scrollY:document.documentElement.scrollHeight>innerHeight,overlay:document.querySelector('.bench-overlay:not([hidden])')?.getBoundingClientRect().toJSON()}))
const details=page.getByRole('region',{name:'Layer or source details'})
const stack=()=>JSON.parse(new URL(page.url()).searchParams.get('stack'))
const primary=()=>browse.locator('.dense-layer-primary')
const dismiss=async()=>{await page.keyboard.press('Escape');await details.waitFor({state:'hidden'})}
try{
 await page.goto(`${base}/?lat=47.5&lon=-52.7&t=2026-09-08T14:00:00Z&stack=${encodeURIComponent('[]')}`)
 await open();await search().waitFor();await page.waitForTimeout(1200)
 const mapClip={x:10,y:180,width:600,height:350}
 const initialMap=await page.screenshot({clip:mapClip})
 await page.mouse.move(400,390);await page.mouse.down();await page.mouse.move(480,430,{steps:12});await page.mouse.up()
 await page.waitForTimeout(1500)
 const pannedMap=await page.screenshot({clip:mapClip})
 assert.equal(initialMap.equals(pannedMap),false,'camera pan must change the map')
 const beforeRequests=requests.length, originalUrl=page.url(), canvas=await page.locator('.maplibregl-canvas').elementHandle()
 await search().fill('WeatherNext 3')
 const pointRow=primary().first()
 await pointRow.click()
 await details.getByRole('button',{name:'Open point · WeatherNext 3 local',exact:true}).waitFor()
 assert.equal(await details.getByRole('button',{name:/Open point/}).count(),2)
 assert.equal(await details.getByRole('button',{name:/Add /}).count(),0)
 await page.screenshot({path:`${output}/weathernext-details.png`})
 await details.getByRole('button',{name:'Source provenance',exact:true}).click()
 await page.getByRole('complementary',{name:'Evidence inspector',exact:true}).waitFor()
 await page.keyboard.press('Escape')
 await details.waitFor();await page.waitForFunction(()=>document.activeElement?.textContent==='Source provenance')
 assert.equal(requests.length,beforeRequests,'browsing or provenance started API work')
 assert.ok(pannedMap.equals(await page.screenshot({clip:mapClip})),'details changed the panned map camera')
 await details.getByRole('button',{name:'Open point · WeatherNext 3 local',exact:true}).click()
 await page.getByText('Point product: WeatherNext 3 local',{exact:false}).waitFor()
 await page.waitForTimeout(200)
 assert.ok(requests.some(r=>r.path==='/point'&&new URLSearchParams(r.query).get('product')==='WeatherNext 3 local'))
 assert.equal(page.url(),originalUrl)
 await page.keyboard.press('Escape');await details.waitFor()
 await page.waitForFunction(()=>document.activeElement?.textContent==='Open point · WeatherNext 3 local')
 await dismiss();await page.waitForFunction(()=>document.activeElement?.classList.contains('dense-layer-primary'))
 assert.equal(await search().inputValue(),'WeatherNext 3')
 assert.equal(await canvas.evaluate(el=>el===document.querySelector('.maplibregl-canvas')),true)
 await search().fill('noaa-goes-east')
 const cloudTitle=catalog.sources.find(s=>s.id==='noaa-goes-east').discovery.map_capabilities[0].title
 const same=()=>browse.getByRole('button',{name:cloudTitle,exact:true})
 assert.ok(await same().count()>1)
 await same().first().click();assert.equal(stack().length,1)
 for(const row of await same().all())assert.equal(await row.getAttribute('aria-pressed'),'true')
 const selectedUrl=page.url()
 await same().last().click({button:'right'});await details.waitFor();assert.equal(page.url(),selectedUrl);await dismiss()
 await same().first().focus();await page.keyboard.press('Shift+F10');await details.waitFor();assert.equal(page.url(),selectedUrl);await dismiss()
 await same().first().press('ContextMenu');await details.waitFor();assert.equal(page.url(),selectedUrl);await dismiss()
 await browse.getByRole('button',{name:`Details for ${cloudTitle}`,exact:true}).first().click();await details.waitFor();assert.equal(page.url(),selectedUrl)
 await details.getByRole('checkbox',{name:`Show ${cloudTitle}`,exact:true}).uncheck()
 await details.getByRole('slider').fill('0.35');assert.equal(stack()[0].opacity,.35)
 await dismiss();for(const row of await same().all())assert.equal(await row.getAttribute('aria-pressed'),'true')
 await same().first().press('Enter');assert.equal(stack().length,0)
 await same().first().press('Space');assert.equal(stack()[0].opacity,.85);assert.equal(stack()[0].visible,true)
 // Shared source Series action is reachable through any associated map row.
 const seriesSource=catalog.sources.find(s=>s.capabilities.some(c=>c.native_series))
 await browse.getByRole('combobox',{name:'Group by'}).selectOption('Ungrouped');await search().fill(seriesSource.id)
 await browse.locator('.dense-layer-details').first().click()
 await details.getByRole('button',{name:/Open series/}).first().click()
 await page.getByRole('heading',{name:'Series',exact:true}).waitFor()
 assert.ok((await page.getByRole('combobox',{name:'Series A',exact:true}).inputValue()).includes(seriesSource.id))
 await page.screenshot({path:`${output}/series-navigation.png`})
 await page.locator('.bench-view-menu > summary').click();await page.getByRole('navigation',{name:'Evidence views'}).getByRole('button',{name:'Map',exact:true}).click();await open()
 if(await details.isVisible())await dismiss()
 await search().fill('');await browse.getByRole('combobox',{name:'Group by'}).selectOption('Ungrouped')
 // Populate an ordered stack by explicit row actions. No returned weather is invented.
 for(let i=0;i<18;i++) await browse.locator('.dense-layer-primary[aria-pressed="false"]').first().click()
 const edited=stack();assert.equal(edited.length,19)
 await page.getByRole('button',{name:/Active ·/}).click()
 const active=page.locator('.bench-stack ol.dense-layer-list'), activeRows=()=>active.locator('.dense-layer-primary')
 const firstName=await activeRows().first().getAttribute('aria-label')
 await active.locator('.dense-visibility').first().click();assert.equal(stack().at(-1).visible,false)
 await active.locator('.dense-layer-details').first().click()
 await details.getByRole('slider').fill('0.4');await details.getByRole('button',{name:`Lower ${firstName}`,exact:true}).click()
 assert.equal(stack().at(-2).opacity,.4)
 await dismiss()
 await page.getByText('Stacks',{exact:true}).click();await page.getByRole('textbox',{name:'Stack name'}).fill('Dense proof');await page.getByRole('button',{name:'Save stack',exact:true}).click()
 const savedUrl=page.url()
 await activeRows().first().click();await page.waitForFunction(()=>document.activeElement?.classList.contains('dense-layer-primary'))
 assert.equal(stack().length,18)
 await page.getByRole('combobox',{name:'Saved stacks'}).selectOption('Dense proof');assert.deepEqual(stack(),JSON.parse(new URL(savedUrl).searchParams.get('stack')))
 await page.getByText('Stacks',{exact:true}).click()
 await page.reload();await open();assert.deepEqual(stack(),JSON.parse(new URL(savedUrl).searchParams.get('stack')))
 await browse.getByRole('combobox',{name:'Group by'}).selectOption('Ungrouped')
 // List scroll and focus survive replacement by details.
 const overlay=page.locator('.bench-overlay:not([hidden])')
 await primary().nth(25).scrollIntoViewIfNeeded()
 const scroll=await overlay.evaluate(el=>el.scrollTop)
 const originName=await primary().nth(25).getAttribute('aria-label')
 await primary().nth(25).click({button:'right'});await details.waitFor();await dismiss()
 await page.waitForFunction(name=>document.activeElement?.getAttribute('aria-label')===name,originName)
 assert.equal(await overlay.evaluate(el=>el.scrollTop),scroll)
 await overlay.evaluate(el=>el.scrollTop=0)
 for(const zoom of [100,200]){
  if(zoom===200){const settings=await browser.newPage();await settings.goto('chrome://settings/appearance');await settings.locator('#zoomLevel').selectOption({label:'200%'});await settings.close()}
  for(const [width,height] of [[1280,800],[1440,900],[1920,1080]]){
   await page.setViewportSize({width,height})
   for(const name of ['dark','light','Red night']){
    await theme(name)
    for(const tab of ['Browse','Active']){
     await page.getByRole('button',{name:tab==='Browse'?'Browse':/Active ·/,exact:tab==='Browse'}).click()
     await overlay.evaluate(el=>el.scrollTop=0)
     const m=await measure();assert.equal(m.scrollX,false);assert.equal(m.scrollY,false);if(zoom===200)assert.equal(m.width,width/2)
     const density=await page.evaluate(()=>{
      const overlay=document.querySelector('.bench-overlay:not([hidden])'), box=overlay.getBoundingClientRect()
      const rows=[...overlay.querySelectorAll('.dense-layer-row')].map(el=>el.getBoundingClientRect()).filter(r=>r.width&&r.height)
      return {rows:rows.length,visible:rows.filter(r=>r.top>=box.top&&r.bottom<=box.bottom).length,heights:[...new Set(rows.map(r=>r.height))],scrollable:overlay.scrollHeight>overlay.clientHeight}
     })
     assert.deepEqual(density.heights,[28]);if(zoom===100&&width===1280&&tab==='Browse')assert.ok(density.visible>=14,JSON.stringify(density))
     measures.push({zoom,theme:name,tab,...m,...density})
     await page.screenshot({path:`${output}/${width}x${height}-${name.replace(' ','-')}-${zoom}-${tab.toLowerCase()}.png`})
     // Trailing controls remain reachable at the bottom of the internally scrolled list.
     const list=tab==='Browse'?browse:active
     if(zoom===200){await list.locator('.dense-layer-primary').first().evaluate(el=>el.scrollIntoView({block:'start'}));await page.screenshot({path:`${output}/${width}x${height}-${name.replace(' ','-')}-${zoom}-${tab.toLowerCase()}-scrolled.png`})}
     await list.locator('.dense-layer-details').last().click();await details.waitFor()
     await details.getByRole('button',{name:/Back to/}).click()
    }
   }
  }
 }
 // Subject expansion and filters survive details, independently of source provenance.
 await page.getByRole('button',{name:'Browse',exact:true}).click()
 await browse.getByRole('combobox',{name:'Group by'}).selectOption('Subject')
 await search().fill('noaa-goes-east')
 const group=browse.locator('.discovery-group').first()
 await group.locator('summary').click();assert.equal(await group.getAttribute('open'),null)
 await browse.locator('.dense-layer-details:visible').first().click();await details.waitFor();await dismiss()
 assert.equal(await group.getAttribute('open'),null);assert.equal(await search().inputValue(),'noaa-goes-east')
 // A failed registry cannot erase a separately returned map descriptor or saved selections.
 failCatalog=true;await page.reload();await open()
 await browse.getByText(/Source catalogue unavailable/).waitFor()
 await browse.getByRole('button',{name:'HRDPS total cloud · deliberately long catalogue-failure proof label',exact:true}).waitFor()
 assert.equal(stack().length,19)
 await page.screenshot({path:`${output}/partial-catalogue-failure.png`})
 assert.deepEqual(errors,[])
 await writeFile(`${output}/receipt.json`,JSON.stringify({catalogueSources:catalog.sources.length,camera:'Panned map pixels unchanged through details and nested provenance; canvas retained across point and Series navigation',weather:'Unavailable constructed responses; zero real weather acquisition',measures,requests,errors},null,2))
 console.log(JSON.stringify({sources:catalog.sources.length,screenshots:(await readdir(output)).filter(name=>name.endsWith('.png')).length,errors,output}))
}catch(error){await page.screenshot({path:`/tmp/dense-failure.png`});throw error}finally{await browser.close()}
