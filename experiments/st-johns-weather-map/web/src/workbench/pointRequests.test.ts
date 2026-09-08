import { afterEach, expect, it, vi } from 'vitest'
import { PointRequestQueue, pointRequest, type PointResult } from './pointRequests'
import { unavailableSnapshot, stations } from '../fixtures'

afterEach(() => vi.useRealTimers())
const result: PointResult = {snapshot:unavailableSnapshot,source:'unavailable'}
const request = (product:string, instant = 0) => pointRequest(stations[0],instant,{sourceId:product,productId:product,product,field:'temperature_2m'})
it('debounces, deduplicates and limits the queue to two concurrent requests', async () => {
  vi.useFakeTimers()
  const finish: ((value:PointResult)=>void)[] = []
  const loader = vi.fn(() => new Promise<PointResult>(resolve => finish.push(resolve))), report = vi.fn()
  const queue = new PointRequestQueue(loader,report)
  queue.replace([request('a'),request('a'),request('b'),request('c')])
  await vi.advanceTimersByTimeAsync(249); expect(loader).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1); expect(loader).toHaveBeenCalledTimes(2)
  finish[0](result); await vi.advanceTimersByTimeAsync(0)
  expect(loader).toHaveBeenCalledTimes(3)
  finish[1](result);finish[2](result);await vi.advanceTimersByTimeAsync(0)
  expect(report).toHaveBeenCalledTimes(3);queue.cancel()
})
it('rejects obsolete responses and counts aborted transports until they really settle', async () => {
  vi.useFakeTimers()
  const finish: ((value:PointResult)=>void)[] = [], signals: AbortSignal[] = []
  const loader = vi.fn((_location,_time,_product,signal) => {signals.push(signal!);return new Promise<PointResult>(resolve => finish.push(resolve))}), report=vi.fn()
  const queue=new PointRequestQueue(loader,report)
  queue.replace([request('a'),request('b')]);await vi.advanceTimersByTimeAsync(250)
  queue.replace([request('a',1000),request('c',1000)]);await vi.advanceTimersByTimeAsync(250)
  expect(signals.every(s=>s.aborted)).toBe(true);expect(loader).toHaveBeenCalledTimes(2)
  finish[0](result);await vi.advanceTimersByTimeAsync(0)
  expect(report).not.toHaveBeenCalled();expect(loader).toHaveBeenCalledTimes(3)
  finish[1](result);await vi.advanceTimersByTimeAsync(0)
  finish[2](result);finish[3](result);await vi.advanceTimersByTimeAsync(0)
  expect(report.mock.calls.map(c=>c[0])).toEqual([request('a',1000).key,request('c',1000).key]);queue.cancel()
})
it('requests settled playback steps and independently reports rejection', async () => {
  vi.useFakeTimers()
  const report=vi.fn(), loader=vi.fn().mockRejectedValueOnce(new Error('Credentials required')).mockResolvedValue(result)
  const queue=new PointRequestQueue(loader,report)
  for(let i=0;i<5;i++){queue.replace([request('a',i*60000)]);await vi.advanceTimersByTimeAsync(100)}
  expect(loader).not.toHaveBeenCalled();await vi.advanceTimersByTimeAsync(150)
  expect(report).toHaveBeenCalledWith(request('a',240000).key,{error:'Credentials required'})
  queue.replace([request('b',300000)]);await vi.advanceTimersByTimeAsync(250)
  expect(report).toHaveBeenLastCalledWith(request('b',300000).key,{result});queue.cancel()
})

it('keeps WeatherNext fields and percentiles in request identity', () => {
  const base={sourceId:'google-weathernext-3-statistics',productId:'wn3',product:'WeatherNext 3 local',field:'temperature_2m',variant:{kind:'provider_statistic' as const,statistic:'ensemble_mean'}}
  const first=pointRequest(stations[0],0,base)
  const second=pointRequest(stations[0],0,{...base,field:'weathernext3_total_cloud_cover_mean'})
  expect(first.options.field).toBe('temperature_2m')
  expect(first.key).not.toBe(second.key)
})
