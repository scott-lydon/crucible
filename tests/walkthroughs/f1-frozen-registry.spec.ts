// tests/walkthroughs/f1-frozen-registry.spec.ts
// F1: the Admin "Wired components" page renders the eight registry components, and the
// "Hot-swap" button is disabled with the tooltip "Registry is frozen at startup".
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

const EXPECTED = [
  "targets", "oracles", "aggregator", "red", "blue", "measure", "halt", "spec_compiler",
];

test("f1: wired components page shows eight fields and a disabled Hot-swap", async ({ page }) => {
  await page.goto("/app/#/admin");
  const fields = page.locator("#wired-components .wired-field");
  await expect(fields).toHaveCount(8);
  for (const name of EXPECTED) {
    await expect(page.locator("#wired-components")).toContainText(name);
  }
  const hotSwap = page.locator("#hot-swap");
  await expect(hotSwap).toBeDisabled();
  await expect(hotSwap).toHaveAttribute("title", "Registry is frozen at startup");

  if (HEADED) await page.pause();
});
