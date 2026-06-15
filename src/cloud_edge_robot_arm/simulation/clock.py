from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(order=True)
class _ScheduledEvent:
    time_ms: int
    priority: int
    sequence: int
    callback: Callable[[], None] = field(compare=False)


class VirtualClock:
    def __init__(self, *, start_ms: int = 0, max_time_ms: int | None = None) -> None:
        if start_ms < 0:
            raise ValueError("start_ms must be non-negative")
        self._now_ms = start_ms
        self._max_time_ms = max_time_ms
        self._sequence = 0
        self._events: list[_ScheduledEvent] = []

    @property
    def now_ms(self) -> int:
        return self._now_ms

    def schedule(
        self,
        delay_ms: int,
        callback: Callable[[], None],
        *,
        priority: int = 0,
    ) -> int:
        if delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")
        scheduled_at = self._now_ms + delay_ms
        if self._max_time_ms is not None and scheduled_at > self._max_time_ms:
            raise ValueError("scheduled event exceeds maximum virtual time")
        self._sequence += 1
        event = _ScheduledEvent(
            time_ms=scheduled_at,
            priority=priority,
            sequence=self._sequence,
            callback=callback,
        )
        heapq.heappush(self._events, event)
        return event.sequence

    def advance(self, delta_ms: int) -> None:
        if delta_ms < 0:
            raise ValueError("delta_ms must be non-negative")
        target = self._now_ms + delta_ms
        if self._max_time_ms is not None and target > self._max_time_ms:
            raise ValueError("advance exceeds maximum virtual time")
        self.run_until(target)

    def run_until(self, target_ms: int) -> None:
        if target_ms < self._now_ms:
            raise ValueError("target_ms must not go backwards")
        if self._max_time_ms is not None and target_ms > self._max_time_ms:
            raise ValueError("target_ms exceeds maximum virtual time")
        while self._events and self._events[0].time_ms <= target_ms:
            event = heapq.heappop(self._events)
            self._now_ms = event.time_ms
            event.callback()
        self._now_ms = target_ms

    def run_until_idle(self) -> None:
        while self._events:
            event = heapq.heappop(self._events)
            if self._max_time_ms is not None and event.time_ms > self._max_time_ms:
                raise ValueError("event exceeds maximum virtual time")
            self._now_ms = event.time_ms
            event.callback()

    def has_pending_events(self) -> bool:
        return bool(self._events)
