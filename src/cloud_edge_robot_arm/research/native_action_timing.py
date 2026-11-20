"""Opt-in, worker-local monotonic timing for the whole-action development run."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar
from functools import wraps
from threading import get_ident
from time import monotonic_ns
from typing import Any, ParamSpec, TypeVar

_ACTIVE: ContextVar[ActionTiming | None] = ContextVar("native_action_timing", default=None)
_P = ParamSpec("_P")
_T = TypeVar("_T")


class ActionTiming:
    """Retain raw same-thread boundaries in memory; serialize after the action."""

    def __init__(self) -> None:
        self._marks: list[dict[str, Any]] = []
        self._spans: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []
        self._thread_id: int | None = None

    def mark(
        self, label: str, *, now_ns: int | None = None, physics_step: int | None = None
    ) -> None:
        self._marks.append(
            dict(
                label=label,
                ns=monotonic_ns() if now_ns is None else now_ns,
                physics_step=physics_step,
            )
        )

    @contextmanager
    def _span(
        self, label: str, operation_id: int | None, acquisition_id: str | None
    ) -> Iterator[None]:
        start = monotonic_ns()
        parent = self._stack[-1] if self._stack else {}
        if operation_id is None:
            operation_id = parent.get("operation_id")
        if acquisition_id is None and operation_id == parent.get("operation_id"):
            acquisition_id = parent.get("acquisition_id")
        row = dict(
            seq=len(self._spans) + 1,
            parent=parent.get("seq"),
            label=label,
            start_ns=start,
            end_ns=None,
            operation_id=operation_id,
            acquisition_id=acquisition_id,
        )
        self._spans.append(row)
        self._stack.append(row)
        try:
            yield
        finally:
            row["end_ns"] = monotonic_ns()
            self._stack.pop()

    def payload(self) -> dict[str, Any]:
        return dict(
            schema_version="native.whole-action.timing.v1",
            clock="monotonic_ns",
            thread_id=self._thread_id,
            marks=[dict(row) for row in self._marks],
            spans=[dict(row) for row in self._spans],
        )


@contextmanager
def use_action_timing(timing: ActionTiming) -> Iterator[None]:
    timing._thread_id = get_ident()
    token = _ACTIVE.set(timing)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def _current() -> ActionTiming | None:
    timing = _ACTIVE.get()
    if timing is None or timing._thread_id != get_ident():
        return None
    return timing


def mark_timing(label: str, *, now_ns: int | None = None, physics_step: int | None = None) -> None:
    timing = _current()
    if timing is not None:
        timing.mark(label, now_ns=now_ns, physics_step=physics_step)


def timed(
    label: str, *, operation_id: int | None = None, acquisition_id: str | None = None
) -> AbstractContextManager[None]:
    timing = _current()
    if timing is None:
        return nullcontext()
    return timing._span(label, operation_id, acquisition_id)


def timed_call(label: str) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    def decorate(function: Callable[_P, _T]) -> Callable[_P, _T]:
        @wraps(function)
        def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            timing = _current()
            if timing is None:
                return function(*args, **kwargs)
            with timing._span(label, None, None):
                return function(*args, **kwargs)

        return wrapped

    return decorate
