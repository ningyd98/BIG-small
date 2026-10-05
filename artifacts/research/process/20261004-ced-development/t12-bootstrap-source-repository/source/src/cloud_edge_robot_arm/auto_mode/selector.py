"""AUTO 模式选择器，根据风险、缓存和合同状态确定控制模式。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.auto_mode.models import (
    AutoModePolicy,
    AutoModeState,
)
from cloud_edge_robot_arm.contracts import (
    AutoModeDecision,
    AutoModeDecisionType,
    ControlMode,
    RiskLevel,
    RiskSnapshot,
)
from cloud_edge_robot_arm.skill_cache.models import SkillCacheLookupResult


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AutoModeSelector:
    """AUTO 模式选择器，根据风险和运行证据选择保持、切换或暂停。"""

    def __init__(
        self,
        *,
        policy: AutoModePolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy or AutoModePolicy(version="auto-v1")
        self._clock = clock or _utc_now

    def decide(
        self,
        *,
        current_state: AutoModeState,
        risk_snapshot: RiskSnapshot,
        cache_lookup: SkillCacheLookupResult,
        active_contract_complete: bool,
        checkpoint_persisted: bool,
        event_autonomy_ready: bool,
        supervision_available: bool,
        atomic_step_active: bool,
        mode_history: list[ControlMode],
    ) -> AutoModeDecision:
        """根据当前状态和风险快照生成单次 AUTO 模式决策。"""
        now = self._clock()
        reason_codes: list[str] = []
        if risk_snapshot.risk_level == RiskLevel.CRITICAL:
            return self._decision(
                current_state,
                now,
                AutoModeDecisionType.SAFE_STOP,
                None,
                risk_snapshot,
                ["critical_risk"],
            )
        if risk_snapshot.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE:
            return self._decision(
                current_state,
                now,
                AutoModeDecisionType.REQUEST_MORE_OBSERVATION,
                None,
                risk_snapshot,
                ["insufficient_evidence"],
            )
        if any(code in risk_snapshot.reason_codes for code in ("safety_pause", "safety_reject")):
            return self._decision(
                current_state,
                now,
                AutoModeDecisionType.PAUSE_TASK,
                None,
                risk_snapshot,
                ["safety_risk"],
            )
        if not active_contract_complete or not checkpoint_persisted:
            return self._decision(
                current_state,
                now,
                AutoModeDecisionType.REQUEST_MORE_OBSERVATION,
                None,
                risk_snapshot,
                ["contract_incomplete"],
            )
        if atomic_step_active:
            return self._keep(current_state, now, risk_snapshot, ["atomic_step_active"])
        if current_state.switch_count >= self._policy.max_switches_per_task:
            return self._decision(
                current_state,
                now,
                AutoModeDecisionType.PAUSE_TASK,
                None,
                risk_snapshot,
                ["switch_limit_exceeded"],
            )

        dwell_elapsed = (
            (now - current_state.last_switch_at).total_seconds()
            if current_state.last_switch_at
            else 0
        )
        if dwell_elapsed < self._policy.min_dwell_seconds:
            reason_codes.append("dwell_time_not_met")
            return self._keep(current_state, now, risk_snapshot, reason_codes)
        if (
            dwell_elapsed < self._policy.switch_cooldown_seconds
            and current_state.last_switch_at is not None
        ):
            reason_codes.append("cooldown_active")
            return self._keep(current_state, now, risk_snapshot, reason_codes)

        if risk_snapshot.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            return self._decision(
                current_state,
                now,
                AutoModeDecisionType.PAUSE_TASK,
                None,
                risk_snapshot,
                ["high_risk"],
            )

        if (
            risk_snapshot.risk_level in {RiskLevel.LOW, RiskLevel.MEDIUM}
            and event_autonomy_ready
            and cache_lookup.match_type in {"exact_match", "compatible_match"}
            and current_state.current_mode != ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
            and checkpoint_persisted
            and active_contract_complete
            and risk_snapshot.component_scores.scene_dynamics_risk < 55.0
        ):
            return self._decision(
                current_state,
                now,
                AutoModeDecisionType.SWITCH_TO_EVENT_TRIGGERED_EDGE_AUTONOMY,
                ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
                risk_snapshot,
                ["event_mode_ready"],
            )

        if (
            risk_snapshot.risk_level in {RiskLevel.LOW, RiskLevel.MEDIUM}
            and supervision_available
            and current_state.current_mode != ControlMode.PERIODIC_CLOUD_SUPERVISION
            and cache_lookup.match_type != "no_match"
        ):
            return self._decision(
                current_state,
                now,
                AutoModeDecisionType.SWITCH_TO_PERIODIC_CLOUD_SUPERVISION,
                ControlMode.PERIODIC_CLOUD_SUPERVISION,
                risk_snapshot,
                ["periodic_mode_ready"],
            )

        return self._keep(current_state, now, risk_snapshot, reason_codes or ["keep_current_mode"])

    def _keep(
        self,
        current_state: AutoModeState,
        now: datetime,
        risk_snapshot: RiskSnapshot,
        reason_codes: list[str],
    ) -> AutoModeDecision:
        return self._decision(
            current_state,
            now,
            AutoModeDecisionType.KEEP_CURRENT_MODE,
            None,
            risk_snapshot,
            reason_codes,
        )

    def _decision(
        self,
        current_state: AutoModeState,
        now: datetime,
        action: AutoModeDecisionType,
        selected_mode: ControlMode | None,
        risk_snapshot: RiskSnapshot,
        reason_codes: list[str],
    ) -> AutoModeDecision:
        return AutoModeDecision(
            decision_id=f"auto-{current_state.task_id}-{risk_snapshot.snapshot_id}",
            task_id=current_state.task_id,
            current_mode=current_state.current_mode,
            selected_mode=selected_mode,
            action=action,
            risk_score=risk_snapshot.total_score,
            confidence=0.9 if action != AutoModeDecisionType.KEEP_CURRENT_MODE else 0.7,
            reason_codes=sorted(set(reason_codes)),
            decision_version=current_state.mode_version + 1,
            created_at=now,
            valid_until=now + timedelta(seconds=30),
            input_snapshot_hash=risk_snapshot.input_hash,
            policy_version=self._policy.version,
        )
