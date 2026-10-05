import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

export default defineConfig({
  ...base,
  testMatch: "**/rgbd-datasets.spec.ts",
  workers: 1,
  timeout: 90000,
  webServer: Array.isArray(base.webServer) ? base.webServer.map((server, index) => index === 0
    ? { ...server, env: { ...server.env, BIGSMALL_VLM_BASE_URL: "http://127.0.0.1:59998",
      BIGSMALL_VLM_FROZEN_DIR: "", BIGSMALL_VLM_MODEL: "unavailable-test-model" } }
    : server) : base.webServer,
});
