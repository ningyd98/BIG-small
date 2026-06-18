// Dashboard REST 客户端，统一设置角色头并把非 2xx 响应转为可追踪错误。
import type {
  DashboardAcceptanceSnapshot,
  DashboardAuditEvents,
  DashboardCapabilities,
  DashboardComparison,
  DashboardEvidenceDetail,
  DashboardEvidenceList,
  DashboardExperimentCreateRequest,
  DashboardExperimentJob,
  DashboardExperimentList,
  DashboardRuntime,
  DashboardSafety,
  DashboardSafetyReviewNoteRequest,
  DashboardSafetyReviewNoteResponse,
  DashboardSummary,
  DashboardUserRole,
} from "./types";

const API_PREFIX = "/api/v1/dashboard";

type RequestOptions = {
  role?: DashboardUserRole;
  headers?: HeadersInit;
  signal?: AbortSignal;
};

async function readJson<T>(path: string, init?: RequestOptions): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.role) {
    headers.set("x-dashboard-role", init.role);
  }
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers,
    signal: init?.signal,
  });
  if (!response.ok) {
    const requestId = response.headers.get("x-request-id") ?? "unavailable";
    const detail = await response.text();
    throw new Error(
      `Dashboard request failed (${response.status}, request_id=${requestId}): ${detail}`,
    );
  }
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
  if (init?.role) {
    headers.set("x-dashboard-role", init.role);
  }
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: init?.signal,
  });
  if (!response.ok) {
    const requestId = response.headers.get("x-request-id") ?? "unavailable";
    const detail = await response.text();
    throw new Error(
      `Dashboard request failed (${response.status}, request_id=${requestId}): ${detail}`,
    );
  }
  return (await response.json()) as T;
}

export const dashboardApi = {
  capabilities: (role?: DashboardUserRole) =>
    readJson<DashboardCapabilities>("/capabilities", { role }),
  summary: (role?: DashboardUserRole) =>
    readJson<DashboardSummary>("/summary", { role }),
  runtime: (role?: DashboardUserRole) =>
    readJson<DashboardRuntime>("/runtime", { role }),
  safety: (role?: DashboardUserRole) =>
    readJson<DashboardSafety>("/safety", { role }),
  recordSafetyReviewNote: (
    body: DashboardSafetyReviewNoteRequest,
    role?: DashboardUserRole,
  ) =>
    writeJson<DashboardSafetyReviewNoteResponse>("/safety/review-notes", body, {
      role,
    }),
  acceptance: (role?: DashboardUserRole) =>
    readJson<DashboardAcceptanceSnapshot>("/acceptance", { role }),
  evidence: (role?: DashboardUserRole, query = "") =>
    readJson<DashboardEvidenceList>(`/evidence${query}`, { role }),
  evidenceDetail: (evidenceId: string, role?: DashboardUserRole) =>
    readJson<DashboardEvidenceDetail>(`/evidence/${evidenceId}`, { role }),
  evidenceDownloadUrl: (evidenceId: string) =>
    `${API_PREFIX}/evidence/${evidenceId}/download`,
  evidenceCompare: (
    leftEvidenceId: string,
    rightEvidenceId: string,
    role?: DashboardUserRole,
  ) =>
    readJson<Record<string, unknown>>(
      `/evidence/${leftEvidenceId}/compare/${rightEvidenceId}`,
      { role },
    ),
  experiments: (role?: DashboardUserRole) =>
    readJson<DashboardExperimentList>("/experiments", { role }),
  startExperiment: (
    body: DashboardExperimentCreateRequest,
    role?: DashboardUserRole,
  ) => writeJson<DashboardExperimentJob>("/experiments", body, { role }),
  cancelExperiment: (experimentId: string, role?: DashboardUserRole) =>
    writeJson<DashboardExperimentJob>(
      `/experiments/${experimentId}/cancel`,
      {},
      { role },
    ),
  comparisons: (role?: DashboardUserRole) =>
    readJson<DashboardComparison>("/comparisons", { role }),
  auditEvents: (role?: DashboardUserRole) =>
    readJson<DashboardAuditEvents>("/audit-events", { role }),
};
