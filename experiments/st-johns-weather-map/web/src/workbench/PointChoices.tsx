import type { CatalogSource, PointFieldSelection } from '../types'
import { capabilityFor, pointLabel, variantIdentity } from './pointSelections'
import { variantLabel } from './sourceCapabilities'

export function PointChoices({ point, catalog, onChange }: { point: PointFieldSelection; catalog: CatalogSource[]; onChange: (point: PointFieldSelection) => void }) {
  const cap = capabilityFor(point, catalog)
  if (!cap) return <p>{pointLabel(point)} · Retained point capability unavailable.</p>
  return <fieldset className="point-choices"><legend>{pointLabel(point)}</legend>
    <label>Member / statistic<select aria-label={`Member or statistic for ${pointLabel(point)}`} value={point.variant ? variantIdentity(point.variant) : ''} onChange={e => onChange({...point, variant: cap.variants.find(v => variantIdentity(v) === e.target.value)})}>
      <option value="">Choose member or statistic…</option>
      {point.variant && !cap.variants.some(v => variantIdentity(v) === variantIdentity(point.variant)) && <option value={variantIdentity(point.variant)}>Retained choice unavailable</option>}
      {cap.variants.map(v => <option key={variantIdentity(v)} value={variantIdentity(v)}>{v.kind === 'member' && v.member === 'all' ? 'All members (existing default)' : variantLabel(v)}</option>)}
    </select></label>
    <label>Level<select aria-label={`Level for ${pointLabel(point)}`} value={point.level ?? ''} onChange={e => onChange({...point, level: e.target.value || undefined})}>
      <option value="">Choose level…</option>
      {point.level && !cap.levels.includes(point.level) && <option>{point.level}</option>}
      {cap.levels.map(level => <option key={level}>{level}</option>)}
    </select></label>
    <small>{cap.time_semantics}</small>
  </fieldset>
}
