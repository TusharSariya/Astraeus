import {useEffect,useRef,useState,useMemo} from 'react'
import type {LayerSelection} from '../types'
import type {components} from '../generated/source-api'
export type IFSGrid = components['schemas']['IFSGrid']
const base='/api/experiments/weather/v0/ifs'
type Definition={id:string;parameter:string;name:string;units:string;levels:number[];products:string[];rendering:string;product_levels?:Record<string,number[]>}
type Catalogue={fields:Definition[];products:{id:string;format:string}[]}
type Run={id:string;run_time:string;files:Record<string,string>}
export type IFSOptions={product:string;field:string;level:number;run:string;member:string;statistic:string;rendering:string;title:string;refresh?:number}
export function IFSLayers({stack,onChange}:{stack:LayerSelection[];onChange:(s:LayerSelection[])=>void}) {
 const [catalogue,setCatalogue]=useState<Catalogue|null>(null),[product,setProduct]=useState('atmosphere-control'),[field,setField]=useState('2t:sfc'),[level,setLevel]=useState(0),[run,setRun]=useState('latest'),[runs,setRuns]=useState<Run[]>([]),[search,setSearch]=useState(''),[error,setError]=useState('')
 useEffect(()=>{const c=new AbortController();fetch(`${base}/catalogue`,{signal:c.signal}).then(r=>r.json()).then(value=>setCatalogue(Array.isArray(value?.fields)&&Array.isArray(value?.products)?value:null)).catch(()=>{});return()=>c.abort()},[])
 useEffect(()=>{const c=new AbortController();setRuns([]);setRun('latest');setError('');fetch(`${base}/runs/${product}`,{signal:c.signal}).then(async r=>{if(!r.ok)throw new Error('IFS inventory unavailable');return r.json()}).then(value=>{if(!Array.isArray(value))throw new Error('IFS inventory unavailable');setRuns(value)}).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>c.abort()},[product])
 const fields=product.startsWith('cyclone')?[{id:'tracks',parameter:'tracks',name:'Cyclone tracks',units:'degrees',levels:[0],products:[product],rendering:'track',product_levels:undefined}]:(catalogue?.fields.filter(f=>f.products.includes(product))??[]),selected=fields.find(f=>f.id===field)
 const update=(id:string,changes:Partial<LayerSelection>)=>onChange(stack.map(s=>s.id===id?{...s,...changes}:s))
 return <details><summary>IFS Atlantic products</summary>
  <p>Native Atlantic cells · experimental · catalogue entries do not guarantee published data.</p>
  <label>Product<select value={product} onChange={e=>{setProduct(e.target.value);const f=catalogue?.fields.find(f=>f.products.includes(e.target.value));setField(e.target.value.startsWith('cyclone')?'tracks':f?.id??'');setLevel(f?.levels[0]??0)}}>{catalogue?.products.map(p=><option key={p.id} value={p.id} >{p.id}</option>)}</select></label>
  <label>Search fields<input type="search" value={search} onChange={e=>setSearch(e.target.value)}/></label>
  <label>Field<select value={field} onChange={e=>{setField(e.target.value);const f=fields.find(f=>f.id===e.target.value);setLevel(f?.product_levels?.[product]?.[0]??f?.levels[0]??0)}}>{fields.filter(f=>`${f.name} ${f.parameter}`.toLowerCase().includes(search.toLowerCase())||f.id===field).map(f=><option key={f.id} value={f.id}>{f.name} ({f.parameter}) · {f.units}</option>)}</select></label>
  <label>Level<select value={level} onChange={e=>setLevel(Number(e.target.value))}>{(selected?.product_levels?.[product]??selected?.levels??[]).map(l=><option key={l}>{l}</option>)}</select></label>
  <label>Run<select value={run} onChange={e=>setRun(e.target.value)}><option value="latest">Latest advertised product run</option>{runs.map(r=><option key={r.id} value={r.id}>{r.run_time}</option>)}</select></label>
  <button disabled={!selected||!runs.length} onClick={()=>{if(!selected)return;onChange([...stack,{id:`ifs-${crypto.randomUUID()}`,visible:true,opacity:.7,ifs:{product,field,level,run,member:product.startsWith('cyclone')?'all':'0',statistic:product.endsWith('ensemble')&&!['direction','categorical'].includes(selected.rendering)?'ensemble_mean':'',rendering:selected.rendering,title:selected.name}}])}}>Add IFS layer</button>
  {error&&<p role="status">{error}</p>}
  {stack.filter(s=>s.ifs).map(s=><fieldset key={s.id}><legend>{s.ifs!.title} · {s.ifs!.product} · {s.ifs!.level}</legend>
   <label><input type="checkbox" checked={s.visible} onChange={e=>update(s.id,{visible:e.target.checked})}/>Visible</label>
   <label>Opacity<input type="range" min="0" max="1" step=".05" value={s.opacity} onChange={e=>update(s.id,{opacity:Number(e.target.value)})}/></label>
   {s.ifs!.product.endsWith('ensemble')&&<>
   {!['direction','categorical','track'].includes(s.ifs!.rendering)&&<label>Statistic<select value={s.ifs!.statistic} onChange={e=>update(s.id,{ifs:{...s.ifs!,statistic:e.target.value}})}><option value="ensemble_mean">Mean</option><option value="ensemble_spread">Sample standard deviation</option><option value="">Native member</option></select></label>}
   <label>Member<select value={s.ifs!.member} onChange={e=>update(s.id,{ifs:{...s.ifs!,member:e.target.value,statistic:''}})}>{s.ifs!.product.startsWith('cyclone')&&<option value="all">All native members</option>}{Array.from({length:51},(_,i)=>{const n=s.ifs!.product.startsWith('cyclone')?i+1:i;return <option key={n} value={String(n)}>{(s.ifs!.product.startsWith('cyclone')?n===51:n===0)?`${n} · control`:n}</option>})}</select></label></>}
   <button onClick={()=>update(s.id,{ifs:{...s.ifs!,refresh:(s.ifs!.refresh??0)+1}})}>Refresh IFS layer</button><button onClick={()=>onChange(stack.filter(x=>x.id!==s.id))}>Remove IFS layer</button>
  </fieldset>)}
 </details>
}

