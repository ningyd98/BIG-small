from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from cloud_edge_robot_arm.contracts import ControlMode, TaskState
from cloud_edge_robot_arm.contracts.models import (
    CheckpointExecutionState,
    ExecutionCheckpoint,
    RetryBudgetSnapshot,
    TaskContract,
)
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator
from cloud_edge_robot_arm.edge.runtime.errors import TASK_TIMEOUT, runtime_error
from cloud_edge_robot_arm.edge.runtime.retry_policy import (
    SAFETY_STOP_ERROR_CODES,
    RetryPolicy,
)
from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
from cloud_edge_robot_arm.edge.runtime.skill_registry import RuntimeSkillRobot, SkillRegistry
from cloud_edge_robot_arm.edge.runtime.state_machine import TaskStateMachine
from cloud_edge_robot_arm.edge.runtime.task_context import TaskRuntimeContext
from cloud_edge_robot_arm.edge.safety.providers import (
    MockSceneStateProvider,
    MockTelemetryProvider,
    SceneStateProvider,
    TelemetryProvider,
)
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.errors import StructuredError
from cloud_edge_robot_arm.repositories.base import TaskRepository
from cloud_edge_robot_arm.repositories.event_autonomy.hashing import stable_payload_hash
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.repositories.models import ActionExecutionRecord, StepExecutionRecord

if TYPE_CHECKING:
    from cloud_edge_robot_arm.edge.event_mode.controller import EventTriggeredModeController
    from cloud_edge_robot_arm.edge.safety.safety_skill_executor import SafetySkillExecutor

