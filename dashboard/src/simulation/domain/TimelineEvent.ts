// 时间线事件类型，统一故障注入、SafetyShield 和运行状态事件。
import type { components } from "../../api/generated/schema";

export type TimelineEvent = Omit<
  components["schemas"]["TimelineEvent"],
  "severity"
> & {
  run_id?: string;
  severity?: string;
};

export type TimelineItem = {
  key: string;
  label: string;
  detail: string;
  virtual_time_ms: number;
  severity: string;
};
