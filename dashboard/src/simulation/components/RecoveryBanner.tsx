import { Alert } from "antd";

import type { components } from "../../api/generated/schema";

// RecoveryBanner 只在存在 interrupted job 或不完整 artifact 时提示人工关注。
type Props = {
  recovery?: components["schemas"]["RecoveryResponse"];
};

export function RecoveryBanner({ recovery }: Props) {
  if (!recovery) return null;
  const interrupted = recovery.interrupted_jobs ?? [];
  const incomplete = recovery.incomplete_artifacts ?? [];
  if (!interrupted.length && !incomplete.length) {
    return null;
  }
  return (
    <Alert
      showIcon
      type={incomplete.length ? "error" : "warning"}
      message={`${interrupted.length} interrupted jobs, ${incomplete.length} incomplete artifacts`}
    />
  );
}
