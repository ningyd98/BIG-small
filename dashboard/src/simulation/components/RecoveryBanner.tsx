import { Alert } from "antd";

import type { components } from "../../api/generated/schema";

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
