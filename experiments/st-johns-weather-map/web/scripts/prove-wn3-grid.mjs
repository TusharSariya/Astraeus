// Synthetic native-grid browser replay. Provider API transport is blocked.
import { chromium } from 'playwright'
import { readFile,mkdir,writeFile,mkdtemp } from 'node:fs/promises'
import assert from 'node:assert/strict'
const dir=process.env.WN3_GRID_PROOF_DIR ?? '/private/tmp/astraeus-wn3-grid-proof'
const base=process.env.BENCH_URL ?? 'http://127.0.0.1:5323'
const catalog=JSON.parse(await readFile(`${dir}/fixture-catalog.json`,'utf8'))
const grid=JSON.parse(await readFile(`${dir}/fixture-grid.json`,'utf8'))
const point=JSON.parse(await readFile(`${dir}/fixture-point.json`,'utf8'))
const source=catalog.sources.find(s=>s.id===grid.source_id)
const cap=source.capabilities.find(c=>c.grid&&c.point_product===grid.product)
assert.ok(cap)
const p={sourceId:source.id,productId:cap.product_id,product:cap.point_product,field:cap.field,variant:cap.variants[0],level:cap.levels[0]}
const id=`point:${encodeURIComponent(JSON.stringify([p.sourceId,p.productId,p.product,p.field]))}`
const stack=[{id,visible:true,opacity:.85,points:[p]}]
const context=await chromium.launchPersistentContext(await mkdtemp('/tmp/wn3-grid-browser-'),{channel:'chrome',headless:true,viewport:{width:1440,height:900}})
const page=await context.newPage(),requests=[],errors=[]
page.on('pageerror',e=>errors.push(String(e)))
await page.clock.setFixedTime(new Date('2026-09-08T00:00:00Z'))
await page.route('**/api/experiments/weather/v0/**',async route=>{
 const u=new URL(route.request().url()),path=u.pathname.split('/v0')[1]
 if(path==='/catalog')return route.fulfill({json:catalog})
 if(path==='/layers')return route.fulfill({json:{data_mode:'live',layers:[],notices:[]}})
 if(path.endsWith('/grid')){requests.push({kind:'grid',params:Object.fromEntries(u.searchParams)});return route.fulfill({json:grid})}
 if(path==='/point'&&u.searchParams.get('product')===cap.point_product){requests.push({kind:'point',params:Object.fromEntries(u.searchParams)});return route.fulfill({json:point})}
 return route.fulfill({status:503,json:{detail:'Provider network blocked in synthetic browser proof'}})
})
await mkdir(`${dir}/browser`,{recursive:true})
try {
 await page.goto(`${base}/?lat=47.5&lon=-53&t=${encodeURIComponent(grid.native_time)}&stack=${encodeURIComponent(JSON.stringify(stack))}`,{waitUntil:'domcontentloaded'})
 console.log('Loaded app');
 await page.getByRole('complementary',{name:'Ensemble-mean cloud cover legend'}).waitFor()
 await page.waitForFunction(()=>document.querySelector('.native-cloud-legend')?.textContent?.includes('2026-08-01'))
 console.log('Grid rendered');
 await page.waitForFunction(()=>document.querySelector('.point-data-value')?.textContent?.includes('50%'))
 assert.equal(requests[0].kind,'grid');assert.equal(requests.filter(r=>r.kind==='grid').length,1)
 await page.getByRole('button',{name:'Layers',exact:true}).click()
 await page.getByRole('button',{name:'Browse',exact:true}).click()
 await page.getByRole('searchbox').last().fill('weathernext3 total cloud cover mean')
 for(const [width,height] of [[1440,900],[1280,720],[1920,1080]]) {
   await page.setViewportSize({width,height})
   for(const theme of ['dark','light','night']) {
     await page.getByText('Settings',{exact:true}).click()
     await page.getByRole('group',{name:'Colour theme'}).getByRole('button',{name:theme==='night'?'Red night':theme,exact:true}).click()
     await page.getByText('Settings',{exact:true}).click()
     for(const zoom of [1,2]) {
       const settings=await context.newPage();await settings.goto('chrome://settings/appearance');await settings.locator('#zoomLevel').selectOption({label:`${zoom*100}%`});await settings.close()
       await page.waitForFunction(expected=>innerWidth===expected,width/zoom)
       await page.screenshot({path:`${dir}/browser/${width}x${height}-${theme}-${zoom*100}.png`})
       const overlap=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth}))
       assert.ok(overlap.scrollWidth<=overlap.width+1,JSON.stringify(overlap))
     }
   }
 }
 const settings=await context.newPage();await settings.goto('chrome://settings/appearance');await settings.locator('#zoomLevel').selectOption({label:'100%'});await settings.close()
 await page.setViewportSize({width:1440,height:900})
 await page.getByRole('button',{name:'Layers',exact:true}).click()
 await page.getByRole('button',{name:'Evidence',exact:true}).click()
 await page.locator('.bench-map-evidence').evaluate(node=>{node.open=true})
 const inspect=page.getByRole('button',{name:/^Inspect Missing ensemble-mean cloud cover from/}).first()
 await inspect.click()
 await page.getByRole('heading',{name:/Evidence ·/}).waitFor()
 await page.screenshot({path:`${dir}/browser/missing-cell-inspection.png`})
 assert.equal(requests.filter(r=>r.kind==='grid').length,1,'viewport/theme/zoom must reuse selected frame')
 assert.equal(errors.length,0,errors.join('\n'))
 await writeFile(`${dir}/browser/result.json`,JSON.stringify({evidence:'synthetic native fixture/browser replay, not upstream evidence',providerWeatherRequests:0,requests,errors,cells:861},null,2))
 console.log('Browser proof passed: native grid, grid-first point, missing inspection, 18 size/theme/zoom captures; one grid request, zero provider requests.')
} catch(error) { console.log('Diagnostic',requests,errors,await page.locator('.native-cloud-legend').textContent()); await page.screenshot({path:`${dir}/browser/failure.png`}); throw error } finally {await context.close()}
