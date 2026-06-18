// Vite 构建配置，集中管理 React 插件、代理和手动分包策略。
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

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
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
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
