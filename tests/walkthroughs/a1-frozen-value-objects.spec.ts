// tests/walkthroughs/a1-frozen-value-objects.spec.ts
// A1: module value objects are frozen, so a verdict replays byte-identical. Drives a run
// through the launcher, opens the verdict detail, clicks "Replay verdict from JSON", and
// asserts the green "Replay matches original (byte-identical)" badge. If any vote shape had
// drifted to a mutable form mid-flight, the round trip would differ and the badge reads red.
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

async function launchFraudAndOpenVerdict(page: import("@playwright/test").Page) {
  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "fraud");
  await page.getByRole("button", { name: /Start evaluation/ }).click();
  // A hash-only change is not a navigation, so poll the URL instead of waitForURL.
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/run/");
  const runId = page.url().split("/run/")[1];

  let verdictId = "";
  await expect
    .poll(async () => {
      const r = await page.request.get(`/runs/${runId}/verdicts`);
      const vs = await r.json();
      if (Array.isArray(vs) && vs.length) {
        verdictId = vs[0].verdictId;
        return true;
      }
      return false;
    }, { timeout: 30000 })
    .toBe(true);

  await page.goto(`/app/#/verdict/${verdictId}`);
  return verdictId;
}

test("a1: verdict replays byte-identical (frozen value objects survive the round trip)", async ({ page }) => {
  await launchFraudAndOpenVerdict(page);
  await page.locator("#replay-btn").click();
  await expect(page.getByText("Replay matches original (byte-identical)")).toBeVisible();
  await expect(page.getByText("Replay DIFFERS from original")).toHaveCount(0);
  if (HEADED) await page.pause(); // operator confirms the green badge
});
