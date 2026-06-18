import { Card, Empty, Table } from "antd";

import { useDashboardAuditEvents } from "../api/queries";

// 审计页读取后端事件流快照，保留 sequence 顺序，便于核对 WebSocket 与轮询事件。
export function AuditLogPage() {
  const audit = useDashboardAuditEvents();
  return (
    <Card title="审计事件">
      <Table
        rowKey="sequence"
        loading={audit.isLoading}
        dataSource={audit.data?.events ?? []}
        pagination={{ pageSize: 50 }}
        locale={{
          emptyText: <Empty description="暂无控制台审计事件" />,
        }}
        columns={[
          { title: "时间", dataIndex: "timestamp" },
          { title: "事件类型", dataIndex: "event_type" },
          { title: "来源", dataIndex: "source" },
          { title: "任务", dataIndex: "task_id" },
          { title: "实验", dataIndex: "experiment_id" },
          { title: "序号", dataIndex: "sequence" },
        ]}
      />
    </Card>
  );
}
