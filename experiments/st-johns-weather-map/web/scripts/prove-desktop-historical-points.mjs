// Offline API replay: exact Focus times beyond the map timeline, without provider access.
import { chromium } from 'playwright'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import assert from 'node:assert/strict'

const base = process.env.BENCH_URL ?? 'http://127.0.0.1:5257'
const out = process.env.BENCH_PROOF_DIR ?? '/tmp/astraeus-historical-point-proof'
if (!process.env.HISTORICAL_POINT_PROOF_FIXTURE) throw new Error('Supply an actual API replay fixture manifest')
const fixture = JSON.parse(await readFile(process.env.HISTORICAL_POINT_PROOF_FIXTURE, 'utf8'))
const requests = [], errors = [], checks = []
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  for (const [index, item] of fixture.cases.entries()) {
    console.log('Checking', item.product)
    const requestStart = requests.length
    const point = item.point
    assert.ok(point.fields.length > 0, 'Proof requires acquired API fields')
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    page.setDefaultTimeout(10000)
    await page.clock.install({ time: new Date(fixture.reference_time) })
    page.on('pageerror', error => errors.push(String(error)))
    await page.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.origin !== base) return route.abort()
      if (!url.pathname.startsWith('/api/')) return route.continue()
      const path = url.pathname.split('/v0')[1]
      let body = { data_mode: 'fixture', notices: [] }
      if (path === '/catalog') body = fixture.catalog
      else if (path === '/point') {
        requests.push(url.pathname + url.search)
        const exact = Number(url.searchParams.get('latitude')) === point.latitude && Number(url.searchParams.get('longitude')) === point.longitude && url.searchParams.get('product') === item.product && Date.parse(url.searchParams.get('valid_time')) === Date.parse(point.valid_time)
          && (!item.statistic || url.searchParams.get('statistic') === item.statistic && url.searchParams.get('quantile') === (item.quantile == null ? null : String(item.quantile)))
        body = exact ? point : { ...body, fields: [], valid_time: url.searchParams.get('valid_time'), selection: { mode: 'evidence_only', badge: 'Offline replay: no matching request', reason: 'Exact source/time only' } }
      } else if (path === '/layers') body = { ...body, layers: [] }
      else if (path === '/sources/status') body = { ...body, statuses: [] }
      else if (path === '/methods') body = { ...body, methods: [] }
      else if (path === '/timeline') body = { ...body, start: new Date(Date.parse(fixture.reference_time) - 86400000).toISOString(), end: fixture.reference_time, items: [] }
      else if (path === '/registry/sites') body = { sites: [], operational: false, version: 'a'.repeat(64) }
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    })
    console.log('Opening page')
    await page.goto(`${base}/?view=map&lat=${point.latitude}&lon=${point.longitude}&stack=[]`)
    await page.locator('.bench-instant summary').click()
    await page.getByLabel('Instant (ISO, with timezone)').fill(point.valid_time)
    await page.getByRole('button', { name: 'Use instant', exact: true }).click()
    await page.getByRole('button', { name: 'Existing evidence panels', exact: true }).click()
    await page.getByRole('button', { name: 'Workbench', exact: true }).click()
    console.log('Selecting product')
    await page.getByRole('combobox', { name: 'Product', exact: true }).selectOption(item.product)
    if (item.statistic) {
      const selector = page.getByRole('combobox', { name: 'Provider statistic', exact: true })
      assert.equal(await selector.inputValue(), '')
      assert.equal(requests.slice(requestStart).filter(request => new URL(request, base).searchParams.get('product') === item.product).length, 0)
      await selector.selectOption(JSON.stringify({ statistic: item.statistic, quantile: item.quantile ?? null }))
    }
    console.log('Waiting for point badge')
    await page.getByText(point.selection.badge, { exact: true }).first().waitFor()
    await page.getByRole('button', { name: 'Return to desktop Bench', exact: true }).click()
    await page.getByText('Point evidence ledger', { exact: true }).click()
    const field = point.fields.find(value => value.value !== null)
    await page.getByRole('button', { name: new RegExp(`^Inspect ${field.field} from ${field.provenance.source_id}`) }).click()
    const inspector = page.getByRole('complementary', { name: 'Evidence inspector' })
    const detail = name => inspector.locator('dt').filter({ hasText: new RegExp(`^${name}$`) }).locator('..').locator('dd').innerText()
    const provenance = JSON.parse(await detail('Complete returned provenance'))
    assert.deepEqual(provenance, field.provenance)
    if (item.statistic) {
      assert.equal(provenance.ensemble.statistic, item.statistic)
      assert.equal(provenance.ensemble.quantile, item.quantile)
      assert.equal(provenance.run_time, null)
      assert.equal(provenance.quality.status, 'unknown')
      assert.equal(await detail('Run'), 'Not supplied')
    }
    assert.equal(Date.parse(new URL(page.url()).searchParams.get('t')), Date.parse(point.valid_time))
    assert.equal(await page.getByLabel('Instant (ISO, with timezone)').inputValue(), new Date(point.valid_time).toISOString())
    await page.screenshot({ path: `${out}/${index}-native-identity.png` })
    checks.push({ product: item.product, statistic: item.statistic, quantile: item.quantile, selectedTime: point.valid_time, sourceId: field.provenance.source_id, nativeTime: field.provenance.valid_time, dataMode: point.data_mode, completeProvenancePreserved: true })
    await page.close()
  }
  assert.deepEqual(errors, [])
  await writeFile(`${out}/receipt.json`, JSON.stringify({ basis: 'Offline replay of supplied API responses; no new acquisition or live verification', providerRequests: 0, externalRequests: 'blocked', checks, requests, errors }, null, 2))
  console.log(`PASS ${checks.length} exact historical/daily point selections`)
} finally {
  await browser.close()
}
