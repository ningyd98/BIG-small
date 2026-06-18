// 取消进度组件：展示后端 cooperative cancellation 状态，不直接终止本地进程。
import { Alert } from "antd";

import type { components } from "../../api/generated/schema";

// CancellationProgress 只显示取消进度；真正的取消由后端 worker 协作完成。
type Props = {
  run?: components["schemas"]["SimulationRunRecord"];
};

export function CancellationProgress({ run }: Props) {
  const status = run?.status ?? "";
  if (
    !run?.cancel_requested &&
    !["CANCEL_REQUESTED", "CANCELLING"].includes(status)
  ) {
    return null;
  }
  return <Alert showIcon type="warning" message={`Cancellation ${status}`} />;
}
