// tests/walkthroughs/e2-halt-override.spec.ts
// E2: the devmode halt override lets the operator launch a new run while the platform is
// halted; the banner keeps reporting the real halt. Override OFF -> launch blocked (409
// shown inline). Override ON -> launch proceeds, banner still halted.
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("e2: halt override gates launch behavior, never the displayed halt", async ({ page }) => {
  await page.request.post("/admin/halt-override?enabled=false"); // start from the default
  await page.request.post("/admin/inject-leaky-run"); // halt the platform

  // Override OFF: the launcher refuses the run with the halt message.
  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "support-bot");
  await page.fill("#f-task", "Help customers");
  await page.getByRole("button", { name: /Start evaluation/ }).click();
  await expect(page.locator("main")).toContainText("Launch failed");
  await expect(page.locator("main")).toContainText("Halted");

  // Flip the override ON via Admin.
  await page.goto("/app/#/admin");
  await page.locator("#halt-override-on").click();
  await expect(page.locator("#halt-override-on")).toContainText("ON");

  // The banner still reports the halt (the override never changes the displayed metric).
  await page.goto("/app/#/dashboard");
  await expect(page.locator("#halt-banner")).toBeVisible();

  // Override ON: the launch now proceeds (no 409).
  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "support-bot");
  await page.fill("#f-task", "Help customers");
  await page.getByRole("button", { name: /Start evaluation/ }).click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/run/");

  await page.request.post("/admin/halt-override?enabled=false"); // reset
  if (HEADED) await page.pause();
});
