import { describe, expect, it } from 'vitest'
import { parseFocusUrl, serializeFocusUrl } from './focusUrl'
import { stations } from '../fixtures'

describe('linked Bench Focus', () => {
  it('round trips precise points, native instants, ordered hidden layers and scoped runs', () => {
    const state = parseFocusUrl('?lat=47.5123456789&lon=-52.6987654321&t=2026-09-07T09:06:03.123Z&view=series&dock=map&run.noaa-gfs=2026-09-07T06:00:00Z&stack=[]', stations[0])
    expect(state.location.latitude).toBe(47.5123456789)
    expect(state.stack).toEqual([])
    state.stack = [{ id: 'radar', visible: false, opacity: 0 }, { id: 'cloud', visible: true, opacity: 0.65 }]
    const link = serializeFocusUrl(state, '?theme=night&external=kept')
    expect(link).not.toContain('theme=')
    expect(link).toContain('external=kept')
    expect(parseFocusUrl(link, stations[0])).toEqual(state)
  })
  it('keeps Now session-relative and never substitutes duplicate or invalid stack entries', () => {
    const state = parseFocusUrl('?lat=&lon=-52&view=bogus&dock=map&t=nope&stack=[{}]', stations[0])
    expect(state.location).toEqual(stations[0]); expect(state.instant).toBeNull(); expect(state.stack).toBeNull()
    expect(state.dock).toBeNull(); expect(state.notices).toHaveLength(4)
    expect(new URLSearchParams(serializeFocusUrl(state)).has('t')).toBe(false)
  })
  it('requires explicit site adoption and keeps unavailable pinned runs selected', () => {
    expect(parseFocusUrl('?site=signal-hill', stations[0]).site).toBe('signal-hill')
    expect(parseFocusUrl('?site=signal-hill&lat=47.5704&lon=-52.6816', stations[0]).site).toBeNull()
    expect(parseFocusUrl('?run.noaa-gfs=removed-run', stations[0]).runs['noaa-gfs']).toBe('removed-run')
  })
})
