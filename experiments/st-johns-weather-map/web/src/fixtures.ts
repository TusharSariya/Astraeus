import type { EvidenceSnapshot, LocationPoint, SourceStatusItem, StationCoverage } from './types'

/** A location picker, not a coverage claim. These three coordinates are written
 *  here rather than returned by the API, so a pin appears whether or not any
 *  source has ever retrieved anything for that place. `sourceIds` names the
 *  registry records whose *declared* coverage names the station, and only those:
 *  `eccc-swob` ingests an Avalon bounding box, but a bounding box containing a
 *  headland is not evidence that a station on the headland reports, so Cape
 *  Spear claims nothing. `/sources/status` decides the rest. */
export const stations: LocationPoint[] = [
  { id: 'cyyt', name: 'CYYT / St. John’s', latitude: 47.6186, longitude: -52.7519, kind: 'airport', sourceIds: ['awc-metar-speci', 'awc-taf'] },
  { id: 'sma-sj', name: 'SmartAtlantic St. John’s', latitude: 47.304, longitude: -52.586, kind: 'buoy', sourceIds: ['smartatlantic-st-johns'] },
  { id: 'cape-spear', name: 'Cape Spear', latitude: 47.523, longitude: -52.622, kind: 'station', sourceIds: [] },
]

/** Whether a live ingested source stands behind one picker entry.
 *
 *  Four states, kept distinct on purpose. "We could not read the status
 *  endpoint" is not "nothing is live", and "no source claims this place" is not
 *  "a source claims it but has retrieved nothing" — collapsing any pair of them
 *  would let a marker imply coverage that was never established. */
export function stationCoverage(point: LocationPoint, statuses: SourceStatusItem[] | null): StationCoverage {
  const declared = point.sourceIds ?? []
  if (point.kind === 'map') {
    return {
      state: 'no-source',
      short: 'not a station',
      detail: `${point.name} is a coordinate you chose, not a station. No ingested source observes it; any values shown come from the point request for those coordinates.`,
    }
  }
  if (declared.length === 0) {
    return {
      state: 'no-source',
      short: 'no ingested source',
      detail: `${point.name}: no registry source declares coverage of this place, so nothing has been ingested for it. It is offered as a location to query, not as an observing station.`,
    }
  }
  if (statuses === null) {
    return {
      state: 'unknown',
      short: 'coverage unknown',
      detail: `${point.name}: source status could not be read, so whether ${declared.join(' or ')} has retrieved anything is unknown. It is not being treated as live.`,
    }
  }
  const rows = declared.map((id) => statuses.find((status) => status.source_id === id) ?? null)
  const live = rows.filter((row): row is SourceStatusItem => row?.data_mode === 'live')
  if (live.length > 0) {
    const newest = live.map((row) => row.last_retrieval).filter((value): value is string => Boolean(value)).sort().at(-1)
    return {
      state: 'live',
      short: 'live source',
      detail: `${point.name}: live ingested source ${live.map((row) => row.source_id).join(', ')}${newest ? `, last retrieval ${newest}` : ', no retrieval timestamp reported'}.`,
    }
  }
  const missing = declared.filter((id) => !statuses.some((status) => status.source_id === id))
  return {
    state: 'declared-not-live',
    short: 'no live retrieval',
    detail: `${point.name}: ${declared.join(', ')} ${declared.length === 1 ? 'is' : 'are'} catalogued but ${missing.length === declared.length ? 'absent from the status response' : 'reported no live retrieval'}. Nothing has been ingested for this station.`,
  }
}

/** Reachable only under the explicit development escape hatch
 *  (`import.meta.env.DEV && VITE_WEATHER_FIXTURES === 'true'`). Every value here
 *  is invented, which is why it is stamped `fixture` field by field and why the
 *  interface watermarks the whole screen when it is in use. */
