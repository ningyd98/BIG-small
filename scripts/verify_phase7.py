#!/usr/bin/env python3
"""Phase 7 风险评估和 AUTO 模式验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。

Phase 7 acceptance verification.

The script exercises production code paths for Skill Cache, RiskEvaluator,
AUTO selection, mode transitions, persistence, production configuration gates,
and Phase 5/6 regressions. Any failed check exits non-zero."""

# ruff: noqa: E402
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from cloud_edge_robot_arm.auto_mode.models import (
    AutoModePolicy,
    AutoModeState,
    AutoModeTransitionRequest,
)
from cloud_edge_robot_arm.auto_mode.repository import (
    SQLiteAutoModeRepository,
)
from cloud_edge_robot_arm.auto_mode.selector import AutoModeSelector
from cloud_edge_robot_arm.auto_mode.transition_service import ModeTransitionService
from cloud_edge_robot_arm.config import AppConfig
from cloud_edge_robot_arm.contracts import (
    AutoModeDecisionType,
    AutoModeTransitionStatus,
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
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    IdempotencyConflictError,
)
from cloud_edge_robot_arm.risk.evaluator import RiskEvaluator
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput
from cloud_edge_robot_arm.skill_cache.models import (
    SkillCacheKey,
    SkillCacheLookupResult,
    SkillCachePromotionPolicy,
    SkillExecutionRecord,
    SkillTemplate,
    SkillTemplateStatus,
)
from cloud_edge_robot_arm.skill_cache.repository import SQLiteSkillCacheRepository

SRC = ROOT / "src" / "cloud_edge_robot_arm"
NOW = datetime(2026, 6, 14, 14, 0, 0, tzinfo=UTC)


def _key(**overrides: object) -> SkillCacheKey:
    data: dict[str, object] = {
        "skill_name": SkillName.GRASP,
        "robot_model": "mock-arm-v1",
        "end_effector_type": "parallel_gripper",
        "object_class": "cube",
        "task_intent": "pick-place",
        "workspace_id": "ws-a",
        "parameter_schema_version": "schema-v1",
        "robot_capability_hash": "cap-v1",
        "safety_policy_hash": "safety-v1",
        "calibration_version": "cal-v1",
    }
    data.update(overrides)
    return SkillCacheKey.model_validate(data)


def _template(template_id: str = "tmpl-grasp") -> SkillTemplate:
    return SkillTemplate(
        template_id=template_id,
        cache_key=_key(),
        skill_name=SkillName.GRASP,
        parameter_template={"object_id": "{object_id}", "approach": "top"},
        required_preconditions=["target_visible"],
        expected_success_conditions=["object_attached"],
        expected_duration_ms=1_000,
        timeout_ms=3_000,
        source_contract_id="contract-1",
        source_plan_version=1,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )


def _record(
    execution_id: str,
    *,
    success: bool = True,
    safety_decision: SafetyDecision = SafetyDecision.ALLOW,
    failure_reason: str = "",
) -> SkillExecutionRecord:
    return SkillExecutionRecord(
        execution_id=execution_id,
        template_id="tmpl-grasp",
        task_id=f"task-{execution_id}",
        plan_id="plan-1",
        step_id="step-grasp",
        success=success,
        safety_decision=safety_decision,
        failure_reason=failure_reason,
        duration_ms=1_000,
        local_retry_count=0,
        cloud_replan_count=0,
        scene_confidence=0.9,
        network_quality=0.8,
        executed_at=NOW,
        evidence_hash=f"evidence-{execution_id}",
    )


