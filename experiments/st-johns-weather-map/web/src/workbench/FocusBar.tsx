import type { RegisteredSites, RegisteredSite } from './registeredSites'
import { useEffect, useId, useState, type ReactNode } from 'react'
import type { LocationPoint } from '../types'

export function FocusBar({ location, site, instant, liveNow, onPoint, onInstant, onNow, registry, registryError, nearest, onSite, children }: {
  registry: RegisteredSites | null; registryError: string; nearest: { site: RegisteredSite; distanceKm: number } | null; onSite: (id: string) => void
  location: LocationPoint; site: string | null; instant: number; liveNow: boolean
  onPoint: (point: LocationPoint) => void; onInstant: (instant: number) => void; onNow: () => void; children: ReactNode
}) {
  const id = useId()
  const [lat, setLat] = useState(String(location.latitude)); const [lon, setLon] = useState(String(location.longitude))
  const [time, setTime] = useState(new Date(instant).toISOString())
  const [error, setError] = useState('')
  useEffect(() => { setLat(String(location.latitude)); setLon(String(location.longitude)) }, [location])
  useEffect(() => setTime(new Date(instant).toISOString()), [instant])
  return <>
    <div className="bench-brand"><h1>Avalon</h1><span>Evidence Bench</span><small>Experimental · not operational</small></div>
    <details className="bench-place"><summary>Focus · {site ?? location.name} <code>{location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}</code></summary>
      <p>{site ? registry?.sites.find((entry) => entry.id === site)?.geometry_note ?? `Registered site ${site}: geometry unavailable.` : 'No registered horizon at this point.'}</p>
      {registryError && <p>{registryError}</p>}
      {!site && nearest && <p>Nearest registered site: {nearest.site.name}, {nearest.distanceKm.toFixed(2)} km. Reference only; its horizon is not borrowed. <button onClick={() => onSite(nearest.site.id)}>Use {nearest.site.name} as Focus</button></p>}
      <label htmlFor={`${id}-site`}>Registered site</label><select id={`${id}-site`} value={site ?? ''} onChange={(e) => { if (e.target.value) onSite(e.target.value) }}><option value="">Choose a registered site…</option>{registry?.sites.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}</select>
      {registry && <small>Registry version {registry.version.slice(0, 12)}</small>}
      <form onSubmit={(event) => {
        event.preventDefault(); const latitude = Number(lat); const longitude = Number(lon)
        if (!lat.trim() || !lon.trim() || !Number.isFinite(latitude) || Math.abs(latitude) > 90 || !Number.isFinite(longitude) || Math.abs(longitude) > 180) { setError('Enter valid latitude and longitude.'); return }
        setError(''); onPoint({ id: 'point', name: 'Selected point', latitude, longitude, kind: 'map' })
      }}>
        <label htmlFor={`${id}-lat`}>Latitude</label><input id={`${id}-lat`} inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} />
        <label htmlFor={`${id}-lon`}>Longitude</label><input id={`${id}-lon`} inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} />
        <button>Use point</button>
      </form>
    </details>
    <details className="bench-instant"><summary>{liveNow ? 'Session Now' : 'Fixed instant'} · <time>{new Date(instant).toISOString()}</time></summary>
      <form onSubmit={(event) => { event.preventDefault(); const value = Date.parse(time); if (!Number.isFinite(value) || !/(Z|[+-]\d\d:\d\d)$/.test(time)) { setError('Use an ISO instant with a timezone.'); return }; setError(''); onInstant(value) }}>
        <label htmlFor={`${id}-time`}>Instant (ISO, with timezone)</label><input id={`${id}-time`} value={time} onChange={(e) => setTime(e.target.value)} /><button>Use instant</button>
      </form><button onClick={onNow}>Use session Now</button>
    </details>
    {children}
    {error && <p role="alert">{error}</p>}
  </>
}
