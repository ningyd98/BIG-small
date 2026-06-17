import type { DashboardCapabilities, DashboardSummary } from "./types";

const API_PREFIX = "/api/v1/dashboard";

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers: { Accept: "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const requestId = response.headers.get("x-request-id") ?? "unavailable";
    throw new Error(
      `Dashboard request failed (${response.status}, request_id=${requestId})`,
    );
  }
  return (await response.json()) as T;
}

export const dashboardApi = {
  capabilities: () => readJson<DashboardCapabilities>("/capabilities"),
  summary: () => readJson<DashboardSummary>("/summary"),
  evidence: () =>
    readJson<{ records: DashboardSummary["latest_evidence"] }>("/evidence"),
};
