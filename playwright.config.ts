import { defineConfig, devices } from "@playwright/test";

// The walkthroughs drive the LIVE Crucible GUI. CRUCIBLE_URL points them at a target;
// it defaults to the local stack on http://127.0.0.1:8099 (uvicorn orchestrator.api:app),
// and can be set to the Render deploy for a remote run.
const BASE = process.env.CRUCIBLE_URL || "http://127.0.0.1:8099";

// Headed + slowMo lets an operator watch the run end to end (PR3 checklist verification
// model); set HEADED=1 to enable. Default is headless so the suite produces its evidence
// (screenshots + trace + HTML report) without a display.
const HEADED = process.env.HEADED === "1";

export default defineConfig({
  testDir: "./tests/walkthroughs",
  fullyParallel: false,
  workers: 1,
  reporter: [["html", { open: "never", outputFolder: "playwright-report" }], ["list"]],
  use: {
    baseURL: BASE,
    headless: !HEADED,
    launchOptions: { slowMo: HEADED ? 250 : 0 },
    screenshot: "on",
    video: "retain-on-failure",
    trace: "on",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
