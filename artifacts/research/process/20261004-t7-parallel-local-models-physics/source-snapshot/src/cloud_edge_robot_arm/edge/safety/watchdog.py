"""安全 watchdog。

通过 heartbeat 检测执行器是否卡死，超时后触发回调并记录 watchdog 状态。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Any


@dataclass
class WatchdogState:
    last_heartbeat: float = field(default_factory=time.monotonic)
    timeout_ms: int = 30_000
    _stop_event: Event = field(default_factory=Event)

    def heartbeat(self) -> None:
        self.last_heartbeat = time.monotonic()

    def is_expired(self) -> bool:
        elapsed = (time.monotonic() - self.last_heartbeat) * 1000
        return elapsed > self.timeout_ms

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.last_heartbeat) * 1000

    def stop(self) -> None:
        self._stop_event.set()


class Watchdog:
    def __init__(
        self,
        *,
        timeout_ms: int = 30_000,
        on_timeout: Callable[[], Any] | None = None,
    ) -> None:
        self._state = WatchdogState(timeout_ms=timeout_ms)
        self._on_timeout = on_timeout
        self._thread: Thread | None = None

    @property
    def state(self) -> WatchdogState:
        return self._state

    def start(self) -> None:
        self._state.heartbeat()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._state.stop()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def heartbeat(self) -> None:
        self._state.heartbeat()

    def is_expired(self) -> bool:
        return self._state.is_expired()

    def _run(self) -> None:
        while not self._state._stop_event.is_set():
            if self._state.is_expired():
                if self._on_timeout is not None:
                    self._on_timeout()
                break
            self._state._stop_event.wait(timeout=0.1)
