import type { ExperimentDraft } from "../domain/ExperimentDraft";

let currentDraft: ExperimentDraft | null = null;

export function setExperimentDraft(draft: ExperimentDraft): void {
  currentDraft = structuredClone(draft);
}

export function getExperimentDraft(): ExperimentDraft | null {
  return currentDraft ? structuredClone(currentDraft) : null;
}
