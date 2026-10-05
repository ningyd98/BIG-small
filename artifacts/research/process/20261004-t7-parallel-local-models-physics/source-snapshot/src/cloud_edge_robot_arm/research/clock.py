"""Advance physics while requests wait; never equate fast action steps with wall time."""

from __future__ import annotations

import math
import time
from collections.abc import Callable


class ExperimentClock:
    def __init__(self, physics_dt_s: float, advance: Callable[[int], object]) -> None:
        if not math.isfinite(physics_dt_s) or physics_dt_s <= 0:
            raise ValueError("finite positive physics timestep required")
        self._dt, self._advance = physics_dt_s, advance
        self._started = self._wait_anchor = time.monotonic()
        self._wait_steps = 0

    def begin_wait(self) -> None:
        self._wait_anchor = time.monotonic()

    def advance_wait(self) -> None:
        now = time.monotonic()
        steps = int((now - self._wait_anchor) / self._dt)
        if steps:
            self._advance(steps)
            self._wait_steps += steps
            self._wait_anchor += steps * self._dt

    def wall_elapsed_s(self) -> float:
        return time.monotonic() - self._started

    def sim_elapsed_s(self) -> float:
        return self._wait_steps * self._dt

    def mapping(self) -> dict[str, float | str]:
        return {"wall_s": self.wall_elapsed_s(), "wait_sim_s": self.sim_elapsed_s(),
                "physics_dt_s": self._dt,
                "mapping": "request waits advance physics at 1 sim second/wall second"}
