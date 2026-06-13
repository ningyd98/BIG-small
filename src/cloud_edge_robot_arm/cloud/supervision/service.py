"""PeriodicSupervisorService: the main orchestration class for PCSC.

Orchestrates the supervision cycle:
1. Receive/read edge status snapshot
2. Validate snapshot
3. Run deterministic supervision policy (Layer 1)
4. Conditionally invoke PlannerAdapter (Layer 2)
5. Generate SupervisoryDecision
6. Persist and emit audit events
7. Dispatch updated contract if needed

Key invariants:
- KEEP decisions NEVER call the planner
- plan_version strictly increases on updates
- Completed steps are never modified
- Idempotency: same input → same output within a cycle
- Concurrent supervision on the same task_id is safe
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from cloud_edge_robot_arm.cloud.planning.adapter import PlannerAdapter
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    PlanningOutcome,
    RobotCapabilities,
    SceneObjectSummary,
    SceneSummary,
    TargetRegionSummary,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.cloud.supervision.core import (
    Clock,
    DeterministicSupervisionPolicy,
    SupervisionScheduler,
    WallClock,
    compute_decision_hash,
    compute_state_hash,
)
from cloud_edge_robot_arm.cloud.supervision.models import (
    EdgeStatusSnapshot,
    SupervisionConfig,
    SupervisionReasonCode,
    SupervisoryDecision,
    SupervisoryDecisionType,
)
from cloud_edge_robot_arm.contracts import Pose, SkillName, TaskContract, TaskStep


# ── Service ──────────────────────────────────────────────────────────────────


@dataclass
class _SupervisionState:
    running: bool = False
    last_plan_version: int = 0
    last_command_seq: int = 0
    last_idempotency_keys: set[str] = field(default_factory=set)
    known_obstacle_ids: set[str] = field(default_factory=set)
    missed_cycles: int = 0
    decisions: list[SupervisoryDecision] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)


class PeriodicSupervisorService:
    """The PCSC supervisor orchestration layer.

    Usage (test):
        clock = FakeClock()
        planner = MockPlannerAdapter()
        service = PeriodicSupervisorService(
            planner=planner,
            config=SupervisionConfig(supervision_period_ms=1000),
            clock=clock,
            scheduler=TestSupervisionScheduler(),
        )
        service.start()
        decision = service.evaluate_snapshot(snapshot, contract)
    """

    def __init__(
        self,
        *,
        planner: PlannerAdapter,
        config: SupervisionConfig | None = None,
        clock: Clock | None = None,
        scheduler: SupervisionScheduler | None = None,
        runtime_profile: str = "test",
    ) -> None:
        self._planner = planner
        self._config = config or SupervisionConfig()
        self._clock = clock or WallClock()
        self._scheduler = scheduler
        self._profile = runtime_profile.strip().lower()
        self._policy = DeterministicSupervisionPolicy()
        self._state = _SupervisionState()
        self._contract_cache: dict[str, TaskContract] = {}
        self._last_target_positions: dict[str, Pose] = {}

        if self._profile == "production":
            if scheduler is None:
                raise ValueError(
                    "scheduler is required in production mode; test scheduler not allowed"
                )

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self, contract: TaskContract, initial_target: Pose | None = None) -> None:
        """Start supervision for a task."""
        self._contract_cache[contract.task_id] = contract
        self._state.running = True
        self._state.last_plan_version = contract.plan_version
        self._state.last_command_seq = contract.command_seq
        self._state.missed_cycles = 0
        if initial_target is not None:
            self._last_target_positions[contract.task_id] = initial_target
        self._emit_audit(
            "SUPERVISION_STARTED",
            contract.task_id,
            contract.plan_version,
            contract.command_seq,
        )

    def stop(self, task_id: str) -> None:
        """Stop supervision for a task."""
        self._state.running = False
        if self._scheduler:
            self._scheduler.stop()
        self._emit_audit(
            "SUPERVISION_STOPPED",
            task_id,
            self._state.last_plan_version,
            self._state.last_command_seq,
        )

    def evaluate_snapshot(
        self,
        snapshot: EdgeStatusSnapshot,
        contract: TaskContract | None = None,
    ) -> SupervisoryDecision:
        """Run one complete supervision cycle.

        Returns a SupervisoryDecision — KEEP, UPDATE, PAUSE, etc.
        """
        self._emit_audit(
            "SUPERVISION_CYCLE_STARTED",
            snapshot.task_id,
            snapshot.plan_version,
            snapshot.command_seq,
            snapshot=snapshot,
        )

        start_mono = self._clock.monotonic()

        # --- Retrieve or validate contract ---
        c = contract or self._contract_cache.get(snapshot.task_id)
        if c is None:
            return self._error_decision(
                snapshot,
                SupervisionReasonCode.SUPERVISOR_INTERNAL_ERROR,
                "no contract for task",
            )

        # --- Validate snapshot ---
        snap_err = self._validate_snapshot(snapshot, c)
        if snap_err is not None:
            self._emit_audit(
                "EDGE_STATUS_REJECTED",
                snapshot.task_id,
                snapshot.plan_version,
                snapshot.command_seq,
                reason=snap_err,
                snapshot=snapshot,
            )
            return self._error_decision(
                snapshot,
                SupervisionReasonCode.EDGE_STATE_STALE,
                snap_err,
            )

        self._emit_audit(
            "EDGE_STATUS_RECEIVED",
            snapshot.task_id,
            snapshot.plan_version,
            snapshot.command_seq,
            snapshot=snapshot,
        )

        # --- Idempotency check ---
        state_hash = compute_state_hash(snapshot)
        if state_hash in self._state.last_idempotency_keys:
            # Same input → return cached decision
            for d in reversed(self._state.decisions):
                if d.input_state_hash == state_hash:
                    return d

        # --- Track target position for change detection ---
        current_target = self._extract_target_pose(snapshot)
        displacement = 0.0
        if current_target is not None and snapshot.task_id in self._last_target_positions:
            prev = self._last_target_positions[snapshot.task_id]
            displacement = current_target.distance_xy_to(prev)
        if current_target is not None:
            self._last_target_positions[snapshot.task_id] = current_target

        # --- Run Layer 1: Deterministic supervision ---
        decision_type, reason_code, detail, should_plan = self._policy.evaluate(
            snapshot, c, self._config, self._state.known_obstacle_ids
        )

        # --- Override: target displacement (tracked via positions) ---
        if displacement > self._config.target_displacement_threshold_m:
            current_idx = DeterministicSupervisionPolicy._step_index(
                c, snapshot.current_step_id
            )
            if current_idx is not None and current_idx < len(c.steps):
                decision_type = SupervisoryDecisionType.UPDATE_CURRENT_STEP
                reason_code = SupervisionReasonCode.TARGET_MOVED_CURRENT_STEP
                detail = f"target moved {displacement:.3f}m"
                should_plan = True

        self._emit_audit(
            "SUPERVISION_STATE_EVALUATED",
            snapshot.task_id,
            c.plan_version,
            c.command_seq,
            decision=decision_type.value,
            reason_code=reason_code.value,
            should_invoke_planner=should_plan,
        )

        # --- Layer 2: Conditional planner invocation ---
        planner_invoked = False
        updated_contract: TaskContract | None = None
        prompt_version: str | None = None

        if should_plan and decision_type in {
            SupervisoryDecisionType.UPDATE_CURRENT_STEP,
            SupervisoryDecisionType.REPLACE_REMAINING_STEPS,
        }:
            self._emit_audit(
                "SUPERVISION_REPLAN_REQUESTED",
                snapshot.task_id,
                c.plan_version,
                c.command_seq,
                reason_code=reason_code.value,
            )
            try:
                scene = self._build_scene_from_snapshot(snapshot)
                p_req = InitialPlanningRequest(
                    request_id=f"supervise-{snapshot.task_id}-{uuid.uuid4().hex[:8]}",
                    user_instruction=c.user_instruction,
                    control_mode="PERIODIC_CLOUD_SUPERVISION",
                    scene=scene,
                    capabilities=RobotCapabilities(
                        supported_skills=[s.value for s in SkillName]
                    ),
                    completed_step_ids=snapshot.completed_step_ids,
                    failed_step_id=snapshot.current_step_id,
                )
                pipeline = PlanningPipeline(planner=self._planner)
                result = pipeline.process(p_req)
                if result.outcome == PlanningOutcome.PLANNED and result.contract:
                    updated_contract = result.contract
                    planner_invoked = True
                    prompt_version = "1.0"
                    self._emit_audit(
                        "SUPERVISION_PLAN_UPDATED",
                        snapshot.task_id,
                        updated_contract.plan_version,
                        updated_contract.command_seq,
                        reason_code=reason_code.value,
                    )
                else:
                    self._emit_audit(
                        "SUPERVISION_CYCLE_FAILED",
                        snapshot.task_id,
                        c.plan_version,
                        c.command_seq,
                        reason=f"replan failed: {result.outcome.value}",
                    )
            except Exception as exc:
                self._emit_audit(
                    "SUPERVISION_CYCLE_FAILED",
                    snapshot.task_id,
                    c.plan_version,
                    c.command_seq,
                    reason=f"planner exception: {exc}",
                )
        elif decision_type == SupervisoryDecisionType.KEEP_CURRENT_PLAN:
            self._emit_audit(
                "SUPERVISION_KEEP_SELECTED",
                snapshot.task_id,
                c.plan_version,
                c.command_seq,
                reason_code=reason_code.value,
            )

        # --- Build decision ---
        new_plan_version = c.plan_version
        new_command_seq = c.command_seq
        updated_steps: list[TaskStep] = []

        if updated_contract is not None:
            new_plan_version = max(c.plan_version + 1, updated_contract.plan_version)
            new_command_seq = c.command_seq + 1
            updated_steps = list(updated_contract.steps)
        elif decision_type == SupervisoryDecisionType.KEEP_CURRENT_PLAN:
            new_plan_version = c.plan_version
            new_command_seq = c.command_seq

        now = self._clock.now()
        ttl = self._config.command_ttl_ms
        decision_id = f"dec-{uuid.uuid4().hex[:12]}"
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"

        decision = SupervisoryDecision(
            decision_id=decision_id,
            task_id=snapshot.task_id,
            robot_id=snapshot.robot_id,
            based_on_plan_version=c.plan_version,
            resulting_plan_version=new_plan_version,
            command_seq=new_command_seq,
            previous_command_seq=c.command_seq,
            decision=decision_type,
            reason_code=reason_code,
            reason_detail=detail,
            edge_state_timestamp=snapshot.timestamp,
            cloud_decision_timestamp=now,
            scene_version=snapshot.scene_version,
            valid_until=now + timedelta(milliseconds=ttl),
            command_ttl_ms=ttl,
            updated_steps=updated_steps,
            planner_invoked=planner_invoked,
            planner_adapter=self._planner.planner_name if planner_invoked else None,
            prompt_version=prompt_version,
            policy_version="1.0",
            policy_hash="",
            correlation_id=correlation_id,
            idempotency_key=state_hash,
            input_state_hash=state_hash,
            cycle_latency_ms=int((self._clock.monotonic() - start_mono) * 1_000),
        )
        decision.output_decision_hash = compute_decision_hash(decision)

        # --- Persist ---
        self._state.decisions.append(decision)
        self._state.last_idempotency_keys.add(state_hash)
        if updated_contract:
            self._contract_cache[snapshot.task_id] = updated_contract
            self._state.last_plan_version = new_plan_version
            self._state.last_command_seq = new_command_seq

        self._emit_audit(
            "SUPERVISION_DECISION_CREATED",
            snapshot.task_id,
            new_plan_version,
            new_command_seq,
            decision_id=decision_id,
            decision_type=decision_type.value,
            reason_code=reason_code.value,
            planner_invoked=planner_invoked,
        )

        return decision

    # ── Helpers ────────────────────────────────────────────────────────────

    def _validate_snapshot(
        self,
        snapshot: EdgeStatusSnapshot,
        contract: TaskContract,
    ) -> str | None:
        """Validate snapshot consistency; return error message or None."""
        # Robot/task mismatch
        if snapshot.task_id != contract.task_id:
            return "task_id mismatch"

        # Timestamp sanity: not from the future
        now = self._clock.now()
        if snapshot.timestamp > now + timedelta(seconds=10):
            return "snapshot timestamp is in the future"

        # Staleness
        age_ms = int((now - snapshot.timestamp).total_seconds() * 1_000)
        if age_ms > self._config.stale_state_threshold_ms:
            return f"snapshot is stale ({age_ms}ms > {self._config.stale_state_threshold_ms}ms)"

        # plan_version cannot exceed cloud known version
        if snapshot.plan_version > contract.plan_version:
            return f"edge plan_version {snapshot.plan_version} > cloud {contract.plan_version}"

        # Completed steps should not regress
        contract_step_ids = {s.step_id for s in contract.steps}
        for sid in snapshot.completed_step_ids:
            if sid not in contract_step_ids:
                return f"completed step {sid!r} not in contract"

        # current_step_id must belong to contract
        if snapshot.current_step_id and snapshot.current_step_id not in contract_step_ids:
            return f"current_step_id {snapshot.current_step_id!r} not in contract"

        return None

    def _build_scene_from_snapshot(self, snapshot: EdgeStatusSnapshot) -> SceneSummary:
        """Construct a SceneSummary from an edge snapshot."""
        objects: list[SceneObjectSummary] = []
        ts_raw = snapshot.target_state
        if ts_raw:
            obj_id = ts_raw.get("object_id", "target")
            obj_cls = ts_raw.get("object_class", "unknown")
            pose_raw = ts_raw.get("pose")
            pose = None
            if isinstance(pose_raw, dict):
                pose = Pose(
                    x=float(pose_raw.get("x", 0)),
                    y=float(pose_raw.get("y", 0)),
                    z=float(pose_raw.get("z", 0)),
                )
            elif "x" in ts_raw and "y" in ts_raw:
                pose = Pose(
                    x=float(ts_raw.get("x", 0)),
                    y=float(ts_raw.get("y", 0)),
                    z=float(ts_raw.get("z", 0)),
                )
            objects.append(
                SceneObjectSummary(
                    object_id=obj_id,
                    object_class=obj_cls,
                    pose=pose,
                    pose_confidence=snapshot.scene_confidence,
                )
            )

        regions: list[TargetRegionSummary] = []
        if ts_raw and "region_id" in ts_raw:
            rid = ts_raw.get("region_id", "target_region")
            center_raw = ts_raw.get("region_center")
            center = Pose(x=0, y=0, z=0.02)
            if isinstance(center_raw, dict):
                center = Pose(
                    x=float(center_raw.get("x", 0)),
                    y=float(center_raw.get("y", 0)),
                    z=float(center_raw.get("z", 0.02)),
                )
            regions.append(TargetRegionSummary(region_id=rid, center=center))

        return SceneSummary(
            scene_version=snapshot.scene_version,
            updated_at=snapshot.timestamp,
            objects=objects,
            regions=regions,
            scene_confidence=snapshot.scene_confidence,
        )

    def _error_decision(
        self,
        snapshot: EdgeStatusSnapshot,
        reason_code: SupervisionReasonCode,
        detail: str,
    ) -> SupervisoryDecision:
        now = self._clock.now()
        return SupervisoryDecision(
            decision_id=f"err-{uuid.uuid4().hex[:12]}",
            task_id=snapshot.task_id,
            robot_id=snapshot.robot_id,
            based_on_plan_version=snapshot.plan_version,
            resulting_plan_version=snapshot.plan_version,
            command_seq=snapshot.command_seq,
            previous_command_seq=snapshot.command_seq,
            decision=SupervisoryDecisionType.REQUEST_MORE_OBSERVATION,
            reason_code=reason_code,
            reason_detail=detail,
            edge_state_timestamp=snapshot.timestamp,
            cloud_decision_timestamp=now,
            scene_version=snapshot.scene_version,
            valid_until=now + timedelta(milliseconds=self._config.command_ttl_ms),
            command_ttl_ms=self._config.command_ttl_ms,
            correlation_id=f"err-corr-{uuid.uuid4().hex[:12]}",
        )

    def _emit_audit(
        self,
        event_type: str,
        task_id: str,
        plan_version: int,
        command_seq: int,
        **extra: object,
    ) -> None:
        event: dict[str, Any] = {
            "event_type": event_type,
            "task_id": task_id,
            "plan_version": plan_version,
            "command_seq": command_seq,
            "timestamp": self._clock.now().isoformat(),
        }
        event.update(extra)
        self._state.audit_events.append(event)

    @staticmethod
    def _extract_target_pose(snapshot: EdgeStatusSnapshot) -> Pose | None:
        ts = snapshot.target_state
        if "pose" in ts:
            p = ts["pose"]
            if isinstance(p, dict):
                return Pose(x=float(p.get("x", 0)), y=float(p.get("y", 0)), z=float(p.get("z", 0)))
        if "x" in ts and "y" in ts:
            return Pose(x=float(ts.get("x", 0)), y=float(ts.get("y", 0)), z=float(ts.get("z", 0)))
        return None

    # ── Query methods ──────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._state.running

    @property
    def decision_count(self) -> int:
        return len(self._state.decisions)

    @property
    def planner_invocation_count(self) -> int:
        return sum(1 for d in self._state.decisions if d.planner_invoked)

    def decisions_for_task(self, task_id: str) -> list[SupervisoryDecision]:
        return [d for d in self._state.decisions if d.task_id == task_id]

    def last_decision(self) -> SupervisoryDecision | None:
        return self._state.decisions[-1] if self._state.decisions else None

    def audit_events(self) -> list[dict[str, Any]]:
        return list(self._state.audit_events)
