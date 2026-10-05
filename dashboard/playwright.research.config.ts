import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const evidenceRoot = path.resolve(
  process.cwd(),
  "../artifacts/research/process/20261004-ced-development/t17b-ui-module/browser",
);

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/research-evidence.spec.ts",
  timeout: 60000,
  workers: 1,
  outputDir: path.join(evidenceRoot, "test-results"),
  use: {
    baseURL: "http://127.0.0.1:5199",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `cd .. && python "${path.join(evidenceRoot, "backend.py")}"`,
      env: {
        ...process.env,
        PYTHONPATH: "src",
        DASHBOARD_AUTH_MODE: "LOCAL_ONLY",
      },
      url: "http://127.0.0.1:8123/health",
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: "npm run dev",
      env: {
        ...process.env,
        DASHBOARD_BACKEND_ORIGIN: "http://127.0.0.1:8123",
        DASHBOARD_FRONTEND_PORT: "5199",
      },
      url: "http://127.0.0.1:5199",
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
