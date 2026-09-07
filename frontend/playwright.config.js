import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  timeout: 120000,
  workers: 1,
  use: {
    baseURL: process.env.STUDIO_URL || 'http://127.0.0.1:8084/studio/',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
    viewport: {width: 1440, height: 1000},
    screenshot: 'only-on-failure',
  },
});
