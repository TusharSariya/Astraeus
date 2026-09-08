import type { CatalogSource, LayerItem, LayerSelection, PointFieldSelection, SourceCapability, SourceVariant, ServedFieldValue } from '../types'
import { layerMapping } from './layerIdentity'
import { CATALOGUE_FIELDS } from '../fieldFamilies'

export const pointIdentity = (p: PointFieldSelection) => JSON.stringify([p.sourceId, p.productId, p.product, p.field])
export const pointSelectionId = (p: PointFieldSelection) => `point:${encodeURIComponent(pointIdentity(p))}`
export const variantIdentity = (v?: SourceVariant | null) => JSON.stringify([v?.kind, v?.member, v?.statistic, v?.quantile, v?.threshold, v?.comparison])
export function pointFieldLabel(p: PointFieldSelection) {
  if (!p.field.startsWith('weathernext3_')) return p.field.replaceAll('_', ' ')
  const stat=p.field.match(/_(mean|p10|p25|p50|p75|p90)(?=_|$)/)?.[1]
  const name=p.field.replace(/^weathernext3_/, '').replace(/_(mean|p10|p25|p50|p75|p90)(?=_|$)/, '').replaceAll('_', ' ')
  return `${stat} · ${name}`
}
export const pointLabel = (p: PointFieldSelection) => `${p.field.startsWith('weathernext3_') ? `WN3 ${p.product.endsWith('historical') ? 'historical' : 'forecast'}` : p.product} · ${pointFieldLabel(p)}`
export function pointCapabilities(catalog: CatalogSource[]) {
  const result = new Map<string, {source: CatalogSource; capability: SourceCapability}>()
  for (const source of catalog) for (const c of source.capabilities ?? []) {
    if (c.source_id !== source.id || !c.point || !c.point_product) continue
    const key = pointIdentity(pointDefault(c)), previous = result.get(key)
    if (previous) {
      previous.capability.variants = [...new Map([...previous.capability.variants, ...c.variants].map(v => [variantIdentity(v),v])).values()]
      previous.capability.levels = [...new Set([...previous.capability.levels, ...c.levels])]
    } else result.set(key, {source, capability: {...c,variants:[...c.variants],levels:[...c.levels]}})
  }
  // Preserve the existing GEFS all-members point default; this is not a reduction.
  for (const {capability:c} of result.values()) if (c.source_id === 'noaa-gefs' && c.point_product === 'GEFS' && c.variants.some(v => v.kind === 'member')) c.variants.unshift({kind:'member',member:'all'})
  return [...result.values()]
}
export function pointDefault(c: SourceCapability): PointFieldSelection {
  return { sourceId: c.source_id, productId: c.product_id, product: c.point_product!, field: c.field,
    variant: c.variants.length === 1 ? c.variants[0] : c.source_id === 'noaa-gefs' && c.point_product === 'GEFS' ? {kind:'member',member:'all'} : undefined,
    level: c.levels.length === 1 ? c.levels[0] : undefined }
}
/** Join declared catalogue keys only. Multiple delivery products are not interchangeable. */
export function layerPoints(layer: LayerItem | undefined, catalog: CatalogSource[]): PointFieldSelection[] {
  if (!layer) return []
  const caps = pointCapabilities(catalog)
  return layerMapping(layer).fields.flatMap(mapping => {
    const matches = caps.filter(({ capability: c }) => c.source_id === mapping.source_id && c.field === mapping.field_key)
    return matches.length === 1 ? [pointDefault(matches[0].capability)] : []
  }).filter((p, index, rows) => rows.findIndex(other => pointIdentity(other) === pointIdentity(p)) === index)
}
export function selectionPoints(entry: LayerSelection, layers: LayerItem[], catalog: CatalogSource[]) {
  return entry.points ?? layerPoints(layers.find(layer => layer.id === entry.id), catalog)
}
export function selectionState(entry?: LayerSelection) { return !entry ? 'Off' : entry.visible && !entry.pointOnly ? 'Map + data' : 'Data only' }
export function cycleSelection(stack: LayerSelection[], id: string, point?: PointFieldSelection, mapped?: PointFieldSelection[]): LayerSelection[] {
  const entry = stack.find(row => row.id === id)
  if (!entry) return [...stack, { id, visible: !point, opacity: .85, ...(point ? { pointOnly: true, points: [point] } : mapped?.length ? { points: mapped } : {}) }]
  if (entry.visible && !entry.pointOnly) return stack.map(row => row.id === id ? { ...row, visible: false } : row)
  return stack.filter(row => row.id !== id)
}
export function capabilityFor(p: PointFieldSelection, catalog: CatalogSource[]) {
  return pointCapabilities(catalog).find(({ capability: c }) => pointIdentity(pointDefault(c)) === pointIdentity(p))?.capability
}
export function pointUnavailable(p: PointFieldSelection, catalog: CatalogSource[], runs: Record<string, string> = {}) {
  const c = capabilityFor(p, catalog)
  if (!c) return 'Point capability unavailable for this retained selection.'
  if (runs[p.sourceId] && runs[p.sourceId] !== 'latest') return 'This point endpoint cannot request the selected named run. Choose Latest available explicitly.'
  if (p.level == null || !c.levels.includes(p.level)) return 'Choose a declared level in layer details.'
  if (!p.variant || !c.variants.some(v => variantIdentity(v) === variantIdentity(p.variant))) return 'Choose a declared member or statistic in layer details.'
  // The point endpoint selects canonical fields, not an arbitrary vertical coordinate.
  if (c.levels.length > 1) return 'This point endpoint cannot request a level independently; selected level is unsupported.'
  return null
}
export function pointFamily(p: PointFieldSelection, catalog: CatalogSource[]) {
  return catalog.find(s => s.id === p.sourceId)?.fields?.find(f => f.key === p.field)?.family ?? CATALOGUE_FIELDS[p.field]?.family ?? 'ungrouped'
}
export function matchesPoint(row: ServedFieldValue, p: PointFieldSelection) {
  const a = row.attribution, v = p.variant
  if (a.sourceId !== p.sourceId || a.fieldKey !== p.field) return false
  if (v?.member && (v.member === 'all' ? !a.member : a.member !== v.member)) return false
  if (v?.statistic && (a.ensemble?.statistic !== v.statistic || (a.ensemble.quantile ?? null) !== (v.quantile ?? null) || (a.ensemble.threshold ?? null) !== (v.threshold ?? null) || (a.ensemble.comparison ?? null) !== (v.comparison ?? null))) return false
  if (v?.kind === 'provider_statistic' && a.ensemble?.computedHere !== false) return false
  if (v?.kind === 'derived_statistic' && a.ensemble?.computedHere !== true) return false
  return true
}

