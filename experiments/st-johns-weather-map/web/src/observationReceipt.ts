import type { components } from './generated/source-api'
type Schemas = components['schemas']
const record = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === 'object' && !Array.isArray(value))
const timestamp = (value: unknown): value is string => typeof value === 'string' && Number.isFinite(Date.parse(value)) && /(?:Z|[+-]\d\d:\d\d)$/.test(value)
const coordinate = (value: unknown, limit: number): value is number => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= limit
function url(value: unknown): value is string {
  if (typeof value !== 'string' || !value.length || value.length > 2048) return false
  try { const parsed = new URL(value); return parsed.protocol === 'https:' && !parsed.username && !parsed.password } catch { return false }
}
function headers(value: unknown, allowed: string[]): Record<string, string> | null {
  if (!record(value) || Object.keys(value).length > 16) return null
  const result: Record<string, string> = {}
  for (const [key, item] of Object.entries(value)) {
    if (typeof item !== 'string' || item.length > 2048 || !key.length || key.length > 128) return null
    if (allowed.includes(key.toLowerCase())) result[key.toLowerCase()] = item
  }
  return result
}
const bounded = <T,>(value: T, limit: number): T | null => new TextEncoder().encode(JSON.stringify(value)).length <= limit ? value : null
/** Project known receipt fields only; never retain nested arbitrary provider keys. */
export function observationReceipt(source: 'eccc-aqhi', value: unknown): Schemas['AQHIAcquisition'] | null
export function observationReceipt(source: 'eccc-swob', value: unknown): Schemas['SWOBAcquisition'] | null
export function observationReceipt(source: 'eccc-aqhi' | 'eccc-swob', value: unknown): Schemas['AQHIAcquisition'] | Schemas['SWOBAcquisition'] | null {
  if (!record(value) || !url(value.effective_url) || !timestamp(value.cached_at) || !timestamp(value.expires_at)
    || Date.parse(value.expires_at) <= Date.parse(value.cached_at) || !timestamp(value.transport_completed_at)
    || typeof value.body_bytes !== 'number' || !Number.isInteger(value.body_bytes) || value.body_bytes <= 0
    || value.body_bytes > (source === 'eccc-aqhi' ? 2 * 1024 * 1024 : 256 * 1024)
    || typeof value.body_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(value.body_sha256)) return null
  const request_headers = headers(value.request_headers, ['accept', 'accept-encoding', 'user-agent'])
  const response_headers = headers(value.response_headers, ['age', 'cache-control', 'content-type', 'date', 'etag', 'last-modified'])
  if (!request_headers || !response_headers) return null
  const common = { effective_url: value.effective_url, cached_at: value.cached_at, expires_at: value.expires_at,
    transport_completed_at: value.transport_completed_at, body_bytes: value.body_bytes, body_sha256: value.body_sha256, request_headers, response_headers }
  if (source === 'eccc-aqhi') return url(value.provider_url) ? bounded({ ...common, provider_url: value.provider_url }, 12 * 1024) : null
  const request = value.request
  if (!record(request) || request.source_id !== 'eccc-swob' || !timestamp(request.selected_time)
    || !coordinate(request.latitude, 90) || !coordinate(request.longitude, 180) || !url(request.provider_url)) return null
  return bounded({ ...common, request: { source_id: 'eccc-swob' as const, selected_time: request.selected_time, latitude: request.latitude, longitude: request.longitude, provider_url: request.provider_url } }, 16 * 1024)
}
