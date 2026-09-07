import { useState } from 'react'
import type { LayerItem, LayerSelection } from '../types'
import { layerFamily } from '../api'
import { familyTitle } from '../fieldFamily'
import { resolveEvidenceClass } from '../evidenceClass'
import { EvidenceGlyph, type InspectedEvidence } from './EvidenceInspector'

// Selected #46 built-in identities. Missing members remain requested, never substituted.
export const NOWCAST_STACK: LayerSelection[] = ['geomet-live-goes-east-naturalcolor', 'eccc-hrdps-surface-total-cloud', 'eccc-cap-alerts-alerts_features', 'eccc-radar-radar', 'eccc-lightning-lightning'].map((id) => ({ id, opacity: 0.85, visible: true }))
export interface DrawEvidence { id: string; drawn: boolean; description: string; times: string[] }
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
export function MapStack({ layers, stack, onChange, drawn, onInspect }: {
  layers: LayerItem[]; stack: LayerSelection[]; onChange: (stack: LayerSelection[]) => void; drawn: DrawEvidence[]
  onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void
}) {
  const [saved, setSaved] = useState(readSaved)
  const [name, setName] = useState(''); const [notice, setNotice] = useState('')
  const patch = (id: string, values: Partial<LayerSelection>) => onChange(stack.map((entry) => entry.id === id ? { ...entry, ...values } : entry))
  const move = (index: number, delta: number) => { const next = [...stack]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; onChange(next) }
  return <section className="bench-stack" aria-label="Ordered Map stack">
    <h3>Map stack <small>Top first</small></h3>
    <div className="bench-stack-actions"><button onClick={() => onChange(NOWCAST_STACK.map((entry) => ({ ...entry })))}>Nowcast</button>
      <label>Saved stacks<select value="" onChange={(e) => { if (Object.hasOwn(saved, e.target.value)) onChange(saved[e.target.value].map((entry) => ({ ...entry }))) }}><option value="">Load stack…</option>{Object.keys(saved).map((key) => <option key={key}>{key}</option>)}</select></label>
      <form onSubmit={(e) => { e.preventDefault(); const key = name.trim(); if (!key || key.length > 60) return; if (Object.keys(saved).length >= 12 && !Object.hasOwn(saved, key)) { setNotice('Twelve Saved stacks maximum.'); return }; const next = { ...saved, [key]: stack }; try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); setSaved(next); setNotice(`Saved ${key}`) } catch { setNotice('Browser storage unavailable; stack was not saved.') } }}>
        <label>Stack name<input maxLength={60} value={name} onChange={(e) => setName(e.target.value)} /></label><button>Save stack</button>
      </form>
      <label>Add layer<select value="" onChange={(e) => { if (e.target.value) onChange([...stack, { id: e.target.value, opacity: 0.85, visible: true }]) }}><option value="">Choose published layer…</option>{layers.filter((layer) => !stack.some((entry) => entry.id === layer.id)).map((layer) => <option key={layer.id} value={layer.id}>{layer.title}</option>)}</select></label>
    </div>
    {notice && <p role="status">{notice}</p>}
    {stack.length === 0 && <p>Basemap only. No meteorological layer is requested.</p>}
    <ol reversed>{[...stack].reverse().map((entry, topIndex) => {
      const index = stack.length - topIndex - 1
      const layer = layers.find((layer) => layer.id === entry.id)
      const actual = drawn.find((row) => row.id === entry.id)
      const title = layer?.title ?? entry.id
      const description = layer ? actual?.description ?? 'No frame has been drawn.' : 'Requested layer is unavailable in the published layer response.'
      return <li key={entry.id}>
        <div><EvidenceGlyph kind={resolveEvidenceClass(layer?.evidence_class)} /><strong>{title}</strong><small>{layer ? familyTitle(layerFamily(layer)) : 'Family unknown'} · {layer?.product || 'Source identity not supplied'}</small></div>
        <p>{entry.visible ? description : 'Hidden by reader.'}</p>
        <div className="bench-stack-row-actions"><label><input type="checkbox" checked={entry.visible} onChange={(e) => patch(entry.id, { visible: e.target.checked })} />Show {title}</label>
          <label>Opacity<input aria-label={`Stack opacity ${title}`} type="range" min={0} max={1} step={0.05} value={entry.opacity} onChange={(e) => patch(entry.id, { opacity: Number(e.target.value) })} /></label>
          <button aria-label={`Raise ${title}`} disabled={index === stack.length - 1} onClick={() => move(index, 1)}>↑</button><button aria-label={`Lower ${title}`} disabled={index === 0} onClick={() => move(index, -1)}>↓</button>
          <button aria-label={`Inspect layer ${title}`} onClick={(e) => onInspect({ key: `layer:${entry.id}`, label: title, text: description, details: { 'Returned layer': layer ?? null, 'Actual frame times': actual?.times ?? null } }, e.currentTarget)}>Inspect</button>
          <button aria-label={`Remove ${title}`} onClick={() => onChange(stack.filter((row) => row.id !== entry.id))}>Remove</button>
        </div>
      </li>
    })}</ol>
  </section>
}
