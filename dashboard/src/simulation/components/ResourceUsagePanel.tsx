import { Card, Descriptions } from "antd";

import type { components } from "../../api/generated/schema";

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
