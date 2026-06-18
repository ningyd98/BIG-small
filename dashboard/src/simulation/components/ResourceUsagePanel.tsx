// 资源用量面板：展示运行时资源限制和当前占用，辅助判断排队或拒绝原因。
import { Card, Descriptions } from "antd";

import type { components } from "../../api/generated/schema";

// ResourceUsagePanel 展示后端资源策略，前端不能绕过 max queue/batch 限制。
type Props = {
  queue?: components["schemas"]["QueueStatusResponse"];
};

export function ResourceUsagePanel({ queue }: Props) {
  return (
    <Card title="Resource Policy" size="small">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="Max queued">
          {queue?.max_queued_jobs ?? 500}
        </Descriptions.Item>
        <Descriptions.Item label="Max batch">
          {queue?.max_batch_runs ?? 120}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
