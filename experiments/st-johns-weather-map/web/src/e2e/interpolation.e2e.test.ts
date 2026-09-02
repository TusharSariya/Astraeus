/** Plan H3: the end-to-end pixel check.
 *
 *  Every other suite in this repo stubs `fetch`. This one does not: it renders
 *  the real `App` in a real Chrome against the real API, turns interpolation
 *  on, scrubs to a position strictly BETWEEN two published HRDPS frames, walks
 *  the interpolation menu, and reads the MapLibre canvas back after each
 *  selection. What it asserts is the one thing a unit test cannot: that
 *  choosing a different construction changes the pixels on the map, and that a
 *  construction which did NOT change them says so on the map.
 *
 *  It is gated twice, because a red test nobody can run is worse than no test:
 *  the vitest project only exists under `VITE_E2E=1` (see vite.config.ts,
 *  which is also where MapPanel's `preserveDrawingBuffer` comes from - the
 *  canvas cannot be read back without it), and the suite skips itself unless
 *  the API answers on localhost:8000.
 *
 *      VITE_E2E=1 npx vitest run --project e2e
 */
import { cleanup, render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import userEvent from '@testing-library/user-event'
import { createElement } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import App from '../App'
import '../styles.css'

const PREFIX = '/api/experiments/weather/v0'
/** The layer the plan names: HRDPS total cloud, rendered locally, the only
 *  kind of layer that draws through the interpolation shader at all. */
const LAYER_ID = (import.meta.env.VITE_E2E_LAYER as string | undefined) || 'eccc-hrdps-surface-total-cloud'

/** Whether the stack is up. Asked once, at module load, so the skip decision
 *  is made before Playwright is asked to render anything. */
const reachable = await (async () => {
  try {
    const response = await fetch(`${PREFIX}/layers`, { headers: { Accept: 'application/json' } })
    return response.ok
  } catch {
    return false
  }
})()

interface PublishedLayer {
  id: string
  title: string
  /** `/layers` publishes plain ISO strings today; the objects are tolerated so
   *  a schema that grows a per-frame record does not silently zero this out. */
  times?: Array<string | { time: string }>
}

/** FNV-1a over the canvas bytes. A hash, not a diff: the assertion is only
 *  ever "the same picture" or "a different picture", and a full-frame
 *  comparison would make a failure unreadable in a terminal. */
function hashPixels(canvas: HTMLCanvasElement): string {
  const data = canvas.toDataURL('image/png')
  let hash = 0x811c9dc5
  for (let index = 0; index < data.length; index += 1) {
    hash ^= data.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return `${hash.toString(16).padStart(8, '0')}:${data.length}`
}

/** MapLibre's own canvas, by its own class. The pane holds more than one
 *  canvas (the deck.gl overlay adds its own), and the first one in document
 *  order is not necessarily the one the interpolation layer draws into. */
const mapCanvas = (): HTMLCanvasElement => {
  const canvas = document.querySelector<HTMLCanvasElement>('.map-pane canvas.maplibregl-canvas')
  if (!canvas) throw new Error('no MapLibre canvas in the pane')
  return canvas
}

/** Two animation frames plus a beat: MapLibre repaints on its own schedule,
 *  and the flow layer repaints again when a texture finishes decoding. */
const settle = async (): Promise<void> => {
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  await new Promise((resolve) => setTimeout(resolve, 600))
}

const mapNote = (): string => document.querySelector('.map-frame-notes')?.textContent ?? ''

/** The canvas hash, once it has stopped changing. Textures land one after
 *  another (motion, then the Hermite tangents, then the method's own suffix),
 *  and each one repaints: hashing the first frame after the disclosure appears
 *  would compare a half-loaded picture of one construction with a finished
 *  picture of the next, and the difference would be timing, not arithmetic. */
const stableHash = async (timeout: number): Promise<string> => {
  const deadline = Date.now() + timeout
  let previous = hashPixels(mapCanvas())
  while (Date.now() < deadline) {
    await settle()
    const current = hashPixels(mapCanvas())
    if (current === previous) return current
    previous = current
  }
  return previous
}

/** The note that means the shader is actually advecting: interpolating BETWEEN
 *  two frames along a motion field the server derived. The plain-crossfade
 *  wording is the honest fallback for a pair with no motion, and comparing
 *  hashes across methods there would compare the same picture with itself. */
const ADVECTING = /temporally interpolated for display/i
const NO_MOTION = /no derived motion field for this pair/i

/** Waits for the map's own disclosure to say it is advecting. The server may be
 *  deriving the motion field on demand, which is why this is generous. */
const waitForAdvection = async (timeout: number): Promise<boolean> => {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const note = mapNote()
    if (ADVECTING.test(note) && !NO_MOTION.test(note)) return true
    await settle()
  }
  return false
}

/** Waits for the disclosure to name the method the SERVER says it served - the
 *  only signal that the newly selected construction's fields have landed. Not
 *  waiting for it is the trap this suite is most likely to fall into: the
 *  previous method's note still reads "advecting" while its texture is still on
 *  the GPU, so a hash taken too early compares one picture with itself and the
 *  whole check passes for the wrong reason. The default construction is the one
 *  the disclosure deliberately leaves unnamed, so it is recognised by absence. */
const waitForServedMethod = async (id: string, defaultMethod: string, timeout: number): Promise<boolean> => {
  const deadline = Date.now() + timeout
  const named = new RegExp(`interpolation method "${escapeRegExp(id)}"`)
  while (Date.now() < deadline) {
    const note = mapNote()
    if (ADVECTING.test(note) && !NO_MOTION.test(note)) {
      if (id === defaultMethod ? !/interpolation method "/.test(note) : named.test(note)) return true
    }
    await settle()
  }
  return false
}

describe.skipIf(!reachable)('interpolation, end to end, pixels read back from the map', () => {
  const restoreFetch: Array<() => void> = []
  afterEach(() => {
    restoreFetch.splice(0).forEach((restore) => restore())
    cleanup()
  })

  it('draws a different picture for each construction, and says so when one reduced to the default', async () => {
    const layers = (await (await fetch(`${PREFIX}/layers`)).json()) as { layers?: PublishedLayer[] }
    const layer = (layers.layers ?? []).find((item) => item.id === LAYER_ID)
    expect(layer, `${LAYER_ID} is not published by this deployment`).toBeTruthy()
    const times = (layer?.times ?? [])
      .map((frame) => Date.parse(typeof frame === 'string' ? frame : frame.time))
      .filter((ms) => Number.isFinite(ms))
      .sort((a, b) => a - b)
    expect(times.length, 'a pair of frames is needed to interpolate between').toBeGreaterThan(1)

    // Every /flow request the app makes, with its status. Printed only when
    // an assertion is about to fail: "the picture did not change" and "the
    // request was never made" look identical on the map, and the difference is
    // the first thing the next reader needs.
    const seen: string[] = []
    const realFetch = window.fetch.bind(window)
    restoreFetch.push(() => { window.fetch = realFetch })
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(typeof input === 'string' ? input : input instanceof URL ? input.href : (input as Request).url)
      if (url.includes('/flow')) seen.push(url)
      return realFetch(input as RequestInfo, init).then((r: Response) => { if (url.includes('/flow')) seen[seen.indexOf(url)] = `${r.status} ${url}`; return r }, (e: unknown) => { if (url.includes('/flow')) seen[seen.indexOf(url)] = `ERR(${(e as Error).name}) ${url}`; throw e })
    }) as typeof window.fetch
    render(createElement(App))
    await userEvent.click(await screen.findByRole('button', { name: /Interpolate forecast . display only/ }))

    // The layer drawer, then the layer itself. Nothing here invents a layer:
    // the row is found by the title the API published for it.
    await userEvent.click(await screen.findByRole('button', { name: /^Layers \(/ }))
    // By the exact title the API published for THIS layer id: several products
    // publish a "total cloud" layer, and turning on the wrong one would compare
    // pictures of a grid the plan never named.
    const row = await screen.findByRole('checkbox', { name: new RegExp(escapeRegExp(layer!.title)) })
    if (!(row as HTMLInputElement).checked) await userEvent.click(row)

    // Scrub to a midpoint BETWEEN two published frames. The slider's unit is
    // minutes from the reference instant, so each candidate is tried until the
    // map itself says it is interpolating - which is the only reliable signal
    // that the position is mid-pair rather than exactly on a frame.
    const slider = await screen.findByLabelText('Valid timeline scrubber')
    const now = Date.now()
    const midpoints = times
      .slice(0, -1)
      .map((time, index) => Math.round(((time + times[index + 1]) / 2 - now) / 60000))
      .filter((minutes) => minutes > Number((slider as HTMLInputElement).min) && minutes < Number((slider as HTMLInputElement).max))
    let interpolating = false
    for (const minutes of midpoints) {
      fireEvent.change(slider, { target: { value: String(minutes) } })
      if (await waitForAdvection(20000)) {
        interpolating = true
        break
      }
    }
    expect(
      interpolating,
      `no scrub position between two ${LAYER_ID} frames drew through a derived motion field; note read: ${mapNote()}`,
    ).toBe(true)

    // Walk the menu. Only the entries this deployment actually offers are
    // visited: a method the registry has retired is not a failure here, it is
    // simply absent, and this suite reports what it found.
    const menu = await screen.findByRole('button', { name: /^Interpolation:/ })
    const readings: Record<string, { hash: string; note: string }> = {}
    const titles = new Map<string, string>()
    const methods = (await (await fetch(`${PREFIX}/methods`)).json()) as {
      default_method?: string
      methods?: Array<{ id: string; title: string; enabled?: boolean; generative?: boolean; generation_disabled?: boolean }>
    }
    const defaultMethod = methods.default_method ?? 'baseline'
    for (const method of methods.methods ?? []) {
      if (method.enabled === false || method.generation_disabled) continue
      titles.set(method.id, method.title)
      // The panel stays open across a selection, so this toggles it only when
      // it is closed - clicking unconditionally would shut it on every method
      // after the first and find nothing to select.
      if (menu.getAttribute('aria-expanded') !== 'true') await userEvent.click(menu)
      // Non-generative entries are radios; a generative one takes the two-click
      // confirm, which is exactly the reader-facing gate carve-out (d) requires.
      const radio = screen.queryByRole('radio', { name: new RegExp(escapeRegExp(method.title)) })
      if (radio) {
        await userEvent.click(radio)
      } else {
        const arm = screen.getByRole('button', { name: 'select' })
        await userEvent.click(arm)
        await userEvent.click(screen.getByRole('button', { name: 'confirm generated?' }))
      }
      // Wait for the server's own answer to reach the disclosure before the
      // canvas is read: a hash taken mid-fetch would compare two pictures of
      // the same construction and pass for the wrong reason.
      const ok = await waitForServedMethod(method.id, defaultMethod, 30000)
      // eslint-disable-next-line no-console
      if (!ok) console.log(`[H3 debug] flow requests seen:\n${seen.filter((u) => u.includes('texture=motion')).join('\n')}`)
      expect(
        ok,
        `"${method.id}" never reached an advected picture the server named as its own; note read: ${mapNote()}`,
      ).toBe(true)
      await settle()
      readings[method.id] = { hash: await stableHash(15000), note: mapNote() }
      // eslint-disable-next-line no-console
      console.log(`[H3 readback] ${method.id} -> ${readings[method.id].hash}\n            note: ${readings[method.id].note.slice(0, 400)}`)
    }

    // 1. Every non-default construction is judged by the server's own verdict
    //    for THIS layer. Where the derive admitted the method's term
    //    (`reduced_to_default` false) the pixels must differ from the
    //    baseline's: equal hashes there is the exact failure the plan exists
    //    to catch, a menu entry that renames the baseline's picture. Where the
    //    fixed-control gate refused the term the pixels must be exactly the
    //    baseline's AND the map must say so. Both outcomes are honest; drawing
    //    a difference the server did not admit, or hiding a reduction, is not.
    const served = (await (await fetch(`${PREFIX}/methods`)).json()) as {
      methods: { id: string; scores: { layer_id: string; reduced_to_default: boolean; applied: Record<string, boolean> }[] }[]
    }
    const verdict = (id: string) => served.methods.find((m) => m.id === id)?.scores.find((s) => s.layer_id === LAYER_ID)
    // eslint-disable-next-line no-console
    console.log(`[H3 verdicts] ${Object.keys(readings).map((id) => `${id}: ${JSON.stringify(verdict(id) ?? null)}`).join('\n              ')}`)
    let admittedSomewhere = 0
    for (const id of Object.keys(readings)) {
      if (id === 'baseline' || !('baseline' in readings)) continue
      const score = verdict(id)
      expect(score, `"${id}" has no served score for ${LAYER_ID}`).toBeTruthy()
      if (score!.reduced_to_default) {
        expect(readings[id].hash, `"${id}" was refused by the gate yet drew something other than the baseline`).toBe(readings.baseline.hash)
        expect(readings[id].note, `"${id}" drew the baseline without disclosing it`).toMatch(/reduced to the default/i)
      } else {
        admittedSomewhere += 1
        expect(readings[id].hash, `"${id}" was admitted by the gate yet drew the baseline's pixels`).not.toBe(readings.baseline.hash)
        expect(readings[id].note, `"${id}" drew its own picture but the map says it reduced`).not.toMatch(/reduced to the default/i)
      }
    }
    // eslint-disable-next-line no-console
    console.log(`[H3] ${admittedSomewhere} non-default construction(s) admitted on ${LAYER_ID} this cycle`)

    // 3. A generated picture names itself as GENERATED wherever it is actually
    //    drawn. A generative method the gate refused draws the baseline and is
    //    named as reduced (checked above); calling that GENERATED would be a
    //    disclosure of a picture that is not on the screen.
    if ('residual-generative' in readings && verdict('residual-generative') && !verdict('residual-generative')!.reduced_to_default) {
      expect(readings['residual-generative'].note).toMatch(/GENERATED/)
    }
  }, 180000)
})

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
