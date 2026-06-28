// tests/walkthroughs/e1-halt-state-row.spec.ts
// E1: the halt banner reads from a persisted halt state. The "Halted at" timestamp only
// advances when the decision changes, so it is byte-identical across a page refresh.
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("e1: the Halted-at timestamp is stable across a refresh", async ({ page }) => {
  const seed = await (await page.request.post("/admin/inject-leaky-run")).json();
  await page.goto(`/app/#/dashboard/${seed.runId}`);

  const stamp = page.locator("#halted-at");
  await expect(stamp).toBeVisible();
  const before = (await stamp.innerText()).trim();
  expect(before).toContain("Halted at:");

  await page.reload(); // hard refresh
  await page.goto(`/app/#/dashboard/${seed.runId}`);
  const after = (await page.locator("#halted-at").innerText()).trim();
  expect(after).toBe(before); // the persisted timestamp did not change

  if (HEADED) await page.pause();
});
