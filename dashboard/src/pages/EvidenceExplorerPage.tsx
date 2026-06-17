import { Card, Table, Tag } from "antd";

import { dashboardApi } from "../api/client";
import type { DashboardSummary } from "../api/types";
import { useQuery } from "@tanstack/react-query";

export function EvidenceExplorerPage() {
  const query = useQuery({
    queryKey: ["dashboard", "evidence"],
    queryFn: dashboardApi.evidence,
  });

  return (
    <Card title="证据浏览">
      <Table<DashboardSummary["latest_evidence"][number]>
        rowKey="evidence_id"
        loading={query.isLoading}
        dataSource={query.data?.records ?? []}
        columns={[
          { title: "阶段", dataIndex: "phase" },
          {
            title: "状态",
            dataIndex: "status",
            render: (status: string) => <Tag>{status}</Tag>,
          },
          { title: "硬件声明", dataIndex: "hardware_claim" },
          { title: "路径", dataIndex: "relative_path" },
        ]}
      />
    </Card>
  );
}
