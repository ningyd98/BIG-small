// Vite 构建配置，集中管理 React 插件、代理和手动分包策略。
import react from "@vitejs/plugin-react";
import process from "node:process";
import { defineConfig } from "vitest/config";

const backendOrigin =
  process.env.DASHBOARD_BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
const frontendHost = process.env.DASHBOARD_FRONTEND_HOST ?? "127.0.0.1";
const frontendPort = Number(process.env.DASHBOARD_FRONTEND_PORT ?? "5173");

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("node_modules/echarts")) return "echarts";
          if (
            id.includes("node_modules/react") ||
            id.includes("node_modules/@tanstack/react-query")
          ) {
            return "react";
          }
          if (
            id.includes("node_modules/antd") ||
            id.includes("node_modules/@ant-design/icons") ||
            id.includes("node_modules/@ant-design")
          ) {
            return "antd";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: frontendHost,
    port: frontendPort,
    strictPort: true,
    proxy: {
      "/api": {
        target: backendOrigin,
        ws: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
  },
});
