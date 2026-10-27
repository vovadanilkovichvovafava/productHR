import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for E2E and visual regression testing
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './tests',

  // Maximum time one test can run for (reduced from 30s)
  timeout: 15 * 1000,

  // Run tests in files in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 1 : 0,

  // Run 4 workers in parallel (optimized for browser tests)
  workers: process.env.CI ? 4 : 8,

  // Reporter to use
  reporter: [
    ['html'],
    ['list'],
    ['json', { outputFile: 'test-results/results.json' }]
  ],

  // Shared settings for all the projects below
  use: {
    // Base URL to use in actions like `await page.goto('/')`
    // Use port 5174 for test server (no API proxy)
    baseURL: 'http://localhost:5174',

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Video on failure
    video: 'retain-on-failure',
  },

  // Configure projects for major browsers and devices
  // Use PLAYWRIGHT_PROJECT env var to run specific project, or 'all' for all
  projects: process.env.PLAYWRIGHT_PROJECT === 'all' ? [
    // All browsers for full compatibility testing
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'Mobile Chrome', use: { ...devices['Pixel 5'] } },
    { name: 'Mobile Safari', use: { ...devices['iPhone 12'] } },
  ] : [
    // Fast mode: Chrome + one mobile only (default)
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'Mobile Chrome', use: { ...devices['Pixel 5'] } },
  ],

  // Run your local dev server before starting the tests
  // Uses vite.config.test.ts which has NO API proxy - allows Playwright to mock /api routes
  webServer: {
    command: 'npx vite --config vite.config.test.ts',
    url: 'http://localhost:5174',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
