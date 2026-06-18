"""云边网关服务，统一处理边缘侧事件、确认和待发送消息。

EdgeGateway Protocol and InProcessEdgeGateway.

The EdgeGateway is the cloud-side dispatch channel.  The cloud must NEVER
assume that "generated successfully" == "executed successfully" — the edge
has the final safety and execution authority.

Phase 4 implements InProcessEdgeGateway only (no MQTT).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts import TaskContract
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutionResult, TaskExecutor
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield


@dataclass(frozen=True)
class EdgeDispatchResult:
    """Result of dispatching a contract to the edge."""

    dispatched: bool
    edge_accepted: bool
    edge_reason: str | None = None
    task_result: TaskExecutionResult | None = None


@runtime_checkable
class EdgeGateway(Protocol):
    """Protocol for dispatching validated contracts to the edge runtime."""

    def dispatch(self, contract: TaskContract) -> EdgeDispatchResult: ...


class InProcessEdgeGateway:
    """Dispatches to a local TaskExecutor within the same process.

    Must pass through SafetyShield — the cloud cannot bypass it.
    """

    def __init__(
        self,
        *,
        executor: TaskExecutor,
        shield: SafetyShield,
    ) -> None:
        self._executor = executor
        self._shield = shield

    def dispatch(self, contract: TaskContract) -> EdgeDispatchResult:
        # The TaskExecutor ALREADY integrates SafetyShield via
        # SafetySkillExecutor — nothing can bypass the shield.
        payload: dict[str, Any] = contract.model_dump(mode="json")
        result = self._executor.submit_contract(payload)
        return EdgeDispatchResult(
            dispatched=True,
            edge_accepted=result.success,
            edge_reason=result.error.message if result.error else None,
            task_result=result,
        )
