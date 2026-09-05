// THROWAWAY station/point study: captured/live evidence normalization, no science or production behavior.
export const FOCUSES = [
  {id:'signal-hill',label:'Signal Hill',lat:47.5704,lon:-52.6816,coordinateBasis:'Existing map Focus; not a weather station'},
  {id:'cyyt',label:'CYYT airport',lat:47.6186,lon:-52.7519,coordinateBasis:'ingest/adapters/awc.py CYYT_LAT/CYYT_LON; reference location, not returned observation geometry'},
  {id:'arbitrary',label:'Arbitrary point',lat:47.54,lon:-52.8,coordinateBasis:'Chosen query coordinate; not a station'},
];
export const TIMES = ['2026-09-04T01:00:00Z','2026-09-05T01:00:00Z'];
const API = '/api/experiments/weather/v0';
const SPECS = [
 {id:'awc-metar-speci-surface',label:'CYYT METAR / SPECI',sourceId:'awc-metar-speci',kind:'station'},
 {id:'awc-taf-surface',label:'CYYT TAF',sourceId:'awc-taf',kind:'station'},
 {id:'eccc-aqhi-aqhi',label:'AQHI',sourceId:'eccc-aqhi',kind:'station'},
 {id:'eccc-cap-alerts-alerts',label:'CAP alert points',sourceId:'eccc-cap-alerts',kind:'alert'},
 {id:'eccc-hrdps-surface',label:'HRDPS surface bundle',sourceId:'eccc-hrdps',kind:'surface'},
 {id:'eccc-rdps-surface',label:'RDPS surface bundle',sourceId:'eccc-rdps',kind:'surface'},
 {id:'noaa-gfs-surface',label:'GFS surface / column bundle',sourceId:'noaa-gfs',kind:'surface'},
 {id:'noaa-gfs-upper_air',label:'GFS upper-air bundle',sourceId:'noaa-gfs',kind:'upper-air'},
];
const routeForPoint = (f,t) => '/point?'+new URLSearchParams({latitude:f.lat,longitude:f.lon,valid_time:t});
const routeForFeatures = (id,t) => '/layers/'+encodeURIComponent(id)+'/features?'+new URLSearchParams({valid_time:t});
function lookup(bundle,path,params={}) {
 return Object.values(bundle.requests||{}).find(r=>{
  const u=new URL(r.route,'http://prototype.invalid');
  return u.pathname===path && Object.entries(params).every(([k,v])=>k==='valid_time' ? Date.parse(u.searchParams.get(k))===Date.parse(v) : Number.isFinite(Number(v)) ? Number(u.searchParams.get(k))===Number(v) : u.searchParams.get(k)===String(v));
 });
}
function fieldReading(f,spec,validTime,point) {
 const p=f.provenance||{};
 const supportedClasses=['retrieved','reprocessed','derived_here','intermediary_derived'];
 let rejected=null;
 if(typeof f.value!=='number'||!Number.isFinite(f.value)) rejected=f.absence_state||'No finite numeric value returned';
 else if(point?.data_mode!=='live'||p.data_mode!=='live') rejected='Numeric payload is not live evidence';
 else if(p.source_id!==spec.sourceId||!p.provider||!p.product||!p.normalized_units) rejected='Source or required provenance is missing';
 else if(!supportedClasses.includes(p.evidence_class)) rejected='Evidence class is missing or unsupported for numeric weather';
 else if(p.quality?.status!=='passed') rejected='Quality has not passed';
 else if(f.blocked||f.absence_state) rejected='The field is blocked or carries an absence state';
 else if(Date.parse(p.valid_time)!==Date.parse(validTime)||Date.parse(point.valid_time)!==Date.parse(validTime)) rejected='Returned sample time does not match Focus; no substitution';
 else if(spec.sourceId==='awc-taf') rejected='TAF forecast-period end time is unavailable; report validity cannot be admitted';
 return {field:f.field,key:f.key,value:rejected?null:f.value,unit:p.normalized_units,cls:p.evidence_class,provenance:p,
  reason:rejected||(p.freshness?.status==='stale'?'Stale retrieved evidence':'Returned by /point'),
  valueReadable:!rejected,raw:f};
}
export function normalize(bundle,focusId,validTime) {
 const focus=typeof focusId==='object'?focusId:(bundle.focuses||FOCUSES).find(f=>f.id===focusId)||FOCUSES[0];
 const layerRequest=lookup(bundle,'/layers');
 const layers=layerRequest?.status===200&&layerRequest.body?.data_mode==='live'&&Array.isArray(layerRequest.body?.layers)?layerRequest.body.layers:[];
 const pointRequest=lookup(bundle,'/point',{latitude:focus.lat,longitude:focus.lon,valid_time:validTime});
 const point=pointRequest?.status===200&&pointRequest.body?.latitude===focus.lat&&pointRequest.body?.longitude===focus.lon&&Array.isArray(pointRequest.body?.fields)?pointRequest.body:null;
 const timeline=lookup(bundle,'/timeline')?.body;
 const records=SPECS.map(spec=>{
  const layer=layers.find(l=>l.id===spec.id)||null;
  const featureRequest=lookup(bundle,'/layers/'+spec.id+'/features',{valid_time:validTime});
  const lastTime=layer?.times?.at(-1)||null;
  const lastRequest=lastTime?lookup(bundle,'/layers/'+spec.id+'/features',{valid_time:lastTime}):null;
  const fields=(point?.fields||[]).filter(f=>f.provenance?.source_id===spec.sourceId).filter(f=>{
   const upper=/hPa|isobaric/i.test(f.provenance?.vertical_level||'');
   return spec.kind==='upper-air'?upper:spec.kind==='surface'?!upper:true;
  });
  const readings=fields.map(f=>fieldReading(f,spec,validTime,point));
  const returnedGeometry=Array.isArray(featureRequest?.body?.features)&&featureRequest.body.features.some(f=>f.geometry!=null);
  const numeric=readings.filter(r=>r.valueReadable);
  const station=spec.kind==='station'||spec.kind==='alert';
  const cyyt=spec.sourceId.startsWith('awc-');
  const stale=numeric.some(r=>r.provenance.freshness?.status==='stale');
  const delta=lastTime?(Date.parse(validTime)-Date.parse(lastTime))/1000:null;
  const withinTolerance=delta!==null&&delta>=0&&delta<=(layer?.staleness_tolerance_seconds??0);
  const sourceNotices=(point?.notices||[]).filter(n=>n.includes(spec.sourceId));
  let reason;
  if(!pointRequest) reason='No capture for this exact coordinate and time. No nearby capture substituted.';
  else if(pointRequest.status!==200||!point) reason=pointRequest.body?.detail||'Point response is unavailable or malformed';
  else if(numeric.length) reason=station?'Returned evidence has no verified station geometry / report validity for a map marker.':`${numeric.length} model fields sampled for Focus. ${stale?'Retrieval is stale. ':''}These are not station observations.`;
  else reason=sourceNotices[0]||featureRequest?.body?.notices?.join(' ')||point?.selection?.reason||'No returned value for this source at Focus.';
  if(returnedGeometry) reason+=' Feature response contains geometry but this study cannot establish report/source/time admission; no weather marker is drawn.';
  if(station&&lastTime&&!withinTolerance) reason+=` Last advertised sample ${lastTime} is outside the Focus tolerance; not substituted.`;
  if(spec.sourceId==='awc-taf') reason+=' TAF forecast-period end times are not available in this response; cadence does not establish a validity interval.';
  // A Focus response establishes a sample location, not a station identifier.
  // This study does not admit live feature geometry without a report contract.
  return {...spec,readings,geometry:null,geometryBasis:returnedGeometry?'Feature response contains geometry but this study cannot establish report/source/time admission':station?'No verified report geometry returned':'Model sample coordinates are provenance, not a station marker',
   referenceGeometry:cyyt?[-52.7519,47.6186]:null,referenceGeometryBasis:cyyt?'Adapter station reference only; no available observation implied':null,
   eligible:false,valueReadable:numeric.length>0,stale,reason,reportTime:numeric[0]?.provenance.valid_time||null,
   validity:null,focusTime:validTime,lastAdvertisedTime:lastTime,withinTolerance,toleranceSeconds:layer?.staleness_tolerance_seconds??null,
   evidenceClass:[...new Set(readings.filter(r=>r.valueReadable).map(r=>r.cls).filter(Boolean))],layer,
   raw:{layer,pointFields:fields,pointSelection:point?.selection,pointNotices:point?.notices||[],features:featureRequest||null,lastAdvertisedFeatures:lastRequest||null}};
 });
 return {focus,validTime,capturedAt:bundle.capturedAt,layers,point,pointRequest,timeline,records,requests:bundle.requests,
  dataMode:point?.data_mode||'unavailable',notices:point?.notices||[],captureMissing:!pointRequest,operational:false};
}
export async function readLive(focus,validTime) {
 const requests={};
 async function read(route) {
  const requestedAt=new Date().toISOString();
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(new Error('Request timed out after 20 seconds')),20000);
  let status=0,headers={};
  try {
   const response=await fetch(API+route,{cache:'no-store',signal:controller.signal});
   status=response.status;
   headers=Object.fromEntries(response.headers.entries());
   const responseText=await response.text();
   let body;
   try {body=JSON.parse(responseText);}
   catch {body={data_mode:'unavailable',detail:'Response was not JSON',responseText};}
   requests[route]={route,url:API+route,requestedAt,capturedAt:new Date().toISOString(),status,headers,body};
  } catch(error) {requests[route]={route,url:API+route,requestedAt,capturedAt:new Date().toISOString(),status,headers,body:{data_mode:'unavailable',detail:String(error)}};}
  finally {clearTimeout(timeout);}
 }
 await Promise.all([read('/layers'),read('/timeline'),read(routeForPoint(focus,validTime)),...SPECS.map(s=>read(routeForFeatures(s.id,validTime)))]);
 return {prototype:true,capturedAt:new Date().toISOString(),apiOrigin:API,focuses:[focus],times:[validTime],requests};
}