def _risk_input(**overrides: object) -> RiskSnapshotInput:
    data: dict[str, object] = {
        "task_id": "task-1",
        "task_type": "pick-place",
        "skill_name": "GRASP",
        "workspace_id": "ws-a",
        "scene_version": 1,
        "scene_updated_at": NOW,
        "scene_confidence": 0.95,
        "target_confidence": 0.9,
        "target_moved": False,
        "target_lost": False,
        "obstacle_count": 0,
        "obstacle_change_rate": 0.0,
        "network_latency_ms": 50,
        "network_jitter_ms": 5,
        "packet_loss_rate": 0.01,
        "disconnected_seconds": 0.0,
        "last_heartbeat_at": NOW,
        "execution_failures": 0,
        "timeout_count": 0,
        "replans_count": 0,
        "safety_rejections": 0,
        "estop_engaged": False,
        "safety_decision": "ALLOW",
        "current_mode": ControlMode.PERIODIC_CLOUD_SUPERVISION,
        "has_complete_contract": True,
        "remaining_steps_persisted": True,
        "edge_capability_ready": True,
        "cloud_available": True,
        "event_autonomy_ready": True,
        "supervision_available": True,
        "cache_confidence": 0.95,
        "cache_match_type": "exact_match",
        "policy_version": "risk-v1",
        "current_time": NOW,
    }
    data.update(overrides)
    return RiskSnapshotInput.model_validate(data)


def _selector_state(
    mode: ControlMode = ControlMode.PERIODIC_CLOUD_SUPERVISION,
    *,
    last_switch_at: datetime | None = None,
    switch_count: int = 0,
) -> AutoModeState:
    return AutoModeState(
        task_id="task-1",
        current_mode=mode,
        mode_version=1,
        switch_count=switch_count,
        last_switch_at=last_switch_at or NOW - timedelta(minutes=10),
        policy_version="auto-v1",
        updated_at=NOW,
    )


def _trusted_cache_lookup() -> SkillCacheLookupResult:
    from cloud_edge_robot_arm.skill_cache.repository import InMemorySkillCacheRepository

    repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    tmpl = _template()
    repo.save_template(tmpl)
    repo.compare_and_set_template_version(
        tmpl.template_id,
        expected_template_version=1,
        new_status=SkillTemplateStatus.TRUSTED,
    )
    return repo.lookup_templates(_key())


def check_skill_cache_sqlite_restart_promotion_invalidation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "skill-cache.db"
        repo = SQLiteSkillCacheRepository(db_path, clock=lambda: NOW)
        repo.save_template(_template())
        repo.save_execution_record(_record("exec-1"))
        repo.save_execution_record(_record("exec-2"))
        promoted = repo.promote_template(
            "tmpl-grasp",
            policy=SkillCachePromotionPolicy(min_successes=2, min_recent_success_rate=0.9),
            expected_template_version=1,
        )
        assert promoted.status == SkillTemplateStatus.TRUSTED
        repo.close()

        reopened = SQLiteSkillCacheRepository(db_path, clock=lambda: NOW)
        template = reopened.get_template("tmpl-grasp")
        assert template is not None
        assert template.status == SkillTemplateStatus.TRUSTED
        assert reopened.get_statistics("tmpl-grasp").successful_executions == 2
        assert reopened.lookup_templates(_key()).match_type == "exact_match"
        invalidated = reopened.invalidate_template("tmpl-grasp", "phase7_acceptance")
        assert invalidated.status == SkillTemplateStatus.INVALIDATED
        assert reopened.lookup_templates(_key()).match_type == "no_match"
        reopened.close()


