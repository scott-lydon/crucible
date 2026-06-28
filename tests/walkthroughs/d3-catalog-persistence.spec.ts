// tests/walkthroughs/d3-catalog-persistence.spec.ts
// D3: the strategy catalog persists. The "Discovery log" link downloads a JSONL with one
// row per evasion, and the reuse counts survive a backend reload (they come from persisted
// attacks + verdicts, and the discovery log is file-backed).
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

function reuseCount(text: string): number {
  // catalog row: tactic | target | uses | runs | detection | confirmed | white-box
  const cells = text.trim().split(/\t|\n/).filter(Boolean);
  return Number(cells[2]);
}

test("d3: discovery log downloads as JSONL and reuse counts survive a reload", async ({ page }) => {
  test.setTimeout(60000);

  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "fraud");
  await page.fill("#f-rounds", "3");
  await page.getByRole("button", { name: /Start evaluation/ }).click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/run/");
  const runId = page.url().split("/run/")[1];
  await expect
    .poll(async () => (await (await page.request.get(`/runs/${runId}`)).json()).status,
      { timeout: 30000 })
    .toMatch(/complete|failed/);

  // The catalog shows the discovery-log link and a reuse count for the tactic.
  await page.goto("/app/#/catalog");
  await expect(page.locator("#discovery-log-link")).toBeVisible();
  const row = page.locator("tr", { hasText: "margin-drift" }).first();
  await expect(row).toBeVisible();
  const before = reuseCount(await row.innerText());
  expect(before).toBeGreaterThan(0);

  // The discovery log download has one row per evasion in this run, with matching tactic.
  const log = await page.request.get(`/catalog/discovery-log?run_id=${runId}`);
  const evasions = (await log.text()).trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));
  expect(evasions.length).toBeGreaterThan(0);
  for (const e of evasions) {
    expect(e.run_id).toBe(runId);
    expect(e.tactic).toBe("margin-drift");
  }

  // Reload the backend (the fresh state a restart produces); the reuse count is unchanged.
  await page.request.post("/admin/reload-backend");
  await page.goto("/app/#/catalog");
  const after = reuseCount(await page.locator("tr", { hasText: "margin-drift" }).first().innerText());
  expect(after).toBe(before);

  if (HEADED) await page.pause();
});
