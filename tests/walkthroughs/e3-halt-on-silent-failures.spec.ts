// tests/walkthroughs/e3-halt-on-silent-failures.spec.ts
// E3: the halt is gated on Julian's trust score (silent-failure rate), not raw catch rate.
// A leaky run with silent failures reads trust 0/F and halts the platform — even though its
// white-box recall reads 100% (so a recall/catch-rate gate alone would NOT have halted it).
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("e3: a leaky-but-recall-clean run halts on the trust score, not catch rate", async ({ page }) => {
  // Seed the leaky run via the Admin debug button, which jumps to its dashboard.
  await page.goto("/app/#/admin");
  await page.locator("#inject-leaky-run").click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/dashboard/");

  // Trust reads 0 / F.
  await expect(page.getByText("Trust score")).toBeVisible();
  await expect(page.locator("main")).toContainText("/100");
  const trustText = await page.locator("main").innerText();
  expect(trustText).toMatch(/\b0\s*\/100/); // trust score 0
  expect(trustText).toContain("F"); // band F

  // The halt banner is gated on the silent-failure rate (trust), not catch rate.
  await expect(page.locator("#halt-banner")).toBeVisible();
  await expect(page.locator("#halt-banner")).toContainText("silent failure rate above threshold");

  // Catch-rate / recall alone reads healthy (100%), proving the halt is NOT from recall.
  await expect(page.locator("main")).toContainText("White-box recall");
  expect(trustText).toContain("100%");

  if (HEADED) await page.pause();
});