def check_cache_cannot_bypass_safety_shield() -> None:
    from cloud_edge_robot_arm.contracts import RobotState

    payload = _template().model_dump()
    payload["parameter_template"] = {"disable_safety": True}
    rejected_template = False
    try:
        SkillTemplate(**payload)
    except ValueError:
        rejected_template = True
    if not rejected_template:
        raise AssertionError("low-level safety bypass template was accepted")
    shield = SafetyShield()
    task = TaskContract(
        task_id="phase7-safety-bypass",
        plan_version=1,
        command_seq=1,
        timestamp=NOW,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=NOW,
        valid_until=NOW + timedelta(seconds=60),
        user_instruction="pick object",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(object_id="obj-1", object_class="cube", target_region_id="bin-a"),
        steps=[
            TaskStep(
                step_id="grasp",
                skill=SkillName.GRASP,
                parameters={"object_id": "obj-1"},
                expected_duration_ms=1_000,
                timeout_ms=3_000,
                retry_limit=0,
            )
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=1.0,
            max_tcp_velocity=0.5,
            minimum_safe_height=0.08,
            workspace_id="ws-a",
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=0,
            on_timeout="pause",
            on_safety_rejection="stop",
            on_network_loss="pause",
        ),
        completion_criteria=["object_attached"],
    )
    step = task.steps[0].model_copy(
        update={"parameters": {"object_id": "obj-1", "disable_safety": True}}
    )
    ctx = shield.context_builder.build(
        contract=task,
        step=step,
        robot_state=RobotState(connected=True),
        scene_version=task.scene_version,
        resolved_parameters=step.parameters,
        scene_updated_at=NOW,
        telemetry_timestamp=NOW,
        wall_clock_now=NOW,
    )
    try:
        shield.pre_check(ctx)
    except ValueError:
        return
    raise AssertionError("SafetyShield accepted bypass parameter")


def check_risk_deterministic_and_fail_closed() -> None:
    evaluator = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW)
    first = evaluator.evaluate(_risk_input())
    second = evaluator.evaluate(_risk_input())
    assert first.input_hash == second.input_hash
    assert first.total_score == second.total_score
    missing = evaluator.evaluate(_risk_input(scene_confidence=None))
    assert missing.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE
    assert missing.total_score >= 80.0
    estop = evaluator.evaluate(_risk_input(safety_decision="EMERGENCY_STOP"))
    assert estop.risk_level == RiskLevel.CRITICAL
    assert estop.total_score == 100.0


def check_auto_decision_matrix() -> None:
    evaluator = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW)
    selector = AutoModeSelector(clock=lambda: NOW, policy=AutoModePolicy(version="auto-v1"))
    event = selector.decide(
        current_state=_selector_state(ControlMode.PERIODIC_CLOUD_SUPERVISION),
        risk_snapshot=evaluator.evaluate(
            _risk_input(network_latency_ms=900, packet_loss_rate=0.35)
        ),
        cache_lookup=_trusted_cache_lookup(),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )
    assert event.action == AutoModeDecisionType.SWITCH_TO_EVENT_TRIGGERED_EDGE_AUTONOMY

    periodic = selector.decide(
        current_state=_selector_state(ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY),
        risk_snapshot=evaluator.evaluate(_risk_input(target_moved=True, scene_confidence=0.8)),
        cache_lookup=_trusted_cache_lookup(),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )
    assert periodic.action == AutoModeDecisionType.SWITCH_TO_PERIODIC_CLOUD_SUPERVISION

    unsafe = selector.decide(
        current_state=_selector_state(ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY),
        risk_snapshot=evaluator.evaluate(_risk_input(safety_decision="EMERGENCY_STOP")),
        cache_lookup=_trusted_cache_lookup(),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )
    assert unsafe.action == AutoModeDecisionType.SAFE_STOP


def check_hysteresis_dwell_cooldown_and_limits() -> None:
    evaluator = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW)
    risk = evaluator.evaluate(_risk_input())
    selector = AutoModeSelector(
        clock=lambda: NOW,
        policy=AutoModePolicy(
            version="auto-v1",
            min_dwell_seconds=120,
            switch_cooldown_seconds=300,
            max_switches_per_task=2,
        ),
    )
    dwell = selector.decide(
        current_state=_selector_state(
            ControlMode.PERIODIC_CLOUD_SUPERVISION,
            last_switch_at=NOW - timedelta(seconds=30),
        ),
        risk_snapshot=risk,
        cache_lookup=_trusted_cache_lookup(),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )
    assert dwell.action == AutoModeDecisionType.KEEP_CURRENT_MODE
    assert "dwell_time_not_met" in dwell.reason_codes

    atomic = selector.decide(
        current_state=_selector_state(ControlMode.PERIODIC_CLOUD_SUPERVISION),
        risk_snapshot=risk,
        cache_lookup=_trusted_cache_lookup(),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=True,
        mode_history=[],
    )
    assert atomic.action == AutoModeDecisionType.KEEP_CURRENT_MODE

    limit = selector.decide(
        current_state=_selector_state(
            ControlMode.PERIODIC_CLOUD_SUPERVISION,
            switch_count=2,
        ),
        risk_snapshot=risk,
        cache_lookup=_trusted_cache_lookup(),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )
    assert limit.action == AutoModeDecisionType.PAUSE_TASK


