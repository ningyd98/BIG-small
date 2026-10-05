"""内存仓储实现，主要用于测试和本地开发，不作为持久真源。

In-memory cloud planning repository (default for tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cloud_edge_robot_arm.contracts import TaskContract


@dataclass
class InMemoryCloudPlanningRepository:
    planning_requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    planning_attempts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    planner_outputs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    validation_results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    generated_contracts: dict[str, TaskContract] = field(default_factory=dict)
    dispatch_records: list[dict[str, Any]] = field(default_factory=list)
    prompt_versions: dict[str, dict[str, str]] = field(default_factory=dict)
    _contracts_by_task_id: dict[str, TaskContract] = field(default_factory=dict)

    def save_planning_request(self, request_id: str, payload: dict[str, Any]) -> None:
        self.planning_requests[request_id] = payload

    def save_planning_attempt(self, request_id: str, attempt: int, payload: dict[str, Any]) -> None:
        self.planning_attempts.setdefault(request_id, []).append({"attempt": attempt, **payload})

    def save_planner_output(self, request_id: str, attempt: int, payload: dict[str, Any]) -> None:
        self.planner_outputs.setdefault(request_id, []).append({"attempt": attempt, **payload})

    def save_validation_result(
        self, request_id: str, attempt: int, payload: dict[str, Any]
    ) -> None:
        self.validation_results.setdefault(request_id, []).append({"attempt": attempt, **payload})

    def save_generated_contract(self, request_id: str, contract: TaskContract) -> None:
        self.generated_contracts[request_id] = contract
        self._contracts_by_task_id[contract.task_id] = contract

    def save_dispatch_record(self, task_id: str, accepted: bool, reason: str | None) -> None:
        self.dispatch_records.append({"task_id": task_id, "accepted": accepted, "reason": reason})

    def save_prompt_version(self, prompt_name: str, prompt_version: str, prompt_hash: str) -> None:
        self.prompt_versions[prompt_name] = {
            "version": prompt_version,
            "hash": prompt_hash,
        }

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        return self.planning_requests.get(request_id)

    def get_contract(self, task_id: str) -> TaskContract | None:
        return self._contracts_by_task_id.get(task_id)
