// Experiment only. Four independently read endpoints; never an atomic revision.
// Verified model selector aliases: api/weather_api/app.py PRODUCT_SOURCE_IDS.
const PRODUCT_SOURCE_IDS = Object.freeze({HRDPS:'eccc-hrdps',RDPS:'eccc-rdps',REPS:'eccc-reps',GFS:'noaa-gfs',NOAA:'noaa-gfs',IFS:'ecmwf-ifs',ECMWF:'ecmwf-ifs',ICON:'dwd-icon-global',DWD:'dwd-icon-global'});
// Exact producer labels paired with source_id in the checked-in adapters.
const ADAPTER_PRODUCT_SOURCE_IDS = Object.freeze({
  'Global Forecast System (GFS 0.25 deg)':'noaa-gfs', // ingest/adapters/noaa_s3.py
  'CYYT METAR/SPECI':'awc-metar-speci', // ingest/adapters/awc.py
  'CYYT TAF (Terminal Aerodrome Forecast)':'awc-taf',
  'Canadian radar composite precipitation rate via GeoMet WMS':'eccc-radar', // ingest/adapters/eccc_geomet.py
  'Lightning flash density 2.5 km via GeoMet WMS':'eccc-lightning',
  'MSC current public alerts (CAP) via GeoMet WMS':'eccc-cap-alerts',
  'Air Quality Health Index observations via GeoMet WMS':'eccc-aqhi',
  'HRDPS Continental 2.5 km via GeoMet WMS':'eccc-hrdps',
  'RDPS 10 km via GeoMet WMS':'eccc-rdps'
});
const array = value => Array.isArray(value) ? value : [];
const stamp = value => value == null ? NaN : Date.parse(value);
const sameInstant = (a,b) => Number.isFinite(stamp(a)) && stamp(a) === stamp(b);

export function normalize(bundle, instant) {
  const requests = bundle?.requests || {};
  const endpoints = Object.fromEntries(['catalog','status','timeline','layers'].map(name => {
    const request = requests[name] || {};
    const ok = Number.isInteger(request.status) && request.status >= 200 && request.status < 300 && request.response && typeof request.response === 'object';
    return [name, {...request, ok: Boolean(ok), error: request.error || (!ok ? (request.status ? `HTTP ${request.status}` : 'Endpoint not read') : null)}];
  }));
  const body = name => endpoints[name].ok ? endpoints[name].response : {};
  const catalog = body('catalog');
  const sources = array(catalog.sources);
  const statuses = array(body('status').statuses);
  const timeline = array(body('timeline').items);
  const focusItem = timeline.find(item => sameInstant(item.valid_time_utc, instant)) || null;
  const layers = array(body('layers').layers);
  const ids = new Set(sources.map(source => source.id));
  // Exact catalogue product names may join only when unique. Never fuzzy-match IDs.
  function productMatch(product) {
    if (typeof product !== 'string') return null;
    if (ids.has(product)) return {sourceId:product,basis:'Exact catalogue source ID (artifact product fallback)'};
    const exact = sources.filter(source => source.product === product);
    if (exact.length === 1) return {sourceId:exact[0].id,basis:'Exact unique catalogue product'};
    const adapterId = ADAPTER_PRODUCT_SOURCE_IDS[product];
    if (adapterId && ids.has(adapterId)) return {sourceId:adapterId,basis:'Exact product/source_id pair in checked-in adapter'};
    const id = PRODUCT_SOURCE_IDS[product.toUpperCase()];
    return id && ids.has(id) ? {sourceId:id,basis:'Explicit backend PRODUCT_SOURCE_IDS alias'} : null;
  }
  const joinedLayers = layers.map(layer => ({layer, match:productMatch(layer.product)}));
  const fieldFamilyValues = array(catalog.field_families).map(family => typeof family === 'string' ? family : family.id || family.key || family.family).filter(Boolean);
  const families = [...new Set(fieldFamilyValues.length ? fieldFamilyValues : sources.flatMap(source => array(source.fields).map(field => field.family).filter(Boolean)))].sort();
  const notices = Object.entries(endpoints).flatMap(([endpoint,value]) => array(value.ok ? value.response.notices : []).map(text => ({endpoint,text})));
  const records = sources.map(source => {
    const status = statuses.find(item => item.source_id === source.id) || null;
    const matches = joinedLayers.filter(item => item.match?.sourceId === source.id);
    const sourceLayers = matches.map(item => item.layer);
    const coverage = array(focusItem?.coverage).filter(item => item.source_id === source.id);
    const availableProducts = array(focusItem?.available_products).filter(product => productMatch(product)?.sourceId === source.id);
    const agedAtFocus = focusItem?.aged_out_sources?.[source.id] ?? null;
    const agedAtLayers = body('layers').aged_out_sources?.[source.id] ?? null;
    const agedOut = Boolean(agedAtFocus || agedAtLayers);
    const fields = array(source.fields);
    const evidenceClasses = array(source.evidence_classes).length ? source.evidence_classes : source.evidence_class ? [source.evidence_class] : [];
    const missingMetadata = [];
    if (!evidenceClasses.length) missingMetadata.push('Evidence class is not supplied by these endpoints');
    if (!status) missingMetadata.push(endpoints.status.ok ? 'No source-status record returned' : 'Source-status endpoint unavailable');
    if (!fields.length) missingMetadata.push('No field-family mappings returned; capabilities are not inferred');
    missingMetadata.push('Location coverage is not established by these four endpoints');
    const temporalState = !endpoints.timeline.ok ? 'unavailable' : !focusItem ? 'unsampled' : coverage.length ? 'retained-run-coverage' : availableProducts.length ? 'product-listed' : agedAtFocus ? 'aged-out' : focusItem.coverage_notice ? 'no-retained-coverage' : 'unknown';
    const runAssessments = [
      ...coverage.map(value => ({endpoint:'timeline',...value})),
      ...sourceLayers.map(layer => ({endpoint:'layers',layer_id:layer.id,run_time:layer.run_time ?? null,run_stale:layer.run_stale ?? null,run_stale_reason:layer.run_stale_reason ?? null,runs:array(layer.runs)}))
    ];
    const layerAtFocus = sourceLayers.map(layer => {
      const exact = array(layer.times).filter(time => sameInstant(time,instant));
      return {layer_id:layer.id,exactTimes:exact,state:exact.length ? 'exact-frame' : array(layer.times).length ? 'no-exact-frame' : 'no-times-declared',evidence_basis:layer.evidence_basis,staleness_tolerance_seconds:layer.staleness_tolerance_seconds};
    });
    return {id:source.id,source,status,layers:sourceLayers,coverage,agedOut,lastValidTime:agedAtFocus || agedAtLayers,agedAtFocus,agedAtLayers,families:[...new Set(fields.map(field => field.family).filter(Boolean))],fields,evidenceClasses,missingMetadata,productMatches:matches.map(({layer,match}) => ({layer_id:layer.id,product:layer.product,...match})),availableProducts,temporalState,runAssessments,layerAtFocus,raw:{catalog:source,status,timeline:focusItem,layers:sourceLayers}};
  });
  return {records,families,familyBasis:fieldFamilyValues.length ? 'catalog.field_families' : 'catalog.sources[].fields[].family (field_families not supplied)',timeline,focusItem,endpoints,notices,unmatchedLayers:joinedLayers.filter(item => !item.match).map(item => item.layer),unmatchedProducts:array(focusItem?.available_products).filter(product => !productMatch(product)),capturedAt:bundle?.captured_at ?? null};
}