type GridState={id:string;tracks?:components['schemas']['IFSTracks'];frame?:IFSGrid;error?:string;job?:string;progress?:string}
const frames=new Map<string,IFSGrid>()
function remember(key:string,frame:IFSGrid){frames.set(key,frame);while([...frames.values()].reduce((n,g)=>n+JSON.stringify(g).length,0)>8*1024**2)frames.delete(frames.keys().next().value!)}
async function getJSON(url:string,signal:AbortSignal,body?:unknown){
 const r=await fetch(url,{signal,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})})
 if(!r.ok)throw new Error(`IFS request failed (${r.status})`)
 const reader=r.body?.getReader();if(!reader)throw new Error('IFS response unavailable')
 const chunks:Uint8Array[]=[];let size=0
 try{for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>512*1024)throw new Error('IFS response exceeds page bound');chunks.push(value)}}finally{await reader.cancel();reader.releaseLock()}
 const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength}
 return JSON.parse(new TextDecoder().decode(bytes))
}
export function useIFSGrids(stack:LayerSelection[],instant:number,includeHidden=false){
 const wanted=stack.filter(s=>s.ifs).map(s=>({id:s.id,...s.ifs!}))
 const latest=useRef(wanted);latest.current=wanted
 const active=useRef(new Map<string,{key:string;controller:AbortController;job?:string;track?:boolean}>())
 const [rows,setRows]=useState<GridState[]>([])
 const set=(id:string,patch:Partial<GridState>)=>setRows(r=>r.some(x=>x.id===id)?r.map(row=>row.id===id?{...row,...patch}:row):[...r,{id,...patch}])
 const signature=JSON.stringify(wanted.map(({member,statistic,rendering,title,...s})=>s))+instant
 useEffect(()=>{
  const identities=new Map(wanted.map(({member,statistic,rendering,title,...s})=>[s.id,JSON.stringify(s)+instant]))
  for(const [id,work] of active.current){if(identities.get(id)!==work.key){work.controller.abort();if(work.job)void fetch(`${base}/${work.track?'track-selections':'selections'}/${work.job}`,{method:'DELETE'}).catch(()=>{});active.current.delete(id);setRows(r=>r.filter(x=>x.id!==id))}}
  for(const item of wanted){if(active.current.has(item.id))continue
   const controller=new AbortController(),work:{key:string;controller:AbortController;job?:string;track?:boolean}={key:identities.get(item.id)!,controller};active.current.set(item.id,work);set(item.id,{frame:undefined,tracks:undefined,job:undefined,error:undefined,progress:undefined})
   void(async()=>{try{
    const runs:Run[]=await getJSON(`${base}/runs/${item.product}`,controller.signal)
    const run=runs.find(r=>item.run==='latest'||r.id===item.run);if(!run)throw new Error('IFS run expired or unpublished')
    if(item.product.startsWith('cyclone')){
     let page:components['schemas']['IFSTrackPage']=await getJSON(`${base}/track-selections`,controller.signal,{product:item.product,run:run.id})
     work.job=page.id;work.track=true
     while(!page.complete){if(controller.signal.aborted)return;set(item.id,{progress:`Decoding native tracks · ${page.bytes_received} bytes`});page=await getJSON(`${base}/track-selections/${page.id}`,controller.signal)}
     if(!page.result)throw new Error(page.reason??'IFS tracks unavailable')
     const tracks=page.result
     if(tracks.product!==item.product||tracks.run_id!==run.id)throw new Error('IFS track selection changed')
     if(!controller.signal.aborted)set(item.id,{tracks,progress:`${tracks.tracks.length} native tracks`})
     return
    }
    const times=Object.keys(run.files).map(Number).filter(n=>n>=0).map(n=>Date.parse(run.run_time)+n*3600000).sort((a,b)=>a-b)
    const native=times.find(n=>n>=instant);if(native===undefined)throw new Error('No native time in the selected window')
    let page=await getJSON(`${base}/selections`,controller.signal,{fields:[{product:item.product,field:item.field,level:item.level,run:run.id,times:[new Date(native).toISOString()]}]})
    const job=page.id;work.job=job;set(item.id,{job})
    for(;;){if(controller.signal.aborted)return;set(item.id,{progress:`${page.completed}/${page.total} records`});if(page.next_cursor===null)break;page=await getJSON(`${base}/selections/${job}?cursor=${page.next_cursor}`,controller.signal)}
    const current=latest.current.find(x=>x.id===item.id);if(!current||controller.signal.aborted)return
    const params=new URLSearchParams(current.statistic?{statistic:current.statistic}:{member:current.member})
    const grid:IFSGrid=await getJSON(`${base}/selections/${job}/grid?${params}`,controller.signal)
    const final=latest.current.find(x=>x.id===item.id)
    if(grid.selection_product!==item.product||grid.field!==item.field||grid.level!==item.level||Date.parse(grid.native_time)!==native)throw new Error('IFS grid selection changed')
    if(controller.signal.aborted)return
    remember(`${job}:${current.statistic}:${current.member}`,grid)
    if(final?.statistic===current.statistic&&final?.member===current.member)set(item.id,{frame:grid})
    else set(item.id,{progress:'Ready for selected variant'})
   }catch(e){if(!controller.signal.aborted)set(item.id,{error:String(e),frame:undefined})}})()
  }
 },[signature])
 useEffect(()=>()=>{for(const work of active.current.values()){work.controller.abort();if(work.job)void fetch(`${base}/${work.track?'track-selections':'selections'}/${work.job}`,{method:'DELETE'}).catch(()=>{})}active.current.clear()},[])
 const variants=JSON.stringify(wanted.map(s=>[s.id,s.member,s.statistic]))
 useEffect(()=>{const c=new AbortController();for(const item of wanted){const row=rows.find(r=>r.id===item.id);if(!row?.job||(!row.frame&&row.progress!=='Ready for selected variant'))continue
   if(row.frame&&(row.frame.statistic??'')===item.statistic&&(item.statistic||row.frame.member===item.member))continue
   const key=`${row.job}:${item.statistic}:${item.member}`,cached=frames.get(key)
   const apply=(frame:IFSGrid)=>{if(c.signal.aborted)return;if(Date.parse(frame.expires_at)<=Date.now()){set(item.id,{frame:undefined,error:'Expired IFS evidence · Refresh required'});return}if((frame.statistic??'')!==item.statistic||(!item.statistic&&frame.member!==item.member))throw new Error('IFS variant changed');set(item.id,{frame,error:undefined})}
   if(cached){apply(cached);continue}
   const params=new URLSearchParams(item.statistic?{statistic:item.statistic}:{member:item.member})
   void getJSON(`${base}/selections/${row.job}/grid?${params}`,c.signal).then(g=>{remember(key,g);apply(g)}).catch(e=>{if(!c.signal.aborted)set(item.id,{frame:undefined,error:String(e)})})
  }return()=>c.abort()},[variants,rows.map(r=>`${r.job}:${r.progress}:${r.frame?.digest}`).join(',')])
 useEffect(()=>{const timers=rows.flatMap(r=>(r.frame||r.tracks)?[setTimeout(()=>set(r.id,{frame:undefined,tracks:undefined,error:'Expired IFS evidence · Refresh required'}),Math.max(0,Date.parse((r.frame??r.tracks)!.expires_at)-Date.now()))]:[]);return()=>timers.forEach(clearTimeout)},[rows.map(r=>r.frame?.expires_at??r.tracks?.expires_at).join(',')])
 const currentRows=rows.filter(r=>{
  const item=wanted.find(s=>s.id===r.id);if(!item)return false
  const {member,statistic,rendering,title,...identity}=item
  if(active.current.get(r.id)?.key!==JSON.stringify(identity)+instant)return false
  return !r.frame || ((r.frame.statistic??'')===statistic && (!!statistic || r.frame.member===member))
 })
 return useMemo(()=>includeHidden ? currentRows : currentRows.filter(r=>stack.find(s=>s.id===r.id)?.visible),[rows,signature,variants,includeHidden,JSON.stringify(stack.map(s=>[s.id,s.visible]))])
}
export function ifsPolygon(g:IFSGrid,i:number){const y=Math.floor(i/g.longitudes.length),x=i%g.longitudes.length;const w=Math.max(-70,Math.min(g.longitude_edges[x],g.longitude_edges[x+1])),e=Math.min(-40,Math.max(g.longitude_edges[x],g.longitude_edges[x+1])),s=Math.max(40,Math.min(g.latitude_edges[y],g.latitude_edges[y+1])),n=Math.min(55,Math.max(g.latitude_edges[y],g.latitude_edges[y+1]));return [[w,s],[e,s],[e,n],[w,n]]}
export function ifsColor(value:number|null,opacity:number,min:number,max:number,rendering:string):[number,number,number,number]{if(value===null)return [100,100,100,opacity*100];if(rendering==='cloud')return [255,255,255,Math.max(0,Math.min(1,value))*opacity*255];if(rendering==='categorical'){const colors=[[90,90,90],[60,150,240],[245,170,50],[210,80,110],[140,90,230],[230,240,255],[80,210,200],[210,210,70]];const c=colors[Math.abs(Math.round(value))%colors.length];return [c[0],c[1],c[2],opacity*220]}const ratio=(value-min)/(max-min||1);return [255*ratio,120,255*(1-ratio),opacity*220]}
