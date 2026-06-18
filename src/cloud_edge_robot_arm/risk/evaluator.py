"""风险评估器，把任务、场景和遥测转换为结构化风险等级。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts import RiskComponentScores, RiskLevel, RiskSnapshot
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RiskEvaluator:
    def __init__(
        self,
        *,
        policy: RiskPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy or RiskPolicy(version="risk-v1")
        self._clock = clock or _utc_now

    def evaluate(self, data: RiskSnapshotInput) -> RiskSnapshot:
        now = data.current_time or self._clock()
        missing_inputs = _missing_inputs(data)
        data_freshness = _freshness(data, now)
        reason_codes: list[str] = []

        safety_score = _safety_risk(data, reason_codes, self._policy)
        if data.estop_engaged or (data.safety_decision or "").upper() == "EMERGENCY_STOP":
            risk_level = RiskLevel.CRITICAL
            reason_codes.append("emergency_stop")
            component_scores = RiskComponentScores(
                task_risk=100.0,
                scene_dynamics_risk=100.0,
                perception_risk=100.0,
                network_risk=100.0,
                execution_risk=100.0,
                safety_risk=100.0,
            )
            total_score = 100.0
        else:
            task_score = _task_risk(data)
            scene_score = _scene_dynamics_risk(data, data_freshness, self._policy, reason_codes)
            perception_score = _perception_risk(data, reason_codes)
            network_score = _network_risk(data, data_freshness, self._policy, reason_codes)
            execution_score = _execution_risk(data, reason_codes, self._policy)
            weighted = (
                task_score * self._policy.task_weight
                + scene_score * self._policy.scene_dynamics_weight
                + perception_score * self._policy.perception_weight
                + network_score * self._policy.network_weight
                + execution_score * self._policy.execution_weight
                + safety_score * self._policy.safety_weight
            )
            total_score = max(weighted, safety_score)
            if scene_score >= 75.0:
                total_score = max(total_score, 75.0)
            if network_score >= 75.0:
                total_score = max(total_score, 70.0)
            if "scene_stale" in reason_codes or "heartbeat_stale" in reason_codes:
                total_score = max(total_score, 75.0)
            if missing_inputs:
                total_score = max(total_score, self._policy.missing_input_penalty)
            component_scores = RiskComponentScores(
                task_risk=task_score,
                scene_dynamics_risk=scene_score,
                perception_risk=perception_score,
                network_risk=network_score,
                execution_risk=execution_score,
                safety_risk=safety_score,
            )
            risk_level = _risk_level(total_score, missing_inputs, self._policy)

        if missing_inputs:
            reason_codes.append("insufficient_evidence")
        input_hash = _input_hash(data, self._policy.version)
        if data.policy_version != self._policy.version:
            reason_codes.append("policy_version_mismatch")
        return RiskSnapshot(
            snapshot_id=_snapshot_id(data.task_id, input_hash),
            task_id=data.task_id,
            component_scores=component_scores,
            total_score=round(min(total_score, 100.0), 3),
            risk_level=risk_level,
            data_freshness=data_freshness,
            missing_inputs=missing_inputs,
            reason_codes=sorted(set(reason_codes)),
            policy_version=self._policy.version,
            created_at=now,
            expires_at=now + timedelta(seconds=30),
            input_hash=input_hash,
        )


def _missing_inputs(data: RiskSnapshotInput) -> list[str]:
    missing: list[str] = []
    for field in (
        "scene_updated_at",
        "scene_confidence",
        "target_confidence",
        "target_moved",
        "obstacle_count",
        "obstacle_change_rate",
        "network_latency_ms",
        "network_jitter_ms",
        "packet_loss_rate",
        "disconnected_seconds",
        "last_heartbeat_at",
        "execution_failures",
        "timeout_count",
        "replans_count",
        "safety_rejections",
        "estop_engaged",
        "safety_decision",
        "has_complete_contract",
        "remaining_steps_persisted",
        "edge_capability_ready",
        "cloud_available",
        "event_autonomy_ready",
        "supervision_available",
        "cache_confidence",
        "cache_match_type",
    ):
        if getattr(data, field) is None:
            missing.append(field)
    return missing


def _freshness(data: RiskSnapshotInput, now: datetime) -> dict[str, int]:
    freshness: dict[str, int] = {}
    if data.scene_updated_at is not None:
        freshness["scene_updated_at_ms"] = max(
            0, int((now - data.scene_updated_at).total_seconds() * 1_000)
        )
    if data.last_heartbeat_at is not None:
        freshness["last_heartbeat_at_ms"] = max(
            0, int((now - data.last_heartbeat_at).total_seconds() * 1_000)
        )
    return freshness


def _task_risk(data: RiskSnapshotInput) -> float:
    score = 10.0
    if data.skill_name.upper() in {"GRASP", "PLACE", "RELEASE"}:
        score += 20.0
    if data.task_type.lower() in {"pick-place", "pick_and_place", "manipulation"}:
        score += 15.0
    if not bool(data.has_complete_contract):
        score += 30.0
    if not bool(data.remaining_steps_persisted):
        score += 25.0
    if not bool(data.edge_capability_ready):
        score += 25.0
    return min(score, 100.0)


def _scene_dynamics_risk(
    data: RiskSnapshotInput,
    freshness: dict[str, int],
    policy: RiskPolicy,
    reason_codes: list[str],
) -> float:
    score = 5.0
    if bool(data.target_moved):
        score += policy.scene_target_moved_bonus
        reason_codes.append("target_moved")
    if data.obstacle_count:
        score += min(25.0, float(data.obstacle_count) * 5.0)
    if data.obstacle_change_rate is not None:
        score += min(20.0, data.obstacle_change_rate * 100.0)
    scene_age_ms = freshness.get("scene_updated_at_ms")
    if scene_age_ms is not None and scene_age_ms > policy.stale_scene_ms:
        score += min(35.0, (scene_age_ms - policy.stale_scene_ms) / 50.0)
        reason_codes.append("scene_stale")
    if data.scene_confidence is not None and data.scene_confidence < 0.5:
        score += (0.5 - data.scene_confidence) * 100.0
        reason_codes.append("scene_confidence_low")
    return min(score, 100.0)


def _perception_risk(data: RiskSnapshotInput, reason_codes: list[str]) -> float:
    score = 5.0
    if data.scene_confidence is not None:
        score += (1.0 - data.scene_confidence) * 50.0
    if data.target_confidence is not None:
        score += (1.0 - data.target_confidence) * 40.0
    if bool(data.target_lost):
        score += 35.0
        reason_codes.append("target_lost")
    return min(score, 100.0)


def _network_risk(
    data: RiskSnapshotInput,
    freshness: dict[str, int],
    policy: RiskPolicy,
    reason_codes: list[str],
) -> float:
    score = 5.0
    if data.network_latency_ms is not None:
        score += min(40.0, data.network_latency_ms / 20.0)
        if data.network_latency_ms > 300:
            reason_codes.append("network_latency_high")
            reason_codes.append("network_degraded")
    if data.network_jitter_ms is not None:
        score += min(20.0, data.network_jitter_ms / 10.0)
    if data.packet_loss_rate is not None:
        score += min(35.0, data.packet_loss_rate * 100.0)
        if data.packet_loss_rate > 0.1:
            reason_codes.append("network_degraded")
    if data.disconnected_seconds is not None:
        score += min(30.0, data.disconnected_seconds * 5.0)
        if data.disconnected_seconds > 0:
            reason_codes.append("network_disconnected")
    heartbeat_age_ms = freshness.get("last_heartbeat_at_ms")
    if heartbeat_age_ms is not None and heartbeat_age_ms > policy.stale_heartbeat_ms:
        score += min(30.0, (heartbeat_age_ms - policy.stale_heartbeat_ms) / 25.0)
        reason_codes.append("heartbeat_stale")
    if data.cloud_available is False:
        score += 20.0
        reason_codes.append("cloud_unavailable")
    if data.current_mode.value == "EVENT_TRIGGERED_EDGE_AUTONOMY" and not bool(
        data.supervision_available
    ):
        score += 10.0
    return min(score, 100.0)


def _execution_risk(
    data: RiskSnapshotInput,
    reason_codes: list[str],
    policy: RiskPolicy,
) -> float:
    score = 5.0
    if data.execution_failures is not None:
        score += min(30.0, data.execution_failures * 10.0)
    if data.timeout_count is not None:
        score += min(25.0, data.timeout_count * 8.0)
        if data.timeout_count > 0:
            reason_codes.append("timeout_history")
    if data.replans_count is not None:
        score += min(20.0, data.replans_count * 5.0)
    if data.cache_confidence is not None:
        score += max(0.0, (0.7 - data.cache_confidence) * 50.0)
    if data.cache_match_type == "exact_match":
        score -= 5.0
    elif data.cache_match_type == "compatible_match":
        score += 5.0
    elif data.cache_match_type == "no_match":
        score += policy.cache_no_match_penalty
        reason_codes.append("cache_miss")
    if data.safety_rejections:
        score += min(40.0, data.safety_rejections * 15.0)
        reason_codes.append("safety_rejections")
    return min(max(score, 0.0), 100.0)


def _safety_risk(
    data: RiskSnapshotInput,
    reason_codes: list[str],
    policy: RiskPolicy,
) -> float:
    safety_decision = (data.safety_decision or "").upper()
    score = 5.0
    if safety_decision == "ALLOW_WITH_LIMITS":
        score += 15.0
        reason_codes.append("safety_limits")
    elif safety_decision == "PAUSE":
        score += 60.0
        reason_codes.append("safety_pause")
    elif safety_decision == "REJECT":
        score += 85.0
        reason_codes.append("safety_reject")
    elif safety_decision == "EMERGENCY_STOP":
        return 100.0
    if data.safety_rejections:
        score += min(25.0, data.safety_rejections * 10.0)
    if data.estop_engaged:
        score += 80.0
    return min(score, 100.0)


def _risk_level(total_score: float, missing_inputs: list[str], policy: RiskPolicy) -> RiskLevel:
    if missing_inputs:
        return RiskLevel.INSUFFICIENT_EVIDENCE
    if total_score >= policy.critical_threshold:
        return RiskLevel.CRITICAL
    if total_score >= policy.high_threshold:
        return RiskLevel.HIGH
    if total_score >= policy.medium_threshold:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _input_hash(data: RiskSnapshotInput, policy_version: str) -> str:
    canonical = json.dumps(
        {"input": data.model_dump(mode="json"), "policy_version": policy_version},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot_id(task_id: str, input_hash: str) -> str:
    return f"risk-{task_id}-{input_hash[:12]}"
