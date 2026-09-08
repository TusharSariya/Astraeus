// Actual TestClient responses replayed offline. No provider requests.
import { chromium } from 'playwright'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5257'
const output = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-ecmwf-browser-proof'
const fixtureDir = process.env.ECMWF_API_FIXTURE_DIR
if (!fixtureDir) throw new Error('ECMWF_API_FIXTURE_DIR must name the actual TestClient replay fixture directory')
const catalog = JSON.parse(await readFile(`${fixtureDir}/catalog.json`, 'utf8'))
const points = { IFS: JSON.parse(await readFile(`${fixtureDir}/pointIFS.json`, 'utf8')), 'AIFS Single': JSON.parse(await readFile(`${fixtureDir}/pointAIFS.json`, 'utf8')) }
const sourceReceipt = JSON.parse(await readFile(`${fixtureDir}/receipt.json`, 'utf8'))
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
await page.clock.install({ time: new Date('2026-09-07T22:44:00Z') })
const requests = []; const errors = []
page.on('pageerror', (error) => errors.push(String(error)))
await page.route('**/*', async (route) => {
  const url = new URL(route.request().url())
  if (url.origin !== new URL(base).origin) return route.abort()
  if (!url.pathname.startsWith('/api/')) return route.continue()
  const path = url.pathname.split('/v0')[1]
  let body = { data_mode: 'fixture', notices: ['Offline API replay of captured ECMWF payloads; no new live retrieval'] }
  if (path === '/catalog') body = catalog
  else if (path === '/point') {
    requests.push(url.pathname + url.search)
    body = points[url.searchParams.get('product')] ?? { ...body, fields: [], operational: false, valid_time: points.IFS.valid_time, selection: { mode: 'evidence_only', badge: 'Offline fixture', reason: 'Select the declared model' } }
  } else if (path === '/layers') body = { ...body, layers: [] }
  else if (path === '/sources/status') body = { ...body, statuses: [] }
  else if (path === '/timeline') body = { ...body, start: points.IFS.valid_time, end: points.IFS.valid_time, items: [] }
  else if (path === '/methods') body = { ...body, methods: [] }
  else if (path === '/registry/sites') body = { operational: false, sites: [], version: 'a'.repeat(64), notice: 'Offline fixture' }
  return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
})
try {
  for (const [product, point] of Object.entries(points)) {
    await page.goto(`${base}/?view=map&lat=${point.latitude}&lon=${point.longitude}&t=${point.valid_time}&stack=[]`)
    await page.getByRole('button', { name: 'Existing evidence panels', exact: true }).click()
    await page.locator('summary').filter({ hasText: /^Forecast model/ }).click()
    await page.locator('.model-buttons button').filter({ has: page.locator('strong').filter({ hasText: new RegExp(`^${product}$`) }) }).click()
    await page.getByText(point.selection.badge, { exact: true }).first().waitFor()
    await page.getByRole('button', { name: 'Return to desktop Bench', exact: true }).click()
    await page.getByText('Point evidence ledger', { exact: true }).click()
    const cloud = point.fields.find((field) => field.field === 'total_cloud_geometric')
    await page.getByRole('button', { name: new RegExp(`^Inspect total_cloud_geometric from ${cloud.provenance.source_id}`) }).click()
    const inspector = page.getByRole('complementary', { name: 'Evidence inspector' })
    const detail = async (name) => inspector.locator('dt').filter({ hasText: new RegExp(`^${name}$`) }).locator('..').locator('dd').innerText()
    const returned = JSON.parse(await detail('Complete returned provenance'))
    assert.equal(returned.source_id, cloud.provenance.source_id)
    assert.equal(returned.original_units, cloud.provenance.original_units)
    assert.equal(returned.normalized_units, cloud.provenance.normalized_units)
    assert.equal(returned.run_time, cloud.provenance.run_time)
    assert.equal(returned.valid_time, cloud.provenance.valid_time)
    assert.equal(returned.source_display_primary, false)
    const receipt = JSON.parse(await detail('Source acquisition receipt'))
    assert.equal(receipt.source_id, cloud.provenance.source_id)
    assert.equal(receipt.transfer_count, cloud.provenance.source_acquisition.transport_receipts.length)
    assert.equal(receipt.normalized_sha256, cloud.provenance.source_acquisition.normalized_sha256)
    assert.ok(requests.some((request) => {
      const url = new URL(request, base)
      return url.searchParams.get('product') === product && Date.parse(url.searchParams.get('valid_time')) === Date.parse(point.valid_time)
        && Number(url.searchParams.get('latitude')) === point.latitude && Number(url.searchParams.get('longitude')) === point.longitude
    }))
    await page.screenshot({ path: `${output}/${product.replaceAll(' ', '-')}-cloud-provenance.png` })
    await inspector.getByText('Source acquisition receipt', { exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: `${output}/${product.replaceAll(' ', '-')}-acquisition-receipt.png` })
  }
  assert.deepEqual(errors, [])
  await writeFile(`${output}/receipt.json`, JSON.stringify({ basis: 'Offline actual TestClient API responses from current captured ECMWF bytes, not a new live acquisition', weatherProviderRequests: 0, externalRequests: 'blocked', sourceReceipt, checks: ['declared IFS/AIFS Single point selectors', 'exact point/time query', 'distinct native cloud units retained', 'native run and valid time', 'non-primary provenance', 'safe acquisition receipt identity/hash/transfer counts'], requests, errors }, null, 2))
  console.log(`PASS: ECMWF browser proof ${output}`)
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` })
  await writeFile(`${output}/failure.txt`, await page.locator('body').innerText())
  throw error
} finally { await browser.close() }
