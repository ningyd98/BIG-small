import type { components } from "../../api/generated/schema";

export type DatasetJob = components["schemas"]["DatasetJobView"];
export type DatasetSample = components["schemas"]["DatasetSampleView"];
export type DatasetJobRequest = components["schemas"]["DatasetJobRequest"];

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1/rgbd-datasets${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "x-dashboard-role": body === undefined ? "VIEWER" : "EXPERIMENT_OPERATOR",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`数据作业请求失败 (${response.status})：${await response.text()}`);
  }
  return (await response.json()) as T;
}

export const rgbdDatasetApi = {
  create: (body: DatasetJobRequest) => request<DatasetJob>("/jobs", body),
  job: (jobId: string) => request<DatasetJob>(`/jobs/${encodeURIComponent(jobId)}`),
  cancel: (jobId: string) => request<DatasetJob>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {}),
  sample: (datasetId: string, sampleId: string) => request<DatasetSample>(
    `/${encodeURIComponent(datasetId)}/samples/${encodeURIComponent(sampleId)}`,
  ),
};
