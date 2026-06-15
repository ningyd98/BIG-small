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
)
from cloud_edge_robot_arm.auto_mode.selector import AutoModeSelector
from cloud_edge_robot_arm.contracts import (
    AutoModeDecisionType,
    ControlMode,
    RiskLevel,
    SkillName,
    TaskContract,
)
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutionResult
from cloud_edge_robot_arm.experiments.metrics import ExperimentCounters
from cloud_edge_robot_arm.experiments.metrics_collector import ExperimentMetricsCollector
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
from cloud_edge_robot_arm.experiments.runtime_harness import RuntimeExperimentHarness
from cloud_edge_robot_arm.experiments.scenario import get_scenario
from cloud_edge_robot_arm.risk.evaluator import RiskEvaluator
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput
from cloud_edge_robot_arm.simulation.clock import VirtualClock
from cloud_edge_robot_arm.simulation.fault_injection import FaultInjector
from cloud_edge_robot_arm.simulation.mock_robot import FaultCode
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
        self.harness = RuntimeExperimentHarness(
            config=config,
            clock=self.clock,
            world=self.world,
        )
        self._last_task_result: TaskExecutionResult | None = None
        self._active_contract: TaskContract | None = None
        self._pending_restart_crash_points: list[str] = []
        self._harness_event_cursor = 0

    def run_once(self) -> ExperimentResult:
        return self.run().result

    def run(self) -> ExperimentExecution:
        self._record_event("run_started", self.config.experiment_id, {"seed": self.config.seed})
        contract = self.harness.create_contract()
        self._prime_cache_if_needed()
        self._schedule_faults()
        self._execute_scenario(contract)
        result = self._build_result()
        self._record_event("run_completed", result.run_id, {"status": result.result_status.value})
        result = result.model_copy(update={"event_count": len(self.events)}, deep=True)
        result = result.model_copy(update={"result_hash": self._result_hash(result)}, deep=True)
        return ExperimentExecution(result=result, events=list(self.events))

    def _execute_scenario(self, contract: TaskContract) -> None:
        self._active_contract = contract
        self._apply_immediate_scenario_effects()
        if self.config.mode == ExperimentMode.AUTO:
            if self._scenario_has_fault(FaultType.EMERGENCY_STOP):
                self._record_event(
                    "auto_decision_deferred",
                    contract.task_id,
                    {"reason": "emergency_stop_fault_profile"},
                )
            else:
                self._run_auto_decision(contract)
        contract = self._contract_for_current_mode(contract)
        self._active_contract = contract
        if self.scenario.scenario_id == "S15_SQLITE_RESTART_DURING_RUN":
            self._simulate_sqlite_restart(contract, crash_point="C1_ACTIVE_CONTRACT_SAVED")
        if self.scenario.scenario_id == "S10_STALE_DUPLICATE_REORDERED_COMMAND":
            self._exercise_command_ingress(contract)
            contract = self._fresh_execution_contract_after_ingress(contract)
            self._active_contract = contract
        if self.scenario.scenario_id == "S12_SKILL_CACHE_QUARANTINE":
            self.counters.cache_quarantine_count = 1
            self.counters.cache_hit_count = 0
            self._record_event(
                "cache_quarantined", contract.task_id, {"template_id": "tmpl-phase8"}
            )

        if self.current_mode == ControlMode.PERIODIC_CLOUD_SUPERVISION:
            self._run_pcsc_tick(contract)

        result = self.harness.submit_contract(contract)
        self._active_contract = contract
        self._last_task_result = result
        self._import_harness_events()
        self._apply_pending_restarts(contract)
        if (
            not result.success
            and result.error is not None
            and result.error.code == "CLOUD_REPLAN_REQUIRED"
        ):
            self._process_eteac_cloud_replan(contract)
            self._import_harness_events()

        self._sync_counters_from_runtime(contract)
        self._finalize_mode_time()
        self._sort_events()

    def _run_auto_decision(self, contract: TaskContract) -> None:
        risk_input = self._risk_input(contract)
        risk_snapshot = RiskEvaluator(
            policy=RiskPolicy(version=self.config.risk_policy_version),
            clock=self._now,
        ).evaluate(risk_input)
        self.harness.save_risk_snapshot(risk_snapshot)
        self._record_event(
            "risk_snapshot_saved",
            risk_snapshot.snapshot_id,
            {"risk_level": risk_snapshot.risk_level.value, "score": risk_snapshot.total_score},
        )
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
        self.harness.save_auto_decision(decision)
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
        transition = self.harness.prepare_mode_transition(
            task_id=task_id,
            to_mode=selected_mode,
            decision_id=decision_id,
            reason="phase8_auto_selection",
        )
        self._record_event(
            "mode_transition_prepared",
            transition.transition_id,
            {"from_mode": transition.from_mode.value, "to_mode": selected_mode.value},
        )
        committed = self.harness.commit_mode_transition(transition.transition_id)
        self.current_mode = self.harness.current_mode
        self.counters.mode_switch_count += 1
        self._record_event(
            "mode_transition_committed",
            committed.transition_id,
            {"from_mode": committed.from_mode.value, "to_mode": committed.to_mode.value},
        )

    def _contract_for_current_mode(self, contract: TaskContract) -> TaskContract:
        now = self._now()
        return contract.model_copy(
            update={
                "control_mode": self.current_mode,
                "timestamp": now,
                "issued_at": now,
                "valid_until": now + timedelta(milliseconds=self.config.timeout_ms),
            },
            deep=True,
        )

    def _exercise_command_ingress(self, contract: TaskContract) -> None:
        accepted = self.harness.deliver_cloud_command(contract, request_id="s10-accepted")
        now = self._now()
        stale_seq = contract.model_copy(
            update={
                "command_seq": contract.command_seq,
                "plan_version": contract.plan_version + 1,
                "timestamp": now,
                "issued_at": now,
                "valid_until": now + timedelta(milliseconds=self.config.timeout_ms),
            },
            deep=True,
        )
        commands = [
            (
                "s10-expired",
                contract.model_copy(
                    update={
                        "command_seq": contract.command_seq + 1,
                        "timestamp": now,
                        "issued_at": now,
                        "valid_until": now,
                    },
                    deep=True,
                ),
            ),
            ("s10-duplicate", contract),
            (
                "s10-conflict",
                contract.model_copy(update={"user_instruction": "changed by conflict"}, deep=True),
            ),
            ("s10-stale-seq", stale_seq),
            (
                "s10-stale-plan",
                contract.model_copy(
                    update={
                        "command_seq": contract.command_seq + 2,
                        "plan_version": 0,
                        "timestamp": now,
                        "issued_at": now,
                        "valid_until": now + timedelta(milliseconds=self.config.timeout_ms),
                    },
                    deep=True,
                ),
            ),
            (
                "s10-newer-out-of-order",
                contract.model_copy(
                    update={
                        "command_seq": contract.command_seq + 4,
                        "plan_version": contract.plan_version + 1,
                        "previous_command_seq": contract.command_seq,
                        "timestamp": now,
                        "issued_at": now,
                        "valid_until": now + timedelta(milliseconds=self.config.timeout_ms),
                    },
                    deep=True,
                ),
            ),
            (
                "s10-older-after-newer",
                contract.model_copy(
                    update={
                        "command_seq": contract.command_seq + 3,
                        "plan_version": contract.plan_version + 1,
                        "previous_command_seq": contract.command_seq,
                        "timestamp": now,
                        "issued_at": now,
                        "valid_until": now + timedelta(milliseconds=self.config.timeout_ms),
                    },
                    deep=True,
                ),
            ),
            (
                "s10-scene-mismatch",
                contract.model_copy(
                    update={
                        "command_seq": contract.command_seq + 5,
                        "plan_version": contract.plan_version + 2,
                        "scene_version": contract.expected_scene_version + 1,
                        "timestamp": now,
                        "issued_at": now,
                        "valid_until": now + timedelta(milliseconds=self.config.timeout_ms),
                    },
                    deep=True,
                ),
            ),
        ]
        self._record_event(
            "command_ingress_started",
            contract.task_id,
            {"accepted_status": accepted.status, "accepted": accepted.accepted},
        )
        for request_id, command in commands:
            self.harness.deliver_cloud_command(command, request_id=request_id)
        self._import_harness_events()

    def _fresh_execution_contract_after_ingress(self, contract: TaskContract) -> TaskContract:
        now = self._now()
        return contract.model_copy(
            update={
                "command_seq": contract.command_seq + 6,
                "previous_command_seq": contract.command_seq + 4,
                "plan_version": contract.plan_version + 2,
                "control_mode": self.current_mode,
                "timestamp": now,
                "issued_at": now,
                "valid_until": now + timedelta(milliseconds=self.config.timeout_ms),
            },
            deep=True,
        )

    def _run_pcsc_tick(self, contract: TaskContract) -> None:
        sent_at = self.clock.now_ms
        decision = self.harness.run_supervision_tick(contract)
        payload = {
            "decision": getattr(getattr(decision, "decision", ""), "value", ""),
            "reason_code": getattr(getattr(decision, "reason_code", ""), "value", ""),
            "planner_invoked": bool(getattr(decision, "planner_invoked", False)),
            "resulting_plan_version": int(getattr(decision, "resulting_plan_version", 0)),
            "command_seq": int(getattr(decision, "command_seq", 0)),
        }
        payload_size = len(stable_hash(payload).encode("utf-8")) + len(str(payload).encode("utf-8"))
        self._record_event("supervisory_decision", contract.task_id, payload)
        if payload["planner_invoked"]:
            self._record_event(
                "cloud_invocation",
                contract.task_id,
                {"source": "PeriodicSupervisorService"},
            )

        def on_deliver(message: NetworkMessage) -> None:
            self._record_event(
                "network_delivered",
                message.message_id,
                {
                    "channel": message.channel,
                    "latency_ms": self.clock.now_ms - sent_at,
                    "payload_size_bytes": message.payload_size_bytes,
                },
            )

        accepted = self.network.send(
            NetworkMessage(
                message_id=f"pcsc-{self.config.experiment_id}-{self.config.seed}-{sent_at}",
                channel="cloud-edge",
                payload_size_bytes=payload_size,
            ),
            on_deliver,
        )
        if not accepted:
            self._record_event(
                "network_dropped",
                contract.task_id,
                {"channel": "cloud-edge", "payload_size_bytes": payload_size},
            )

    def _process_eteac_cloud_replan(self, contract: TaskContract) -> None:
        messages = self.harness.event_repo.list_pending_outbox(contract.task_id)
        request_ids = [message.request_id for message in messages if message.request_id]
        if not request_ids:
            return
        request = self.harness.event_repo.get_replan_request(request_ids[-1])
        if request is None:
            return
        response, applied = self.harness.replanning.process_and_apply(request, dispatch=False)
        self._record_event(
            "cloud_invocation",
            contract.task_id,
            {"source": "LocalReplanningService", "request_id": request.request_id},
        )
        if response.outcome == "REPLANNED":
            self._record_event(
                "replan_proposal_saved",
                request.request_id,
                {
                    "outcome": response.outcome,
                    "new_plan_version": response.new_plan_version,
                    "new_command_seq": response.new_command_seq,
                },
            )
        if applied is not None:
            self._record_event(
                "replan_applied",
                request.request_id,
                {
                    "applied": applied.applied,
                    "status": applied.record.status,
                    "ack_status": "" if applied.ack is None else applied.ack.status,
                },
            )
            if applied.applied and applied.contract is not None:
                checkpoint = self.harness.event_repo.get_latest_execution_checkpoint(
                    contract.task_id
                )
                if checkpoint is not None:
                    resumed = self.harness.executor.resume_from_checkpoint(
                        applied.contract,
                        checkpoint,
                    )
                    self._last_task_result = resumed

    def _import_harness_events(self) -> None:
        raw_events = self.harness.observer.events[self._harness_event_cursor :]
        self._harness_event_cursor = len(self.harness.observer.events)
        for raw in raw_events:
            payload = raw.get("payload", {})
            event_payload = payload if isinstance(payload, dict) else {"payload": str(payload)}
            virtual_time = _payload_int(raw.get("virtual_time_ms"), default=self.clock.now_ms)
            event_type = str(raw.get("event_type", "unknown"))
            entity_id = str(raw.get("entity_id", ""))
            self.events.append(
                ExperimentEvent(
                    virtual_time_ms=virtual_time,
                    event_type=event_type,
                    entity_id=entity_id,
                    payload=dict(event_payload),
                    payload_hash=stable_hash(
                        {
                            "event_type": event_type,
                            "entity_id": entity_id,
                            "payload": event_payload,
                            "t": virtual_time,
                        }
                    ),
                )
            )
        self._sort_events()

    def _sync_counters_from_runtime(self, contract: TaskContract) -> None:
        cache_hit = self.counters.cache_hit_count
        cache_miss = self.counters.cache_miss_count
        cache_quarantine = self.counters.cache_quarantine_count
        trusted = self.counters.trusted_template_execution_count
        time_pcsc = self.counters.time_in_pcsc_ms
        time_eteac = self.counters.time_in_eteac_ms
        unsafe_counterfactual = self.counters.unsafe_counterfactual_count
        mode_switch_count = self.counters.mode_switch_count
        counterfactual_count = self.counters.unsafe_counterfactual_count
        self.counters = ExperimentCounters(
            cache_hit_count=cache_hit,
            cache_miss_count=cache_miss,
            cache_quarantine_count=cache_quarantine,
            trusted_template_execution_count=trusted,
            time_in_pcsc_ms=time_pcsc,
            time_in_eteac_ms=time_eteac,
            unsafe_counterfactual_count=unsafe_counterfactual,
            mode_switch_count=mode_switch_count,
        )
        metrics = ExperimentMetricsCollector.from_events(self.events).collect()
        self.counters.safety_allow_count = metrics.safety_allow_count
        self.counters.safety_allow_with_limits_count = metrics.safety_allow_with_limits_count
        self.counters.safety_pause_count = metrics.safety_pause_count
        self.counters.safety_reject_count = metrics.safety_reject_count
        self.counters.emergency_stop_count = metrics.emergency_stop_count
        self.counters.stale_command_rejection_count = metrics.stale_command_rejection_count
        self.counters.duplicate_command_rejection_count = metrics.duplicate_command_rejection_count
        self.counters.reordered_command_rejection_count = metrics.reordered_command_rejection_count
        self.counters.cloud_invocation_count = metrics.cloud_invocation_count
        self.counters.supervisory_decision_count = metrics.supervisory_decision_count
        self.counters.replan_count = metrics.replan_count

        records = self.harness.step_execution_records(contract.task_id)
        if records:
            self.counters.completed_steps = [record.step_id for record in records if record.success]
            self.counters.failed_steps = [
                record.step_id for record in records if not record.success
            ]
        else:
            self.counters.completed_steps = [
                event.entity_id for event in self.events if event.event_type == "step_completed"
            ]
            self.counters.failed_steps = [
                event.entity_id
                for event in self.events
                if event.event_type in {"step_failed", "step_rejected", "step_paused"}
            ]
        for record in records:
            self.counters.step_attempts[record.step_id] = max(
                self.counters.step_attempts.get(record.step_id, 0),
                int(record.attempt),
            )
        if not records:
            for event in self.events:
                if event.event_type not in {
                    "step_completed",
                    "step_failed",
                    "step_rejected",
                    "step_paused",
                }:
                    continue
                self.counters.step_attempts[event.entity_id] = max(
                    self.counters.step_attempts.get(event.entity_id, 0),
                    _payload_int(event.payload.get("attempt"), default=1),
                )
        self.counters.local_retry_count = sum(
            1 for record in records if int(record.attempt) > 1 and record.success
        )
        self.counters.command_count = len(self.harness.accepted_command_records(contract.task_id))
        self.counters.telemetry_count = len(
            [event for event in self.events if event.event_type == "step_completed"]
        )
        self.counters.simulated_collision_count = (
            1 if self.harness.robot.get_state().collision_detected else 0
        )
        self.counters.unsafe_counterfactual_count = counterfactual_count + sum(
            1 for event in self.events if event.event_type == "safety_counterfactual"
        )
        self._derive_fault_latencies()

    def _derive_fault_latencies(self) -> None:
        first_fault_by_type: dict[str, int] = {}
        first_detection_after_fault: int | None = None
        first_recovery_after_fault: int | None = None
        for event in self.events:
            if event.event_type == "fault_injected":
                fault_type = str(event.payload.get("fault_type", ""))
                first_fault_by_type.setdefault(fault_type, event.virtual_time_ms)
            elif first_fault_by_type and event.event_type == "fault_detected":
                first_detection_after_fault = event.virtual_time_ms
            elif first_fault_by_type and event.event_type in {
                "step_completed",
                "replan_applied",
                "network_delivered",
            }:
                first_recovery_after_fault = event.virtual_time_ms
        if first_fault_by_type and first_detection_after_fault is not None:
            injected_at = min(first_fault_by_type.values())
            self.counters.fault_detection_latency_ms = max(
                0, first_detection_after_fault - injected_at
            )
        if first_fault_by_type and first_recovery_after_fault is not None:
            injected_at = min(first_fault_by_type.values())
            self.counters.recovery_latency_ms = max(0, first_recovery_after_fault - injected_at)
            self.counters.recovery_success = True
        if "CLOUD_UNAVAILABLE" in first_fault_by_type:
            self.counters.cloud_response_latency_ms = get_network_profile(
                self.config.network_profile
            ).cloud_timeout_ms

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
        if self._last_task_result is not None:
            if self._last_task_result.success:
                return ResultStatus.SUCCESS
            if self._last_task_result.error is not None:
                if self._last_task_result.error.code in {
                    "SAFETY_EMERGENCY_STOP",
                    "EMERGENCY_STOP_ACTIVE",
                    "SAFETY_STOP_EVENT",
                }:
                    return ResultStatus.SAFETY_STOPPED
                if self._last_task_result.error.code in {
                    "TASK_PAUSED_EVENT_CONTROLLER",
                    "COMPLETION_EVALUATION_FAILED",
                    "SAFETY_ACTION_REJECTED",
                    "SAFETY_REQUEST_CORRECTION",
                    "CLOUD_REPLAN_REQUIRED",
                }:
                    return ResultStatus.NEEDS_OBSERVATION
            return ResultStatus.FAILED
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
        return self.counters.cloud_invocation_count

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
        if fault_type == FaultType.GRASP_FAILURE:
            failures = int(getattr(fault, "parameters", {}).get("failures", 1))  # type: ignore[union-attr]
            self.harness.robot.inject_fault(FaultCode.GRASP_FAILED, count=max(1, failures))
        elif fault_type == FaultType.EMERGENCY_STOP:
            self.harness.robot.inject_fault(FaultCode.EMERGENCY_STOP_ACTIVE, count=1)
        elif fault_type == FaultType.SQLITE_RESTART:
            self._pending_restart_crash_points.append("C9_CHECKPOINT_UPDATED")
        if fault_type == FaultType.STALE_DUPLICATE_REORDERED_COMMAND:
            self._record_event(
                "command_fault_triggered",
                fault.fault_id,  # type: ignore[attr-defined]
                {"fault_type": fault_type.value},
            )
        self._record_event(
            "fault_injected",
            fault.fault_id,  # type: ignore[attr-defined]
            {
                "fault_type": fault_type.value,
                "trigger_time_ms": getattr(fault, "trigger_time_ms", self.clock.now_ms),
            },
        )
        self._record_event(
            "fault_detected",
            fault.fault_id,  # type: ignore[attr-defined]
            {"fault_type": fault_type.value},
        )
        if (
            fault_type == FaultType.OBSTACLE_INSERTED
            and AblationType.A7_SAFETY_SHADOW_COUNTERFACTUAL in self.config.ablations
        ):
            self._record_event(
                "safety_counterfactual",
                fault.fault_id,  # type: ignore[attr-defined]
                {
                    "metric_kind": "counterfactual",
                    "would_enter_execution_without_safety": True,
                    "fault_type": fault_type.value,
                },
            )

    def _apply_pending_restarts(self, contract: TaskContract) -> None:
        while self._pending_restart_crash_points:
            crash_point = self._pending_restart_crash_points.pop(0)
            self._simulate_sqlite_restart(contract, crash_point=crash_point)

    def _scenario_has_fault(self, fault_type: FaultType) -> bool:
        return any(fault.fault_type == fault_type for fault in self.scenario.scheduled_faults)

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

    def _simulate_sqlite_restart(self, contract: TaskContract | None, *, crash_point: str) -> None:
        if contract is not None:
            self.harness.event_repo.save_active_contract(
                contract,
                plan_id=f"plan-{contract.task_id}",
                robot_id="robot-unknown",
                status="ACTIVE",
            )
            self.harness.auto_repo.save_status(
                AutoModeState(
                    task_id=contract.task_id,
                    current_mode=self.current_mode,
                    mode_version=1 + self.counters.mode_switch_count,
                    switch_count=self.counters.mode_switch_count,
                    last_switch_at=self._now(),
                    policy_version="auto-v1",
                    updated_at=self._now(),
                )
            )
        self._record_event(
            "sqlite_crash_point",
            "" if contract is None else contract.task_id,
            {"crash_point": crash_point},
        )
        self.harness.restart_runtime()
        self._import_harness_events()
        self.current_mode = self.harness.current_mode if contract is not None else self.current_mode
        self._record_event(
            "sqlite_restart_recovered",
            "" if contract is None else contract.task_id,
            {"crash_point": crash_point, "status": "ok"},
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

    def _sort_events(self) -> None:
        indexed = list(enumerate(self.events))
        indexed.sort(key=lambda item: (item[1].virtual_time_ms, item[0]))
        self.events = [event for _, event in indexed]

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


def stable_run_id(
    experiment_id: str,
    scenario_id: str,
    mode: ExperimentMode,
    seed: int,
) -> str:
    return f"run-{stable_hash(_run_id_payload(experiment_id, scenario_id, mode, seed))[:16]}"


def _payload_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


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
