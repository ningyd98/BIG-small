from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from uuid import uuid4

from cloud_edge_robot_arm.dashboard.models import DashboardEvent


class DashboardEventStream:
    def __init__(self, *, max_replay: int = 256) -> None:
        self._sequence = 0
        self._events: deque[DashboardEvent] = deque(maxlen=max_replay)

    def publish(
        self,
        event_type: str,
        source: str,
        payload: dict[str, object],
        *,
        task_id: str = "",
        experiment_id: str = "",
    ) -> DashboardEvent:
        self._sequence += 1
        event = DashboardEvent(
            event_id=str(uuid4()),
            sequence=self._sequence,
            event_type=event_type,
            source=source,
            timestamp=datetime.now(UTC),
            task_id=task_id,
            experiment_id=experiment_id,
            payload=dict(payload),
        )
        self._events.append(event)
        return event

    def append(self, event: DashboardEvent) -> DashboardEvent:
        self._sequence = max(self._sequence, event.sequence)
        self._events.append(event)
        return event

    def heartbeat(self) -> DashboardEvent:
        return self.publish("heartbeat", "dashboard", {})

    def replay_after(self, sequence: int) -> list[DashboardEvent]:
        return [event for event in self._events if event.sequence > sequence]
