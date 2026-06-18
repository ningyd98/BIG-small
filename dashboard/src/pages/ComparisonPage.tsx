import { Card, Empty, Space, Table, Typography } from "antd";

import { useDashboardComparison } from "../api/queries";

type MetricRow = {
  name?: unknown;
  unit?: unknown;
  pcsc?: unknown;
  eteac?: unknown;
  auto?: unknown;
};

function valueText(value: unknown): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (value == null) {
    return "-";
  }
  return String(value);
}

export function ComparisonPage() {
  const comparison = useDashboardComparison();
  const rows = (comparison.data?.metrics ?? []) as MetricRow[];

  return (
    <Card title="指标对比">
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Typography.Text>
          指标来源：{comparison.data?.source ?? "unavailable"}
        </Typography.Text>
        <Table<MetricRow>
          rowKey={(record) => String(record.name)}
          loading={comparison.isLoading}
          dataSource={rows}
          locale={{ emptyText: <Empty description="暂无 artifact 指标" /> }}
          columns={[
            { title: "指标", dataIndex: "name", render: valueText },
            { title: "单位", dataIndex: "unit", render: valueText },
            { title: "PCSC", dataIndex: "pcsc", render: valueText },
            { title: "ETEAC", dataIndex: "eteac", render: valueText },
            { title: "AUTO", dataIndex: "auto", render: valueText },
          ]}
        />
      </Space>
    </Card>
  );
}
