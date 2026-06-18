"""事件自治仓储包，保存恢复预算、检查点、消息 outbox 和重规划记录。

Event autonomy persistence — Phase 6 repository layer.
"""

from cloud_edge_robot_arm.repositories.event_autonomy.hashing import stable_payload_hash
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    EventAutonomyRepository,
    IdempotencyConflictError,
    RepositoryConflictError,
    VersionConflictError,
)
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository

__all__ = [
    "EventAutonomyRepository",
    "IdempotencyConflictError",
    "InMemoryEventAutonomyRepository",
    "RepositoryConflictError",
    "SQLiteEventAutonomyRepository",
    "VersionConflictError",
    "stable_payload_hash",
]
