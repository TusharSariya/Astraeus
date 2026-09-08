import { useMemo, useState } from 'react'
import type { CatalogSource, LayerItem, LayerSelection } from '../types'
import { subjectForFamily, discoveryEntries, dimensions, groupDiscovery, matchesDiscovery, type Dimension, type Filters, type DiscoveryEntry } from './discovery'
import { layerImagery } from './layerIdentity'
import { EvidenceGlyph } from './EvidenceInspector'
import { resolveEvidenceClass } from '../evidenceClass'

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
    <label>{label}<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Name, provider, model or field" /></label>
    {setGroup && <label>Group by<select value={group} onChange={e => setGroup(e.target.value as Dimension | 'Ungrouped')}>{['Subject', 'Provider', 'Model/product', 'Kind', 'Ungrouped'].map(g => <option key={g}>{g}</option>)}</select></label>}
    <div className="discovery-chips">{dimensions.flatMap(key => (filters[key] ?? []).map(value => <button key={`${key}:${value}`} onClick={() => toggle(key,value)} aria-label={`Remove ${key} filter ${value}`}>{value} ×</button>))}</div>
    <details className="discovery-filters"><summary>Filters{Object.values(filters).flat().length ? ` · ${Object.values(filters).flat().length}` : ''}</summary>
      {dimensions.map(key => <fieldset key={key}><legend>{key}</legend>{[...new Set(entries.flatMap(e => e.facets[key]))].sort().map(value => <label key={value}><input type="checkbox" checked={filters[key]?.includes(value) ?? false} onChange={() => toggle(key,value)} />{value}</label>)}</fieldset>)}
    </details>
    <button onClick={() => { setQuery(''); setFilters({}); onClear?.() }}>Clear filters</button>
  </div>
}
export function DiscoveryBrowser({ catalog, layers, stack = [], onAdd, onPoint, onSeries, onSource, error }: DiscoveryActions & {
  catalog: CatalogSource[]; layers: LayerItem[]; stack?: LayerSelection[]; onAdd?: (id: string) => void; error?: string | null
}) {
  const [query,setQuery] = useState(''), [filters,setFilters] = useState<Filters>({}), [group,setGroup] = useState<Dimension | 'Ungrouped'>('Subject')
  const entries = useMemo(() => discoveryEntries(catalog,layers), [catalog,layers])
  const visible = entries.filter(entry => matchesDiscovery(entry,query,filters))
  return <section aria-label="Unified source discovery" className="discovery-browser">
    <DiscoveryFilters {...{ entries, query, setQuery, filters, setFilters, group, setGroup }} />
    <p role="status">{visible.length} unique entries · {catalog.length} registered sources returned</p>
    {error && <p role="status">Source catalogue unavailable: {error}. Other returned entries remain visible.</p>}
    {!visible.length && <p>No matching sources or layers. Clear filters to browse all entries.</p>}
    {groupDiscovery(visible,group).map(section => <details key={section.label} className="discovery-group" open><summary>{section.label} · {section.entries.length}</summary>
      {section.entries.map(entry => <DiscoveryCard key={entry.id} subjects={group === 'Subject' ? [section.label] : filters.Subject ?? []} {...{ entry, stack, onAdd, onPoint, onSeries, onSource }} />)}
    </details>)}
  </section>
}
function DiscoveryCard({ entry, stack, onAdd, onPoint, onSeries, onSource, subjects }: DiscoveryActions & { entry: DiscoveryEntry; subjects: string[]; stack: LayerSelection[]; onAdd?: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false)
  const source = entry.source
  const matchesSubject = (values: string[]) => !subjects.length || !values.length || values.some(v => subjects.includes(v))
  const declared = source?.discovery?.map_capabilities ?? []
  const maps = [...declared.filter(c => matchesSubject(c.subjects)).map(c => ({ id: c.layer_id, title: c.title, layer: entry.layers.find(l => l.id === c.layer_id) })), ...entry.layers.filter(l => !declared.some(c => c.layer_id === l.id) && matchesSubject(l.family ? [subjectForFamily(l.family)] : [])).map(layer => ({ id: layer.id, title: layer.title, layer }))]
  const points = [...new Set(source?.capabilities?.filter(c => c.point && c.point_product).map(c => c.point_product!) ?? [])]
  const series = [...new Set(source?.capabilities?.filter(c => c.native_series && matchesSubject(source?.fields?.filter(f => f.key === c.field).map(f => subjectForFamily(f.family)) ?? [])).map(c => c.field) ?? [])]
  return <article className="discovery-card" data-source-id={source?.id ?? entry.id}>
    <strong title={entry.title}>{entry.title}</strong>
    <small>{entry.facets.Provider.join(', ')} · {entry.facets.Kind.join(', ')}</small>
    <small>{entry.facets.Interface.join(' · ')} · {source?.state ?? 'Source identity unknown'}</small>
    {!entry.actionable && <p className="discovery-absence" title={source?.status_reason}>{source?.status_reason ?? 'No implemented delivery capability declared.'}</p>}
    <details onToggle={e => setExpanded(e.currentTarget.open)}><summary>Capabilities · {maps.length + points.length + series.length}</summary>{expanded && <>
      {maps.map(({ id,title,layer }) => <div className="discovery-capability" key={id}><strong title={title}><EvidenceGlyph kind={resolveEvidenceClass(layer?.evidence_class)} /> {title}</strong><small>{layer ? layer.kind === 'raster' ? `Imagery ${layerImagery(layer).status}` : 'Map features · availability at Focus unestablished' : 'Implemented map path · no frame currently listed'}</small>
        {onAdd && <button disabled={stack.some(s => s.id === id)} onClick={() => onAdd(id)} aria-label={`Add ${title}`}>{stack.some(s => s.id === id) ? 'Added' : 'Add to map'}</button>}
        <details><summary>Layer details</summary><p>{layer?.semantics ?? 'No current frame returned. Adding preserves this selection and reports availability without inventing imagery.'}</p>{layer && <p>{layerImagery(layer).reason}</p>}</details>
      </div>)}
      {points.map(product => <div className="discovery-capability" key={product}><strong>{product}</strong><small>Point · availability at Focus unestablished</small>{onPoint && <button onClick={e => onPoint(product,e.currentTarget)}>Open point · {product}</button>}<details><summary>Point limits</summary>{source?.capabilities?.filter(c => c.point_product === product).map((c,i) => <p key={i}>{c.field} · {c.time_semantics} · {c.coverage_description}</p>)}</details></div>)}
      {series.map(field => <div className="discovery-capability" key={field}><strong>{field}</strong>{onSeries && source && <button onClick={() => onSeries(field,source.id)}>Open series · {field}</button>}</div>)}
    </>} </details>
    {source && onSource && <button onClick={e => onSource(source,e.currentTarget)}>Source details</button>}
  </article>
}
