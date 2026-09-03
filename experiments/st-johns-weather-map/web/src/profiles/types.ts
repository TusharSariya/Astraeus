import { resolveAbsenceState } from '../fieldFamily'

/** Types for task 6.1: rendering an activity profile and the per-field output
 *  contract the evidence layer answers it with.
 *
 *  `ProfileFile` mirrors the registry file shape pinned in the design's
 *  "Profile files" seam (`registry/profiles/<id>.yaml`, validated by
 *  `registry/profiles/schema.json`) - see `registry/profiles/running.yaml` for
 *  a served example. `ProfileField` mirrors the per-field output contract
 *  pinned in "Absence states and the per-field output contract": every field
 *  the evidence layer returns to a profile carries value-or-absence-state,
 *  evidence class, quality, freshness, source and comparability, and nothing
 *  is ever omitted. This module renders that contract; it computes nothing
 *  and scores nothing. */

/** A named threshold: the profile's default and the units/comparison it is
 *  read under. `default` is required by the schema - a threshold with no
 *  default fails validation before this ever runs. */
export interface ProfileThreshold {
  field: string
  default: number
  units: string
  comparison: 'ge' | 'gt' | 'le' | 'lt'
}

/** A hard stop answers on its own, without reference to any weight - kept in
 *  its own list, never merged with graded criteria. */
export interface HardStop {
  name: string
  field: string
  threshold: string
}

/** A graded criterion carries a weight (a key into `ProfileFile.weights`) and
 *  is evaluated only when no hard stop is in force. */
export interface GradedCriterion {
  name: string
  field: string
  threshold: string
  weight: string
}

/** The window rule, written only in the derived-here Sun/Moon geometry fields
 *  of the pinned DE442 entry - never in wall-clock offsets. */
export interface ProfileWindow {
  rule: 'any_window_within_24h' | 'astronomical_night' | 'dark_hours' | 'sunrise_sunset_margin'
  geometry_entry: string
  geometry_fields: string[]
  params: Record<string, unknown>
}

/** A sector is a parameter set of the registered sector-sampling entry
 *  `sector_sampling_along_bearing`. */
export interface SiteSector {
  name: string
  field: string
  bearing_deg: number
  width_deg: number
  max_range_km: number
}

export interface SiteNeeds {
  horizon_required: boolean
  sectors: SiteSector[]
}

/** A field the profile would read that no admitted source can supply. Listed
 *  explicitly rather than silently omitted; never contributes to a hard stop
 *  or a weight. */
export interface BlockedFieldEntry {
  field: string
  reason: 'licence' | 'credential' | 'partnership'
  source_id: string
  terms: string
  request: string | null
}

/** A quantity the owner's list names that the field catalogue does not yet
 *  carry - disclosed, rather than dropped. */
export interface WantedNotCatalogued {
  field: string
  note: string
}

/** One profile file, as validated by `registry/profiles/schema.json`. */
export interface ProfileFile {
  id: string
  version: number
  title: string
  families: string[]
  thresholds: Record<string, ProfileThreshold>
  weights: Record<string, number>
  hard_stops: HardStop[]
  graded_criteria: GradedCriterion[]
  window: ProfileWindow
  site_needs: SiteNeeds
  blocked_fields: BlockedFieldEntry[]
  wanted_not_catalogued: WantedNotCatalogued[]
}

/** One threshold a reader raised or lowered from the profile's default. */
export interface ThresholdOverride {
  threshold: string
  profile_default: number
  value: number
}

/** Provenance for the overrides in force on a score: names the threshold,
 *  the profile default and the override value, or states explicitly that no
 *  threshold was overridden. Never omitted in favour of silence. */
export interface OverrideProvenance {
  profile_id: string
  profile_version: number
  overrides: ThresholdOverride[]
  no_override_in_force: boolean
}

/** The three disjoint absence states a profile field's contract can carry.
 *  Distinct from the four-state `AbsenceState` in `../fieldFamily`, which
 *  additionally names `retrieval_failed` as a reason flag under `null` - the
 *  profile output contract collapses that flag into `null` and keeps only
 *  the three the spec names as disjoint states. */
export type ProfileAbsenceState = 'null' | 'blocked' | 'aged_out'

/** Why a field is `blocked`: the reason kind, the source it would come from,
 *  the terms or notice, and any outstanding request. */
export interface BlockedReason {
  kind: 'licence' | 'credential' | 'partnership'
  source_id: string
  terms: string
  request: string | null
}

/** The per-field output contract: value, evidence class, quality, freshness,
 *  source and comparability, with no element ever omitted. A present value
 *  carries no absence state; an absent one carries exactly one of the three
 *  and, when blocked, the `blocked` reason object. */
export interface ProfileField {
  field: string
  key: string | null
  value: unknown
  evidence_class: string
  quality: { status: string; flags: string[] }
  freshness: { status: string; age_seconds: number | null; threshold_seconds: number | null }
  source_id: string | null
  comparability: string | null
  absence_state: ProfileAbsenceState | null
  blocked: BlockedReason | null
}

/** The absence state a profile field renders under, reading `absence_state`
 *  first and falling back to `resolveAbsenceState` from `../fieldFamily` (the
 *  same flag-priority reader the rest of this interface uses) when it is
 *  unset. A present value always yields `null`: a field carrying a value has
 *  nothing to disclose here, whatever a stray flag might otherwise suggest.
 *
 *  The fallback's four-state vocabulary is narrowed to this contract's three:
 *  `retrieval_failed` is, per the design's absence-state rule, a reason flag
 *  riding on a `"null"` absence rather than a fourth disjoint state, so it
 *  folds into `null` here rather than being surfaced as its own rendering. */
export function resolveProfileAbsence(field: ProfileField): ProfileAbsenceState | null {
  if (field.value !== null && field.value !== undefined) return null
  if (field.absence_state) return field.absence_state
  const fallback = resolveAbsenceState(undefined, field.quality.flags)
  if (fallback === 'aged_out' || fallback === 'blocked') return fallback
  return 'null'
}
