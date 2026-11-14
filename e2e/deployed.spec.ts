import { expect, test, type Locator, type Page } from '@playwright/test'
import path from 'node:path'

const PKG = path.resolve(__dirname, '..', 'HitachiDS_Datathon_Challenges_Package')
// Golden labels from eval/golden.csv. TC5 is left out on purpose (see docs/VERIFY.md).
const CASES = [
  { id: 'TC1', file: 'TC1_Sample_Public_Marketing_Document.pdf', sensitivity: 'Public', safety: 'Safe' },
  { id: 'TC2', file: 'TC2_Filled_In_Employement_Application.pdf', sensitivity: 'Highly Sensitive', safety: 'Safe' },
  { id: 'TC3', file: 'TC3_Sample_Internal_Memo.pdf', sensitivity: 'Confidential', safety: 'Safe' },
  { id: 'TC4', file: 'TC4_ Stealth_Fighter_With_Part_Names.pdf', sensitivity: 'Confidential', safety: 'Safe' },
]

test.describe.configure({ mode: 'serial' })

test.beforeAll(async ({ request }) => {
  // a free instance sleeps after 15 idle minutes and takes about a minute to wake
  const t0 = Date.now()
  await expect
    .poll(async () => (await request.get('/health', { timeout: 20_000 }).catch(() => null))?.status(), {
      timeout: 170_000,
      intervals: [2_000],
    })
    .toBe(200)
  console.log(`WAKE: /health answered after ${((Date.now() - t0) / 1000).toFixed(1)} s`)
})

/** Open a row's document view and assert label, safety and at least one citation whose quote was found on its page. */
async function checkDocument(page: Page, c: (typeof CASES)[number], row: Locator) {
  await expect(row).toContainText(c.sensitivity)
  await expect(row.getByText(c.safety, { exact: true })).toBeVisible()
  await row.getByRole('link').click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(c.file)
  const label = page.locator('dl').filter({ hasText: 'Sensitivity' })
  await expect(label).toContainText(c.sensitivity)
  await expect(label.getByText(c.safety, { exact: true })).toBeVisible() // exact: "Safety" and "Unsafe" also contain the letters
  const ticked = page.getByRole('button').filter({ has: page.getByLabel('quote found on this page') })
  await expect(ticked.first(), `${c.id}: a citation whose quote was found on the cited page`).toBeVisible()
  await ticked.first().click()
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 60_000 }) // PDF.js drew the cited page
  console.log(`${c.id}: ${c.sensitivity}, ${c.safety}, ${await ticked.count()} citation(s) with the quote found`)
}

test('queue shows the seeded test cases with the model name', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await expect(page.getByText('claude-haiku-5-5')).toBeVisible()
  for (const c of CASES) await expect(page.getByRole('row', { name: new RegExp(c.file) })).toHaveCount(1)
  await expect(page.getByText(/erased when this free demo goes to sleep/)).toBeVisible()
})

for (const c of CASES) {
  test(`seeded ${c.id}: label, safety and a valid citation`, async ({ page }) => {
    await page.goto('/')
    await checkDocument(page, c, page.getByRole('row', { name: new RegExp(c.file) }))
  })
}

test('the PDF.js worker is served gzipped', async ({ page }) => {
  const worker = page.waitForResponse((r) => /pdf\.worker.*\.mjs/.test(r.url()))
  await page.goto('/')
  await page.getByRole('row', { name: /TC3_/ }).getByRole('link').click()
  const r = await worker
  console.log(`worker: ${r.status()} content-encoding=${r.headers()['content-encoding']}`)
  expect(r.headers()['content-encoding']).toBe('gzip')
})

test('document ids are not guessable', async ({ request }) => {
  expect((await request.get('/api/documents/1/file')).status()).toBe(404)
  expect((await request.get('/api/documents/1')).status()).toBe(404)
})

test.describe('uploads (spend real API calls)', () => {
  test.skip(!process.env.E2E_UPLOAD, 'set E2E_UPLOAD=1')

  for (const c of CASES) {
    test(`upload ${c.id} through the UI`, async ({ page }) => {
      await page.goto('/')
      await page.getByLabel('PDF to classify').setInputFiles(path.join(PKG, c.file))
      await page.getByRole('button', { name: 'Upload and classify' }).click()
      await expect(page.getByRole('status')).toContainText('Classified and added to the queue', { timeout: 120_000 })
      // the queue sorts newest first, so the first matching row is this upload, not the seeded one
      await checkDocument(page, c, page.getByRole('row', { name: new RegExp(c.file) }).first())
    })
  }

  test('per-IP limit answers 429 and a forged X-Forwarded-For does not reset it', async ({ request }) => {
    const pdf = { name: 'guard-probe.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 probe') }
    const codes: number[] = []
    for (let i = 0; i < 3; i++) codes.push((await request.post('/api/documents/upload', { multipart: { file: pdf } })).status())
    const forged = await request.post('/api/documents/upload', {
      multipart: { file: pdf },
      headers: { 'x-forwarded-for': '203.0.113.7' },
    })
    console.log(`upload statuses after the four UI uploads: ${codes.join(', ')}, forged header: ${forged.status()}`)
    expect(codes).toContain(429)
    expect(forged.status()).toBe(429)
  })
})