def check_transition_prepare_commit_abort_cas_idempotency() -> None:
    service = ModeTransitionService(clock=lambda: NOW)
    request = AutoModeTransitionRequest(
        task_id="task-1",
        from_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        expected_mode_version=1,
        idempotency_key="idem-transition",
        decision_id="decision-1",
        reason="phase7_acceptance",
    )
    prepared = service.prepare(request)
    assert prepared.status == AutoModeTransitionStatus.PREPARED
    same = service.prepare(request)
    assert same.transition_id == prepared.transition_id
    conflict_detected = False
    try:
        service.prepare(request.model_copy(update={"reason": "conflict"}))
    except IdempotencyConflictError:
        conflict_detected = True
    if not conflict_detected:
        raise AssertionError("transition idempotency conflict was not detected")
    committed = service.commit(prepared.transition_id)
    assert committed.status == AutoModeTransitionStatus.COMMITTED
    aborted = service.abort("unknown-transition", reason="restart_recovery")
    assert aborted.status == AutoModeTransitionStatus.ABORTED


def check_auto_repo_sqlite_restart_prepared_recovery() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "auto-mode.db"
        repo = SQLiteAutoModeRepository(db_path, clock=lambda: NOW)
        snapshot = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
            _risk_input()
        )
        repo.save_risk_snapshot(snapshot)
        repo.save_status(_selector_state())
        transition = ModeTransitionService(clock=lambda: NOW).prepare(
            AutoModeTransitionRequest(
                task_id="task-1",
                from_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
                to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
                expected_mode_version=1,
                idempotency_key="restart-idem",
                decision_id="decision-1",
                reason="prepared_before_restart",
            )
        )
        repo.save_transition(transition)
        repo.close()

        reopened = SQLiteAutoModeRepository(db_path, clock=lambda: NOW)
        recovered = reopened.latest_prepared_transition("task-1")
        assert recovered is not None
        assert recovered.transition_id == transition.transition_id
        assert reopened.get_status("task-1") is not None
        reopened.close()


def check_phase5_phase6_regression() -> None:
    for script in ("verify_phase5.py", "verify_phase6.py"):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script)],
            cwd=ROOT,
            check=True,
        )


def check_production_config_blocks_unsafe_defaults() -> None:
    base = {
        "RUNTIME_PROFILE": "production",
        "DATABASE_URL": "sqlite:////var/lib/big-small/robot_control.db",
        "MQTT_BROKER_URL": "mqtt://broker.internal:1883",
        "PLANNER_API_ENDPOINT": "https://planner.internal/v1/chat/completions",
        "PLANNER_API_KEY": "prod-secret-key",
        "ROBOT_ADAPTER": "real_robot_sdk",
        "TELEMETRY_PROVIDER": "robot_sdk",
        "SCENE_STATE_PROVIDER": "vision_pipeline",
        "SUPERVISION_REPOSITORY": "sqlite",
        "SUPERVISION_SCHEDULER": "asyncio",
        "AUTO_MODE_ENABLED": "true",
        "RISK_POLICY_VERSION": "risk-v1",
        "RISK_COMPONENT_WEIGHTS": (
            "task=0.15,scene=0.15,perception=0.15,network=0.15,execution=0.2,safety=0.2"
        ),
        "RISK_LEVEL_THRESHOLDS": "low=25,medium=50,high=75,critical=90",
    }
    try:
        AppConfig.from_env(base)
    except ValueError as exc:
        assert "SKILL_CACHE_BACKEND" in str(exc)
    else:
        raise AssertionError("production AUTO accepted missing Phase 7 persistence")

    cfg = AppConfig.from_env(
        {
            **base,
            "SKILL_CACHE_BACKEND": "sqlite",
            "SKILL_CACHE_DB_PATH": "/var/lib/big-small/skill-cache.db",
            "AUTO_MODE_REPOSITORY": "sqlite",
            "AUTO_MODE_DB_PATH": "/var/lib/big-small/auto-mode.db",
        }
    )
    assert cfg.auto_mode_enabled is True
    assert cfg.skill_cache_backend == "sqlite"


