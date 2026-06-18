import { Card, Empty, Space, Table, Typography } from "antd";

import { useSimulationRuns } from "../api/simulationQueries";

export function LiveRunPage() {
  const runs = useSimulationRuns();
  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card title="Live Run Monitor">
        <Table
          rowKey="run_id"
          loading={runs.isLoading}
          dataSource={runs.data?.runs ?? []}
          locale={{
            emptyText: <Empty description="No active simulation runs" />,
          }}
          columns={[
            { title: "Run", dataIndex: "run_id" },
            { title: "Status", dataIndex: "status" },
            { title: "Scenario", dataIndex: "scenario_id" },
            { title: "Mode", dataIndex: "control_mode" },
            { title: "Backend", dataIndex: "backend" },
          ]}
        />
      </Card>
      <Card title="Runtime Channels">
        <Typography.Text>
          WebSocket stream uses heartbeat, sequence replay and polling fallback.
        </Typography.Text>
      </Card>
    </Space>
  );
}
