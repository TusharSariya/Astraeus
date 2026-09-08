import { afterEach, expect, it, vi } from 'vitest'
import { loadPoint, POINT_REQUEST_TIMEOUT_MS } from './api'

const location = { id: 'test', name: 'Test', latitude: 47.56, longitude: -52.71, kind: 'map' as const }
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

function hangUntilAborted(signal: AbortSignal) {
  return new Promise<never>((_, reject) => {
    const abort = () => reject(new DOMException('Aborted', 'AbortError'))
    if (signal.aborted) abort()
    else signal.addEventListener('abort', abort, { once: true })
  })
}

it.each(['headers', 'body'])('ends indefinite point loading while waiting for %s', async phase => {
  vi.useFakeTimers()
  let transportSignal: AbortSignal | undefined
  vi.stubGlobal('fetch', vi.fn((_url, options) => {
    transportSignal = options.signal
    return phase === 'headers' ? hangUntilAborted(options.signal)
      : Promise.resolve({ ok: true, json: () => hangUntilAborted(options.signal) })
  }))
  const pending = loadPoint(location)
  await vi.advanceTimersByTimeAsync(POINT_REQUEST_TIMEOUT_MS)
  const result = await pending
  expect(transportSignal?.aborted).toBe(true)
  expect(result.source).toBe('unavailable')
  expect(result.error).toContain('timed out after 30 seconds')
  expect(vi.getTimerCount()).toBe(0)
})

it('keeps obsolete-request cancellation distinct from a timeout', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn((_url, options) => hangUntilAborted(options.signal)))
  const controller = new AbortController()
  const pending = loadPoint(location, undefined, undefined, controller.signal)
  const assertion = expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  controller.abort()
  await assertion
  expect(vi.getTimerCount()).toBe(0)
})

it('clears the timeout after an immediate API failure', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 503 })))
  expect((await loadPoint(location)).error).toContain('503')
  expect(vi.getTimerCount()).toBe(0)
})
