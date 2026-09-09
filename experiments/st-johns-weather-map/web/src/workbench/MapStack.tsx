import { TemperatureSourceControl, precipitationScale, PrecipitationLegend } from './precipitationColours'
import { IFSLayers } from "./IFSLayers"
import { mapOnlyLayer, capabilityFor, cycleSelection, parseSelection, pointLabel, selectionPoints, selectionState } from './pointSelections'
import { PointChoices } from './PointChoices'
import { DiscoveryBrowser, SourceActions, type DiscoveryActions } from './DiscoveryBrowser'
import { LayerRow } from './LayerRow'
import { discoveryRows, type DiscoveryRow } from './discovery'
import { mapLayerEvidence } from './MapEvidenceDetails'
import { layerImagery } from './layerIdentity'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CatalogSource, LayerItem, LayerSelection, GeoJsonFeature, ResolvedEvidenceClass, PointFieldSelection } from '../types'
import { layerFamily, layerGroup, layerLegendUrl } from '../api'
import { ActiveFamilyLegends } from '../MapFamilyLegend'
import { groupByFamily } from '../fieldFamily'
import { resolveEvidenceClass } from '../evidenceClass'
import { EvidenceGlyph, type InspectedEvidence } from './EvidenceInspector'

// Five #46 roles, using current delivery paths. Linked/saved identities remain explicit.
export const NOWCAST_STACK: LayerSelection[] = ['geomet-live-goes-east-naturalcolor', 'geomet-live-hrdps-nt', 'eccc-cap-alerts-current', 'eccc-radar-radar', 'eccc-lightning-lightning'].map((id) => ({ id, opacity: 0.85, visible: true }))
// Explicit delivery transitions, not provider or scientific-field inference.
const DELIVERY_UPDATES: Record<string, { id: string; reason: string }> = {
  'eccc-hrdps-surface-total-cloud': {
    id: 'geomet-live-hrdps-nt',
    reason: 'Stored HRDPS cloud delivery was retired. The current cloud image is a GeoMet live proxy; it has different provenance and does not restore archived imagery.',
  },
  'eccc-cap-alerts-alerts_features': {
    id: 'eccc-cap-alerts-current',
    reason: 'This stack selects the older stored CAP layer. Current CAP alerts use selected-time demand features; historical availability is not implied.',
  },
}
export interface DrawEvidence {
  id: string; title?: string; sourceId?: string; drawn: boolean; description: string; times: string[]
  status?: 'loading' | 'refreshing' | 'drawn' | 'unavailable' | 'hidden' | 'empty'
  selection?: { latitude: number; longitude: number; instant: number }
  evidenceClass?: ResolvedEvidenceClass
  images?: Array<{ frame: string; weight: number; request: unknown; provenance: unknown }>
  display?: { kind: string; selectedMethod: string; usedMethod: string | null; shader: string | null; inputFrames: string[]; responseHeaders: Record<string, string | null> | null; options: unknown; captureIdentity: string | null; methodVersion: string | null }
  nativeGrid?: import("./sourceGrid").SourceGrid
  precipitation?: Array<ReturnType<typeof import('./precipitationColours').featurePrecipitation>>
  features?: GeoJsonFeature[]
}
interface DetailsSelection {
  identity: { kind: 'layer'; id: string } | { kind: 'source'; id: string }
  row?: DiscoveryRow
  opener: HTMLButtonElement
  scroll: number
}
const STORAGE_KEY = 'astraeus-saved-map-stacks'
function readSaved(): Record<string, LayerSelection[]> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const result: Record<string, LayerSelection[]> = {}
    for (const [name, entries] of Object.entries(parsed).slice(0, 12)) {
      if (name.length > 60 || !Array.isArray(entries) || entries.length > 32) continue
      try {
        const valid = entries.map(parseSelection)
        if (new Set(valid.map(entry => entry.id)).size === valid.length) result[name] = valid
      } catch { /* Invalid saved stack is not partially restored. */ }
    }
    return result
  } catch { return {} }
}
export function MapStack({ layers, stack, onChange, drawn, onInspect, loading = false, error = null, notices = [], catalog = [], catalogError, onPoint, onSeries, onSource, onOpenPointData }: DiscoveryActions & {
  onOpenPointData?: (id: string) => void
  catalog?: CatalogSource[]; catalogError?: string | null
  layers: LayerItem[]; stack: LayerSelection[]; onChange: (stack: LayerSelection[]) => void; drawn: DrawEvidence[]
  onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void; loading?: boolean; error?: string | null; notices?: string[]
}) {
  const discovery = useMemo(() => discoveryRows(catalog, layers), [catalog, layers])
  const [details, setDetails] = useState<DetailsSelection | null>(null)
  const root = useRef<HTMLElement>(null)
  const heading = useRef<HTMLHeadingElement>(null), listHeading = useRef<HTMLParagraphElement>(null)
  const primaryButtons = useRef(new Map<string, HTMLButtonElement>())
  const pendingFocus = useRef<string | 'heading' | null>(null)
  useLayoutEffect(() => {
    if (pendingFocus.current) {
      (primaryButtons.current.get(pendingFocus.current) ?? listHeading.current)?.focus()
      pendingFocus.current = null
    }
  }, [stack])
  useLayoutEffect(() => { if (details) heading.current?.focus() }, [details?.identity.id])
  const openDetails = (id: string, opener: HTMLButtonElement, row?: DiscoveryRow) => {
    const overlay = opener.closest('.bench-overlay')
    setDetails({ identity: row && !row.layerId && !row.point ? { kind: 'source', id } : { kind: 'layer', id }, row, opener, scroll: overlay?.scrollTop ?? 0 })
    if (overlay) overlay.scrollTop = 0
  }
  const closeDetails = () => {
    const back = details; setDetails(null)
    requestAnimationFrame(() => {
      if (!back) return
      const overlay = back.opener.closest('.bench-overlay')
      if (overlay) overlay.scrollTop = back.scroll
      if (back.opener.isConnected) back.opener.focus({ preventScroll: true })
      else if (tab === 'Browse') root.current?.querySelector<HTMLInputElement>('.discovery-search input[type="search"]')?.focus()
      else listHeading.current?.focus()
    })
  }
  const remove = (id: string) => {
    const order = [...stack].reverse(), index = order.findIndex(row => row.id === id)
    pendingFocus.current = order[index + 1]?.id ?? order[index - 1]?.id ?? 'heading'
    onChange(stack.filter(row => row.id !== id))
  }
  const toggle = (id: string, point?: PointFieldSelection) => {
    if(point?.sourceId==='ecmwf-ifs' && !stack.some(s=>s.id===id) && capabilityFor(point,catalog)?.grid){
      const fields:Record<string,string>={temperature_2m:'2t',dew_point_2m:'2d',mean_sea_level_pressure:'msl',total_cloud_geometric:'tcc',wind_u_10m:'10u',wind_v_10m:'10v',wind_gust_10m:'10fg',precipitation_accumulation:'tp'}
      const parameter=fields[point.field]
      if(parameter){onChange([...stack,{id,visible:true,opacity:.7,points:[point],ifs:{product:'atmosphere-control',field:`${parameter}:sfc`,level:0,run:'latest',member:'0',statistic:'',rendering:parameter==='tcc'?'cloud':'scalar',title:pointLabel(point)}}]);return}
    }
    const next = cycleSelection(stack, id, point, selectionPoints({ id, visible: true, opacity: .85 }, layers, catalog), !!point && capabilityFor(point,catalog)?.grid === true, mapOnlyLayer(layers.find(layer => layer.id === id),catalog))
    if (tab === 'Active' && !next.some(row => row.id === id)) remove(id)
    else onChange(next)
  }
  const replacementFocus = useRef<string | null>(null)
  const [saved, setSaved] = useState(readSaved)
  const [name, setName] = useState(''); const [notice, setNotice] = useState('')
  const [tab, setTab] = useState<'Active' | 'Browse'>('Active')
  const patch = (id: string, values: Partial<LayerSelection>) => onChange(stack.map(entry => entry.id === id ? { ...entry, ...values } : entry))
  const move = (index: number, delta: number) => { const next = [...stack]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; onChange(next); if (index + delta === 0 || index + delta === stack.length - 1) heading.current?.focus() }
  return <section ref={root} className="bench-stack" aria-label="Ordered Map stack" onKeyDown={event => {
    if (details && event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); event.stopPropagation(); closeDetails() }
  }}>
    <div hidden={!!details}>
    <div className="bench-stack-tabs" role="group" aria-label="Layer lists">{(['Active', 'Browse'] as const).map(value => <button key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{value}{value === 'Active' ? ` · ${stack.length}` : ''}</button>)}</div>
    <details className="bench-stacks-menu"><summary>Stacks</summary><div className="bench-stack-actions">
      <button onClick={() => onChange(NOWCAST_STACK.map(entry => ({ ...entry })))}>Nowcast</button>
      <label>Saved stacks<select value="" onChange={event => { if (Object.hasOwn(saved, event.target.value)) onChange(saved[event.target.value].map(entry => ({ ...entry }))) }}><option value="">Load stack…</option>{Object.keys(saved).map(key => <option key={key}>{key}</option>)}</select></label>
      <form onSubmit={event => { event.preventDefault(); const key = name.trim(); if (!key || key.length > 60) return; if (Object.keys(saved).length >= 12 && !Object.hasOwn(saved, key)) { setNotice('Twelve Saved stacks maximum.'); return }; const next = { ...saved, [key]: stack }; try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); setSaved(next); setNotice(`Saved ${key}`) } catch { setNotice('Browser storage unavailable; stack was not saved.') } }}>
        <label>Stack name<input maxLength={60} value={name} onChange={event => setName(event.target.value)} /></label><button>Save stack</button>
      </form>
    </div></details>
    {notice && <p role="status">{notice}</p>}
    {loading && <p role="status">Loading available layers…</p>}{error && <p role="status">Layers unavailable: {error}</p>}
    <div hidden={tab !== 'Browse'}>
      <IFSLayers stack={stack} onChange={onChange} />
      <DiscoveryBrowser drawn={drawn} catalog={catalog} layers={layers} stack={stack} error={catalogError} onToggle={toggle} onDetails={(row, opener) => openDetails(row.layerId ?? row.id, opener, row)} />
    </div>
    <div hidden={tab !== 'Active'}>
      <p ref={listHeading} tabIndex={-1} className="bench-order-label">Drawing order · top first</p>
      {stack.length === 0 && <p>Basemap only. No meteorological layer is requested.</p>}
      <ol reversed className="dense-layer-list">{[...stack].reverse().map(entry => {
        const layer = layers.find(candidate => candidate.id === entry.id), actual = drawn.find(row => row.id === entry.id)
        const title = entry?.ifs?.title ?? layer?.title ?? discovery.find(row => (row.layerId ?? row.id) === entry.id)?.title ?? (entry.points?.[0] ? pointLabel(entry.points[0]) : entry.id)
        const state = entry.ifs ? (entry.visible ? 'Native IFS · see map legend' : 'Hidden') : !entry.visible ? mapOnlyLayer(layer,catalog) ? 'Hidden' : 'Data only' : entry.opacity <= 0 ? 'Opacity zero' : !layer && entry.points?.[0] && !entry.pointOnly ? actual?.status === 'loading' ? 'Loading frame' : actual?.drawn ? 'Drawn' : 'Unavailable · no frame drawn' : loading && !layer ? 'Checking layer catalogue' : error && !layer ? 'Catalogue request failed · availability unknown' : !layer ? 'Not in current catalogue · imagery not requested' : actual?.status === 'loading' ? 'Loading frame' : actual?.status === 'refreshing' ? 'Refreshing' : actual?.status === 'empty' ? 'No features returned' : actual?.drawn ? actual.evidenceClass === 'generated_display' ? 'Generated' : layer.run_stale ? 'Stale' : 'Drawn' : 'Unavailable · no frame drawn'
        const precipitation = entry.ifs?.field==='tp:sfc' || layer?.field==='radar' || selectionPoints(entry,layers,catalog).some(p=>['precipitation_rate','snow_rate','precipitation_accumulation'].includes(p.field))
        return <li className={precipitation?'precipitation-layer-row':undefined} key={entry.id}><LayerRow title={title} status={state} selected state={selectionState(entry, mapOnlyLayer(layer,catalog))} onPrimary={() => toggle(entry.id)}
          primaryRef={node => { if (node) primaryButtons.current.set(entry.id, node); else primaryButtons.current.delete(entry.id) }}
          onDetails={opener => openDetails(entry.id, opener)} visibility={<button className="dense-remove" aria-label={`Remove ${title}`} title={`Remove ${title}`}
            ref={node => { if (node && replacementFocus.current === entry.id) { node.focus(); replacementFocus.current = null } }}
            onClick={() => remove(entry.id)}>×</button>} />{precipitation && <TemperatureSourceControl value={entry.temperatureSource} onChange={temperatureSource=>patch(entry.id,{temperatureSource})} catalog={catalog} providerImage={layer?.raster_available===true && layerGroup(layer)!=='rendered_grid'}/>}</li>
      })}</ol>
    </div>
    </div>
    {details && (() => {
      const id = details.identity.id, isLayer = details.identity.kind === 'layer'
      const layer = isLayer ? layers.find(candidate => candidate.id === id) : undefined
      const actual = isLayer ? drawn.find(row => row.id === id) : undefined
      const entry = isLayer ? stack.find(row => row.id === id) : undefined, index = stack.findIndex(row => row.id === id)
      const row = discovery.find(row => isLayer ? (row.layerId ?? row.id) === id : row.id === id) ?? details.row
      const title = entry?.ifs?.title ?? layer?.title ?? row?.title ?? (entry?.points?.[0] ? pointLabel(entry.points[0]) : id)
      const selectedPoints = entry ? selectionPoints(entry, layers, catalog) : row?.point ? [row.point] : selectionPoints({id, visible:true, opacity:.85}, layers, catalog)
      const source = row?.source
      const update = isLayer ? DELIVERY_UPDATES[id] : undefined
      const replacement = !loading && !error && update ? layers.find(candidate => candidate.id === update.id) : undefined
      const alreadySelected = replacement && stack.some(row => row.id === replacement.id)
      const catalogueState = loading ? 'Checking layer catalogue' : error ? 'Catalogue request failed · availability unknown' : layer ? 'Listed in current catalogue' : 'Not in current catalogue · imagery not requested'
      const diagnosis = !layer ? `${catalogueState}.${error ? ` ${error}` : ''}` : actual?.description ?? 'No current draw receipt for this layer.'
      return <section className="layer-details" aria-label="Layer or source details">
        <div className="bench-view-heading"><h3 ref={heading} tabIndex={-1}>{title}</h3><button onClick={closeDetails}>Back to {tab}</button></div>
          {(entry?.ifs?.field==='tp:sfc' || selectedPoints.some(p=>['precipitation_rate','snow_rate','precipitation_accumulation'].includes(p.field)) || layer?.field==='radar') && <p>Temperature-based colours · Temperature source: Same source → HRDPS (automatic, loaded data only). Imagery-only layers retain provider style. Temperature unavailable where matching data is absent.</p>}
        {((isLayer && !entry?.pointOnly && !row?.point) || (row?.point && capabilityFor(row.point,catalog)?.grid)) && <>
          <p>{id}</p><p><EvidenceGlyph kind={actual?.evidenceClass ?? resolveEvidenceClass(layer?.evidence_class)} /> {actual?.evidenceClass ?? resolveEvidenceClass(layer?.evidence_class)} · {source?.product ?? layer?.product ?? 'Source unknown'}</p>
          <p>{layer?.semantics ?? 'No current layer metadata returned.'}</p><p>{diagnosis}</p>
          <p>Actual frame: {actual?.times.join(', ') || 'None drawn'}. Drawn frame run: {actual?.times.length ? actual.times.map(time => layer?.frames?.find(frame => Date.parse(frame.valid_time) === Date.parse(time))?.run_time ?? 'not supplied').join(', ') : 'not supplied'}. Index newest run: {layer?.run_time ?? 'not supplied'}</p>
          <p>Run state: {layer?.run_stale === true ? 'Stale' : layer?.run_stale === false ? 'Current' : 'Unknown'}. Imagery checked: {layer ? layerImagery(layer).checked_at ?? 'not supplied' : 'not supplied'}.</p>
          <p>{layer ? layerImagery(layer).reason : 'No imagery request was made for this absent layer.'}</p>
          {notices.length > 0 && <details><summary>Catalogue notices · all sources</summary><ul>{notices.map((value, index) => <li key={index}>{value}</li>)}</ul></details>}
          {update && <div className="bench-layer-repair"><p>{update.reason}</p>{entry && replacement && !alreadySelected && <button onClick={() => { replacementFocus.current = replacement.id; patch(id, { id: replacement.id }); setDetails(null); setNotice(`Selected ${replacement.title}. Its returned evidence basis applies. Save the stack again to retain this change in browser storage.`) }}>Use {replacement.title}</button>}{alreadySelected && <small>Current delivery is already in this stack. Remove the older selection when ready.</small>}</div>}
          {entry ? <div className="bench-stack-row-actions">
            <button onClick={() => patch(id, { visible: !entry.visible })} aria-label={`Selection state for ${title}`} title="Change map and data state">{selectionState(entry, mapOnlyLayer(layer,catalog))}</button>
            <label>Opacity<input aria-label={`Stack opacity ${title}`} type="range" min={0} max={1} step={.05} value={entry.opacity} onChange={event => patch(id, { opacity: Number(event.target.value) })} /></label>
            <button aria-label={`Raise ${title}`} disabled={index === stack.length - 1} onClick={() => move(index, 1)}>↑</button><button aria-label={`Lower ${title}`} disabled={index === 0} onClick={() => move(index, -1)}>↓</button>
          </div> : <button onClick={() => toggle(id)}>Add {title}</button>}
          <button aria-label={`Inspect layer ${title}`} onClick={event => onInspect({ ...mapLayerEvidence(id, layer, actual), text: diagnosis, details: { ...mapLayerEvidence(id, layer, actual).details, 'Catalogue status': catalogueState, 'Catalogue error': error, 'Catalogue notices': notices, 'Delivery update': update ?? null } }, event.currentTarget)}>Provenance</button>
        </>}
        {(isLayer || row?.point) && <>
          {selectedPoints.map(point => <PointChoices key={JSON.stringify([point.sourceId,point.product,point.field])} point={point} catalog={catalog} onChange={updated => {
            const points = selectedPoints.map(p => p === point ? updated : p)
            if (entry) patch(id, {points})
            else onChange([...stack, {id, opacity:.85, visible: !row?.point, ...(row?.point ? {pointOnly:true} : {}), points}])
          }} />)}
          {onOpenPointData && selectedPoints.length > 0 && <button onClick={() => {
            if (!entry) onChange([...stack, {id, opacity:.85, visible: !row?.point, ...(row?.point ? {pointOnly:true} : {}), ...(selectedPoints.length ? {points:selectedPoints} : {})}])
            onOpenPointData(id)
          }}>Open point data</button>}
          {entry && <button onClick={() => { remove(id); setDetails(null) }}>Remove {title}</button>}
        </>}
        <SourceActions source={source} onPoint={onOpenPointData ? undefined : onPoint} onSeries={onSeries} onSource={onSource} />
      </section>
    })()}

  </section>
}
export function MapLegends({ layers, stack, drawn = [] }: { layers: LayerItem[]; stack: LayerSelection[]; drawn?: DrawEvidence[] }) {
  const activeLayers = stack.filter(entry => entry.visible).flatMap(entry => { const layer = layers.find(candidate => candidate.id === entry.id); return layer ? [layer] : [] })
  return <section className="bench-family-legends"><h3>Active family scales</h3>
    {drawn.filter(row=>row.drawn).map(row=>{
      const scales=[...new Map((row.precipitation??[]).flatMap(reading=>reading?[[`${reading.field}:${reading.scale.units}`,reading.scale] as const]:[])).values()]
      return scales.length?<section key={row.id}><h4>{layers.find(layer=>layer.id===row.id)?.title??row.id} · numeric samples</h4>{scales.map(scale=><PrecipitationLegend key={`${scale.label}:${scale.units}`} scale={scale}/>)}</section>:null
    })}
    {!activeLayers.length && <p>No active provider scales.</p>}
    {groupByFamily(activeLayers, layerFamily).map(group => <section key={group.family}><ActiveFamilyLegends layers={group.members} />{group.members.filter(layer => layer.raster_available === true).map(layer => <FamilyScale key={layer.id} layer={layer} />)}</section>)}
  </section>
}
function FamilyScale({ layer }: { layer: LayerItem }) {
  const [failed, setFailed] = useState(false)
  const scale=precipitationScale(layer.field,layer.units)
  if(layer.raster_available!==true && scale)return <PrecipitationLegend scale={scale}/>
  if (!layer.legend_available || failed) return <p>{layer.title} · {failed ? 'Legend could not be retrieved' : 'No provider legend declared'}; no scale is invented.</p>
  return <figure><img src={layerLegendUrl(layer)} alt={`Legend for ${layer.title}`} onError={() => setFailed(true)} /><figcaption>{layer.title} · {layerGroup(layer) === 'rendered_grid' ? 'Exact rendering colormap' : 'Provider legend'}</figcaption></figure>
}
