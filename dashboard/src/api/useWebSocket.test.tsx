import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDashboardSocket } from "./useWebSocket";

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(payload: string) {
    this.sent.push(payload);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
  }
}

describe("useDashboardSocket", () => {
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.stubGlobal("WebSocket", originalWebSocket);
  });

  it("uses the dashboard API stream without URL tokens and reconnects after close", () => {
    const { result, unmount } = renderHook(() => useDashboardSocket());
    const first = MockWebSocket.instances[0];

    expect(first.url).toContain("/api/v1/dashboard/stream");
    expect(first.url).not.toContain("token=");

    act(() => {
      first.readyState = MockWebSocket.OPEN;
      first.onopen?.(new Event("open"));
    });
    expect(result.current.connected).toBe(true);
    expect(first.sent[0]).toBe(JSON.stringify({ last_sequence: 0 }));

    act(() => {
      first.readyState = MockWebSocket.CLOSED;
      first.onclose?.(new CloseEvent("close"));
    });
    expect(result.current.stale).toBe(true);

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);

    unmount();
  });
});
