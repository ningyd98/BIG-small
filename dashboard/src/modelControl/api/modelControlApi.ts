// 模型控制中心 API 客户端；API key 只在写请求体中出现，不进入本地缓存。
const API_PREFIX = "/api/v1/model-control";

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

async function writeJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

async function deleteJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "DELETE",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

export type PlannerProviderKind =
  | "MOCK"
  | "RULE_BASED"
  | "OPENAI_COMPATIBLE"
  | "OLLAMA";

export type ModelProviderProfile = {
  profile_id: string;
  display_name: string;
  provider_kind: PlannerProviderKind;
  base_url: string;
  chat_completions_path: string;
  model_name: string;
  active: boolean;
  secret_present: boolean;
  secret_store_kind: string;
  endpoint_hash: string;
  config_version: number;
};

export type PlannerRuntimeStatus = {
  active_profile_id: string;
  active_provider: PlannerProviderKind;
  active_model: string;
  endpoint_hash: string;
  config_version: number;
  health: string;
  circuit_breaker: string;
};

export type ModelDownloadJob = {
  download_id: string;
  model_name: string;
  status: string;
  completed_bytes: number;
  total_bytes: number;
  progress_ratio: number;
  message: string;
};

export type LocalModel = {
  name: string;
  size?: number;
  modified_at?: string;
};

export type ModelTestResult = {
  reachable: boolean;
  authenticated: boolean;
  model_available: boolean;
  response_format_valid: boolean;
  latency_ms?: number;
  error_code?: string;
  sanitized_message?: string;
};

export type SmallModelCatalogItem = {
  catalog_id: string;
  display_name: string;
  ollama_model: string;
  family: string;
  parameter_size_b?: number | null;
  quantization: string;
  estimated_download_bytes?: number | null;
  minimum_ram_gb?: number | null;
  recommended_vram_gb?: number | null;
  capabilities: string[];
  recommended_for: string[];
  source: string;
  license: string;
  tested: boolean;
  checked_at: string;
  notes: string;
  installed: boolean;
};

export const modelControlApi = {
  capabilities: () =>
    readJson<{ supported_provider_kinds: PlannerProviderKind[] }>(
      "/capabilities",
    ),
  profiles: () => readJson<ModelProviderProfile[]>("/profiles"),
  createProfile: (body: {
    display_name: string;
    provider_kind: PlannerProviderKind;
    base_url?: string;
    chat_completions_path?: string;
    model_name: string;
    api_key?: string;
  }) => writeJson<ModelProviderProfile>("/profiles", body),
  activateProfile: (profileId: string) =>
    writeJson<PlannerRuntimeStatus>(`/profiles/${profileId}/activate`, {}),
  testProfile: (profileId: string) =>
    writeJson<ModelTestResult>(`/profiles/${profileId}/test`, {}),
  runtime: () => readJson<PlannerRuntimeStatus>("/runtime"),
  reloadRuntime: () =>
    writeJson<{
      reloaded: boolean;
      real_controller_contacted: boolean;
      hardware_motion_observed: boolean;
      hardware_write_operations: string[];
    }>("/runtime/reload", {}),
  ollamaStatus: () =>
    readJson<{ reachable: boolean; version: string; error_code?: string }>(
      "/ollama/status",
    ),
  ollamaModels: () => readJson<LocalModel[]>("/ollama/models"),
  ollamaModelDetail: (modelName: string) =>
    readJson<Record<string, unknown>>(
      `/ollama/models/${encodeURIComponent(modelName)}`,
    ),
  deleteOllamaModel: (modelName: string) =>
    deleteJson<{ deleted: boolean; model_name: string }>(
      `/ollama/models/${encodeURIComponent(modelName)}`,
    ),
  catalog: () => readJson<SmallModelCatalogItem[]>("/catalog"),
  startDownload: (modelName: string) =>
    writeJson<ModelDownloadJob>("/ollama/downloads", { model_name: modelName }),
  downloads: () => readJson<ModelDownloadJob[]>("/ollama/downloads"),
  download: (downloadId: string) =>
    readJson<ModelDownloadJob>(`/ollama/downloads/${downloadId}`),
  cancelDownload: (downloadId: string) =>
    writeJson<ModelDownloadJob>(`/ollama/downloads/${downloadId}/cancel`, {}),
  activateOllamaModel: (modelName: string) =>
    writeJson<PlannerRuntimeStatus>(
      `/ollama/models/${encodeURIComponent(modelName)}/activate`,
      {},
    ),
  dryRun: (body: {
    user_instruction: string;
    sample_scene: string;
    control_mode: string;
  }) =>
    writeJson<{
      dispatch: boolean;
      hardware_execution: boolean;
      provider_kind: PlannerProviderKind;
      model_name: string;
      raw_planner_output: string;
    }>("/planner/dry-run", body),
};
