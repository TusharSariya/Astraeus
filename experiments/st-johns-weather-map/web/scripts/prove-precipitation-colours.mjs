// Reuses the fixed-response browser proof: provider traffic is blocked.
import {chromium} from 'playwright'
import {mkdir,writeFile,readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const base=process.env.BENCH_URL??'http://127.0.0.1:5269',output='/tmp/astraeus-precipitation-proof'
await mkdir(output,{recursive:true})
const fixture=JSON.parse(await readFile(new URL('../../contracts/fixtures/source-delivery.json',import.meta.url),'utf8'))
const at='2026-09-09T03:00:00.000Z', run='2026-09-09T00:00:00.000Z'
const browser=await chromium.launch({channel:'chrome',headless:true})
const context=await browser.newContext({viewport:{width:1440,height:900}})
const page=await context.newPage()
await page.clock.install({time:new Date(at)})
const errors=[],requests=[],jobs=new Map()
page.setDefaultTimeout(10000)
page.on('pageerror',e=>errors.push(String(e)))
const fieldValues={'tp:sfc':[[.005,.025,.05],[0,null,.01]],'2t:sfc':[[275,273.15,270],[275,275,null]],'tcc:sfc':[[1,1,1],[1,1,1]]}
await page.route('**/*',async route=>{
 const url=new URL(route.request().url());if(url.origin!==new URL(base).origin)return route.abort()
 if(!url.pathname.startsWith('/api/'))return route.continue()
 requests.push(`${route.request().method()} ${url.pathname}`)
 const path=url.pathname.split('/v0')[1];let body={data_mode:'unavailable',notices:[]}
 if(path==='/ifs/catalogue')body={fields:[],products:[]}
 else if(path?.startsWith('/ifs/runs/'))body=[{id:'fixed-run',run_time:run,files:{3:'fixture'}}]
 else if(path==='/ifs/selections'&&route.request().method()==='POST'){
  const field=route.request().postDataJSON().fields[0].field,id=`job-${jobs.size}`;jobs.set(id,field);body={id,next_cursor:null,completed:1,total:1,items:[]}
 }else if(path?.includes('/ifs/selections/')&&path.endsWith('/grid')){
  const field=jobs.get(path.split('/')[3]);body={selection_product:'atmosphere-control',product:'atmosphere-control',field,level:0,run_id:'fixed-run',run_time:run,member:'0',statistic:null,native_time:at,interval_start:run,interval_end:at,units:field==='tp:sfc'?'m':field==='2t:sfc'?'K':'1',expires_at:'2026-09-09T04:00:00Z',digest:field,values:fieldValues[field],latitudes:[47.7,47.3],longitudes:[-53.5,-53,-52.5],latitude_edges:[47.9,47.5,47.1],longitude_edges:[-53.75,-53.25,-52.75,-52.25],receipt_manifest:'/fixed-fixture-receipts',receipt_ids:[],native_metadata:{},region:[-70,40,-40,55]}
 }else if(path==='/catalog')body=fixture.catalog
 else if(path==='/sources/status')body=fixture.status
 else if(path==='/point')body={...fixture.point,valid_time:at,fields:[]}
 else if(path==='/layers')body={data_mode:'fixture',layers:[],notices:[]}
 else if(path==='/timeline')body={data_mode:'fixture',start:run,end:'2026-09-10T03:00:00Z',items:[]}
 else if(path==='/methods')body={data_mode:'fixture',methods:[],notices:[]}
 else if(path==='/registry/sites')body={operational:false,version:'a'.repeat(64),sites:[],notice:null}
 return route.fulfill({json:body})
})
const layer=(id,field,visible=true)=>({id:id.replaceAll(' ','-'),visible,opacity:1,ifs:{product:'atmosphere-control',field,level:0,run:'latest',member:'0',statistic:'',rendering:field==='tcc:sfc'?'cloud':'scalar',title:id}})
try{
 const stack=[layer('Temperature','2t:sfc',false),layer('Precipitation','tp:sfc'),layer('White cloud','tcc:sfc')]
 await page.goto(`${base}/?view=map&lat=47.5&lon=-53&t=${at}&stack=${encodeURIComponent(JSON.stringify(stack))}`,{waitUntil:'domcontentloaded'})
 const legends=page.getByRole('complementary',{name:'IFS native layer legends'})
 await legends.getByText('Precipitation',{exact:true}).click()
 await legends.getByText('Temperature-based colours',{exact:true}).waitFor()
 await page.screenshot({path:`${output}/01-overlapping-cloud.png`})
 const count=requests.filter(r=>r.startsWith('POST')||r.endsWith('/grid')||r.includes('/point')).length
 await page.getByRole('button',{name:'Layers',exact:true}).click()
 await page.getByRole('button',{name:'Browse',exact:true}).click()
 await page.getByText('IFS Atlantic products',{exact:true}).click()
 const cloud=page.locator('fieldset').filter({has:page.locator('legend').filter({hasText:'White cloud'})})
 await cloud.getByRole('checkbox',{name:'Visible',exact:true}).uncheck()
 const precipitation=page.locator('fieldset').filter({has:page.locator('legend').filter({hasText:'Precipitation'})})
 await precipitation.getByRole('slider',{name:'Opacity',exact:true}).fill('0.8')
 await page.getByRole('button',{name:'Layers',exact:true}).click()
 await page.screenshot({path:`${output}/02-isolated-precipitation.png`})
 assert.equal(requests.filter(r=>r.startsWith('POST')||r.endsWith('/grid')||r.includes('/point')).length,count)
 assert.equal(jobs.size,3)
 await page.mouse.click(650,400)
 await legends.getByText(/1.9°C · ecmwf-ifs/).waitFor()
 await page.screenshot({path:`${output}/03-inspection.png`})
 // Browser settings pages terminate this installed headless Chrome. Reproduce
 // the 200% effective CSS viewport with CDP, without provider calls.
 await page.setViewportSize({width:720,height:450})
 const cdp=await context.newCDPSession(page)
 await cdp.send('Emulation.setDeviceMetricsOverride',{width:720,height:450,deviceScaleFactor:2,mobile:false,screenWidth:1440,screenHeight:900})
 await page.screenshot({path:`${output}/04-200-percent-equivalent.png`})
 assert.equal(await page.evaluate(()=>window.innerWidth),720)
 const mapBox=await page.getByTestId('map-canvas').boundingBox()
 const legendBox=await legends.boundingBox(),pointBox=await page.getByRole('complementary',{name:'Point data',exact:true}).boundingBox()
 assert.ok(legendBox.y+legendBox.height<=mapBox.y+mapBox.height,'Legend must remain above the map footer')
 assert.ok(legendBox.x>=pointBox.x+pointBox.width || legendBox.y+legendBox.height<=pointBox.y,'Legend must not overlap Point data at 200% equivalent viewport')
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
 assert.deepEqual(errors,[])
 await writeFile(`${output}/receipt.json`,JSON.stringify({errors,requests,providerRequests:0,scienceSelections:jobs.size,checks:['Hidden loaded temperature','Overlapping white cloud isolated','Opacity and visibility reuse science selections','Numeric precipitation legend','200% equivalent effective CSS viewport (emulation)', 'Native cell temperature inspection']},null,2))
 console.log(`PASS ${output}`)
}catch(error){console.error('Original browser error:',error);await page.screenshot({path:`${output}/failure.png`});await writeFile(`${output}/failure.json`,JSON.stringify({error:String(error),errors,requests,body:await page.locator('body').innerText()},null,2));throw error}finally{await browser.close()}
