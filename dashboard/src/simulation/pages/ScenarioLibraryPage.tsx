import { Card, Space, Table, Tag, Typography } from "antd";

import { useSimulationScenarios } from "../api/simulationQueries";
import type { ScenarioDefinition } from "../domain/ScenarioDefinition";

export function ScenarioLibraryPage() {
  const scenarios = useSimulationScenarios();
  return (
    <Card title="Scenario Library">
      <Table<ScenarioDefinition>
        rowKey="scenario_id"
        loading={scenarios.isLoading}
        dataSource={scenarios.data?.scenarios ?? []}
        columns={[
          {
            title: "Scenario",
            dataIndex: "scenario_id",
            render: (value: string, record) => (
              <Space orientation="vertical" size={2}>
                <Typography.Text strong>{value}</Typography.Text>
                <Typography.Text>{record.description}</Typography.Text>
              </Space>
            ),
          },
          { title: "Category", dataIndex: "category" },
          {
            title: "Faults",
            dataIndex: "fault_types",
            render: (faults: string[]) =>
              faults.map((fault) => <Tag key={fault}>{fault}</Tag>),
          },
          {
            title: "Allowed",
            dataIndex: "allowed_result_statuses",
            render: (statuses: string[]) => statuses.join(", "),
          },
          {
            title: "Max duration",
            dataIndex: "maximum_virtual_duration_ms",
            render: (value: number) => `${value} ms`,
          },
        ]}
      />
    </Card>
  );
}
