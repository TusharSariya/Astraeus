import { resolveProfileAbsence, type ProfileField, type ProfileFile, type OverrideProvenance } from './types'

/** The words shown for a profile field's absence, distinct in text (not only
 *  colour) so a screen reader and a colour-blind reader both get three
 *  different claims:
 *  - `null`: not retrieved this cycle, with provenance.
 *  - `blocked`: refused for a stated reason - never presented as `null`.
 *  - `aged_out`: retrieved once, now outside the retention window. */
const PROFILE_ABSENCE_LABELS: Record<'null' | 'blocked' | 'aged_out', string> = {
  null: 'No value',
  blocked: 'Blocked',
  aged_out: 'Aged out',
}

/** One field's value or its absence rendering. Renders exactly one of: the
 *  value, or one of the three distinguishable absence states, each carrying
 *  its own `data-absence` attribute and its own visible label. A blocked
 *  field additionally states its reason, source and terms - it is never
 *  rendered as an unexplained gap. */
function ProfileFieldRow({ field }: { field: ProfileField }) {
  const absence = resolveProfileAbsence(field)
  if (absence === null) {
    return (
      <li className="profile-field profile-field-present" data-field={field.field}>
        <span className="profile-field-name">{field.field}</span>
        <span className="profile-field-value">{String(field.value)}</span>
      </li>
    )
  }

  const label = PROFILE_ABSENCE_LABELS[absence]

  return (
    <li className="profile-field profile-field-absent" data-field={field.field} data-absence={absence}>
      <span className="profile-field-name">{field.field}</span>
      <span className="profile-field-absence-label" data-absence={absence}>{label}</span>
      {field.blocked && (
        <span className="profile-field-blocked-reason">
          reason: {field.blocked.kind}; source: {field.blocked.source_id}; terms: {field.blocked.terms}
          {field.blocked.request ? `; request: ${field.blocked.request}` : ''}
        </span>
      )}
    </li>
  )
}

/** A profile's families, thresholds with any override, hard stops separated
 *  from graded criteria, its window and its blocked fields with reasons - the
 *  read side of the output contract in "Absence states and the per-field
 *  output contract" and the profile file shape in "Profile files". This
 *  component computes nothing: no score, no ranking, no recommendation - it
 *  is a rendering of what the evidence layer already answered. */
export function ProfilePanel({ profile, fields, overrides }: { profile: ProfileFile; fields: ProfileField[]; overrides: OverrideProvenance }) {
  const overrideByThreshold = new Map(overrides.overrides.map((entry) => [entry.threshold, entry]))

  return (
    <section aria-label={`${profile.title} profile`} className="profile-panel">
      <header>
        <h2>{profile.title}</h2>
        <p className="profile-version">id: {profile.id}; version: {profile.version}</p>
      </header>

      <section aria-label="Families">
        <h3>Families</h3>
        <ul>
          {profile.families.map((family) => (
            <li key={family}>{family}</li>
          ))}
        </ul>
      </section>

      <section aria-label="Thresholds">
        <h3>Thresholds</h3>
        <ul>
          {Object.entries(profile.thresholds).map(([name, threshold]) => {
            const override = overrideByThreshold.get(name)
            return (
              <li key={name} data-threshold={name}>
                <span className="threshold-name">{name}</span>
                <span className="threshold-field">{threshold.field}</span>
                <span className="threshold-comparison">{threshold.comparison}</span>
                <span className="threshold-default">default: {threshold.default} {threshold.units}</span>
                {override && (
                  <span className="threshold-override" data-override="true">
                    override: {override.value} {threshold.units} (default {override.profile_default} {threshold.units})
                  </span>
                )}
              </li>
            )
          })}
        </ul>
        {overrides.no_override_in_force && (
          <p className="threshold-no-override">No threshold was overridden.</p>
        )}
      </section>

      <section aria-label="Hard stops">
        <h3>Hard stops</h3>
        <ul>
          {profile.hard_stops.map((stop) => (
            <li key={stop.name} data-hard-stop={stop.name}>
              {stop.name}: {stop.field} vs. {stop.threshold}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Graded criteria">
        <h3>Graded criteria</h3>
        <ul>
          {profile.graded_criteria.map((criterion) => (
            <li key={criterion.name} data-graded-criterion={criterion.name}>
              {criterion.name}: {criterion.field} vs. {criterion.threshold}, weight {criterion.weight}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Window">
        <h3>Window</h3>
        <p>
          rule: {profile.window.rule}; geometry entry: {profile.window.geometry_entry}; geometry fields: {profile.window.geometry_fields.join(', ')}
        </p>
      </section>

      <section aria-label="Fields">
        <h3>Fields</h3>
        <ul>
          {fields.map((field) => (
            <ProfileFieldRow key={field.field} field={field} />
          ))}
        </ul>
      </section>

      <section aria-label="Blocked fields">
        <h3>Blocked fields</h3>
        <ul>
          {profile.blocked_fields.map((entry) => (
            <li key={entry.field} data-blocked-field={entry.field}>
              {entry.field}: reason {entry.reason}; source {entry.source_id}; terms {entry.terms}
              {entry.request ? `; request ${entry.request}` : ''}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Wanted but not catalogued">
        <h3>Wanted, not in the catalogue</h3>
        <ul>
          {profile.wanted_not_catalogued.map((entry) => (
            <li key={entry.field} data-wanted-not-catalogued={entry.field}>
              {entry.field} - not in the catalogue: {entry.note}
            </li>
          ))}
        </ul>
      </section>
    </section>
  )
}
