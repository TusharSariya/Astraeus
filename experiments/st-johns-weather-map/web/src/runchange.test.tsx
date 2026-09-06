import { describe, expect, it } from 'vitest'
import { resolveLayerFrame } from './api'
import { runChangePoints, runSegments } from './runSegments'
import type { LayerFrame, LayerItem } from './types'

function frame(valid: string, runTime: string | null, runStale: boolean | null = null): LayerFrame {
  return { valid_time: valid, run_time: runTime, provider_run_id: runTime ? `run-${runTime}` : null, run_stale: runStale }
}

describe('runSegments: consecutive frames sharing one run_time (task 4.3)', () => {
  it('groups consecutive frames that share a run time into one segment', () => {
    const frames = [
      frame('2026-09-02T00:00:00Z', '2026-09-01T18:00:00Z'),
      frame('2026-09-02T06:00:00Z', '2026-09-01T18:00:00Z'),
      frame('2026-09-02T12:00:00Z', '2026-09-02T06:00:00Z'),
    ]
    const segments = runSegments(frames)
    expect(segments).toHaveLength(2)
    expect(segments[0].runTime).toBe('2026-09-01T18:00:00Z')
    expect(segments[0].frames).toHaveLength(2)
    expect(segments[0].label).toBe('run 2026-09-01T18:00:00Z')
    expect(segments[1].runTime).toBe('2026-09-02T06:00:00Z')
    expect(segments[1].frames).toHaveLength(1)
  })

  it('the 06z short cycle: both segments are labelled with their own run time', () => {
    // The 06z IFS run covers to 144h; the retained 00z run covers beyond it.
    const frames = [
      frame('2026-09-08T06:00:00Z', '2026-09-08T06:00:00Z'),
      frame('2026-09-08T12:00:00Z', '2026-09-08T06:00:00Z'),
      frame('2026-09-08T18:00:00Z', '2026-09-08T00:00:00Z'), // retained 00z run, far lead
    ]
    const segments = runSegments(frames)
    expect(segments.map((segment) => segment.runTime)).toEqual(['2026-09-08T06:00:00Z', '2026-09-08T00:00:00Z'])
    expect(runChangePoints(segments)).toEqual([2])
  })

  it('a segment with a null run time is labelled unknown with the reason, and never inherits a neighbour\'s time', () => {
    const frames = [
      frame('2026-09-02T00:00:00Z', '2026-09-01T18:00:00Z'),
      frame('2026-09-02T06:00:00Z', null),
      frame('2026-09-02T12:00:00Z', '2026-09-01T18:00:00Z'),
    ]
    const segments = runSegments(frames)
    expect(segments).toHaveLength(3)
    expect(segments[1].unknown).toBe(true)
    expect(segments[1].runTime).toBeNull()
    expect(segments[1].label).toMatch(/^run unknown: /)
    // Neighbours on both sides keep their own time — nothing merged across it.
    expect(segments[0].runTime).toBe('2026-09-01T18:00:00Z')
    expect(segments[2].runTime).toBe('2026-09-01T18:00:00Z')
  })

  it('two adjacent unknown-run frames are two segments, not one shared "unknown" segment', () => {
    const frames = [frame('2026-09-02T00:00:00Z', null), frame('2026-09-02T06:00:00Z', null)]
    const segments = runSegments(frames)
    expect(segments).toHaveLength(2)
    expect(segments.every((segment) => segment.unknown)).toBe(true)
  })

  it('runChangePoints names no change point for the first frame', () => {
    expect(runChangePoints(runSegments([frame('2026-09-02T00:00:00Z', '2026-09-01T18:00:00Z')]))).toEqual([])
  })
})

