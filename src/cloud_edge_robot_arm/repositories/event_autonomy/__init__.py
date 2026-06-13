"""Event autonomy persistence — Phase 6 repository layer.

Provides:
- EventAutonomyRepository: Protocol defining the persistence contract
- InMemoryEventAutonomyRepository: Thread-safe in-memory impl (test/CI only)
- SQLiteEventAutonomyRepository: Production-grade SQLite impl (CAS semantics)
"""

from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    EventAutonomyRepository,
)

__all__ = [
    "EventAutonomyRepository",
]
