import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { SafetyAcceptancePage } from "./SafetyAcceptancePage";

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
