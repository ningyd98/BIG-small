import type { components } from "../../api/generated/schema";
import type { DashboardUserRole } from "../../api/types";
import type { ExperimentDraft } from "../domain/ExperimentDraft";

const API_PREFIX = "/api/v1/simulation";

type RequestOptions = {
  role?: DashboardUserRole;
  headers?: HeadersInit;
  signal?: AbortSignal;
};

async function readJson<T>(path: string, init?: RequestOptions): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.role) headers.set("x-dashboard-role", init.role);
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers,
    signal: init?.signal,
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

async function writeJson<T>(
  path: string,
  body: unknown,
  init?: RequestOptions,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  headers.set("Content-Type", "application/json");
  if (init?.role) headers.set("x-dashboard-role", init.role);
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: init?.signal,
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

export const simulationApi = {
  capabilities: () =>
    readJson<components["schemas"]["SimulationCapabilitiesResponse"]>(
      "/capabilities",
    ),
  scenarios: () =>
    readJson<components["schemas"]["ScenarioListResponse"]>("/scenarios"),
  scenario: (scenarioId: string) =>
    readJson<components["schemas"]["ScenarioDefinitionView"]>(
      `/scenarios/${scenarioId}`,
    ),
  parameterSchema: () =>
    readJson<components["schemas"]["ParameterSchemaResponse"]>(
      "/parameter-schema",
    ),
  validate: (body: ExperimentDraft) =>
    writeJson<components["schemas"]["ValidationResponse"]>("/validate", body),
  runs: () =>
    readJson<components["schemas"]["SimulationRunListResponse"]>("/runs"),
  run: (runId: string) =>
    readJson<components["schemas"]["SimulationRunRecord"]>(`/runs/${runId}`),
  runEvents: (runId: string) =>
    readJson<components["schemas"]["SimulationEventsResponse"]>(
      `/runs/${runId}/events`,
    ),
  runMetrics: (runId: string) =>
    readJson<components["schemas"]["SimulationMetricsResponse"]>(
      `/runs/${runId}/metrics`,
    ),
  runArtifacts: (runId: string) =>
    readJson<components["schemas"]["SimulationArtifactsResponse"]>(
      `/runs/${runId}/artifacts`,
    ),
  startRun: (body: ExperimentDraft) =>
    writeJson<components["schemas"]["SimulationRunRecord"]>("/runs", body, {
      role: "EXPERIMENT_OPERATOR",
    }),
  cancelRun: (runId: string) =>
    writeJson<components["schemas"]["SimulationRunRecord"]>(
      `/runs/${runId}/cancel`,
      {},
      { role: "EXPERIMENT_OPERATOR" },
    ),
  cloneRun: (runId: string) =>
    writeJson<components["schemas"]["ReproductionResponse"]>(
      `/runs/${runId}/clone`,
      {},
    ),
  reproduceRun: (runId: string) =>
    writeJson<components["schemas"]["ReproductionResponse"]>(
      `/runs/${runId}/reproduce`,
      {},
    ),
  startBatch: (body: ExperimentDraft) =>
    writeJson<components["schemas"]["BatchRecord"]>("/batches", body, {
      role: "EXPERIMENT_OPERATOR",
    }),
  batch: (batchId: string) =>
    readJson<components["schemas"]["BatchRecord"]>(`/batches/${batchId}`),
  batchRuns: (batchId: string) =>
    readJson<components["schemas"]["SimulationRunListResponse"]>(
      `/batches/${batchId}/runs`,
    ),
  compare: (body: components["schemas"]["ComparisonRequest"]) =>
    writeJson<
      components["schemas"]["cloud_edge_robot_arm__simulation_workbench__models__ComparisonResponse"]
    >("/comparisons", body),
  export: (body: components["schemas"]["ExportRequest"]) =>
    writeJson<components["schemas"]["ExportResponse"]>("/exports", body),
};
