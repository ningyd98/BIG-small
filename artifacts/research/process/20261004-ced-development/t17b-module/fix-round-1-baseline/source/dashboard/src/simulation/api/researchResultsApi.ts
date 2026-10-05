// 研究结果仅从后端登记的只读产物读取；软件诊断不代表实际研究验收。
import type { components } from "../../api/generated/schema";

export type ResearchGoalView = components["schemas"]["ResearchGoalView"];
export type ResearchMethodView = components["schemas"]["ResearchMethodView"];
export type ResearchRunView = components["schemas"]["ResearchRunView"];
export type ResearchRunList = components["schemas"]["ResearchRunList"];

const PREFIX = "/api/v1/research/runs";

async function read<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json", "x-dashboard-role": "VIEWER" },
    signal,
  });
  if (!response.ok) {
    throw new Error(
      `研究证据请求失败 (${response.status})：${await response.text()}`,
    );
  }
  return (await response.json()) as T;
}

export const researchResultsApi = {
  runs: (signal?: AbortSignal) => read<ResearchRunList>(PREFIX, signal),
  evidence: (runId: string, signal?: AbortSignal) =>
    read<ResearchRunView>(
      `${PREFIX}/${encodeURIComponent(runId)}/evidence`,
      signal,
    ),
  exportUrl: (runId: string) => `${PREFIX}/${encodeURIComponent(runId)}/export`,
};