export const fixtureSnapshot: EvidenceSnapshot = {
  mode: 'consensus',
  selectionBadge: 'Development fixture',
  selectedProductId: null,
  selectedSourceId: null,
  dataMode: 'fixture',
  fieldSources: {},
  fieldModes: {
    temperature: 'fixture', dew_point: 'fixture', relative_humidity: 'fixture',
    wind_speed: 'fixture', wind_gust: 'fixture', visibility: 'fixture',
    cloud_low: 'fixture', cloud_middle: 'fixture', cloud_high: 'fixture',
    aqhi: 'fixture', wave_height: 'fixture', sea_surface_temperature: 'fixture',
  },
  issuedAt: '2026-08-29T12:30:00Z',
  validAt: '2026-08-29T13:00:00Z',
  temperatureC: 14.2,
  dewPointC: 12.6,
  relativeHumidityPct: 90,
  windKmh: 31,
  windDirectionDeg: 240,
  gustKmh: 46,
  precipitation: 'Drizzle ending; 35% next 3 h',
  precipitationProbabilityPct: 35,
  cloud: { low: 92, middle: 48, high: 16 },
  totalCloudPct: 95,
  cloudLayers: [],
  pressureHpa: 1009.4,
  visibilityKm: 5.8,
  fogRisk: 'evidence_present',
  aqhi: 2,
  upperAir: { jet200Kmh: 145, jet300Kmh: 122, precipitableWaterKgM2: 14.2 },
  marine: { waveHeightM: 2.3, sstC: 11.8, tide: 'Rising · high 17:42 NDT' },
  warnings: ['Marine wind warning · Avalon waters'],
  story: [
    { time: 'Now', offset: 0, label: 'Low cloud · drizzle', dataMode: 'fixture', temperatureC: 14, dewPointC: 13, precipPct: 35, windKmh: 31 },
    { time: '+3h', offset: 3, label: 'Cloud lifting', dataMode: 'fixture', temperatureC: 15, dewPointC: 13, precipPct: 20, windKmh: 28 },
    { time: '+6h', offset: 6, label: 'Broken low cloud', dataMode: 'fixture', temperatureC: 16, dewPointC: 13, precipPct: 15, windKmh: 22 },
    { time: '+12h', offset: 12, label: 'Cloud returns', dataMode: 'fixture', temperatureC: 12, dewPointC: 11, precipPct: 25, windKmh: 18 },
    { time: '+18h', offset: 18, label: 'Patchy fog', dataMode: 'fixture', temperatureC: 11, dewPointC: 11, precipPct: 20, windKmh: 12 },
    { time: '+24h', offset: 24, label: 'Fog risk elevated', dataMode: 'fixture', temperatureC: 13, dewPointC: 12, precipPct: 30, windKmh: 17 },
  ],
  provenance: [
    { provider: 'ECCC', product: 'HRDPS', run: '2026-08-29 06Z', role: 'Regional guidance', freshness: 'Fresh · 38 min', member: null, level: '2 m above ground', dataMode: 'fixture', derivations: [] },
    { provider: 'ECCC', product: 'REPS', run: '2026-08-29 06Z', role: 'Ensemble family', freshness: 'Fresh · 1 h', member: 'control', level: '2 m above ground', dataMode: 'fixture', derivations: [] },
  ],
}

export const unavailableSnapshot: EvidenceSnapshot = {
  mode: 'unavailable', selectionBadge: null, selectedProductId: null, selectedSourceId: null,
  dataMode: 'unavailable', fieldModes: {}, fieldSources: {}, issuedAt: '', validAt: null,
  temperatureC: null, dewPointC: null, relativeHumidityPct: null,
  windKmh: null, windDirectionDeg: null, gustKmh: null,
  precipitation: 'Unavailable', precipitationProbabilityPct: null,
  cloud: { low: null, middle: null, high: null }, totalCloudPct: null, cloudLayers: [], pressureHpa: null,
  visibilityKm: null, fogRisk: 'unknown', aqhi: null,
  upperAir: { jet200Kmh: null, jet300Kmh: null, precipitableWaterKgM2: null },
  marine: { waveHeightM: null, sstC: null, tide: 'Unavailable' },
  warnings: [], story: [], provenance: [],
}
