import type { AstronomyResponse, ServedFieldValue, SpaceWeatherResponse, SpaceWeatherSeries } from '../types'
import { EvidenceGlyph, EvidenceLedger, evidenceKey, type InspectedEvidence } from './EvidenceInspector'
import type { RegisteredSite } from './registeredSites'
import type { CameraRegistry } from './registeredCameras'
interface Props {
  site: RegisteredSite | null; registryVersion: string | null; fields: ServedFieldValue[]
  astronomy: AstronomyResponse | null; astronomyNotice: string | null
  spaceWeather: SpaceWeatherResponse | null; spaceWeatherNotice: string | null
  cameras: CameraRegistry | null; cameraNotice: string | null
  onInspect: (value: InspectedEvidence, opener: HTMLButtonElement) => void
}
const shown = (value: unknown, units = '') => typeof value === 'number' && Number.isFinite(value) ? `${value} ${units}`.trim() : 'Unavailable'
export function SkyView(props: Props) {
  const { site, fields, spaceWeather, onInspect } = props
  const astronomy = props.astronomy?.provenance ? props.astronomy : null
  const allowed = (row: ServedFieldValue) => row.hasValue && row.attribution.evidenceClass !== 'unrecognised' && !row.attribution.derivationRefused && !row.attribution.provenanceUnmodelled && !row.attribution.uncatalogued
  const inspect = (key: string, label: string, value: string, details: Record<string, unknown>) => <button onClick={(event) => onInspect({ key: `sky:${key}`, label, text: value, details }, event.currentTarget)}>Inspect {label}</button>
  const cloudRows = [['cloud_low', 'Low cloud'], ['cloud_middle', 'Middle cloud'], ['cloud_high', 'High cloud']].flatMap<{ row: ServedFieldValue | null; label: string }>(([key, label]) => {
    const rows = fields.filter((row) => row.field === key)
    return rows.length ? rows.map((row) => ({ row, label })) : [{ row: null, label }]
  })
  return <div className="sky-instrument">
    <div><section className="sky-panel"><h3>Horizon · looking up</h3>
      <Horizon site={site} />
      <p>{site ? site.geometry_note ?? 'Registration basis not supplied' : 'No registered horizon at this point. A nearby site is not borrowed.'}</p>
      {site && <p>Terrain check: {site.horizon.terrain_check_status} · {site.horizon.terrain_check_note}</p>}
      {inspect('horizon', 'registered horizon', site?.name ?? 'No registered horizon', { 'Registry version': props.registryVersion, 'Registered site': site, 'Geometry scope': 'Registered horizon only; no directional cloud or celestial position is inferred' })}
      {site && <details><summary>Registered bearing and elevation samples</summary><table><caption>{site.name} registered horizon</caption><thead><tr><th scope="col">True bearing</th><th scope="col">Elevation</th></tr></thead><tbody>{site.horizon.elevation_deg.map((altitude, i) => <tr key={i}><th scope="row">{i * site.horizon.bearing_resolution_deg}°</th><td>{altitude}°</td></tr>)}</tbody></table></details>}
    </section>
    <section className="sky-panel"><h3>Scalar cloud layers</h3><div className="sky-clouds">{cloudRows.map(({ row, label }, index) => {
      const value = row && allowed(row) ? row.value : null
      const percent = row && ['%', 'percent'].includes(row.units ?? '') && value !== null && value >= 0 && value <= 100 ? value : null
      return <div className="sky-cloud-gauge" key={row ? evidenceKey(row) : `missing:${index}`}><h4>{label}</h4><svg viewBox="0 0 100 100" role="img" aria-label={`${label}: ${shown(value, row?.units ?? '')}; scalar gauge, not direction`}>
        <circle className="sky-gauge-track" cx="50" cy="50" r="35" />
        {percent !== null ? <circle className="sky-gauge-value" cx="50" cy="50" r="35" pathLength="100" strokeDasharray={`${percent} ${100 - percent}`} transform="rotate(-90 50 50)" /> : <path d="M35 50H65" stroke="currentColor" fill="none" />}
      </svg><p>{shown(value, row?.units ?? '')}</p><p><EvidenceGlyph kind={row?.attribution.evidenceClass ?? 'unrecognised'} />{row?.attribution.sourceId ?? 'Source not returned'}</p>
        {value !== null && percent === null && <p>No gauge scale for the returned unit</p>}
        {row ? <button onClick={(event) => onInspect({ key: evidenceKey(row), label: row.field, text: allowed(row) ? row.text : 'Unavailable', attribution: row.attribution }, event.currentTarget)}>Inspect {row.field} from {row.attribution.sourceId}</button> : <p>No layer fraction returned</p>}
      </div>
    })}</div><p>Rings are fraction gauges, not bearings or sky sectors. Layer fractions are not added together and do not establish seeing or transparency.</p>
      <details><summary>Cloud evidence and native absence reasons</summary><EvidenceLedger rows={fields.filter((row) => row.attribution.family === 'cloud_cover' || row.field.startsWith('cloud_'))} onInspect={onInspect} /></details>
    </section>
    <section className="sky-panel"><h3>Night geometry</h3><p>Server intervals use geometric reference horizons. No registered-horizon or weather correction is applied here.</p>
      {astronomy ? <>{[['Darkness', astronomy.twilight_bands.filter((band) => band.kind === 'night')], ['Moon above geometric horizon', astronomy.moon.above_horizon], ['Galactic core window', astronomy.milky_way_core.windows]].map(([label, intervals]) => <div key={String(label)}><h4>{String(label)}</h4><p>{Array.isArray(intervals) && intervals.length ? intervals.map((interval) => `${interval.start} → ${interval.end}`).join('; ') : 'No interval returned within the response window'}</p></div>)}
        <p>Response window: {astronomy.window_start} → {astronomy.window_end}</p>{inspect('windows', 'geometric windows', 'Returned geometry intervals', { astronomy })}</> : <p>Geometry unavailable: {props.astronomyNotice ?? 'No response'}. This is not an empty night window.</p>}
    </section></div>
    <div><section className="sky-panel"><h3>Geometry at Focus</h3>{astronomy?.notices.map((notice) => <p key={notice}>{notice}</p>)}<p>Azimuths are not supplied, so no Sun, Moon or core marker is placed against the site horizon.</p>
      <table><caption>Returned geometric altitudes and lunar geometry</caption><thead><tr><th scope="col">Class / quantity</th><th scope="col">Value</th><th scope="col">Provenance</th></tr></thead><tbody>
        {([['Sun altitude', astronomy?.sun_altitude_deg, '°'], ['Moon altitude', astronomy?.moon_altitude_deg, '°'], ['Galactic core altitude', astronomy?.core_altitude_deg, '°'], ['Moon phase angle', astronomy?.moon.phase_deg, '°'], ['Moon illuminated fraction', astronomy?.moon.illuminated_fraction, 'fraction']] as const).map(([label, value, units]) => <tr key={label}><th scope="row"><EvidenceGlyph kind={astronomy?.provenance ? 'derived_here' : 'unrecognised'} />{label}</th><td>{shown(value, units)}</td><td>{inspect(label, label, shown(value, units), { 'Returned astronomy provenance': astronomy?.provenance ?? null, 'Native valid time': astronomy?.valid_time ?? null, 'Value': value ?? null, Units: units, 'Response notices': astronomy?.notices ?? props.astronomyNotice })}</td></tr>)}
      </tbody></table>
    </section>
    <section className="sky-panel"><h3>Atmosphere and missing direction</h3><p>Cloud direction is not supplied. Returned seeing or transparency classes retain their source definitions; scalar readings do not fill directional positions.</p>
      <EvidenceLedger rows={fields.filter((row) => ['visibility', 'fog_state', 'aurora_probability', 'precipitable_water'].includes(row.field) || ['seeing', 'transparency'].includes(row.attribution.family ?? ''))} onInspect={onInspect} />
    </section>
    <section className="sky-panel"><h3>Camera eligibility</h3><p>Registration metadata only. Cameras are not associated with the Focus; registration does not establish sky coverage or horizon alignment. No camera images or image placement are provided.</p>
      {props.cameras ? <>{props.cameras.cameras.map((camera) => <div key={camera.id}><h4>{camera.name} · {camera.source_id}</h4><p>{camera.status} · Registration {camera.registration_complete ? 'complete' : 'incomplete'} · {camera.declared_retrieval_eligible ? 'Registry eligibility declared; image delivery unavailable' : `Retrieval ineligible: ${camera.refusal_code ?? 'reason not supplied'}`}</p><p>Position {camera.position_surveyed ? 'surveyed' : 'not surveyed'} · Geometry {camera.geometry_validation}</p>{inspect(`camera:${camera.id}`, `camera ${camera.name}`, camera.status, { 'Registry version': props.cameras?.version ?? null, 'Public camera record': camera })}</div>)}{props.cameras.notices.map((notice) => <p key={notice}>{notice}</p>)}</> : <p>Camera eligibility unknown: {props.cameraNotice ?? 'Registry not read'}</p>}
    </section>
    <KpContext series={spaceWeather?.kp_observed} label="Kp observed" onInspect={onInspect} /><KpContext series={spaceWeather?.kp_forecast} label="Kp outlook" onInspect={onInspect} />
    <section className="sky-panel"><h3>Solar wind · planetary context</h3><p>Solar-wind measurements and planetary indices are not a local aurora probability.</p>
      {spaceWeather ? <><p>{spaceWeather.solar_wind.source_id ?? 'Source not supplied'} · Measured {spaceWeather.solar_wind.measured_at ?? 'time not supplied'} · {spaceWeather.solar_wind.freshness.status}</p><p><EvidenceGlyph kind="unrecognised" />Class not supplied · Bz GSM: {shown(spaceWeather.solar_wind.available ? spaceWeather.solar_wind.bz_gsm_nt : null, 'nT')} · <EvidenceGlyph kind="unrecognised" />Bt: {shown(spaceWeather.solar_wind.available ? spaceWeather.solar_wind.bt_nt : null, 'nT')}</p>
        <p>{spaceWeather.solar_wind_plasma.source_id ?? 'Source not supplied'} · Measured {spaceWeather.solar_wind_plasma.measured_at ?? 'time not supplied'} · {spaceWeather.solar_wind_plasma.freshness.status}</p><p><EvidenceGlyph kind="unrecognised" />Class not supplied · Proton speed: {shown(spaceWeather.solar_wind_plasma.available ? spaceWeather.solar_wind_plasma.proton_speed_km_s : null, 'km/s')} · <EvidenceGlyph kind="unrecognised" />Density: {shown(spaceWeather.solar_wind_plasma.available ? spaceWeather.solar_wind_plasma.proton_density_cm3 : null, 'cm⁻³')} · <EvidenceGlyph kind="unrecognised" />Temperature: {shown(spaceWeather.solar_wind_plasma.available ? spaceWeather.solar_wind_plasma.proton_temperature_k : null, 'K')}</p>
        {inspect('solar-wind', 'solar wind evidence', 'Native planetary context; no local score', { 'Complete returned evidence': spaceWeather })}</> : <p>Space weather unavailable: {props.spaceWeatherNotice ?? 'No response'}</p>}
    </section></div>
  </div>
}
function Horizon({ site }: { site: RegisteredSite | null }) {
  const points = site?.horizon.elevation_deg.map((alt, index) => { const angle = index * site.horizon.bearing_resolution_deg * Math.PI / 180, radius = 145 * (90 - alt) / 90; return `${240 + radius * Math.sin(angle)},${175 - radius * Math.cos(angle)}` }).join(' ')
  return <svg className="sky-horizon" viewBox="0 0 480 350" role="img" aria-label={site ? `${site.name} registered horizon; no directional sky values` : 'Reference grid only; no registered horizon'}>
    <title>Sky reference grid; clockwise true bearings, zenith at centre</title>
    {[0, 30, 60].map((alt) => <g key={alt}><circle cx="240" cy="175" r={145 * (90 - alt) / 90} /><text x="246" y={189 - 145 * (90 - alt) / 90}>{alt}°</text></g>)}
    <path d="M95 175H385M240 30V320" />{points && <polygon className="sky-registered-horizon" points={points} />}
    <text x="240" y="20" textAnchor="middle">N · 000°</text><text x="407" y="180">E</text><text x="240" y="344" textAnchor="middle">S · 180°</text><text x="62" y="180">W</text>
    <rect className="sky-horizon-label" x="112" y="139" width="256" height="74" /><text x="240" y="166" textAnchor="middle">{site ? 'Registered horizon only' : 'Horizon unknown'}</text><text x="240" y="189" textAnchor="middle">Directional sky evidence absent</text><text x="240" y="207" textAnchor="middle">Not a cloud map</text>
  </svg>
}
function KpContext({ series, label, onInspect }: { series?: SpaceWeatherSeries; label: string; onInspect: Props['onInspect'] }) {
  return <section className="sky-panel"><h3>{label}</h3><p><EvidenceGlyph kind="unrecognised" />Class not supplied · {series?.source_id ?? 'Source not supplied'} · {series?.freshness.status ?? 'Freshness unknown'}</p><p>Native planetary index; provider status is retained separately from evidence class. No points are connected and no local probability is inferred.</p>
    {series?.available ? <table><caption>{label} at returned native timestamps</caption><thead><tr><th scope="col">Native UTC time</th><th scope="col">Kp</th><th scope="col">Provider status</th></tr></thead><tbody>{series.readings.map((reading, index) => <tr key={index}><th scope="row">{reading.time}</th><td><EvidenceGlyph kind="unrecognised" />{shown(reading.value)}</td><td>{reading.status ?? 'Not supplied'}</td></tr>)}</tbody></table> : <p>Unavailable: {series?.notices.join('; ') || 'No applicable native readings returned'}</p>}
    <button onClick={(event) => onInspect({ key: `sky:${label}`, label, text: 'Planetary context only', details: { 'Complete returned series': series ?? null } }, event.currentTarget)}>Inspect {label}</button>
  </section>
}
