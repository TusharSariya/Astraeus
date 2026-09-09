// Replay a captured provider PNG to verify RGB preservation, not current geography.
import {chromium} from 'playwright'
import {readFile,mkdir,writeFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const base=process.env.BENCH_URL??'http://127.0.0.1:5173',out='/tmp/astraeus-radar-colours-proof'
await mkdir(out,{recursive:true})
const fixture=JSON.parse(await readFile(new URL('../../contracts/fixtures/source-delivery.json',import.meta.url),'utf8'))
const inputs=new URL('../../../../docs/evidence/radar-colours-20260909/',import.meta.url)
const radar=JSON.parse(await readFile(new URL('radar-layer.json',inputs),'utf8')),at='2026-09-09T15:48:00.000Z'
radar.imagery_availability={status:'known',checked_at:at,basis:'fixed-image-replay',times:[at],reason:'Captured provider image replay; no current geographic claim'}
const png=await readFile(new URL('provider-radar.png',inputs))
const browser=await chromium.launch({channel:'chrome',headless:true})
const page=await browser.newPage({viewport:{width:1440,height:900}})
await page.clock.install({time:new Date(at)})
let science=0;const errors=[]
page.on('pageerror',e=>errors.push(String(e)))
await page.route('**/*',async route=>{
 const url=new URL(route.request().url());if(url.origin!==new URL(base).origin)return route.abort()
 if(!url.pathname.startsWith('/api/'))return route.continue()
 const path=url.pathname.split('/v0')[1]
 if(path?.endsWith('/raster')){science++;return route.fulfill({body:png,contentType:'image/png',headers:{'X-Weather-Retrieval-Status':'retrieved','X-Weather-Wms-Layer':'RADAR_1KM_RRAI','X-Weather-Evidence-Basis':'published_artifact','X-Weather-Image-Basis':'live_proxy','X-Weather-Valid-Time':at,'X-Weather-Reference-Time':'none'}})}
 if(path==='/point')science++
 let body={data_mode:'unavailable',notices:[]}
 if(path==='/layers')body={data_mode:'live',layers:[radar],notices:[]}
 else if(path==='/catalog')body=fixture.catalog
 else if(path==='/point')body={...fixture.point,fields:[],valid_time:at}
 else if(path==='/sources/status')body=fixture.status
 else if(path==='/ifs/catalogue')body={fields:[],products:[]}
 else if(path?.startsWith('/ifs/runs/'))body=[]
 else if(path==='/methods')body={data_mode:'live',methods:[],notices:[]}
 else if(path==='/timeline')body={data_mode:'live',start:at,end:'2026-09-09T16:48:00Z',items:[]}
 else if(path==='/registry/sites')body={operational:false,version:'a'.repeat(64),sites:[],notice:null}
 else if(path?.endsWith('/features'))body={type:'FeatureCollection',features:[],data_mode:'live'}
 return route.fulfill({json:body})
})
try{
 await page.goto(`${base}/?view=map&lat=47.5&lon=-53&t=${at}&interp=1&stack=${encodeURIComponent(JSON.stringify([{id:radar.id,visible:true,opacity:.85}]))}`,{waitUntil:'domcontentloaded'})
 await page.getByRole('button',{name:'Layers',exact:true}).click()
 await page.getByRole('combobox',{name:'Temperature source'}).waitFor()
 await page.getByText('Provider colours',{exact:true}).waitFor()
 await page.locator('.dense-layer-row .bench-layer-state').filter({hasText:'Drawn'}).waitFor()
 const count=science
 await page.getByRole('combobox',{name:'Temperature source'}).selectOption('eccc-hrdps')
 await page.screenshot({path:`${out}/radar-provider-colours-and-picker.png`})
 assert.equal(science,count)
 assert.equal(JSON.parse(new URL(page.url()).searchParams.get('stack'))[0].temperatureSource,'eccc-hrdps')
 assert.deepEqual(errors,[])
 await writeFile(`${out}/receipt.json`,JSON.stringify({science,additionalRequestsFromSourceChoice:science-count,providerRequests:0,errors,replay:'Captured PNG replay; geometry is illustrative. RGB and controls test only.'},null,2))
 console.log(`PASS ${out}`)
}catch(error){console.error(error);await page.screenshot({path:`${out}/failure.png`});await writeFile(`${out}/failure.txt`,await page.locator('body').innerText());throw error}finally{await browser.close()}
