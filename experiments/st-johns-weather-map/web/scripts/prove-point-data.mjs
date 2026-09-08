// Constructed browser evidence; real catalogue declarations, no provider weather traffic.
import { chromium } from 'playwright'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'

const output=process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-point-data-proof'
const base=process.env.BENCH_URL ?? 'http://127.0.0.1:5301'
const catalog=await (await fetch(`${process.env.BENCH_CATALOG_API ?? 'http://127.0.0.1:8197'}/api/experiments/weather/v0/catalog`)).json()
await mkdir(output,{recursive:true})
const at='2026-09-08T12:00:00Z'
const source=catalog.sources.find(s=>s.id==='noaa-gfs')
assert.ok(source)
const capability=source.capabilities.find(c=>c.field==='temperature_2m')
const fieldPoint=c=>({sourceId:c.source_id,productId:c.product_id,product:c.point_product,field:c.field,variant:c.variants[0],level:c.levels[0]})
const pointId=p=>`point:${encodeURIComponent(JSON.stringify([p.sourceId,p.productId,p.product,p.field]))}`
const pointEntry=c=>{const point=fieldPoint(c);return {id:pointId(point),visible:false,opacity:.85,pointOnly:true,points:[point]}}
const layers=source.capabilities.slice(0,10).map((c,index)=>({id:`proof-gfs-${index}`,title:`GFS · ${c.field.replaceAll('_',' ')}`,field:c.field,field_key:c.field,family:source.fields.find(f=>f.key===c.field)?.family ?? 'ungrouped',
  kind:'raster',product:capability.point_product,units:'declared by point response',semantics:'Constructed descriptor; no provider imagery',raster_available:false,evidence_class:'retrieved',
  mapping_status:'known',field_mappings:[{source_id:source.id,field_key:c.field,declared_field:c.field}],times:[at,'2026-09-08T13:00:00Z']}))
