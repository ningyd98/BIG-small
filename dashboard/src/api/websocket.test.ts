// 前端单元测试，验证 API、WebSocket 或仿真工具行为。
import { describe, expect, it } from "vitest";

import { dashboardStreamUrl } from "./websocket";

describe("dashboardStreamUrl", () => {
  it("targets the backend dashboard stream path without query tokens", () => {
    const url = dashboardStreamUrl();

    expect(url).toMatch(/^ws:\/\/.+\/api\/v1\/dashboard\/stream$/);
    expect(url).not.toContain("token=");
  });
});
