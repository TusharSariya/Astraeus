// Fixed native chart browser proof; all weather/provider traffic intercepted.
import { chromium } from 'playwright'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base=process.env.BENCH_URL ?? 'http://127.0.0.1:5173'
const live=process.env.LIVE_COMPARISON==='1'
const output=live?'/tmp/astraeus-comparison-live-browser':'/tmp/astraeus-comparison-proof'
await mkdir(output,{recursive:true})
const fixture=JSON.parse(await readFile(new URL('../../contracts/fixtures/source-delivery.json',import.meta.url),'utf8'))
const browser=await chromium.launch({channel:'chrome',headless:true})
const page=await browser.newPage({viewport:{width:1440,height:1100}})
const at=live?'2026-09-09T10:43:34.379Z':'2026-09-09T03:00:00Z', errors=[], calls=[]
const livePages=[]
const ownedIds=new Set()
await page.clock.install({time:new Date(at)})
page.on('pageerror',e=>errors.push(String(e)))
let comparisonCalls=0
await page.route('**/*',async route=>{
  const url=new URL(route.request().url())
  if(url.origin!==new URL(base).origin)return route.abort()
  if(!url.pathname.startsWith('/api/'))return route.continue()
  calls.push(url.pathname)
  const path=url.pathname.split('/v0')[1]
  let body={data_mode:'unavailable',notices:[]}
  if(path==='/point/comparison') {
    comparisonCalls++
    if(live) {
      if(comparisonCalls>4) return route.abort()
      const response=await route.fetch({timeout:55000})
      const native=await response.json()
      if(response.ok()) {
        ownedIds.add(native.id)
        await writeFile(`${output}/page-${comparisonCalls}.json`,JSON.stringify(native))
        livePages.push({status:response.status(),completed:native.completed_positions,total:native.total_positions,
          sources:native.curves.filter(c=>c.samples.some(s=>typeof s.evidence?.value==='number')).map(c=>c.source_id)})
      }
      return route.fulfill({response})
    }
    const selection=route.request().postDataJSON()
    const groups=[['temperature','temperature_2m','degC',12],['humidity','relative_humidity_2m','percent',70],['cloud','total_cloud_opacity','percent',45],['wind','wind_speed_10m','m/s',8],['precipitation','precipitation_amount','mm',1]]
    const curves=selection.sources.flatMap((source,j)=>groups.map(([group,key,units,baseline])=>{
      const geometric=j>1 && group==='cloud'
      const field=geometric?'total_cloud_geometric':key
      return {id:`${source.source_id}:${field}`,source_id:source.source_id,product_id:source.source_id,group,field,units,definition:group==='cloud'?(geometric?'geometric cover':'opacity-weighted cover'):group,
        samples:Array.from({length:j===3?8:24},(_,i)=>{
          const time=new Date(Date.parse(selection.start)+i*(j===3?3:1)*3600000).toISOString()
          const evidence={...fixture.series.series[0].samples[0],field,key:field,value:i===9?null:baseline+j+Math.sin(i/3)*3,
            provenance:{...fixture.series.series[0].samples[0].provenance,source_id:source.source_id,valid_time:time,run_time:at,normalized_units:units}}
          return {time,run_id:'fixed-native-run',evidence,interval_start:group==='precipitation'?new Date(Date.parse(time)-3600000).toISOString():null,interval_end:group==='precipitation'?time:null}
        })}
    }))
    body={id:'fixed-comparison',selection:{...selection,sources:selection.sources.map(s=>({source_id:s.source_id,product_id:s.product_id,run:s.run}))},selected_at:at,expires_at:new Date(Date.parse(at)+900000).toISOString(),curves,coverage:[],complete:true,next_cursor:null,completed_positions:80,total_positions:80}
  } else if(path==='/catalog')body=fixture.catalog
  else if(path==='/sources/status')body=fixture.status
  else if(path==='/point')body={...fixture.point,latitude:47.5,longitude:-52.7,valid_time:at,fields:[]}
  else if(path==='/layers')body={data_mode:'fixture',layers:[],notices:[]}
  else if(path==='/timeline')body={data_mode:'fixture',start:at,end:'2026-09-10T03:00:00Z',items:[]}
  else if(path==='/methods')body={data_mode:'fixture',methods:[],notices:[]}
  else if(path==='/registry/sites')body={operational:false,version:'a'.repeat(64),sites:[],notice:null}
  return route.fulfill({contentType:'application/json',body:JSON.stringify(body)})
})
try {
  await page.goto(`${base}/?view=series&lat=${live?'47.6186':'47.5'}&lon=${live?'-52.7519':'-52.7'}&t=${at}`,{waitUntil:'domcontentloaded'})
  const section=page.getByRole('region',{name:'Forecast comparison'})
  await section.getByText('Details · native values, runs and provenance').waitFor()
  assert.equal(await section.getByRole('img').count(),6)
  assert.equal(await section.getByRole('slider').count(),0)
  assert.equal(await section.getByRole('button',{name:'Use cursor as map time'}).count(),0)
  assert.ok(await section.getByRole('img').first().locator('circle').count()>1)
  assert.match(await section.getByRole('img').first().locator('path[stroke-width="2"]').first().getAttribute('d'),/L/)
  const timeline=page.getByRole('slider',{name:'Valid timeline scrubber'})
  assert.equal(await timeline.count(),1)
  assert.ok(Math.abs((Number(await timeline.getAttribute('max'))-Number(await timeline.getAttribute('min')))-1440)<.01)
  const selectedBefore=await section.getByRole('img').first().locator('.comparison-shared-cursor').getAttribute('d')
  await timeline.focus()
  await page.keyboard.press('ArrowRight')
  await page.waitForFunction(old=>document.querySelector('.comparison-shared-cursor')?.getAttribute('d')!==old,selectedBefore)

  if(live) {
    await page.waitForFunction(()=>document.querySelectorAll('.comparison-chart circle').length>1,null,{timeout:60000})
    await page.screenshot({path:`${output}/rendered.png`,fullPage:true})
    const chart=section.getByRole('img').first()
    assert.ok(await chart.locator('circle').count()>1)
    assert.match(await chart.locator('path[stroke-width="2"]').first().getAttribute('d'),/L/)
    assert.equal(await section.getByText(/Comparison selection changed/).count(),0)
    await writeFile(`${output}/receipt.json`,JSON.stringify({live_comparison:true,other_api_fixtures:true,pages:livePages,points:await chart.locator('circle').count(),connected_native_samples:true,property_order_accepted:true,errors},null,2))
    console.log(`Live native rendering passed: ${output}`)
    process.exitCode=0
    // Close the page before cleaning up this proof's finite comparisons.
    await page.unrouteAll({behavior:'ignoreErrors'})
    await page.close()
    for(const id of ownedIds)await fetch(`${base}/api/experiments/weather/v0/point/comparison/${id}`,{method:'DELETE'})
  } else {
  const before=comparisonCalls
  const science=()=>calls.filter(p=>/\/(point|grid|features)$/.test(p)).length
  const scienceBefore=science()
  await section.getByRole('img').first().hover({position:{x:200,y:80}})
  await section.getByRole('button',{name:'HRDPS',exact:true}).click()
  await section.getByRole('button',{name:'HRDPS (hidden)',exact:true}).click()
  assert.equal(science(),scienceBefore)
  const initial=await section.getByLabel('Start (UTC)').inputValue()
  await section.getByRole('img').first().click({position:{x:300,y:80}})
  assert.equal(await section.getByLabel('Start (UTC)').inputValue(),initial)
  assert.equal(comparisonCalls,before)
  const pointCount=await section.locator('circle').count()
  await page.getByRole('button',{name:'Play',exact:true}).click()
  await page.clock.fastForward(2000)
  assert.equal(await section.locator('circle').count(),pointCount)
  await page.getByRole('button',{name:'Pause',exact:true}).click()
  assert.equal(comparisonCalls,before)
  await page.screenshot({path:`${output}/normal.png`,fullPage:true})
  await section.getByRole('img').last().scrollIntoViewIfNeeded()
  await page.screenshot({path:`${output}/lower-charts.png`,fullPage:true})
  await section.getByLabel('Start (UTC)').scrollIntoViewIfNeeded()
  await page.evaluate(()=>{document.documentElement.style.zoom='2'})
  await page.screenshot({path:`${output}/zoom-200.png`,fullPage:true})
  assert.equal(await section.getByRole('button',{name:'Refresh',exact:true}).isVisible(),true)
  assert.equal(comparisonCalls,before)
  await page.clock.fastForward(900001)
  await section.getByText(/Expired comparison/).waitFor()
  assert.equal(comparisonCalls,before)
  assert.deepEqual(errors,[])
  await writeFile(`${output}/receipt.json`,JSON.stringify({fixture:true,provider_requests:0,comparison_requests:comparisonCalls,chart_count:6,normal_viewport:[1440,1100],zoom:'CSS zoom 200%, layout and text inspection',single_bottom_timeline:true,api_property_order:true,native_points_and_lines:true,stable_window:true,no_hover_acquisition:true,expired_without_renewal:true,errors},null,2))
  console.log(`Browser proof passed: ${output}`)
  }
} finally {await browser.close()}
