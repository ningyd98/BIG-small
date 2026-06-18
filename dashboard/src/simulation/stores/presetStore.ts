// 预设 store，管理本地实验 preset 的保存、导入和导出。
import type { ExperimentPreset } from "../services/PresetRepository";

let presets: ExperimentPreset[] = [];

export function setPresets(next: ExperimentPreset[]): void {
  presets = structuredClone(next);
}

export function getPresets(): ExperimentPreset[] {
  return structuredClone(presets);
}
