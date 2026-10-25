import { defineConfig, devices } from '@playwright/test';

// Checks a DEPLOYED copy of the app (not a local one):
//   $env:LIVE_URL = "https://your-app.onrender.com"; npm run test:live      (PowerShell)
//   LIVE_URL=https://your-app.onrender.com npm run test:live                (macOS / Linux)
// It starts no server and builds nothing. It warms the instance up first, because a free Render
// service sleeps when idle and the first request can take a minute.
const LIVE_URL = process.env.LIVE_URL;
if (!LIVE_URL) {
  throw new Error('Set LIVE_URL to the deployed address first, e.g. LIVE_URL=https://your-app.onrender.com');
}

export default defineConfig({
  testDir: './e2e',
  testMatch: /live\.spec\.js/,
  timeout: 240_000,                 // generous: cold start, then a real analysis on a small instance
  expect: { timeout: 30_000 },
  retries: 1,
  workers: 1,                       // be gentle with a small shared instance
  reporter: [['list']],
  use: {
    baseURL: LIVE_URL.replace(/\/+$/, ''),
    trace: 'retain-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ['--no-sandbox', '--disable-gpu'] }
      : {},
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
