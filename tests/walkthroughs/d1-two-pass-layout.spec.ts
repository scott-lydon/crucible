// tests/walkthroughs/d1-two-pass-layout.spec.ts
// D1: the live-run view shows two clearly labelled passes (Black-box pass, then White-box
// pass), each its own section with a verdict count, and the white-box pass is separate from
// the black-box pass (no interleaving).
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("d1: the run view shows a Black-box pass then a White-box pass", async ({ page }) => {
  test.setTimeout(60000);
  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "fraud");
  await page.getByRole("button", { name: /Start evaluation/ }).click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/run/");
  const runId = page.url().split("/run/")[1];

  await expect
    .poll(async () => (await (await page.request.get(`/runs/${runId}`)).json()).status,
      { timeout: 30000 })
    .toMatch(/complete|failed/);

  // Re-open the run view so it renders both passes from persisted verdicts.
  await page.goto(`/app/#/run/${runId}`);
  const sections = page.locator(".pass-section");
  await expect(sections).toHaveCount(2);
  const blackbox = page.locator('.pass-section[data-pass="black-box"]');
  const whitebox = page.locator('.pass-section[data-pass="white-box"]');
  await expect(blackbox).toContainText("Black-box pass");
  await expect(blackbox).toContainText("Pass: 1 of 2");
  await expect(whitebox).toContainText("White-box pass");
  await expect(whitebox).toContainText("Pass: 2 of 2");

  if (HEADED) await page.pause(); // operator confirms the two labelled passes
});
