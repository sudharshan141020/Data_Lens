import { test } from '@playwright/test';
import path from 'node:path';

// Regenerates the README / portfolio screenshots from the real running app:
//   DATALENS_SCREENSHOTS=1 npx playwright test e2e/screenshots.spec.js
// Skipped otherwise, so CI never runs it. Uses the same deterministic sample
// file as the tests, so the images are reproducible.
const OUT = path.resolve('..', 'docs', 'screenshots');
const SALES_CSV = path.resolve('src/test/fixtures/analysis.csv');
const panelOf = (page, name) => page.getByRole('heading', { name }).locator('xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " panel ")][1]');

test.skip(!process.env.DATALENS_SCREENSHOTS, 'set DATALENS_SCREENSHOTS=1 to regenerate the screenshots');
test.use({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 1 });

test('capture screenshots', async ({ page }) => {
  await page.route((url) => !['127.0.0.1', 'localhost'].includes(url.hostname), (route) => route.abort());
  await page.goto('/');

  await page.setInputFiles('input[type="file"]', SALES_CSV);
  await page.getByText('Ask Your Own Question').waitFor();
  await page.waitForTimeout(800);                                     // let the charts finish animating

  await page.locator('.explorer-tab', { hasText: 'Patterns' }).click();
  const drivers = panelOf(page, 'Why Did It Change?');
  await drivers.scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);
  await drivers.screenshot({ path: path.join(OUT, 'feature-why-did-it-change.png') });

  await page.locator('.explorer-tab', { hasText: 'Precision & Text' }).click();
  const robust = panelOf(page, 'Does This Hold Without the Outliers?');
  await robust.scrollIntoViewIfNeeded();
  await robust.screenshot({ path: path.join(OUT, 'feature-robustness.png') });

  const test_ = panelOf(page, 'Test a Hypothesis');
  await test_.scrollIntoViewIfNeeded();
  await test_.getByRole('button', { name: 'Run test' }).click();
  await test_.locator('.insight-type').first().waitFor();
  await test_.screenshot({ path: path.join(OUT, 'feature-hypothesis-test.png') });

  await page.getByRole('button', { name: /export/i }).click();
  await page.getByRole('menuitem', { name: /share link/i }).click();
  const dialog = page.getByRole('dialog', { name: 'Personal data may be included' });
  await dialog.waitFor();
  await page.screenshot({ path: path.join(OUT, 'feature-personal-data-guard.png') });
  await page.keyboard.press('Escape');
  await dialog.waitFor({ state: 'hidden' });

  // The same two screens in the other theme: the warning has to be legible in both.
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.getByRole('button', { name: /export/i }).click();
  await page.getByRole('menuitem', { name: /share link/i }).click();
  await dialog.waitFor();
  await page.screenshot({ path: path.join(OUT, 'feature-personal-data-guard-dark.png') });
  await page.keyboard.press('Escape');
  await dialog.waitFor({ state: 'hidden' });
  await test_.scrollIntoViewIfNeeded();
  await test_.screenshot({ path: path.join(OUT, 'feature-hypothesis-test-dark.png') });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));

  await page.getByRole('button', { name: /present/i }).first().click();
  await page.getByRole('dialog', { name: 'Story presentation' }).waitFor();
  await page.screenshot({ path: path.join(OUT, 'feature-story-presentation.png') });
});
