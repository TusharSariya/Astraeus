// Bounded live observation proof: real catalogue and radar/lightning images; other API panels
// deliberately unavailable so this check cannot trigger unrelated acquisition.
import { chromium } from 'playwright'
import { mkdir, writeFile, mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5197'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-observation-inventory-proof'
await mkdir(output, { recursive: true })
const context = await chromium.launchPersistentContext(await mkdtemp(`${tmpdir()}/layer-live-chrome-`), { channel: 'chrome', headless: true, viewport: { width: 1440, height: 900 } })
const page = await context.newPage(), requests = [], responses = [], errors = []
const ids = ['eccc-radar-radar', 'eccc-lightning-lightning']
page.on('pageerror', error => errors.push(String(error)))
page.on('response', response => {
  if (ids.some(id => response.url().includes(`/layers/${id}/raster`))) responses.push({ url: response.url(), status: response.status(), headers: Object.fromEntries(Object.entries(response.headers()).filter(([key]) => key.startsWith('x-weather-') || ['content-type', 'cache-control'].includes(key))) })
})
await page.route('**/*', async route => {
  const url = new URL(route.request().url())
  if (url.hostname === 'tiles.openfreemap.org') return route.continue()
  if (url.origin !== new URL(base).origin) return route.abort()
  if (!url.pathname.startsWith('/api/')) return route.continue()
  const path = url.pathname.split('/v0')[1]
  if (path.endsWith('/features') && ids.some(id => path.includes(id))) requests.push(path + url.search)
  if ((path === '/layers' && url.searchParams.get('product') !== 'CAP') || ids.some(id => path === `/layers/${id}/raster`)) {
    requests.push(path + url.search)
    return route.continue()
  }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data_mode: 'unavailable', layers: [], notices: ['Bounded live-layer check: unrelated API panels intentionally withheld'] }) })
})
try {
  const at = new Date().toISOString()
  await page.goto(`${base}/?t=${at}&stack=${encodeURIComponent(JSON.stringify(ids.map(id => ({ id, opacity: .85, visible: true }))))}`)
  await page.getByRole('button', { name: 'Layers', exact: true }).click()
  await page.waitForFunction(() => [...document.querySelectorAll('.bench-layer-state')].length === 2 && [...document.querySelectorAll('.bench-layer-state')].every(row => row.textContent?.startsWith('Frame ')), null, { timeout: 45000 })
  for (const id of ids) assert.ok(responses.some(response => response.url.includes(`/layers/${id}/raster`) && response.status === 200 && response.headers['content-type']?.includes('image/png')))
  assert.equal(requests.some(path => path.includes('/features')), false)
  assert.equal(requests.some(path => path.includes('2026-09-03')), false)
  await page.locator('.bench-settings > summary').click()
  await page.getByRole('button', { name: 'dark', exact: true }).click()
  await page.locator('.bench-settings > summary').click()
  await page.screenshot({ path: `${output}/radar-lightning-current-frames.png` })
  await page.locator('.bench-stack ol > li > details > summary').first().click()
  await page.screenshot({ path: `${output}/native-image-details.png` })
  await page.getByRole('button', { name: 'Close Layers', exact: true }).click()
  await page.getByRole('button', { name: 'Tracks', exact: true }).click()
  await page.screenshot({ path: `${output}/image-timestamp-tracks.png` })
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ at, scope: 'Live catalogue and radar/lightning imagery; unrelated API responses explicitly unavailable; live OpenFreeMap tiles', requests, responses, errors }, null, 2))
  console.log(`PASS: ${output}`)
} finally { await context.close() }
