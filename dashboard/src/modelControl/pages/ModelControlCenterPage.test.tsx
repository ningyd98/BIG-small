import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModelControlCenterPage } from "./ModelControlCenterPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const existing = {
  profile_id: "existing-profile",
  display_name: "Already configured model",
  provider_kind: "OPENAI_COMPATIBLE",
  base_url: "https://api.example.test",
  chat_completions_path: "/v1/chat/completions",
  model_name: "fictional-model",
  active: true,
  secret_present: false,
  secret_store_kind: "ENCRYPTED_FILE",
  endpoint_hash: "example-hash",
  config_version: 1,
};

function renderExisting() {
  let resolveWrite: (response: Response) => void = () => undefined;
  let current = { ...existing };
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method) {
      return new Promise<Response>((resolve) => {
        resolveWrite = resolve;
      });
    }
    return new Response(
      JSON.stringify(
        path.endsWith("/profiles")
          ? [current]
          : path.endsWith("/runtime")
            ? {
                active_profile_id: current.profile_id,
                active_provider: current.provider_kind,
                active_model: current.model_name,
                health: "READY",
              }
            : path.endsWith("/capabilities")
              ? { supported_provider_kinds: ["RULE_BASED"] }
              : path.endsWith("/status")
                ? { reachable: true, version: "test" }
                : [],
      ),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ConfigProvider theme={{ token: { motion: false } }}>
        <ModelControlCenterPage />
      </ConfigProvider>
    </QueryClientProvider>,
  );
  return {
    queryClient,
    fetchMock,
    ...view,
    finish(success: boolean, kind = "ENCRYPTED_FILE", present = true) {
      if (success)
        current = {
          ...current,
          secret_present: present,
          secret_store_kind: kind,
          config_version: 2,
        };
      resolveWrite(
        new Response(
          JSON.stringify(
            success ? current : { detail: "r489-fictional-modal-key" },
          ),
          { status: success ? 200 : 500 },
        ),
      );
    },
  };
}

