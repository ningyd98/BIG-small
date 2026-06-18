import { Descriptions } from "antd";

import type { components } from "../../api/generated/schema";

type Props = {
  run?: components["schemas"]["SimulationRunRecord"];
};

export function LeaseStatus({ run }: Props) {
  return (
    <Descriptions column={1} size="small">
      <Descriptions.Item label="Worker">
        {run?.worker_id || "none"}
      </Descriptions.Item>
      <Descriptions.Item label="Lease">
        {run?.lease_id || "none"}
      </Descriptions.Item>
      <Descriptions.Item label="Attempt">{run?.attempt ?? 0}</Descriptions.Item>
    </Descriptions>
  );
}
