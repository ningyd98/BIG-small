// 仿真后端枚举类型，明确 Mock、MuJoCo、Isaac 和 MoveIt dry-run 的区别。
import type { components } from "../../api/generated/schema";

export type SimulationBackend = components["schemas"]["SimulationBackend"];
export type BackendReadiness = components["schemas"]["BackendReadiness"];
export type SimulationRunStatus = components["schemas"]["SimulationRunStatus"];
export type SimulationRunType = components["schemas"]["SimulationRunType"];
