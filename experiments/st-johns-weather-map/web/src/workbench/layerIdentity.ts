import type { LayerItem } from '../types'
import { resolveFieldKey } from '../fieldFamily'

export function layerMapping(layer: LayerItem) {
  const unknown = { status: 'unknown' as const, fields: [] as NonNullable<LayerItem['field_mappings']>, reason: layer.mapping_reason ?? 'Source identity not supplied; no join is inferred from product or title' }
  if (layer.mapping_status === undefined && layer.field_mappings === undefined) return unknown
  if (!['known', 'partial', 'unknown'].includes(layer.mapping_status ?? '') || !Array.isArray(layer.field_mappings) || layer.field_mappings.length > 128) return { ...unknown, reason: 'Source mapping is unreadable' }
  const fields = layer.field_mappings
  if (!fields.every((row) => row && typeof row.source_id === 'string' && row.source_id.length > 0 && (row.field_key === null || (typeof row.field_key === 'string' && resolveFieldKey(row.field_key) === row.field_key)) && (row.declared_field === null || typeof row.declared_field === 'string'))) return { ...unknown, reason: 'Source mapping is unreadable' }
  const expected = fields.length ? fields.every((row) => row.field_key !== null) ? 'known' : 'partial' : 'unknown'
  if (expected !== layer.mapping_status) return { ...unknown, reason: 'Source mapping status contradicts its records' }
  return { status: layer.mapping_status, fields, reason: layer.mapping_reason ?? 'Mapping reason not supplied' }
}

export function layerImagery(layer: LayerItem) {
  const unknown = { status: 'unknown' as const, checked_at: null, basis: 'not_supplied', times: [] as string[], reason: 'Imagery availability is unknown; listed sample times are not an image inventory' }
  const value = layer.imagery_availability
  if (!value) return unknown
  if (!['known', 'unknown', 'unavailable'].includes(value.status) || typeof value.reason !== 'string' || typeof value.basis !== 'string' || !Array.isArray(value.times)
    || !value.times.every((time) => typeof time === 'string' && Number.isFinite(Date.parse(time)))
    || (value.checked_at !== null && (typeof value.checked_at !== 'string' || !Number.isFinite(Date.parse(value.checked_at))))
    || (value.status === 'known' && value.checked_at === null) || (value.status !== 'known' && value.times.length > 0)) return { ...unknown, reason: 'Imagery availability is unreadable' }
  return value
}
