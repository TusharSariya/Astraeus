import { pointCapabilities, pointDefault, pointIdentity, pointSelectionId, pointLabel, layerPoints, pointFamily } from './pointSelections'
import type { CatalogSource, LayerItem, PointFieldSelection } from '../types'
import { layerMapping } from './layerIdentity'
import { familyTitle } from '../fieldFamily'

export interface DiscoveryMetadata {
  subjects: string[]; kinds: string[]; methods: string[]; ensemble_forms: string[]
  map_capabilities: { layer_id: string; title: string; product: string | null; subjects: string[] }[]
}
export const dimensions = ['Subject', 'Provider', 'Model/product', 'Kind', 'Method', 'Ensemble form', 'Interface'] as const
export type Dimension = typeof dimensions[number]
export type Filters = Partial<Record<Dimension, string[]>>
export interface DiscoveryEntry {
  id: string; title: string; source?: CatalogSource; layers: LayerItem[]
  facets: Record<Dimension, string[]>; searchable: string; actionable: boolean
}
export const subjectForFamily = (family: string) => ['cloud_cover', 'cloud_geometry', 'cloud_microphysics'].includes(family) ? 'Clouds' : familyTitle(family)
export const subjectsFor = (source: CatalogSource) => source.discovery?.subjects?.length ? source.discovery.subjects :
  [...new Set(source.fields?.filter(f => f.storage !== 'not-published').map(f => subjectForFamily(f.family)) ?? [])]
export function discoveryEntries(catalog: CatalogSource[], layers: LayerItem[]): DiscoveryEntry[] {
  const associated = new Set<string>()
  const entries: DiscoveryEntry[] = catalog.filter(source => !['google-weathernext-2', 'open-meteo-weathernext-2'].includes(source.id)).map(source => {
    const mapped = layers.filter(layer => layerMapping(layer).fields.some(f => f.source_id === source.id) || source.discovery?.map_capabilities.some(c => c.layer_id === layer.id))
    mapped.forEach(layer => associated.add(layer.id))
    const caps = source.capabilities ?? [], meta = source.discovery
    const interfaces = [...(mapped.length || meta?.map_capabilities.length ? ['Map'] : []), ...(caps.some(c => c.point && c.point_product) ? ['Point'] : []), ...(caps.some(c => c.native_series) ? ['Series'] : [])]
    const facets: Record<Dimension, string[]> = {
      Subject: subjectsFor(source), Provider: [source.producer], 'Model/product': [source.product],
      Kind: meta?.kinds ?? [], Method: meta?.methods ?? [], 'Ensemble form': meta?.ensemble_forms ?? [], Interface: interfaces.length ? interfaces : ['Information only'],
    }
    for (const key of dimensions) if (!facets[key].length) facets[key] = ['Unknown']
    return { id: source.id, title: source.product, source, layers: mapped, facets, actionable: interfaces.length > 0,
      searchable: [source.id, source.product, source.producer, source.intermediary, ...Object.values(facets).flat(), ...source.fields?.map(f => f.key) ?? [], ...caps.map(c => `${c.field} ${c.point_product ?? ''}`), ...mapped.map(l => `${l.title} ${l.id}`), ...meta?.map_capabilities.map(c => c.title) ?? []].join(' ').toLowerCase() }
  })
  for (const layer of layers.filter(l => !associated.has(l.id))) {
    const facets: Record<Dimension, string[]> = { Subject: [layer.family ? subjectForFamily(layer.family) : 'Unknown'], Provider: ['Unknown'], 'Model/product': [layer.product || 'Unknown'], Kind: ['Unknown'], Method: ['Unknown'], 'Ensemble form': ['Unknown'], Interface: ['Map'] }
    entries.push({ id: `layer:${layer.id}`, title: layer.title, source: undefined, layers: [layer], facets, actionable: true, searchable: `${layer.id} ${layer.title} ${Object.values(facets).flat().join(' ')}`.toLowerCase() })
  }
  return entries.sort((a,b) => Number(b.actionable)-Number(a.actionable) || a.title.localeCompare(b.title) || a.id.localeCompare(b.id))
}
export function matchesDiscovery(entry: DiscoveryEntry, query: string, filters: Filters) {
  return query.trim().toLowerCase().split(/\s+/).every(word => (entry.searchable.includes(word) || entry.searchable.replace(/[^a-z0-9]/g, '').includes(word.replace(/[^a-z0-9]/g, '')))) &&
    dimensions.every(key => !filters[key]?.length || filters[key]!.some(value => entry.facets[key].includes(value)))
}
export function groupDiscovery<T extends DiscoveryEntry>(entries: T[], group: Dimension | 'Ungrouped') {
  if (group === 'Ungrouped') return [{ label: 'All sources', entries }]
  const labels = [...new Set(entries.flatMap(e => e.facets[group]))].sort((a,b) => Number(a === 'Unknown')-Number(b === 'Unknown') || a.localeCompare(b))
  return labels.map(label => ({ label, entries: entries.filter(e => e.facets[group].includes(label)) }))
}

