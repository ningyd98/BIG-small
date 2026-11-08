import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModelControlCenterPage } from "./ModelControlCenterPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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
        expect(secret).toHaveValue("");
        expect(screen.getByPlaceholderText("Profile 名称")).toHaveValue(
          "Test profile",
        );
        expect(
          await screen.findByRole("cell", { name: "Test profile" }),
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
