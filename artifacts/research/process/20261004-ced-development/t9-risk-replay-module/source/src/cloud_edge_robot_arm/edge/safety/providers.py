"""安全数据 provider 协议。

Provider 提供遥测、场景和工作空间数据；缺失或过期数据应由规则 fail-closed 处理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from cloud_edge_robot_arm.edge.safety.models import Obstacle, WorkspaceDefinition


@dataclass(frozen=True)
class TelemetrySample:
    timestamp: datetime
    tcp_velocity: float
    joint_velocities: list[float] = field(default_factory=list)
    acceleration: float = 0.0


@dataclass(frozen=True)
class SceneSnapshot:
    scene_version: int
    updated_at: datetime
    obstacles: list[Obstacle] = field(default_factory=list)
    forbidden_zones: list[WorkspaceDefinition] = field(default_factory=list)


@runtime_checkable
class TelemetryProvider(Protocol):
    def latest(self) -> TelemetrySample | None: ...


@runtime_checkable
class SceneStateProvider(Protocol):
    def snapshot(self) -> SceneSnapshot | None: ...


class MockTelemetryProvider:
    """Telemetry provider that derives a fresh sample from wall clock.

    Use ``missing=True`` to simulate the provider failing to deliver telemetry
    (fail-closed -> PAUSE) and ``stale_ms`` to simulate an outdated sample.
    """

    def __init__(
        self,
        *,
        tcp_velocity: float = 0.0,
        joint_velocities: list[float] | None = None,
        acceleration: float = 0.0,
        missing: bool = False,
        stale_ms: int | None = None,
    ) -> None:
        self._tcp_velocity = tcp_velocity
        self._joint_velocities = list(joint_velocities or [])
        self._acceleration = acceleration
        self._missing = missing
        self._stale_ms = stale_ms

    def latest(self) -> TelemetrySample | None:
        if self._missing:
            return None
        now = datetime.now(UTC)
        timestamp = now if self._stale_ms is None else now - timedelta(milliseconds=self._stale_ms)
        return TelemetrySample(
            timestamp=timestamp,
            tcp_velocity=self._tcp_velocity,
            joint_velocities=list(self._joint_velocities),
            acceleration=self._acceleration,
        )


class MockSceneStateProvider:
    """Scene provider that freezes the scene state at construction time.

    The ``robot`` argument is only read once during ``__init__`` to capture
    the initial ``scene_version``; subsequent calls to ``snapshot()`` return
    the frozen version.
    """

    def __init__(
        self,
        robot: Any,
        *,
        initial_scene_version: int | None = None,
        obstacles: list[Obstacle] | None = None,
        forbidden_zones: list[WorkspaceDefinition] | None = None,
        missing: bool = False,
        stale_ms: int | None = None,
    ) -> None:
        self._obstacles = list(obstacles or [])
        self._forbidden_zones = list(forbidden_zones or [])
        self._missing = missing
        self._stale_ms = stale_ms
        self._frozen_scene_version: int = (
            initial_scene_version
            if initial_scene_version is not None
            else getattr(robot, "scene_version", 1)
        )

    def snapshot(self) -> SceneSnapshot | None:
        if self._missing:
            return None
        now = datetime.now(UTC)
        updated_at = now if self._stale_ms is None else now - timedelta(milliseconds=self._stale_ms)
        return SceneSnapshot(
            scene_version=self._frozen_scene_version,
            updated_at=updated_at,
            obstacles=list(self._obstacles),
            forbidden_zones=list(self._forbidden_zones),
        )
