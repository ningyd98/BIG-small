// 后端能力适配器，区分 READY、BLOCKED_BY_ENV 和 unavailable。
import type { components } from "../../api/generated/schema";

export function readyBackends(
  capabilities: components["schemas"]["SimulationCapabilitiesResponse"],
): string[] {
  return capabilities.backends
    .filter((backend) => backend.readiness === "READY")
    .map((backend) => backend.backend);
}