/** Shared saved-stack / URL decoder. Never drop a retained point identity. */
export function parseSelection(value: unknown): LayerSelection {
  if (!value || typeof value !== 'object') throw new Error('invalid selection')
  const e = value as LayerSelection
  if (typeof e.id !== 'string' || !/^[\w.:%\-]{1,1600}$/.test(e.id) || typeof e.visible !== 'boolean' || !Number.isFinite(e.opacity) || e.opacity < 0 || e.opacity > 1 || (e.pointOnly !== undefined && typeof e.pointOnly !== 'boolean')) throw new Error('invalid selection')
  if (e.points !== undefined && (!Array.isArray(e.points) || e.points.length > 128 || !e.points.every(p => {
    if (!p || ![p.sourceId,p.productId,p.product,p.field].every(v => typeof v === 'string' && v.length > 0 && v.length <= 256) || (p.level != null && typeof p.level !== 'string')) return false
    const v = p.variant
    return v == null || (typeof v === 'object' && ['deterministic','observation','member','provider_statistic','derived_statistic','unknown'].includes(v.kind) && [v.member,v.statistic,v.comparison].every(x => x == null || typeof x === 'string') && [v.quantile,v.threshold].every(x => x == null || Number.isFinite(x)))
  }))) throw new Error('invalid point selection')
  if (e.pointOnly && (e.visible || e.points?.length !== 1 || e.id !== pointSelectionId(e.points[0]))) throw new Error('invalid point-only selection')
  return { id: e.id, visible: e.visible, opacity: e.opacity, ...(e.pointOnly ? { pointOnly: true } : {}), ...(e.points ? { points: e.points } : {}) }
}
