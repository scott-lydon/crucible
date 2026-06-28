// tests/walkthroughs/a2-typed-wiring-errors.spec.ts
// A2: a missing target fails loud at the boundary with the registered-types enumeration,
// rendered inline in the launcher (never "Internal server error").
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("a2: unknown target kind shows the registered-types error, not a 500", async ({ page }) => {
  // The launcher's "#/launch?target=<kind>" debug override forces an unregistered kind,
  // the state the happy-path target select cannot reach.
  await page.goto("/app/#/launch?target=nope");
  await page.getByRole("button", { name: /Start evaluation/ }).click();

  const err = page.getByText(/Registered target types:/);
  await expect(err).toBeVisible();
  await expect(err).toContainText("No target adapter registered for target_kind='nope'");
  await expect(err).toContainText("fraud");
  await expect(page.locator("main")).not.toContainText("Internal server error");

  if (HEADED) await page.pause(); // operator confirms the inline error pane
});