SAFETY_DECISION_ERROR_CODES: dict[str, str] = {
    "PAUSE": "SAFETY_PAUSE_REQUESTED",
    "REJECT": "SAFETY_ACTION_REJECTED",
    "REQUEST_CORRECTION": "SAFETY_REQUEST_CORRECTION",
    "EMERGENCY_STOP": "SAFETY_EMERGENCY_STOP",
}


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
        shield: SafetyShield,
        repository: TaskRepository | None = None,
        registry: SkillRegistry | None = None,
        min_plan_version: int = 1,
        scene_version: int = 1,
        telemetry_provider: TelemetryProvider | None = None,
        scene_provider: SceneStateProvider | None = None,
        runtime_profile: str = "test",
        event_controller: EventTriggeredModeController | None = None,
    ) -> None:
        if not isinstance(shield, SafetyShield):
            raise TypeError(
                f"TaskExecutor requires a SafetyShield instance; got {type(shield).__name__!r}"
            )
        self._robot = robot
        self._shield = shield
        self._repository = repository or InMemoryRepository()
        self._registry = registry or SkillRegistry.default()
        self._min_plan_version = min_plan_version
        self._scene_version = scene_version
        self._runtime_profile = runtime_profile.strip().lower()

        if self._runtime_profile == "production":
            if telemetry_provider is None:
                raise ValueError(
                    "telemetry_provider is required in production mode; "
                    "MockTelemetryProvider is not allowed"
                )
            if scene_provider is None:
                raise ValueError(
                    "scene_provider is required in production mode; "
                    "MockSceneStateProvider is not allowed"
                )
            if isinstance(telemetry_provider, MockTelemetryProvider):
                raise ValueError("MockTelemetryProvider is not allowed in production mode")
            if isinstance(scene_provider, MockSceneStateProvider):
                raise ValueError("MockSceneStateProvider is not allowed in production mode")

        self._telemetry_provider = telemetry_provider or MockTelemetryProvider()
        self._scene_provider = scene_provider or MockSceneStateProvider(
            robot, initial_scene_version=self._scene_version
        )
        self._state_machine = TaskStateMachine()
        self._retry_policy = RetryPolicy()
        self._event_controller = event_controller

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
        connected_error = self._connected_error()
        if connected_error is not None:
            return TaskExecutionResult(
                success=False, repository=self._repository, error=connected_error
            )

        command_decision = self._repository.accept_command(
            contract,
            payload_hash=self._payload_hash(payload),
        )
        if not command_decision.accepted:
            error = runtime_error(command_decision.code, command_decision.message)
            self._repository.record_audit_event(
                task_id=contract.task_id,
                event_type="CONTRACT_REJECTED",
                details={"error_code": error.code},
            )
            return TaskExecutionResult(success=False, repository=self._repository, error=error)

        self._repository.create_task_from_contract(contract)
        context = TaskRuntimeContext.from_contract(contract)
        self._repository.record_audit_event(
            task_id=contract.task_id,
            event_type="CONTRACT_ACCEPTED",
            details={"plan_version": contract.plan_version, "command_seq": contract.command_seq},
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

        if self._is_event_contract(contract):
            assert self._event_controller is not None
            self._event_controller.initialize_task(contract)
            self._save_checkpoint(context, CheckpointExecutionState.STARTED.value)

        return self._execute_runtime(contract=contract, context=context, start_step_index=0)

    def resume_from_checkpoint(
        self,
        contract: TaskContract,
        checkpoint: ExecutionCheckpoint,
    ) -> TaskExecutionResult:
        """Resume an event-triggered task from a persisted checkpoint."""
        if self._event_controller is None:
            return TaskExecutionResult(
                success=False,
                repository=self._repository,
                error=runtime_error(
                    "EVENT_CONTROLLER_REQUIRED", "resume requires event controller"
                ),
            )
        validation_error = self._validate_resume_contract(contract, checkpoint)
        if validation_error is not None:
            return TaskExecutionResult(
                success=False, repository=self._repository, error=validation_error
            )
        connected_error = self._connected_error()
        if connected_error is not None:
            return TaskExecutionResult(
                success=False, repository=self._repository, error=connected_error
            )

        self._repository.create_task_from_contract(contract)
        context = TaskRuntimeContext.from_contract(contract, initial_state=TaskState.EXECUTING)
        context.completed_step_ids = list(checkpoint.completed_step_ids)
        context.step_attempts = dict(checkpoint.step_attempts)
        context.failed_step_id = checkpoint.failed_step_id or None
        start_index = self._first_pending_index(contract, checkpoint.completed_step_ids)
        context.current_step_index = start_index
        context.current_step_id = (
            contract.steps[start_index].step_id if start_index < len(contract.steps) else None
        )
        repo = self._event_controller.repository
        repo.save_state_transition(
            contract.task_id,
            "READY_TO_RESUME",
            "RESUMING",
            "resume from checkpoint",
            checkpoint.correlation_id,
        )
        self._save_checkpoint(context, CheckpointExecutionState.RESUMING.value)
        result = self._execute_runtime(
            contract=contract, context=context, start_step_index=start_index
        )
        if result.success:
            repo.save_state_transition(
                contract.task_id,
                "RESUMING",
                "COMPLETED",
                "resume completed task",
                checkpoint.correlation_id,
            )
        return result

    def _execute_runtime(
        self,
        *,
        contract: TaskContract,
        context: TaskRuntimeContext,
        start_step_index: int,
    ) -> TaskExecutionResult:
        safety_executor = self._build_safety_executor()
        safety_executor.start_task()

        current_step_index = start_step_index
        last_post_safety_decision = ""
        last_post_safety_details: dict[str, object] = {}
        while current_step_index < len(contract.steps):
            step = contract.steps[current_step_index]
            context.current_step_index = current_step_index
            context.current_step_id = step.step_id
            safety_executor.start_step()
            self._repository.record_audit_event(
                task_id=contract.task_id,
                event_type="STEP_STARTED",
                details={"step_id": step.step_id, "skill": step.skill.value},
            )
            if self._is_event_contract(contract):
                self._save_checkpoint(context, CheckpointExecutionState.STEP_STARTED.value)

            step_result = self._execute_step_with_retries(
                safety_executor=safety_executor,
                context=context,
                step_index=current_step_index,
            )
            if step_result.post_safety_decision:
                last_post_safety_decision = step_result.post_safety_decision
                last_post_safety_details = dict(step_result.post_safety_details or {})
            if step_result.success:
                if step.step_id not in context.completed_step_ids:
                    context.completed_step_ids.append(step.step_id)
                self._repository.record_audit_event(
                    task_id=contract.task_id,
                    event_type="STEP_COMPLETED",
                    details={"step_id": step.step_id, "attempt": step_result.attempt},
                )
                if self._is_event_contract(contract):
                    self._save_checkpoint(
                        context,
                        CheckpointExecutionState.STEP_SUCCEEDED.value,
                        safety_state=last_post_safety_details,
                    )
                current_step_index += 1
                timeout_error = self._task_timeout_error(
                    context, next_step_index=current_step_index
                )
                if timeout_error is not None:
                    context.failed_step_id = step.step_id
                    return self._fail_task(
                        context=context, error=timeout_error, state=TaskState.FAILED
                    )
                continue

            error_code = step_result.error_code or "STEP_FAILED"
            if self._is_event_contract(contract):
                self._save_checkpoint(
                    context,
                    CheckpointExecutionState.STEP_FAILED.value,
                    safety_state=dict(step_result.post_safety_details or {}),
                )
                from cloud_edge_robot_arm.edge.events.models import DetectionContext

                robot_state = self._robot.get_state()
                det_ctx = DetectionContext(
                    task_id=contract.task_id,
                    plan_version=contract.plan_version,
                    command_seq=contract.command_seq,
                    robot_id=self._robot_id(),
                    step=step,
                    step_result=step_result,
                    robot_state=robot_state,
                    contract=contract,
                    elapsed_action_ms=context.elapsed_action_ms,
                    step_attempts=dict(context.step_attempts),
                    scene_version=contract.scene_version,
                    completed_step_ids=list(context.completed_step_ids),
                    completion_criteria=list(contract.completion_criteria),
                )

                assert self._event_controller is not None
                ctrl_result = self._event_controller.on_step_result(
                    result=step_result,
                    context=det_ctx,
                    contract=contract,
                )
                if ctrl_result.action.value == "RETRY_STEP":
                    self._repository.record_audit_event(
                        task_id=contract.task_id,
                        event_type="LOCAL_RECOVERY_APPLIED",
                        details={
                            "action": ctrl_result.action.value,
                            "event_id": ctrl_result.event.event_id if ctrl_result.event else "",
                        },
                    )
                    self._save_checkpoint(
                        context, CheckpointExecutionState.LOCAL_RETRY_STARTED.value
                    )
                    safety_executor.start_step()
                    continue
                if ctrl_result.action.value == "CONTINUE":
                    return self._fail_task(
                        context=context,
                        error=runtime_error(
                            "UNHANDLED_FAILED_STEP",
                            "failed step cannot be skipped by CONTINUE",
                            details={"step_id": step.step_id, "error_code": error_code},
                        ),
                        state=TaskState.FAILED,
                    )
                if ctrl_result.action.value == "REPLAN_AND_CONTINUE":
                    self._repository.record_audit_event(
                        task_id=contract.task_id,
                        event_type="CLOUD_REPLAN_REQUESTED",
                        details={"failed_step_id": step.step_id},
                    )
                    self._save_checkpoint(
                        context, CheckpointExecutionState.WAITING_CLOUD_REPLAN.value
                    )
                    return self._fail_task(
                        context=context,
                        error=runtime_error(
                            "CLOUD_REPLAN_REQUIRED",
                            f"Local recovery failed for step {step.step_id}, cloud replan needed",
                            details={
                                "event_id": ctrl_result.event.event_id if ctrl_result.event else "",
                                "summary_id": ctrl_result.summary.summary_id
                                if ctrl_result.summary
                                else "",
                            },
                        ),
                        state=TaskState.WAITING_CLOUD_UPDATE,
                    )
                if ctrl_result.action.value == "PAUSE":
                    self._transition(context, TaskState.PAUSED, reason="Paused by event controller")
                    return TaskExecutionResult(
                        success=False,
                        repository=self._repository,
                        context=context,
                        error=runtime_error(
                            "TASK_PAUSED_EVENT_CONTROLLER", "Task paused by event controller"
                        ),
                    )
                if ctrl_result.action.value == "SAFETY_STOP":
                    stop_ok = self._execute_safety_stop(context)
                    if not stop_ok:
                        return self._fail_task(
                            context=context,
                            error=runtime_error(
                                "SAFETY_STOP_FAILED", "both stop and emergency_stop failed"
                            ),
                            state=TaskState.FAILED,
                        )
                    self._save_checkpoint(context, CheckpointExecutionState.SAFETY_STOPPED.value)
                    return self._fail_task(
                        context=context,
                        error=step_result.error
                        or runtime_error(
                            "SAFETY_STOP_EVENT", "Critical event triggered safety stop"
                        ),
                        state=TaskState.SAFETY_STOPPED,
                    )

            final_state = self._determine_failure_state(error_code, step_result)
            if final_state == TaskState.SAFETY_STOPPED:
                stop_ok = self._execute_safety_stop(context)
                if not stop_ok:
                    return self._fail_task(
                        context=context,
                        error=runtime_error(
                            "SAFETY_STOP_FAILED", "both stop and emergency_stop failed"
                        ),
                        state=TaskState.FAILED,
                    )
            return self._fail_task(
                context=context,
                error=step_result.error
                or runtime_error("STEP_FAILED", "step failed without structured error"),
                state=final_state,
            )

        return self._complete_task(
            contract=contract,
            context=context,
            final_safety_decision=last_post_safety_decision,
            final_safety_details=last_post_safety_details,
        )

    def _complete_task(
        self,
        *,
        contract: TaskContract,
        context: TaskRuntimeContext,
        final_safety_decision: str,
        final_safety_details: dict[str, object],
    ) -> TaskExecutionResult:
        from cloud_edge_robot_arm.edge.completion_evaluator import CompletionEvaluator

        if not final_safety_decision:
            return self._fail_task(
                context=context,
                error=runtime_error(
                    "FINAL_SAFETY_UNVERIFIED",
                    "cannot complete without a real SafetyShield post-check result",
                ),
                state=TaskState.FAILED,
            )
        robot_state = self._robot.get_state()
        robot_state_dict = robot_state.model_dump() if hasattr(robot_state, "model_dump") else {}
        final_target_state: dict[str, object] = {
            "object_at_target": self._robot.object_region(contract.task_target.object_id)
            == contract.task_target.target_region_id
        }
        criteria_results = self._completion_criteria_results(
            contract=contract,
            completed_step_ids=list(context.completed_step_ids),
            target_state=final_target_state,
        )
        completion_repository = getattr(self._event_controller, "repository", None)
        scene = self._scene_provider.snapshot()
        scene_version = scene.scene_version if scene is not None else contract.scene_version
        scene_updated_at = scene.updated_at if scene is not None else None
        evaluation = CompletionEvaluator(repository=completion_repository).evaluate(
            contract=contract,
            completed_step_ids=list(context.completed_step_ids),
            completion_criteria_results=criteria_results,
            final_safety_decision=final_safety_decision,
            final_robot_state=robot_state_dict,
            final_target_state=final_target_state,
            scene_version=scene_version,
            last_scene_update_at=scene_updated_at,
        )
        if not evaluation.completed:
            self._repository.record_audit_event(
                task_id=contract.task_id,
                event_type="TASK_COMPLETION_EVALUATION_FAILED",
                details={
                    "failed_checks": evaluation.failed_checks,
                    "reason_codes": evaluation.reason_codes,
                },
            )
            failure_detail = "; ".join(evaluation.failed_checks)
            return self._fail_task(
                context=context,
                error=runtime_error(
                    "COMPLETION_EVALUATION_FAILED",
                    f"Task did not pass completion evaluation: {failure_detail}",
                    details={"failed_checks": evaluation.failed_checks},
                ),
                state=TaskState.FAILED,
            )

        if self._is_event_contract(contract):
            assert self._event_controller is not None
            budget = self._event_controller.retry_budget(contract.task_id)
            self._event_controller.on_task_completed(
                contract=contract,
                completed_step_ids=list(context.completed_step_ids),
                completion_criteria_results=criteria_results,
                final_robot_state=robot_state_dict,
                final_target_state=final_target_state,
                final_safety_decision=final_safety_decision,
                local_retry_count=budget.retry_count_used if budget is not None else 0,
            )
            self._save_checkpoint(
                context,
                CheckpointExecutionState.COMPLETED.value,
                safety_state=final_safety_details,
            )

        self._transition(context, TaskState.COMPLETED, reason="all steps completed and evaluated")
        self._repository.record_audit_event(
            task_id=contract.task_id,
            event_type="TASK_COMPLETED",
            details={
                "completed_step_ids": list(context.completed_step_ids),
                "evaluation_passed": True,
            },
        )
        return TaskExecutionResult(
            success=True, repository=self._repository, context=context, error=None
        )

    def _completion_criteria_results(
        self,
        *,
        contract: Any,
        completed_step_ids: list[str],
        target_state: dict[str, object],
    ) -> dict[str, bool]:
        all_steps = {step.step_id for step in contract.steps}
        completed = set(completed_step_ids)
        results: dict[str, bool] = {}
        for criterion in contract.completion_criteria:
            normalized = criterion.strip().lower()
            if normalized in {"all_steps_completed", "done", "ok"}:
                results[criterion] = all_steps.issubset(completed)
            elif normalized in {
                "object_placed",
                "object_in_bin",
                "object_in_bin_a",
                "object_inside_target_region",
            }:
                results[criterion] = bool(target_state.get("object_at_target", False))
            elif normalized in {"robot_in_safe_pose", "robot_safe"}:
                state = self._robot.get_state()
                results[criterion] = not state.estop_engaged and not state.collision_detected
            else:
                results[criterion] = False
        return results

    def _determine_failure_state(self, error_code: str, result: StepExecutionResult) -> TaskState:
        if error_code in SAFETY_STOP_ERROR_CODES:
            return TaskState.SAFETY_STOPPED
        if error_code == "SAFETY_EMERGENCY_STOP":
            return TaskState.SAFETY_STOPPED
        if result.error is not None and result.error.category == "SAFETY_SHIELD":
            decision_code = result.error.details.get("safety_decision", "")
            if decision_code == "EMERGENCY_STOP":
                return TaskState.SAFETY_STOPPED
            if decision_code == "PAUSE":
                return TaskState.PAUSED
            if decision_code in ("REJECT", "REQUEST_CORRECTION"):
                return TaskState.FAILED
        return TaskState.FAILED

    def _execute_safety_stop(self, context: TaskRuntimeContext) -> bool:
        from cloud_edge_robot_arm.edge.safety.stop_controller import StopController

        controller = StopController(self._robot)
        self._repository.record_audit_event(
            task_id=context.task_id,
            event_type="STOP_REQUESTED",
            details={"method": "stop"},
        )
        result = controller.execute_stop()

        if result.verified_stopped:
            self._repository.record_audit_event(
                task_id=context.task_id,
                event_type="STOP_CONFIRMED",
                details={"method": result.method_used},
            )
            self._record_stop_actions(context, result)
            return True

        if result.verified_estop:
            self._repository.record_audit_event(
                task_id=context.task_id,
                event_type="EMERGENCY_STOP_CONFIRMED",
                details={"method": result.method_used},
            )
            self._record_stop_actions(context, result)
            return True

        self._repository.record_audit_event(
            task_id=context.task_id,
            event_type="SAFETY_STOP_FAILED",
            details={
                "error": result.error.message if result.error else "unknown",
                "critical": True,
            },
        )
        self._record_stop_actions(context, result)
        return False

    def _record_stop_actions(self, context: TaskRuntimeContext, result: object) -> None:
        stop_result = getattr(result, "stop_action_result", None)
        estop_result = getattr(result, "estop_action_result", None)
        if stop_result is not None:
            self._repository.record_action_execution(
                ActionExecutionRecord(
                    task_id=context.task_id,
                    step_id=context.current_step_id or "",
                    action_id=stop_result.action_id,
                    action_type="STOP",
                    success=stop_result.success,
                    error_code=stop_result.error_code,
                    duration_ms=stop_result.duration_ms,
                    timestamp=stop_result.finished_at,
                )
            )
        if estop_result is not None:
            self._repository.record_action_execution(
                ActionExecutionRecord(
                    task_id=context.task_id,
                    step_id=context.current_step_id or "",
                    action_id=estop_result.action_id,
                    action_type="EMERGENCY_STOP",
                    success=estop_result.success,
                    error_code=estop_result.error_code,
                    duration_ms=estop_result.duration_ms,
                    timestamp=estop_result.finished_at,
                )
            )

    def _execute_step_with_retries(
        self,
        *,
        safety_executor: SafetySkillExecutor,
        context: TaskRuntimeContext,
        step_index: int,
    ) -> StepExecutionResult:
        step = context.contract.steps[step_index]
        if self._is_event_contract(context.contract):
            attempt = context.step_attempts.get(step.step_id, 0) + 1
            context.step_attempts[step.step_id] = attempt
            result = safety_executor.execute_attempt(
                contract=context.contract, step=step, attempt=attempt
            )
            self._persist_step_attempt(context, result)
            context.elapsed_action_ms += result.duration_ms
            if not result.success:
                context.failed_step_id = step.step_id
                if result.error is not None:
                    context.set_error(result.error)
                self._repository.record_audit_event(
                    task_id=context.task_id,
                    event_type="STEP_FAILED",
                    details={
                        "step_id": step.step_id,
                        "attempt": attempt,
                        "error_code": result.error_code,
                    },
                )
            return result

        max_attempts = self._retry_policy.max_attempts(step, context.contract.failure_policy)
        latest_result: StepExecutionResult | None = None
        for attempt in range(1, max_attempts + 1):
            context.step_attempts[step.step_id] = attempt
            latest_result = safety_executor.execute_attempt(
                contract=context.contract, step=step, attempt=attempt
            )
            self._persist_step_attempt(context, latest_result)
            context.elapsed_action_ms += latest_result.duration_ms
            if latest_result.success:
                return latest_result

            context.failed_step_id = step.step_id
            if latest_result.error is not None:
                context.set_error(latest_result.error)

            if latest_result.error_code in SAFETY_STOP_ERROR_CODES:
                return latest_result
            if latest_result.error and latest_result.error.category == "SAFETY_SHIELD":
                decision = latest_result.error.details.get("safety_decision", "")
                if decision in ("EMERGENCY_STOP", "PAUSE", "REJECT", "REQUEST_CORRECTION"):
                    return latest_result

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
                safety_executor.start_step()
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

        return latest_result or safety_executor.execute_attempt(
            contract=context.contract, step=step, attempt=1
        )

    def _persist_step_attempt(
        self, context: TaskRuntimeContext, result: StepExecutionResult
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
        self, context: TaskRuntimeContext, target_state: TaskState, *, reason: str
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
            success=False, repository=self._repository, context=context, error=error
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

    def _build_safety_executor(self) -> SafetySkillExecutor:
        from cloud_edge_robot_arm.edge.safety.safety_skill_executor import SafetySkillExecutor

        return SafetySkillExecutor(
            robot=self._robot,
            registry=self._registry,
            shield=self._shield,
            context_builder=self._shield.context_builder,
            telemetry_provider=self._telemetry_provider,
            scene_provider=self._scene_provider,
            repository=self._repository,
        )

    def _save_checkpoint(
        self,
        context: TaskRuntimeContext,
        execution_state: str,
        *,
        safety_state: dict[str, object] | None = None,
    ) -> ExecutionCheckpoint | None:
        if self._event_controller is None:
            return None
        repo = self._event_controller.repository
        robot_state = self._robot.get_state()
        scene = self._scene_provider.snapshot()
        budget = self._event_controller.retry_budget(context.task_id)
        pending = [
            step.step_id
            for step in context.contract.steps
            if step.step_id not in set(context.completed_step_ids)
        ]
        target_state = {
            "object_at_target": self._robot.object_region(context.contract.task_target.object_id)
            == context.contract.task_target.target_region_id
        }
        now = datetime.now(UTC)
        checkpoint = ExecutionCheckpoint(
            checkpoint_id=(
                f"ckpt-{context.task_id}-{context.plan_version}-{context.command_seq}-"
                f"{len(context.completed_step_ids)}-{execution_state}-{now.strftime('%Y%m%d%H%M%S%f')}"
            ),
            task_id=context.task_id,
            plan_id=self._plan_id(context.contract),
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            robot_id=self._robot_id(),
            current_step_id=context.current_step_id or "",
            current_step_index=context.current_step_index,
            failed_step_id=context.failed_step_id or "",
            last_successful_step_id=context.completed_step_ids[-1]
            if context.completed_step_ids
            else "",
            completed_step_ids=list(context.completed_step_ids),
            pending_step_ids=pending,
            step_attempts=dict(context.step_attempts),
            retry_budget_snapshot=RetryBudgetSnapshot(
                task_retry_count=budget.task_retry_count if budget else 0,
                step_retry_counts=dict(budget.step_retry_counts) if budget else {},
                skill_retry_counts=dict(budget.skill_retry_counts) if budget else {},
                event_retry_counts=dict(budget.event_retry_counts) if budget else {},
                remaining_retries=budget.remaining_retries if budget else 0,
            ),
            robot_state=robot_state.model_dump(mode="json")
            if hasattr(robot_state, "model_dump")
            else {},
            target_state=target_state,
            scene_version=scene.scene_version
            if scene is not None
            else context.contract.scene_version,
            scene_timestamp=scene.updated_at if scene is not None else None,
            safety_state=dict(safety_state or {}),
            execution_state=execution_state,
            created_at=now,
            updated_at=now,
            correlation_id=self._checkpoint_correlation(context, execution_state),
        )
        checkpoint = checkpoint.model_copy(
            update={
                "checkpoint_hash": stable_payload_hash(
                    checkpoint, ignore_fields={"checkpoint_hash"}
                )
            },
            deep=True,
        )
        return repo.save_execution_checkpoint(checkpoint)

    def _validate_resume_contract(
        self, contract: TaskContract, checkpoint: ExecutionCheckpoint
    ) -> StructuredError | None:
        if not self._is_event_contract(contract):
            return runtime_error(
                "RESUME_REQUIRES_EVENT_MODE", "only event-triggered contracts can resume"
            )
        if checkpoint.execution_state in {
            CheckpointExecutionState.COMPLETED.value,
            CheckpointExecutionState.SAFETY_STOPPED.value,
        }:
            return runtime_error("CHECKPOINT_TERMINAL", "cannot resume a terminal checkpoint")
        if contract.task_id != checkpoint.task_id:
            return runtime_error(
                "CHECKPOINT_TASK_MISMATCH", "contract task_id does not match checkpoint"
            )
        if self._plan_id(contract) != checkpoint.plan_id:
            return runtime_error(
                "CHECKPOINT_PLAN_MISMATCH", "contract plan_id does not match checkpoint"
            )
        if self._robot_id() != checkpoint.robot_id:
            return runtime_error("CHECKPOINT_ROBOT_MISMATCH", "robot_id does not match checkpoint")
        if contract.plan_version <= checkpoint.plan_version:
            return runtime_error(
                "STALE_PLAN_VERSION", "resume contract must be newer than checkpoint plan"
            )
        if contract.command_seq <= checkpoint.command_seq:
            return runtime_error("STALE_COMMAND_SEQ", "resume command_seq must increase")
        if contract.scene_version < checkpoint.scene_version:
            return runtime_error(
                "SCENE_VERSION_REGRESSED", "resume scene_version is older than checkpoint"
            )
        validation = EdgeContractValidator(
            supported_skills=self._registry.skills(),
            min_plan_version=self._min_plan_version,
        ).accept_payload(contract.model_dump(mode="json"), now=datetime.now(UTC))
        if not validation.accepted:
            return validation.error or runtime_error(
                "CONTRACT_SCHEMA_INVALID", "resume contract invalid"
            )
        if self._event_controller is not None:
            active_versions = self._event_controller.repository.list_contract_versions(
                contract.task_id
            )
            base = next(
                (
                    record.contract
                    for record in active_versions
                    if record.plan_version == checkpoint.plan_version
                ),
                None,
            )
            if base is not None:
                base_steps = {step.step_id: step for step in base.steps}
                new_steps = {step.step_id: step for step in contract.steps}
                for step_id in checkpoint.completed_step_ids:
                    if step_id not in new_steps:
                        return runtime_error(
                            "COMPLETED_STEP_REMOVED", "resume contract removed completed step"
                        )
                    if step_id in base_steps and new_steps[step_id] != base_steps[step_id]:
                        return runtime_error(
                            "COMPLETED_STEP_MODIFIED", "resume contract modified completed step"
                        )
        return None

    def _connected_error(self) -> StructuredError | None:
        from cloud_edge_robot_arm.contracts import RobotState

        robot_state = self._robot.get_state()
        if not isinstance(robot_state, RobotState):
            return runtime_error("ROBOT_STATE_INVALID", "robot adapter did not return a RobotState")
        if not robot_state.connected:
            return runtime_error(
                "ROBOT_DISCONNECTED", "robot is not connected; call connect() first"
            )
        return None

    def _is_event_contract(self, contract: TaskContract) -> bool:
        return (
            self._event_controller is not None
            and contract.control_mode == ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
        )

    def _first_pending_index(self, contract: TaskContract, completed_step_ids: list[str]) -> int:
        completed = set(completed_step_ids)
        for index, step in enumerate(contract.steps):
            if step.step_id not in completed:
                return index
        return len(contract.steps)

    def _plan_id(self, contract: TaskContract) -> str:
        return f"plan-{contract.task_id}"

    def _robot_id(self) -> str:
        return "robot-unknown"

    def _checkpoint_correlation(self, context: TaskRuntimeContext, execution_state: str) -> str:
        return f"{context.task_id}:{context.plan_version}:{context.command_seq}:{execution_state}"

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
