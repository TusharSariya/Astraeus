import type { BlockedFieldEntry, OverrideProvenance, ProfileField, ProfileFile } from './types'

/** A minimal but complete profile fixture, shaped like the real running
 *  profile at `registry/profiles/running.yaml`: one threshold, one hard
 *  stop, one graded criterion, a window written in geometry fields, one
 *  blocked field and one wanted-not-catalogued entry. */
export function fixtureProfile(overrides: Partial<ProfileFile> = {}): ProfileFile {
  return {
    id: 'running',
    version: 1,
    title: 'Running',
    families: ['temperature', 'wind', 'lightning'],
    thresholds: {
      gust: { field: 'wind_gust_10m', default: 15.0, units: 'm s-1', comparison: 'ge' },
      lightning_in_range: { field: 'lightning_strike', default: 0.1, units: 'flash km-2 min-1', comparison: 'ge' },
    },
    weights: { wind: 0.5 },
    hard_stops: [
      { name: 'lightning', field: 'lightning_strike', threshold: 'lightning_in_range' },
    ],
    graded_criteria: [
      { name: 'gustiness', field: 'wind_gust_10m', threshold: 'gust', weight: 'wind' },
    ],
    window: {
      rule: 'any_window_within_24h',
      geometry_entry: 'de442_sun_moon_geometry',
      geometry_fields: ['sun_altitude'],
      params: { length_hours: 1.0, daylight_only: false },
    },
    site_needs: { horizon_required: false, sectors: [] },
    blocked_fields: [
      { field: 'road_state', reason: 'licence', source_id: 'nl-511', terms: 'The NL 511 site terms grant no reuse', request: null },
    ],
    wanted_not_catalogued: [
      { field: 'humidex', note: "the owner's list names humidex; the catalogue has no key for it" },
    ],
    ...overrides,
  }
}

const baseFieldContract = {
  evidence_class: 'retrieved',
  freshness: { status: 'fresh', age_seconds: 60, threshold_seconds: 3600 },
}

/** A field carrying a present value: no absence state, nothing to disclose. */
export function fixturePresentField(field = 'temperature_2m'): ProfileField {
  return {
    field,
    key: field,
    value: 12.4,
    ...baseFieldContract,
    quality: { status: 'ok', flags: [] },
    source_id: 'eccc-hrdps',
    comparability: 'air temperature at 2 m',
    absence_state: null,
    blocked: null,
  }
}

/** A field simply not retrieved this cycle: `null` with provenance. */
export function fixtureNullField(field = 'wind_gust_10m'): ProfileField {
  return {
    field,
    key: field,
    value: null,
    ...baseFieldContract,
    quality: { status: 'unavailable', flags: ['no_retrieval'] },
    source_id: 'eccc-hrdps',
    comparability: null,
    absence_state: 'null',
    blocked: null,
  }
}

/** A field refused for a licence, credential or partnership reason. */
export function fixtureBlockedField(field = 'road_state'): ProfileField {
  return {
    field,
    key: null,
    value: null,
    ...baseFieldContract,
    quality: { status: 'unavailable', flags: ['blocked', 'blocked:licence'] },
    source_id: 'nl-511',
    comparability: null,
    absence_state: 'blocked',
    blocked: { kind: 'licence', source_id: 'nl-511', terms: 'The NL 511 site terms grant no reuse', request: null },
  }
}

/** A field retrieved once and now outside the retention window, with its
 *  `absence_state` left unset - so the fallback to `resolveAbsenceState` must
 *  read it off the `aged_out` flag. */
export function fixtureAgedOutField(field = 'lightning_strike'): ProfileField {
  return {
    field,
    key: field,
    value: null,
    ...baseFieldContract,
    quality: { status: 'unavailable', flags: ['aged_out'] },
    source_id: 'eccc-hrdps',
    comparability: null,
    absence_state: null,
    blocked: null,
  }
}

export function fixtureBlockedEntry(field = 'road_state'): BlockedFieldEntry {
  return { field, reason: 'licence', source_id: 'nl-511', terms: 'The NL 511 site terms grant no reuse', request: null }
}

export function fixtureOverrideProvenance(overrides: Partial<OverrideProvenance> = {}): OverrideProvenance {
  return {
    profile_id: 'running',
    profile_version: 1,
    overrides: [],
    no_override_in_force: true,
    ...overrides,
  }
}
