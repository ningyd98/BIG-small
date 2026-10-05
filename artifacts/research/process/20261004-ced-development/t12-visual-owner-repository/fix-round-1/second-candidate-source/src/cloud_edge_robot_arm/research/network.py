"""Bidirectional, seeded application transport injection; schedule stays offline."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NetworkSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schedule_id: str = Field(min_length=1)
    rtt_ms: float = Field(ge=0, allow_inf_nan=False)
    jitter_fraction: float = Field(default=.2, ge=0, le=1, allow_inf_nan=False)
    loss_rate: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    bandwidth_mbit_s: float = Field(default=10, gt=0, allow_inf_nan=False)
    outages: tuple[tuple[float, float], ...] = ()
    seed: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_outages(self) -> NetworkSchedule:
        import math

        if any(not math.isfinite(a + b) or a < 0 or b <= a for a, b in self.outages):
            raise ValueError("outages require finite ordered start/end seconds")
        return self


class NetworkCostSnapshot(BaseModel):
    observed_rtt_s: float | None
    observed_roundtrip_s: float | None = None
    observed_loss_rate: float | None
    observed_bandwidth_bytes_s: float | None
    sampled_at: datetime


@dataclass(frozen=True)
class _Transfer:
    downlink_s: float
    started_at: float


class NetworkInjector:
    def __init__(self, schedule: NetworkSchedule, *, wait: Callable[[float], None] = time.sleep):
        self._schedule, self._wait = schedule, wait
        self._rng = random.Random(schedule.seed)
        self._lock = threading.RLock()
        self._started = time.monotonic()
        self._attempts = self._lost = 0
        self._roundtrips: list[float] = []

    def sample_delays(self) -> tuple[float, float]:
        with self._lock:
            s = self._schedule
            rtt = s.rtt_ms / 1000 * (1 + self._rng.uniform(-s.jitter_fraction, s.jitter_fraction))
            return rtt / 2, rtt / 2

    def _bandwidth_delay(self, length: int) -> float:
        if length < 0:
            raise ValueError("payload length must be nonnegative")
        return length * 8 / (self._schedule.bandwidth_mbit_s * 1_000_000)

    def begin(self, sent_bytes: int) -> _Transfer:
        started = time.monotonic()
        up, down = self.sample_delays()
        with self._lock:
            elapsed = time.monotonic() - self._started
            outage = any(a <= elapsed < b for a, b in self._schedule.outages)
            lost = outage or self._rng.random() < self._schedule.loss_rate
            self._attempts += 1
            self._lost += int(lost)
        self._wait(up + self._bandwidth_delay(sent_bytes))
        if lost:
            raise TimeoutError("injected request loss/outage; no model result")
        return _Transfer(down, started)

    def finish(self, transfer: _Transfer, received_bytes: int) -> None:
        self._wait(transfer.downlink_s + self._bandwidth_delay(received_bytes))
        with self._lock:
            elapsed = time.monotonic() - self._started
            lost = any(a <= elapsed < b for a, b in self._schedule.outages) or (
                self._rng.random() < self._schedule.loss_rate
            )
            self._lost += int(lost)
            self._roundtrips.append(time.monotonic() - transfer.started_at)
        if lost:
            raise TimeoutError("injected response loss/outage; sent request remains a cost")

    def snapshot(self) -> NetworkCostSnapshot:
        with self._lock:
            return NetworkCostSnapshot(
                # An HTTP round trip includes provider inference; it cannot identify RTT
                # or link bandwidth. Injection truth is retained only in offline artifacts.
                observed_rtt_s=None,
                observed_roundtrip_s=(sum(self._roundtrips) / len(self._roundtrips)
                                      if self._roundtrips else None),
                observed_loss_rate=self._lost / self._attempts if self._attempts else None,
                observed_bandwidth_bytes_s=None,
                sampled_at=datetime.now(UTC),
            )
