// 实验草稿 store，保存前端编辑状态并避免持久化敏感字段。
import type { ExperimentDraft } from "../domain/ExperimentDraft";

let currentDraft: ExperimentDraft | null = null;

export function setExperimentDraft(draft: ExperimentDraft): void {
  currentDraft = structuredClone(draft);
}

export function getExperimentDraft(): ExperimentDraft | null {
  return currentDraft ? structuredClone(currentDraft) : null;
}
