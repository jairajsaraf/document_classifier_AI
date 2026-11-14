import { defineConfig, devices } from '@playwright/test'

// BASE_URL: the deployed service (or a local container). E2E_UPLOAD=1 also uploads and classifies
// TC1-TC4 through the UI, which spends real API calls (about $0.002 each) and uses the per-IP quota.
// Uses the installed Google Chrome (https://playwright.dev/docs/browsers), so no browser download.
export default defineConfig({
  testDir: '.',
  timeout: 180_000,
  workers: 1,
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: process.env.BASE_URL,
    ...devices['Desktop Chrome'],
    channel: 'chrome',
  },
})
