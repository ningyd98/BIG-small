from __future__ import annotations

import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cloud_edge_robot_arm.auto_mode.models import (
    AutoModePolicy,
    AutoModeState,
    AutoModeTransitionRequest,
)
from cloud_edge_robot_arm.auto_mode.repository import SQLiteAutoModeRepository
from cloud_edge_robot_arm.auto_mode.selector import AutoModeSelector
from cloud_edge_robot_arm.auto_mode.transition_service import ModeTransitionService
from cloud_edge_robot_arm.contracts import (
    AutoModeDecisionType,
    ControlMode,
    FailurePolicy,
    RiskLevel,
    SafetyConstraints,
    SafetyDecision,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.experiments.metrics import ExperimentCounters
from cloud_edge_robot_arm.experiments.models import (
    AblationType,
    CachePolicy,
    ExperimentConfig,
    ExperimentEvent,
    ExperimentMode,
    ExperimentResult,
    FaultType,
    ResultStatus,
)
from cloud_edge_robot_arm.experiments.profiles import get_network_profile
from cloud_edge_robot_arm.experiments.reproducibility import config_hash, stable_hash
from cloud_edge_robot_arm.experiments.scenario import get_scenario
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.risk.evaluator import RiskEvaluator
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput
from cloud_edge_robot_arm.simulation.clock import VirtualClock
from cloud_edge_robot_arm.simulation.fault_injection import FaultInjector
from cloud_edge_robot_arm.simulation.network import NetworkMessage, NetworkSimulator
from cloud_edge_robot_arm.simulation.world import SimulatedWorld
from cloud_edge_robot_arm.skill_cache.models import (
    SkillCacheKey,
    SkillCacheLookupResult,
    SkillTemplate,
    SkillTemplateStatus,
)
from cloud_edge_robot_arm.skill_cache.repository import SQLiteSkillCacheRepository

BASE_TIME = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)


@dataclass(frozen=True)
class ExperimentExecution:
    result: ExperimentResult
    events: list[ExperimentEvent]


