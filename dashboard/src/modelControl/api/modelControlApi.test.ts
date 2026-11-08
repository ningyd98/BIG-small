// 模型控制中心 API 客户端测试，确保管理入口走后端且不缓存 secret。
import { beforeEach, describe, expect, it, vi } from "vitest";

import { modelControlApi } from "./modelControlApi";

describe("modelControlApi", () => {
  it("updates only the key on an encoded existing profile id", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ profile_id: "existing/id" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await modelControlApi.updateProfileSecret({
      profileId: "existing/id",
      apiKey: "r489-fictional-frontend-value",
    });
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      "/api/v1/model-control/profiles/existing%2Fid",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ api_key: "r489-fictional-frontend-value" }),
      }),
    );
  });
  it("does not retain a credential echoed in failed write responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("r489-fictional-echoed-credential", { status: 500 }),
      ),
    );
    await expect(
      modelControlApi.updateProfileSecret({
        profileId: "existing",
        apiKey: "r489-fictional-echoed-credential",
      }),
    ).rejects.toThrow(/^model_profile_save_failed$/);
    await expect(
      modelControlApi.createProfile({
        display_name: "test",
        provider_kind: "MOCK",
        model_name: "mock",
        api_key: "r489-fictional-echoed-credential",
      }),
    ).rejects.toThrow(/^model_profile_save_failed$/);
  });
  beforeEach(() => {
    localStorage.clear();
  });

  it("calls profile test and runtime reload without storing API keys", async () => {
    const fetchMock = vi.fn(
      async (...args: [RequestInfo | URL, RequestInit?]) => {
        const [url] = args;
        if (String(url).endsWith("/test")) {
          return jsonResponse({
            reachable: true,
            authenticated: true,
            model_available: true,
            response_format_valid: true,
          });
        }
        return jsonResponse({
          reloaded: true,
          real_controller_contacted: false,
          hardware_motion_observed: false,
          hardware_write_operations: [],
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    await modelControlApi.testProfile("profile-1");
    await modelControlApi.reloadRuntime();

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/model-control/profiles/profile-1/test",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/v1/model-control/runtime/reload",
    );
    expect(localStorage.length).toBe(0);
  });

  it("uses safe model and download management endpoints", async () => {
    const fetchMock = vi.fn(
      async (...args: [RequestInfo | URL, RequestInit?]) => {
        const [url, init = {}] = args;
        if (String(url).includes("/downloads/download-1/cancel")) {
          return jsonResponse({
            download_id: "download-1",
            status: "CANCELLED",
          });
        }
        if (String(url).includes("/downloads/download-1")) {
          return jsonResponse({
            download_id: "download-1",
            status: "DOWNLOADING",
          });
        }
        if (init.method === "DELETE") {
          return jsonResponse({ deleted: true, model_name: "qwen2.5:3b" });
        }
        return jsonResponse({ model: "qwen2.5:3b" });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    await modelControlApi.ollamaModelDetail("qwen2.5:3b");
    await modelControlApi.deleteOllamaModel("qwen2.5:3b");
    await modelControlApi.download("download-1");
    await modelControlApi.cancelDownload("download-1");

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/v1/model-control/ollama/models/qwen2.5%3A3b",
      "/api/v1/model-control/ollama/models/qwen2.5%3A3b",
      "/api/v1/model-control/ollama/downloads/download-1",
      "/api/v1/model-control/ollama/downloads/download-1/cancel",
    ]);
    expect(fetchMock.mock.calls[1][1]?.method).toBe("DELETE");
  });
});

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
