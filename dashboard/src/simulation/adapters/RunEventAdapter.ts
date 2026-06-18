// 运行事件适配器，负责 sequence 去重和 timeline 事件归一化。
import type { TimelineEvent } from "../domain/TimelineEvent";

export function eventSeverity(event: TimelineEvent): string {
  if (
    event.event_type.includes("failed") ||
    event.event_type.includes("reject")
  )
    return "error";
  if (event.event_type.includes("blocked")) return "warning";
  return event.severity ?? "info";
}
