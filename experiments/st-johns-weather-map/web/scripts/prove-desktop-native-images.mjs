// Actual TestClient metadata and captured producer GIFs replayed offline.
// No provider reads; no claim of current radar or live frontend acquisition.
import { chromium } from 'playwright'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5257'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-native-image-browser-proof'
const fixtureDir = process.env.NATIVE_IMAGE_FIXTURE_DIR
if (!fixtureDir) throw new Error('NATIVE_IMAGE_FIXTURE_DIR must name the external TestClient/captured-image fixture directory')
const pair = JSON.parse(await readFile(`${fixtureDir}/metadata.json`, 'utf8'))
const source = JSON.parse(await readFile(`${fixtureDir}/catalog_source.json`, 'utf8'))
const sourceReceipt = JSON.parse(await readFile(`${fixtureDir}/receipt.json`, 'utf8'))
const images = Object.fromEntries(await Promise.all(pair.images.map(async (image) => [image.image_url, await readFile(`${fixtureDir}/${image.phase}.gif`)])))
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
await page.clock.install({ time: new Date(Date.parse(pair.retained_until) - 60000) })
const requests = []; const errors = []; let failRefresh = false
page.on('pageerror', (error) => errors.push(String(error)))
await page.route('**/*', async (route) => {
  const url = new URL(route.request().url())
  if (url.origin !== new URL(base).origin) return route.abort()
  if (!url.pathname.startsWith('/api/')) return route.continue()
  const path = url.pathname.split('/v0')[1]
  if (url.pathname === source.native_image_endpoint) {
    requests.push(url.pathname + url.search)
    assert.equal(Date.parse(url.searchParams.get('valid_time')), Date.parse(pair.valid_time))
    return route.fulfill({ status: failRefresh ? 503 : 200, contentType: 'application/json', body: JSON.stringify(failRefresh ? { detail: 'Exact native pair unavailable' } : pair) })
  }
  if (images[url.pathname]) { requests.push(url.pathname); return route.fulfill({ contentType: 'image/gif', body: images[url.pathname] }) }
  let body = { data_mode: 'fixture', notices: ['Offline captured-image fixture; not current radar'] }
  if (path === '/catalog') body = { ...body, sources: [source] }
  else if (path === '/point') body = { ...body, fields: [], operational: false, latitude: 47.5615, longitude: -52.7126, valid_time: pair.valid_time, selection: { mode: 'evidence_only', badge: 'Offline captured-image fixture', reason: 'Native September 6, 2026 04:54 UTC images; not current radar' } }
  else if (path === '/layers') body = { ...body, layers: [] }
  else if (path === '/sources/status') body = { ...body, statuses: [] }
  else if (path === '/timeline') body = { ...body, start: pair.valid_time, end: pair.valid_time, items: [] }
  else if (path === '/methods') body = { ...body, methods: [] }
  else if (path === '/registry/sites') body = { operational: false, sites: [], version: 'a'.repeat(64), notice: 'Fixture only' }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
})
try {
  await page.goto(`${base}/?view=sources&lat=47.5615&lon=-52.7126&t=${pair.valid_time}&stack=[]`)
  await page.getByRole('button', { name: `Inspect source ${source.id}`, exact: true }).click()
  const region = page.getByRole('region', { name: 'Native image evidence' })
  await region.waitFor()
  assert.deepEqual(requests, [])
  await region.getByRole('button', { name: 'Read native images', exact: true }).click()
  await region.getByRole('img').first().waitFor()
  await page.waitForFunction(() => [...document.querySelectorAll('.native-images img')].length === 2 && [...document.querySelectorAll('.native-images img')].every((image) => image.complete && image.naturalWidth === 580 && image.naturalHeight === 480))
  assert.equal(requests.length, 3)
  assert.ok((await region.innerText()).includes('Source QC unknown · Scientific freshness unknown'))
  await region.getByRole('img').first().scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${output}/native-rain.png` })
  await region.getByRole('img').last().scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${output}/native-snow.png` })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  failRefresh = true
  await region.getByRole('button', { name: 'Refresh native images', exact: true }).click()
  await region.getByText(/previous retained pair remains/).waitFor()
  assert.equal(await region.getByRole('img').count(), 2)
  assert.equal(requests.length, 4)
  assert.ok(requests.at(-1).includes('refresh=true'))
  await page.clock.runFor(60001)
  await region.getByText(/Image revision retention expired/).waitFor()
  assert.equal(await region.getByRole('img').count(), 0)
  assert.equal(requests.length, 4)
  await region.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${output}/native-pair-expired.png` })
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ basis: 'Offline actual TestClient metadata plus captured native GIF bytes, not current radar', providerRequests: 0, externalRequests: 'blocked', nativeValidTime: pair.valid_time, revision: pair.pair_revision, imageHashes: Object.fromEntries(Object.entries(images).map(([path, bytes]) => [path, createHash('sha256').update(bytes).digest('hex')])), sourceReceipt, checks: ['declared endpoint only', 'no metadata/image prefetch', 'exact selected time', 'Rain/Snow original 580x480 image bytes', 'unknown QC/freshness and non-primary notice', 'failed refresh retains unexpired revision', 'fixed expiry removes images without acquisition'], requests, errors }, null, 2))
  console.log(`PASS: native images browser proof ${output}`)
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` })
  await writeFile(`${output}/failure.txt`, await page.locator('body').innerText())
  throw error
} finally { await browser.close() }
