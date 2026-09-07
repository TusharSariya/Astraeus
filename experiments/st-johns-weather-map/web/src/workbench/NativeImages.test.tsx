import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { isNativeImagePair, NativeImages, nativeImageEndpoint, type NativeImagePair } from './NativeImages'

const at = '2026-09-07T12:00:00Z'
const selection = { sourceId: 'eccc-holyrood-cashr-dpqpe', endpoint: '/api/experiments/weather/v0/sources/eccc-holyrood-cashr-dpqpe/images', instant: Date.parse(at) }
const revision = 'a'.repeat(64)
const receipt = { url: 'https://example.test/native.gif', body_bytes: 1, sha256: revision, completed_at: at, headers: [] }
const image = (phase: 'Rain' | 'Snow'): NativeImagePair['images'][number] => ({ phase, source_filename: `${phase}.gif`, width: 580, height: 480, frames: 1, receipt, image_url: `${selection.endpoint}/${revision}/${phase}.gif` })
const pair: NativeImagePair = { source_id: 'eccc-holyrood-cashr-dpqpe', producer: 'Environment and Climate Change Canada', station_id: 'CASHR', product: 'DPQPE', pair_revision: revision,
  valid_time: at, retained_until: '2026-09-07T12:05:00Z', cache_status: 'miss', semantics: 'rendered-image-only', source_quality: 'unknown', scientific_freshness: 'unknown', primary: false, operational: false,
  presentation: { encoding: 'image/gif', transformation: 'unmodified-producer-image', legend: 'preserved-in-producer-image', native_crs: null, georeferencing: 'not-established', numeric_pixel_values: 'unavailable' }, listing_receipt: receipt,
  images: [image('Rain'), image('Snow')] }
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('reads only on explicit action and preserves exact native time and image identity', async () => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse(at))
  const fetch = vi.fn(async (_url: string | URL | Request) => Response.json(pair)); vi.stubGlobal('fetch', fetch)
  render(<NativeImages selection={selection} />)
  expect(fetch).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Read native images' }))
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(new URL(String(fetch.mock.calls[0][0])).searchParams.get('valid_time')).toBe('2026-09-07T12:00:00.000Z')
  expect(screen.getAllByRole('img')).toHaveLength(2)
  expect(screen.getByRole('region')).toHaveTextContent('Source QC unknown · Scientific freshness unknown')
  expect(screen.getAllByRole('img')[0]).toHaveAttribute('src', pair.images[0].image_url)
})
it('retains the old unexpired pair after failed refresh and withholds failed image revisions', async () => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse(at))
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(pair)).mockResolvedValueOnce(new Response('', { status: 503 })))
  render(<NativeImages selection={selection} />)
  await userEvent.click(screen.getByRole('button', { name: 'Read native images' }))
  await userEvent.click(screen.getByRole('button', { name: 'Refresh native images' }))
  expect(screen.getByRole('status')).toHaveTextContent('previous retained pair remains')
  expect(screen.getAllByRole('img')).toHaveLength(2)
  fireEvent.error(screen.getAllByRole('img')[0])
  expect(screen.getByText(/Rain image revision unavailable/)).toBeVisible()
  expect(screen.getAllByRole('img')).toHaveLength(1)
})
it('expires retained images without automatically reading another pair', async () => {
  vi.useFakeTimers(); vi.setSystemTime(at)
  const fetch = vi.fn(async (_url: string | URL | Request) => Response.json(pair)); vi.stubGlobal('fetch', fetch)
  render(<NativeImages selection={selection} />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Read native images' })) })
  expect(screen.getAllByRole('img')).toHaveLength(2)
  act(() => { vi.advanceTimersByTime(300001) })
  expect(screen.queryAllByRole('img')).toHaveLength(0)
  expect(screen.getByRole('status')).toHaveTextContent('retention expired')
  expect(fetch).toHaveBeenCalledTimes(1)
})
it('rejects substituted native times, sources, phases and external or wrong-revision image URLs', () => {
  expect(isNativeImagePair(pair, selection)).toBe(true)
  for (const bad of [{ ...pair, valid_time: '2026-09-07T12:06:00Z' }, { ...pair, source_id: 'other' }, { ...pair, primary: true },
    { ...pair, images: [pair.images[0], pair.images[0]] }, { ...pair, images: [{ ...pair.images[0], image_url: 'https://example.test/image.gif' }, pair.images[1]] },
    { ...pair, images: [{ ...pair.images[0], image_url: pair.images[0].image_url.replace(revision, 'b'.repeat(64)) }, pair.images[1]] }]) expect(isNativeImagePair(bad, selection)).toBe(false)
  expect(nativeImageEndpoint(selection.sourceId, 'https://example.test/images')).toBe(false)
})
it('aborts an abandoned source-time read and does not prefetch its replacement', async () => {
  let signal: AbortSignal | null = null
  const fetch = vi.fn((_url: unknown, init?: RequestInit) => { signal = init?.signal ?? null; return new Promise<Response>(() => {}) })
  vi.stubGlobal('fetch', fetch)
  const { rerender } = render(<NativeImages key="first" selection={selection} />)
  fireEvent.click(screen.getByRole('button', { name: 'Read native images' }))
  rerender(<NativeImages key="next" selection={{ ...selection, instant: selection.instant + 360000 }} />)
  expect(signal).toMatchObject({ aborted: true })
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Read native images' })).toBeEnabled()
  expect(screen.queryAllByRole('img')).toHaveLength(0)
})
it('withholds a response for another native time and makes no image requests', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ ...pair, valid_time: '2026-09-07T12:06:00Z' })))
  render(<NativeImages selection={selection} />)
  await userEvent.click(screen.getByRole('button', { name: 'Read native images' }))
  expect(screen.getByRole('status')).toHaveTextContent('identity or presentation contract did not match')
  expect(screen.queryAllByRole('img')).toHaveLength(0)
})
