import { selectionState } from './pointSelections'
import { useMemo, useState } from 'react'
import type { CatalogSource, LayerItem, LayerSelection, PointFieldSelection } from '../types'
import { discoveryRows, dimensions, groupDiscovery, matchesDiscovery, type Dimension, type Filters, type DiscoveryRow, type DiscoveryEntry } from './discovery'
import { layerImagery } from './layerIdentity'
import { LayerRow } from './LayerRow'

export interface DiscoveryActions {
  onPoint?: (product: string, opener: HTMLButtonElement) => void
  onSeries?: (field: string, source: string) => void
  onSource?: (source: CatalogSource, opener: HTMLButtonElement) => void
}
export function DiscoveryFilters({ entries, query, setQuery, filters, setFilters, group, setGroup, label = 'Search layers and sources', onClear }: {
  label?: string; onClear?: () => void
  entries: DiscoveryEntry[]; query: string; setQuery: (s: string) => void; filters: Filters; setFilters: (f: Filters) => void
  group?: Dimension | 'Ungrouped'; setGroup?: (g: Dimension | 'Ungrouped') => void
}) {
  const toggle = (key: Dimension, value: string) => setFilters({ ...filters, [key]: filters[key]?.includes(value) ? filters[key]!.filter(v => v !== value) : [...filters[key] ?? [], value] })
  return <div className="discovery-controls">
    <label className="discovery-search"><span className="visually-hidden">{label}</span><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Name, provider, model or field" /></label>
    {setGroup && <label>Group by<select value={group} onChange={e => setGroup(e.target.value as Dimension | 'Ungrouped')}>{['Subject', 'Provider', 'Model/product', 'Kind', 'Ungrouped'].map(g => <option key={g}>{g}</option>)}</select></label>}
    <div className="discovery-chips">{dimensions.flatMap(key => (filters[key] ?? []).map(value => <button key={`${key}:${value}`} onClick={() => toggle(key,value)} aria-label={`Remove ${key} filter ${value}`}>{value} ×</button>))}</div>
    <details className="discovery-filters"><summary>Filters{Object.values(filters).flat().length ? ` · ${Object.values(filters).flat().length}` : ''}</summary>
      {dimensions.map(key => <fieldset key={key}><legend>{key}</legend>{[...new Set(entries.flatMap(e => e.facets[key]))].sort().map(value => <label key={value}><input type="checkbox" checked={filters[key]?.includes(value) ?? false} onChange={() => toggle(key,value)} />{value}</label>)}</fieldset>)}
    </details>
    {(query || Object.values(filters).some(values => values?.length)) && <button className="discovery-clear" onClick={() => { setQuery(''); setFilters({}); onClear?.() }}>Clear</button>}
  </div>
}
export function DiscoveryBrowser({ catalog, layers, stack = [], onToggle, onDetails, error }: {
  catalog: CatalogSource[]; layers: LayerItem[]; stack?: LayerSelection[]
  onToggle: (id: string, point?: PointFieldSelection) => void; onDetails: (row: DiscoveryRow, opener: HTMLButtonElement) => void; error?: string | null
}) {
  const [query,setQuery] = useState(''), [filters,setFilters] = useState<Filters>({}), [group,setGroup] = useState<Dimension | 'Ungrouped'>('Subject')
  const entries = useMemo(() => discoveryRows(catalog,layers), [catalog,layers])
  const visible = entries.filter(entry => matchesDiscovery(entry,query,filters))
  const row = (entry: DiscoveryRow) => {
    const layer = layers.find(layer => layer.id === entry.layerId)
    const status = entry.layerId ? layer ? layer.kind === 'raster' ? layerImagery(layer).status : 'Map' : 'Unknown' : entry.facets.Interface.includes('Point') ? 'Point' : entry.source?.state ?? 'Unknown'
    return <li key={entry.id} data-source-id={entry.source?.id ?? entry.id}><LayerRow title={entry.title} status={status}
      selected={entry.layerId || entry.point ? stack.some(s => s.id === (entry.layerId ?? entry.id)) : undefined}
      state={entry.layerId || entry.point ? selectionState(stack.find(s => s.id === (entry.layerId ?? entry.id))) : undefined}
      onPrimary={opener => entry.layerId || entry.point ? onToggle(entry.layerId ?? entry.id, entry.point) : onDetails(entry, opener)}
      onDetails={opener => onDetails(entry, opener)} /></li>
  }
  return <section aria-label="Unified source discovery" className="discovery-browser">
    <DiscoveryFilters {...{ entries, query, setQuery, filters, setFilters, group, setGroup }} />
    <span className="visually-hidden" role="status">{visible.length} unique entries</span>
    {error && <p role="status">Source catalogue unavailable: {error}. Other returned entries remain visible.</p>}
    {!visible.length && <p>No matching sources or layers. Clear filters to browse all entries.</p>}
    {group === 'Ungrouped' ? <ul className="dense-layer-list">{visible.map(row)}</ul> : groupDiscovery(visible,group).map(section => <details key={section.label} className="discovery-group" open><summary>{section.label}</summary>
      <ul className="dense-layer-list">{section.entries.map(row)}</ul>
    </details>)}
  </section>
}

export function SourceActions({ source, onPoint, onSeries, onSource }: DiscoveryActions & { source?: CatalogSource }) {
  if (!source) return null
  const points = [...new Set(source.capabilities?.filter(c => c.point && c.point_product).map(c => c.point_product!) ?? [])]
  const series = [...new Set(source.capabilities?.filter(c => c.native_series).map(c => c.field) ?? [])]
  return <section aria-label="Source capabilities">
    <h4>{source.product}</h4><p>{source.producer} · {source.id} · {source.state}</p><p>{source.status_reason}</p>
    {points.map(product => <div key={product}>{onPoint && <button onClick={e => onPoint(product,e.currentTarget)}>Open point · {product}</button>}
      {source.capabilities?.filter(c => c.point_product === product).map((c,i) => <p key={i}>{c.field} · {c.time_semantics} · {c.coverage_description}</p>)}</div>)}
    {series.map(field => onSeries && <button key={field} onClick={() => onSeries(field,source.id)}>Open series · {field}</button>)}
    {onSource && <button onClick={e => onSource(source,e.currentTarget)}>Source provenance</button>}
  </section>
}
