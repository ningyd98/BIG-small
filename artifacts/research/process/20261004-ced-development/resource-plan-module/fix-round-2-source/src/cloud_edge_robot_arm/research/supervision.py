"""Independent wall-clock PCSC ticks; MuJoCo snapshots stay on the owner thread."""

from __future__ import annotations

import math
import queue
import threading
import time
from collections.abc import Callable
from typing import Any


class PeriodicSupervision:
    def __init__(self, period_s: float, infer: Callable[[Any], Any],
                 capture: Callable[[], Any]) -> None:
        if not math.isfinite(period_s) or period_s <= 0:
            raise ValueError("finite positive supervision period required")
        self.period_s, self._infer, self._capture = period_s, infer, capture
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._ticks = self._observed_ticks = self._merged = self._sent = 0
        self._pending: Any = None
        self._worker: threading.Thread | None = None
        self._result: queue.Queue[Any] = queue.Queue(maxsize=1)
        self._deferred: list[Any] = []
        self._ticker: threading.Thread | None = None
        self._closed = False

    def __enter__(self) -> PeriodicSupervision:
        def tick() -> None:
            deadline = time.monotonic() + self.period_s
            while not self._stop.wait(max(0., deadline - time.monotonic())):
                with self._lock:
                    self._ticks += 1
                deadline += self.period_s

        self._ticker = threading.Thread(target=tick, name="pcsc-tick", daemon=True)
        self._ticker.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._closed = True
        self._stop.set()
        if self._ticker is not None:
            self._ticker.join(timeout=1)
        # Late calls remain real costs; they cannot apply after this episode closes.
        self._pending = None
        self._deferred.clear()

    def poll(self, *, atomic_action_active: bool) -> list[Any]:
        if self._closed:
            return []
        with self._lock:
            ticks = self._ticks
        if ticks > self._observed_ticks:
            self._merged += max(0, ticks - self._observed_ticks - 1)
            self._observed_ticks = ticks
            if self._pending is not None:
                self._merged += 1
            self._pending = self._capture()
        if self._worker is not None and not self._worker.is_alive():
            self._deferred.append(self._result.get_nowait())
            self._worker = None
        if self._worker is None and self._pending is not None:
            frame, self._pending = self._pending, None
            self._sent += 1

            def invoke() -> None:
                try:
                    result = self._infer(frame)
                except Exception as exc:
                    result = exc
                self._result.put(result)

            self._worker = threading.Thread(target=invoke, name="pcsc-infer", daemon=True)
            self._worker.start()
        if atomic_action_active:
            return []
        results, self._deferred = self._deferred, []
        return results

    def snapshot(self) -> dict[str, int | bool]:
        return {"ticks": self._ticks, "sent": self._sent, "merged_pending": self._merged,
                "inflight": self._worker is not None and self._worker.is_alive(),
                "pending": self._pending is not None, "closed": self._closed}
