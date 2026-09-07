import { useEffect, useRef, useState } from 'react'
import type { components } from '../generated/source-api'

export type NativeImagePair = components['schemas']['HolyroodImagesResponse']
export interface NativeImageSelection { sourceId: string; endpoint: string; instant: number }
const prefix = '/api/experiments/weather/v0/sources/'
export function nativeImageEndpoint(sourceId: string, endpoint: unknown): endpoint is string {
  return /^[a-z0-9-]+$/.test(sourceId) && endpoint === `${prefix}${sourceId}/images`
}
function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value) }
export function isNativeImagePair(value: unknown, selection: NativeImageSelection): value is NativeImagePair {
  if (!record(value) || value.source_id !== selection.sourceId || typeof value.valid_time !== 'string' || Date.parse(value.valid_time) !== selection.instant
    || typeof value.retained_until !== 'string' || !Number.isFinite(Date.parse(value.retained_until))
    || typeof value.pair_revision !== 'string' || !/^[a-f0-9]{64}$/.test(value.pair_revision)
    || value.semantics !== 'rendered-image-only' || value.primary !== false || value.operational !== false
    || value.source_quality !== 'unknown' || value.scientific_freshness !== 'unknown'
    || typeof value.station_id !== 'string' || typeof value.product !== 'string'
    || !record(value.presentation) || value.presentation.transformation !== 'unmodified-producer-image'
    || value.presentation.georeferencing !== 'not-established' || value.presentation.numeric_pixel_values !== 'unavailable'
    || !Array.isArray(value.images) || value.images.length !== 2) return false
  return ['Rain', 'Snow'].every((phase) => value.images instanceof Array && value.images.filter((image: unknown) => record(image)
    && image.phase === phase && image.image_url === `${selection.endpoint}/${value.pair_revision}/${phase}.gif`
    && Number.isInteger(image.width) && Number(image.width) > 0 && Number.isInteger(image.height) && Number(image.height) > 0
    && image.frames === 1 && typeof image.source_filename === 'string').length === 1)
}

/** Mounted with source/time identity: focus changes abandon the old read without prefetching. */
export function NativeImages({ selection }: { selection: NativeImageSelection }) {
  const [pair, setPair] = useState<NativeImagePair | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expired, setExpired] = useState(false)
  const [failedImages, setFailedImages] = useState<string[]>([])
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => {
    if (!pair) return
    const remaining = Date.parse(pair.retained_until) - Date.now()
    setExpired(remaining <= 0)
    if (remaining <= 0) return
    const timer = setTimeout(() => setExpired(true), Math.min(remaining, 2147483647))
    return () => clearTimeout(timer)
  }, [pair])
  async function read() {
    if (!nativeImageEndpoint(selection.sourceId, selection.endpoint)) return
    request.current?.abort()
    const controller = new AbortController(); request.current = controller
    setBusy(true); setError(null)
    try {
      const url = new URL(selection.endpoint, window.location.origin)
      url.searchParams.set('valid_time', new Date(selection.instant).toISOString())
      if (pair) url.searchParams.set('refresh', 'true')
      const response = await fetch(url, { signal: controller.signal, cache: 'no-store', headers: { Accept: 'application/json' } })
      if (!response.ok) throw new Error(`Image evidence unavailable (HTTP ${response.status}).`)
      const body: unknown = await response.json()
      if (!isNativeImagePair(body, selection)) throw new Error('Image response identity or presentation contract did not match the selection.')
      if (controller.signal.aborted) return
      setPair(body); setExpired(Date.parse(body.retained_until) <= Date.now()); setFailedImages([])
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error && cause.message.startsWith('Image ') ? cause.message : 'Image evidence could not be read.')
    } finally { if (!controller.signal.aborted) setBusy(false) }
  }
  if (!nativeImageEndpoint(selection.sourceId, selection.endpoint)) return null
  return <section className="native-images" aria-label="Native image evidence">
    <h3>Original image evidence</h3>
    <p>Selected native time: {new Date(selection.instant).toISOString()}. Read only this exact image pair.</p>
    <button onClick={read} disabled={busy}>{busy ? 'Reading images…' : pair ? 'Refresh native images' : 'Read native images'}</button>
    {error && <p role="status">{error} {pair && !expired ? 'The previous retained pair remains below; its retention has not been extended.' : 'No available image pair is shown.'}</p>}
    {pair && <>
      <p>{pair.station_id} · {pair.product} · Native valid time {pair.valid_time}</p>
      <p>Rendered image only · Source QC unknown · Scientific freshness unknown · Not a display primary · Experimental, not operational.</p>
      <p>Original producer legends retained. Georeferencing is not established; numerical pixel values are unavailable.</p>
      <p>Revision {pair.pair_revision} · Retained until {pair.retained_until}. Retention is cache availability, not scientific freshness.</p>
      {expired ? <p role="status">Image revision retention expired. Images are withheld; explicitly refresh to read again.</p> : pair.images.map((image) => <figure key={`${pair.pair_revision}:${image.phase}`}>
        <figcaption>{image.phase} · {image.source_filename}</figcaption>
        {failedImages.includes(image.phase) ? <p role="status">{image.phase} image revision unavailable. No replacement or numerical reading is inferred.</p> : <a href={image.image_url} target="_blank" rel="noreferrer"><img src={image.image_url} alt={`${image.phase} original producer image at ${pair.valid_time}; legend included`} width={image.width} height={image.height} onError={() => setFailedImages((current) => [...current, image.phase])} /></a>}
      </figure>)}
    </>}
  </section>
}
