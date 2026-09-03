import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SitePanel } from './SitePanel'
import { fixtureHorizonField, fixtureRegistry, fixtureSite } from './fixtures'
import type { PointSelection } from './types'

const NO_SELECTION: PointSelection = { latitude: 47.5615, longitude: -52.7126, site_id: null }

describe('sites are preferred locations, never a limit', () => {
  it('renders each site as a button and selects it with its own position and id on click', async () => {
    const user = userEvent.setup()
    const registry = fixtureRegistry()
    const onSelect = vi.fn()
    render(<SitePanel registry={registry} selection={NO_SELECTION} onSelect={onSelect} horizonFields={[]} />)

    const buttons = registry.sites.map((site) => screen.getByRole('button', { name: site.name }))
    expect(buttons).toHaveLength(3)

    await user.click(buttons[1])
    expect(onSelect).toHaveBeenCalledWith({
      latitude: registry.sites[1].latitude,
      longitude: registry.sites[1].longitude,
      site_id: registry.sites[1].id,
    })
  })

  it('never ranks or recommends: the heading names sites as preferred, not as a limit', () => {
    render(<SitePanel registry={fixtureRegistry()} selection={NO_SELECTION} onSelect={vi.fn()} horizonFields={[]} />)
    const heading = screen.getByText(/preferred locations/i)
    expect(heading.textContent).toMatch(/never a limit/i)
  })

  it('selects an arbitrary in-box point through the custom point control, with site_id null', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<SitePanel registry={fixtureRegistry()} selection={NO_SELECTION} onSelect={onSelect} horizonFields={[]} />)

    await user.type(screen.getByLabelText('Custom point latitude'), '47.6')
    await user.type(screen.getByLabelText('Custom point longitude'), '-52.7')
    await user.click(screen.getByRole('button', { name: 'Use this point' }))

    expect(onSelect).toHaveBeenCalledWith({ latitude: 47.6, longitude: -52.7, site_id: null })
  })

  it('refuses a custom point outside the evidence box, naming the box, and never calls onSelect for it', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<SitePanel registry={fixtureRegistry()} selection={NO_SELECTION} onSelect={onSelect} horizonFields={[]} />)

    await user.type(screen.getByLabelText('Custom point latitude'), '10')
    await user.type(screen.getByLabelText('Custom point longitude'), '10')
    await user.click(screen.getByRole('button', { name: 'Use this point' }))

    const refusal = await screen.findByRole('alert')
    expect(refusal.textContent).toMatch(/45/)
    expect(refusal.textContent).toMatch(/50\.5/)
    expect(refusal.textContent).toMatch(/-58/)
    expect(refusal.textContent).toMatch(/-46/)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('shows a no_registered_horizon field as unavailable off-site with the not-borrowed statement', () => {
    render(
      <SitePanel
        registry={fixtureRegistry()}
        selection={NO_SELECTION}
        onSelect={vi.fn()}
        horizonFields={[fixtureHorizonField()]}
      />,
    )
    const row = screen.getByText(/sector_statistic/).closest('li')
    expect(row).not.toBeNull()
    expect(row!.textContent).toMatch(/no_registered_horizon/)
    expect(row!.textContent).toMatch(/no nearby site's horizon is borrowed/i)
  })

  it('renders a registry notice when the registry set one', () => {
    render(
      <SitePanel
        registry={fixtureRegistry({ notice: 'quidi-vidi: site_horizon_gap:200' })}
        selection={NO_SELECTION}
        onSelect={vi.fn()}
        horizonFields={[]}
      />,
    )
    expect(screen.getByText('quidi-vidi: site_horizon_gap:200')).toBeInTheDocument()
  })

  it('discloses a not_run terrain check on the site that carries one', () => {
    const registry = fixtureRegistry({
      sites: [fixtureSite({ id: 'solo-site', name: 'Solo Site' })],
    })
    render(<SitePanel registry={registry} selection={NO_SELECTION} onSelect={vi.fn()} horizonFields={[]} />)
    const row = screen.getByRole('button', { name: 'Solo Site' }).closest('li')
    expect(row).not.toBeNull()
    expect(row!.textContent).toMatch(/not_run/)
    expect(row!.textContent).toMatch(/No digital elevation model/i)
  })
})
