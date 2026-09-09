import { GRID_FIELD, waitForGrid, wn3Request } from './sourceGrid'
import { useEffect, useRef, useState } from 'react'
import { loadPoint, type NormalizeOptions } from '../api'
import type { LocationPoint, PointFieldSelection } from '../types'

export type PointResult = Awaited<ReturnType<typeof loadPoint>>
export interface PointRequest { key: string; location: LocationPoint; instant: number; product: string; options: NormalizeOptions }
export function pointRequest(location: LocationPoint, instant: number, p: PointFieldSelection): PointRequest {
  const v = p.variant
  const options: NormalizeOptions = { timeSelection: 'directional', ...(p.sourceId === 'google-weathernext-3-statistics' ? {field:p.field} : {}), member: v?.member === 'all' ? null : v?.member ?? null, statistic: v?.statistic ?? null, quantile: v?.quantile ?? null, threshold: v?.threshold ?? null, comparison: v?.comparison ?? null }
  return { key: JSON.stringify([location.latitude, location.longitude, instant, p.product, options]), location, instant, product: p.product, options }
}
export type RequestState = { result?: PointResult; error?: string }
/** Canceled transports still occupy a slot until they settle, even if they ignore AbortSignal. */
export class PointRequestQueue {
  private active = new Set<AbortController>()
  private pending: PointRequest[] = []
  private generation = 0
  private timer: ReturnType<typeof setTimeout> | undefined
  private ready = false
  constructor(private loader = loadPoint, private report: (key: string, state: RequestState) => void) {}
  replace(requests: PointRequest[]) {
    this.cancel()
    this.pending = [...new Map(requests.map(r => [r.key, r])).values()]
    this.timer = setTimeout(() => { this.ready = true; this.pump() }, 250)
  }
  cancel() {
    this.generation++; this.ready = false; this.pending = []
    clearTimeout(this.timer)
    for (const controller of this.active) controller.abort()
  }
  private pump() {
    while (this.ready && this.active.size < 2 && this.pending.length) {
      const request = this.pending.shift()!, generation = this.generation, controller = new AbortController()
      this.active.add(controller)
      Promise.resolve().then(async () => {
        const load = () => this.loader(request.location, new Date(request.instant).toISOString(), request.product, controller.signal, request.options)
        if (!request.product.startsWith('WeatherNext 3')) return load()
        if(request.options.field===GRID_FIELD) await waitForGrid(request.product, request.instant)
        return wn3Request(controller.signal, load)
      })
        .then(result => { if (generation === this.generation && !controller.signal.aborted) this.report(request.key, { result }) })
        .catch(error => { if (generation === this.generation && !controller.signal.aborted) this.report(request.key, { error: error instanceof Error ? error.message : String(error) }) })
        .finally(() => { this.active.delete(controller); this.pump() })
    }
  }
}
const EMPTY_RESULTS: Record<string, RequestState> = {}
export function usePointRequests(requests: PointRequest[]) {
  const signature = JSON.stringify([...new Set(requests.map(r => r.key))].sort())
  const [state, setState] = useState<{ signature: string; results: Record<string, RequestState> }>({ signature: '', results: {} })
  const scope = useRef(signature)
  const queue = useRef<PointRequestQueue | null>(null)
  if (!queue.current) queue.current = new PointRequestQueue(loadPoint, (key, result) => setState(current => ({ signature: scope.current, results: { ...(current.signature === scope.current ? current.results : {}), [key]: result } })))
  useEffect(() => {
    scope.current = signature
    setState({ signature, results: {} })
    queue.current!.replace(requests)
    return () => queue.current!.cancel()
  }, [signature])
  // Render-time gate prevents even a single render of evidence from the previous Focus.
  return state.signature === signature ? state.results : EMPTY_RESULTS
}
