import { useEffect, useMemo, useState } from "react";

import { dashboardStreamUrl, type DashboardSocketEvent } from "./websocket";

export type DashboardSocketState = {
  connected: boolean;
  stale: boolean;
  lastEvent: DashboardSocketEvent | null;
};

export function useDashboardSocket(): DashboardSocketState {
  const [connected, setConnected] = useState(false);
  const [stale, setStale] = useState(true);
  const [lastEvent, setLastEvent] = useState<DashboardSocketEvent | null>(null);

  const url = useMemo(() => dashboardStreamUrl(), []);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let heartbeatTimer: number | null = null;
    let lastSequence = 0;

    const connect = () => {
      socket = new WebSocket(url);
      socket.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        setStale(false);
        socket?.send(JSON.stringify({ last_sequence: lastSequence }));
        heartbeatTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ last_sequence: lastSequence }));
          }
        }, 5_000);
      };
      socket.onmessage = (event) => {
        const payload = JSON.parse(
          event.data as string,
        ) as DashboardSocketEvent;
        lastSequence = payload.sequence;
        setLastEvent(payload);
        setConnected(true);
        setStale(false);
      };
      socket.onerror = () => {
        if (cancelled) return;
        setConnected(false);
        setStale(true);
      };
      socket.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        setStale(true);
        if (heartbeatTimer !== null) {
          window.clearInterval(heartbeatTimer);
          heartbeatTimer = null;
        }
        reconnectTimer = window.setTimeout(connect, 2_000);
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
      socket?.close();
    };
  }, [url]);

  return { connected, stale: !connected || stale, lastEvent };
}
