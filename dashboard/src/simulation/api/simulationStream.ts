export function simulationStreamUrl(lastSequence = 0): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/v1/simulation/stream?last_sequence=${lastSequence}`;
}