describe('resolveLayerFrame: display interpolation refuses to pair frames from different runs (task 4.3)', () => {
  const reference = new Date('2026-09-08T09:00:00Z')

  function layerWithFrames(frames: LayerFrame[]): LayerItem {
    return {
      id: 'ifs-cloud', title: 'IFS total cloud', kind: 'raster', field: 'total_cloud', product: 'IFS',
      units: '%', semantics: 'total cloud cover', times: frames.map((f) => f.valid_time),
      staleness_tolerance_seconds: 21600, group: 'published_model', frames,
    }
  }

  it('refuses to blend two frames whose frames[] entries carry different non-null run_time', () => {
    const layer = layerWithFrames([
      frame('2026-09-08T06:00:00Z', '2026-09-08T06:00:00Z'),
      frame('2026-09-08T18:00:00Z', '2026-09-08T00:00:00Z'), // retained 00z run, different from 06z
    ])
    const at = new Date('2026-09-08T12:00:00Z') // strictly between the two, would otherwise blend
    const resolution = resolveLayerFrame(layer, at, { interpolate: true, reference })
    expect(resolution.kind).not.toBe('blend')
  })

  it('still blends two frames sharing the same run_time', () => {
    const layer = layerWithFrames([
      frame('2026-09-08T06:00:00Z', '2026-09-08T00:00:00Z'),
      frame('2026-09-08T18:00:00Z', '2026-09-08T00:00:00Z'),
    ])
    const at = new Date('2026-09-08T12:00:00Z')
    const resolution = resolveLayerFrame(layer, at, { interpolate: true, reference })
    expect(resolution.kind).toBe('blend')
  })

  it('does not refuse when a side has an unknown (null) run_time — nothing to compare', () => {
    const layer = layerWithFrames([
      frame('2026-09-08T06:00:00Z', null),
      frame('2026-09-08T18:00:00Z', '2026-09-08T00:00:00Z'),
    ])
    const at = new Date('2026-09-08T12:00:00Z')
    const resolution = resolveLayerFrame(layer, at, { interpolate: true, reference })
    expect(resolution.kind).toBe('blend')
  })

  it('keeps every existing frame-fallback scenario green: a layer with no frames[] at all still blends as before', () => {
    const layer: LayerItem = {
      id: 'gfs-cloud', title: 'GFS total cloud', kind: 'raster', field: 'total_cloud', product: 'GFS',
      units: '%', semantics: 'total cloud cover',
      times: ['2026-09-08T06:00:00Z', '2026-09-08T18:00:00Z'],
      staleness_tolerance_seconds: 21600, group: 'published_model',
      // No `frames` array published (older API).
    }
    const at = new Date('2026-09-08T12:00:00Z')
    const resolution = resolveLayerFrame(layer, at, { interpolate: true, reference })
    expect(resolution.kind).toBe('blend')
  })

  it('falls back to the disclosed nearest frame under the existing rules when the pair is refused', () => {
    const layer = layerWithFrames([
      frame('2026-09-08T06:00:00Z', '2026-09-08T06:00:00Z'),
      frame('2026-09-08T18:00:00Z', '2026-09-08T00:00:00Z'),
    ])
    const at = new Date('2026-09-08T12:00:00Z')
    const resolution = resolveLayerFrame(layer, at, { interpolate: true, reference })
    // Not a blend, but still resolves to a disclosed single frame — nothing
    // is silently dropped because a run change refused the composite.
    expect(['snapped', 'exact']).toContain(resolution.kind)
  })

  it('observed layers never interpolate regardless of run_time (unchanged rule)', () => {
    const layer: LayerItem = {
      id: 'radar', title: 'Radar', kind: 'raster', field: 'reflectivity', product: 'RADAR',
      units: 'dBZ', semantics: 'radar reflectivity', times: ['2026-09-08T05:54:00Z', '2026-09-08T06:00:00Z'],
      staleness_tolerance_seconds: 360, group: 'observation',
    }
    const at = new Date('2026-09-08T05:57:00Z')
    const resolution = resolveLayerFrame(layer, at, { interpolate: true, reference })
    expect(resolution.kind).not.toBe('blend')
  })
})
