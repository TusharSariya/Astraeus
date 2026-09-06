import { useState } from 'react'
import { EVIDENCE_BOX, insideEvidenceBox, NO_REGISTERED_HORIZON, type HorizonDependentField, type PointSelection, type Site, type SiteRegistry } from './types'

const BEARING_STEP_FALLBACK = 10

/** The compact horizon summary a site row shows: the shallowest and steepest
 *  registered elevation angle, and the bearing the steepest one sits at. It
 *  is a summary, not the full array — a reader who wants every bearing has
 *  the source record; this is what fits in a row. */
function horizonSummary(site: Site): string {
  const angles = site.horizon.elevation_deg
  if (!angles.length) return 'no horizon registered'
  const step = site.horizon.bearing_resolution_deg || BEARING_STEP_FALLBACK
  let minAngle = angles[0]
  let maxAngle = angles[0]
  let maxIndex = 0
  for (let i = 0; i < angles.length; i++) {
    const angle = angles[i]
    if (angle < minAngle) minAngle = angle
    if (angle > maxAngle) { maxAngle = angle; maxIndex = i }
  }
  const maxBearing = (maxIndex * step) % 360
  return `horizon ${minAngle.toFixed(1)}° to ${maxAngle.toFixed(1)}°, highest at ${maxBearing}°`
}

function formatBox(): string {
  const { south, north, west, east } = EVIDENCE_BOX
  return `latitude ${south} to ${north}, longitude ${west} to ${east}`
}

function SiteRow({ site, selected, onSelect }: { site: Site; selected: boolean; onSelect: (selection: PointSelection) => void }) {
  const check = site.horizon.terrain_check_status
  return (
    <li className="site-row" data-site-id={site.id} data-selected={selected}>
      <button
        type="button"
        className="site-select-button"
        onClick={() => onSelect({ latitude: site.latitude, longitude: site.longitude, site_id: site.id })}
      >
        {site.name}
      </button>
      <p className="site-elevation">
        {site.elevation_m === null ? 'elevation not registered' : `${site.elevation_m} m (${site.datum})`}
      </p>
      <p className="site-horizon-summary">{horizonSummary(site)}</p>
      <p className="site-terrain-check" data-terrain-check-status={check}>
        terrain check: {check}
        {check === 'not_run' && <span className="site-terrain-check-note"> — {site.horizon.terrain_check_note}</span>}
      </p>
    </li>
  )
}

function CustomPointControl({ onSelect }: { onSelect: (selection: PointSelection) => void }) {
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [refusal, setRefusal] = useState<string | null>(null)

  function useThisPoint() {
    const lat = Number(latitude)
    const lon = Number(longitude)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setRefusal('Enter a latitude and longitude to use a custom point.')
      return
    }
    if (!insideEvidenceBox(lat, lon)) {
      setRefusal(`${lat}, ${lon} lies outside the evidence box (${formatBox()}); no value is extrapolated to it.`)
      return
    }
    setRefusal(null)
    onSelect({ latitude: lat, longitude: lon, site_id: null })
  }

  return (
    <div className="site-custom-point">
      <label className="site-custom-point-field">
        Latitude
        <input
          type="number"
          value={latitude}
          onChange={(event) => setLatitude(event.target.value)}
          aria-label="Custom point latitude"
        />
      </label>
      <label className="site-custom-point-field">
        Longitude
        <input
          type="number"
          value={longitude}
          onChange={(event) => setLongitude(event.target.value)}
          aria-label="Custom point longitude"
        />
      </label>
      <button type="button" onClick={useThisPoint}>Use this point</button>
      {refusal && <p className="site-custom-point-refusal" role="alert">{refusal}</p>}
    </div>
  )
}

function HorizonDependentRow({ field }: { field: HorizonDependentField }) {
  return (
    <li className="site-horizon-dependent-field" data-field={field.field}>
      <code>{field.field}</code> is unavailable off-site: no horizon is registered here
      ({NO_REGISTERED_HORIZON}), and no nearby site's horizon is borrowed for it.
    </li>
  )
}

export interface SitePanelProps {
  registry: SiteRegistry
  selection: PointSelection
  onSelect: (selection: PointSelection) => void
  horizonFields: HorizonDependentField[]
}

/** Sites shown as preferred locations with their horizons. Selecting a site
 *  or a custom point are the same action from this panel's point of view —
 *  neither is ranked, recommended, or chosen for the reader. A horizon is a
 *  property of one registered position; nothing here offers a substitute
 *  horizon for an unregistered point. */
export function SitePanel({ registry, selection, onSelect, horizonFields }: SitePanelProps) {
  const blockedFields = horizonFields.filter((field) => field.quality.flags.includes(NO_REGISTERED_HORIZON))

  return (
    <section className="site-panel" aria-label="Sites">
      <h2 className="site-panel-heading">
        Registered sites are preferred locations with a known horizon, never a limit on where evidence can be
        served — any point in the evidence box can be selected below.
      </h2>
      {registry.notice && <p className="site-registry-notice" role="status">{registry.notice}</p>}
      <ul className="site-list">
        {registry.sites.map((site) => (
          <SiteRow key={site.id} site={site} selected={selection.site_id === site.id} onSelect={onSelect} />
        ))}
      </ul>
      <CustomPointControl onSelect={onSelect} />
      {blockedFields.length > 0 && (
        <ul className="site-horizon-dependent-fields">
          {blockedFields.map((field) => (
            <HorizonDependentRow key={field.field} field={field} />
          ))}
        </ul>
      )}
    </section>
  )
}
