// 队列状态面板：展示持久化运行时队列统计，提交后不假设任务已完成。
import { Card, Descriptions, Progress } from "antd";

import type { components } from "../../api/generated/schema";

// QueueStatusPanel 展示后端持久队列状态；容量百分比只是提示，不在前端放行任务。
type Props = {
  queue?: components["schemas"]["QueueStatusResponse"];
};

export function QueueStatusPanel({ queue }: Props) {
  const capacity =
    queue && queue.max_queued_jobs > 0
      ? Math.round((queue.queued / queue.max_queued_jobs) * 100)
      : 0;
  return (
    <Card title="Queue" size="small">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="Queued">
          {queue?.queued ?? 0}
        </Descriptions.Item>
        <Descriptions.Item label="Running">
          {queue?.running ?? 0}
        </Descriptions.Item>
        <Descriptions.Item label="Blocked">
          {queue?.blocked ?? 0}
        </Descriptions.Item>
        <Descriptions.Item label="Batch limit">
          {queue?.max_batch_runs ?? 120}
        </Descriptions.Item>
      </Descriptions>
      <Progress percent={capacity} size="small" />
    </Card>
  );
}
