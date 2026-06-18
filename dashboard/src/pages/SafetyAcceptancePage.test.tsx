import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { SafetyAcceptancePage } from "./SafetyAcceptancePage";

// 安全验收页测试复核备注流程，同时确认备注不会变成硬件运动授权。
function renderWithQueryClient(children: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>,
  );
}

describe("SafetyAcceptancePage", () => {
  it("submits reviewer notes without authorizing hardware motion", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void init;
        const url = String(input);
        if (url.endsWith("/acceptance")) {
          return new Response(
            JSON.stringify({
              current_level: "NONE",
              next_level: "LEVEL_0",
              blocked_reasons: ["no controller connection"],
              hardware_motion_allowed: false,
              validation_claimed: false,
              level0_read_only: {
                mode_label: "REAL HARDWARE - READ ONLY",
                controller_state: "READ_ONLY",
                emergency_stop_state: "INACTIVE",
                fault_state: "CLEAR",
                operation_mode: "READ_ONLY",
                joint_state_freshness: "FRESH",
                tcp_pose_freshness: "FRESH",
                robot_identity_hash: "robot-hash",
                config_hash: "config-hash",
                site_session_id: "session-hash",
                evidence_complete: true,
                blocker:
                  "fake adapter results cannot be used as real hardware acceptance",
                blockers: [
                  "fake adapter results cannot be used as real hardware acceptance",
                ],
                checks: { "L0-01": true, "L0-20": false },
                controller_contacted: false,
                hardware_state_sampled: false,
                write_operation_count: 0,
                hardware_motion_observed: false,
              },
              levels: [],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.endsWith("/safety/review-notes")) {
          return new Response(
            JSON.stringify({
              note_id: "note-1",
              role: "SAFETY_REVIEWER",
              note: "reviewed blockers",
              related_evidence_id: "",
              hardware_motion_authorized: false,
              created_at: "2026-06-17T00:00:00Z",
            }),
            { status: 201, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response("not found", { status: 404 });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<SafetyAcceptancePage />);

    expect(await screen.findByText("当前级别：NONE")).toBeInTheDocument();
    expect(screen.getByText("REAL HARDWARE - READ ONLY")).toBeInTheDocument();
    expect(screen.getByText("控制器")).toBeInTheDocument();
    expect(screen.getAllByText("READ_ONLY").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("E-Stop")).toBeInTheDocument();
    expect(screen.getByText("INACTIVE")).toBeInTheDocument();
    expect(screen.queryByText(/Level 1 操作/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("安全复核备注"), {
      target: { value: "reviewed blockers" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交复核备注" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/dashboard/safety/review-notes",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const reviewCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/safety/review-notes"),
    );
    if (!reviewCall) throw new Error("missing safety review request");
    const headers = new Headers(reviewCall[1]?.headers);
    expect(headers.get("x-dashboard-role")).toBe("SAFETY_REVIEWER");
    expect(screen.getByText(/硬件运动授权：false/)).toBeInTheDocument();
  });
});
