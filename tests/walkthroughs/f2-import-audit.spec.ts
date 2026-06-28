// tests/walkthroughs/f2-import-audit.spec.ts
// F2: the Admin page renders a green "Module boundaries clean" badge when no module imports
// another module's concrete class; injecting a demo cross-module import flips it red with the
// offending file listed; clearing it restores green.
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("f2: module-boundary badge is green, flips red on an injected import, clears green", async ({ page }) => {
  await page.request.post("/admin/inject-bad-import?enabled=false"); // start clean
  await page.goto("/app/#/admin");

  const badge = page.locator("#boundaries-badge");
  await expect(badge).toHaveText("Module boundaries clean");
  await expect(badge).toHaveClass(/green/);

  // Inject a demo cross-module import -> the badge flips red and lists the offender.
  await page.locator("#inject-bad-import").click();
  await expect(page.locator("#boundaries-badge")).toHaveClass(/red/);
  await expect(page.locator("main")).toContainText("demo-injected cross-module import");

  // Clear the demo injection -> green again.
  await page.locator("#clear-bad-import").click();
  await expect(page.locator("#boundaries-badge")).toHaveText("Module boundaries clean");
  await expect(page.locator("#boundaries-badge")).toHaveClass(/green/);

  if (HEADED) await page.pause();
});