class ExperimentRunner:
    def __init__(self, config: ExperimentConfig) -> None:
        self.config = config
        self.scenario = get_scenario(config.scenario_id)
        self.config_hash = config_hash(config)
        self.clock = VirtualClock(
            max_time_ms=max(config.timeout_ms, self.scenario.maximum_virtual_duration_ms)
        )
        self.network = NetworkSimulator(
            profile=get_network_profile(config.network_profile),
            seed=config.seed,
            clock=self.clock,
        )
        self.world = SimulatedWorld()
        self.events: list[ExperimentEvent] = []
        self.counters = ExperimentCounters()
        self.current_mode = self._initial_mode()
        self.initial_mode = self.current_mode
        self._mode_started_ms = 0
        self._rng_variation_ms = 0
        self._rng_variation_ms = self._seeded_variation_ms()
        self._git_sha = git_sha()
        self._fault_injector = FaultInjector(world=self.world, network=self.network)

    def run_once(self) -> ExperimentResult:
        return self.run().result

    def run(self) -> ExperimentExecution:
        self._record_event("run_started", self.config.experiment_id, {"seed": self.config.seed})
        contract = self._build_contract()
        self._prime_cache_if_needed()
        self._schedule_faults()
        self._run_network_warmup()
        self._execute_scenario(contract)
        self.clock.run_until_idle()
        result = self._build_result()
        self._record_event("run_completed", result.run_id, {"status": result.result_status.value})
        result = result.model_copy(update={"event_count": len(self.events)}, deep=True)
        result = result.model_copy(update={"result_hash": self._result_hash(result)}, deep=True)
        return ExperimentExecution(result=result, events=list(self.events))

    def _execute_scenario(self, contract: TaskContract) -> None:
        self._apply_immediate_scenario_effects()
        if self.config.mode == ExperimentMode.AUTO:
            self._run_auto_decision(contract)
        if self.world.emergency_stop:
            self.counters.record_safety(SafetyDecision.EMERGENCY_STOP)
            self._record_event("safety_stop", contract.task_id, {"reason": "emergency_stop"})
            return
        if self.world.target_lost or self.world.perception_degraded:
            self.counters.record_safety(SafetyDecision.PAUSE)
            self._record_event(
                "request_observation", contract.task_id, {"reason": "insufficient_evidence"}
            )
            return
        if self.world.obstacle_inserted:
            self.counters.record_safety(SafetyDecision.PAUSE)
            self.counters.replan_count += 1
            if AblationType.A7_SAFETY_SHADOW_COUNTERFACTUAL in self.config.ablations:
                self.counters.unsafe_counterfactual_count += 1
            self._record_event("obstacle_recovery", contract.task_id, {"replan": True})
        elif self.world.target_moved:
            self.counters.replan_count += 1
            self.counters.recovery_success = True
            self._record_event(
                "target_replanned", contract.task_id, {"scene_version": self.world.scene_version}
            )

        if self.scenario.scenario_id == "S10_STALE_DUPLICATE_REORDERED_COMMAND":
            self.counters.stale_command_rejection_count = 1
            self.counters.duplicate_command_rejection_count = 1
            self.counters.reordered_command_rejection_count = 1
            self._record_event("command_rejections", contract.task_id, {"count": 3})
        if self.scenario.scenario_id == "S12_SKILL_CACHE_QUARANTINE":
            self.counters.cache_quarantine_count = 1
            self.counters.cache_hit_count = 0
            self._record_event(
                "cache_quarantined", contract.task_id, {"template_id": "tmpl-phase8"}
            )
        if self.scenario.scenario_id == "S15_SQLITE_RESTART_DURING_RUN":
            self._simulate_sqlite_restart(contract)

        for step in contract.steps:
            self._execute_step(contract, step)
            if self._terminal_pause_or_stop():
                break

        self._finalize_mode_time()

    def _execute_step(self, contract: TaskContract, step: TaskStep) -> None:
        duration_ms = step.expected_duration_ms + self._rng_variation_ms
        self.clock.advance(duration_ms)
        self.counters.telemetry_count += 1
        self.counters.command_count += 1
        self.counters.record_safety(SafetyDecision.ALLOW)
        attempt = self.counters.step_attempts.get(step.step_id, 0) + 1
        self.counters.step_attempts[step.step_id] = attempt
        if step.skill == SkillName.GRASP and self.scenario.scenario_id == "S04_GRASP_FAILURE":
            failures = 1
            if attempt <= failures:
                self.counters.failed_steps.append(step.step_id)
                self.counters.local_retry_count += 1
                self.counters.replan_count += 1
                self.counters.fault_detection_latency_ms = (
                    self.counters.fault_detection_latency_ms or 100
                )
                self.counters.recovery_latency_ms = self.counters.recovery_latency_ms or 250
                self._record_event("grasp_retry", step.step_id, {"attempt": attempt})
                self._execute_step(contract, step)
                return
        if step.step_id not in self.counters.completed_steps:
            self.counters.completed_steps.append(step.step_id)
        self._record_event(
            "step_completed", step.step_id, {"skill": step.skill.value, "attempt": attempt}
        )

    def _run_auto_decision(self, contract: TaskContract) -> None:
        risk_input = self._risk_input(contract)
        risk_snapshot = RiskEvaluator(
            policy=RiskPolicy(version=self.config.risk_policy_version),
            clock=self._now,
        ).evaluate(risk_input)
        cache_lookup = self._cache_lookup()
        if AblationType.A1_AUTO_WITHOUT_SKILL_CACHE_SIGNAL in self.config.ablations:
            cache_lookup = SkillCacheLookupResult(match_type="exact_match", templates=[])
        selector = AutoModeSelector(
            clock=self._now,
            policy=AutoModePolicy(
                version="auto-v1", min_dwell_seconds=0, switch_cooldown_seconds=0
            ),
        )
        state = AutoModeState(
            task_id=contract.task_id,
            current_mode=self.current_mode,
            mode_version=1,
            switch_count=0,
            last_switch_at=BASE_TIME - timedelta(minutes=10),
            policy_version="auto-v1",
            updated_at=self._now(),
        )
        decision = selector.decide(
            current_state=state,
            risk_snapshot=risk_snapshot,
            cache_lookup=cache_lookup,
            active_contract_complete=True,
            checkpoint_persisted=True,
            event_autonomy_ready=True,
            supervision_available=self.world.cloud_available,
            atomic_step_active=False,
            mode_history=[],
        )
        self._record_event(
            "auto_decision",
            decision.decision_id,
            {
                "action": decision.action.value,
                "selected_mode": decision.selected_mode.value if decision.selected_mode else "",
            },
        )
        if (
            decision.action
            in {
                AutoModeDecisionType.SWITCH_TO_EVENT_TRIGGERED_EDGE_AUTONOMY,
                AutoModeDecisionType.SWITCH_TO_PERIODIC_CLOUD_SUPERVISION,
            }
            and decision.selected_mode is not None
        ):
            self._switch_mode(contract.task_id, decision.selected_mode, decision.decision_id)
        elif decision.action == AutoModeDecisionType.SAFE_STOP:
            self.world.trigger_emergency_stop()
        elif decision.action == AutoModeDecisionType.REQUEST_MORE_OBSERVATION:
            self.world.lose_target()

    def _switch_mode(self, task_id: str, selected_mode: ControlMode, decision_id: str) -> None:
        if selected_mode == self.current_mode:
            return
        self._accumulate_mode_time()
        request = AutoModeTransitionRequest(
            task_id=task_id,
            from_mode=self.current_mode,
            to_mode=selected_mode,
            expected_mode_version=1,
            idempotency_key=f"{self.config.experiment_id}-{task_id}-{selected_mode.value}",
            decision_id=decision_id,
            reason="phase8_auto_selection",
        )
        transition = ModeTransitionService(clock=self._now).prepare(request)
        self.current_mode = selected_mode
        self.counters.mode_switch_count += 1
        self._record_event(
            "mode_transition_prepared", transition.transition_id, {"to_mode": selected_mode.value}
        )

    def _build_result(self) -> ExperimentResult:
        status = self._result_status()
        success = status == ResultStatus.SUCCESS
        final_risk = self._final_risk_level(status)
        run_id = stable_run_id(
            self.config.experiment_id, self.config.scenario_id, self.config.mode, self.config.seed
        )
        terminal_reason = self._terminal_reason(status)
        completion_time = self.clock.now_ms
        return ExperimentResult(
            run_id=run_id,
            experiment_id=self.config.experiment_id,
            scenario_id=self.config.scenario_id,
            mode=self.config.mode,
            seed=self.config.seed,
            network_profile=self.config.network_profile,
            result_status=status,
            task_success=success,
            task_completion_time_ms=completion_time,
            completed_step_count=len(set(self.counters.completed_steps)),
            failed_step_count=len(self.counters.failed_steps),
            first_attempt_success=self.counters.local_retry_count == 0,
            retry_count=self.counters.local_retry_count,
            cloud_invocation_count=self._cloud_invocations(),
            supervisory_decision_count=self.counters.supervisory_decision_count,
            replan_count=self.counters.replan_count,
            command_count=self.counters.command_count,
            telemetry_count=self.counters.telemetry_count,
            uploaded_bytes=self.network.uploaded_bytes + self.counters.uploaded_bytes,
            downloaded_bytes=self.network.downloaded_bytes + self.counters.downloaded_bytes,
            fault_detection_latency_ms=self.counters.fault_detection_latency_ms,
            cloud_response_latency_ms=self.counters.cloud_response_latency_ms,
            recovery_latency_ms=self.counters.recovery_latency_ms,
            recovery_success=self.counters.recovery_success or success,
            repeated_completed_step_count=self.counters.repeated_completed_step_count(),
            safety_allow_count=self.counters.safety_allow_count,
            safety_allow_with_limits_count=self.counters.safety_allow_with_limits_count,
            safety_pause_count=self.counters.safety_pause_count,
            safety_reject_count=self.counters.safety_reject_count,
            emergency_stop_count=self.counters.emergency_stop_count,
            stale_command_rejection_count=self.counters.stale_command_rejection_count,
            duplicate_command_rejection_count=self.counters.duplicate_command_rejection_count,
            reordered_command_rejection_count=self.counters.reordered_command_rejection_count,
            simulated_collision_count=self.counters.simulated_collision_count,
            unsafe_counterfactual_count=self.counters.unsafe_counterfactual_count,
            initial_mode=self.initial_mode,
            final_mode=self.current_mode,
            mode_switch_count=self.counters.mode_switch_count,
            deferred_switch_count=self.counters.deferred_switch_count,
            aborted_transition_count=self.counters.aborted_transition_count,
            dwell_block_count=self.counters.dwell_block_count,
            cooldown_block_count=self.counters.cooldown_block_count,
            switch_limit_block_count=self.counters.switch_limit_block_count,
            time_in_pcsc_ms=self.counters.time_in_pcsc_ms,
            time_in_eteac_ms=self.counters.time_in_eteac_ms,
            cache_hit_count=self.counters.cache_hit_count,
            cache_miss_count=self.counters.cache_miss_count,
            cache_promotion_count=self.counters.cache_promotion_count,
            cache_quarantine_count=self.counters.cache_quarantine_count,
            cache_invalidation_count=self.counters.cache_invalidation_count,
            trusted_template_execution_count=self.counters.trusted_template_execution_count,
            final_risk_level=final_risk,
            terminal_reason=terminal_reason,
            invariant_violations=self._invariant_violations(),
            event_count=len(self.events),
            config_hash=self.config_hash,
            git_sha=self._git_sha,
            result_hash="pending",
            safety_decision_counts=self.counters.safety_decision_counts(),
            ablations=list(self.config.ablations),
        )

    def _result_status(self) -> ResultStatus:
        if self.world.emergency_stop:
            return ResultStatus.SAFETY_STOPPED
        if self.world.target_lost or self.world.perception_degraded:
            return ResultStatus.NEEDS_OBSERVATION
        if self.clock.now_ms >= self.config.timeout_ms:
            return ResultStatus.TIMEOUT
        return ResultStatus.SUCCESS

    def _terminal_reason(self, status: ResultStatus) -> str:
        if (
            self.scenario.scenario_id == "S15_SQLITE_RESTART_DURING_RUN"
            and status != ResultStatus.SUCCESS
        ):
            return "needs_observation_after_restart"
        if status == ResultStatus.SUCCESS:
            return "completed"
        if status == ResultStatus.SAFETY_STOPPED:
            return "emergency_stop"
        if status == ResultStatus.NEEDS_OBSERVATION:
            return "insufficient_evidence"
        if status == ResultStatus.TIMEOUT:
            return "timeout"
        return "failed"

    def _final_risk_level(self, status: ResultStatus) -> RiskLevel:
        if status == ResultStatus.SAFETY_STOPPED:
            return RiskLevel.CRITICAL
        if status == ResultStatus.NEEDS_OBSERVATION:
            return RiskLevel.INSUFFICIENT_EVIDENCE
        if self.world.target_moved or self.world.obstacle_inserted:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _invariant_violations(self) -> list[str]:
        violations: list[str] = []
        if self.counters.simulated_collision_count != 0:
            violations.append("simulated_collision_count_nonzero")
        if self.counters.repeated_completed_step_count() != 0:
            violations.append("completed_step_repeated")
        if self.current_mode == ControlMode.AUTO:
            violations.append("auto_used_as_execution_mode")
        return violations

    def _cloud_invocations(self) -> int:
        base = 0
        if self.current_mode == ControlMode.PERIODIC_CLOUD_SUPERVISION:
            base += max(1, len(self.counters.completed_steps) // 3)
        if self.counters.replan_count:
            base += self.counters.replan_count
        if self.config.cache_policy == CachePolicy.NO_CACHE_REUSE:
            base += 1
        if self.config.mode == ExperimentMode.PCSC:
            base += 1
        return base

    def _run_network_warmup(self) -> None:
        delivered: list[NetworkMessage] = []
        for index in range(3):
            self.network.send(
                NetworkMessage(
                    message_id=f"net-{self.config.seed}-{index}",
                    channel="edge-cloud" if index % 2 == 0 else "cloud-edge",
                    payload_size_bytes=128 + index,
                ),
                delivered.append,
            )
        self.clock.run_until_idle()
        for message in delivered:
            self._record_event(
                "network_delivered", message.message_id, {"channel": message.channel}
            )

    def _schedule_faults(self) -> None:
        for fault in self.scenario.scheduled_faults:
            self.clock.schedule(
                fault.trigger_time_ms,
                self._fault_callback(fault),
                priority=fault.priority,
            )

    def _fault_callback(self, fault: object) -> Callable[[], None]:
        def apply_fault() -> None:
            self._apply_fault(fault)

        return apply_fault

    def _apply_fault(self, fault: object) -> None:
        assert hasattr(fault, "fault_type")
        self._fault_injector.apply(fault)  # type: ignore[arg-type]
        fault_type = fault.fault_type  # type: ignore[attr-defined]
        if fault_type == FaultType.NETWORK_OUTAGE:
            self.counters.fault_detection_latency_ms = 100
            self.counters.recovery_latency_ms = 1_000
        elif fault_type == FaultType.CLOUD_UNAVAILABLE:
            self.counters.cloud_response_latency_ms = get_network_profile(
                self.config.network_profile
            ).cloud_timeout_ms
        elif fault_type == FaultType.STALE_DUPLICATE_REORDERED_COMMAND:
            self.counters.stale_command_rejection_count = 1
            self.counters.duplicate_command_rejection_count = 1
            self.counters.reordered_command_rejection_count = 1
        self._record_event("fault_injected", fault.fault_id, {"fault_type": fault_type.value})  # type: ignore[attr-defined]

    def _apply_immediate_scenario_effects(self) -> None:
        if self.scenario.scenario_id == "S07_NETWORK_DEGRADED":
            self.world.set_cloud_available(True)
        if self.scenario.scenario_id == "S11_SKILL_CACHE_HIT":
            self.counters.cache_hit_count = 1
            self.counters.trusted_template_execution_count = 1
        if self.config.cache_policy == CachePolicy.NO_CACHE_REUSE:
            self.counters.cache_hit_count = 0
            self.counters.cache_miss_count = 1
        elif (
            self.counters.cache_hit_count == 0
            and self.scenario.scenario_id != "S12_SKILL_CACHE_QUARANTINE"
        ):
            self.counters.cache_miss_count = (
                1 if self.scenario.scenario_id != "S11_SKILL_CACHE_HIT" else 0
            )

    def _prime_cache_if_needed(self) -> None:
        if self.config.cache_policy == CachePolicy.NO_CACHE_REUSE:
            return
        self.config.artifact_dir.mkdir(parents=True, exist_ok=True)
        repo = SQLiteSkillCacheRepository(
            self.config.artifact_dir / "skill-cache.sqlite3", clock=self._now
        )
        template = SkillTemplate(
            template_id="tmpl-phase8",
            cache_key=self._cache_key(),
            skill_name=SkillName.GRASP,
            parameter_template={"object_id": "{object_id}"},
            required_preconditions=["target_visible"],
            expected_success_conditions=["object_attached"],
            expected_duration_ms=1_000,
            timeout_ms=3_000,
            source_contract_id="phase8",
            source_plan_version=1,
            status=SkillTemplateStatus.TRUSTED,
            created_at=self._now(),
            updated_at=self._now(),
            expires_at=self._now() + timedelta(days=1),
        )
        repo.save_template(template)
        if self.scenario.scenario_id == "S12_SKILL_CACHE_QUARANTINE":
            repo.quarantine_template(template.template_id, "phase8_fault")
        repo.close()

    def _cache_lookup(self) -> SkillCacheLookupResult:
        if self.config.cache_policy == CachePolicy.NO_CACHE_REUSE:
            return SkillCacheLookupResult(
                match_type="no_match", templates=[], reason_codes=["cache_reuse_disabled"]
            )
        repo = SQLiteSkillCacheRepository(
            self.config.artifact_dir / "skill-cache.sqlite3", clock=self._now
        )
        result = repo.lookup_templates(self._cache_key())
        repo.close()
        return result

    def _simulate_sqlite_restart(self, contract: TaskContract) -> None:
        db_dir = self.config.artifact_dir
        db_dir.mkdir(parents=True, exist_ok=True)
        auto_path = db_dir / "auto-mode.sqlite3"
        event_path = db_dir / "event-autonomy.sqlite3"
        auto_repo = SQLiteAutoModeRepository(auto_path, clock=self._now)
        auto_repo.save_status(
            AutoModeState(
                task_id=contract.task_id,
                current_mode=self.current_mode,
                mode_version=1,
                switch_count=self.counters.mode_switch_count,
                last_switch_at=self._now(),
                policy_version="auto-v1",
                updated_at=self._now(),
            )
        )
        auto_repo.close()
        reopened_auto = SQLiteAutoModeRepository(auto_path, clock=self._now)
        assert reopened_auto.get_status(contract.task_id) is not None
        reopened_auto.close()
        event_repo = SQLiteEventAutonomyRepository(event_path)
        event_repo.save_active_contract(
            contract,
            plan_id=f"plan-{contract.task_id}",
            robot_id="robot-phase8",
            status="ACTIVE",
        )
        event_repo.close()
        reopened_event = SQLiteEventAutonomyRepository(event_path)
        assert reopened_event.get_active_contract(contract.task_id) is not None
        reopened_event.close()
        self._record_event("sqlite_restart_recovered", contract.task_id, {"status": "ok"})

    def _terminal_pause_or_stop(self) -> bool:
        return self.world.emergency_stop or self.world.target_lost or self.world.perception_degraded

    def _build_contract(self) -> TaskContract:
        issued = self._now()
        mode = self.current_mode
        return TaskContract(
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

    def _risk_input(self, contract: TaskContract) -> RiskSnapshotInput:
        network_profile = get_network_profile(self.config.network_profile)
        latency = network_profile.base_latency_ms
        jitter = network_profile.jitter_ms
        loss = network_profile.loss_rate
        if AblationType.A2_AUTO_WITHOUT_NETWORK_SIGNAL in self.config.ablations:
            latency, jitter, loss = 20, 0, 0.0
        target_moved = self.world.target_moved
        obstacle_rate = self.world.obstacle_change_rate
        if AblationType.A3_AUTO_WITHOUT_SCENE_DYNAMICS_SIGNAL in self.config.ablations:
            target_moved, obstacle_rate = False, 0.0
        return RiskSnapshotInput(
            task_id=contract.task_id,
            task_type="pick-place",
            skill_name="GRASP",
            workspace_id="workspace_a",
            scene_version=self.world.scene_version,
            scene_updated_at=self._now(),
            scene_confidence=self.world.scene_confidence,
            target_confidence=self.world.target_confidence,
            target_moved=target_moved,
            target_lost=self.world.target_lost,
            obstacle_count=self.world.obstacle_count,
            obstacle_change_rate=obstacle_rate,
            network_latency_ms=latency,
            network_jitter_ms=jitter,
            packet_loss_rate=loss,
            disconnected_seconds=0.0 if self.network.connected else 1.0,
            last_heartbeat_at=self._now(),
            execution_failures=len(self.counters.failed_steps),
            timeout_count=0,
            replans_count=self.counters.replan_count,
            safety_rejections=self.counters.safety_reject_count,
            estop_engaged=self.world.emergency_stop,
            safety_decision="EMERGENCY_STOP" if self.world.emergency_stop else "ALLOW",
            current_mode=self.current_mode,
            has_complete_contract=True,
            remaining_steps_persisted=True,
            edge_capability_ready=True,
            cloud_available=self.world.cloud_available,
            event_autonomy_ready=True,
            supervision_available=self.world.cloud_available,
            cache_confidence=0.95 if self.config.cache_policy == CachePolicy.CACHE_ENABLED else 0.0,
            cache_match_type=self._cache_lookup().match_type,
            policy_version=self.config.risk_policy_version,
            current_time=self._now(),
        )

    def _initial_mode(self) -> ControlMode:
        if self.config.mode == ExperimentMode.PCSC:
            return ControlMode.PERIODIC_CLOUD_SUPERVISION
        if self.config.mode == ExperimentMode.ETEAC:
            return ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
        return ControlMode.PERIODIC_CLOUD_SUPERVISION

    def _accumulate_mode_time(self) -> None:
        delta = self.clock.now_ms - self._mode_started_ms
        if self.current_mode == ControlMode.PERIODIC_CLOUD_SUPERVISION:
            self.counters.time_in_pcsc_ms += max(0, delta)
        else:
            self.counters.time_in_eteac_ms += max(0, delta)
        self._mode_started_ms = self.clock.now_ms

    def _finalize_mode_time(self) -> None:
        self._accumulate_mode_time()

    def _now(self) -> datetime:
        return BASE_TIME + timedelta(milliseconds=self.clock.now_ms)

    def _record_event(self, event_type: str, entity_id: str, payload: dict[str, object]) -> None:
        event_payload = {
            "event_type": event_type,
            "entity_id": entity_id,
            "payload": payload,
            "t": self.clock.now_ms,
        }
        self.events.append(
            ExperimentEvent(
                virtual_time_ms=self.clock.now_ms,
                event_type=event_type,
                entity_id=entity_id,
                payload=dict(payload),
                payload_hash=stable_hash(event_payload),
            )
        )

    def _result_hash(self, result: ExperimentResult) -> str:
        payload = result.model_dump(mode="json")
        payload["git_sha"] = ""
        payload["result_hash"] = ""
        return stable_hash(payload)

    def _cache_key(self) -> SkillCacheKey:
        return SkillCacheKey(
            skill_name=SkillName.GRASP,
            robot_model="mock-arm-v1",
            end_effector_type="parallel_gripper",
            object_class=self.config.task_profile.object_class,
            task_intent="pick-place",
            workspace_id="workspace_a",
            parameter_schema_version="phase8.v1",
            robot_capability_hash="mock-capability-v1",
            safety_policy_hash="safety-v1",
            calibration_version="cal-v1",
        )

    def _seeded_variation_ms(self) -> int:
        return self.config.seed % 7


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
        parameters=parameters or {},
        expected_duration_ms=100,
        timeout_ms=1_000,
        retry_limit=retry_limit,
    )


def stable_run_id(
    experiment_id: str,
    scenario_id: str,
    mode: ExperimentMode,
    seed: int,
) -> str:
    return f"run-{stable_hash(_run_id_payload(experiment_id, scenario_id, mode, seed))[:16]}"


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def environment_metadata() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }


def _run_id_payload(
    experiment_id: str,
    scenario_id: str,
    mode: ExperimentMode,
    seed: int,
) -> dict[str, object]:
    return {
        "experiment_id": experiment_id,
        "scenario_id": scenario_id,
        "mode": mode.value,
        "seed": seed,
    }
