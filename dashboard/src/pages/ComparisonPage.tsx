import { Card, Empty, Space, Table, Typography } from "antd";
import { useMemo } from "react";

import { useDashboardComparison } from "../api/queries";
import { useSimulationRuns } from "../simulation/api/simulationQueries";
import { MetricChart } from "../simulation/components/MetricChart";

// 指标对比页优先使用仿真工作台运行记录，缺数据时才展示 artifact 来源提示。
type ComparisonRow = {
  run_id: string;
  backend: string;
  scenario: string;
  status: string;
  sample_count: number;
  source: string;
};

export function ComparisonPage() {
  const dashboardComparison = useDashboardComparison();
  const runs = useSimulationRuns();
  const rows: ComparisonRow[] = useMemo(
    () =>
      (runs.data?.runs ?? []).map((run) => ({
        run_id: run.run_id,
        backend: run.backend,
        scenario: run.scenario_id,
        status: run.status,
        sample_count: 1,
        source: "simulation_workbench",
      })),
    [runs.data?.runs],
  );
  const artifactSource = dashboardComparison.data?.source ?? "unavailable";

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card title="指标对比">
        <Typography.Text>
          Source: {rows.length ? "simulation_workbench" : artifactSource}
        </Typography.Text>
        {rows.length ? (
          <MetricChart
            title="Run success status"
            labels={rows.map((row) => row.run_id)}
            values={rows.map((row) => (row.status === "SUCCEEDED" ? 1 : 0))}
          />
        ) : (
          <Empty description="暂无 Phase 11 run metrics" />
        )}
        <Table<ComparisonRow>
          rowKey="run_id"
          loading={runs.isLoading}
          dataSource={rows}
          columns={[
            { title: "Run", dataIndex: "run_id" },
            { title: "Backend", dataIndex: "backend" },
            { title: "Scenario", dataIndex: "scenario" },
            { title: "Status", dataIndex: "status" },
            { title: "Source", dataIndex: "source" },
            { title: "Sample count", dataIndex: "sample_count" },
          ]}
        />
      </Card>
    </Space>
  );
}
