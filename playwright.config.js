import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir:'./tests/browser',
  workers:1,
  timeout:45000,
  fullyParallel:false,
  use:{
    baseURL:'http://127.0.0.1:8407',
    viewport:{width:1586,height:992},
    channel:process.env.PLAYWRIGHT_CHANNEL || undefined,
    trace:'retain-on-failure',
    screenshot:'only-on-failure'
  },
  webServer:{
    command:'.venv/bin/python tests/serve_e2e.py',
    url:'http://127.0.0.1:8407/health',
    reuseExistingServer:false,
    timeout:30000
  }
});
