import { Card, Empty, Table } from "antd";

export function AuditLogPage() {
  return (
    <Card title="审计事件">
      <Table
        rowKey="sequence"
        dataSource={[]}
        locale={{
          emptyText: <Empty description="暂无控制台审计事件" />,
        }}
        columns={[
          { title: "时间", dataIndex: "timestamp" },
          { title: "事件类型", dataIndex: "event_type" },
          { title: "来源", dataIndex: "source" },
          { title: "原因码", dataIndex: "reason_code" },
          { title: "序号", dataIndex: "sequence" },
        ]}
      />
    </Card>
  );
}