layers.push({id:'proof-image',title:'Image-only proof',kind:'raster',field:'satellite_natural_color',product:'Image proof',units:'RGB',semantics:'Constructed image-only capability',raster_available:false,times:[at]})
const context=await chromium.launchPersistentContext(await mkdtemp(`${tmpdir()}/point-data-chrome-`),{channel:'chrome',headless:true,viewport:{width:1440,height:900}})
const page=await context.newPage(), requests=[], errors=[], measures=[]
let temperature=17, radarEchoOnly=true
const radarSource=catalog.sources.find(s=>s.id==='eccc-radar')
assert.ok(radarSource?.capabilities.length)
page.on('pageerror',error=>errors.push(String(error)))
await page.route('**/api/experiments/weather/v0/**',async route=>{
  const url=new URL(route.request().url()),path=url.pathname.split('/v0')[1]
  requests.push({path,query:url.search})
  if(path==='/catalog') return route.fulfill({json:catalog})
  if(path==='/layers') return route.fulfill({json:{data_mode:'live',layers,notices:['Constructed browser test. Weather acquisition blocked.']}})
  if(path==='/point' && url.searchParams.get('product')==='Radar') {
    const fields=radarSource.capabilities.map(c=>({field:c.field,key:c.field,family:'precipitation',
      value:radarEchoOnly ? c.field==='radar_echo'?0:null : c.field==='radar_echo'?1:c.field==='snow_rate'?.4:2.5,
      provenance:{source_id:'eccc-radar',provider:'ECCC',product:'Radar',evidence_class:'retrieved',data_mode:'live',valid_time:at,
        normalized_units:c.field==='radar_echo'?'flag':c.field==='snow_rate'?'cm h-1':'mm h-1',quality:{status:'passed',flags:[]},licence:'Constructed browser proof'}}))
    return route.fulfill({json:{data_mode:'live',valid_time:url.searchParams.get('valid_time'),selection:{mode:'evidence_only',badge:'Constructed radar test'},fields}})
  }
  if(path==='/point' && url.searchParams.get('product')==='GFS') {
    const fields=source.capabilities.map((c,index)=>({field:c.field,key:c.field,family:source.fields.find(f=>f.key===c.field)?.family ?? 'ungrouped',value:index===0?temperature:index,
      provenance:{source_id:source.id,provider:'NOAA',product:'GFS',evidence_class:'retrieved',data_mode:'live',valid_time:at,run_time:'2026-09-08T06:00:00Z',normalized_units:index===0?'degC':'test units',quality:{status:'passed',flags:[]},licence:'Constructed browser proof; not weather evidence'}}))
    return route.fulfill({json:{data_mode:'live',valid_time:url.searchParams.get('valid_time'),selection:{mode:'evidence_only',badge:'Constructed test'},fields,notices:['Constructed values for UI verification only']}})
  }
  if(path==='/point' && url.searchParams.get('product')?.startsWith('WeatherNext')) return route.fulfill({json:{data_mode:'unavailable',valid_time:url.searchParams.get('valid_time'),selection:{mode:'evidence_only',reason:'Credentials required for WeatherNext test',badge:'Unavailable'},fields:[],notices:['Constructed credentials refusal']}})
  return route.fulfill({status:503,json:{detail:'Constructed verification withheld weather acquisition'}})
})
const panel=page.getByRole('complementary',{name:'Point data',exact:true})
const overlay=page.locator('.bench-overlay[aria-label="Layers overlay"]')
const browse=page.getByRole('region',{name:'Unified source discovery'})
const details=page.getByRole('region',{name:'Layer or source details'})
const stack=()=>JSON.parse(new URL(page.url()).searchParams.get('stack'))
const openLayers=async()=>{const button=page.getByRole('button',{name:'Layers',exact:true});if(await button.getAttribute('aria-expanded')!=='true')await button.click()}
const theme=async name=>{await page.locator('.bench-settings > summary').click();await page.getByRole('button',{name,exact:true}).click();await page.locator('.bench-settings > summary').click();await page.waitForTimeout(500)}
const measure=()=>page.evaluate(()=>{
  const rect=selector=>document.querySelector(selector)?.getBoundingClientRect().toJSON()
  const panel=document.querySelector('.point-data-panel'), contents=panel.querySelector('.point-data-contents')
  return {width:innerWidth,height:innerHeight,scrollX:document.documentElement.scrollWidth>innerWidth,scrollY:document.documentElement.scrollHeight>innerHeight,
    panel:rect('.point-data-panel'),map:rect('.bench-map-layout'),overlay:rect('.bench-overlay:not([hidden])'),timeline:rect('.bench-time-expanded'),
    heading:rect('.point-data-heading'), panelScroll:panel.scrollTop, contents:{height:contents.clientHeight,scrollHeight:contents.scrollHeight}}
})
try {
  const radarStack=[...radarSource.capabilities.map(pointEntry),{id:'proof-image',visible:true,opacity:1}]
  await page.goto(`${base}/?lat=47.5&lon=-52.7&t=${at}&stack=${encodeURIComponent(JSON.stringify(radarStack))}`)
  await panel.getByText('0 · no echo',{exact:true}).waitFor()
  await panel.getByRole('button',{name:/Point data not available \(3\)/}).waitFor()
  await page.screenshot({path:`${output}/radar-no-echo-and-unavailable.png`})
  radarEchoOnly=false
  await page.goto(`${base}/?lat=47.5&lon=-52.7&t=2026-09-08T12:01:00Z&stack=${encodeURIComponent(JSON.stringify(radarStack))}`)
  await panel.getByText('2.5 mm h-1',{exact:true}).waitFor()
  await panel.getByText('0.4 cm h-1',{exact:true}).waitFor()
  await page.screenshot({path:`${output}/radar-numeric-rain-snow.png`})
  await page.goto(`${base}/?lat=47.5&lon=-52.7&t=${at}&stack=[]`)
  await panel.getByText(/Select fields in Layers/).waitFor()
  const empty=await measure()
  await page.screenshot({path:`${output}/empty.png`})
  await page.mouse.move(570,250);await page.mouse.down();await page.mouse.move(620,275,{steps:10});await page.mouse.up();await page.waitForTimeout(1500)
  const cameraClip={x:500,y:200,width:150,height:150}
  const cameraBefore=await page.screenshot({clip:cameraClip})
  await openLayers();await page.getByRole('button',{name:'Browse',exact:true}).click()
  await browse.getByRole('combobox',{name:'Group by'}).selectOption('Ungrouped')
  await browse.getByRole('searchbox').fill('proof-gfs-0')
  const primary=browse.getByRole('button',{name:layers[0].title,exact:true})
  await primary.click()
  await panel.getByText('17 degC',{exact:true}).waitFor()
  assert.equal(stack()[0].visible,true)
  await page.screenshot({path:`${output}/one-reading.png`})
  await primary.press('Enter');assert.equal(stack()[0].visible,false)
  await primary.press('Space');assert.equal(stack().length,0)
  await primary.click();await panel.getByText('17 degC',{exact:true}).waitFor()
  const beforeDetails=JSON.stringify(stack())
  await primary.click({button:'right'});await details.waitFor()
  assert.equal(JSON.stringify(stack()),beforeDetails)
  await details.getByRole('slider').fill('0.35')
  await panel.getByRole('button',{name:'Minimize Point data'}).click()
  await details.getByRole('button',{name:'Open point data',exact:true}).click()
  await page.waitForFunction(()=>document.activeElement?.classList.contains('point-data-reading'))
  assert.equal(stack()[0].opacity,.35)
  const reading=panel.getByRole('button',{name:/Details for point reading/}).first()
  await reading.press('Enter');await panel.getByRole('heading',{name:/Evidence ·/}).waitFor()
  await page.keyboard.press('Escape');await page.waitForFunction(()=>document.activeElement?.classList.contains('point-data-reading'))
  await page.keyboard.press('Escape');await panel.getByRole('button',{name:'Expand Point data'}).waitFor()
  assert.ok(cameraBefore.equals(await page.screenshot({clip:cameraClip})),'Overlay controls changed the panned map')
  await page.screenshot({path:`${output}/minimized.png`})
  await details.getByRole('button',{name:/Back to/}).click()
  await browse.getByRole('searchbox').fill('WeatherNext 3 local')
  await browse.locator('.dense-layer-primary').first().click()
  await page.waitForTimeout(500)
  assert.equal(await panel.getByRole('button',{name:'Expand Point data'}).count(),1)
  await panel.getByRole('button',{name:'Expand Point data'}).click()
  await panel.getByText('Credentials required').waitFor()
  assert.equal(stack().filter(e=>e.pointOnly).length,1)
  await page.screenshot({path:`${output}/weathernext-credentials.png`})
  // Add more selected fields to exercise growth and internal scrolling.
  const many=[...source.capabilities.slice(0,10).map(pointEntry),{id:'proof-image',visible:true,opacity:.6}]
  await page.goto(`${base}/?lat=47.5&lon=-52.7&t=${at}&stack=${encodeURIComponent(JSON.stringify(many))}`)
  await panel.getByText('Image only',{exact:true}).waitFor()
  await panel.getByText('17 degC',{exact:true}).waitFor()
  const grown=await measure()
  assert.ok(grown.panel.height>empty.panel.height)
  assert.ok(grown.contents.scrollHeight>grown.contents.height)
  // Browser preference survives reload; requests still refresh while minimized.
  await panel.getByRole('button',{name:'Minimize Point data'}).click()
  temperature=19;const beforeRefresh=requests.length
  await page.reload();await panel.getByRole('button',{name:'Expand Point data'}).waitFor()
  await page.waitForTimeout(600)
  assert.ok(requests.slice(beforeRefresh).some(r=>r.path==='/point'&&r.query.includes('product=GFS')))
  await panel.getByRole('button',{name:'Expand Point data'}).click();await panel.getByText('19 degC',{exact:true}).waitFor()
  // Save/load retains point identities, order and image opacity.
  await openLayers();await overlay.getByText('Stacks',{exact:true}).click()
  await overlay.getByRole('textbox',{name:'Stack name'}).fill('Point proof')
  await overlay.getByRole('button',{name:'Save stack',exact:true}).click()
  await overlay.getByRole('button',{name:'Remove Image-only proof',exact:true}).click()
  await overlay.getByRole('combobox',{name:'Saved stacks'}).selectOption('Point proof')
  assert.deepEqual(stack(),many)
  await overlay.getByText('Stacks',{exact:true}).click()
  // Preserve the map canvas and camera across overlay operations.
  const canvas=await page.locator('.maplibregl-canvas').elementHandle()
  const mapBefore=await page.locator('.maplibregl-canvas').boundingBox()
  await page.getByRole('button',{name:'Tracks',exact:true}).click()
  assert.equal(await overlay.isVisible(),true)
  assert.deepEqual(await page.locator('.maplibregl-canvas').boundingBox(),mapBefore)
  for(const zoom of [100,200]) {
    if(zoom===200){const settings=await context.newPage();await settings.goto('chrome://settings/appearance');await settings.locator('#zoomLevel').selectOption({label:'200%'});await settings.close()}
    for(const [width,height] of [[1280,800],[1440,900],[1920,1080]]) {
      await page.setViewportSize({width,height})
      for(const name of ['dark','light','Red night']) {
        await theme(name)
        await panel.locator('.point-data-contents').evaluate(el=>el.scrollTop=0)
        const m=await measure()
        assert.equal(m.scrollX,false);assert.equal(m.scrollY,false)
        if(zoom===200)assert.equal(m.width,width/2)
        assert.ok(m.panel.x>=m.map.x && m.panel.right<=m.map.right+1)
        assert.ok(m.panel.bottom<=m.timeline.top+1)
        assert.ok(m.panel.height<=m.map.height*.5+1)
        assert.ok(m.heading.top>=m.panel.top && m.heading.bottom<=m.panel.bottom,JSON.stringify(m))
        assert.equal(m.panelScroll,0)
        assert.ok(m.contents.height>=22,JSON.stringify(m))
        const overlap=m.panel.x<m.overlay.right&&m.panel.right>m.overlay.x&&m.panel.y<m.overlay.bottom&&m.panel.bottom>m.overlay.y
        assert.equal(overlap,false,JSON.stringify(m))
        measures.push({zoom,theme:name,...m})
        const prefix=`${output}/${width}x${height}-${name.replace(' ','-')}-${zoom}`
        await page.screenshot({path:`${prefix}-layers-timeline.png`})
        await panel.locator('.point-data-reading').first().click()
        await panel.getByRole('heading',{name:/Evidence ·/}).waitFor()
        await page.screenshot({path:`${prefix}-provenance-layers-timeline.png`})
        await page.keyboard.press('Escape')
        await page.waitForFunction(()=>document.activeElement?.classList.contains('point-data-reading'))
      }
    }
  }
  assert.equal(await canvas.evaluate(el=>el===document.querySelector('.maplibregl-canvas')),true)
  assert.deepEqual(errors,[])
  await writeFile(`${output}/results.json`,JSON.stringify({constructed:true,providerWeatherRequests:0,requests,measures,errors},null,2))
  console.log(`Point data proof passed: ${measures.length} size/theme/zoom combinations; ${output}`)
} finally { await context.close() }
