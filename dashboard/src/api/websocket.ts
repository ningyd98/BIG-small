// Dashboard WebSocket 客户端，封装鉴权、心跳和消息大小保护。
export type DashboardSocketEvent = {
  event_id: string;
  sequence: number;
  event_type: string;
  source: string;
  timestamp: string;
  payload: unknown;
};

export function dashboardStreamUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/v1/dashboard/stream`;
}
