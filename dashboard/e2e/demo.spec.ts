// End-to-end validation of the LIVE Crucible dashboard — the operator's demo
// gate. We drive a real chromium against the running dev server (:5180, /api ->
// :8077) and prove the five demo flows with real assertions (chart series
// present, confirm dialog visible, status transitions), capturing a screenshot
// at each key step. Run IDs are resolved at runtime from GET /runs so the spec
// is not pinned to a stale id.

import { expect, test, type Page } from "@playwright/test"

const API = "http://localhost:8077"
const SHOTS = "e2e/__screenshots__"

type RunSummary = { run_id: string; target: string; status: string; rounds: number }

async function listRuns(page: Page): Promise<RunSummary[]> {
  const res = await page.request.get(`${API}/runs`)
  expect(res.ok(), "GET /runs should succeed").toBeTruthy()
  const body = await res.json()
  return body.runs as RunSummary[]
}

// A populated recharts <Line> renders a single SVG path with a non-trivial "d"
// attribute (multiple line segments). An empty series renders no path or a
// path with an empty/degenerate "d". We assert the path exists and has real
// geometry so a blank chart fails honestly rather than passing on "rendered".
async function expectChartPopulated(page: Page, testid: string, label: string) {
  const chart = page.getByTestId(testid)
  await expect(chart, `${label} container present`).toBeVisible()
  const path = chart.locator("path.recharts-line-curve")
  await expect(path, `${label} line path present`).toHaveCount(1, { timeout: 15_000 })
  const d = await path.getAttribute("d")
  expect(d, `${label} line path has geometry`).toBeTruthy()
  // A real multi-point series has several "L"/"C" commands; a single point or
  // empty series does not. Require at least a couple of segments.
  const segments = (d ?? "").match(/[LC]/g)?.length ?? 0
  expect(segments, `${label} has >=2 plotted segments (d=${(d ?? "").slice(0, 40)}…)`).toBeGreaterThanOrEqual(2)
}

// Find a completed run to exercise the SSE-replay repopulation path.
async function completedRunId(page: Page): Promise<string> {
  const runs = await listRuns(page)
  const done = runs.find((r) => r.status === "complete")
  expect(done, "expected at least one completed run for replay validation").toBeTruthy()
  return done!.run_id
}

