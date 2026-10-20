import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// The same deterministic file the smoke test and the integration tests use.
// It has a "Customer ID" column, which the personal-data scan flags.
const SALES_CSV = path.resolve('src/test/fixtures/analysis.csv');
const CUSTOMER_IDS = new Set(
  fs.readFileSync(SALES_CSV, 'utf8').trim().split('\n').slice(1).map((l) => l.split(',')[1]),
);

// Same ground rules as the smoke test: hermetic, and any uncaught exception or
// console error fails the test, so a feature that "works" but logs a React
// warning or throws in the background cannot pass.
async function openDashboard(page) {
  const problems = [];
  page.on('pageerror', (err) => problems.push(`uncaught: ${err.message}`));
  page.on('console', (msg) => { if (msg.type() === 'error' && !/net::ERR_(FAILED|BLOCKED_BY_CLIENT|NAME_NOT_RESOLVED)/.test(msg.text())) problems.push(`console.error: ${msg.text()}`); });
  await page.route((url) => !['127.0.0.1', 'localhost'].includes(url.hostname), (route) => route.abort());
  await page.goto('/');
  await page.setInputFiles('input[type="file"]', SALES_CSV);
  await expect(page.getByText('Ask Your Own Question')).toBeVisible();
  return problems;
}

// The panel a heading belongs to: its NEAREST enclosing element whose class list includes exactly "panel"
// (not "panel-head", which a substring match would pick up). (Deep Dive wraps every
// sub-panel in a .panel of its own, so a bare .panel filter matches both.)
const panelOf = (page, name) => page.getByRole('heading', { name }).locator('xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " panel ")][1]');

const noProblems = (problems) => expect(problems, `the browser reported problems:\n${problems.join('\n')}`).toEqual([]);

function pythonBinary() {
  for (const bin of [process.env.PYTHON, 'python', 'python3'].filter(Boolean)) {
    try { execFileSync(bin, ['--version'], { stdio: 'ignore' }); return bin; } catch { /* try the next one */ }
  }
  throw new Error('No Python interpreter found to run the downloaded script.');
}

test('Test a Hypothesis: only runs when asked, explains itself, and drops a stale answer', async ({ page }) => {
  const problems = await openDashboard(page);
  const panel = panelOf(page, 'Test a Hypothesis');
  await expect(panel).toBeVisible();

  const requests = [];
  page.on('request', (r) => { if (r.url().includes('/api/hypothesis-test')) requests.push(r); });
  await page.waitForTimeout(500);
  expect(requests, 'a test must never run on its own').toHaveLength(0);

  await panel.getByRole('button', { name: 'Run test' }).click();
  const verdict = panel.locator('.insight-type').first();
  await expect(verdict).toHaveText(/Likely a real difference|No clear difference/);
  await expect(panel.getByText('Why this test:')).toBeVisible();
  await expect(panel.getByText(/Cross-check with/)).toBeVisible();
  await expect(panel.getByRole('img', { name: /interval .* to / })).toBeVisible();      // the interval graphic really drew
  expect(requests).toHaveLength(1);

  // only the two chosen groups' values were uploaded, not the dataset
  const sent = requests[0].postDataJSON();
  expect(new Set(sent.groups)).toEqual(new Set([sent.group_a, sent.group_b]));
  expect(sent.groups.length).toBeLessThan(162);
  expect(Object.keys(sent)).not.toContain('rows');

  // changing the question must not leave the old answer standing
  await panel.getByLabel('On the outcome').selectOption({ index: 1 });
  await expect(verdict).toBeHidden();
  await expect(panel.getByText(/run the test again/)).toBeVisible();
  noProblems(problems);
});

test('Export > Python script: the downloaded file really runs and reproduces the analysis', async ({ page }) => {
  const problems = await openDashboard(page);
  await page.getByRole('button', { name: /export/i }).click();
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('menuitem', { name: /python script/i }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('analysis_datalens.py');

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'datalens-script-'));
  const script = path.join(dir, download.suggestedFilename());
  await download.saveAs(script);
  fs.copyFileSync(SALES_CSV, path.join(dir, 'analysis.csv'));
  const source = fs.readFileSync(script, 'utf8');
  expect(source).toContain("DATA_FILE = 'analysis.csv'");
  expect(source).toContain('RESULTS = {');

  const out = execFileSync(pythonBinary(), [script], { cwd: dir, encoding: 'utf8', env: { ...process.env, PYTHONWARNINGS: 'ignore' } });
  expect(out).toContain('162 rows x 8 columns');
  expect(out).toMatch(/Sales\s+\d/);                       // the headline numbers printed
  noProblems(problems);
});