export function readDiscovery(value: unknown): DiscoveryMetadata | undefined {
  if (!value || typeof value !== 'object') return undefined
  const record = value as Record<string, unknown>
  const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(x => typeof x === 'string' && x.length > 0)
  if (!strings(record.subjects) || !strings(record.kinds) || !strings(record.methods) || !strings(record.ensemble_forms) || !Array.isArray(record.map_capabilities)) return undefined
  if (!record.map_capabilities.every(c => c && typeof c === 'object' && typeof c.layer_id === 'string' && typeof c.title === 'string' && (c.product === null || typeof c.product === 'string') && strings(c.subjects))) return undefined
  return record as unknown as DiscoveryMetadata
}

export interface DiscoveryRow extends DiscoveryEntry {
  layerId?: string
  point?: PointFieldSelection
}
/** The source ledger stays source-based; only Browse flattens capabilities. */
export function discoveryRows(catalog: CatalogSource[], layers: LayerItem[]): DiscoveryRow[] {
  return discoveryEntries(catalog, layers).flatMap(entry => {
    const declared = entry.source?.discovery?.map_capabilities ?? []
    const maps = [...declared.map(cap => {
      const family = entry.layers.find(layer => layer.id === cap.layer_id)?.family
      return { id: cap.layer_id, title: cap.title, subjects: cap.subjects.length ? cap.subjects : family ? [subjectForFamily(family)] : [] }
    }),
      ...entry.layers.filter(layer => !declared.some(cap => cap.layer_id === layer.id)).map(layer => ({
        id: layer.id, title: layer.title, subjects: layer.family ? [subjectForFamily(layer.family)] : ['Unknown'],
      }))]
    const mapped = entry.layers.flatMap(layer => layerPoints(layer, catalog))
    const points: DiscoveryRow[] = pointCapabilities(entry.source ? [entry.source] : []).filter(({capability}) => !mapped.some(p => pointIdentity(p) === pointIdentity(pointDefault(capability)))).map(({capability}) => {
      const point = pointDefault(capability), title = pointLabel(point)
      const facets = { ...entry.facets, Subject: [subjectForFamily(pointFamily(point, catalog))], Interface: ['Point'] }
      return { ...entry, id: pointSelectionId(point), point, title, facets,
        searchable: [title, point.field, point.sourceId, entry.source?.producer, entry.source?.product, ...Object.values(facets).flat()].join(' ').toLowerCase() }
    })
    if (!maps.length) return points.length ? points : [entry]
    return [...points, ...maps.map(map => ({ ...entry, id: `${entry.id}:layer:${map.id}`, layerId: map.id, title: map.title,
      facets: { ...entry.facets, Subject: map.subjects.length ? map.subjects : ['Unknown'] },
      searchable: [map.id, map.title, entry.source?.id, entry.source?.producer, entry.source?.product,
        ...Object.entries(entry.facets).filter(([key]) => key !== 'Subject').flatMap(([, values]) => values), ...map.subjects].join(' ').toLowerCase(),
    }))]
  })
}
