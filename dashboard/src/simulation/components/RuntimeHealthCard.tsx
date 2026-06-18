import { Card, Descriptions } from "antd";

import { StatusBadge } from "../../components/StatusBadge";
import type { components } from "../../api/generated/schema";

type Props = {
  health?: components["schemas"]["RuntimeHealthResponse"];
};

export function RuntimeHealthCard({ health }: Props) {
  return (
    <Card title="Runtime Health" size="small">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="Status">
          <StatusBadge status={health?.status ?? "UNKNOWN"} />
        </Descriptions.Item>
        <Descriptions.Item label="Database">
          {health?.database ?? "sqlite"}
        </Descriptions.Item>
        <Descriptions.Item label="Controller contacted">
          {String(health?.real_controller_contacted ?? false)}
        </Descriptions.Item>
        <Descriptions.Item label="Hardware motion">
          {String(health?.hardware_motion_observed ?? false)}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
