// 前端单元测试，验证 API、WebSocket 或仿真工具行为。
import { describe, expect, it, vi } from "vitest";

import { dashboardApi } from "./client";

describe("dashboardApi", () => {
  it("submits safety review notes with the reviewer role header", async () => {
    const fetchMock = vi.fn(
      async (...args: [RequestInfo | URL, RequestInit?]) => {
        void args;
        return new Response(
          JSON.stringify({
            note_id: "note-1",
            role: "SAFETY_REVIEWER",
            note: "reviewed",
            related_evidence_id: "",
            hardware_motion_authorized: false,
            created_at: "2026-06-17T00:00:00Z",
          }),
          {
            status: 201,
            headers: { "Content-Type": "application/json" },
          },
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    await dashboardApi.recordSafetyReviewNote(
      { note: "reviewed", related_evidence_id: "" },
      "SAFETY_REVIEWER",
    );

    const [url, init = {}] = fetchMock.mock.calls[0];
    const headers = new Headers(init.headers);
    expect(url).toBe("/api/v1/dashboard/safety/review-notes");
    expect(init.method).toBe("POST");
    expect(headers.get("x-dashboard-role")).toBe("SAFETY_REVIEWER");
    expect(JSON.parse(String(init.body))).toEqual({
      note: "reviewed",
      related_evidence_id: "",
    });
  });
});
