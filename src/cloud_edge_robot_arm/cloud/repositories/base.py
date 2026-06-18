"""基础仓储协议，定义持久化层必须满足的最小方法。

Abstract base for cloud planning repositories.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts import TaskContract


@runtime_checkable
class CloudPlanningRepository(Protocol):
    """Persistence contract for cloud planning artifacts.

    Implementations: InMemory, SQLite, PostgreSQL.
    """

    @abstractmethod
    def save_planning_request(self, request_id: str, payload: dict[str, Any]) -> None: ...

    @abstractmethod
    def save_planning_attempt(
        self, request_id: str, attempt: int, payload: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    def save_planner_output(
        self, request_id: str, attempt: int, payload: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    def save_validation_result(
        self, request_id: str, attempt: int, payload: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    def save_generated_contract(self, request_id: str, contract: TaskContract) -> None: ...

    @abstractmethod
    def save_dispatch_record(self, task_id: str, accepted: bool, reason: str | None) -> None: ...

    @abstractmethod
    def save_prompt_version(
        self, prompt_name: str, prompt_version: str, prompt_hash: str
    ) -> None: ...

    @abstractmethod
    def get_request(self, request_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def get_contract(self, task_id: str) -> TaskContract | None: ...
