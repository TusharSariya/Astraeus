import { DiscoveryBrowser, type DiscoveryActions } from './DiscoveryBrowser'
import { SourceTag } from './SourceTag'
import { mapLayerEvidence } from './MapEvidenceDetails'
import { layerMapping, layerImagery } from './layerIdentity'
import { useRef, useState } from 'react'
import type { CatalogSource, LayerItem, LayerSelection, GeoJsonFeature, ResolvedEvidenceClass } from '../types'
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
  id: string; drawn: boolean; description: string; times: string[]
  status?: 'loading' | 'refreshing' | 'drawn' | 'unavailable' | 'hidden' | 'empty'
  selection?: { latitude: number; longitude: number; instant: number }
  evidenceClass?: ResolvedEvidenceClass
  images?: Array<{ frame: string; weight: number; request: unknown; provenance: unknown }>
  display?: { kind: string; selectedMethod: string; usedMethod: string | null; shader: string | null; inputFrames: string[]; responseHeaders: Record<string, string | null> | null; options: unknown; captureIdentity: string | null; methodVersion: string | null }
  features?: GeoJsonFeature[]
}
const STORAGE_KEY = 'astraeus-saved-map-stacks'
function readSaved(): Record<string, LayerSelection[]> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const result: Record<string, LayerSelection[]> = {}
    for (const [name, entries] of Object.entries(parsed).slice(0, 12)) {
      if (name.length > 60 || !Array.isArray(entries) || entries.length > 32) continue
      if (entries.every((entry) => entry && typeof entry.id === 'string' && /^[\w.:-]{1,160}$/.test(entry.id) && typeof entry.visible === 'boolean' && typeof entry.opacity === 'number' && entry.opacity >= 0 && entry.opacity <= 1) && new Set(entries.map((entry) => entry.id)).size === entries.length) result[name] = entries
    }
    return result
  } catch { return {} }
}
export function MapStack({ layers, stack, onChange, drawn, onInspect, loading = false, error = null, notices = [], catalog = [], catalogError, onPoint, onSeries, onSource }: DiscoveryActions & {
  catalog?: CatalogSource[]; catalogError?: string | null
  layers: LayerItem[]; stack: LayerSelection[]; onChange: (stack: LayerSelection[]) => void; drawn: DrawEvidence[]
  onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void; loading?: boolean; error?: string | null; notices?: string[]
}) {
  const replacementFocus = useRef<string | null>(null)
  const [saved, setSaved] = useState(readSaved)
  const [name, setName] = useState(''); const [notice, setNotice] = useState('')
  const [tab, setTab] = useState<'Active' | 'Browse'>('Active')
  const patch = (id: string, values: Partial<LayerSelection>) => onChange(stack.map(entry => entry.id === id ? { ...entry, ...values } : entry))
  const move = (index: number, delta: number) => { const next = [...stack]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; onChange(next) }
  return <section className="bench-stack" aria-label="Ordered Map stack">
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
      <DiscoveryBrowser catalog={catalog} layers={layers} stack={stack} error={catalogError} onPoint={onPoint} onSeries={onSeries} onSource={onSource} onAdd={id => { if (!stack.some(s => s.id === id)) onChange([...stack, { id, visible: true, opacity: .85 }]) }} />
    </div>
    <div hidden={tab !== 'Active'}>
      <p className="bench-order-label">Drawing order · top first</p>
      {stack.length === 0 && <p>Basemap only. No meteorological layer is requested.</p>}
      <ol reversed>{[...stack].reverse().map((entry, topIndex) => {
        const index = stack.length - topIndex - 1
        const layer = layers.find(candidate => candidate.id === entry.id); const actual = drawn.find(row => row.id === entry.id)
        const title = layer?.title ?? entry.id
        const update = DELIVERY_UPDATES[entry.id]
        const replacement = !loading && !error && update ? layers.find(candidate => candidate.id === update.id) : undefined
        const alreadySelected = replacement && stack.some(row => row.id === replacement.id)
        const catalogueState = loading ? 'Checking layer catalogue' : error ? 'Catalogue request failed · availability unknown' : layer ? 'Listed in current catalogue' : 'Not in current catalogue · imagery not requested'
        const state = !entry.visible ? 'Hidden' : entry.opacity <= 0 ? 'Opacity zero' : actual?.status === 'refreshing' ? `Refreshing · showing frame ${actual.times.join(', ') || 'time unknown'}` : actual?.drawn ? `Frame ${actual.times.join(', ') || 'time unknown'}` : !layer ? catalogueState : actual?.status === 'loading' ? 'Loading frame' : actual?.status === 'empty' ? 'No features returned' : 'Unavailable · no frame drawn'
        const diagnosis = !layer ? `${catalogueState}.${error ? ` ${error}` : ''}` : actual?.description ?? 'No current draw receipt for this layer.'
        const sources = layer ? [...new Set(layerMapping(layer).fields.map(row => row.source_id))] : []
        return <li key={entry.id}>
          <div className="bench-layer-title"><EvidenceGlyph kind={actual?.evidenceClass ?? resolveEvidenceClass(layer?.evidence_class)} /><strong title={title}>{actual?.evidenceClass === 'generated_display' && 'GENERATED · '}{title}</strong></div>
          <small>{sources.length ? sources.map(id => <SourceTag key={id} id={id} />) : layer?.product ?? 'Source unknown'} · {actual?.evidenceClass ?? resolveEvidenceClass(layer?.evidence_class)}</small>
          <small className="bench-layer-state">{state} · {layer?.run_stale === true ? 'Stale run' : layer?.run_stale === false ? 'Run current' : 'Age unknown'}</small>
          {update && <div className="bench-layer-repair"><p>{update.reason}</p>{replacement && !alreadySelected && <button onClick={() => { replacementFocus.current = replacement.id; patch(entry.id, { id: replacement.id }); setNotice(`Selected ${replacement.title}. Its returned evidence basis applies. Save the stack again to retain this change in browser storage.`) }}>Use {replacement.title}</button>}{alreadySelected && <small>Current delivery is already in this stack. Remove the older selection when ready.</small>}</div>}
          <div className="bench-stack-row-actions"><label title={title}><input ref={node => { if (node && replacementFocus.current === entry.id) { node.focus(); replacementFocus.current = null } }} type="checkbox" aria-label={`Show ${title}`} checked={entry.visible} onChange={event => patch(entry.id, { visible: event.target.checked })} />Visible</label><button aria-label={`Remove ${title}`} onClick={() => onChange(stack.filter(row => row.id !== entry.id))}>Remove</button></div>
          <details><summary>Adjust layer · run details</summary>
            <p>{title}</p><p>{diagnosis}</p>
            <p>Actual frame: {actual?.times.join(', ') || 'None drawn'}. Drawn frame run: {actual?.times.length ? actual.times.map(time => layer?.frames?.find(frame => Date.parse(frame.valid_time) === Date.parse(time))?.run_time ?? 'not supplied').join(', ') : 'not supplied'}. Index newest run: {layer?.run_time ?? 'not supplied'}</p>
            <p>{layer ? layerImagery(layer).reason : 'No imagery request was made for this absent layer.'}</p>
            {notices.length > 0 && <details><summary>Catalogue notices · all sources</summary><ul>{notices.map((value, index) => <li key={index}>{value}</li>)}</ul></details>}
            <div className="bench-stack-row-actions">
              <label>Opacity<input aria-label={`Stack opacity ${title}`} type="range" min={0} max={1} step={.05} value={entry.opacity} onChange={event => patch(entry.id, { opacity: Number(event.target.value) })} /></label>
              <button aria-label={`Raise ${title}`} disabled={index === stack.length - 1} onClick={() => move(index, 1)}>↑</button><button aria-label={`Lower ${title}`} disabled={index === 0} onClick={() => move(index, -1)}>↓</button>
              <button aria-label={`Inspect layer ${title}`} onClick={event => onInspect({ ...mapLayerEvidence(entry.id, layer, actual), text: diagnosis, details: { ...mapLayerEvidence(entry.id, layer, actual).details, 'Catalogue status': catalogueState, 'Catalogue error': error, 'Catalogue notices': notices, 'Delivery update': update ?? null } }, event.currentTarget)}>Inspect</button>
            </div>
          </details>
        </li>
      })}</ol>
    </div>
  </section>
}
export function MapLegends({ layers, stack }: { layers: LayerItem[]; stack: LayerSelection[] }) {
  const activeLayers = stack.filter(entry => entry.visible).flatMap(entry => { const layer = layers.find(candidate => candidate.id === entry.id); return layer ? [layer] : [] })
  return <section className="bench-family-legends"><h3>Active family scales</h3>
    {!activeLayers.length && <p>No active provider scales.</p>}
    {groupByFamily(activeLayers, layerFamily).map(group => <section key={group.family}><ActiveFamilyLegends layers={group.members} />{group.members.filter(layer => layer.raster_available === true).map(layer => <FamilyScale key={layer.id} layer={layer} />)}</section>)}
  </section>
}
function FamilyScale({ layer }: { layer: LayerItem }) {
  const [failed, setFailed] = useState(false)
  if (!layer.legend_available || failed) return <p>{layer.title} · {failed ? 'Legend could not be retrieved' : 'No provider legend declared'}; no scale is invented.</p>
  return <figure><img src={layerLegendUrl(layer)} alt={`Legend for ${layer.title}`} onError={() => setFailed(true)} /><figcaption>{layer.title} · {layerGroup(layer) === 'rendered_grid' ? 'Exact rendering colormap' : 'Provider legend'}</figcaption></figure>
}
