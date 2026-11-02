import { test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

// Captures the frames for docs/demo.gif from the real running app:
//   DATALENS_DEMO=1 npx playwright test e2e/demo.spec.js && python ../scripts/make_demo_gif.py
// Skipped otherwise, so CI never runs it. Uses the same deterministic sample file as the tests.
const OUT = path.resolve('test-results', 'demo-frames');
const SALES_CSV = path.resolve('src/test/fixtures/analysis.csv');
const panelOf = (page, name) => page.getByRole('heading', { name }).locator('xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " panel ")][1]');

test.skip(!process.env.DATALENS_DEMO, 'set DATALENS_DEMO=1 to capture the demo frames');
test.use({ viewport: { width: 1280, height: 800 } });

test('capture demo frames', async ({ page }) => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  const shot = async (name, target = page) => { await target.screenshot({ path: path.join(OUT, `${name}.png`) }); };
  await page.route((url) => !['127.0.0.1', 'localhost'].includes(url.hostname), (route) => route.abort());

  await page.goto('/');
  await shot('01-upload');

  await page.setInputFiles('input[type="file"]', SALES_CSV);
  await page.getByText('Ask Your Own Question').waitFor();
  await page.waitForTimeout(900);
  await shot('02-dashboard');

  await page.locator('.explorer-tab', { hasText: 'Patterns' }).click();
  const drivers = panelOf(page, 'Why Did It Change?');
  await drivers.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await shot('03-why-did-it-change', drivers);

  // filter to two regions: the reports follow
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole('button', { name: /^Region/ }).click();
  await page.getByLabel('West', { exact: true }).check();
  await page.getByLabel('East', { exact: true }).check();
  await page.keyboard.press('Escape');
  await page.getByRole('status').waitFor();
  await page.waitForFunction(() => /rows you are looking at/.test(document.querySelector('[role="status"]')?.textContent || ''));
  const note = page.getByRole('status');
  await note.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  // Three crops of the real page, stacked by make_demo_gif.py so the text stays readable: the note that says
  // filters are on, the Period Comparison card, and the top of "Why did it change?" (its headline). Nothing is altered.
  await note.screenshot({ path: path.join(OUT, '04a-note.png') });
  await panelOf(page, 'Period Comparison').screenshot({ path: path.join(OUT, '04b-period.png') });
  const box = await drivers.boundingBox();
  const top = await page.evaluate((el) => el.getBoundingClientRect().top + window.scrollY, await drivers.elementHandle());
  await page.screenshot({ path: path.join(OUT, '04c-drivers-top.png'), fullPage: true, clip: { x: box.x, y: top, width: box.width, height: Math.min(150, box.height) } });
  await page.getByRole('button', { name: /reset/i }).click();

  const test_ = panelOf(page, 'Test a Hypothesis');
  await test_.scrollIntoViewIfNeeded();
  await test_.getByRole('button', { name: 'Run test' }).click();
  await test_.locator('.insight-type').first().waitFor();
  await shot('05-hypothesis-test', test_);

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole('button', { name: /export/i }).click();
  await page.getByRole('menuitem', { name: /share link/i }).click();
  await page.getByRole('dialog', { name: 'Personal data may be included' }).waitFor();
  await shot('06-personal-data-guard');
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: /present/i }).first().click();
  await page.getByRole('dialog', { name: 'Story presentation' }).waitFor();
  await shot('07-story-presentation');
});
