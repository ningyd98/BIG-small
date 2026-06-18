"""Phase 7 风险评估和 AUTO 模式回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cloud_edge_robot_arm.contracts import SafetyDecision, SkillName
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    IdempotencyConflictError,
)
from cloud_edge_robot_arm.skill_cache.models import (
    SkillCacheKey,
    SkillCachePromotionPolicy,
    SkillExecutionRecord,
    SkillTemplate,
    SkillTemplateStatus,
)
from cloud_edge_robot_arm.skill_cache.repository import (
    InMemorySkillCacheRepository,
    SQLiteSkillCacheRepository,
)

NOW = datetime(2026, 6, 14, 10, 0, 0, tzinfo=UTC)


def _key(*, safety_policy_hash: str = "safety-v1") -> SkillCacheKey:
    return SkillCacheKey(
        skill_name=SkillName.GRASP,
        robot_model="mock-arm-v1",
        end_effector_type="parallel_gripper",
        object_class="cube",
        task_intent="pick-place",
        workspace_id="ws-a",
        parameter_schema_version="schema-v1",
        robot_capability_hash="cap-v1",
        safety_policy_hash=safety_policy_hash,
        calibration_version="cal-v1",
    )


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
    evidence_hash: str = "evidence-ok",
) -> SkillExecutionRecord:
    return SkillExecutionRecord(
        execution_id=execution_id,
        template_id="tmpl-grasp",
        task_id=f"task-{execution_id}",
        plan_id="plan-1",
        step_id="step-grasp",
        success=success,
        safety_decision=safety_decision,
        failure_reason="" if success else "grasp failed",
        duration_ms=1_100,
        local_retry_count=0,
        cloud_replan_count=0,
        scene_confidence=0.9,
        network_quality=0.8,
        executed_at=NOW,
        evidence_hash=evidence_hash,
    )


def test_candidate_template_promotes_to_trusted_after_verified_successes() -> None:
    repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    template = repo.save_template(_template())

    assert template.status == SkillTemplateStatus.CANDIDATE

    repo.save_execution_record(_record("exec-1"))
    repo.save_execution_record(_record("exec-2"))
    promoted = repo.promote_template(
        "tmpl-grasp",
        policy=SkillCachePromotionPolicy(
            min_successes=2,
            min_recent_success_rate=0.9,
            quarantine_failures=2,
        ),
        expected_template_version=1,
    )

    assert promoted.status == SkillTemplateStatus.TRUSTED
    stats = repo.get_statistics("tmpl-grasp")
    assert stats.total_executions == 2
    assert stats.successful_executions == 2
    assert stats.recent_success_rate == pytest.approx(1.0)
    assert stats.confidence_score > 0.0


def test_safety_rejection_quarantines_template_and_prevents_lookup() -> None:
    repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    repo.save_template(_template())

    repo.save_execution_record(
        _record(
            "exec-reject",
            success=False,
            safety_decision=SafetyDecision.REJECT,
            evidence_hash="evidence-reject",
        )
    )

    stats = repo.get_statistics("tmpl-grasp")
    quarantined = repo.get_template("tmpl-grasp")
    assert quarantined is not None
    assert stats.safety_rejection_count == 1
    assert quarantined.status == SkillTemplateStatus.QUARANTINED
    assert repo.lookup_templates(_key()).match_type == "no_match"


def test_policy_hash_change_prevents_cache_hit() -> None:
    repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    repo.save_template(_template())

    lookup = repo.lookup_templates(_key(safety_policy_hash="safety-v2"))

    assert lookup.match_type == "no_match"
    assert "safety_policy_hash_mismatch" in lookup.reason_codes


def test_template_expiry_invalidates_lookup() -> None:
    after_expiry = NOW + timedelta(days=2)
    repo = InMemorySkillCacheRepository(clock=lambda: after_expiry)
    repo.save_template(_template())

    expired = repo.expire_templates(now=after_expiry)

    assert expired == ["tmpl-grasp"]
    template = repo.get_template("tmpl-grasp")
    assert template is not None
    assert template.status == SkillTemplateStatus.EXPIRED
    assert repo.lookup_templates(_key()).match_type == "no_match"


def test_execution_record_idempotency_detects_conflicting_payload() -> None:
    repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    repo.save_template(_template())
    repo.save_execution_record(_record("exec-same"))

    same = repo.save_execution_record(_record("exec-same"))
    assert same.execution_id == "exec-same"

    with pytest.raises(IdempotencyConflictError):
        repo.save_execution_record(_record("exec-same", success=False))


def test_template_cas_rejects_stale_update() -> None:
    repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    repo.save_template(_template())

    ok = repo.compare_and_set_template_version(
        "tmpl-grasp",
        expected_template_version=1,
        new_status=SkillTemplateStatus.TRUSTED,
    )
    stale = repo.compare_and_set_template_version(
        "tmpl-grasp",
        expected_template_version=1,
        new_status=SkillTemplateStatus.INVALIDATED,
    )

    assert ok
    assert not stale
    template = repo.get_template("tmpl-grasp")
    assert template is not None
    assert template.status == SkillTemplateStatus.TRUSTED


def test_sqlite_skill_cache_recovers_template_and_statistics(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "skill-cache.db"
    repo = SQLiteSkillCacheRepository(db_path, clock=lambda: NOW)
    repo.save_template(_template())
    repo.save_execution_record(_record("exec-1"))
    repo.close()

    reopened = SQLiteSkillCacheRepository(db_path, clock=lambda: NOW)
    template = reopened.get_template("tmpl-grasp")
    assert template is not None
    assert template.template_id == "tmpl-grasp"
    assert reopened.get_statistics("tmpl-grasp").successful_executions == 1
    reopened.close()
