import type { LayerSelection, LocationPoint } from '../types'

export const VIEWS = ['Map', 'Series', 'Sky', 'Activity', 'Sources'] as const
export type View = typeof VIEWS[number]
export interface BenchState {
  location: LocationPoint
  site: string | null
  instant: number | null
  view: View
  dock: View | null
  stack: LayerSelection[] | null
  runs: Record<string, string>
  notices: string[]
}
const viewOf = (value: string | null): View | undefined => VIEWS.find((view) => view.toLowerCase() === value?.toLowerCase())
const validId = (value: unknown): value is string => typeof value === 'string' && /^[a-zA-Z0-9_.:-]{1,160}$/.test(value)

/** Parse only UI selection, never evidence or a promise of source availability. */
export function parseFocusUrl(search: string, fallback: LocationPoint): BenchState {
  const params = new URLSearchParams(search)
  const notices: string[] = []
  let location = fallback
  let site: string | null = params.get('site')
  if (site && !validId(site)) { site = null; notices.push('Invalid registered site in link.') }
  if (params.has('lat') || params.has('lon')) {
    const lat = params.get('lat'); const lon = params.get('lon')
    const latitude = Number(lat); const longitude = Number(lon)
    if (lat?.trim() && lon?.trim() && Number.isFinite(latitude) && Math.abs(latitude) <= 90 && Number.isFinite(longitude) && Math.abs(longitude) <= 180) {
      location = { id: 'point', name: 'Selected point', latitude, longitude, kind: 'map' }
      site = null
    } else notices.push('Invalid coordinates in link; default point selected.')
  }
  const rawTime = params.get('t')
  let instant: number | null = null
  if (rawTime !== null) {
    const value = Date.parse(rawTime)
    if (/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(rawTime) && Number.isFinite(value)) instant = value
    else notices.push('Invalid fixed instant in link; session Now selected.')
  }
  const view = viewOf(params.get('view')) ?? 'Map'
  if (params.has('view') && !viewOf(params.get('view'))) notices.push('Unknown view in link; Map selected.')
  const dock = viewOf(params.get('dock')) ?? null
  let stack: LayerSelection[] | null = null
  if (params.has('stack')) {
    try {
      const raw: unknown = JSON.parse(params.get('stack')!)
      if (!Array.isArray(raw) || raw.length > 32) throw new Error('stack bounds')
      const seen = new Set<string>()
      stack = raw.map((entry: unknown) => {
        if (!entry || typeof entry !== 'object' || !('id' in entry) || !validId(entry.id) || seen.has(entry.id)
          || !('opacity' in entry) || typeof entry.opacity !== 'number' || !Number.isFinite(entry.opacity) || entry.opacity < 0 || entry.opacity > 1
          || !('visible' in entry) || typeof entry.visible !== 'boolean') throw new Error('invalid stack')
        seen.add(entry.id)
        return { id: entry.id, opacity: entry.opacity, visible: entry.visible }
      })
    } catch { notices.push('Invalid Map stack in link; default stack selected.') }
  }
  const runs: Record<string, string> = {}
  for (const [key, value] of params) if (key.startsWith('run.') && validId(key.slice(4)) && value.length <= 160 && value.trim()) runs[key.slice(4)] = value
  return { location, site, instant, view, dock: dock === view ? null : dock, stack, runs, notices }
}

export function serializeFocusUrl(state: Omit<BenchState, 'notices'>, search = ''): string {
  const params = new URLSearchParams(search)
  for (const key of [...params.keys()]) if (['site', 'lat', 'lon', 'view', 'dock', 't', 'stack', 'theme'].includes(key) || key.startsWith('run.')) params.delete(key)
  if (state.site) params.set('site', state.site)
  else { params.set('lat', String(state.location.latitude)); params.set('lon', String(state.location.longitude)) }
  if (state.instant !== null) params.set('t', new Date(state.instant).toISOString())
  params.set('view', state.view.toLowerCase())
  if (state.dock && state.dock !== state.view) params.set('dock', state.dock.toLowerCase())
  if (state.stack !== null) params.set('stack', JSON.stringify(state.stack))
  for (const [source, run] of Object.entries(state.runs)) params.set(`run.${source}`, run)
  return `?${params}`
}
