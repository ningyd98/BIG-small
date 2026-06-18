from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository


class InMemorySimulationJobRepository(SQLiteSimulationJobRepository):
    """Test repository with SQLite semantics and process-local storage."""

    def __init__(self) -> None:
        self._tmp = TemporaryDirectory(prefix="simulation-runtime-memory-")
        super().__init__(Path(self._tmp.name) / "runtime.db")

    def close(self) -> None:
        self._tmp.cleanup()
