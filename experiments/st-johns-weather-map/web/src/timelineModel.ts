/** Presentation geometry and navigation; never an inventory or a frame resolver. */
import type { FrameMarker } from './api'
import type { ScaleMark } from './scrubberAxis'

export const TIME_RANGES = [
  { id: 'near', label: 'Near term · −1h / +6h', back: 60, forward: 360, tick: 60 },
  { id: 'day', label: 'Day · −6h / +24h', back: 360, forward: 1440, tick: 180 },
  { id: 'outlook', label: 'Outlook · −24h / +14d', back: 1440, forward: 20160, tick: 1440 },
] as const
export type TimeRange = typeof TIME_RANGES[number]['id']
export function containingRange(selectedMs: number, referenceMs: number): TimeRange {
  const offset = (selectedMs - referenceMs) / 60_000
  return TIME_RANGES.find(range => offset >= -range.back && offset <= range.forward)?.id ?? 'outlook'
}
export function displayWindow(range: TimeRange, referenceMs: number, start: number, end: number) {
  const preset = TIME_RANGES.find(item => item.id === range) ?? TIME_RANGES[0]
  return { start: Math.max(start, referenceMs - preset.back * 60_000), end: Math.min(end, referenceMs + preset.forward * 60_000) }
}
export function frameNeighbour(instants: number[], selectedMs: number, direction: 1 | -1): number | null {
  return direction === 1 ? instants.find(time => time > selectedMs) ?? null : [...instants].reverse().find(time => time < selectedMs) ?? null
}
const localClock = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/St_Johns', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short' })
export function frameTime(ms: number): string { return localClock.format(ms) }
export function markerDescription(marker: FrameMarker): string {
  return `${frameTime(marker.ms)} · UTC ${new Date(marker.ms).toISOString()} · ${marker.layers.map(layer => `${layer.title} · ${layer.runTime ? `run ${layer.runTime}` : 'run unknown'}`).join('; ')}`
}
export function rangeMarks(range: TimeRange, start: number, end: number, reference: number): ScaleMark[] {
  const preset = TIME_RANGES.find(item => item.id === range) ?? TIME_RANGES[0]
  const times = new Set([start, end, reference])
  for (let time = reference; time <= end; time += preset.tick * 60_000) times.add(time)
  for (let time = reference; time >= start; time -= preset.tick * 60_000) times.add(time)
  return [...times].filter(time => time >= start && time <= end).sort((a,b) => a-b).map(time => {
    const hours = (time - reference) / 3_600_000
    const label = time === reference ? 'Now' : new Intl.DateTimeFormat('en-CA', { timeZone: 'America/St_Johns', month: 'short', day: 'numeric', ...(range !== 'outlook' ? { hour: '2-digit', minute: '2-digit' } : {}) }).format(time)
    return { hours, label, short: time === reference ? 'Now' : range === 'outlook' ? `${hours < 0 ? '-24h' : `+${Math.round(hours/24)}d`}` : `${hours > 0 ? '+' : ''}${Number(hours.toFixed(1))}h` }
  })
}
export interface MarkerCluster { fraction: number; markers: FrameMarker[] }
/** Bound hit-target overlap without dropping any exact timestamp. */
export function clusterMarkers(markers: FrameMarker[], start: number, end: number, width: number): MarkerCluster[] {
  const clusters: MarkerCluster[] = []
  if (!(end > start)) return clusters
  for (const marker of markers) {
    if (marker.ms < start || marker.ms > end) continue
    const fraction = (marker.ms - start) / (end - start)
    const previous = clusters.at(-1)
    if (previous && (fraction - previous.fraction) * Math.max(1, width) < 26) previous.markers.push(marker)
    else clusters.push({ fraction, markers: [marker] })
  }
  return clusters
}
