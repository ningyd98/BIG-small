"""测试用内存仓库。

底层仍使用临时 SQLite，目的是在单元测试中保留事务、CAS 和 schema 行为，
同时不把运行数据库写入仓库。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository


class InMemorySimulationJobRepository(SQLiteSimulationJobRepository):
    """具备 SQLite 语义的进程本地测试仓库。"""

    def __init__(self) -> None:
        self._tmp = TemporaryDirectory(prefix="simulation-runtime-memory-")
        super().__init__(Path(self._tmp.name) / "runtime.db")

    def close(self) -> None:
        self._tmp.cleanup()
