// 事件时间线组装器：统一排序和去重运行事件，保留虚拟时间与事件来源。
import type { TimelineEvent, TimelineItem } from "../domain/TimelineEvent";

// EventTimelineAssembler 负责把持久化事件转换为 UI 时间线项，不丢弃原始事件。
export class EventTimelineAssembler {
  static assemble(events: TimelineEvent[]): TimelineItem[] {
    return [...events]
      .sort((left, right) => left.sequence - right.sequence)
      .map((event) => ({
        key: String(event.sequence),
        label: event.event_type,
        detail: `${event.source} @ ${event.virtual_time_ms ?? 0}ms`,
        virtual_time_ms: event.virtual_time_ms ?? 0,
        severity: event.severity ?? "info",
      }));
  }
}
