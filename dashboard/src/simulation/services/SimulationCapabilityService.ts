import type { components } from "../../api/generated/schema";
import { simulationApi } from "../api/simulationApi";

// SimulationCapabilityService 以 capability API 为准；枚举存在不等于 backend READY。
export class SimulationCapabilityService {
  async load(): Promise<
    components["schemas"]["SimulationCapabilitiesResponse"]
  > {
    return simulationApi.capabilities();
  }

  readiness(
    capabilities: components["schemas"]["SimulationCapabilitiesResponse"],
    backend: string,
  ): string {
    return (
      capabilities.backends.find((item) => item.backend === backend)
        ?.readiness ?? "BLOCKED_BY_ENV"
    );
  }
}
