// 租约状态组件：呈现 worker lease 与心跳信息，帮助识别中断和恢复场景。
import { Descriptions } from "antd";

import type { components } from "../../api/generated/schema";

// LeaseStatus 展示当前 worker/lease/attempt，帮助确认任务是否由持久租约保护。
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
