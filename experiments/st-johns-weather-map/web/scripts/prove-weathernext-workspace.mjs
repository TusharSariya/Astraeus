// Synthetic browser proof. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
import { chromium } from 'playwright'
import {readFile,writeFile,mkdir,mkdtemp} from 'node:fs/promises'
import assert from 'node:assert/strict'
const base=process.env.BENCH_URL??'http://127.0.0.1:5391'
const output=new URL('../../../../docs/evidence/weathernext-workspace-20260909/browser/',import.meta.url).pathname
await mkdir(output,{recursive:true})
const fixture=JSON.parse(await readFile(new URL('../../contracts/fixtures/source-delivery.json',import.meta.url),'utf8'))
const at='2026-09-09T12:00:00.000Z',errors=[],selections=new Map()
let science=0,thresholds=0,pausePages=false,held=[]
const context=await chromium.launchPersistentContext(await mkdtemp('/tmp/wn-workspace-'),{channel:'chrome',headless:true,viewport:{width:1440,height:1100}})
const page=await context.newPage()
page.on('pageerror',e=>errors.push(String(e)))
await page.clock.install({time:new Date(at)})
const makePage=(selection,id,offset=0)=>{
 const start=Math.ceil(Date.parse(selection.start)/3600000)*3600000
 const times=Array.from({length:36},(_,i)=>new Date(start+i*3600000).toISOString()).filter(t=>Date.parse(t)<Date.parse(selection.end))
 const qs=selection.section==='clouds'?['total_cloud_cover','low_cloud_cover','medium_cloud_cover','high_cloud_cover']:selection.section==='precipitation'?['total_precipitation_1hr']:['temperature_2m','dewpoint_temperature_2m']
 const quantityIndex=Math.floor(offset/times.length),timeIndex=offset%times.length
 return {completed_pages:offset+1,total_pages:times.length*qs.length,id,selection,run_id:'synthetic-run',run_time:'2026-09-09T00:00:00Z',native_times:times,expires_at:'2026-09-09T12:15:00Z',state:'available',next_offset:offset+1<times.length*qs.length?offset+1:null,samples:times.slice(timeIndex,timeIndex+1).map((t,i)=>({time:t,expires_at:'2026-09-09T12:01:00Z',provenance:{...fixture.series.series[0].samples[0].provenance,source_id:'google-weathernext-3-statistics',run_time:'2026-09-09T00:00:00Z',valid_time:t},summaries:qs.slice(quantityIndex,quantityIndex+1).map(q=>{
 const j=quantityIndex
 const cloud=q.includes('cloud'),precip=q.includes('1hr'),a=cloud?[[4,8,12,16,20],[0,2,8,45,90],[5,20,45,75,95],[0,null,25,50,65]][j]:precip?[0,0,0,0,8]:[5,10,12,15,19]
 const values=Object.fromEntries(['p10','p25','p50','p75','p90'].map((s,k)=>[s,a[k]===null?null:a[k]+(precip?0:Math.sin(i/4)*2)]));values.mean=precip?1:20
 return {quantity:q,unit:cloud?'percent':precip?'mm':'degC',values,state:'available',sampled_latitude:47.5,sampled_longitude:-52.7,native_fields:Object.keys(values).map(s=>q+'_'+s),grid:'0p1',level:'surface',original_unit:cloud?'(0 - 1)':precip?'m':'K',conversion_scale:cloud?100:precip?1000:1,conversion_offset:cloud||precip?0:-273.15,interval_start:precip?new Date(Date.parse(t)-3600000).toISOString():null,interval_end:precip?t:null}
 })}))}
}
await page.route('**/*',async route=>{
 const u=new URL(route.request().url());if(u.origin!==new URL(base).origin)return route.abort()
 if(!u.pathname.startsWith('/api/'))return route.continue()
 const path=u.pathname.split('/v0')[1]
 if(path?.startsWith('/weathernext/selection')){
  const idFrom=path.split('/')[3]
  if(path.endsWith('/threshold')){thresholds++;const threshold=route.request().postDataJSON(),s=selections.get(idFrom),p=makePage(s,idFrom);return route.fulfill({json:{id:idFrom,run_time:p.run_time,threshold,estimates:Object.fromEntries(Array.from({length:p.total_pages},(_,i)=>makePage(s,idFrom,i)).flatMap(p=>p.samples).filter(sample=>sample.summaries.some(v=>v.quantity===threshold.quantity)).map(sample=>{const v=sample.summaries.find(v=>v.quantity===threshold.quantity)?.values??{};const qs=[10,25,50,75,90].filter(q=>typeof v['p'+q]==='number');const low=qs.filter(q=>v['p'+q]<threshold.value).at(-1)??0,high=qs.find(q=>v['p'+q]>threshold.value)??100;return [sample.time,{lower:threshold.event==='above'?100-high:low,upper:threshold.event==='above'?100-low:high,approximate:true,basis:`Synthetic expected bracket P${low}–P${high}; estimate from published percentiles`}] }))}})}
  if(route.request().method()==='DELETE')return route.fulfill({status:204})
  science++;let id=idFrom,s=selections.get(id),offset=Number(u.searchParams.get('offset')??0)
  if(route.request().method()==='POST'){s=route.request().postDataJSON();id='selection-'+science;selections.set(id,s)}
  if(pausePages&&offset)await new Promise(resolve=>held.push(resolve))
  return route.fulfill({json:makePage(s,id,offset)})
 }
 let body={data_mode:'unavailable',notices:[]}
 if(path==='/catalog')body=fixture.catalog
 else if(path==='/sources/status')body=fixture.status
 else if(path==='/point')body={...fixture.point,latitude:47.5,longitude:-52.7,valid_time:at,fields:[]}
 else if(path==='/layers')body={data_mode:'fixture',layers:[],notices:[]}
 else if(path==='/methods')body={data_mode:'fixture',methods:[],notices:[]}
 else if(path==='/registry/sites')body={operational:false,version:'a'.repeat(64),sites:[],notice:null}
 return route.fulfill({json:body})
})
try{
 await page.goto(`${base}/?view=weathernext&lat=47.5&lon=-52.7&t=${at}`,{waitUntil:'domcontentloaded'})
 await page.addStyleTag({content:'.wn-chart figcaption::after{content:" · SYNTHETIC DATA";font-size:.7rem}'})
 const section=page.getByRole('region',{name:'WeatherNext forecast workspace'})
 await section.getByText('Loading complete',{exact:true}).waitFor();await page.clock.runFor(300)
 assert.equal(await section.getByRole('img').count(),4);assert.equal(await section.getByRole('slider').count(),0)
 await page.evaluate(()=>{const el=document.createElement('p');el.textContent='SYNTHETIC DESIGN DATA · NOT A FORECAST';el.style.fontWeight='bold';document.querySelector('.wn-workspace').prepend(el)})
 const before=science
 await section.getByLabel('Show mean').check();await section.getByLabel('Threshold (%)').fill('40');await page.clock.runFor(300)
 await section.getByLabel('Next Total time').focus();await page.keyboard.press('Enter')
 const timeline=page.getByRole('slider',{name:'Valid timeline scrubber'});assert.equal(await timeline.count(),1)
 await timeline.focus();await page.keyboard.press('ArrowRight');assert.equal(science,before)
 for(const theme of ['light','dark','night']){await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);for(const width of [1440,390]){await page.setViewportSize({width,height:1100});await section.locator('figure').first().scrollIntoViewIfNeeded();await page.screenshot({path:`${output}/${theme}-${width}.png`});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)}}
 await page.setViewportSize({width:1440,height:1100})
 for(let i=1;i<4;i++){await section.locator('figure').nth(i).scrollIntoViewIfNeeded();await page.screenshot({path:`${output}/cloud-${i}.png`})}
 const settings=await context.newPage();await settings.goto('chrome://settings/appearance');await settings.locator('#zoomLevel').selectOption({label:'200%'});await settings.close();await page.waitForFunction(()=>innerWidth===720)
 await section.locator('figure').first().scrollIntoViewIfNeeded();await page.screenshot({path:`${output}/zoom-200.png`});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
 const reset=await context.newPage();await reset.goto('chrome://settings/appearance');await reset.locator('#zoomLevel').selectOption({label:'100%'});await reset.close()
 await section.getByRole('button',{name:'Precipitation',exact:true}).click();await section.getByText('Loading complete',{exact:true}).waitFor();await section.getByLabel('Threshold (mm)').fill('0');await page.clock.runFor(300);await page.screenshot({path:`${output}/precipitation-ties.png`})
 await section.getByRole('button',{name:'Clouds',exact:true}).click();const cached=science;await page.clock.runFor(300);assert.equal(science,cached)
 pausePages=true;await section.getByRole('button',{name:'Refresh selection'}).click();await section.getByText(/Loading · [1-9]/).waitFor();await page.screenshot({path:`${output}/pending.png`});pausePages=false;held.forEach(r=>r());held=[]
 await section.getByText('Loading complete',{exact:true}).waitFor();await page.clock.runFor(61000);await page.screenshot({path:`${output}/expired.png`})
 assert.equal(errors.length,0,errors.join('\n'))
 await writeFile(`${output}/result.json`,JSON.stringify({synthetic:true,providerRequests:0,scienceApiRequests:science,thresholdRequests:thresholds,errors,checks:['four aligned charts','shared timeline keyboard','keyboard details','no display science downloads','section cache reuse','three themes','390px narrow','actual browser 200% zoom','precipitation ties','pending pages','expiry']},null,2))
 console.log('WeatherNext synthetic browser proof passed')
}finally{held.forEach(r=>r());await context.close()}
