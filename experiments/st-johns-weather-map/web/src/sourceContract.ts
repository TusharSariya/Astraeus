import type { SourceCapability, SourceConfiguration, SourceVariant } from './types'
const record = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === 'object' && !Array.isArray(value))
const named = (value: unknown): value is string => typeof value === 'string' && value.length > 0
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(named)
export function isSourceVariant(value: unknown): value is SourceVariant {
  if (!record(value) || !['deterministic', 'observation', 'member', 'provider_statistic', 'derived_statistic'].includes(String(value.kind))) return false
  const member = value.kind === 'member', statistic = value.kind === 'provider_statistic' || value.kind === 'derived_statistic'
  return (member ? named(value.member) : value.member == null)
    && (statistic ? named(value.statistic) : value.statistic == null)
    && (value.quantile == null || (statistic && typeof value.quantile === 'number' && Number.isFinite(value.quantile) && value.quantile >= 0 && value.quantile <= 1))
    && (value.threshold == null ? value.comparison == null : statistic && typeof value.threshold === 'number' && Number.isFinite(value.threshold) && named(value.comparison))
}
export const isPointProductToken = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 100 && value.trim() === value && !/[\u0000-\u001f\u007f-\u009f]/.test(value)
export function isSourceCapability(value: unknown, sourceId: string): value is SourceCapability {
  return record(value) && value.source_id === sourceId && named(value.product_id) && named(value.field)
    && (value.point_product == null || isPointProductToken(value.point_product))
    && Array.isArray(value.variants) && value.variants.length > 0 && value.variants.every(isSourceVariant)
    && strings(value.levels) && value.levels.length > 0 && typeof value.point === 'boolean' && typeof value.native_series === 'boolean'
    && ['latest', 'latest_previous', 'not_applicable'].includes(String(value.run_selection)) && named(value.time_semantics) && named(value.coverage_description)
}
export function isSourceConfiguration(value: unknown): value is SourceConfiguration {
  return record(value) && ['ready', 'missing_configuration', 'access_denied', 'product_unavailable', 'missing_compute', 'acquisition_failed', 'unknown'].includes(String(value.state))
    && named(value.reason) && strings(value.required_environment)
    && (value.checked_at == null || typeof value.checked_at === 'string' && Number.isFinite(Date.parse(value.checked_at)))
}
