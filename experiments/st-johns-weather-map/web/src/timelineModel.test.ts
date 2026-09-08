import { describe, expect, it } from 'vitest'
import { clusterMarkers, containingRange, displayWindow, frameNeighbour, rangeMarks } from './timelineModel'
import type { FrameMarker } from './api'
const now = Date.parse('2026-09-08T12:00:00Z')
const minute = 60_000
const marker = (ms: number): FrameMarker => ({ ms, time: new Date(ms).toISOString(), layers: [{ id:'radar', title:'Radar', color:'#abc' }] })
describe('desktop display ranges', () => {
  it('contains restored history and forecast selections without moving time', () => {
    expect(containingRange(now,now)).toBe('near')
    expect(containingRange(now-6*60*minute,now)).toBe('day')
    expect(containingRange(now+7*24*60*minute,now)).toBe('outlook')
    expect(containingRange(now-24*60*minute,now)).toBe('outlook')
  })
  it('intersects presets with actual API bounds', () => {
    expect(displayWindow('near', now,now-30*minute,now+60*minute)).toEqual({ start:now-30*minute,end:now+60*minute })
  })
  it('retains Now and both boundaries in scale candidates', () => {
    const marks=rangeMarks('near',now-60*minute,now+360*minute,now)
    expect(marks.map(mark=>mark.hours)).toEqual([-1,0,1,2,3,4,5,6])
  })
})
describe('native timestamp access', () => {
  it('clusters dense Outlook timestamps without losing or changing a single instant', () => {
    const frames=Array.from({length:1441},(_,index)=>marker(now-24*60*minute+index*minute+1234))
    const clusters=clusterMarkers(frames,now-24*60*minute,now+14*24*60*minute,900)
    expect(clusters.length).toBeLessThan(10)
    expect(clusters.flatMap(cluster=>cluster.markers)).toEqual(frames)
  })
  it('retains isolated exact-second markers and excludes out-of-range frames', () => {
    const frames=[marker(now-1),marker(now+1234),marker(now+60*minute),marker(now+61*minute)]
    expect(clusterMarkers(frames,now,now+60*minute,900).flatMap(cluster=>cluster.markers)).toEqual(frames.slice(1,3))
  })
  it('steps to strict neighbours and stops at either end, even between frames', () => {
    expect(frameNeighbour([100,300,900],200,1)).toBe(300)
    expect(frameNeighbour([100,300,900],300,-1)).toBe(100)
    expect(frameNeighbour([100,300,900],900,1)).toBeNull()
    expect(frameNeighbour([],300,-1)).toBeNull()
  })
})
