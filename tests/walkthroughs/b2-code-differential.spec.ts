// tests/walkthroughs/b2-code-differential.spec.ts
// B2: a code_agent run shows a `differential` vote in the verdict drawer with the second
// implementation's source visible (a different model family solved the same task; both ran
// in the sandbox and their outputs were compared). Needs Docker for the code sandbox, and
// a non-halted platform to launch (a prior code_agent run leaves white-box recall
// unmeasured, which fails the halt gate closed; clear the runs or use the E2 halt override
// before re-running).
import { test, expect } from "@playwright/test";

const HEADED = process.env.HEADED === "1";

test("b2: code-agent differential shows the second implementation source", async ({ page }) => {
  test.setTimeout(120000); // code_agent runs the Docker sandbox

  await page.goto("/app/#/launch");
  await page.selectOption("#f-target", "code-agent");
  await page.fill("#f-task", "Write a program that prints the sum of 2 and 3");
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
    }, { timeout: 90000 })
    .toBe(true);

  await page.goto(`/app/#/verdict/${verdictId}`);
  const diffCard = page.locator(".card", { hasText: "differential" }).last();
  await expect(diffCard).toBeVisible();
  await expect(diffCard).toContainText("Second implementation");
  await expect(diffCard.locator("pre")).toContainText("print(");

  if (HEADED) await page.pause(); // operator reads the second implementation's source
});
