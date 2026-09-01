/** The transport model: the speed ladder clamps at both ends, and the clock
 *  advances by wall-clock time, wrapping inside the window rather than
 *  escaping it. */

import { describe, expect, it } from 'vitest'

import { advanceClock, describeSpeed, fasterSpeed, PLAYBACK_SPEEDS, slowerSpeed } from './playback'

const START = Date.UTC(2026, 7, 31, 12, 0, 0)
const END = START + 28 * 60 * 60_000

const at = (ms: number, elapsedSeconds: number, speed = 1, direction: 1 | -1 = 1) =>
  advanceClock({ ms, elapsedSeconds, speedMinutesPerSecond: speed, direction, windowStartMs: START, windowEndMs: END })

describe('the speed ladder', () => {
  it('doubles by rung and clamps at both ends', () => {
    expect([...PLAYBACK_SPEEDS]).toEqual([1, 2, 4, 8, 16, 32])
    expect(fasterSpeed(1)).toBe(2)
    expect(fasterSpeed(16)).toBe(32)
    expect(fasterSpeed(32)).toBe(32)
    expect(slowerSpeed(32)).toBe(16)
    expect(slowerSpeed(1)).toBe(1)
  })
})

describe('advanceClock', () => {
  it('advances a minute of weather time per second at the first speed', () => {
    expect(at(START, 1)).toBe(START + 60_000)
    expect(at(START, 2, 16)).toBe(START + 32 * 60_000)
  })

  it('runs backwards under a reversed direction', () => {
    expect(at(START + 10 * 60_000, 1, 4, -1)).toBe(START + 6 * 60_000)
  })

  it('wraps to the window start after the far edge, and to the end going back', () => {
    // One second at 32 min/s from ten minutes before the end lands 22
    // minutes past it: the loop puts that 22 minutes at the window start.
    const nearEnd = END - 10 * 60_000
    expect(at(nearEnd, 1, 32)).toBe(START + 22 * 60_000)
    const nearStart = START + 5 * 60_000
    expect(at(nearStart, 1, 32, -1)).toBe(END - 27 * 60_000)
  })

  it('stays inside the window even after a stall longer than the window', () => {
    // A backgrounded tab, a slow paint: whatever the gap, the clock lands
    // somewhere in the window rather than running off the far edge.
    for (const elapsed of [1, 60, 3_600, 86_400]) {
      const landed = at(START + 3 * 60_000, elapsed, 32)
      expect(landed).toBeGreaterThanOrEqual(START)
      expect(landed).toBeLessThanOrEqual(END)
    }
  })

  it('holds still for a zero, negative or unreadable elapsed time', () => {
    expect(at(START + 60_000, 0)).toBe(START + 60_000)
    expect(at(START + 60_000, -5)).toBe(START + 60_000)
    expect(at(START + 60_000, Number.NaN)).toBe(START + 60_000)
  })

  it('clamps an instant already outside the window when nothing advances', () => {
    expect(at(END + 60_000, 0)).toBe(END)
    expect(at(START - 60_000, 0)).toBe(START)
  })
})

describe('describeSpeed', () => {
  it('names the speed and says when it runs backwards', () => {
    expect(describeSpeed(16, 1)).toBe('16 min/s')
    expect(describeSpeed(16, -1)).toBe('16 min/s reversed')
  })
})
