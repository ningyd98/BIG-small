from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from cloud_edge_robot_arm.contracts import RobotState, SafetyDecision, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.runtime.errors import runtime_error
from cloud_edge_robot_arm.edge.runtime.skill_executor import (
    SkillExecutor,
    StepExecutionResult,
)
from cloud_edge_robot_arm.edge.runtime.skill_registry import RuntimeSkillRobot, SkillRegistry
from cloud_edge_robot_arm.edge.safety.context_builder import SafetyContextBuilder
from cloud_edge_robot_arm.edge.safety.errors import safety_error
from cloud_edge_robot_arm.edge.safety.intent_resolver import SkillSafetyIntentResolver
from cloud_edge_robot_arm.edge.safety.models import SafetyEvaluationResult
from cloud_edge_robot_arm.edge.safety.providers import (
    SceneStateProvider,
    TelemetryProvider,
)
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.errors import StructuredError
from cloud_edge_robot_arm.repositories.base import TaskRepository

SAFETY_DECISION_ERROR_CODES: dict[str, str] = {
    "PAUSE": "SAFETY_PAUSE_REQUESTED",
    "REJECT": "SAFETY_ACTION_REJECTED",
    "REQUEST_CORRECTION": "SAFETY_REQUEST_CORRECTION",
    "EMERGENCY_STOP": "SAFETY_EMERGENCY_STOP",
}


