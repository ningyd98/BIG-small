from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cloud_edge_robot_arm.contracts import TaskState
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator
from cloud_edge_robot_arm.edge.runtime.errors import TASK_TIMEOUT, runtime_error
from cloud_edge_robot_arm.edge.runtime.retry_policy import (
    SAFETY_STOP_ERROR_CODES,
    RetryPolicy,
)
from cloud_edge_robot_arm.edge.runtime.skill_executor import (
    SkillExecutor,
    StepExecutionResult,
)
from cloud_edge_robot_arm.edge.runtime.skill_registry import RuntimeSkillRobot, SkillRegistry
from cloud_edge_robot_arm.edge.runtime.state_machine import TaskStateMachine
from cloud_edge_robot_arm.edge.runtime.task_context import TaskRuntimeContext
from cloud_edge_robot_arm.errors import StructuredError
from cloud_edge_robot_arm.repositories.base import TaskRepository
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.repositories.models import ActionExecutionRecord, StepExecutionRecord


@dataclass(frozen=True)
class TaskExecutionResult:
    success: bool
    repository: TaskRepository
    context: TaskRuntimeContext | None = None
    error: StructuredError | None = None


class TaskExecutor:
    def __init__(
        self,
        *,
        robot: RuntimeSkillRobot,
        repository: TaskRepository | None = None,
        registry: SkillRegistry | None = None,
        min_plan_version: int = 1,
    ) -> None:
        self._robot = robot
        self._repository = repository or InMemoryRepository()
        self._registry = registry or SkillRegistry.default()
        self._min_plan_version = min_plan_version
        self._state_machine = TaskStateMachine()
        self._retry_policy = RetryPolicy()

    def submit_contract(self, payload: dict[str, Any]) -> TaskExecutionResult:
        task_id = self._extract_task_id(payload)
        self._repository.record_audit_event(
            task_id=task_id,
            event_type="CONTRACT_RECEIVED",
            details={"command_seq": payload.get("command_seq")},
        )

        validation = EdgeContractValidator(
            supported_skills=self._registry.skills(),
            min_plan_version=self._min_plan_version,
        ).accept_payload(payload, now=self._validation_now(payload))
        if not validation.accepted or validation.contract is None:
            error = validation.error or runtime_error(
                "CONTRACT_SCHEMA_INVALID",
                "contract validation failed without structured details",
            )
            self._repository.record_audit_event(
                task_id=task_id,
                event_type="CONTRACT_REJECTED",
                details={"error_code": error.code},
            )
            return TaskExecutionResult(success=False, repository=self._repository, error=error)

        contract = validation.contract
        task_id = contract.task_id

        robot_state = self._robot.get_state()
        from cloud_edge_robot_arm.contracts import RobotState

        if not isinstance(robot_state, RobotState):
            return TaskExecutionResult(
                success=False,
                repository=self._repository,
                error=runtime_error(
                    "ROBOT_STATE_INVALID",
                    "robot adapter did not return a RobotState",
                ),
            )
        if not robot_state.connected:
            return TaskExecutionResult(
                success=False,
                repository=self._repository,
                error=runtime_error(
                    "ROBOT_DISCONNECTED",
                    "robot is not connected; call connect() before submitting contracts",
                ),
            )

        command_decision = self._repository.accept_command(
            contract,
            payload_hash=self._payload_hash(payload),
        )
        if not command_decision.accepted:
            error = runtime_error(command_decision.code, command_decision.message)
            self._repository.record_audit_event(
                task_id=task_id,
                event_type="CONTRACT_REJECTED",
                details={"error_code": error.code},
            )
            return TaskExecutionResult(success=False, repository=self._repository, error=error)

        self._repository.create_task_from_contract(contract)
        context = TaskRuntimeContext.from_contract(contract)
        self._repository.record_audit_event(
            task_id=task_id,
            event_type="CONTRACT_ACCEPTED",
            details={
                "plan_version": contract.plan_version,
                "command_seq": contract.command_seq,
            },
        )

        for target_state in (TaskState.VALIDATING, TaskState.READY, TaskState.EXECUTING):
            transition = self._transition(context, target_state, reason="task accepted")
            if not transition:
                return TaskExecutionResult(
                    success=False,
                    repository=self._repository,
                    context=context,
                    error=context.last_error,
                )

        skill_executor = SkillExecutor(robot=self._robot, registry=self._registry)
        for index, step in enumerate(contract.steps):
            context.current_step_index = index
            context.current_step_id = step.step_id
            self._repository.record_audit_event(
                task_id=task_id,
                event_type="STEP_STARTED",
                details={"step_id": step.step_id, "skill": step.skill.value},
            )

            step_result = self._execute_step_with_retries(
                skill_executor=skill_executor,
                context=context,
                step_index=index,
            )
            if not step_result.success:
                final_state = (
                    TaskState.SAFETY_STOPPED
                    if step_result.error_code in SAFETY_STOP_ERROR_CODES
                    else TaskState.FAILED
                )
                if final_state == TaskState.SAFETY_STOPPED:
                    self._execute_safety_stop(context)
                return self._fail_task(
                    context=context,
                    error=step_result.error
                    or runtime_error("STEP_FAILED", "step failed without structured error"),
                    state=final_state,
                )

            context.completed_step_ids.append(step.step_id)
            self._repository.record_audit_event(
                task_id=task_id,
                event_type="STEP_COMPLETED",
                details={"step_id": step.step_id, "attempt": step_result.attempt},
            )

            timeout_error = self._task_timeout_error(context, next_step_index=index + 1)
            if timeout_error is not None:
                context.failed_step_id = step.step_id
                return self._fail_task(
                    context=context,
                    error=timeout_error,
                    state=TaskState.FAILED,
                )

        self._transition(context, TaskState.COMPLETED, reason="all steps completed")
        self._repository.record_audit_event(
            task_id=task_id,
            event_type="TASK_COMPLETED",
            details={"completed_step_ids": list(context.completed_step_ids)},
        )
        return TaskExecutionResult(
            success=True,
            repository=self._repository,
            context=context,
            error=None,
        )

    def _execute_safety_stop(self, context: TaskRuntimeContext) -> None:
        from cloud_edge_robot_arm.edge.safety.stop_controller import StopController

        controller = StopController(self._robot)
        result = controller.execute_stop()

        self._repository.record_audit_event(
            task_id=context.task_id,
            event_type="STOP_REQUESTED",
            details={"method": "stop"},
        )

        if result.verified_stopped:
            self._repository.record_audit_event(
                task_id=context.task_id,
                event_type="STOP_CONFIRMED",
                details={"method": result.method_used},
            )
        elif result.verified_estop:
            self._repository.record_audit_event(
                task_id=context.task_id,
                event_type="EMERGENCY_STOP_CONFIRMED",
                details={"method": result.method_used},
            )
        else:
            self._repository.record_audit_event(
                task_id=context.task_id,
                event_type="SAFETY_STOP_FAILED",
                details={"error": result.error.message if result.error else "unknown"},
            )

        if result.stop_action_result is not None:
            self._repository.record_action_execution(
                ActionExecutionRecord(
                    task_id=context.task_id,
                    step_id=context.current_step_id or "",
                    action_id=result.stop_action_result.action_id,
                    action_type="STOP",
                    success=result.stop_action_result.success,
                    error_code=result.stop_action_result.error_code,
                    duration_ms=result.stop_action_result.duration_ms,
                    timestamp=result.stop_action_result.finished_at,
                )
            )
        if result.estop_action_result is not None:
            self._repository.record_action_execution(
                ActionExecutionRecord(
                    task_id=context.task_id,
                    step_id=context.current_step_id or "",
                    action_id=result.estop_action_result.action_id,
                    action_type="EMERGENCY_STOP",
                    success=result.estop_action_result.success,
                    error_code=result.estop_action_result.error_code,
                    duration_ms=result.estop_action_result.duration_ms,
                    timestamp=result.estop_action_result.finished_at,
                )
            )

    def _execute_step_with_retries(
        self,
        *,
        skill_executor: SkillExecutor,
        context: TaskRuntimeContext,
        step_index: int,
    ) -> StepExecutionResult:
        step = context.contract.steps[step_index]
        max_attempts = self._retry_policy.max_attempts(step, context.contract.failure_policy)
        latest_result: StepExecutionResult | None = None
        for attempt in range(1, max_attempts + 1):
            context.step_attempts[step.step_id] = attempt
            latest_result = skill_executor.execute_attempt(
                contract=context.contract,
                step=step,
                attempt=attempt,
            )
            self._persist_step_attempt(context, latest_result)
            context.elapsed_action_ms += latest_result.duration_ms
            if latest_result.success:
                return latest_result

            context.failed_step_id = step.step_id
            if latest_result.error is not None:
                context.set_error(latest_result.error)
            retry = self._retry_policy.decide(
                step=step,
                failure_policy=context.contract.failure_policy,
                error_code=latest_result.error_code,
                attempt=attempt,
            )
            if retry.should_retry:
                self._repository.record_audit_event(
                    task_id=context.task_id,
                    event_type="STEP_RETRYING",
                    details={
                        "step_id": step.step_id,
                        "attempt": attempt,
                        "max_attempts": retry.max_attempts,
                        "error_code": latest_result.error_code,
                    },
                )
                continue
            self._repository.record_audit_event(
                task_id=context.task_id,
                event_type="STEP_FAILED",
                details={
                    "step_id": step.step_id,
                    "attempt": attempt,
                    "error_code": latest_result.error_code,
                },
            )
            return latest_result

        return latest_result or skill_executor.execute_attempt(
            contract=context.contract,
            step=step,
            attempt=1,
        )

    def _persist_step_attempt(
        self,
        context: TaskRuntimeContext,
        result: StepExecutionResult,
    ) -> None:
        self._repository.record_step_execution(
            StepExecutionRecord(
                task_id=context.task_id,
                step_id=result.step_id,
                skill=result.skill,
                attempt=result.attempt,
                success=result.success,
                error_code=result.error_code,
                duration_ms=result.duration_ms,
                timestamp=result.timestamp,
            )
        )
        if result.action_result is None:
            return
        self._repository.record_action_execution(
            ActionExecutionRecord(
                task_id=context.task_id,
                step_id=result.step_id,
                action_id=result.action_result.action_id,
                action_type=result.action_result.action_type,
                success=result.action_result.success,
                error_code=result.action_result.error_code,
                duration_ms=result.action_result.duration_ms,
                timestamp=result.action_result.finished_at,
            )
        )

    def _transition(
        self,
        context: TaskRuntimeContext,
        target_state: TaskState,
        *,
        reason: str,
    ) -> bool:
        from_state = context.state
        result = self._state_machine.transition(context, target_state, reason=reason)
        if not result.success:
            return False
        self._repository.record_state_transition(
            task_id=context.task_id,
            from_state=from_state.value,
            to_state=target_state.value,
            reason=reason,
        )
        self._repository.record_audit_event(
            task_id=context.task_id,
            event_type="TASK_STATE_CHANGED",
            details={
                "from_state": from_state.value,
                "to_state": target_state.value,
                "reason": reason,
            },
        )
        return True

    def _fail_task(
        self,
        *,
        context: TaskRuntimeContext,
        error: StructuredError,
        state: TaskState,
    ) -> TaskExecutionResult:
        context.set_error(error)
        self._transition(context, state, reason=error.code)
        if state == TaskState.SAFETY_STOPPED:
            self._repository.record_audit_event(
                task_id=context.task_id,
                event_type="SAFE_STOP_TRIGGERED",
                details={"error_code": error.code},
            )
        self._repository.record_audit_event(
            task_id=context.task_id,
            event_type="TASK_FAILED",
            details={"error_code": error.code, "failed_step_id": context.failed_step_id},
        )
        return TaskExecutionResult(
            success=False,
            repository=self._repository,
            context=context,
            error=error,
        )

    def _task_timeout_error(
        self,
        context: TaskRuntimeContext,
        *,
        next_step_index: int,
    ) -> StructuredError | None:
        if next_step_index >= len(context.contract.steps):
            return None
        budget_ms = int(
            (context.contract.valid_until - context.contract.issued_at).total_seconds() * 1_000
        )
        if context.elapsed_action_ms < budget_ms:
            return None
        return runtime_error(
            TASK_TIMEOUT,
            "task execution exceeded contract deadline before the next step",
            details={"elapsed_action_ms": context.elapsed_action_ms, "budget_ms": budget_ms},
        )

    def _payload_hash(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _extract_task_id(self, payload: dict[str, Any]) -> str:
        raw_task_id = payload.get("task_id")
        if isinstance(raw_task_id, str) and raw_task_id:
            return raw_task_id
        return "UNKNOWN_TASK"

    def _validation_now(self, payload: dict[str, Any]) -> datetime:
        raw_timestamp = payload.get("timestamp")
        if isinstance(raw_timestamp, datetime):
            return raw_timestamp
        if isinstance(raw_timestamp, str):
            try:
                parsed = datetime.fromisoformat(raw_timestamp)
            except ValueError:
                return datetime.now(UTC)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        return datetime.now(UTC)
