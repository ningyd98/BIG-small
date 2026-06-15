from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cloud_edge_robot_arm.contracts import RiskLevel
from cloud_edge_robot_arm.risk.evaluator import RiskEvaluator
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput

NOW = datetime(2026, 6, 14, 11, 0, 0, tzinfo=UTC)


def _input(**overrides: object) -> RiskSnapshotInput:
    base = dict(
        task_id="task-1",
        task_type="pick-place",
        skill_name="GRASP",
        workspace_id="ws-a",
        scene_version=3,
        scene_updated_at=NOW,
        scene_confidence=0.95,
        target_confidence=0.9,
        target_moved=False,
        obstacle_count=0,
        obstacle_change_rate=0.0,
        network_latency_ms=60,
        network_jitter_ms=5,
        packet_loss_rate=0.01,
        disconnected_seconds=0.0,
        last_heartbeat_at=NOW,
        execution_failures=0,
        timeout_count=0,
        replans_count=0,
        safety_rejections=0,
        estop_engaged=False,
        safety_decision="ALLOW",
        current_mode="EVENT_TRIGGERED_EDGE_AUTONOMY",
        has_complete_contract=True,
        remaining_steps_persisted=True,
        edge_capability_ready=True,
        cloud_available=True,
        event_autonomy_ready=True,
        supervision_available=True,
        cache_confidence=0.9,
        cache_match_type="exact_match",
        policy_version="risk-v1",
        current_time=NOW,
    )
    base.update(overrides)
    return RiskSnapshotInput.model_validate(base)


def test_deterministic_risk_evaluation_is_stable() -> None:
    evaluator = RiskEvaluator(clock=lambda: NOW, policy=RiskPolicy(version="risk-v1"))
    snapshot_1 = evaluator.evaluate(_input())
    snapshot_2 = evaluator.evaluate(_input())

    assert snapshot_1 == snapshot_2
    assert snapshot_1.risk_level == RiskLevel.LOW
    assert snapshot_1.total_score == pytest.approx(snapshot_2.total_score)


def test_missing_key_inputs_fail_closed() -> None:
    evaluator = RiskEvaluator(clock=lambda: NOW, policy=RiskPolicy(version="risk-v1"))
    snapshot = evaluator.evaluate(_input(scene_confidence=None, cache_confidence=None))

    assert snapshot.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE
    assert "scene_confidence" in snapshot.missing_inputs
    assert "cache_confidence" in snapshot.missing_inputs
    assert snapshot.total_score >= 80.0


def test_emergency_stop_hard_overrides_everything() -> None:
    evaluator = RiskEvaluator(clock=lambda: NOW, policy=RiskPolicy(version="risk-v1"))
    snapshot = evaluator.evaluate(_input(safety_decision="EMERGENCY_STOP"))

    assert snapshot.risk_level == RiskLevel.CRITICAL
    assert "emergency_stop" in snapshot.reason_codes
    assert snapshot.total_score == 100.0


def test_expired_inputs_raise_risk_and_record_freshness() -> None:
    evaluator = RiskEvaluator(clock=lambda: NOW, policy=RiskPolicy(version="risk-v1"))
    snapshot = evaluator.evaluate(
        _input(
            scene_updated_at=NOW - timedelta(seconds=120),
            last_heartbeat_at=NOW - timedelta(seconds=30),
        )
    )

    assert snapshot.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
    assert snapshot.data_freshness["scene_updated_at_ms"] > 100_000
    assert snapshot.data_freshness["last_heartbeat_at_ms"] > 20_000


def test_network_risk_weights_latency_loss_and_disconnect() -> None:
    evaluator = RiskEvaluator(clock=lambda: NOW, policy=RiskPolicy(version="risk-v1"))
    snapshot = evaluator.evaluate(
        _input(network_latency_ms=800, network_jitter_ms=150, packet_loss_rate=0.3)
    )

    assert snapshot.component_scores.network_risk > 70.0
    assert "network_degraded" in snapshot.reason_codes


def test_policy_version_changes_affect_snapshot_hash() -> None:
    evaluator = RiskEvaluator(clock=lambda: NOW, policy=RiskPolicy(version="risk-v1"))
    first = evaluator.evaluate(_input())
    second = RiskEvaluator(clock=lambda: NOW, policy=RiskPolicy(version="risk-v2")).evaluate(
        _input(policy_version="risk-v2")
    )

    assert first.input_hash != second.input_hash
    assert first.policy_version == "risk-v1"
    assert second.policy_version == "risk-v2"