class SafetySkillExecutor:
    def __init__(
        self,
        *,
        robot: RuntimeSkillRobot,
        registry: SkillRegistry,
        shield: SafetyShield,
        context_builder: SafetyContextBuilder,
        telemetry_provider: TelemetryProvider,
        scene_provider: SceneStateProvider,
        repository: TaskRepository | None = None,
    ) -> None:
        self._robot = robot
        self._registry = registry
        self._shield = shield
        self._context_builder = context_builder
        self._telemetry_provider = telemetry_provider
        self._scene_provider = scene_provider
        self._repository = repository
        self._resolver = SkillSafetyIntentResolver(robot)
        self._task_started_at_mono: float | None = None
        self._step_started_at_mono: float | None = None
        self._skill_executor = SkillExecutor(robot=robot, registry=registry)

    def start_task(self) -> None:
        self._task_started_at_mono = time.monotonic()

    def start_step(self) -> None:
        self._step_started_at_mono = time.monotonic()

    @property
    def _policy_version(self) -> str:
        return self._shield.config.policy_version

    @property
    def _policy_hash(self) -> str:
        return self._shield.config.policy_hash

    def execute_attempt(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
    ) -> StepExecutionResult:
        robot_state = self._robot.get_state()
        if not isinstance(robot_state, RobotState):
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=runtime_error(
                    "ROBOT_STATE_INVALID",
                    "robot adapter did not return a RobotState",
                ),
                action_result=None,
                duration_ms=0,
            )

        telemetry = self._telemetry_provider.latest()
        scene = self._scene_provider.snapshot()

        # Resolve the high-level skill into an explicit, checkable intent. The SAME
        # resolved intent (target pose + limited velocity) is used for the shield
        # check and for the robot motion below.
        intent = self._resolver.resolve(
            contract=contract,
            step=step,
            robot_state=robot_state,
            telemetry=telemetry,
        )

        self._record_audit(
            "SAFETY_EVALUATION_STARTED",
            contract=contract,
            step=step,
            rule_id="-",
            decision="-",
            reason_code="STARTED",
        )

        scene_version = scene.scene_version if scene is not None else contract.scene_version
        scene_updated_at = scene.updated_at if scene is not None else None
        telemetry_timestamp = telemetry.timestamp if telemetry is not None else None
        obstacles = scene.obstacles if scene is not None else []
        forbidden = scene.forbidden_zones if scene is not None else []

        ctx = self._context_builder.build(
            contract=contract,
            step=step,
            robot_state=robot_state,
            scene_version=scene_version,
            resolved_parameters=intent.resolved_parameters,
            scene_updated_at=scene_updated_at,
            telemetry_timestamp=telemetry_timestamp,
            step_started_at_mono=self._step_started_at_mono,
            task_started_at_mono=self._task_started_at_mono,
            requested_velocity=intent.requested_tcp_velocity,
            requested_joint_velocities=(
                list(telemetry.joint_velocities)
                if telemetry is not None and telemetry.joint_velocities
                else [intent.requested_joint_velocity]
                if intent.requested_joint_velocity > 0
                else []
            ),
            requested_acceleration=intent.requested_acceleration,
            obstacles=obstacles,
            forbidden_zones=forbidden,
        )

        try:
            pre_result = self._shield.pre_check(ctx)
        except ValueError as exc:
            self._record_audit(
                "SAFETY_ACTION_REJECTED",
                contract=contract,
                step=step,
                rule_id="BYPASS",
                decision="REJECT",
                reason_code="SAFETY_BYPASS_REJECTED",
            )
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=safety_error("SAFETY_BYPASS_REJECTED", str(exc)),
                action_result=None,
                duration_ms=0,
            )

        self._record_rule_results(contract, step, pre_result)

        if pre_result.decision in {SafetyDecision.ALLOW, SafetyDecision.ALLOW_WITH_LIMITS}:
            params = intent.resolved_parameters
            if pre_result.decision == SafetyDecision.ALLOW_WITH_LIMITS:
                params = pre_result.limited_parameters or intent.resolved_parameters
                self._record_audit(
                    "SAFETY_PARAMETERS_LIMITED",
                    contract=contract,
                    step=step,
                    rule_id=self._limiting_rule_id(pre_result),
                    decision="ALLOW_WITH_LIMITS",
                    reason_code="PARAMETERS_LIMITED",
                    original_parameters=pre_result.original_parameters,
                    limited_parameters=pre_result.limited_parameters,
                )
            return self._execute_with_robot(
                contract=contract,
                step=step,
                attempt=attempt,
                parameters=params,
            )

        return self._rejected_result(
            contract=contract,
            step=step,
            attempt=attempt,
            pre_result=pre_result,
        )

    def _rejected_result(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
        pre_result: SafetyEvaluationResult,
    ) -> StepExecutionResult:
        decision = pre_result.decision
        limiting = pre_result.limiting_rule
        error_code = SAFETY_DECISION_ERROR_CODES.get(decision.value, "SAFETY_ACTION_REJECTED")
        audit_event = {
            "PAUSE": "SAFETY_PAUSE_REQUESTED",
            "REJECT": "SAFETY_ACTION_REJECTED",
            "REQUEST_CORRECTION": "SAFETY_ACTION_REJECTED",
            "EMERGENCY_STOP": "EMERGENCY_STOP_REQUESTED",
        }.get(decision.value, "SAFETY_ACTION_REJECTED")
        self._record_audit(
            audit_event,
            contract=contract,
            step=step,
            rule_id=limiting.rule_id if limiting else "UNKNOWN",
            decision=decision.value,
            reason_code=limiting.reason_code if limiting else "UNKNOWN",
            measured_value=limiting.measured_value if limiting else None,
            limit_value=limiting.limit_value if limiting else None,
        )
        return self._result(
            contract=contract,
            step=step,
            attempt=attempt,
            success=False,
            error=safety_error(
                error_code,
                limiting.message if limiting else f"safety decision {decision.value}",
                details=self._error_details(decision.value, limiting),
            ),
            action_result=None,
            duration_ms=0,
        )

    def _execute_with_robot(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
        parameters: dict[str, Any],
    ) -> StepExecutionResult:
        step_with_params = step.model_copy(update={"parameters": parameters})

        result = self._skill_executor.execute_attempt(
            contract=contract,
            step=step_with_params,
            attempt=attempt,
        )

        if result.success:
            robot_state = self._robot.get_state()
            if isinstance(robot_state, RobotState):
                telemetry = self._telemetry_provider.latest()
                scene = self._scene_provider.snapshot()
                scene_version = scene.scene_version if scene is not None else contract.scene_version
                post_ctx = self._context_builder.build(
                    contract=contract,
                    step=step,
                    robot_state=robot_state,
                    scene_version=scene_version,
                    resolved_parameters=parameters,
                    scene_updated_at=scene.updated_at if scene is not None else None,
                    telemetry_timestamp=telemetry.timestamp if telemetry is not None else None,
                    step_started_at_mono=self._step_started_at_mono,
                    task_started_at_mono=self._task_started_at_mono,
                    requested_velocity=telemetry.tcp_velocity if telemetry is not None else 0.0,
                    requested_joint_velocities=(
                        list(telemetry.joint_velocities)
                        if telemetry is not None and telemetry.joint_velocities
                        else []
                    ),
                    requested_acceleration=telemetry.acceleration if telemetry is not None else 0.0,
                    obstacles=scene.obstacles if scene is not None else [],
                    forbidden_zones=scene.forbidden_zones if scene is not None else [],
                )
                post_result = self._shield.post_check(post_ctx)
                if post_result.decision not in {
                    SafetyDecision.ALLOW,
                    SafetyDecision.ALLOW_WITH_LIMITS,
                }:
                    limiting = post_result.limiting_rule
                    post_error_code = SAFETY_DECISION_ERROR_CODES.get(
                        post_result.decision.value, "SAFETY_POST_CHECK_FAILED"
                    )
                    self._record_audit(
                        "SAFETY_POST_CHECK_FAILED",
                        contract=contract,
                        step=step,
                        rule_id=limiting.rule_id if limiting else "UNKNOWN",
                        decision=post_result.decision.value,
                        reason_code=limiting.reason_code if limiting else "UNKNOWN",
                        measured_value=limiting.measured_value if limiting else None,
                        limit_value=limiting.limit_value if limiting else None,
                    )
                    return StepExecutionResult(
                        task_id=contract.task_id,
                        step_id=step.step_id,
                        skill=step.skill.value,
                        attempt=attempt,
                        success=False,
                        error=safety_error(
                            post_error_code,
                            limiting.message if limiting else "post-check failed",
                            details=self._error_details(post_result.decision.value, limiting),
                        ),
                        action_result=result.action_result,
                        duration_ms=result.duration_ms,
                        timestamp=datetime.now(UTC),
                    )

        return result

    def _error_details(self, decision: str, limiting: object) -> dict[str, object]:
        rule_id = getattr(limiting, "rule_id", "UNKNOWN")
        reason_code = getattr(limiting, "reason_code", "UNKNOWN")
        measured = getattr(limiting, "measured_value", None)
        limit = getattr(limiting, "limit_value", None)
        return {
            "safety_decision": decision,
            "rule_id": rule_id,
            "reason_code": reason_code,
            "policy_version": self._policy_version,
            "policy_hash": self._policy_hash,
            "measured_value": measured,
            "limit_value": limit,
        }

    def _limiting_rule_id(self, result: SafetyEvaluationResult) -> str:
        for rule in result.evaluated_rules:
            if rule.decision == SafetyDecision.ALLOW_WITH_LIMITS:
                return rule.rule_id
        return "UNKNOWN"

    def _record_rule_results(
        self,
        contract: TaskContract,
        step: TaskStep,
        result: SafetyEvaluationResult,
    ) -> None:
        if self._repository is None:
            return
        for rule in result.evaluated_rules:
            if rule.decision in {SafetyDecision.ALLOW, SafetyDecision.ALLOW_WITH_LIMITS}:
                event = "SAFETY_RULE_PASSED"
            else:
                event = "SAFETY_RULE_FAILED"
            self._record_audit(
                event,
                contract=contract,
                step=step,
                rule_id=rule.rule_id,
                decision=rule.decision.value,
                reason_code=rule.reason_code,
                measured_value=rule.measured_value,
                limit_value=rule.limit_value,
            )

    def _record_audit(
        self,
        event_type: str,
        *,
        contract: TaskContract,
        step: TaskStep,
        rule_id: str,
        decision: str,
        reason_code: str,
        measured_value: float | None = None,
        limit_value: float | None = None,
        original_parameters: dict[str, object] | None = None,
        limited_parameters: dict[str, object] | None = None,
    ) -> None:
        if self._repository is None:
            return
        self._repository.record_audit_event(
            task_id=contract.task_id,
            event_type=event_type,
            details={
                "plan_version": contract.plan_version,
                "command_seq": contract.command_seq,
                "step_id": step.step_id,
                "rule_id": rule_id,
                "decision": decision,
                "reason_code": reason_code,
                "policy_version": self._policy_version,
                "policy_hash": self._policy_hash,
                "measured_value": measured_value,
                "limit_value": limit_value,
                "original_parameters": original_parameters,
                "limited_parameters": limited_parameters,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    def _result(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
        success: bool,
        error: StructuredError | None,
        action_result: Any,
        duration_ms: int,
    ) -> StepExecutionResult:
        return StepExecutionResult(
            task_id=contract.task_id,
            step_id=step.step_id,
            skill=step.skill.value,
            attempt=attempt,
            success=success,
            error=error,
            action_result=action_result,
            duration_ms=duration_ms,
            timestamp=datetime.now(UTC),
        )
