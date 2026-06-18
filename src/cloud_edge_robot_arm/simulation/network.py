"""网络仿真模型，描述延迟、抖动、丢包和带宽限制。"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from cloud_edge_robot_arm.experiments.models import NetworkProfile
from cloud_edge_robot_arm.simulation.clock import VirtualClock


@dataclass(frozen=True)
class NetworkMessage:
    message_id: str
    channel: str
    payload_size_bytes: int


class NetworkSimulator:
    def __init__(self, *, profile: NetworkProfile, seed: int, clock: VirtualClock) -> None:
        self._profile = profile
        self._rng = random.Random(seed)
        self._clock = clock
        self._disconnected_until_ms = 0
        self.uploaded_bytes = 0
        self.downloaded_bytes = 0
        self.dropped_count = 0
        self.duplicated_count = 0
        self.reordered_count = 0

    @property
    def connected(self) -> bool:
        return self._clock.now_ms >= self._disconnected_until_ms

    def disconnect(self, *, duration_ms: int) -> None:
        if duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        self._disconnected_until_ms = max(
            self._disconnected_until_ms, self._clock.now_ms + duration_ms
        )

    def send(
        self,
        message: NetworkMessage,
        on_deliver: Callable[[NetworkMessage], None],
        *,
        priority: int = 0,
    ) -> bool:
        if message.payload_size_bytes < 0:
            raise ValueError("payload_size_bytes must be non-negative")
        if not self.connected or not self._profile.cloud_available:
            self.dropped_count += 1
            return False
        if self._rng.random() < self._profile.loss_rate:
            self.dropped_count += 1
            return False

        delivery_count = 2 if self._rng.random() < self._profile.duplication_rate else 1
        if delivery_count == 2:
            self.duplicated_count += 1
        for duplicate_index in range(delivery_count):
            delay_ms = self._latency_ms()
            event_priority = priority
            if self._rng.random() < self._profile.reorder_rate:
                event_priority += 10 + duplicate_index
                delay_ms += self._rng.randint(1, max(1, self._profile.jitter_ms + 1))
                self.reordered_count += 1
            delivery = _delivery_callback(on_deliver, message)
            self._clock.schedule(
                delay_ms,
                delivery,
                priority=event_priority,
            )
        if message.channel == "edge-cloud":
            self.uploaded_bytes += message.payload_size_bytes * delivery_count
        else:
            self.downloaded_bytes += message.payload_size_bytes * delivery_count
        return True

    def _latency_ms(self) -> int:
        latency = self._profile.base_latency_ms
        if self._profile.jitter_ms:
            latency += self._rng.randint(-self._profile.jitter_ms, self._profile.jitter_ms)
        if self._profile.bandwidth_bytes_per_ms is not None:
            latency += 1
        return max(0, latency)


def _delivery_callback(
    on_deliver: Callable[[NetworkMessage], None],
    message: NetworkMessage,
) -> Callable[[], None]:
    def deliver() -> None:
        on_deliver(message)

    return deliver
