import type { ExperimentPreset } from "../services/PresetRepository";

let presets: ExperimentPreset[] = [];

export function setPresets(next: ExperimentPreset[]): void {
  presets = structuredClone(next);
}

export function getPresets(): ExperimentPreset[] {
  return structuredClone(presets);
}
