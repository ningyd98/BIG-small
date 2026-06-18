import { Card, Empty, Table } from "antd";

import type { components } from "../../api/generated/schema";

type Props = {
  attempts?: components["schemas"]["AttemptView"][];
};

export function AttemptHistory({ attempts = [] }: Props) {
  return (
    <Card title="Attempts" size="small">
      <Table
        size="small"
        pagination={false}
        rowKey="attempt"
        dataSource={attempts}
        locale={{ emptyText: <Empty description="No attempts" /> }}
        columns={[
          { title: "Attempt", dataIndex: "attempt" },
          { title: "Worker", dataIndex: "worker_id" },
          { title: "Result", dataIndex: "result" },
          { title: "Error", dataIndex: "error" },
        ]}
      />
    </Card>
  );
}
