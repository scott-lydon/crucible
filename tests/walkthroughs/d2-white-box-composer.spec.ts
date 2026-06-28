// tests/walkthroughs/d2-white-box-composer.spec.ts
// D2: the live-run "White-box prompt" inspector shows the brief assembled from the WIRED
// oracles, not a hard-coded list. Drop the LLM judge via the admin debug route, then the
// brief for a fraud run contains exactly the four remaining oracle protocol descriptions.
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("d2: white-box brief reflects the wired oracles (judge dropped -> four lines)", async ({ page }) => {
  test.setTimeout(60000);

  // Drop the LLM judge from the fraud panel via the admin debug button.
  await page.goto("/app/#/admin");
  await page.locator("#drop-llm-judge").click();
  await expect(page.locator("#drop-llm-judge")).toContainText("dropped");

  // Launch a fraud run (now four oracles) and open its white-box prompt inspector.
  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "fraud");
  await page.getByRole("button", { name: /Start evaluation/ }).click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/run/");
  const runId = page.url().split("/run/")[1];
  await expect
    .poll(async () => (await (await page.request.get(`/runs/${runId}`)).json()).status,
      { timeout: 30000 })
    .toMatch(/complete|failed/);

  await page.goto(`/app/#/run/${runId}`);
  await page.locator("#white-box-inspector summary").click();
  const brief = page.locator("#wb-brief");
  await expect(brief).toContainText("Held-out oracle");
  await expect(brief).toContainText("Differential oracle");
  await expect(brief).toContainText("Metamorphic oracle");
  await expect(brief).toContainText("Property / fuzz oracle");
  await expect(brief).not.toContainText("LLM judge"); // the dropped oracle is absent

  const text = await brief.innerText();
  const lines = text.split("\n").filter((l) => l.trim().startsWith("- "));
  expect(lines.length).toBe(4); // exactly the four wired oracles

  if (HEADED) await page.pause();
});
