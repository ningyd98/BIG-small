import { Alert } from "antd";

import type { components } from "../../api/generated/schema";

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
