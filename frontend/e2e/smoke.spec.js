import { test, expect } from '@playwright/test';
import path from 'node:path';

// The same deterministic file the integration tests are built from.
const SALES_CSV = path.resolve('src/test/fixtures/analysis.csv');
const FILE_NAME = path.basename(SALES_CSV); // the sidebar lists the upload under its real name

test('upload a file, explore the dashboard, present the story, navigate home', async ({ page }) => {
  // Anything the page logs as an error, or any uncaught exception, fails the run.
  const problems = [];
  page.on('pageerror', (err) => problems.push(`uncaught: ${err.message}`));
  page.on('console', (msg) => { if (msg.type() === 'error' && !/net::ERR_(FAILED|BLOCKED_BY_CLIENT|NAME_NOT_RESOLVED)/.test(msg.text())) problems.push(`console.error: ${msg.text()}`); });

  // Hermetic: the test is about OUR app, so third-party requests (web fonts
  // etc.) are blocked outright rather than left to succeed or fail with the
  // network -- and a blocked request is recorded as a request failure, not as
  // an application console error, so it can't make the run flaky.
  await page.route((url) => !['127.0.0.1', 'localhost'].includes(url.hostname), (route) => route.abort());

  await test.step('the landing page loads from the real server', async () => {
    await page.goto('/');
    await expect(page.getByText('Automated Data Intelligence')).toBeVisible();
    await expect(page.getByText('Drop your data files here')).toBeVisible();
  });

  await test.step('uploading a CSV runs the real analysis and shows the dashboard', async () => {
    await page.setInputFiles('input[type="file"]', SALES_CSV);
    await expect(page.getByText('Ask Your Own Question')).toBeVisible();
    for (const heading of ['Key Analyses', 'The Story', 'Weak Points']) {
      await expect(page.getByText(heading, { exact: true })).toBeVisible();
    }
    // real SVG charts actually drew (something jsdom cannot show)
    await expect(page.locator('.recharts-surface').first()).toBeVisible();
    await expect(page.locator('.insight-card').first()).toBeVisible();
  });

  await test.step('no raw escape sequence leaked into the visible page', async () => {
    const text = await page.locator('body').innerText();
    expect(text).not.toMatch(/\\u[0-9a-fA-F]{4}/);
  });

  await test.step('the query builder re-queries and redraws', async () => {
    const caption = page.getByText(/^Total of Sales, by /);
    await expect(caption).toBeVisible();
    await page.getByLabel('Aggregation').selectOption('count');
    await expect(page.getByText(/^Count of records, by /)).toBeVisible();
  });

  await test.step('Present opens the walkthrough and steps through it', async () => {
    await page.getByRole('button', { name: /present/i }).click();
    const dialog = page.getByRole('dialog', { name: /story presentation/i });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('1 /', { exact: false })).toBeVisible();
    await page.keyboard.press('ArrowRight');
    await expect(dialog.getByText('2 /', { exact: false })).toBeVisible();
  });

  await test.step('Escape closes only the walkthrough; a second Escape goes home', async () => {
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
    await expect(page.getByText('Ask Your Own Question')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(page.getByText('Automated Data Intelligence')).toBeVisible();
  });

  await test.step('the logo also goes home, and the analysis is still in the sidebar', async () => {
    await page.getByRole('complementary').getByText(FILE_NAME).click();
    await expect(page.getByText('Ask Your Own Question')).toBeVisible();
    await page.getByRole('button', { name: /datalens/i }).click();
    await expect(page.getByText('Automated Data Intelligence')).toBeVisible();
  });

  expect(problems, `the browser reported problems:\n${problems.join('\n')}`).toEqual([]);
});
