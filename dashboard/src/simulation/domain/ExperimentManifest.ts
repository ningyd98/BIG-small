import type { components } from "../../api/generated/schema";

export type ExperimentManifest = components["schemas"]["ExperimentManifest"];
export type BatchExperimentManifest =
  components["schemas"]["ExperimentDraft"] & {
    paired_key?: string;
  };
