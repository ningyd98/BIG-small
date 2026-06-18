import type { ExperimentDraft } from "../domain/ExperimentDraft";

// PresetRepository 只保存仿真实验草稿；sanitizePreset 会去掉 token/IP/credential 等敏感字段。
const storageKey = "big-small-simulation-presets";

export type ExperimentPreset = {
  id: string;
  name: string;
  draft: ExperimentDraft;
};

export class ExperimentPresetRepository {
  list(): ExperimentPreset[] {
    return JSON.parse(
      localStorage.getItem(storageKey) ?? "[]",
    ) as ExperimentPreset[];
  }

  save(preset: ExperimentPreset): void {
    const sanitized = sanitizePreset(preset);
    const others = this.list().filter((item) => item.id !== preset.id);
    localStorage.setItem(storageKey, JSON.stringify([...others, sanitized]));
  }

  delete(id: string): void {
    localStorage.setItem(
      storageKey,
      JSON.stringify(this.list().filter((item) => item.id !== id)),
    );
  }
}

function sanitizePreset(preset: ExperimentPreset): ExperimentPreset {
  const draft = structuredClone(preset.draft);
  delete (draft.parameter_overrides as Record<string, unknown>).token;
  delete (draft.parameter_overrides as Record<string, unknown>).credential;
  delete (draft.parameter_overrides as Record<string, unknown>)
    .controller_config;
  return { ...preset, draft };
}
