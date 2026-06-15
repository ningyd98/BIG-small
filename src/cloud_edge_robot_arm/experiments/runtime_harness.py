from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.auto_mode.models import AutoModeTransitionRequest
from cloud_edge_robot_arm.auto_mode.repository import SQLiteAutoModeRepository
from cloud_edge_robot_arm.auto_mode.transition_service import ModeTransitionService
from cloud_edge_robot_arm.cloud.replanning.adapters import RuleBasedReplannerAdapter
from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
from cloud_edge_robot_arm.cloud.replanning.service import LocalReplanningService
from cloud_edge_robot_arm.cloud.supervision.core import Clock
from cloud_edge_robot_arm.cloud.supervision.models import EdgeStatusSnapshot, SupervisoryDecision
from cloud_edge_robot_arm.cloud.supervision.repository import SQLiteSupervisionRepository
from cloud_edge_robot_arm.cloud.supervision.service import PeriodicSupervisorService
from cloud_edge_robot_arm.contracts import (
    AutoModeDecision,
    AutoModeStatus,
    AutoModeTransition,
    CommandAck,
    CommandAckStatus,
    ControlMode,
    FailurePolicy,
    RiskSnapshot,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator
from cloud_edge_robot_arm.edge.event_mode.controller import EventTriggeredModeController
from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutionResult, TaskExecutor
from cloud_edge_robot_arm.edge.safety.models import Obstacle
from cloud_edge_robot_arm.edge.safety.providers import (
    SceneSnapshot,
    TelemetrySample,
)
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.errors import StructuredError
from cloud_edge_robot_arm.experiments.models import ExperimentConfig, ExperimentMode
from cloud_edge_robot_arm.experiments.reproducibility import stable_hash
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.repositories.models import (
    AcceptedCommandRecord,
    AuditEventRecord,
    StepExecutionRecord,
)
from cloud_edge_robot_arm.simulation.clock import VirtualClock
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene
from cloud_edge_robot_arm.simulation.world import SimulatedWorld
from cloud_edge_robot_arm.skill_cache.repository import SQLiteSkillCacheRepository

BASE_TIME = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)


class VirtualClockAdapter(Clock):
    def __init__(self, clock: VirtualClock) -> None:
        self._clock = clock

    def now(self) -> datetime:
        return BASE_TIME + timedelta(milliseconds=self._clock.now_ms)

    def monotonic(self) -> float:
        return self._clock.now_ms / 1000.0


class ExperimentTelemetryProvider:
    def __init__(self, clock: VirtualClockAdapter) -> None:
        self._clock = clock

    def latest(self) -> TelemetrySample:
        return TelemetrySample(timestamp=self._clock.now(), tcp_velocity=0.0)


class ExperimentSceneProvider:
    def __init__(
        self, *, clock: VirtualClockAdapter, robot: MockRobotAdapter, world: SimulatedWorld
    ) -> None:
        self._clock = clock
        self._robot = robot
        self._world = world
        self.expected_scene_version = robot.scene_version

    def snapshot(self) -> SceneSnapshot:
        obstacles: list[Obstacle] = []
        if self._world.obstacle_inserted:
            state = self._robot.get_state()
            obstacles.append(
                Obstacle(
                    obstacle_id="dynamic-obstacle",
                    x=state.tcp_pose.x,
                    y=state.tcp_pose.y,
                    z=max(0.08, state.tcp_pose.z),
                    radius_m=0.08,
                )
            )
        return SceneSnapshot(
            scene_version=self.expected_scene_version,
            updated_at=self._clock.now(),
            obstacles=obstacles,
            forbidden_zones=[],
        )


