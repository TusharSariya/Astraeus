/** Sites as preferred locations, never as a limit on where evidence is served.
 *
 *  These types mirror `api/weather_api/sites.py` (`SiteSummary`, `Horizon`,
 *  `NO_REGISTERED_HORIZON`, `EVIDENCE_BOX`) and the real site records at
 *  `registry/sites/*.yaml`. Nothing here ranks or recommends a site: the
 *  registry is a convenience list, and the evidence layer serves every
 *  catalogue field at any point inside the evidence box whether or not that
 *  point is a registered site.
 */

/** A site's hand-registered directional horizon and its terrain check.
 *
 *  `elevation_deg` runs from true north clockwise in steps of
 *  `bearing_resolution_deg`. The terrain check travels with the horizon
 *  because a check that was not run is a disclosure a reader is owed, not an
 *  absence to be quietly read as agreement. */
export interface SiteHorizon {
  site_id: string
  bearing_resolution_deg: number
  elevation_deg: number[]
  terrain_check_status: 'passed' | 'failed' | 'not_run'
  terrain_check_note: string
}

/** A servable site record as the client reads it. */
export interface Site {
  id: string
  name: string
  latitude: number
  longitude: number
  elevation_m: number | null
  datum: string
  horizon: SiteHorizon
  registered_on: string
  registered_by: string
}

/** The servable sites, and the notice for whatever was left out.
 *
 *  `notice` is `null` only when every file read cleanly and every record
 *  audited clean. It never turns into a refusal: an empty registry means
 *  every horizon-dependent field is `null` and nothing else changes. */
export interface SiteRegistry {
  sites: Site[]
  notice: string | null
}

/** The point a reader has selected: either a registered site (by id) or an
 *  arbitrary point in the evidence box. `site_id` is the only thing that
 *  distinguishes the two — the latitude and longitude of a custom point may
 *  happen to match a site's position without making it "the site". */
export interface PointSelection {
  latitude: number
  longitude: number
  site_id: string | null
}

/** One catalogue field that needs a registered horizon to answer, as served
 *  under the output contract. `absence_state` mirrors the wire's own carrier
 *  (`api/weather_api/models.py` `AbsenceState`): `null`, `blocked`,
 *  `aged_out`, or `null` (the TS type) when the response declared none. */
export interface HorizonDependentField {
  field: string
  value: unknown
  quality: { status: string; flags: string[] }
  absence_state: 'null' | 'blocked' | 'aged_out' | null
}

/** The flag a horizon-dependent field carries when it is requested at a point
 *  with no registered horizon. Mirrors
 *  `api.weather_api.sites.NO_REGISTERED_HORIZON`. */
export const NO_REGISTERED_HORIZON = 'no_registered_horizon'

/** The area evidence is served over, as the deployment's four bounds in
 *  degrees. Mirrors `api.weather_api.sites.EVIDENCE_BOX`, restated here
 *  rather than imported because this is a separately deployed client. */
export const EVIDENCE_BOX = { south: 45.0, north: 50.5, west: -58.0, east: -46.0 } as const

/** Whether a point is one the deployment serves evidence over. Bounds are
 *  inclusive: a point exactly on an edge is inside, because a reader standing
 *  on the boundary is not standing anywhere else. */
export function insideEvidenceBox(lat: number, lon: number): boolean {
  return lat >= EVIDENCE_BOX.south && lat <= EVIDENCE_BOX.north && lon >= EVIDENCE_BOX.west && lon <= EVIDENCE_BOX.east
}
