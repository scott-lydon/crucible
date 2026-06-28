// tests/walkthroughs/c2-holdout-contamination.spec.ts
// C2: a deliberately contaminated patch (held-out set overlaps the training attacks) appears
// as a red banner on the Blue Patch Review, not a silent recovery claim. Uses the admin debug
// route "Inject contamination demo".
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("c2: a contaminated patch shows a red banner and withholds the recovery claim", async ({ page }) => {
  await page.goto("/app/#/admin");
  await page.locator("#inject-contamination").click();
  // The button seeds the patch and routes to its co-evolution run.
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/coevolution/");

  await page.locator("table a", { hasText: /applied|validated/ }).first().click();

  const banner = page.locator("#patchbox .patch-contamination");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("overlap training");
  await expect(banner).toContainText("atk-7"); // one of the first five overlapping ids
  // No false recovery: the after-recall number is withheld, not shown.
  await expect(page.locator("#patchbox")).toContainText("after-recall withheld");

  if (HEADED) await page.pause(); // operator confirms the red contamination banner
});
