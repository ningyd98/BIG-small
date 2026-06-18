// 仿真 WebSocket 流客户端，支持 last_sequence replay 和 polling fallback。
export function simulationStreamUrl(lastSequence = 0): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/v1/simulation/stream?last_sequence=${lastSequence}`;
}
