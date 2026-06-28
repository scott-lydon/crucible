// tests/walkthroughs/b1-judge-unavailable.spec.ts
// B1: a judge response that is plain prose (no JSON) renders as an UNAVAILABLE vote in the
// verdict drawer, not as a guessed violation. Requires the server running with the
// judge-prose-fallback fixture: CRUCIBLE_JUDGE_PROSE=1 (the mock judge answers in prose).
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("b1: a prose judge response renders UNAVAILABLE, not a guessed VIOLATION", async ({ page }) => {
  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "fraud");
  await page.getByRole("button", { name: /Start evaluation/ }).click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toContain("/run/");
  const runId = page.url().split("/run/")[1];

  let verdictId = "";
  await expect
    .poll(async () => {
      const r = await page.request.get(`/runs/${runId}/verdicts`);
      const vs = await r.json();
      if (Array.isArray(vs) && vs.length) {
        verdictId = vs[0].verdictId;
        return true;
      }
      return false;
    }, { timeout: 30000 })
    .toBe(true);

  await page.goto(`/app/#/verdict/${verdictId}`);
  const judgeCard = page.locator(".card", { hasText: "llm_judge" }).last();
  await expect(judgeCard).toBeVisible();
  // Grey UNAVAILABLE pill, not a red FIRED/VIOLATION badge.
  await expect(judgeCard.locator("span.pill.grey", { hasText: "UNAVAILABLE" })).toBeVisible();
  await expect(judgeCard).toContainText("not parseable as JSON");
  await expect(judgeCard.locator("span.pill.red")).toHaveCount(0);

  if (HEADED) await page.pause(); // operator confirms the grey UNAVAILABLE badge
});