test.describe("Crucible dashboard — demo gate", () => {
  test("Flow 1 — app loads, runs list renders real runs", async ({ page }) => {
    const runs = await listRuns(page)
    expect(runs.length, "backend reports >=1 run").toBeGreaterThan(0)

    await page.goto("/runs")
    await expect(page.getByRole("heading", { name: "Runs", exact: true })).toBeVisible()
    // The newest run's short id must appear as a real row link.
    const shortId = runs[0].run_id.slice(0, 8)
    await expect(page.getByRole("link", { name: shortId }).first()).toBeVisible()
    // Table has a row per run (header + body rows).
    const rows = page.locator("table tbody tr")
    await expect(rows).toHaveCount(runs.length)
    await page.screenshot({ path: `${SHOTS}/flow1-runs-list.png`, fullPage: true })
  })

  test("Flow 2 — open a completed run, charts repopulate from SSE replay", async ({ page }) => {
    const id = await completedRunId(page)
    await page.goto(`/runs/${id}`)
    await expect(page.getByRole("heading", { name: /^Run/ })).toBeVisible()

    // SSE replay must repopulate BOTH charts (run is complete -> not live).
    await expectChartPopulated(page, "asr-chart", "ASR chart")
    await expectChartPopulated(page, "detection-chart", "Detection chart")
    // The streamed-counts captions back the chart assertion with real numbers.
    await expect(page.getByText(/\d+ attack events? streamed/)).toBeVisible()
    await expect(page.getByText(/\d+ verdict events? streamed/)).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/flow2-runview-charts.png`, fullPage: true })
  })

  test("Flow 3 — navigation recovery: charts stay populated on return", async ({ page }) => {
    const id = await completedRunId(page)
    await page.goto(`/runs/${id}`)
    await expectChartPopulated(page, "asr-chart", "ASR chart (first visit)")

    // Wander away: Metrics -> Catalog -> back to the run.
    await page.goto(`/metrics?run_id=${id}`)
    await expect(page.getByRole("heading", { name: "Metrics", exact: true })).toBeVisible()
    await page.goto(`/catalog?run_id=${id}`)
    await page.goto(`/runs/${id}`)

    // The recovery fix: charts must repopulate on return, not go blank.
    await expectChartPopulated(page, "asr-chart", "ASR chart (recovered)")
    await expectChartPopulated(page, "detection-chart", "Detection chart (recovered)")
    await page.screenshot({ path: `${SHOTS}/flow3-recovered-runview.png`, fullPage: true })
  })

  test("Flow 4 — metrics defaults to newest run and picker navigates", async ({ page }) => {
    const runs = await listRuns(page)
    const newest = runs[0].run_id

    // No run_id in URL -> should default to the newest run (replaceState).
    await page.goto("/metrics")
    await expect(page.getByRole("heading", { name: "Metrics", exact: true })).toBeVisible()
    await expect.poll(() => new URL(page.url()).searchParams.get("run_id"), { timeout: 15_000 }).toBe(newest)

    const picker = page.getByLabel("Select run")
    await expect(picker).toBeVisible()
    await expect(picker).toHaveValue(newest)
    await page.screenshot({ path: `${SHOTS}/flow4-metrics-default-picker.png`, fullPage: true })

    // Changing the picker navigates to that run's metrics.
    if (runs.length > 1) {
      const other = runs[1].run_id
      await picker.selectOption(other)
      await expect.poll(() => new URL(page.url()).searchParams.get("run_id"), { timeout: 15_000 }).toBe(other)
    }
  })

  test("Flow 5 — launch, then stop with confirm (cancel then confirm)", async ({ page }) => {
    // Launch a fresh run through the UI (small rounds so it's cheap).
    await page.goto("/")
    await expect(page.getByRole("heading", { name: "Launch a Crucible run" })).toBeVisible()

    // Prefer the sparkov target if present.
    const targetSelect = page.locator("#target")
    await expect(targetSelect).toBeEnabled({ timeout: 20_000 })
    const options = await targetSelect.locator("option").allTextContents()
    const sparkov = options.find((o) => o.toLowerCase().includes("sparkov"))
    if (sparkov) await targetSelect.selectOption({ label: sparkov })

    await page.locator("#rounds").fill("1")
    await page.getByRole("button", { name: "Start run" }).click()

    // On 201 we navigate to the live run view.
    await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+$/, { timeout: 30_000 })
    const runId = new URL(page.url()).pathname.split("/").pop()!

    // While running, a "Stop run" button must appear.
    const stopBtn = page.getByRole("button", { name: "Stop run" })
    await expect(stopBtn).toBeVisible({ timeout: 20_000 })

    // First click -> CONFIRMATION dialog (no stop fires yet).
    await stopBtn.click()
    const dialog = page.getByRole("dialog", { name: "Stop this run?" })
    await expect(dialog).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/flow5-confirm-dialog.png`, fullPage: true })

    // Cancel -> dialog closes, NO stop happened: status still non-terminal, the
    // run is not stopping/stopped.
    await dialog.getByRole("button", { name: "Cancel" }).click()
    await expect(dialog).toBeHidden()
    const statusAfterCancel = await page.request
      .get(`${API}/runs`)
      .then((r) => r.json())
      .then((b: { runs: RunSummary[] }) => b.runs.find((r) => r.run_id === runId)?.status)
    expect(["queued", "running"], `run still active after cancel (was ${statusAfterCancel})`).toContain(
      statusAfterCancel,
    )

    // Stop again -> Confirm.
    await page.getByRole("button", { name: "Stop run" }).click()
    await expect(page.getByRole("dialog", { name: "Stop this run?" })).toBeVisible()
    await page.getByRole("dialog").getByRole("button", { name: "Stop run" }).click()

    // The status transitions toward stopping/stopped and the button hides or
    // disables. Assert via the visible status pill OR the backend status.
    await expect
      .poll(
        async () => {
          const b = (await page.request.get(`${API}/runs`).then((r) => r.json())) as { runs: RunSummary[] }
          return b.runs.find((r) => r.run_id === runId)?.status
        },
        { timeout: 30_000 },
      )
      .toMatch(/stopping|stopped|complete/)

    // Button should be hidden (terminal) or disabled/"Stopping…".
    const stillThere = page.getByRole("button", { name: /Stop run|Stopping/ })
    const visible = await stillThere.isVisible().catch(() => false)
    if (visible) {
      await expect(stillThere).toBeDisabled()
    }
    await page.screenshot({ path: `${SHOTS}/flow5-stopped-state.png`, fullPage: true })
  })
})
