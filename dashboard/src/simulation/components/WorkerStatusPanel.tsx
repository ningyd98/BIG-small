import { Card, Table, Tag } from "antd";

import type { components } from "../../api/generated/schema";

// WorkerStatusPanel 展示固定 worker 列表；用户不能从 UI 提交任意 runner。
type Props = {
  workers?: components["schemas"]["WorkerStatusView"][];
};

export function WorkerStatusPanel({ workers = [] }: Props) {
  return (
    <Card title="Workers" size="small">
      <Table
        size="small"
        pagination={false}
        rowKey="worker_id"
        dataSource={workers}
        columns={[
          { title: "Worker", dataIndex: "worker_id" },
          { title: "Backend", dataIndex: "backend" },
          {
            title: "Status",
            dataIndex: "status",
            render: (status: string) => (
              <Tag color={status === "BUSY" ? "processing" : "default"}>
                {status}
              </Tag>
            ),
          },
          { title: "Job", dataIndex: "active_job_id" },
        ]}
      />
    </Card>
  );
}
