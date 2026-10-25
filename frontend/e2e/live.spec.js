import { test, expect } from '@playwright/test';
import path from 'node:path';

// Smoke test for a DEPLOYED instance. Run it with `npm run test:live` (see playwright.live.config.js).
// Read-only apart from one tiny share link (expires in 24h). It answers the questions a deploy
// raises that no local test can: is the frontend the CURRENT build, is the host's configuration
// applied, and do the features work against the real server?
const SALES_CSV = path.resolve('src/test/fixtures/analysis.csv');
const MAX_SAFE_UPLOAD_MB = Number(process.env.LIVE_MAX_SAFE_UPLOAD_MB || 50);

const STALE = [
  'The deployed frontend is out of date: it does not contain features that are in this repo.',
  'Rebuild and refresh the deployed copy, then commit and redeploy:',
  '  cd frontend; npm run build; cd ..; Remove-Item -Recurse -Force app\\static; Copy-Item -Recurse frontend\\dist app\\static',
].join('\n');

test.beforeAll(async ({ request }) => {
  // A free instance may be asleep. Poll the health endpoint until it answers, then say how long it took.
  const started = Date.now();
  let last = 'no response';
  while (Date.now() - started < 180_000) {
    try {
      const r = await request.get('/api/health', { timeout: 20_000 });
      if (r.ok()) { console.log(`instance ready after ${Math.round((Date.now() - started) / 1000)}s`); return; }
      last = `HTTP ${r.status()}`;
    } catch (e) { last = String(e.message).split('\n')[0]; }
    await new Promise((r) => setTimeout(r, 5_000));
  }
  throw new Error(`The deployed instance did not become healthy within 3 minutes (${last}). Check the Render logs.`);
});

// Text that only the current frontend build contains, one marker per feature added since the first deploy.
const CURRENT_BUILD_MARKERS = ['Test a Hypothesis', 'Why Did It Change?', 'Does This Hold Without the Outliers?', 'Personal data may be included', 'Python script (pandas)'];

test('the deployed frontend is the current build', async ({ request }) => {
  // Read the JavaScript the server is actually serving and look for the current features' text. This
  // does not depend on clicking through the app, so it still gives a clear answer when the old
  // frontend cannot even complete an upload.
  const html = await (await request.get('/')).text();
  const scripts = [...html.matchAll(/src="(\/assets\/[^"]+\.js)"/g)].map((m) => m[1]);
  expect(scripts.length, 'the page does not reference any script: the frontend is not being served').toBeGreaterThan(0);
  let bundle = '';
  for (const src of scripts) bundle += await (await request.get(src)).text();
  const missing = CURRENT_BUILD_MARKERS.filter((m) => !bundle.includes(m));
  expect(missing, `${STALE}\nMissing from the deployed bundle: ${missing.join(' | ')}`).toEqual([]);
});

test('the deployment is configured safely', async ({ request }) => {
  const health = await (await request.get('/api/health')).json();
  expect(health.status).toBe('ok');
  expect(health.max_file_mb, 'health does not report the upload cap: the backend is an older version than this repo').toBeDefined();
  expect(
    health.max_file_mb,
    `upload cap is ${health.max_file_mb} MB. A 512 MB instance is killed by ~30 MB files; set DATALENS_MAX_FILE_MB (render.yaml sets 10).`,
  ).toBeLessThanOrEqual(MAX_SAFE_UPLOAD_MB);
});

test('the deployed frontend is current and the features work against the real server', async ({ page, request }) => {
  const problems = [];
  page.on('pageerror', (err) => problems.push(`uncaught: ${err.message}`));
  page.on('console', (msg) => { if (msg.type() === 'error' && !/net::ERR_/.test(msg.text())) problems.push(`console.error: ${msg.text()}`); });

  await page.goto('/');
  await page.setInputFiles('input[type="file"]', SALES_CSV);
  await expect(page.getByText('Ask Your Own Question')).toBeVisible();

  // A stale bundle is the easy mistake (the build writes to frontend/dist; the deployed copy is app/static).
  await expect(page.getByRole('heading', { name: 'Test a Hypothesis' }), STALE).toBeVisible();
  await expect(page.getByRole('note', { name: 'Personal data warning' }), STALE).toBeVisible();

  const panel = page.getByRole('heading', { name: 'Test a Hypothesis' }).locator('xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " panel ")][1]');
  await panel.getByRole('button', { name: 'Run test' }).click();
  await expect(panel.locator('.insight-type').first()).toHaveText(/Likely a real difference|No clear difference/);

  await page.getByRole('button', { name: /export/i }).click();
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('menuitem', { name: /python script/i }).click()]);
  expect(download.suggestedFilename()).toBe('analysis_datalens.py');

  expect(problems, problems.join('\n')).toEqual([]);

  // The share API must refuse a result that carries personal data, and accept a clean one.
  const leaky = await request.post('/api/share', { data: { file_name: 'live-check.csv', kpis: {}, v2: { findings: [{ text: 'contact live.check@example.org' }] } } });
  expect(leaky.status(), 'the server accepted personal data without acknowledgement: it is running an older backend').toBe(409);
  expect(await leaky.text()).not.toContain('live.check@example.org');
  const clean = await request.post('/api/share', { data: { file_name: 'live-check.csv', kpis: {}, v2: { findings: [{ text: 'ok' }] } } });
  expect(clean.status()).toBe(200);
});
