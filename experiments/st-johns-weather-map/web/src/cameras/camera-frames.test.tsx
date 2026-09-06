import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CameraPanel } from './CameraPanel'
import {
  fixtureAwaitingValidationCamera,
  fixtureCaptureTimeUnknownFrame,
  fixtureDerivedFromDisabledMethod,
  fixtureDerivedWithRefusal,
  fixtureFlaggedFrame,
  fixtureFrame,
  fixtureMethods,
  fixturePartnershipCamera,
} from './fixtures'

describe('a partnership-only camera', () => {
  it('shows its status badge, terms and request state, and renders no img', () => {
    const camera = fixturePartnershipCamera()
    const frame = fixtureFrame({ camera_id: camera.id })
    render(<CameraPanel cameras={[camera]} frames={[frame]} methods={fixtureMethods()} derived={[]} />)

    const section = screen.getByRole('region', { name: camera.name })
    const badge = within(section).getByText('partnership-only')
    expect(badge.getAttribute('data-status')).toBe('partnership-only')

    expect(within(section).getByText(/offered to the public as a courtesy/)).toBeInTheDocument()
    expect(within(section).getByText(/requested on 2026-09-02 from Canadian Coast Guard/)).toBeInTheDocument()
    expect(within(section).queryByText(/granted/)).not.toBeInTheDocument()

    expect(section.querySelector('img')).toBeNull()
  })

  it('never says "granted" when no request has been sent', () => {
    const camera = fixturePartnershipCamera({
      terms: {
        text: 'reserved rights notice',
        url: 'https://example.invalid/terms',
        permission: { requested_on: null, requested_from: 'Operator', granted_on: null },
      },
    })
    render(<CameraPanel cameras={[camera]} frames={[]} methods={fixtureMethods()} derived={[]} />)
    const section = screen.getByRole('region', { name: camera.name })
    expect(within(section).getByText('no request sent')).toBeInTheDocument()
    expect(within(section).queryByText(/granted/)).not.toBeInTheDocument()
  })

  it('lists the missing elements of an incomplete registration', () => {
    const camera = fixturePartnershipCamera()
    render(<CameraPanel cameras={[camera]} frames={[]} methods={fixtureMethods()} derived={[]} />)
    const section = screen.getByRole('region', { name: camera.name })
    for (const element of camera.registration.missing) {
      expect(within(section).getByText(element)).toBeInTheDocument()
    }
  })
})

describe('an awaiting_validation camera frame', () => {
  it('shows health flags as chips and the derivations-refused statement', () => {
    const camera = fixtureAwaitingValidationCamera()
    const frame = fixtureFlaggedFrame({ camera_id: camera.id })
    render(<CameraPanel cameras={[camera]} frames={[frame]} methods={fixtureMethods()} derived={[]} />)

    const section = screen.getByRole('region', { name: camera.name })
    const badge = within(section).getByText('awaiting_validation')
    expect(badge.getAttribute('data-status')).toBe('awaiting_validation')

    for (const flag of frame.flags) {
      expect(within(section).getByText(flag)).toBeInTheDocument()
    }
    expect(within(section).getByText(/derivations are refused naming blur/)).toBeInTheDocument()
  })

  it('shows "capture time unknown" for a frame with no capture time', () => {
    const camera = fixtureAwaitingValidationCamera()
    const frame = fixtureCaptureTimeUnknownFrame({ camera_id: camera.id })
    render(<CameraPanel cameras={[camera]} frames={[frame]} methods={fixtureMethods()} derived={[]} />)
    const section = screen.getByRole('region', { name: camera.name })
    expect(within(section).getByText('capture time unknown')).toBeInTheDocument()
  })

  it('renders an img for a frame with an image_url on a non-partnership-only camera', () => {
    const camera = fixtureAwaitingValidationCamera()
    const frame = fixtureFrame({ camera_id: camera.id })
    render(<CameraPanel cameras={[camera]} frames={[frame]} methods={fixtureMethods()} derived={[]} />)
    const section = screen.getByRole('region', { name: camera.name })
    expect(section.querySelector('img')).not.toBeNull()
  })
})

describe('a derived field never presents a claim from a disabled method', () => {
  it('shows "no claim" naming the method, and the distinctive value never appears in the document', () => {
    const camera = fixtureAwaitingValidationCamera()
    const derived = fixtureDerivedFromDisabledMethod({ camera_id: camera.id })
    render(<CameraPanel cameras={[camera]} frames={[]} methods={fixtureMethods()} derived={[derived]} />)

    expect(screen.getByText(/no claim: method camera_fog_and_visibility_class/)).toBeInTheDocument()
    expect(screen.queryByText('0.42')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('0.42')
  })

  it('shows "no claim" for a row carrying a refusal, and its value never appears', () => {
    const camera = fixtureAwaitingValidationCamera()
    const methods = fixtureMethods().map((method) =>
      method.name === 'camera_daytime_sector_cloud_fraction' ? { ...method, enabled: true } : method,
    )
    const derived = fixtureDerivedWithRefusal({ camera_id: camera.id })
    render(<CameraPanel cameras={[camera]} frames={[]} methods={methods} derived={[derived]} />)

    expect(screen.getByText(/no claim: method camera_daytime_sector_cloud_fraction.*blur/)).toBeInTheDocument()
    expect(screen.queryByText('0.77')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('0.77')
  })
})

describe('the camera method registry', () => {
  it('shows every disabled method with its disabled statement', () => {
    const methods = fixtureMethods()
    render(<CameraPanel cameras={[]} frames={[]} methods={methods} derived={[]} />)
    const registry = screen.getByRole('region', { name: 'Camera methods' })
    expect(methods.every((method) => !method.enabled)).toBe(true)
    for (const method of methods) {
      const row = registry.querySelector(`[data-method="${method.name}"]`) as HTMLElement
      expect(row).not.toBeNull()
      expect(within(row).getByText(method.version)).toBeInTheDocument()
      expect(within(row).getByText('disabled, awaiting validation')).toBeInTheDocument()
    }
  })
})