def check_auto_capability_not_pre_advertised() -> None:
    from cloud_edge_robot_arm.cloud.api.app import create_app
    from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", "") == "/api/v1/auto-mode/capabilities"
    )
    import asyncio

    assert hasattr(route, "endpoint")
    endpoint = cast(Callable[[], Any], route.endpoint)
    response = asyncio.run(endpoint())
    assert response.configured is False
    assert response.auto_mode_enabled is False
    assert ControlMode.AUTO.value not in response.supported_control_modes


def check_no_placeholders_or_safety_bypass_paths() -> None:
    for package_dir in (SRC / "skill_cache", SRC / "risk", SRC / "auto_mode"):
        for path in package_dir.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Pass):
                    raise AssertionError(f"placeholder pass found in {path}")
    text = "\n".join(path.read_text(encoding="utf-8") for path in SRC.rglob("*.py"))
    forbidden_phrases = [
        "success=true",
        "fixed printing",
        "bypass SafetyShield",
        "disable_safety=True",
    ]
    for phrase in forbidden_phrases:
        if phrase in text:
            raise AssertionError(f"forbidden pseudo-success or bypass phrase: {phrase}")


def report(index: int, name: str, func: Callable[[], None]) -> bool:
    label = f"{index}. {name}"
    try:
        func()
    except Exception as exc:
        print(f"✗ {label}: {type(exc).__name__}: {exc}", flush=True)
        return False
    print(f"✓ {label}", flush=True)
    return True


def main() -> int:
    print("Phase 7 Acceptance Verification", flush=True)
    print("=" * 60, flush=True)
    checks: list[tuple[str, Callable[[], None]]] = [
        (
            "Skill Cache SQLite restart, promotion, and invalidation",
            check_skill_cache_sqlite_restart_promotion_invalidation,
        ),
        ("cache hit cannot bypass SafetyShield", check_cache_cannot_bypass_safety_shield),
        (
            "risk determinism and fail-closed missing inputs",
            check_risk_deterministic_and_fail_closed,
        ),
        ("AUTO decision matrix", check_auto_decision_matrix),
        (
            "hysteresis, dwell time, cooldown, and switch limits",
            check_hysteresis_dwell_cooldown_and_limits,
        ),
        (
            "mode transition prepare/commit/abort/CAS/idempotency",
            check_transition_prepare_commit_abort_cas_idempotency,
        ),
        (
            "AUTO SQLite restart recovers prepared transition",
            check_auto_repo_sqlite_restart_prepared_recovery,
        ),
        ("Phase 5 and Phase 6 dual-mode regressions", check_phase5_phase6_regression),
        (
            "production config blocks InMemory and mock AUTO defaults",
            check_production_config_blocks_unsafe_defaults,
        ),
        (
            "AUTO capability is not advertised before configuration",
            check_auto_capability_not_pre_advertised,
        ),
        (
            "production source has no placeholder or bypass paths",
            check_no_placeholders_or_safety_bypass_paths,
        ),
    ]
    passed = 0
    for index, (name, func) in enumerate(checks, start=1):
        if report(index, name, func):
            passed += 1
    print(f"\n{passed}/{len(checks)} checks passed", flush=True)
    success = passed == len(checks)
    print(f"success={str(success).lower()}", flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