describe("existing profile key persistence", () => {
  it.each([true, false])(
    "keeps pending key modal open on Escape and settles safely (success=%s)",
    async (success) => {
      const { queryClient, fetchMock, finish, unmount } = renderExisting();
      const open = await screen.findByRole("button", { name: "保存/更新密钥" });
      fireEvent.click(open);
      await screen.findByRole("dialog");
      // Positive control: exercise the actual Portal -> Dialog -> Modal key listener.
      fireEvent.keyDown(window, { key: "Escape", code: "Escape" });
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      );
      fireEvent.click(open);
      const dialog = await screen.findByRole("dialog");
      const input =
        within(dialog).getByPlaceholderText("输入 API Key，仅用于保存");
      expect(input).toHaveValue("");
      fireEvent.change(input, {
        target: { value: "r489-fictional-modal-key" },
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "保存密钥" }));
      await waitFor(() =>
        expect(
          fetchMock.mock.calls.filter((call) => call[1]?.method),
        ).toHaveLength(1),
      );
      expect(
        within(dialog).getByRole("button", { name: /保存密钥/ }),
      ).toBeDisabled();
      fireEvent.keyDown(window, { key: "Escape", code: "Escape" });
      expect(screen.getByRole("dialog")).toBe(dialog);
      expect(input).toHaveValue("r489-fictional-modal-key");
      expect(
        within(dialog).getByText(existing.display_name),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/密钥已保存：|保存失败/),
      ).not.toBeInTheDocument();
      expect(
        fetchMock.mock.calls.filter((call) => call[1]?.method),
      ).toHaveLength(1);
      finish(success);
      if (success) {
        expect(
          await screen.findByText(/密钥已保存：.*密钥已加密保存在本机/),
        ).toBeInTheDocument();
        await waitFor(() =>
          expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
        );
      } else {
        expect(await within(dialog).findByText(/保存失败/)).toBeInTheDocument();
        expect(input).toHaveValue("r489-fictional-modal-key");
        expect(
          screen.queryByText(/r489-fictional-modal-key/),
        ).not.toBeInTheDocument();
        await waitFor(() =>
          expect(
            within(dialog).getByRole("button", { name: "取消" }),
          ).not.toBeDisabled(),
        );
        fireEvent.keyDown(window, { key: "Escape", code: "Escape" });
        await waitFor(() =>
          expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
        );
      }
      await waitFor(() =>
        expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
      );
      fireEvent.click(open);
      const reopened = await screen.findByRole("dialog");
      expect(
        within(reopened).getByPlaceholderText("输入 API Key，仅用于保存"),
      ).toHaveValue("");
      expect(within(reopened).queryByText(/保存失败/)).not.toBeInTheDocument();
      unmount();
      queryClient.clear();
    },
  );
  it.each([
    ["ENCRYPTED_FILE", true, "密钥已加密保存在本机，服务重启后可继续使用"],
    [
      "SESSION_ONLY",
      true,
      "API Key 仅在当前服务运行期间有效，服务重启后需重新录入",
    ],
    ["ENCRYPTED_FILE", false, "未配置 API Key"],
    ["UNKNOWN", true, "已配置 API Key"],
  ])(
    "saves only the existing key with truthful %s notice",
    async (kind, present, notice) => {
      const { queryClient, fetchMock, finish, unmount } = renderExisting();
      fireEvent.click(
        await screen.findByRole("button", { name: "保存/更新密钥" }),
      );
      const dialog = await screen.findByRole("dialog");
      expect(
        within(dialog).getByText(existing.display_name),
      ).toBeInTheDocument();
      const password =
        within(dialog).getByPlaceholderText("输入 API Key，仅用于保存");
      expect(password).toHaveValue("");
      fireEvent.change(password, {
        target: { value: "r489-fictional-modal-key" },
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "保存密钥" }));
      await waitFor(() =>
        expect(
          fetchMock.mock.calls.filter((call) => call[1]?.method),
        ).toHaveLength(1),
      );
      expect(fetchMock.mock.calls.find((call) => call[1]?.method)).toEqual([
        `/api/v1/model-control/profiles/${existing.profile_id}`,
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ api_key: "r489-fictional-modal-key" }),
        }),
      ]);
      expect(
        within(dialog).getByRole("button", { name: /保存密钥/ }),
      ).toBeDisabled();
      const profileReads = fetchMock.mock.calls.filter((call) =>
        call[0].endsWith("/profiles"),
      ).length;
      const runtimeReads = fetchMock.mock.calls.filter((call) =>
        call[0].endsWith("/runtime"),
      ).length;
      finish(true, kind as string, present as boolean);
      const message = await screen.findByText(
        new RegExp(`密钥已保存：.*${notice}`),
      );
      expect(message).toBeInTheDocument();
      if (kind !== "ENCRYPTED_FILE" || !present)
        expect(message.textContent).not.toContain("已加密保存在本机");
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      );
      await waitFor(() => {
        expect(
          fetchMock.mock.calls.filter((call) => call[0].endsWith("/profiles"))
            .length,
        ).toBeGreaterThan(profileReads);
        expect(
          fetchMock.mock.calls.filter((call) => call[0].endsWith("/runtime"))
            .length,
        ).toBeGreaterThan(runtimeReads);
        expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
      });
      const cached = queryClient.getQueryData<Array<typeof existing>>([
        "model-control",
        "profiles",
      ]);
      expect(cached?.[0]).toMatchObject({
        profile_id: existing.profile_id,
        display_name: existing.display_name,
        model_name: existing.model_name,
        base_url: existing.base_url,
        active: true,
      });
      expect(
        JSON.stringify(
          queryClient
            .getQueryCache()
            .getAll()
            .map((q) => q.state.data),
        ),
      ).not.toContain("r489-fictional-modal-key");
      expect(localStorage.length).toBe(0);
      expect(sessionStorage.length).toBe(0);
      fireEvent.click(screen.getByRole("button", { name: "保存/更新密钥" }));
      const reopened = await screen.findByRole("dialog");
      expect(
        within(reopened).getByPlaceholderText("输入 API Key，仅用于保存"),
      ).toHaveValue("");
      unmount();
      queryClient.clear();
    },
  );

  it("validates empty input, preserves failed input, clears on cancel/reopen and unmount", async () => {
    const { queryClient, fetchMock, finish, unmount } = renderExisting();
    fireEvent.click(
      await screen.findByRole("button", { name: "保存/更新密钥" }),
    );
    let dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "保存密钥" }));
    expect(
      await within(dialog).findByText("请输入 API Key"),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter((call) => call[1]?.method)).toHaveLength(
      0,
    );
    let password =
      within(dialog).getByPlaceholderText("输入 API Key，仅用于保存");
    fireEvent.change(password, {
      target: { value: "r489-fictional-modal-key" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存密钥" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter((call) => call[1]?.method),
      ).toHaveLength(1),
    );
    finish(false);
    expect(await within(dialog).findByText(/保存失败/)).toBeInTheDocument();
    expect(password).toHaveValue("r489-fictional-modal-key");
    expect(
      screen.queryByText(/r489-fictional-modal-key/),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存/更新密钥" }));
    dialog = await screen.findByRole("dialog");
    password = within(dialog).getByPlaceholderText("输入 API Key，仅用于保存");
    expect(password).toHaveValue("");
    fireEvent.change(password, {
      target: { value: "r489-fictional-unmount-value" },
    });
    unmount();
    await waitFor(() =>
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
    );
    queryClient.clear();
  });
});

