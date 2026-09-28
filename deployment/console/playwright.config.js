import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: '*.spec.js', workers: 1, timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:8766', viewport: { width: 1440, height: 1040 },
    launchOptions: process.platform === 'darwin' ? { executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' } : {},
  },
  webServer: { command: 'python3 tests/fixture.py', url: 'http://127.0.0.1:8766', timeout: 15000, reuseExistingServer: false },
});
