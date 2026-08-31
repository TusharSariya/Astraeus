/** The shader's blend math, pinned on the CPU reference the fragment shader
 *  mirrors, plus the layer's safety before it has a GL context. */

import { describe, expect, it, vi } from 'vitest'

// jsdom cannot import the real MapLibre bundle (it builds a worker URL at
// module load); only MercatorCoordinate is reachable from this module.
vi.mock('maplibre-gl', () => ({
  default: { MercatorCoordinate: { fromLngLat: (point: { lng: number; lat: number }) => ({ x: point.lng, y: point.lat }) } },
}))

import { FlowBlendLayer, blendReference, hermiteDisplacement } from './FlowBlendLayer'

describe('hermiteDisplacement (the fragment shader cubic)', () => {
  it('is endpoint-exact: d0(0) = 0 and d0(1) = F, whatever the tangents claim', () => {
    expect(hermiteDisplacement(5, 2, 9, 0)).toBeCloseTo(0, 10)
    expect(hermiteDisplacement(5, 2, 9, 1)).toBeCloseTo(5, 10)
  })

  it('collapses exactly to linear advection when both tangents equal the flow', () => {
    for (const t of [0.1, 0.25, 0.5, 0.9]) {
      expect(hermiteDisplacement(4, 4, 4, t)).toBeCloseTo(4 * t, 10)
    }
  })

  it('shares the knot velocity across segments: C1 at every real frame', () => {
    // Two segments with displacements 2 then 4 and the shared knot velocity 3
    // (the QVI central difference). Velocity d0'(t) = vs + 2bt + 3ct^2; at the
    // shared knot the end of segment A and the start of segment B match.
    const epsilon = 1e-6
    const velocityAtEndOfA = (hermiteDisplacement(2, 2, 3, 1) - hermiteDisplacement(2, 2, 3, 1 - epsilon)) / epsilon
    const velocityAtStartOfB = (hermiteDisplacement(4, 3, 4, epsilon) - hermiteDisplacement(4, 3, 4, 0)) / epsilon
    expect(velocityAtEndOfA).toBeCloseTo(velocityAtStartOfB, 4)
    expect(velocityAtStartOfB).toBeCloseTo(3, 4)
    // The linear model has no such share: its velocities are 2 then 4.
    expect(Math.abs(2 - 4)).toBeGreaterThan(Math.abs(velocityAtEndOfA - velocityAtStartOfB))
  })

  it('bends the trajectory between the endpoints under acceleration', () => {
    // Accelerating motion (velocity 2 into the segment, 4 out, displacement 3):
    // the midpoint sits behind the linear midpoint, as a slow start should.
    const mid = hermiteDisplacement(3, 2, 4, 0.5)
    expect(mid).toBeLessThan(1.5)
    expect(mid).toBeGreaterThan(0)
  })
})

describe('blendReference (the fragment shader formula)', () => {
  it('is endpoint-exact: at t=0 and t=1 the warp offsets vanish and the real frame shows untouched', () => {
    // At t=0 the frame0 warp offset is -t*f = 0, so warpedAlpha0 == alpha0;
    // whatever the confidence, the output is exactly the real earlier frame.
    expect(blendReference(0.8, 0.1, 0.8, 0.55, 0, 1)).toBeCloseTo(0.8, 10)
    // At t=1 the frame1 warp offset is (1-t)*f = 0, so warpedAlpha1 == alpha1.
    expect(blendReference(0.8, 0.1, 0.3, 0.1, 1, 1)).toBeCloseTo(0.1, 10)
  })

  it('is a true linear cross-dissolve at zero confidence — not 1-(1-a)(1-b)', () => {
    const alpha = blendReference(1, 1, 0, 0, 0.5, 0)
    expect(alpha).toBeCloseTo(1.0, 10)
    // The old stacked-opacity composite of two full-cover frames at 50/50
    // painted 1-(1-0.5)(1-0.5) = 0.75 - a visibly wrong dip in overcast.
    expect(alpha).not.toBeCloseTo(0.75, 2)
  })

  it('follows the warped samples exactly at full confidence', () => {
    expect(blendReference(0.2, 0.9, 0.6, 0.4, 0.5, 1)).toBeCloseTo(0.5, 10)
  })

  it('mixes warp and crossfade per the confidence, never outside its inputs', () => {
    const alpha = blendReference(0.2, 0.9, 0.6, 0.4, 0.5, 0.5)
    const plain = 0.2 * 0.5 + 0.9 * 0.5
    const warped = 0.6 * 0.5 + 0.4 * 0.5
    expect(alpha).toBeCloseTo((plain + warped) / 2, 10)
    expect(alpha).toBeGreaterThanOrEqual(Math.min(plain, warped))
    expect(alpha).toBeLessThanOrEqual(Math.max(plain, warped))
  })
})

describe('FlowBlendLayer before GL exists', () => {
  it('accepts updates before onAdd and removal without a context', () => {
    const layer = new FlowBlendLayer('flowblend-test')
    expect(layer.type).toBe('custom')
    layer.update({
      frame0Url: 'blob:a', frame1Url: 'blob:b', flowUrl: null, flowScalePixels: 0,
      tangentsUrl: null, tangentsScalePixels: 0,
      bounds: { west: -55, south: 46, east: -50, north: 49 }, widthPx: 100, heightPx: 100,
      t: 0.5, opacity: 0.85,
    })
    // No GL yet: render must be a no-op, not a crash.
    layer.render(undefined as unknown as WebGLRenderingContext, { defaultProjectionData: { mainMatrix: new Float32Array(16) } })
    layer.onRemove()
  })
})
