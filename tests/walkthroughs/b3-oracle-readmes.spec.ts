// tests/walkthroughs/b3-oracle-readmes.spec.ts
// B3: the strategy catalog's "Disclosed verification scheme" panel renders each oracle's
// name + the first paragraph of its README — one accordion per oracle kind, each non-empty.
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("b3: catalog discloses the five oracle verification schemes", async ({ page }) => {
  await page.goto("/app/#/catalog");
  await expect(page.getByText("Disclosed verification scheme", { exact: false })).toBeVisible();

  const sections = page.locator(".scheme-oracle");
  await expect(sections).toHaveCount(5);

  for (let i = 0; i < 5; i++) {
    const section = sections.nth(i);
    await expect(section.locator("summary")).not.toBeEmpty(); // oracle name (README H1)
    await section.locator("summary").click();                 // expand the accordion
    const body = section.locator("div").first();
    await expect(body).toBeVisible();
    const text = (await body.innerText()).trim();
    expect(text.length).toBeGreaterThan(40);                  // first paragraph, non-empty
  }

  if (HEADED) await page.pause(); // operator reads each disclosed scheme
});
