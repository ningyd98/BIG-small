"""Edge outbox — persistent pending message queue for Phase 6.

Persist-before-send semantics: messages are persisted before transmission.
Network recovery: messages are retried with idempotency keys and backoff.
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts.models import MessageStatus, PendingMessage


@runtime_checkable
class PendingMessageRepository(Protocol):
    """Protocol for pending message persistence.

    Messages are persisted before send. On send success, status → SENT.
    On send failure, status → FAILED with retry counting and backoff.
    """

    def enqueue(self, message: PendingMessage) -> None:
        """Persist a message before attempting to send."""
        ...

    def dequeue(self, task_id: str | None = None) -> PendingMessage | None:
        """Get the next pending message to send."""
        ...

    def mark_sent(self, message_id: str) -> None:
        """Mark a message as successfully sent."""
        ...

    def mark_failed(self, message_id: str, error: str) -> None:
        """Mark a message as failed, increment retry count."""
        ...

    def list_pending(self, task_id: str | None = None) -> list[PendingMessage]:
        """List all messages in PENDING or FAILED (with retries remaining) state."""
        ...

    def count_pending(self, task_id: str | None = None) -> int:
        """Count pending messages."""
        ...

    def close(self) -> None:
        """Release resources."""
        ...


class InMemoryPendingMessageRepository:
    """Thread-safe in-memory implementation for testing."""

    def __init__(self) -> None:
        self._messages: dict[str, PendingMessage] = {}
        self._lock = threading.Lock()

    def enqueue(self, message: PendingMessage) -> None:
        with self._lock:
            self._messages[message.message_id] = message

    def dequeue(self, task_id: str | None = None) -> PendingMessage | None:
        with self._lock:
            for _msg_id, msg in self._messages.items():
                if msg.status != MessageStatus.PENDING:
                    continue
                if task_id is not None and msg.task_id != task_id:
                    continue
                msg.status = MessageStatus.SENDING
                return msg
        return None

    def mark_sent(self, message_id: str) -> None:
        with self._lock:
            if message_id in self._messages:
                self._messages[message_id].status = MessageStatus.SENT

    def mark_failed(self, message_id: str, error: str) -> None:
        with self._lock:
            if message_id in self._messages:
                msg = self._messages[message_id]
                msg.retry_count += 1
                msg.last_error = error
                if msg.retry_count >= msg.max_retries:
                    msg.status = MessageStatus.FAILED
                else:
                    msg.status = MessageStatus.PENDING

    def list_pending(self, task_id: str | None = None) -> list[PendingMessage]:
        with self._lock:
            result = []
            for msg in self._messages.values():
                if msg.status in (MessageStatus.PENDING,):
                    if task_id is None or msg.task_id == task_id:
                        result.append(msg)
            return result

    def count_pending(self, task_id: str | None = None) -> int:
        return len(self.list_pending(task_id))

    def close(self) -> None:
        with self._lock:
            self._messages.clear()
