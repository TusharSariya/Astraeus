// Constructed SWOB TestClient response; no provider traffic or live evidence.
import {chromium} from 'playwright'
import {readFile,writeFile,mkdir} from 'node:fs/promises'
import assert from 'node:assert/strict'
const base=process.env.BENCH_URL??'http://127.0.0.1:5257',out=process.env.BENCH_PROOF_DIR??'/tmp/astraeus-observation-product-proof'
if(!process.env.NATIVE_SOURCE_PROOF_FIXTURE||!process.env.SOURCE_CATALOG_FIXTURE)throw new Error('Supply actual native and catalogue fixture paths')
const fixtures=JSON.parse(await readFile(process.env.NATIVE_SOURCE_PROOF_FIXTURE,'utf8'))
const catalog=JSON.parse(await readFile(process.env.SOURCE_CATALOG_FIXTURE,'utf8')).catalog
const point=fixtures.point_swob; const requests=[],errors=[]
await mkdir(out,{recursive:true})
const browser=await chromium.launch({channel:'chrome',headless:true}),page=await browser.newPage({viewport:{width:1440,height:1000}})
await page.clock.install({time:new Date(point.valid_time)})
page.on('pageerror',e=>errors.push(String(e)))
await page.route('**/*',async route=>{
 const url=new URL(route.request().url());if(url.origin!==base)return route.abort();if(!url.pathname.startsWith('/api/'))return route.continue()
 const path=url.pathname.split('/v0')[1];let body={data_mode:'fixture',notices:[]}
 if(path==='/catalog')body=catalog
 else if(path==='/point'){requests.push(url.pathname+url.search);body=url.searchParams.get('product')==='SWOB'?point:{...body,fields:[],valid_time:point.valid_time,selection:{mode:'evidence_only',badge:'Fixture',reason:'Constructed proof'}}}
 else if(path==='/layers')body={...body,layers:[]}
 else if(path==='/sources/status')body={...body,statuses:[]}
 else if(path==='/methods')body={...body,methods:[]}
 else if(path==='/timeline')body={...body,start:point.valid_time,end:point.valid_time,items:[]}
 else if(path==='/registry/sites')body={sites:[],operational:false,version:'a'.repeat(64)}
 return route.fulfill({contentType:'application/json',body:JSON.stringify(body)})
})
try{
 await page.goto(`${base}/?view=map&lat=${point.latitude}&lon=${point.longitude}&t=${point.valid_time}&stack=[]`)
 await page.getByRole('button',{name:'Existing evidence panels',exact:true}).click()
 await page.getByRole('button',{name:'Workbench',exact:true}).click()
 const product=page.getByRole('combobox',{name:'Product',exact:true})
 assert.ok((await product.locator('optgroup[label="Native observations"]').innerText()).includes('SWOB'))
 assert.equal(await page.locator('.model-buttons button strong').filter({hasText:/^SWOB$/}).count(),0)
 await product.selectOption('SWOB')
 await page.getByText(point.selection.badge,{exact:true}).first().waitFor()
 await page.screenshot({path:`${out}/observation-product-selector.png`})
 await page.getByRole('button',{name:'Return to desktop Bench',exact:true}).click()
 await page.getByText('Point evidence ledger',{exact:true}).click()
 await page.getByRole('button',{name:new RegExp(`^Inspect ${point.fields.find(field=>field.key==='temperature_2m').field} from eccc-swob`)}).click()
 const inspector=page.getByRole('complementary',{name:'Evidence inspector'})
 const detail=async name=>inspector.locator('dt').filter({hasText:new RegExp(`^${name}$`)}).locator('..').locator('dd').innerText()
 assert.equal(await detail('Run'),'Not supplied')
 const provenance=JSON.parse(await detail('Complete returned provenance'))
 assert.equal(provenance.source_id,'eccc-swob');assert.equal(provenance.native_report.station_id,'71801');assert.equal(provenance.native_report.provider_report_id,'CAJW');assert.equal(provenance.data_mode,'fixture')
 assert.equal(Date.parse(provenance.valid_time),Date.parse(point.fields[0].provenance.valid_time))
 assert.ok(requests.some(request=>{const url=new URL(request,base);return url.searchParams.get('product')==='SWOB'&&Date.parse(url.searchParams.get('valid_time'))===Date.parse(point.valid_time)&&Number(url.searchParams.get('latitude'))===point.latitude&&Number(url.searchParams.get('longitude'))===point.longitude}))
 await page.screenshot({path:`${out}/swob-native-identity.png`})
 assert.deepEqual(errors,[])
 await writeFile(`${out}/receipt.json`,JSON.stringify({basis:'Constructed deterministic SWOB TestClient point response with current generated catalogue; not live evidence',providerRequests:0,externalRequests:'blocked',checks:['native-observation product group','excluded from forecast strip','exact SWOB product/location/time request','station/report identity','no model run','fixture data mode'],requests,errors},null,2))
 console.log('PASS native observation product browser proof')
}catch(error){await page.screenshot({path:`${out}/failure.png`});await writeFile(`${out}/failure.txt`,await page.locator('body').innerText());throw error}finally{await browser.close()}
