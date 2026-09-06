import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProfilePanel } from './ProfilePanel'
import { resolveProfileAbsence } from './types'
import {
  fixtureAgedOutField,
  fixtureBlockedField,
  fixtureNullField,
  fixtureOverrideProvenance,
  fixturePresentField,
  fixtureProfile,
} from './fixtures'

describe('the three absence states render distinguishably', () => {
  it('gives three fixture fields three different data-absence values and three different labels', () => {
    const profile = fixtureProfile()
    const fields = [fixtureBlockedField(), fixtureNullField(), fixtureAgedOutField()]
    render(<ProfilePanel profile={profile} fields={fields} overrides={fixtureOverrideProvenance()} />)

    const list = screen.getByRole('region', { name: 'Fields' })
    const nodes = [...list.querySelectorAll('li[data-absence]')]
    const values = nodes.map((node) => node.getAttribute('data-absence'))
    expect(new Set(values)).toEqual(new Set(['blocked', 'null', 'aged_out']))
    expect(values).toHaveLength(3)

    const labels = nodes.map((node) => node.querySelector('.profile-field-absence-label')?.textContent)
    expect(new Set(labels).size).toBe(3)
  })

  it('resolves aged_out from the flag when absence_state is unset', () => {
    const field = fixtureAgedOutField()
    expect(field.absence_state).toBeNull()
    expect(field.quality.flags).toContain('aged_out')
    expect(resolveProfileAbsence(field)).toBe('aged_out')
  })

  it('shows no absence attribute for a present value', () => {
    const profile = fixtureProfile()
    render(<ProfilePanel profile={profile} fields={[fixturePresentField()]} overrides={fixtureOverrideProvenance()} />)
    const list = screen.getByRole('region', { name: 'Fields' })
    expect(list.querySelector('[data-absence]')).toBeNull()
    expect(resolveProfileAbsence(fixturePresentField())).toBeNull()
  })
})

describe('hard stops and grades are in separate labelled sections', () => {
  it('never puts a hard stop and a graded criterion in the same list', () => {
    const profile = fixtureProfile()
    render(<ProfilePanel profile={profile} fields={[]} overrides={fixtureOverrideProvenance()} />)

    const hardStops = screen.getByRole('region', { name: 'Hard stops' })
    const graded = screen.getByRole('region', { name: 'Graded criteria' })
    expect(hardStops).not.toBe(graded)

    expect(within(hardStops).getByText(/lightning:/)).toBeInTheDocument()
    expect(within(graded).getByText(/gustiness:/)).toBeInTheDocument()
    expect(within(hardStops).queryByText(/gustiness:/)).not.toBeInTheDocument()
    expect(within(graded).queryByText(/lightning:/)).not.toBeInTheDocument()
  })
})

describe('thresholds show the default and, when overridden, the override', () => {
  it('marks an overridden threshold with both values', () => {
    const profile = fixtureProfile()
    const overrides = fixtureOverrideProvenance({
      overrides: [{ threshold: 'gust', profile_default: 15.0, value: 20.0 }],
      no_override_in_force: false,
    })
    render(<ProfilePanel profile={profile} fields={[]} overrides={overrides} />)

    const thresholds = screen.getByRole('region', { name: 'Thresholds' })
    const gustRow = thresholds.querySelector('[data-threshold="gust"]') as HTMLElement
    expect(gustRow.querySelector('[data-override="true"]')?.textContent).toContain('20')
    expect(gustRow.textContent).toContain('15')
    // No blanket "no override" statement when one is in force.
    expect(screen.queryByText('No threshold was overridden.')).not.toBeInTheDocument()
  })

  it('states explicitly when no threshold was overridden', () => {
    const profile = fixtureProfile()
    render(<ProfilePanel profile={profile} fields={[]} overrides={fixtureOverrideProvenance()} />)
    expect(screen.getByText('No threshold was overridden.')).toBeInTheDocument()
    const thresholds = screen.getByRole('region', { name: 'Thresholds' })
    expect(thresholds.querySelector('[data-override="true"]')).toBeNull()
  })
})

describe('each blocked field shows its reason, source and terms', () => {
  it('renders every element of the blocked_fields entry', () => {
    const profile = fixtureProfile()
    render(<ProfilePanel profile={profile} fields={[]} overrides={fixtureOverrideProvenance()} />)
    const blocked = screen.getByRole('region', { name: 'Blocked fields' })
    const row = blocked.querySelector('[data-blocked-field="road_state"]') as HTMLElement
    expect(row.textContent).toContain('licence')
    expect(row.textContent).toContain('nl-511')
    expect(row.textContent).toContain('The NL 511 site terms grant no reuse')
  })

  it('shows a blocked field row with its reason inline in the fields list', () => {
    const profile = fixtureProfile()
    render(<ProfilePanel profile={profile} fields={[fixtureBlockedField()]} overrides={fixtureOverrideProvenance()} />)
    const list = screen.getByRole('region', { name: 'Fields' })
    const row = list.querySelector('[data-field="road_state"]') as HTMLElement
    expect(row.getAttribute('data-absence')).toBe('blocked')
    expect(row.textContent).toContain('licence')
    expect(row.textContent).toContain('nl-511')
  })
})

describe('window, families and wanted-not-catalogued', () => {
  it('renders the window rule, geometry entry and geometry fields', () => {
    const profile = fixtureProfile()
    render(<ProfilePanel profile={profile} fields={[]} overrides={fixtureOverrideProvenance()} />)
    const window = screen.getByRole('region', { name: 'Window' })
    expect(window.textContent).toContain('any_window_within_24h')
    expect(window.textContent).toContain('de442_sun_moon_geometry')
    expect(window.textContent).toContain('sun_altitude')
  })

  it('lists the families', () => {
    const profile = fixtureProfile()
    render(<ProfilePanel profile={profile} fields={[]} overrides={fixtureOverrideProvenance()} />)
    const families = screen.getByRole('region', { name: 'Families' })
    expect(within(families).getByText('temperature')).toBeInTheDocument()
    expect(within(families).getByText('wind')).toBeInTheDocument()
    expect(within(families).getByText('lightning')).toBeInTheDocument()
  })

  it('labels a wanted-not-catalogued entry as not in the catalogue', () => {
    const profile = fixtureProfile()
    render(<ProfilePanel profile={profile} fields={[]} overrides={fixtureOverrideProvenance()} />)
    const wanted = screen.getByRole('region', { name: 'Wanted but not catalogued' })
    expect(wanted.textContent).toContain('humidex')
    expect(wanted.textContent).toContain('not in the catalogue')
  })
})
