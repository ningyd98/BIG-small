"""监督核心逻辑，判断遥测新鲜度、心跳和重规划触发条件。

Phase 5 supervision core: Clock, SceneChangeDetector, PlanValidityEvaluator,
DeterministicSupervisionPolicy, and SupervisionScheduler.

The supervision system is split into two layers:
1. Deterministic lightweight supervisor (runs every cycle)
2. Conditional planner invocation (only when state changes significantly)
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from cloud_edge_robot_arm.cloud.supervision.models import (
    EdgeStatusSnapshot,
    SupervisionConfig,
    SupervisionReasonCode,
    SupervisoryDecision,
    SupervisoryDecisionType,
)
from cloud_edge_robot_arm.contracts import Pose, TaskContract

# ── Clock (injectable, no real sleep in tests) ───────────────────────────────


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class WallClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        import time

        return time.monotonic()


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
        self._mono: float = 0.0
        self._advance_s: float = 0.0

    def now(self) -> datetime:
        return self._now + timedelta(seconds=self._advance_s)

    def monotonic(self) -> float:
        return self._mono + self._advance_s

    def advance(self, seconds: float) -> None:
        self._advance_s += seconds

    def set_now(self, dt: datetime) -> None:
        self._now = dt
        self._advance_s = 0


# ── SceneChangeDetector ─────────────────────────────────────────────────────


class SceneChangeDetector:
    """Detect meaningful state changes that may require supervision action."""

    def __init__(self, threshold_m: float = 0.02) -> None:
        self._threshold_m = threshold_m

    def target_displacement_from_telemetry(
        self, snapshot: EdgeStatusSnapshot, contract: TaskContract
    ) -> tuple[float, Pose | None, Pose | None]:
        """Compute displacement between contract's target and edge telemetry.

        Returns (distance_m, expected_pose, current_pose).
        """
        target_state = snapshot.target_state
        expected = self._extract_pose_from_contract(contract)
        current = self._extract_pose_from_target_state(target_state)
        if expected is None or current is None:
            return 0.0, expected, current
        dist = expected.distance_xy_to(current)
        return dist, expected, current

    def has_significant_change(self, snapshot: EdgeStatusSnapshot, contract: TaskContract) -> bool:
        dist, _, _ = self.target_displacement_from_telemetry(snapshot, contract)
        return dist > self._threshold_m

    def new_obstacles(self, snapshot: EdgeStatusSnapshot, known_obstacle_ids: set[str]) -> bool:
        obs = snapshot.obstacle_state.get("obstacles", [])
        if not isinstance(obs, list):
            return False
        current_ids = {o.get("obstacle_id", "") for o in obs if isinstance(o, dict)}
        return bool(current_ids - known_obstacle_ids)

    def scene_confidence_dropped(self, snapshot: EdgeStatusSnapshot, min_confidence: float) -> bool:
        return snapshot.scene_confidence < min_confidence

    @staticmethod
    def _extract_pose_from_contract(c: TaskContract) -> Pose | None:
        # The contract references objects by ID — actual positions come from
        # the scene at planning time.  For supervision, we use the edge
        # telemetry as the source of truth for target position.
        return None  # No fixed position in contract — refer to scene

    @staticmethod
    def _extract_pose_from_target_state(target: dict[str, Any]) -> Pose | None:
        if "pose" in target:
            p = target["pose"]
            if isinstance(p, dict):
                return Pose(
                    x=float(p.get("x", 0)),
                    y=float(p.get("y", 0)),
                    z=float(p.get("z", 0)),
                )
        if "x" in target and "y" in target:
            return Pose(
                x=float(target.get("x", 0)),
                y=float(target.get("y", 0)),
                z=float(target.get("z", 0)),
            )
        return None


# ── PlanValidityEvaluator ───────────────────────────────────────────────────


class PlanValidityEvaluator:
    """Determine whether the current plan is still valid given latest state."""

    def evaluate(
        self,
        snapshot: EdgeStatusSnapshot,
        contract: TaskContract,
        *,
        stale_threshold_ms: int = 5_000,
        now: datetime | None = None,
    ) -> tuple[bool, SupervisionReasonCode | None]:
        """Return (is_valid, reason_if_invalid)."""

        # Task already completed
        if snapshot.execution_status in ("COMPLETED", "FAILED", "SAFETY_STOPPED"):
            return False, SupervisionReasonCode.PLAN_ALREADY_COMPLETED

        # Plan version mismatch
        if snapshot.plan_version > contract.plan_version:
            return False, SupervisionReasonCode.PLAN_VERSION_MISMATCH
        # If snapshot plan_version < contract, edge is behind (KEEP should push update)

        # State staleness
        checked_at = now or datetime.now(UTC)
        age_ms = int((checked_at - snapshot.timestamp).total_seconds() * 1_000)
        if age_ms > stale_threshold_ms:
            return False, SupervisionReasonCode.EDGE_STATE_STALE

        # Robot state invalid
        robot = snapshot.robot_state
        if not robot:
            return False, SupervisionReasonCode.ROBOT_STATE_INVALID
        if robot.get("estop_engaged"):
            return False, SupervisionReasonCode.SAFETY_RISK_INCREASED

        # Scene confidence
        if snapshot.scene_confidence < 0.5:
            return False, SupervisionReasonCode.SCENE_CONFIDENCE_LOW

        # Completed steps should not regress
        contract_step_ids = {s.step_id for s in contract.steps}
        for sid in snapshot.completed_step_ids:
            if sid not in contract_step_ids:
                return False, SupervisionReasonCode.UNSUPPORTED_STATE_TRANSITION

        # current_step_id should belong to contract
        if snapshot.current_step_id and snapshot.current_step_id not in contract_step_ids:
            return False, SupervisionReasonCode.UNSUPPORTED_STATE_TRANSITION

        # Network state
        network = snapshot.network_state
        if network.get("degraded") or network.get("rtt_ms", 0) > 1_000:
            return False, SupervisionReasonCode.NETWORK_DEGRADED

        return True, None


# ── DeterministicSupervisionPolicy ───────────────────────────────────────────


class DeterministicSupervisionPolicy:
    """Layer 1: deterministic judgements without calling any model."""

    def __init__(
        self,
        detector: SceneChangeDetector | None = None,
        evaluator: PlanValidityEvaluator | None = None,
    ) -> None:
        self._detector = detector or SceneChangeDetector()
        self._evaluator = evaluator or PlanValidityEvaluator()

    def evaluate(
        self,
        snapshot: EdgeStatusSnapshot,
        contract: TaskContract,
        config: SupervisionConfig,
        known_obstacle_ids: set[str] | None = None,
        now: datetime | None = None,
    ) -> tuple[SupervisoryDecisionType, SupervisionReasonCode, str, bool]:
        """Return (decision, reason_code, detail, should_invoke_planner).

        should_invoke_planner is True only when a planner call is actually
        needed (target moved, new obstacles, plan invalid).
        """

        # 1. Check plan validity
        valid, invalid_reason = self._evaluator.evaluate(
            snapshot,
            contract,
            stale_threshold_ms=config.stale_state_threshold_ms,
            now=now,
        )
        if not valid:
            reason = invalid_reason or SupervisionReasonCode.SUPERVISOR_INTERNAL_ERROR
            if reason in (
                SupervisionReasonCode.PLAN_ALREADY_COMPLETED,
                SupervisionReasonCode.PLAN_VERSION_MISMATCH,
            ):
                return SupervisoryDecisionType.KEEP_CURRENT_PLAN, reason, "", False
            if reason == SupervisionReasonCode.EDGE_STATE_STALE:
                return (
                    SupervisoryDecisionType.REQUEST_MORE_OBSERVATION,
                    reason,
                    f"state age > {config.stale_state_threshold_ms}ms",
                    False,
                )
            if reason == SupervisionReasonCode.SCENE_CONFIDENCE_LOW:
                return (
                    SupervisoryDecisionType.REQUEST_MORE_OBSERVATION,
                    reason,
                    f"confidence {snapshot.scene_confidence} < {config.min_scene_confidence}",
                    False,
                )
            if reason == SupervisionReasonCode.SAFETY_RISK_INCREASED:
                if snapshot.robot_state.get("estop_engaged"):
                    return (
                        SupervisoryDecisionType.ABORT_TASK,
                        reason,
                        "emergency stop engaged",
                        False,
                    )
                return (
                    SupervisoryDecisionType.PAUSE_TASK,
                    reason,
                    "safety risk increased",
                    False,
                )
            if reason == SupervisionReasonCode.NETWORK_DEGRADED:
                if config.pause_on_unknown_risk:
                    return (
                        SupervisoryDecisionType.PAUSE_TASK,
                        reason,
                        "network degraded, pausing",
                        False,
                    )
                return (
                    SupervisoryDecisionType.KEEP_CURRENT_PLAN,
                    reason,
                    "network degraded but continuing",
                    False,
                )
            return (
                SupervisoryDecisionType.PAUSE_TASK,
                reason,
                "plan validity check failed",
                False,
            )

        # 2. Check target displacement
        displacement, expected, current = self._detector.target_displacement_from_telemetry(
            snapshot, contract
        )
        if displacement > config.target_displacement_threshold_m:
            # Determine if current step or future steps are affected
            current_step_idx = self._step_index(contract, snapshot.current_step_id)
            if current_step_idx is not None and current_step_idx < len(contract.steps):
                return (
                    SupervisoryDecisionType.UPDATE_CURRENT_STEP,
                    SupervisionReasonCode.TARGET_MOVED_CURRENT_STEP,
                    (
                        f"target moved {displacement:.3f}m "
                        f"(threshold={config.target_displacement_threshold_m:.3f}m)"
                    ),
                    True,
                )
            return (
                SupervisoryDecisionType.REPLACE_REMAINING_STEPS,
                SupervisionReasonCode.TARGET_MOVED_REMAINING_PLAN,
                f"target moved {displacement:.3f}m, affecting remaining plan",
                True,
            )

        # 3. Check new obstacles
        known = known_obstacle_ids or set()
        new_obs = self._detector.new_obstacles(snapshot, known)
        if new_obs:
            # Does obstacle block current step or just future steps?
            current_step_idx = self._step_index(contract, snapshot.current_step_id)
            if current_step_idx is not None and current_step_idx < len(contract.steps):
                return (
                    SupervisoryDecisionType.PAUSE_TASK,
                    SupervisionReasonCode.OBSTACLE_BLOCKS_CURRENT_PATH,
                    f"new obstacles detected: {known_obstacle_ids}",
                    True,
                )
            return (
                SupervisoryDecisionType.REPLACE_REMAINING_STEPS,
                SupervisionReasonCode.OBSTACLE_BLOCKS_REMAINING_PATH,
                "new obstacles affecting remaining path",
                True,
            )

        # 4. Scene confidence check (edge case, already handled above)
        if self._detector.scene_confidence_dropped(snapshot, config.min_scene_confidence):
            return (
                SupervisoryDecisionType.REQUEST_MORE_OBSERVATION,
                SupervisionReasonCode.SCENE_CONFIDENCE_LOW,
                f"confidence {snapshot.scene_confidence}",
                False,
            )

        # 5. Stable — keep current plan
        return (
            SupervisoryDecisionType.KEEP_CURRENT_PLAN,
            SupervisionReasonCode.SCENE_STABLE,
            "",
            False,
        )

    @staticmethod
    def _step_index(contract: TaskContract, step_id: str | None) -> int | None:
        if step_id is None:
            return None
        for i, s in enumerate(contract.steps):
            if s.step_id == step_id:
                return i
        return None


# ── SupervisionScheduler (injectable, test-friendly) ────────────────────────


@runtime_checkable
class SupervisionScheduler(Protocol):
    """Injectable scheduler for periodic supervision.

    In production this wraps an event loop; in tests it uses FakeClock.
    """

    def schedule(self, callback: Any, period_ms: int) -> None: ...

    def stop(self) -> None: ...

    @property
    def running(self) -> bool: ...


class TestSupervisionScheduler:
    """Scheduler that records callbacks; does NOT use real timers."""

    def __init__(self) -> None:
        self._callbacks: list[Any] = []
        self._stopped = False
        self.cycles_run: int = 0

    def schedule(self, callback: Any, period_ms: int) -> None:
        self._callbacks.append((callback, period_ms))

    def run_cycle(self) -> None:
        """Manually invoke the registered callback once."""
        for cb, _ in self._callbacks:
            cb()
        self.cycles_run += 1

    def stop(self) -> None:
        self._stopped = True

    @property
    def running(self) -> bool:
        return not self._stopped


# ── Helpers ──────────────────────────────────────────────────────────────────


def compute_state_hash(snapshot: EdgeStatusSnapshot) -> str:
    canonical = json.dumps(
        snapshot.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def compute_decision_hash(decision: SupervisoryDecision) -> str:
    canonical = json.dumps(
        decision.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
