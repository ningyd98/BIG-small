// 尝试历史组件：展示持久化 attempt 记录，区分最终结果和历史执行尝试。
import { Card, Empty, Table } from "antd";

import type { components } from "../../api/generated/schema";

// AttemptHistory 展示持久化 attempt 审计，不把失败 attempt 覆盖成最终结果。
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
