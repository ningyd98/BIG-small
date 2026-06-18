import {
  Button,
  Card,
  Descriptions,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { dashboardApi } from "../api/client";
import type {
  DashboardEvidenceDetail,
  DashboardEvidenceRecord,
} from "../api/types";
import { JsonViewer } from "../components/JsonViewer";

// 证据浏览页只通过后端 evidence API 读取相对路径，下载和对比都避免浏览器拼接本机路径。
type EvidenceFilters = {
  status?: string;
  sort: string;
  order: string;
};

function queryString(filters: EvidenceFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  params.set("sort", filters.sort);
  params.set("order", filters.order);
  params.set("limit", "50");
  const rendered = params.toString();
  return rendered ? `?${rendered}` : "";
}

export function EvidenceExplorerPage() {
  const [filters, setFilters] = useState<EvidenceFilters>({
    sort: "generated_at",
    order: "desc",
  });
  const [selected, setSelected] = useState<DashboardEvidenceDetail | null>(
    null,
  );
  const [compareResult, setCompareResult] = useState<Record<
    string,
    unknown
  > | null>(null);
  const evidenceQuery = useQuery({
    queryKey: ["dashboard", "evidence", filters],
    queryFn: () => dashboardApi.evidence("VIEWER", queryString(filters)),
  });
  const detailMutation = useMutation({
    mutationFn: (evidenceId: string) =>
      dashboardApi.evidenceDetail(evidenceId, "VIEWER"),
    onSuccess: (detail) => setSelected(detail),
  });
  const compareMutation = useMutation({
    mutationFn: ([left, right]: [string, string]) =>
      dashboardApi.evidenceCompare(left, right, "VIEWER"),
    onSuccess: (result) => setCompareResult(result),
  });
  const records = useMemo(
    () => evidenceQuery.data?.records ?? [],
    [evidenceQuery.data?.records],
  );
  const firstTwo = useMemo(
    () => records.slice(0, 2).map((record) => record.evidence_id),
    [records],
  );

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card title="证据浏览">
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 220 }}
            value={filters.status}
            onChange={(status) =>
              setFilters((current) => ({ ...current, status }))
            }
            options={[
              { value: "ACCEPTED", label: "ACCEPTED" },
              { value: "BLOCKED_BY_ENV", label: "BLOCKED_BY_ENV" },
              { value: "REJECTED", label: "REJECTED" },
              { value: "UNKNOWN", label: "UNKNOWN" },
            ]}
          />
          <Select
            style={{ width: 180 }}
            value={filters.sort}
            onChange={(sort) => setFilters((current) => ({ ...current, sort }))}
            options={[
              { value: "generated_at", label: "generated_at" },
              { value: "relative_path", label: "relative_path" },
              { value: "status", label: "status" },
              { value: "phase", label: "phase" },
            ]}
          />
          <Select
            style={{ width: 120 }}
            value={filters.order}
            onChange={(order) =>
              setFilters((current) => ({ ...current, order }))
            }
            options={[
              { value: "desc", label: "desc" },
              { value: "asc", label: "asc" },
            ]}
          />
          <Button
            disabled={firstTwo.length < 2}
            loading={compareMutation.isPending}
            onClick={() =>
              void compareMutation.mutate([firstTwo[0], firstTwo[1]])
            }
          >
            对比前两项
          </Button>
        </Space>
        <Table<DashboardEvidenceRecord>
          rowKey="evidence_id"
          loading={evidenceQuery.isLoading}
          dataSource={records}
          columns={[
            { title: "阶段", dataIndex: "phase" },
            {
              title: "状态",
              dataIndex: "status",
              render: (status: string) => <Tag>{status}</Tag>,
            },
            { title: "硬件声明", dataIndex: "hardware_claim" },
            { title: "路径", dataIndex: "relative_path" },
            {
              title: "操作",
              render: (_, record) => (
                <Space>
                  <Button
                    aria-label="详情"
                    size="small"
                    loading={detailMutation.isPending}
                    onClick={() =>
                      void detailMutation.mutate(record.evidence_id)
                    }
                  >
                    详情
                  </Button>
                  <Button
                    aria-label="下载"
                    size="small"
                    href={dashboardApi.evidenceDownloadUrl(record.evidence_id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    下载
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      {selected && (
        <Card title="证据详情">
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="ID">
              {selected.record.evidence_id}
            </Descriptions.Item>
            <Descriptions.Item label="路径">
              {selected.record.relative_path}
            </Descriptions.Item>
            <Descriptions.Item label="提交">
              {selected.record.generated_from_commit || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="源码树">
              {selected.record.source_tree_hash || "-"}
            </Descriptions.Item>
          </Descriptions>
          <JsonViewer value={selected.content} />
        </Card>
      )}
      {compareResult && (
        <Card title="证据对比">
          <Typography.Text>changed_fields</Typography.Text>
          <JsonViewer value={compareResult} />
        </Card>
      )}
    </Space>
  );
}