@dataclass
class ExperimentExecutionObserver:
    clock: VirtualClock
    events: list[dict[str, object]] = field(default_factory=list)
    contract_validator_calls: int = 0
    task_executor_calls: int = 0
    safety_precheck_calls: int = 0
    robot_action_calls: int = 0
    terminal_results: list[TaskExecutionResult] = field(default_factory=list)

    def on_contract_received(self, task_id: str, payload: dict[str, Any]) -> None:
        self.record("contract_received", task_id, {"command_seq": payload.get("command_seq")})

    def on_contract_validation(self, task_id: str, accepted: bool, error_code: str) -> None:
        self.contract_validator_calls += 1
        self.record(
            "contract_validated",
            task_id,
            {"accepted": accepted, "error_code": error_code},
        )

    def on_task_executor_called(self, task_id: str) -> None:
        self.task_executor_calls += 1
        self.record("task_executor_called", task_id, {})

    def on_step_started(self, contract: TaskContract, step_id: str, attempt: int) -> None:
        self.record(
            "step_started",
            step_id,
            {
                "task_id": contract.task_id,
                "attempt": attempt,
                "plan_version": contract.plan_version,
                "command_seq": contract.command_seq,
            },
        )

    def on_step_result(self, contract: TaskContract, result: StepExecutionResult) -> None:
        if result.post_safety_decision:
            self.safety_precheck_calls += 1
        if result.action_result is not None:
            self.robot_action_calls += 1
        event_type = "step_completed"
        if not result.success:
            decision = result.post_safety_decision
            if decision == "PAUSE":
                event_type = "step_paused"
            elif decision in {"REJECT", "REQUEST_CORRECTION", "EMERGENCY_STOP"}:
                event_type = "step_rejected"
            else:
                event_type = "step_failed"
        self.record(
            event_type,
            result.step_id,
            {
                "task_id": contract.task_id,
                "attempt": result.attempt,
                "skill": result.skill,
                "success": result.success,
                "error_code": result.error_code or "",
                "safety_decision": result.post_safety_decision,
            },
        )

    def on_task_terminal(self, result: TaskExecutionResult) -> None:
        self.terminal_results.append(result)
        task_id = result.context.task_id if result.context is not None else ""
        self.record(
            "task_terminal",
            task_id,
            {
                "success": result.success,
                "error_code": "" if result.error is None else result.error.code,
            },
        )

    def record(self, event_type: str, entity_id: str, payload: dict[str, object]) -> None:
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        self.events.append(
            {
                "virtual_time_ms": self.clock.now_ms,
                "event_type": event_type,
                "entity_id": entity_id,
                "payload": dict(payload),
                "payload_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            }
        )


class RuntimeExperimentHarness:
    def __init__(
        self,
        *,
        config: ExperimentConfig,
        clock: VirtualClock,
        world: SimulatedWorld | None = None,
    ) -> None:
        self.config = config
        self.clock = clock
        self.clock_adapter = VirtualClockAdapter(clock)
        self.world = world or SimulatedWorld()
        self.artifact_dir = Path(config.artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.observer = ExperimentExecutionObserver(clock=clock)
        self._last_contract: TaskContract | None = None
        self._build_runtime()

    @property
    def current_mode(self) -> ControlMode:
        if self._last_contract is None:
            task_id = f"task-{self.config.experiment_id}-{self.config.seed}"
        else:
            task_id = self._last_contract.task_id
        status = self.auto_repo.get_status(task_id)
        if status is not None:
            return status.current_mode
        return self._initial_mode()

    def create_contract(self) -> TaskContract:
        issued = self.clock_adapter.now()
        mode = self._initial_mode()
        contract = TaskContract(
            task_id=f"task-{self.config.experiment_id}-{self.config.seed}",
            plan_version=1,
            command_seq=1,
            timestamp=issued,
            control_mode=mode,
            issued_at=issued,
            valid_until=issued + timedelta(milliseconds=self.config.timeout_ms),
            user_instruction="place the red cube into bin a",
            scene_version=1,
            expected_scene_version=1,
            task_target=TaskTarget(
                object_id="red_cube",
                object_class=self.config.task_profile.object_class,
                target_region_id="bin_a",
            ),
            steps=[
                _step("step-home", SkillName.HOME),
                _step(
                    "step-move-above",
                    SkillName.MOVE_ABOVE,
                    {"object_id": "red_cube", "z_offset_m": 0.12},
                ),
                _step("step-approach", SkillName.APPROACH, {"object_id": "red_cube"}),
                _step("step-grasp", SkillName.GRASP, {"object_id": "red_cube"}, retry_limit=1),
                _step("step-lift", SkillName.LIFT, {"height_m": 0.16}),
                _step("step-move-region", SkillName.MOVE_TO_REGION, {"region_id": "bin_a"}),
                _step("step-place", SkillName.PLACE, {"region_id": "bin_a"}),
                _step("step-release", SkillName.RELEASE),
                _step(
                    "step-verify",
                    SkillName.VERIFY_RESULT,
                    {"object_id": "red_cube", "region_id": "bin_a"},
                ),
                _step("step-retreat", SkillName.RETREAT, {"distance_m": 0.1}),
                _step("step-home-final", SkillName.HOME),
            ],
            safety_constraints=SafetyConstraints(
                max_joint_velocity=0.5,
                max_tcp_velocity=0.15,
                minimum_safe_height=0.08,
                workspace_id="workspace_a",
            ),
            failure_policy=FailurePolicy(
                local_retry_limit=1,
                on_timeout="pause",
                on_safety_rejection="stop",
                on_network_loss="pause",
            ),
            completion_criteria=["object_inside_target_region", "robot_in_safe_pose"],
            supervision_period_ms=self.config.supervision_period_ms,
            command_ttl_ms=2_500,
        )
        self._last_contract = contract
        self.auto_repo.save_status(
            AutoModeStatus(
                task_id=contract.task_id,
                current_mode=mode,
                mode_version=1,
                switch_count=0,
                last_switch_at=self.clock_adapter.now() - timedelta(minutes=10),
                policy_version="auto-v1",
                updated_at=self.clock_adapter.now(),
            )
        )
        return contract

    def submit_contract(self, contract: TaskContract) -> TaskExecutionResult:
        self._last_contract = contract
        self.event_repo.save_active_contract(
            contract,
            plan_id=f"plan-{contract.task_id}",
            robot_id="robot-unknown",
            status="ACTIVE",
        )
        return self.executor.submit_contract(contract.model_dump(mode="json"))

    def deliver_cloud_command(self, contract: TaskContract, *, request_id: str) -> CommandAck:
        payload = contract.model_dump(mode="json")
        validation = EdgeContractValidator(supported_skills=self.registry.skills()).accept_payload(
            payload, now=self.clock_adapter.now()
        )
        if not validation.accepted or validation.contract is None:
            status = _ack_status_for_error(
                "" if validation.error is None else validation.error.code
            )
            return self._save_ack(
                contract,
                request_id,
                accepted=False,
                status=status,
                error=validation.error,
            )
        if validation.contract.scene_version != validation.contract.expected_scene_version:
            return self._save_ack(
                validation.contract,
                request_id,
                accepted=False,
                status=CommandAckStatus.REJECTED_SCENE_MISMATCH.value,
                error=StructuredError(
                    code="SCENE_VERSION_MISMATCH",
                    message="scene_version does not match expected_scene_version",
                    category="COMMAND_INGRESS",
                ),
            )
        accepted_records = [
            record
            for record in getattr(self.runtime_repo, "_accepted_commands", {}).values()
            if record.task_id == validation.contract.task_id
        ]
        if accepted_records:
            max_seq = max(record.command_seq for record in accepted_records)
            max_plan = max(record.plan_version for record in accepted_records)
            if validation.contract.plan_version < max_plan:
                return self._save_ack(
                    validation.contract,
                    request_id,
                    accepted=False,
                    status="REJECTED_STALE_PLAN",
                    error=StructuredError(
                        code="STALE_PLAN_VERSION",
                        message="plan_version is older than accepted command history",
                        category="COMMAND_INGRESS",
                    ),
                )
            if validation.contract.command_seq < max_seq:
                return self._save_ack(
                    validation.contract,
                    request_id,
                    accepted=False,
                    status="REJECTED_STALE_SEQUENCE",
                    error=StructuredError(
                        code="STALE_COMMAND_SEQ",
                        message="command_seq is older than accepted command history",
                        category="COMMAND_INGRESS",
                    ),
                )
            if validation.contract.command_seq == max_seq:
                same_seq = next(
                    record for record in accepted_records if record.command_seq == max_seq
                )
                if validation.contract.plan_version > max_plan:
                    return self._save_ack(
                        validation.contract,
                        request_id,
                        accepted=False,
                        status="REJECTED_STALE_SEQUENCE",
                        error=StructuredError(
                            code="STALE_COMMAND_SEQ",
                            message="command_seq is not newer than accepted history",
                            category="COMMAND_INGRESS",
                        ),
                    )
                if same_seq.payload_hash == stable_hash(payload):
                    return self._save_ack(
                        validation.contract,
                        request_id,
                        accepted=False,
                        status=CommandAckStatus.REJECTED_DUPLICATE.value,
                        error=StructuredError(
                            code="COMMAND_SEQ_REPLAYED",
                            message="command_seq has already been accepted for this task",
                            category="COMMAND_INGRESS",
                        ),
                    )
                return self._save_ack(
                    validation.contract,
                    request_id,
                    accepted=False,
                    status="REJECTED_IDEMPOTENCY_CONFLICT",
                    error=StructuredError(
                        code="COMMAND_SEQ_CONFLICT",
                        message="command_seq was reused with a different payload",
                        category="COMMAND_INGRESS",
                    ),
                )
        decision = self.runtime_repo.accept_command(
            validation.contract,
            payload_hash=stable_hash(payload),
        )
        if not decision.accepted:
            return self._save_ack(
                validation.contract,
                request_id,
                accepted=False,
                status=_ack_status_for_error(decision.code),
                error=StructuredError(
                    code=decision.code,
                    message=decision.message,
                    category="COMMAND_INGRESS",
                ),
            )
        return self._save_ack(
            validation.contract,
            request_id,
            accepted=True,
            status=CommandAckStatus.ACCEPTED.value,
            error=None,
        )

    def run_supervision_tick(self, contract: TaskContract) -> SupervisoryDecision:
        snapshot = self._edge_snapshot(contract)
        return self.supervisor.evaluate_snapshot(snapshot, contract)

    def emit_edge_event(self, event_type: str, details: dict[str, object] | None = None) -> None:
        self.event_repo.record_audit_event(
            self._last_contract.task_id if self._last_contract else "unknown",
            event_type,
            dict(details or {}),
        )

    def apply_replan(self, request: object) -> object:
        return self.replanning.process(request)  # type: ignore[arg-type]

    def prepare_mode_transition(
        self,
        task_id: str,
        *,
        to_mode: ControlMode,
        decision_id: str,
        reason: str,
    ) -> AutoModeTransition:
        status = self.auto_repo.get_status(task_id)
        from_mode = status.current_mode if status is not None else self._initial_mode()
        version = status.mode_version if status is not None else 1
        request = AutoModeTransitionRequest(
            task_id=task_id,
            from_mode=from_mode,
            to_mode=to_mode,
            expected_mode_version=version,
            idempotency_key=f"{task_id}:{decision_id}:{to_mode.value}",
            decision_id=decision_id,
            reason=reason,
        )
        transition = self.transition_service.prepare(request)
        self.auto_repo.save_transition(transition)
        self.auto_repo.record_audit_event(
            task_id,
            "transition_prepared",
            {"transition_id": transition.transition_id, "to_mode": to_mode.value},
        )
        return transition

    def save_risk_snapshot(self, snapshot: RiskSnapshot) -> RiskSnapshot:
        return self.auto_repo.save_risk_snapshot(snapshot)

    def save_auto_decision(self, decision: AutoModeDecision) -> AutoModeDecision:
        return self.auto_repo.save_decision(decision)

    def commit_mode_transition(self, transition_id: str) -> AutoModeTransition:
        committed = self.transition_service.commit(transition_id)
        self.auto_repo.save_transition(committed)
        previous = self.auto_repo.get_status(committed.task_id)
        self.auto_repo.save_status(
            AutoModeStatus(
                task_id=committed.task_id,
                current_mode=committed.to_mode,
                mode_version=committed.new_mode_version,
                switch_count=(previous.switch_count if previous else 0) + 1,
                last_switch_at=self.clock_adapter.now(),
                last_decision_id=committed.decision_id,
                policy_version="auto-v1",
                updated_at=self.clock_adapter.now(),
            )
        )
        self.auto_repo.record_audit_event(
            committed.task_id,
            "transition_committed",
            {"transition_id": committed.transition_id, "to_mode": committed.to_mode.value},
        )
        return committed

    def abort_mode_transition(self, transition_id: str, *, reason: str) -> AutoModeTransition:
        aborted = self.transition_service.abort(transition_id, reason=reason)
        self.auto_repo.save_transition(aborted)
        self.auto_repo.record_audit_event(
            aborted.task_id,
            "transition_aborted",
            {"transition_id": aborted.transition_id, "reason": reason},
        )
        return aborted

    def restart_runtime(self) -> None:
        self.close()
        self._build_runtime()
        self.observer.record(
            "runtime_restarted", "sqlite", {"artifact_dir": str(self.artifact_dir)}
        )

    def completed_step_ids(self) -> list[str]:
        if self._last_contract is None:
            return []
        return [
            record.step_id
            for record in self.runtime_repo.list_step_executions(self._last_contract.task_id)
            if record.success
        ]

    def completion_summary(self) -> object | None:
        if self._last_contract is None:
            return None
        return self.event_repo.get_completion_summary_for_task(self._last_contract.task_id)

    def audit_events(self, task_id: str) -> list[AuditEventRecord]:
        return self.runtime_repo.list_audit_events(task_id)

    def accepted_command_records(self, task_id: str) -> list[AcceptedCommandRecord]:
        return [
            record
            for record in getattr(self.runtime_repo, "_accepted_commands", {}).values()
            if record.task_id == task_id
        ]

    def step_execution_records(self, task_id: str) -> list[StepExecutionRecord]:
        return self.runtime_repo.list_step_executions(task_id)

    def command_ack_rejection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for raw in self.observer.events:
            if raw["event_type"] != "command_ack":
                continue
            payload = raw["payload"]
            if not isinstance(payload, dict) or payload.get("accepted") is True:
                continue
            status = str(payload.get("status", ""))
            counts[status] = counts.get(status, 0) + 1
        return counts

    def close(self) -> None:
        self.event_repo.close()
        self.auto_repo.close()
        self.skill_cache_repo.close()
        self.supervision_repo.close()

    def _build_runtime(self) -> None:
        self.scene = MockScene.with_default_pick_place_scene()
        self.robot = MockRobotAdapter(
            scene=self.scene,
            auto_connect=True,
            default_action_duration_ms=100,
            clock=self.clock_adapter.now,
            advance_clock=self.clock.advance,
        )
        self.runtime_repo = InMemoryRepository()
        self.event_repo = SQLiteEventAutonomyRepository(
            self.artifact_dir / "event-autonomy.sqlite3"
        )
        self.auto_repo = SQLiteAutoModeRepository(
            self.artifact_dir / "auto-mode.sqlite3", clock=self.clock_adapter.now
        )
        self.skill_cache_repo = SQLiteSkillCacheRepository(
            self.artifact_dir / "skill-cache.sqlite3", clock=self.clock_adapter.now
        )
        self.supervision_repo = SQLiteSupervisionRepository(
            self.artifact_dir / "supervision.sqlite3"
        )
        self.shield = SafetyShield()
        self.registry = SkillRegistry.default()
        self.event_controller = EventTriggeredModeController(repository=self.event_repo)
        self.telemetry_provider = ExperimentTelemetryProvider(self.clock_adapter)
        self.scene_provider = ExperimentSceneProvider(
            clock=self.clock_adapter, robot=self.robot, world=self.world
        )
        self.executor = TaskExecutor(
            robot=self.robot,
            shield=self.shield,
            repository=self.runtime_repo,
            registry=self.registry,
            scene_version=self.robot.scene_version,
            telemetry_provider=self.telemetry_provider,
            scene_provider=self.scene_provider,
            event_controller=self.event_controller,
            observer=self.observer,
            clock=self.clock_adapter,
        )
        self.transition_service = ModeTransitionService(
            clock=self.clock_adapter.now, repository=self.auto_repo
        )
        self.apply_service = ReplanApplyService(
            repository=self.event_repo, dispatcher=None, clock=self.clock_adapter.now
        )
        self.replanning = LocalReplanningService(
            adapter=RuleBasedReplannerAdapter(clock=self.clock_adapter.now),
            repository=self.event_repo,
            apply_service=self.apply_service,
            clock=self.clock_adapter.now,
        )
        from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter

        self.supervisor = PeriodicSupervisorService(
            planner=MockPlannerAdapter(),
            clock=self.clock_adapter,
            repository=self.supervision_repo,
        )

    def _initial_mode(self) -> ControlMode:
        if self.config.mode == ExperimentMode.PCSC:
            return ControlMode.PERIODIC_CLOUD_SUPERVISION
        if self.config.mode == ExperimentMode.ETEAC:
            return ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
        return ControlMode.PERIODIC_CLOUD_SUPERVISION

    def _save_ack(
        self,
        contract: TaskContract,
        request_id: str,
        *,
        accepted: bool,
        status: str,
        error: StructuredError | None,
    ) -> CommandAck:
        ack = CommandAck(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            timestamp=self.clock_adapter.now(),
            accepted=accepted,
            status=status,
            error=error,
            request_id=request_id,
            correlation_id=f"{contract.task_id}:{request_id}",
            details={"scene_version": contract.scene_version},
        )
        saved = self.event_repo.save_command_ack(ack)
        self.observer.record(
            "command_ack",
            request_id,
            {
                "accepted": saved.accepted,
                "status": saved.status,
                "command_seq": saved.command_seq,
                "plan_version": saved.plan_version,
                "error_code": "" if saved.error is None else saved.error.code,
            },
        )
        return saved

    def _edge_snapshot(self, contract: TaskContract) -> EdgeStatusSnapshot:
        current_step_id = self._current_step_id_from_observer(contract.task_id)
        scene = self.scene_provider.snapshot()
        return EdgeStatusSnapshot(
            robot_id="robot-unknown",
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            scene_version=self.world.scene_version,
            timestamp=self.clock_adapter.now(),
            current_step_id=current_step_id,
            completed_step_ids=self.completed_step_ids(),
            robot_state=self.robot.get_state().model_dump(mode="json"),
            target_state={
                "object_id": contract.task_target.object_id,
                "object_class": contract.task_target.object_class,
                "region_id": contract.task_target.target_region_id,
                "target_visible": self.world.target_visible,
                "target_moved": self.world.target_moved,
                "target_lost": self.world.target_lost,
                "obstacle_inserted": self.world.obstacle_inserted,
                "obstacle_count": self.world.obstacle_count,
                "scene_version": self.world.scene_version,
            },
            obstacle_state={
                "obstacle_ids": [obstacle.obstacle_id for obstacle in scene.obstacles],
                "obstacle_inserted": self.world.obstacle_inserted,
                "obstacle_count": self.world.obstacle_count,
            },
            scene_confidence=self.world.scene_confidence,
        )

    def _current_step_id_from_observer(self, task_id: str) -> str:
        active = ""
        completed: set[str] = set()
        for event in self.observer.events:
            payload = event.get("payload")
            if not isinstance(payload, dict) or payload.get("task_id") != task_id:
                continue
            event_type = str(event.get("event_type", ""))
            entity_id = str(event.get("entity_id", ""))
            if event_type == "step_started":
                active = entity_id
            elif event_type in {"step_completed", "step_failed", "step_paused", "step_rejected"}:
                completed.add(entity_id)
                if active == entity_id:
                    active = ""
        return "" if active in completed else active


def _ack_status_for_error(code: str) -> str:
    if code in {"CONTRACT_EXPIRED", "COMMAND_EXPIRED"}:
        return CommandAckStatus.REJECTED_EXPIRED.value
    if code == "COMMAND_SEQ_CONFLICT":
        return "REJECTED_IDEMPOTENCY_CONFLICT"
    if code == "COMMAND_SEQ_REPLAYED":
        return CommandAckStatus.REJECTED_DUPLICATE.value
    if code == "STALE_PLAN_VERSION":
        return "REJECTED_STALE_PLAN"
    if code in {"STALE_COMMAND_SEQ", "COMMAND_SEQ_OUT_OF_ORDER"}:
        return "REJECTED_STALE_SEQUENCE"
    return CommandAckStatus.REJECTED_SEMANTIC_INVALID.value


def _step(
    step_id: str,
    skill: SkillName,
    parameters: dict[str, object] | None = None,
    *,
    retry_limit: int = 0,
) -> TaskStep:
    return TaskStep(
        step_id=step_id,
        skill=skill,
        parameters=dict(parameters or {}),
        expected_duration_ms=100,
        timeout_ms=3_000,
        retry_limit=retry_limit,
    )
