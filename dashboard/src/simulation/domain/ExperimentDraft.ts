// 实验草稿类型，描述前端可编辑的高层仿真配置。
import type { components } from "../../api/generated/schema";

export type ExperimentDraft = components["schemas"]["ExperimentDraft"];
export type NetworkDraft = components["schemas"]["NetworkDraft"];
export type FaultProfileDraft = components["schemas"]["FaultProfileDraft"];
export type DomainRandomizationDraft =
  components["schemas"]["DomainRandomizationDraft"];
