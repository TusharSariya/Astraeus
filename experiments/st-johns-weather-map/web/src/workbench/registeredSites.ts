import type { Site } from '../sites/types'
import type { LocationPoint } from '../types'
export interface RegisteredSite extends Site { geometry_note: string | null }
export interface RegisteredSites { version: string; sites: RegisteredSite[]; notice: string | null }
export async function loadRegisteredSites(signal?: AbortSignal): Promise<RegisteredSites> {
  const response = await fetch('/api/experiments/weather/v0/registry/sites', { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`Registered sites unavailable (${response.status})`)
  const body = await response.json() as Partial<RegisteredSites>
  if (typeof body.version !== 'string' || !/^[a-f0-9]{64}$/.test(body.version) || !Array.isArray(body.sites) || body.sites.length > 1000) throw new Error('Registered site response is malformed')
  for (const site of body.sites) {
    if (!site || typeof site.id !== 'string' || typeof site.name !== 'string' || !Number.isFinite(site.latitude) || Math.abs(site.latitude) > 90 || !Number.isFinite(site.longitude) || Math.abs(site.longitude) > 180 || !site.horizon || !Number.isFinite(site.horizon.bearing_resolution_deg) || site.horizon.bearing_resolution_deg <= 0 || !Array.isArray(site.horizon.elevation_deg) || site.horizon.elevation_deg.length > 3600 || !site.horizon.elevation_deg.every(Number.isFinite)) throw new Error('Registered site geometry is malformed')
  }
  return { version: body.version, sites: body.sites, notice: typeof body.notice === 'string' ? body.notice : null }
}
/** Reference distance only, never site adoption, evidence coverage or horizon transfer. */
export function nearestRegisteredSite(point: LocationPoint, sites: RegisteredSite[]) {
  const rad = Math.PI / 180
  return sites.map((site) => {
    const a = Math.sin((site.latitude - point.latitude) * rad / 2) ** 2 + Math.cos(point.latitude * rad) * Math.cos(site.latitude * rad) * Math.sin((site.longitude - point.longitude) * rad / 2) ** 2
    return { site, distanceKm: 6371.0088 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a)))) }
  }).sort((a, b) => a.distanceKm - b.distanceKm)[0] ?? null
}
