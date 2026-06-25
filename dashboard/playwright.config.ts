// Playwright e2e config for the live Crucible dashboard. We drive the ALREADY
// running dev server (vite on :5180, proxying /api -> backend :8077) — we do not
// start our own server, so there is no `webServer` block. Headless chromium from
// the cached install. Screenshots are captured explicitly in the spec and also
// retained on failure; artifacts land under e2e/__screenshots__ / test-results.

import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  outputDir: "./test-results",
  use: {
    baseURL: "http://localhost:5180",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
})
