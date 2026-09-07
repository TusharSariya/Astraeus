import type { components as SourceApi } from '../generated/source-api'
import type { CatalogSource, SourceVariant } from '../types'

type Choice = { key: string; label: string; selection: Omit<SourceApi['schemas']['Selector'], 'id' | 'run'>; reason: string }
export function variantLabel(variant: SourceVariant): string {
  return [variant.kind.replaceAll('_', ' '), variant.member ? `Member ${variant.member}` : null, variant.statistic,
    variant.quantile != null ? `quantile ${variant.quantile}` : null,
    variant.threshold != null ? `${variant.comparison} ${variant.threshold}` : null].filter(Boolean).join(' · ')
}
export function capabilityOptions(catalog: CatalogSource[]): Choice[] {
  return catalog.flatMap((source) => (source.capabilities ?? []).filter((capability) => capability.native_series && capability.source_id === source.id).flatMap((capability) => capability.variants.flatMap((variant) => capability.levels.map((level) => {
    const selection = { source_id: source.id, product_id: capability.product_id, field: capability.field, variant: { kind: variant.kind, member: variant.member ?? null, statistic: variant.statistic ?? null, quantile: variant.quantile ?? null, threshold: variant.threshold ?? null, comparison: variant.comparison ?? null }, level }
    return { key: JSON.stringify(selection), selection,
      label: `${source.id} · ${capability.product_id} · ${capability.field} · ${variantLabel(variant)} · ${level}`,
      reason: `${capability.time_semantics}. ${capability.coverage_description}. Declared read path; available samples are established by the response.` }
  }))))
}
export function resolveSeriesOption(key: string, options: Choice[]): Choice {
  const exact = options.find((option) => option.key === key)
  if (exact) return exact
  const [source_id, field] = key.split('|')
  // Resolve legacy field jumps only when the catalogue names one unambiguous path.
  const matches = options.filter((option) => option.selection.source_id === source_id && option.selection.field === field)
  if (matches.length === 1) return { ...matches[0], key }
  let selection: Choice['selection'] = { source_id, field: field ?? '', product_id: null, variant: null, level: null }
  try { const retained = JSON.parse(key); if (retained && typeof retained.source_id === 'string' && typeof retained.field === 'string') selection = retained } catch { /* Legacy selection remains visible. */ }
  return { key, selection, label: [selection.source_id, selection.product_id, selection.field, selection.variant ? variantLabel(selection.variant) : null, selection.level, 'Retained selection'].filter(Boolean).join(' · '),
    reason: matches.length > 1 ? 'Choose a declared product, variant and level; this retained field has multiple delivery paths.' : 'Native Series support is not declared for this retained selection. A response may report unavailable; no alternative is substituted.' }
}
