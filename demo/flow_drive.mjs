// Drive the REAL run-launch flow with assertions at every step. Records video,
// verifies target selection actually changes, the spec reloads, sealing enables
// Start, and Start launches a real run. Reports PASS/FAIL per step — no filming
// of static end-states.
//   node demo/flow_drive.mjs <base> <target_type>   e.g. http://localhost:8910 code_agent
import fs from 'node:fs';
const { chromium } = await import(process.env.PW_PATH);
const base = process.argv[2] || 'http://localhost:8910';
const target = process.argv[3] || 'code_agent';
const targetLabel = target === 'code_agent' ? 'Code Agent' : 'Fraud';
const outDir = 'demo/clips'; fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync('demo/integrity', { recursive: true });
const VW = 1366, VH = 854;
const results = [];
function check(name, cond, detail) { results.push({ name, pass: !!cond, detail }); console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail ? ' — ' + detail : '')); }

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: VW, height: VH }, recordVideo: { dir: outDir, size: { width: VW, height: VH } }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
const consoleErrs = []; page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text()); });

await page.goto(`${base}/app/Run%20Launcher.dc.html`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(2500);
// Which card (by visible title) currently shows the ✓ selected checkmark.
const selectedCard = () => page.evaluate(() => {
  const titles = ['Fraud', 'Code Agent'];
  for (const card of document.querySelectorAll('div[style]')) {
    const titleEl = [...card.querySelectorAll('span')].find(s => titles.includes(s.textContent.trim()));
    if (!titleEl) continue;
    const check = [...card.querySelectorAll('span')].find(s => s.textContent.trim() === '✓');
    if (check && getComputedStyle(check).display !== 'none' && getComputedStyle(check).visibility !== 'hidden')
      return titleEl.textContent.trim();
  }
  return null;
});
const sel0 = await selectedCard();
check('initial: Fraud is the default selection', sel0 === 'Fraud', `✓ selected card = ${sel0}`);

// Step 1: select the target by clicking its box
await page.getByText(targetLabel, { exact: false }).first().click({ timeout: 8000 }).catch(e => console.log('click target err', e.message));
await page.waitForTimeout(2500);
const sel1 = await selectedCard();
check(`click "${targetLabel}" → selection moves to ${targetLabel}`, sel1 === targetLabel, `✓ selected card = ${sel1}`);

// Step 2: seal the spec
await page.getByText('Seal spec', { exact: false }).first().click({ timeout: 8000 }).catch(e => console.log('seal err', e.message));
await page.waitForTimeout(1800);
const t2 = await page.evaluate(() => document.body.innerText);
check('click "Seal spec" → Start (Run evaluation) becomes enabled', /Run evaluation/i.test(t2) && !/Seal spec to enable run/i.test(t2), 'sealed; Run-evaluation button present');

// capture run count before start
const before = await (await page.request.get(`${base}/runs`)).json().catch(() => []);
const beforeIds = new Set((before || []).map(r => r.run_id));

// Step 3: start the run
await page.getByText('Run evaluation', { exact: false }).first().click({ timeout: 8000 }).catch(e => console.log('start err', e.message));
await page.waitForTimeout(4000);
const t3 = await page.evaluate(() => document.body.innerText);
const after = await (await page.request.get(`${base}/runs`)).json().catch(() => []);
const newRun = (after || []).find(r => !beforeIds.has(r.run_id));
check('click "Run evaluation" → a NEW run was created for this target', !!newRun && newRun.target_type === target, newRun ? `run ${newRun.run_id} target=${newRun.target_type} status=${newRun.status}` : 'no new run found');
check('UI navigated to the Running view', /running/i.test(t3), 'running tab text present');

await page.waitForTimeout(3000);
await page.screenshot({ path: 'demo/integrity/flow_final.png', fullPage: true });
fs.writeFileSync('demo/integrity/flow_drive.txt', t3);
await ctx.close(); await browser.close().catch(() => {});
const vids = fs.readdirSync(outDir).filter(f => f.endsWith('.webm'));
vids.sort((a, b) => fs.statSync(`${outDir}/${b}`).mtimeMs - fs.statSync(`${outDir}/${a}`).mtimeMs);
if (vids[0]) fs.renameSync(`${outDir}/${vids[0]}`, `${outDir}/flow-drive-${target}.webm`);
fs.writeFileSync('demo/integrity/flow_drive.result.json', JSON.stringify({ results, consoleErrs, newRun }, null, 2));
const failed = results.filter(r => !r.pass);
console.log(`\n=== FLOW DRIVE: ${results.length - failed.length}/${results.length} assertions PASS, ${failed.length} FAIL, consoleErrs ${consoleErrs.length} ===`);
if (newRun) console.log('NEW_RUN_ID=' + newRun.run_id);
