import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

const PORT = Number(process.env.E2E_PORT || 8000);

// Run with:  npm run test:e2e   (builds the frontend, then drives a real
// browser against the real FastAPI backend serving that build).
export default defineConfig({
  testDir: './e2e',
  testIgnore: /live\.spec\.js/,   // runs against a deployed URL only: see playwright.live.config.js
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Escape hatch for machines that can't download Playwright's bundled
    // Chromium (locked-down networks): point at any Chromium/Chrome binary.
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ['--no-sandbox', '--disable-gpu'] }
      : {},
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `python -m uvicorn app.main:app --host 127.0.0.1 --port ${PORT}`,
    cwd: '..',
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    // Serve the build we just made, straight from frontend/dist -- never
    // touches app/static (your deployed copy).
    env: { ...process.env, DATALENS_STATIC_DIR: path.resolve('dist') },
  },
});
