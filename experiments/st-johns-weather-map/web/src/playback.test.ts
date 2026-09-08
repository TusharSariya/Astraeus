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
  it('advances by the selected rung and clamps at both ends', () => {
    expect([...PLAYBACK_SPEEDS]).toEqual([1, 2, 4, 8, 15, 30])
    expect(fasterSpeed(1)).toBe(2)
    expect(fasterSpeed(15)).toBe(30)
    expect(fasterSpeed(30)).toBe(30)
    expect(slowerSpeed(30)).toBe(15)
    expect(slowerSpeed(1)).toBe(1)
  })
})

describe('advanceClock', () => {
  it('advances a minute of weather time per second at the first speed', () => {
    expect(at(START, 1)).toBe(START + 60_000)
    expect(at(START, 2, 15)).toBe(START + 30 * 60_000)
  })

  it('runs backwards under a reversed direction', () => {
    expect(at(START + 10 * 60_000, 1, 4, -1)).toBe(START + 6 * 60_000)
  })

  it('wraps to the window start after the far edge, and to the end going back', () => {
    // One second at 30 min each second from ten minutes before the end lands 20
    // minutes past it: the loop puts that 20 minutes at the window start.
    const nearEnd = END - 10 * 60_000
    expect(at(nearEnd, 1, 30)).toBe(START + 20 * 60_000)
    const nearStart = START + 5 * 60_000
    expect(at(nearStart, 1, 30, -1)).toBe(END - 25 * 60_000)
  })

  it('stays inside the window even after a stall longer than the window', () => {
    // A backgrounded tab, a slow paint: whatever the gap, the clock lands
    // somewhere in the window rather than running off the far edge.
    for (const elapsed of [1, 60, 3_600, 86_400]) {
      const landed = at(START + 3 * 60_000, elapsed, 30)
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
    expect(describeSpeed(15, 1)).toBe('15 min each second')
    expect(describeSpeed(15, -1)).toBe('15 min each second reversed')
  })
})
