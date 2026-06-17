import { Card, Table, Typography } from "antd";

const rows = [
  {
    metric: "success_rate",
    unit: "%",
    pcsc: "artifact",
    eteac: "artifact",
    auto: "artifact",
  },
  {
    metric: "completion_time_ms",
    unit: "ms",
    pcsc: "artifact",
    eteac: "artifact",
    auto: "artifact",
  },
  {
    metric: "cloud_call_count",
    unit: "count",
    pcsc: "artifact",
    eteac: "artifact",
    auto: "artifact",
  },
];

export function ComparisonPage() {
  return (
    <Card title="指标对比">
      <Typography.Paragraph>
        对比页展示 PCSC / ETEAC / AUTO
        的数值和单位；不以单一雷达图作为结论依据。
      </Typography.Paragraph>
      <Table
        rowKey="metric"
        dataSource={rows}
        columns={[
          { title: "指标", dataIndex: "metric" },
          { title: "单位", dataIndex: "unit" },
          { title: "PCSC", dataIndex: "pcsc" },
          { title: "ETEAC", dataIndex: "eteac" },
          { title: "AUTO", dataIndex: "auto" },
        ]}
      />
    </Card>
  );
}