describe("model profile save feedback", () => {
  it.each([true, false])(
    "shows save outcome and handles the secret (success=%s)",
    async (success) => {
      let finish: (response: Response) => void = () => undefined;
      const saved = {
        profile_id: "test-profile",
        display_name: "Test profile",
        provider_kind: "RULE_BASED",
        model_name: "rule-based",
        secret_present: true,
        secret_store_kind: "ENCRYPTED_FILE",
      };
      let profiles: unknown[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (path: string, init?: RequestInit) => {
          if (init?.method === "POST") {
            return new Promise<Response>((resolve) => {
              finish = resolve;
            });
          }
          const value = path.endsWith("/profiles")
            ? profiles
            : path.endsWith("/capabilities")
              ? { supported_provider_kinds: ["RULE_BASED"] }
              : path.endsWith("/runtime")
                ? {
                    active_provider: "MOCK",
                    active_model: "mock",
                    health: "READY",
                  }
                : path.endsWith("/status")
                  ? { reachable: true, version: "test" }
                  : [];
          return new Response(JSON.stringify(value));
        }),
      );
      const queryClient = new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      });
      render(
        <QueryClientProvider client={queryClient}>
          <ModelControlCenterPage />
        </QueryClientProvider>,
      );
      fireEvent.change(screen.getByPlaceholderText("Profile 名称"), {
        target: { value: "Test profile" },
      });
      const secret = screen.getByPlaceholderText("API key，不回显已有值");
      fireEvent.change(secret, { target: { value: "TEST_SECRET_VALUE_FORM" } });
      fireEvent.click(screen.getByTestId("model-profile-save"));
      await waitFor(() =>
        expect(screen.getByTestId("model-profile-save")).toHaveClass(
          "ant-btn-loading",
        ),
      );
      if (success) profiles = [saved];
      finish(
        new Response(
          JSON.stringify(
            success ? saved : { detail: "TEST_SECRET_VALUE_FORM" },
          ),
          { status: success ? 201 : 500 },
        ),
      );
      if (success) {
        expect(await screen.findByText(/配置已保存/)).toBeInTheDocument();
        expect(
          screen.getByText(/密钥已加密保存在本机，服务重启后可继续使用/),
        ).toBeInTheDocument();
        expect(secret).toHaveValue("");
        expect(screen.getByPlaceholderText("Profile 名称")).toHaveValue(
          "Test profile",
        );
        expect(
          await screen.findByRole("cell", { name: "Test profile" }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: "保存/更新密钥" }),
        ).toBeInTheDocument();
      } else {
        expect(await screen.findByText(/保存失败/)).toBeInTheDocument();
        expect(secret).toHaveValue("TEST_SECRET_VALUE_FORM");
        expect(
          screen.queryByText(/TEST_SECRET_VALUE_FORM/),
        ).not.toBeInTheDocument();
      }
      queryClient.clear();
    },
  );
});
