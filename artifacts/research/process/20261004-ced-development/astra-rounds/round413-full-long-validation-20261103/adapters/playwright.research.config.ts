import { defineConfig, devices } from "/home/ningyd/文档/ChatGPT/BIGsmall/dashboard/node_modules/@playwright/test/index.mjs";
import path from "node:path";

const evidenceRoot = process.env.R413_STAGE_DIR!;

export default defineConfig({
  testDir: "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/adapters/research-tests",
  testMatch: "**/research-evidence.spec.ts",
  timeout: 60000,
  workers: 1,
  outputDir: path.join(evidenceRoot, "test-results"),
  reporter: [["list"], ["junit", {outputFile: path.join(evidenceRoot, "junit.xml")}]],
  use: {
    baseURL: "http://127.0.0.1:5199",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      cwd: "/home/ningyd/文档/ChatGPT/BIGsmall/dashboard",
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
      cwd: "/home/ningyd/文档/ChatGPT/BIGsmall/dashboard",
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
