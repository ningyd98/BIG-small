"""OutboxDispatcher — background message sender with exponential backoff.

Transactional outbox: persist-before-send, CAS claim, exponential backoff,
DEAD_LETTER on max retries. At-least-once delivery with consumer-side
idempotency-key deduplication.

Lifecycle: PENDING → SENDING → SENT
           PENDING → SENDING → PENDING (retry with backoff)
           PENDING → SENDING → DEAD_LETTER (max retries)
Outbox 后台发送器。

发送器通过 CAS claim、指数退避和 DEAD_LETTER 状态实现至少一次投递；消费者必须使用幂等键去重。

"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts.models import PendingMessage
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    EventAutonomyRepository,
)


class OutboxDispatcher:
    """Dispatches pending outbox messages with retry and backoff.

    - CAS claim prevents duplicate sending across multiple dispatchers
    - Exponential backoff: base_ms * 2^(retry_count - 1)
    - DEAD_LETTER after max_retries exceeded
    - Graceful shutdown via stop()
    - Injectable clock for deterministic testing
    """

    def __init__(
        self,
        *,
        repository: EventAutonomyRepository,
        send_fn: Callable[[PendingMessage], bool],
        poll_interval_ms: int = 1000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._send_fn = send_fn
        self._poll_interval = poll_interval_ms / 1000.0
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="outbox-dispatcher"
        )
        self._thread.start()

    def stop(self, *, join_timeout_s: float = 5.0) -> None:
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=join_timeout_s)

    @property
    def is_running(self) -> bool:
        return self._running

    def _dispatch_loop(self) -> None:
        while self._running:
            msg = self._repo.claim_outbox_message()
            if msg is None:
                self._sleep(self._poll_interval)
                continue
            try:
                success = self._send_fn(msg)
                if success:
                    self._repo.mark_outbox_sent(msg.message_id)
                else:
                    self._repo.mark_outbox_failed(msg.message_id, "send_fn returned false")
            except Exception as exc:
                self._repo.mark_outbox_failed(msg.message_id, str(exc))

    def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        end = self._clock() + timedelta(seconds=seconds)
        while self._running:
            now = self._clock()
            if now >= end:
                break
            remaining = (end - now).total_seconds()
            time.sleep(min(0.1, max(0, remaining)))
