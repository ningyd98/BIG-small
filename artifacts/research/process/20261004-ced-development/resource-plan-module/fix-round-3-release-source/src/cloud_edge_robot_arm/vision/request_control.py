"""Bounded callers and one actual in-flight request per visual provider."""

from __future__ import annotations

import math
import queue
import threading
import time
from collections.abc import Callable
from typing import cast

_registry_lock = threading.Lock()
_provider_slots: dict[str, threading.BoundedSemaphore] = {}


class ModelCallCancelled(RuntimeError):
    """Caller cancelled; a late response must never dispatch motion."""


class ModelCallTimedOut(TimeoutError):
    """The caller's deadline expired, including time spent waiting for capacity."""


def bounded_model_call[T](
    call: Callable[[], T],
    *,
    timeout_s: float,
    cancelled: Callable[[], bool] | None = None,
    resource_key: str = "visual-provider",
    on_wait: Callable[[], object] | None = None,
) -> T:
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ModelCallTimedOut("visual request deadline expired")
    deadline = time.monotonic() + timeout_s

    def check() -> None:
        if cancelled is not None and cancelled():
            raise ModelCallCancelled("visual request cancelled; result discarded")
        if on_wait is not None:
            on_wait()
        if time.monotonic() >= deadline:
            raise ModelCallTimedOut("visual request deadline expired; result discarded")

    with _registry_lock:
        slot = _provider_slots.setdefault(resource_key, threading.BoundedSemaphore(1))
    while True:
        check()
        if slot.acquire(timeout=min(0.025, max(0, deadline - time.monotonic()))):
            break
    try:
        check()
    except BaseException:
        slot.release()
        raise
    result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            result.put((True, call()))
        except BaseException as exc:
            result.put((False, exc))
        finally:
            # Only the actual request can free capacity, even if the caller left.
            slot.release()

    threading.Thread(target=invoke, name="bounded-visual-request", daemon=True).start()
    while True:
        check()
        try:
            ok, value = result.get(timeout=min(0.025, max(0, deadline - time.monotonic())))
        except queue.Empty:
            continue
        check()
        if not ok:
            raise cast(BaseException, value)
        return cast(T, value)