test('Personal data: a banner on the dashboard, a stop-and-ask before sharing, and masking that really removes the values', async ({ page }) => {
  const problems = await openDashboard(page);
  await expect(page.getByRole('note', { name: 'Personal data warning' })).toBeVisible();

  const shareRequests = [];
  page.on('request', (r) => { if (r.url().endsWith('/api/share')) shareRequests.push(r); });

  await test.step('cancelling uploads nothing', async () => {
    await page.getByRole('button', { name: /export/i }).click();
    await page.getByRole('menuitem', { name: /share link/i }).click();
    const dialog = page.getByRole('dialog', { name: 'Personal data may be included' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('checkbox', { name: 'Mask Customer ID' })).toBeChecked();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(page.getByText('Ask Your Own Question')).toBeVisible();   // Escape closed the dialog, not the dashboard
    expect(shareRequests).toHaveLength(0);
  });

  await test.step('masking sends a copy without the real customer ids', async () => {
    await page.getByRole('button', { name: /export/i }).click();
    await page.getByRole('menuitem', { name: /share link/i }).click();
    const [request] = await Promise.all([
      page.waitForRequest((r) => r.url().endsWith('/api/share')),
      page.getByRole('button', { name: /mask 1 selected/i }).click(),
    ]);
    const body = request.postData();
    const v2 = request.postDataJSON().v2;
    expect(v2.filterable_data.rows.length).toBeGreaterThan(0);
    expect(v2.filterable_data.rows.every((r) => !('Customer ID' in r))).toBe(true);

    // The real ids also live OUTSIDE the row data: in the at-risk customer list and as raw
    // numbers in scatter charts that plot them. The first version of the masking missed
    // both, and this assertion is what caught it.
    expect(v2.cohorts.at_risk.at_risk.length).toBeGreaterThan(0);
    expect(v2.cohorts.at_risk.at_risk.every((r) => /^Customer ID \d+$/.test(r.entity))).toBe(true);
    expect(v2.all_analyses.some((a) => /customer_id/.test(a.id))).toBe(false);
    expect(body).not.toMatch(/"(entity|x|y)":10[0-3]\d(?=[,}])/);
    for (const id of CUSTOMER_IDS) expect(body).not.toContain(`"entity":${id}`);

    // and the unrelated analysis is still there, so masking did not just gut the result
    expect(v2.all_analyses.some((a) => a.id === 'sum_region')).toBe(true);
  });
  noProblems(problems);
});

test('Deep Dive: the driver analysis and the robustness check are on the page and say something', async ({ page }) => {
  const problems = await openDashboard(page);

  await page.locator('.explorer-tab', { hasText: 'Patterns' }).click();
  const drivers = panelOf(page, 'Why Did It Change?');
  await expect(drivers).toBeVisible();
  await expect(drivers.getByText(/^Sales (fell|rose)/)).toBeVisible();          // the headline names the metric and direction
  await expect(drivers.getByText(/where the change landed, not why it happened/)).toBeVisible();
  await drivers.getByRole('tab', { name: /Region/ }).click();                   // switching the split redraws
  await expect(drivers.locator('.recharts-surface').first()).toBeVisible();

  await page.locator('.explorer-tab', { hasText: 'Precision & Text' }).click();
  const robust = panelOf(page, 'Does This Hold Without the Outliers?');
  await expect(robust).toBeVisible();
  await expect(robust.getByText(/Robust|Sensitive to extreme rows/)).toBeVisible();
  await expect(robust.getByText(/Extreme rows are not errors/)).toBeVisible();
  noProblems(problems);
});


// Regression test for a bug no unit test could see: the personal-data banner and dialog were styled with
// CSS variables the app does not define, so in the light theme they rendered dark text on a dark box.
// Computes the real WCAG contrast ratio of what the browser painted, in both themes.
const contrastOf = (page, selector) => page.locator(selector).first().evaluate((el) => {
  const parse = (c) => c.match(/[\d.]+/g).map(Number);
  const lum = ([r, g, b]) => 0.2126 * ((r / 255) ** 2.2) + 0.7152 * ((g / 255) ** 2.2) + 0.0722 * ((b / 255) ** 2.2);
  const backgroundOf = (node) => {
    for (let n = node; n; n = n.parentElement) {
      const m = parse(getComputedStyle(n).backgroundColor);
      if (m.length < 4 || m[3] > 0.5) return m.slice(0, 3);
    }
    return [255, 255, 255];
  };
  const fg = parse(getComputedStyle(el).color).slice(0, 3);
  const [hi, lo] = [lum(fg), lum(backgroundOf(el))].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
});

for (const theme of ['light', 'dark']) {
  test(`Personal data warning is legible in the ${theme} theme (WCAG AA contrast)`, async ({ page }) => {
    const problems = await openDashboard(page);
    await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);

    const banner = '[role="note"][aria-label="Personal data warning"]';
    await expect(page.locator(banner)).toBeVisible();
    expect(await contrastOf(page, `${banner} strong`)).toBeGreaterThanOrEqual(4.5);
    expect(await contrastOf(page, banner)).toBeGreaterThanOrEqual(4.5);

    await page.getByRole('button', { name: /export/i }).click();
    await page.getByRole('menuitem', { name: /share link/i }).click();
    const dialog = '[role="dialog"][aria-label], [role="dialog"][aria-labelledby]';
    await expect(page.locator(dialog)).toBeVisible();
    expect(await contrastOf(page, '#sensitive-dialog-title')).toBeGreaterThanOrEqual(4.5);
    expect(await contrastOf(page, `${dialog} p`)).toBeGreaterThanOrEqual(4.5);
    for (const name of [/cancel/i, /continue without masking/i, /mask 1 selected/i]) {
      const button = page.getByRole('button', { name });
      const ratio = await button.evaluate((el) => {
        const parse = (c) => c.match(/[\d.]+/g).map(Number);
        const lum = ([r, g, b]) => 0.2126 * ((r / 255) ** 2.2) + 0.7152 * ((g / 255) ** 2.2) + 0.0722 * ((b / 255) ** 2.2);
        const cs = getComputedStyle(el);
        const paint = parse(cs.backgroundColor);
        let bg = paint.length < 4 || paint[3] > 0.5 ? paint.slice(0, 3) : null;
        for (let n = el.parentElement; !bg && n; n = n.parentElement) {
          const m = parse(getComputedStyle(n).backgroundColor);
          if (m.length < 4 || m[3] > 0.5) bg = m.slice(0, 3);
        }
        const [hi, lo] = [lum(parse(cs.color).slice(0, 3)), lum(bg || [255, 255, 255])].sort((a, b) => b - a);
        return (hi + 0.05) / (lo + 0.05);
      });
      expect(ratio, `${name} button text contrast`).toBeGreaterThanOrEqual(4.5);
    }
    noProblems(problems);
  });
}
