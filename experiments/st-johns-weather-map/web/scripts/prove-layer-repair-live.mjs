// Bounded live layer proof: real catalogue and cloud raster; other API panels
// deliberately unavailable so this check cannot trigger unrelated acquisition.
import { chromium } from 'playwright'
import { mkdir, writeFile, mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5197'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-layer-live-proof'
await mkdir(output, { recursive: true })
const context = await chromium.launchPersistentContext(await mkdtemp(`${tmpdir()}/layer-live-chrome-`), { channel: 'chrome', headless: true, viewport: { width: 1440, height: 900 } })
const page = await context.newPage(), requests = [], responses = [], errors = []
const cloudId = 'geomet-live-hrdps-nt', retiredId = 'eccc-hrdps-surface-total-cloud'
page.on('pageerror', error => errors.push(String(error)))
page.on('response', response => {
  if (response.url().includes(`/layers/${cloudId}/raster`)) responses.push({ url: response.url(), status: response.status(), headers: Object.fromEntries(Object.entries(response.headers()).filter(([key]) => key.startsWith('x-weather-') || ['content-type', 'cache-control'].includes(key))) })
})
await page.route('**/*', async route => {
  const url = new URL(route.request().url())
  if (url.hostname === 'tiles.openfreemap.org') return route.continue()
  if (url.origin !== new URL(base).origin) return route.abort()
  if (!url.pathname.startsWith('/api/')) return route.continue()
  const path = url.pathname.split('/v0')[1]
  if ((path === '/layers' && url.searchParams.get('product') !== 'CAP') || path === `/layers/${cloudId}/raster`) {
    requests.push(path + url.search)
    return route.continue()
  }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data_mode: 'unavailable', layers: [], notices: ['Bounded live-layer check: unrelated API panels intentionally withheld'] }) })
})
try {
  const at = new Date().toISOString()
  await page.goto(`${base}/?t=${at}&stack=${encodeURIComponent(JSON.stringify([{ id: retiredId, opacity: .85, visible: true }]))}`)
  await page.getByRole('button', { name: 'Layers', exact: true }).click()
  const use = page.getByRole('button', { name: /^Use HRDPS total cloud/ })
  await use.waitFor({ timeout: 45000 })
  await page.screenshot({ path: `${output}/live-retired-selection.png` })
  await use.click()
  await page.waitForFunction(() => document.querySelector('.bench-layer-state')?.textContent?.startsWith('Frame '), null, { timeout: 45000 })
  assert.ok(responses.some(response => response.status === 200 && response.headers['content-type']?.includes('image/png')))
  assert.equal(requests.some(path => path.includes(retiredId)), false)
  assert.equal(JSON.parse(new URL(page.url()).searchParams.get('stack'))[0].id, cloudId)
  await page.screenshot({ path: `${output}/live-cloud-drawn.png` })
  await page.locator('.bench-stack ol > li > details > summary').click()
  await page.screenshot({ path: `${output}/live-cloud-details.png` })
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ at, scope: 'Live catalogue and cloud imagery; unrelated API responses explicitly unavailable; live OpenFreeMap tiles', requests, responses, errors }, null, 2))
  console.log(`PASS: ${output}`)
} finally { await context.close() }
