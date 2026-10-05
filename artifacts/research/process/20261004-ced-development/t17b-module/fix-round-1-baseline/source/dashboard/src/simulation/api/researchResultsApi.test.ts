import { afterEach, describe, expect, it, vi } from "vitest";

import { researchResultsApi } from "./researchResultsApi";

afterEach(() => vi.unstubAllGlobals());

describe("read-only research API", () => {
  it("encodes run ids without sending paths or shell bodies", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ run_id: "run" }) });
    vi.stubGlobal("fetch", fetcher);
    await researchResultsApi.evidence("a/b;touch");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/research/runs/a%2Fb%3Btouch/evidence",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetcher.mock.calls[0][1].body).toBeUndefined();
    expect(researchResultsApi.exportUrl("run-1")).toBe(
      "/api/v1/research/runs/run-1/export",
    );
  });

  it("reports a missing or rejected source instead of fabricating an empty success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        text: async () => "research_artifact_invalid",
      }),
    );
    await expect(researchResultsApi.evidence("run")).rejects.toThrow("409");
  });

  it("lists only server registrations with viewer headers and an abort signal", async () => {
    const payload = {
      runs: [],
      actual_research_status: "NOT_RUN",
      reasons: [],
    };
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => payload });
    vi.stubGlobal("fetch", fetcher);
    const controller = new AbortController();
    expect(await researchResultsApi.runs(controller.signal)).toEqual(payload);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("/api/v1/research/runs");
    expect(init.method).toBe("GET");
    expect(init.signal).toBe(controller.signal);
    expect(init.headers["x-dashboard-role"]).toBe("VIEWER");
    expect(init.headers.Accept).toBe("application/json");
  });

  it("encodes the identical run identity for read and JSON export", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ run_id: "x y" }) });
    vi.stubGlobal("fetch", fetcher);
    await researchResultsApi.evidence("x y");
    expect(fetcher.mock.calls[0][0]).toBe(
      "/api/v1/research/runs/x%20y/evidence",
    );
    expect(researchResultsApi.exportUrl("x y")).toBe(
      "/api/v1/research/runs/x%20y/export",
    );
  });
});
