// 实验 manifest 类型，记录配置哈希、提交和可复现信息。
import type { components } from "../../api/generated/schema";

export type ExperimentManifest = components["schemas"]["ExperimentManifest"];
export type BatchExperimentManifest =
  components["schemas"]["ExperimentDraft"] & {
    paired_key?: string;
  };
