// tests/walkthroughs/c3-agent-blue-shared-validator.spec.ts
// C3: the agent blue (LLMAgentBlue) shares HoldoutValidator and emits the same three-section
// patch audit trail as the fraud blue. Launches an agent co-evolution run, opens the blue
// patch, and asserts the three labelled sub-sections (Proposal, Rewrite, Holdout validation)
// render in chronological order. Needs a non-halted platform to launch.
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("c3: agent blue patch shows the three-section audit trail", async ({ page }) => {
  test.setTimeout(120000);

  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "support-bot");
  await page.selectOption("#f-mode", "coevolution");
  await page.fill("#f-task", "Help customers with their orders");
  await page.getByRole("button", { name: /Start evaluation/ }).click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/run/");
  const runId = page.url().split("/run/")[1];

  await expect
    .poll(async () => {
      const r = await page.request.get(`/runs/${runId}`);
      return (await r.json()).status;
    }, { timeout: 90000 })
    .toMatch(/complete|failed/);

  await page.goto(`/app/#/coevolution/${runId}`);
  await page.locator("table a", { hasText: /validated|applied/ }).first().click();

  const sections = page.locator("#patchbox .patch-section");
  await expect(sections).toHaveCount(3);
  await expect(sections.nth(0)).toContainText("Proposal");
  await expect(sections.nth(1)).toContainText("Rewrite");
  await expect(sections.nth(2)).toContainText("Holdout validation");

  if (HEADED) await page.pause(); // operator reads the three-section patch trail
});
