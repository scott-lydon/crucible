// tests/walkthroughs/a3-replay-determinism.spec.ts
// A3: the OracleVote serialization round trip is byte-identical. Opens a real verdict, clicks
// Replay, and asserts the "Original (stored votes JSON)" and "Replayed (round-tripped JSON)"
// panels carry the SAME votes (deep-equal once parsed; the byte-identical badge is the
// app's own proof). Display key order differs by design, so we compare parsed JSON, not text.
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("a3: stored votes round-trip byte-identical through serialize/deserialize", async ({ page }) => {
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
  await page.locator("#replay-btn").click();

  await expect(page.getByText("Replay matches original (byte-identical)")).toBeVisible();
  const original = JSON.parse((await page.locator("#replay-original").innerText()).trim());
  const replayed = JSON.parse((await page.locator("#replay-replayed").innerText()).trim());
  expect(original).toEqual(replayed); // order-independent: the votes survived the round trip
  expect(Array.isArray(original)).toBe(true);
  expect(original.length).toBeGreaterThan(0);

  if (HEADED) await page.pause(); // operator confirms the two panels match
});
