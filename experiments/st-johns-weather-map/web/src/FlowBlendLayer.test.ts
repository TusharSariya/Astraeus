/** The shader's blend math, pinned on the CPU reference the fragment shader
 *  mirrors, plus the layer's safety before it has a GL context. */

import { describe, expect, it, vi } from 'vitest'

// jsdom cannot import the real MapLibre bundle (it builds a worker URL at
// module load); only MercatorCoordinate is reachable from this module.
vi.mock('maplibre-gl', () => ({
  default: { MercatorCoordinate: { fromLngLat: (point: { lng: number; lat: number }) => ({ x: point.lng, y: point.lat }) } },
}))

import { FlowBlendLayer, blendReference, envelopeTerm, hermiteDisplacement, visibilityWeights } from './FlowBlendLayer'

describe('envelopeTerm (the residual-advection development envelope)', () => {
  it('is zero at both real frames for every (a, b), by algebra rather than a clamp', () => {
    // The whole licence for drawing it: whatever the server fitted, the two
    // retrieved frames show untouched at their own instants.
    for (const [a, b] of [[0.4, 0], [-0.3, 0.2], [1, -1], [0, 0.7]]) {
      expect(envelopeTerm(a, b, 0)).toBeCloseTo(0, 12)
      expect(envelopeTerm(a, b, 1)).toBeCloseTo(0, 12)
    }
  })

  it('is identically zero where the server measured no residual, so it costs nothing', () => {
    for (const t of [0.1, 0.25, 0.5, 0.9]) expect(envelopeTerm(0, 0, t)).toBe(0)
  })

  it('evaluates exactly the parabola the server stored: t(1-t)(a + b t)', () => {
    // The same numbers ResidualAdvectionMethod.composite evaluates in
    // ingest/derive/methods/residual_advection.py. If these drift, the bench
    // ranks a construction the map does not draw.
    expect(envelopeTerm(0.4, 0, 0.5)).toBeCloseTo(0.25 * 0.4, 12)
    expect(envelopeTerm(0.4, 0.2, 0.5)).toBeCloseTo(0.25 * (0.4 + 0.1), 12)
    expect(envelopeTerm(-0.4, 0, 0.25)).toBeCloseTo(0.1875 * -0.4, 12)
  })

  it('can draw a value in neither frame between them - which is why the map discloses it', () => {
    // Frame0 alpha 0, frame1 alpha 1, midpoint mix 0.5. A positive a pushes
    // the midpoint above the crossfade; a large one pushes it above BOTH
    // retrieved values at a cell where both are low. That is carve-out (d),
    // allowed only for the generative method and named GENERATED on the map.
    const lowBoth = 0.1 * 0.5 + 0.1 * 0.5 + envelopeTerm(1, 0, 0.5)
    expect(lowBoth).toBeGreaterThan(0.1)
    expect(0.5 + envelopeTerm(0.4, 0, 0.5)).toBeCloseTo(0.6, 12)
  })
})

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

describe('visibilityWeights (the fragment shader visibility branch)', () => {
  it('is endpoint-exact: one frame carries the whole pixel at its own instant', () => {
    // Whatever the two reliabilities claim - including a frame declared all
    // but invisible - the real frame shows untouched at its own end.
    expect(visibilityWeights(0.01, 1, 0)).toEqual({ w0: 1, w1: 0 })
    expect(visibilityWeights(1, 0.01, 1)).toEqual({ w0: 0, w1: 1 })
  })

  it('reduces exactly to the symmetric (1-t, t) where both warps are equally reliable', () => {
    // The reduction that makes this a controlled change: equal reliabilities
    // normalise back to the shipped fusion whatever their common value, so any
    // visible difference is a measured disagreement, never a new blend applied
    // everywhere.
    for (const v of [1, 0.4, 0.05]) {
      for (const t of [0.1, 0.25, 0.5, 0.9]) {
        const { w0, w1 } = visibilityWeights(v, v, t)
        expect(w0).toBeCloseTo(1 - t, 10)
        expect(w1).toBeCloseTo(t, 10)
      }
    }
  })

  it('lets the reliable warp carry the pixel instead of averaging in the unreliable one', () => {
    // At the midpoint the shipped fusion is 50/50 - which is how two warps
    // that disagree become a double image. With frame 1's warp measured at a
    // fiftieth of frame 0's, frame 0 takes ~98 percent of the pixel.
    const { w0, w1 } = visibilityWeights(1, 0.02, 0.5)
    expect(w0).toBeCloseTo(1 / 1.02, 10)
    expect(w1).toBeCloseTo(0.02 / 1.02, 10)
    expect(w0).toBeGreaterThan(0.97)
  })

  it('always sums to 1 and stays a convex combination, so nothing is invented', () => {
    for (const [v0, v1, t] of [[1, 0.02, 0.25], [0.3, 0.9, 0.75], [0.5, 0.5, 0.5], [1, 1, 0.1]]) {
      const { w0, w1 } = visibilityWeights(v0, v1, t)
      expect(w0 + w1).toBeCloseTo(1, 10)
      expect(w0).toBeGreaterThanOrEqual(0)
      expect(w1).toBeGreaterThanOrEqual(0)
    }
  })

  it('reads a zero pair as an absent measurement, not a reliability of zero', () => {
    // Off-grid pixels of the served texture carry zero in both channels. A
    // literal reading would make one retrieved frame vanish there; the
    // fallback is the time weights the baseline already draws.
    for (const t of [0.25, 0.5, 0.75]) {
      const { w0, w1 } = visibilityWeights(0, 0, t)
      expect(w0).toBeCloseTo(1 - t, 10)
      expect(w1).toBeCloseTo(t, 10)
    }
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
      visibilityUrl: null, residualUrl: null, residualScalePixels: 0, construction: 'visibility',
      bounds: { west: -55, south: 46, east: -50, north: 49 }, widthPx: 100, heightPx: 100,
      t: 0.5, opacity: 0.85,
    })
    // No GL yet: render must be a no-op, not a crash.
    layer.render(undefined as unknown as WebGLRenderingContext, { defaultProjectionData: { mainMatrix: new Float32Array(16) } })
    layer.onRemove()
  })
})
