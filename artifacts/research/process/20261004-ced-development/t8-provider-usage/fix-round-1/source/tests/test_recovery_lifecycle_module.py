"""Software-only durable task verification pool; no physical recovery acceptance."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository


@pytest.fixture(params=["memory", "sqlite"])
def lifecycle_repo(request, tmp_path):
    repo = (
        SQLiteEventAutonomyRepository(tmp_path / "lifecycle.sqlite")
        if request.param == "sqlite"
        else InMemoryEventAutonomyRepository()
    )
    yield repo
    if request.param == "sqlite":
        repo.close()


def verification_pool():
    now = datetime.now(UTC)
    return VerificationBudgetState(
        remaining_reobservations=1,
        remaining_retries=0,
        consecutive_no_progress=2,
        deadline_at=now + timedelta(seconds=60),
        limits=VerificationBudget(2, 0, 3, 60),
        previous_conditions={"object_held:obj-1": ("FAIL", 0.1)},
        verification_rounds=3,
    )


def test_task_verification_initialize_preserves_spent_pool_and_deadline(lifecycle_repo):
    original = lifecycle_repo.initialize_verification_budget_if_absent("task", verification_pool())
    replacement = VerificationBudgetState.start(VerificationBudget(99, 99, 99, 999))
    actual = lifecycle_repo.initialize_verification_budget_if_absent("task", replacement)
    assert actual == original
    assert actual.state.remaining_reobservations == 1
    assert actual.state.consecutive_no_progress == 2
    assert actual.state.deadline_at == original.state.deadline_at
    assert actual.state.limits.max_no_progress == 3
    assert actual.revision == original.revision


def test_task_pool_read_and_initialize_do_not_expose_mutable_saved_state(lifecycle_repo):
    proposed = verification_pool()
    original_deadline = proposed.deadline_at
    saved = lifecycle_repo.initialize_verification_budget_if_absent("task", proposed)
    proposed.previous_conditions.clear()
    proposed.remaining_reobservations = 99
    saved.state.previous_conditions.clear()
    saved.state.deadline_at += timedelta(days=1)
    read = lifecycle_repo.get_verification_budget("task")
    assert read.state.remaining_reobservations == 1
    assert read.state.previous_conditions == {"object_held:obj-1": ("FAIL", 0.1)}
    assert read.state.deadline_at == original_deadline
    read.state.previous_conditions.clear()
    assert lifecycle_repo.get_verification_budget("task").state.previous_conditions


def test_sqlite_restart_preserves_task_pool_complete_bytes(tmp_path):
    path = tmp_path / "restart.sqlite"
    repo = SQLiteEventAutonomyRepository(path)
    original = repo.initialize_verification_budget_if_absent("task", verification_pool())
    row_before = tuple(
        repo._conn.execute("SELECT * FROM verification_budgets WHERE task_id='task'").fetchone()
    )
    repo.close()
    restarted = SQLiteEventAutonomyRepository(path)
    actual = restarted.initialize_verification_budget_if_absent(
        "task", VerificationBudgetState.start(VerificationBudget(100, 100, 100, 999))
    )
    assert actual == original
    assert (
        tuple(
            restarted._conn.execute(
                "SELECT * FROM verification_budgets WHERE task_id='task'"
            ).fetchone()
        )
        == row_before
    )
    restarted.close()


def test_two_sqlite_initializers_share_one_task_pool_without_refilling(tmp_path):
    path = tmp_path / "race.sqlite"
    first, second = (SQLiteEventAutonomyRepository(path) for _ in range(2))
    proposals = [verification_pool(), verification_pool()]
    proposals[1].remaining_reobservations = 0
    barrier = Barrier(2)

    def initialize(repo, proposal):
        barrier.wait(timeout=5)
        return repo.initialize_verification_budget_if_absent("task", proposal)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(initialize, repo, proposal)
            for repo, proposal in zip((first, second), proposals, strict=True)
        ]
        results = [future.result(timeout=10) for future in futures]
    assert results[0] == results[1]
    assert first.get_verification_budget("task") == second.get_verification_budget("task")
    assert first._conn.execute("SELECT count(*) FROM verification_budgets").fetchone()[0] == 1
    first.close()
    second.close()


@pytest.mark.parametrize("invalid", ["", "   "])
def test_task_verification_pool_rejects_missing_task_identity(lifecycle_repo, invalid):
    with pytest.raises(ValueError):
        lifecycle_repo.initialize_verification_budget_if_absent(invalid, verification_pool())
    assert lifecycle_repo.get_verification_budget(invalid) is None


@pytest.mark.parametrize("retry_available", [False, True])
def test_task_pool_retry_allowance_only_mirrors_existing_authority(lifecycle_repo, retry_available):
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget

    now = datetime.now(UTC)
    if retry_available:
        lifecycle_repo.initialize_retry_budget_if_absent(
            RecoveryBudget(
                budget_id="authority",
                task_id="task",
                remaining_retries=1,
                task_total_retry_limit=4,
                task_retry_count=3,
                retry_count_used=3,
                retry_deadline=now + timedelta(seconds=10),
            )
        )
    proposed = VerificationBudgetState.start(VerificationBudget(2, 8, 3, 60), now=now)
    actual = lifecycle_repo.initialize_verification_budget_if_absent("task", proposed)
    assert actual.state.remaining_retries == (1 if retry_available else 0)
    if retry_available:
        assert actual.state.deadline_at == now + timedelta(seconds=10)


def detected_record(
    repo, *, event_id="event-1", recovery_id="recovery-1", required_preconditions=()
):
    """Complete software failure identity, with no gateway or physical effect."""
    from cloud_edge_robot_arm.contracts.models import EdgeEvent, ExecutionCheckpoint, RecoveryBudget
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryRecord
    from tests.test_phase6_2_replan_resume import _contract

    now = datetime.now(UTC)
    active = repo.get_active_contract("task")
    if active is None:
        contract = _contract(task_id="task", retry_limit=3)
        contract.steps[1].preconditions = list(required_preconditions)
        repo.save_active_contract(contract, plan_id="plan", robot_id="robot")
        repo.initialize_retry_budget_if_absent(
            RecoveryBudget(
                budget_id="authority",
                task_id="task",
                per_step_retry_limit=3,
                per_skill_retry_limit=8,
                task_total_retry_limit=8,
                remaining_retries=8,
                retry_deadline=now + timedelta(seconds=60),
            )
        )
        repo.initialize_verification_budget_if_absent(
            "task", VerificationBudgetState.start(VerificationBudget(2, 8, 3, 60), now=now)
        )
        repo.save_execution_checkpoint(
            ExecutionCheckpoint(
                checkpoint_id="checkpoint",
                task_id="task",
                plan_id="plan",
                robot_id="robot",
                plan_version=1,
                command_seq=1,
                failed_step_id="grasp",
                execution_state="PAUSED",
                created_at=now,
                updated_at=now,
            )
        )
    repo.save_event(
        EdgeEvent(
            task_id="task",
            plan_version=1,
            command_seq=1,
            event_id=event_id,
            event_type="GRASP_FAILED",
            step_id="grasp",
            timestamp=now,
            severity="ERROR",
        )
    )
    active = repo.get_active_contract("task")
    checkpoint = repo.get_latest_execution_checkpoint("task")
    return RecoveryRecord(
        recovery_id,
        event_id,
        "task",
        f"MOCK-attempt-{event_id}",
        "DETECTED",
        repo.get_verification_budget("task").state,
        "",
        None,
        "",
        "software detection",
        plan_version=1,
        command_seq=1,
        failure_plan_version=1,
        failure_command_seq=1,
        episode_id="episode",
        step_id="grasp",
        skill="GRASP",
        payload_hash=active.contract_hash,
        checkpoint_hash=checkpoint.checkpoint_hash,
        conditions=(ConditionSpec("object_held", target_id="obj-1"),),
    )


def test_detected_recovery_is_persisted_and_remains_unresolved(lifecycle_repo):
    proposal = detected_record(lifecycle_repo)
    saved = lifecycle_repo.initialize_recovery_if_absent(proposal)
    assert saved.state == "DETECTED" and saved.resolution_observation_id == ""
    assert lifecycle_repo.get_recovery(saved.recovery_id) == saved
    assert lifecycle_repo.list_unresolved_recoveries("task") == [saved]
    assert lifecycle_repo.initialize_recovery_if_absent(proposal) == saved


def test_public_initialization_cannot_assert_authorized_or_resolved(lifecycle_repo):
    from dataclasses import replace

    proposal = detected_record(lifecycle_repo)
    for state in ("RECOVERY_AUTHORIZED", "RETRY_EXECUTED", "VERIFIED_RESOLVED"):
        with pytest.raises(ValueError):
            lifecycle_repo.initialize_recovery_if_absent(replace(proposal, state=state))
    assert lifecycle_repo.get_recovery(proposal.recovery_id) is None


def test_recovery_identity_conflict_cannot_replace_original_event(lifecycle_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError

    proposal = detected_record(lifecycle_repo)
    saved = lifecycle_repo.initialize_recovery_if_absent(proposal)
    with pytest.raises(IdempotencyConflictError):
        lifecycle_repo.initialize_recovery_if_absent(replace(proposal, event_id="decoy"))
    assert lifecycle_repo.get_recovery(proposal.recovery_id) == saved


def test_detected_record_restart_preserves_bindings_and_shared_task_pool(tmp_path):
    path = tmp_path / "record.sqlite"
    repo = SQLiteEventAutonomyRepository(path)
    proposal = detected_record(repo)
    saved = repo.initialize_recovery_if_absent(proposal)
    repo.close()
    restarted = SQLiteEventAutonomyRepository(path)
    assert restarted.get_recovery(saved.recovery_id) == saved
    assert restarted.list_unresolved_recoveries("task") == [saved]
    assert restarted.get_verification_budget("task").state == saved.budget_state
    restarted.close()


def authorization_proof(record):
    """Synthetic complete canonical inputs, explicitly no real model/robot acceptance."""
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.edge.evidence.models import (
        ActionEvidenceContract,
        CommitContext,
        DecisionEnvelope,
        VisualEvidence,
    )
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryAuthorizationEvidence
    from tests.test_visual_evidence_contract import online_evidence

    now = datetime.now(UTC)
    source = online_evidence()
    observation = type(source.observation).model_validate(
        {
            **source.observation.model_dump(),
            "captured_at": now,
            "episode_id": "episode",
            "checksum_sha256": "",
        }
    )
    online = replace(
        source,
        observation=observation,
        plan_version=1,
        command_seq=1,
        context_hash=record.checkpoint_hash,
        visual_facts={
            "target_visible": {**source.visual_facts["target_visible"], "target_id": "obj-1"},
        },
    )
    visual = VisualEvidence(
        observation.observation_id, "cal-1", now, 0.001, 0.0, "CONFIRMED", "VALID"
    )
    action = ActionEvidenceContract(
        visual,
        3.0,
        0.01,
        ("rgbd",),
        (ConditionSpec("target_visible", target_id="obj-1"),),
        record.conditions,
        1,
        1,
        record.checkpoint_hash,
    )
    decision = DecisionEnvelope(
        "MOCK-decision",
        "task",
        "episode",
        observation.observation_id,
        1,
        1,
        1,
        record.checkpoint_hash,
        record.payload_hash,
        "LOCAL_RECOVER",
        "MOCK-policy",
        "MOCK-provider",
        now,
        now + timedelta(seconds=60),
    )
    current = CommitContext(
        "task",
        "episode",
        observation.observation_id,
        1,
        1,
        1,
        record.checkpoint_hash,
        record.payload_hash,
        False,
    )
    return RecoveryAuthorizationEvidence(
        record.recovery_id, decision, current, action, online, evidence_scope="SOFTWARE_ONLY"
    )


def atomic_authorize(repo, saved, proof=None, **changes):
    params = {
        "recovery_id": saved.recovery_id,
        "expected_recovery_revision": saved.revision,
        "expected_verification_budget_revision": repo.get_verification_budget("task").revision,
        "expected_retry_count": repo.get_retry_budget("task").retry_count_used,
        "step_id": saved.step_id,
        "skill": saved.skill,
        "authorization": proof if proof is not None else authorization_proof(saved),
    }
    return repo.consume_retry_and_authorize_recovery_if_current(**{**params, **changes})


def test_atomic_authorization_spends_existing_retry_once_but_does_not_resolve(lifecycle_repo):
    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    proof = authorization_proof(saved)
    result = atomic_authorize(lifecycle_repo, saved, proof)
    assert result.authorized and result.recovery.state == "RECOVERY_AUTHORIZED"
    assert result.recovery.resolution_observation_id == ""
    assert result.retry_budget.task_retry_count == 1 and result.retry_budget.remaining_retries == 7
    assert result.retry_budget.event_retry_counts == {"event-1": 1}
    assert result.verification_budget.state.remaining_retries == 7
    assert lifecycle_repo.list_unresolved_recoveries("task") == [result.recovery]
    repeated = atomic_authorize(lifecycle_repo, saved, proof)
    assert not repeated.authorized
    assert lifecycle_repo.get_retry_budget("task").task_retry_count == 1
    assert lifecycle_repo.get_recovery(saved.recovery_id) == result.recovery


@pytest.mark.parametrize("change", ["caller_valid", "no_motion", "wrong_context", "decoy_target"])
def test_invalid_authorization_proof_cannot_spend_any_pool(lifecycle_repo, change):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict

    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    proof = authorization_proof(saved)
    if change == "caller_valid":
        proof = EvidenceVerdict("VALID", ("caller assertion",))
    elif change == "no_motion":
        proof = replace(
            proof,
            action=replace(
                proof.action, evidence=replace(proof.action.evidence, motion_bound_m_s=None)
            ),
        )
    elif change == "wrong_context":
        proof = replace(proof, current=replace(proof.current, context_hash="forged"))
    else:
        proof = replace(
            proof,
            action=replace(
                proof.action, preconditions=(ConditionSpec("target_visible", target_id="decoy"),)
            ),
        )
    retry_before = lifecycle_repo.get_retry_budget("task")
    pool_before = lifecycle_repo.get_verification_budget("task")
    result = atomic_authorize(lifecycle_repo, saved, proof)
    assert not result.authorized and result.reasons
    assert lifecycle_repo.get_recovery(saved.recovery_id) == saved
    assert lifecycle_repo.get_retry_budget("task") == retry_before
    assert lifecycle_repo.get_verification_budget("task") == pool_before


@pytest.mark.parametrize(
    "field",
    ["expected_recovery_revision", "expected_verification_budget_revision", "expected_retry_count"],
)
def test_stale_authorization_cas_cannot_spend_retry_or_advance_state(lifecycle_repo, field):
    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    before = lifecycle_repo.get_retry_budget("task")
    result = atomic_authorize(lifecycle_repo, saved, **{field: 99})
    assert not result.authorized
    assert lifecycle_repo.get_retry_budget("task") == before
    assert lifecycle_repo.get_recovery(saved.recovery_id) == saved


def test_actual_step_zero_retry_limit_cannot_use_task_maximum(lifecycle_repo):
    from dataclasses import replace

    proposal = replace(detected_record(lifecycle_repo), step_id="approach", skill="APPROACH")
    saved = lifecycle_repo.initialize_recovery_if_absent(proposal)
    result = atomic_authorize(lifecycle_repo, saved)
    assert not result.authorized and lifecycle_repo.get_retry_budget("task").task_retry_count == 0


def test_two_sqlite_authorizations_commit_one_recovery_retry_and_task_pool(tmp_path):
    path = tmp_path / "authorize.sqlite"
    first, second = (SQLiteEventAutonomyRepository(path) for _ in range(2))
    saved = first.initialize_recovery_if_absent(detected_record(first))
    proof = authorization_proof(saved)
    barrier = Barrier(2)

    def authorize(repo):
        barrier.wait(timeout=5)
        return atomic_authorize(repo, saved, proof)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=10)
            for future in [executor.submit(authorize, repo) for repo in (first, second)]
        ]
    assert sum(result.authorized for result in results) == 1
    assert first.get_retry_budget("task").task_retry_count == 1
    assert second.get_retry_budget("task").event_retry_counts == {"event-1": 1}
    assert first.get_recovery(saved.recovery_id) == second.get_recovery(saved.recovery_id)
    assert first.get_verification_budget("task") == second.get_verification_budget("task")
    first.close()
    second.close()


@pytest.mark.parametrize(
    "change",
    [
        "cancel",
        "checkpoint",
        "critical_event",
        "actual_skill_limit",
        "boolean_counters",
        "expired_retry",
    ],
)
def test_authorization_rechecks_transaction_current_guards(lifecycle_repo, change):
    from cloud_edge_robot_arm.contracts.models import EdgeEvent

    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    proof = authorization_proof(saved)
    params = {}
    if change == "cancel":
        lifecycle_repo.save_state("task", "CANCELLED", "MOCK late cancellation")
    elif change == "checkpoint":
        checkpoint = lifecycle_repo.get_latest_execution_checkpoint("task")
        lifecycle_repo.save_execution_checkpoint(
            checkpoint.model_copy(
                update={
                    "checkpoint_id": "changed",
                    "checkpoint_hash": "",
                    "updated_at": datetime.now(UTC),
                }
            )
        )
    elif change == "critical_event":
        lifecycle_repo.save_event(
            EdgeEvent(
                task_id="task",
                plan_version=1,
                command_seq=1,
                event_id="critical",
                event_type="GRASP_FAILED",
                severity="CRITICAL",
                step_id="grasp",
                timestamp=datetime.now(UTC),
            )
        )
    elif change == "actual_skill_limit":
        budget = lifecycle_repo.get_retry_budget("task")
        lifecycle_repo.save_retry_budget(
            budget.model_copy(
                update={
                    "skill_retry_counts": {"GRASP": 3},
                    "retry_count_used": 3,
                    "task_retry_count": 3,
                    "remaining_retries": 5,
                }
            )
        )
    elif change == "boolean_counters":
        params = {
            "expected_recovery_revision": False,
            "expected_verification_budget_revision": False,
            "expected_retry_count": False,
        }
    else:
        budget = lifecycle_repo.get_retry_budget("task")
        lifecycle_repo.save_retry_budget(
            budget.model_copy(
                update={
                    "retry_deadline": datetime.now(UTC) - timedelta(seconds=1),
                }
            )
        )
    before = lifecycle_repo.get_retry_budget("task")
    pool_before = lifecycle_repo.get_verification_budget("task")
    result = atomic_authorize(lifecycle_repo, saved, proof, **params)
    assert not result.authorized
    assert lifecycle_repo.get_retry_budget("task") == before
    assert lifecycle_repo.get_verification_budget("task") == pool_before
    assert lifecycle_repo.get_recovery(saved.recovery_id) == saved


def execution_proof(repo, record, *, completed=True, success=False):
    """MOCK start plus independent typed completion source, not a physical acceptance."""
    from uuid import uuid4

    from cloud_edge_robot_arm.contracts.models import ReplanExecutionReceipt, SkillExecutionResult
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryExecutionEvidence

    started_at = datetime.now(UTC)
    receipt = ReplanExecutionReceipt(
        repair_id=record.attempt_id,
        task_id=record.task_id,
        plan_version=record.plan_version,
        command_seq=record.command_seq,
        activation_token="MOCK-execution-token",
        payload_hash=record.payload_hash,
        event_id=f"MOCK-start-{record.event_id}",
        started_at=started_at,
    )
    completion = None
    if completed:
        completed_at = datetime.now(UTC)
        completion = SkillExecutionResult(
            task_id=record.task_id,
            plan_version=record.plan_version,
            command_seq=record.command_seq,
            timestamp=completed_at,
            step_id=record.step_id,
            skill=record.skill,
            scene_version=1,
            success=success,
            duration_ms=0,
            details={
                "source": "MOCK",
                "recovery_id": record.recovery_id,
                "attempt_id": record.attempt_id,
            },
        )
        previous = repo.get_latest_execution_checkpoint(record.task_id)
        repo.save_execution_checkpoint(
            previous.model_copy(
                update={
                    "checkpoint_id": uuid4().hex,
                    "checkpoint_hash": "",
                    "updated_at": completed_at,
                    "step_attempts": {record.step_id: 1},
                    "completed_step_ids": [record.step_id] if success else [],
                    "failed_step_id": "" if success else record.step_id,
                }
            )
        )
    checkpoint = repo.get_latest_execution_checkpoint(record.task_id)
    return RecoveryExecutionEvidence(
        receipt, completion, checkpoint.checkpoint_hash, evidence_scope="SOFTWARE_ONLY"
    )


def verification_snapshot(repo, record, status, *, residual=None, frame_id=None):
    from dataclasses import replace
    from uuid import uuid4

    from tests.test_visual_evidence_contract import online_evidence

    source = online_evidence()
    now = datetime.now(UTC)
    frame_id = frame_id or uuid4().hex
    observation = type(source.observation).model_validate(
        {
            **source.observation.model_dump(),
            "observation_id": frame_id,
            "frame_id": frame_id,
            "captured_at": now,
            "episode_id": record.episode_id,
            "checksum_sha256": "",
        }
    )
    fact = {
        "source": "rgbd_estimate",
        "observation_id": frame_id,
        "target_id": "obj-1",
        "identity_confirmed": True,
        "value": status == "PASS",
        "pixel": [0, 0],
    }
    if residual is not None:
        fact["measured_values"] = {"residual_m": residual}
    return replace(
        source,
        observation=observation,
        plan_version=record.plan_version,
        command_seq=record.command_seq,
        context_hash=repo.get_latest_execution_checkpoint(record.task_id).checkpoint_hash,
        visual_facts={"object_held": fact} if status != "UNKNOWN" else {},
    )


def executed_recovery(repo, *, event_id="event-1", recovery_id="recovery-1", success=False):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    saved = repo.initialize_recovery_if_absent(
        detected_record(repo, event_id=event_id, recovery_id=recovery_id)
    )
    authorized = atomic_authorize(repo, saved).recovery
    proof = execution_proof(repo, authorized, success=success)
    service = RecoveryLifecycleService(
        repository=repo,
        execution_provider=lambda _: proof,
        current_state_provider=lambda record: reservation_proof(repo, record),
    )
    executed = service.advance_recovery(recovery_id, "RECOVERY_AUTHORIZED", "RETRY_EXECUTED", ())
    return service, executed


def canonical(record, snapshot):
    from cloud_edge_robot_arm.edge.evidence.conditions import evaluate_conditions

    return evaluate_conditions(record.conditions, snapshot, now=datetime.now(UTC))


def test_missing_execution_provider_and_start_only_source_do_not_assert_execution(lifecycle_repo):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    authorized = atomic_authorize(lifecycle_repo, saved).recovery
    service = RecoveryLifecycleService(repository=lifecycle_repo)
    assert (
        service.advance_recovery(
            saved.recovery_id, "RECOVERY_AUTHORIZED", "RETRY_EXECUTED", ()
        ).state
        == "RECOVERY_AUTHORIZED"
    )
    proof = execution_proof(lifecycle_repo, authorized, completed=False)
    service = RecoveryLifecycleService(
        repository=lifecycle_repo, execution_provider=lambda _: proof
    )
    actual = service.advance_recovery(
        saved.recovery_id, "RECOVERY_AUTHORIZED", "RETRY_EXECUTED", ()
    )
    assert actual.state == "RECOVERY_AUTHORIZED" and actual.execution_receipt is None
    assert actual.resolution_observation_id == ""


def test_completed_failed_retry_is_executed_but_remains_unresolved(lifecycle_repo):
    _, executed = executed_recovery(lifecycle_repo, success=False)
    assert executed.state == "RETRY_EXECUTED" and executed.execution_receipt is not None
    assert executed.executed_at is not None and executed.resolution_observation_id == ""
    assert lifecycle_repo.list_unresolved_recoveries("task") == [executed]


def test_fresh_canonical_all_pass_resolves_only_its_event(lifecycle_repo):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    _, executed = executed_recovery(lifecycle_repo)
    snapshot = verification_snapshot(lifecycle_repo, executed, "PASS")
    service = RecoveryLifecycleService(
        repository=lifecycle_repo, evidence_provider=lambda _: snapshot
    )
    resolved = service.advance_recovery(
        executed.recovery_id, "RETRY_EXECUTED", "VERIFIED_RESOLVED", canonical(executed, snapshot)
    )
    assert resolved.state == "VERIFIED_RESOLVED"
    assert resolved.event_id == "event-1"
    assert resolved.resolution_observation_id == snapshot.observation.observation_id
    assert resolved.evidence_scope == "SOFTWARE_ONLY"
    assert lifecycle_repo.list_unresolved_recoveries("task") == [resolved]
    assert lifecycle_repo.get_event("event-1") is not None


@pytest.mark.parametrize("status", ["FAIL", "UNKNOWN"])
def test_failed_or_unknown_verification_remains_unresolved(lifecycle_repo, status):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    _, executed = executed_recovery(lifecycle_repo)
    snapshot = verification_snapshot(lifecycle_repo, executed, status)
    service = RecoveryLifecycleService(
        repository=lifecycle_repo, evidence_provider=lambda _: snapshot
    )
    actual = service.advance_recovery(
        executed.recovery_id, "RETRY_EXECUTED", "VERIFIED_RESOLVED", canonical(executed, snapshot)
    )
    assert actual.state == "RETRY_EXECUTED" and actual.resolution_observation_id == ""
    assert lifecycle_repo.list_unresolved_recoveries("task") == [actual]


def test_caller_pass_labels_without_actual_provider_cannot_resolve(lifecycle_repo):
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionVerdict
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    _, executed = executed_recovery(lifecycle_repo)
    service = RecoveryLifecycleService(repository=lifecycle_repo)
    actual = service.advance_recovery(
        executed.recovery_id,
        "RETRY_EXECUTED",
        "VERIFIED_RESOLVED",
        (ConditionVerdict("PASS", "object_held", "invented-frame"),),
    )
    assert actual.state == "RETRY_EXECUTED" and actual.resolution_observation_id == ""


@pytest.mark.parametrize("change", ["foreign_episode", "old_version", "before_execution"])
def test_pass_on_foreign_old_or_preexecution_source_cannot_resolve(lifecycle_repo, change):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    _, executed = executed_recovery(lifecycle_repo)
    snapshot = verification_snapshot(lifecycle_repo, executed, "PASS")
    if change == "old_version":
        snapshot = replace(snapshot, command_seq=99)
    else:
        observation = snapshot.observation.model_copy(
            update={
                "episode_id": "foreign" if change == "foreign_episode" else "episode",
                "captured_at": (
                    executed.execution_receipt.started_at - timedelta(seconds=1)
                    if change == "before_execution"
                    else snapshot.observation.captured_at
                ),
                "checksum_sha256": "",
            }
        )
        observation = type(observation).model_validate(observation.model_dump())
        snapshot = replace(snapshot, observation=observation)
    service = RecoveryLifecycleService(
        repository=lifecycle_repo, evidence_provider=lambda _: snapshot
    )
    actual = service.advance_recovery(
        executed.recovery_id, "RETRY_EXECUTED", "VERIFIED_RESOLVED", canonical(executed, snapshot)
    )
    assert actual.state != "VERIFIED_RESOLVED" and actual.resolution_observation_id == ""


def test_caller_verdict_must_match_canonical_actual_evidence(lifecycle_repo):
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionVerdict
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    _, executed = executed_recovery(lifecycle_repo)
    snapshot = verification_snapshot(lifecycle_repo, executed, "UNKNOWN")
    service = RecoveryLifecycleService(
        repository=lifecycle_repo, evidence_provider=lambda _: snapshot
    )
    with pytest.raises(ValueError):
        service.advance_recovery(
            executed.recovery_id,
            "RETRY_EXECUTED",
            "VERIFIED_RESOLVED",
            (ConditionVerdict("PASS", "object_held", snapshot.observation.observation_id),),
        )
    assert lifecycle_repo.get_recovery(executed.recovery_id) == executed


def verify_round(repo, recovery, status, *, residual=None, snapshot=None):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    source = snapshot or verification_snapshot(repo, recovery, status, residual=residual)
    service = RecoveryLifecycleService(repository=repo, evidence_provider=lambda _: source)
    return service.advance_recovery(
        recovery.recovery_id, "RETRY_EXECUTED", "VERIFIED_RESOLVED", canonical(recovery, source)
    )


def test_all_recovery_reader_keeps_resolved_history_and_returns_detached_task_records(
    lifecycle_repo,
):
    _, executed = executed_recovery(lifecycle_repo)
    resolved = verify_round(lifecycle_repo, executed, "PASS")
    assert lifecycle_repo.list_recoveries("task") == [resolved]
    assert lifecycle_repo.list_recoveries("other-task") == []
    detached = lifecycle_repo.list_recoveries("task")[0]
    detached.budget_state.remaining_reobservations = 0
    assert lifecycle_repo.get_recovery(resolved.recovery_id) == resolved


def test_three_nonprogress_rounds_exhaust_even_with_distinct_frames(lifecycle_repo):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    service, record = executed_recovery(lifecycle_repo)
    for index in range(3):
        if index:
            assert service.reserve_reobservation(record.recovery_id) is not None
            record = lifecycle_repo.get_recovery(record.recovery_id)
        record = verify_round(lifecycle_repo, record, "UNKNOWN")
        assert record.budget_state.consecutive_no_progress == index + 1
    assert record.state == "EXHAUSTED"
    assert record.budget_state.exhausted_reason == "no_progress_exhausted"
    assert lifecycle_repo.list_unresolved_recoveries("task") == [record]
    unavailable = RecoveryLifecycleService(repository=lifecycle_repo)
    assert unavailable.reserve_reobservation(record.recovery_id) is None


def test_unknown_to_fail_and_measured_residual_improvement_reset_only_no_progress(lifecycle_repo):
    service, record = executed_recovery(lifecycle_repo)
    record = verify_round(lifecycle_repo, record, "UNKNOWN")
    deadline = record.budget_state.deadline_at
    service.reserve_reobservation(record.recovery_id)
    record = verify_round(
        lifecycle_repo, lifecycle_repo.get_recovery(record.recovery_id), "FAIL", residual=0.2
    )
    assert record.budget_state.consecutive_no_progress == 0
    service.reserve_reobservation(record.recovery_id)
    record = verify_round(
        lifecycle_repo, lifecycle_repo.get_recovery(record.recovery_id), "FAIL", residual=0.1
    )
    assert record.budget_state.consecutive_no_progress == 0
    assert record.budget_state.remaining_reobservations == 0
    assert record.budget_state.deadline_at == deadline
    assert service.reserve_reobservation(record.recovery_id) is None
    assert lifecycle_repo.get_recovery(record.recovery_id).state == "EXHAUSTED"


def test_new_frame_provider_is_not_called_without_prior_reservation(lifecycle_repo):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    _, record = executed_recovery(lifecycle_repo)
    record = verify_round(lifecycle_repo, record, "UNKNOWN")
    calls = []
    service = RecoveryLifecycleService(
        repository=lifecycle_repo, evidence_provider=lambda _: calls.append("capture")
    )
    actual = service.advance_recovery(record.recovery_id, "RETRY_EXECUTED", "VERIFIED_RESOLVED", ())
    assert calls == [] and actual == record


def test_same_reservation_is_not_replayed_or_refilled(lifecycle_repo):
    service, record = executed_recovery(lifecycle_repo)
    first = service.reserve_reobservation(record.recovery_id)
    assert first is not None
    assert first.budget_state.remaining_reobservations == 1
    assert service.reserve_reobservation(record.recovery_id) is None
    assert lifecycle_repo.get_recovery(record.recovery_id) == first


@pytest.mark.parametrize(
    "change",
    [
        "early_start",
        "future_finish",
        "old_task",
        "old_attempt",
        "wrong_checkpoint",
        "missing_attempt_count",
    ],
)
def test_actual_completion_order_and_identity_are_required(lifecycle_repo, change):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    authorized = atomic_authorize(lifecycle_repo, saved).recovery
    proof = execution_proof(lifecycle_repo, authorized)
    if change == "early_start":
        proof = replace(
            proof,
            receipt=proof.receipt.model_copy(
                update={"started_at": datetime(2000, 1, 1, tzinfo=UTC)}
            ),
        )
    elif change == "future_finish":
        proof = replace(
            proof,
            completion=proof.completion.model_copy(
                update={"timestamp": datetime.now(UTC) + timedelta(seconds=5)}
            ),
        )
    elif change == "old_task":
        proof = replace(proof, completion=proof.completion.model_copy(update={"task_id": "other"}))
    elif change == "old_attempt":
        proof = replace(proof, receipt=proof.receipt.model_copy(update={"repair_id": "other"}))
    elif change == "wrong_checkpoint":
        proof = replace(proof, checkpoint_hash="wrong")
    else:
        from uuid import uuid4

        cp = lifecycle_repo.get_latest_execution_checkpoint("task")
        lifecycle_repo.save_execution_checkpoint(
            cp.model_copy(
                update={"checkpoint_id": uuid4().hex, "checkpoint_hash": "", "step_attempts": {}}
            )
        )
    service = RecoveryLifecycleService(
        repository=lifecycle_repo, execution_provider=lambda _: proof
    )
    actual = service.advance_recovery(
        saved.recovery_id, "RECOVERY_AUTHORIZED", "RETRY_EXECUTED", ()
    )
    assert actual == authorized


def test_public_rehashed_record_cannot_promote_or_rebind(lifecycle_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryTransitionEvidence

    _, record = executed_recovery(lifecycle_repo)
    source = verification_snapshot(lifecycle_repo, record, "PASS")
    proof = RecoveryTransitionEvidence(
        "VERIFIED_RESOLVED", tuple(canonical(record, source)), online_evidence=source
    )
    pool = lifecycle_repo.get_verification_budget("task")
    for changed in (
        replace(record, state="VERIFIED_RESOLVED"),
        replace(record, event_id="other"),
        replace(record, reason="fake"),
    ):
        with pytest.raises(ValueError):
            lifecycle_repo.advance_recovery_if_current(
                changed,
                expected_state=record.state,
                expected_revision=record.revision,
                expected_budget_revision=pool.revision,
                verified_transition=proof,
            )
    assert lifecycle_repo.get_recovery(record.recovery_id) == record


def test_reservation_restart_and_new_event_preserve_shared_spent_pool(tmp_path):
    from dataclasses import replace

    path = tmp_path / "reserved.sqlite"
    repo = SQLiteEventAutonomyRepository(path)
    service, record = executed_recovery(repo)
    reserved = service.reserve_reobservation(record.recovery_id)
    pool = repo.get_verification_budget("task")
    repo.close()
    restarted = SQLiteEventAutonomyRepository(path)
    assert restarted.get_recovery(record.recovery_id) == reserved
    assert restarted.get_verification_budget("task") == pool
    proposal = detected_record(restarted, event_id="event-2", recovery_id="recovery-2")
    proposal = replace(proposal, task_budget_revision=pool.revision)
    second = restarted.initialize_recovery_if_absent(proposal)
    assert second.budget_state == pool.state
    assert restarted.get_verification_budget("task") == pool
    restarted.close()


def test_initial_task_mirror_respects_already_spent_frozen_retry_cap(lifecycle_repo):
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget

    lifecycle_repo.initialize_retry_budget_if_absent(
        RecoveryBudget(
            task_id="task",
            per_step_retry_limit=9,
            per_skill_retry_limit=9,
            task_total_retry_limit=9,
            task_retry_count=2,
            retry_count_used=2,
            remaining_retries=7,
        )
    )
    record = lifecycle_repo.initialize_verification_budget_if_absent(
        "task", VerificationBudgetState.start(VerificationBudget(2, 2, 3, 60))
    )
    assert record.state.remaining_retries == 0


def test_two_connections_reserve_exactly_one_allowance(tmp_path):
    path = tmp_path / "reserve-race.sqlite"
    first = SQLiteEventAutonomyRepository(path)
    _, record = executed_recovery(first)
    second = SQLiteEventAutonomyRepository(path)
    pool = first.get_verification_budget("task")
    barrier = Barrier(2)

    def reserve(repo):
        barrier.wait()
        return repo.reserve_reobservation_if_current(
            recovery_id=record.recovery_id,
            expected_revision=record.revision,
            expected_budget_revision=pool.revision,
            reservation=reservation_proof(repo, record),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, (first, second)))
    assert sum(item is not None for item in results) == 1
    assert first.get_verification_budget("task").state.remaining_reobservations == 1
    first.close()
    second.close()


def test_atomic_authorization_rollback_preserves_all_three_sources(tmp_path, monkeypatch):
    path = tmp_path / "rollback.sqlite"
    repo = SQLiteEventAutonomyRepository(path)
    saved = repo.initialize_recovery_if_absent(detected_record(repo))
    pool = repo.get_verification_budget("task")
    retry = repo.get_retry_budget("task")
    original = repo._update_recovery_locked

    def fail_after_update(record, budget):
        original(record, budget)
        raise RuntimeError("MOCK transaction fault")

    monkeypatch.setattr(repo, "_update_recovery_locked", fail_after_update)
    with pytest.raises(RuntimeError, match="MOCK transaction fault"):
        atomic_authorize(repo, saved)
    assert repo.get_recovery(saved.recovery_id) == saved
    assert repo.get_retry_budget("task") == retry
    assert repo.get_verification_budget("task") == pool
    repo.close()
    restarted = SQLiteEventAutonomyRepository(path)
    assert restarted.get_recovery(saved.recovery_id) == saved
    assert restarted.get_retry_budget("task") == retry
    assert restarted.get_verification_budget("task") == pool
    restarted.close()


def test_resolution_rechecks_current_cancel_after_provider_returns(lifecycle_repo):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    _, record = executed_recovery(lifecycle_repo)
    source = verification_snapshot(lifecycle_repo, record, "PASS")

    def acquire(_):
        lifecycle_repo.save_state("task", "CANCELLED", "MOCK cancellation race")
        return source

    service = RecoveryLifecycleService(repository=lifecycle_repo, evidence_provider=acquire)
    result = service.advance_recovery(
        record.recovery_id, "RETRY_EXECUTED", "VERIFIED_RESOLVED", canonical(record, source)
    )
    assert result == record and not result.resolution_observation_id


def test_sqlite_rehashed_payload_cannot_change_indexed_task_or_revision(tmp_path):
    import json
    from dataclasses import replace

    repo = SQLiteEventAutonomyRepository(tmp_path / "index.sqlite")
    saved = repo.initialize_recovery_if_absent(detected_record(repo))
    pool = repo.get_verification_budget("task")
    changed = replace(saved, task_id="foreign-task")
    repo._conn.execute(
        "UPDATE recovery_records SET payload_json=?,content_hash=? WHERE recovery_id=?",
        (json.dumps(changed.to_payload()), changed.content_hash(), saved.recovery_id),
    )
    repo._conn.commit()
    with pytest.raises(ValueError):
        repo.get_recovery(saved.recovery_id)
    changed_pool = replace(pool, task_id="foreign-task", revision=99, content_hash="")
    repo._conn.execute(
        "UPDATE verification_budgets SET payload_json=?,content_hash=? WHERE task_id=?",
        (json.dumps(changed_pool.to_payload()), changed_pool.content_hash, "task"),
    )
    repo._conn.commit()
    with pytest.raises(ValueError):
        repo.get_verification_budget("task")
    repo.close()


def test_nonprogress_pool_cannot_be_revived_through_new_authorization(lifecycle_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryTransitionEvidence

    service, record = executed_recovery(lifecycle_repo)
    for index in range(3):
        if index:
            service.reserve_reobservation(record.recovery_id)
            record = lifecycle_repo.get_recovery(record.recovery_id)
        record = verify_round(lifecycle_repo, record, "UNKNOWN")
    pool = lifecycle_repo.get_verification_budget("task")
    proposal = detected_record(lifecycle_repo, event_id="new-event", recovery_id="new-recovery")
    proposal = replace(proposal, task_budget_revision=pool.revision)
    saved = lifecycle_repo.initialize_recovery_if_absent(proposal)
    retry = lifecycle_repo.get_retry_budget("task")
    actual = atomic_authorize(lifecycle_repo, saved)
    assert not actual.authorized and lifecycle_repo.get_retry_budget("task") == retry
    terminal = lifecycle_repo.advance_recovery_if_current(
        saved,
        expected_state="DETECTED",
        expected_revision=saved.revision,
        expected_budget_revision=pool.revision,
        verified_transition=RecoveryTransitionEvidence("EXHAUSTED"),
    )
    assert terminal.state == "EXHAUSTED"
    assert terminal.budget_state.deadline_at == pool.state.deadline_at


def test_best_condition_progress_survives_event_changes(lifecycle_repo):
    from dataclasses import replace

    service, first = executed_recovery(lifecycle_repo)
    first = verify_round(lifecycle_repo, first, "FAIL", residual=0.1)
    pool = lifecycle_repo.get_verification_budget("task")
    proposal = detected_record(lifecycle_repo, event_id="new-event", recovery_id="new-recovery")
    proposal = replace(proposal, task_budget_revision=pool.revision)
    second = lifecycle_repo.initialize_recovery_if_absent(proposal)
    authorized = atomic_authorize(lifecycle_repo, second).recovery
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    proof = execution_proof(lifecycle_repo, authorized)
    service = RecoveryLifecycleService(
        repository=lifecycle_repo, execution_provider=lambda _: proof
    )
    second = service.advance_recovery(
        second.recovery_id, "RECOVERY_AUTHORIZED", "RETRY_EXECUTED", ()
    )
    second = verify_round(lifecycle_repo, second, "FAIL", residual=0.2)
    assert second.budget_state.consecutive_no_progress == 2
    assert second.budget_state.deadline_at == first.budget_state.deadline_at
    assert len(lifecycle_repo.list_unresolved_recoveries("task")) == 2


def test_failure_events_cannot_share_one_execution_attempt_identity(lifecycle_repo):
    from dataclasses import replace

    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    second = detected_record(lifecycle_repo, event_id="second-event", recovery_id="second-recovery")
    with pytest.raises(ValueError):
        lifecycle_repo.initialize_recovery_if_absent(replace(second, attempt_id=saved.attempt_id))
    assert lifecycle_repo.get_recovery(second.recovery_id) is None


def test_same_camera_frame_replay_is_not_fresh_resolution(lifecycle_repo):
    from dataclasses import replace

    service, record = executed_recovery(lifecycle_repo)
    source = verification_snapshot(lifecycle_repo, record, "FAIL")
    record = verify_round(lifecycle_repo, record, "FAIL", snapshot=source)
    service.reserve_reobservation(record.recovery_id)
    record = lifecycle_repo.get_recovery(record.recovery_id)
    pass_source = verification_snapshot(lifecycle_repo, record, "PASS")
    observation = type(pass_source.observation).model_validate(
        {
            **pass_source.observation.model_dump(),
            "observation_id": source.observation.observation_id,
            "frame_id": source.observation.frame_id,
            "checksum_sha256": "",
        }
    )
    fact = dict(pass_source.visual_facts["object_held"])
    fact["observation_id"] = observation.observation_id
    pass_source = replace(pass_source, observation=observation, visual_facts={"object_held": fact})
    result = verify_round(lifecycle_repo, record, "PASS", snapshot=pass_source)
    assert result.state != "VERIFIED_RESOLVED" and not result.resolution_observation_id


def test_authorization_conditions_cannot_select_decoy_target(lifecycle_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    proposal = detected_record(lifecycle_repo)
    proposal = replace(proposal, conditions=(ConditionSpec("object_held", target_id="decoy"),))
    saved = lifecycle_repo.initialize_recovery_if_absent(proposal)
    actual = atomic_authorize(lifecycle_repo, saved)
    assert not actual.authorized
    assert lifecycle_repo.get_retry_budget("task").retry_count_used == 0


def test_nested_condition_bindings_are_not_mutable_aliases(lifecycle_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    tolerances = {"nested": {"margin": [1, 2]}}
    proposal = replace(
        detected_record(lifecycle_repo),
        conditions=(ConditionSpec("object_held", "obj-1", tolerances),),
    )
    saved = lifecycle_repo.initialize_recovery_if_absent(proposal)
    tolerances["nested"]["margin"][0] = 99
    assert lifecycle_repo.get_recovery(saved.recovery_id) == saved
    with pytest.raises(TypeError):
        saved.conditions[0].tolerances["nested"]["margin"][0] = 77


@pytest.mark.parametrize("field", ["estop_engaged", "collision_detected", "connected"])
def test_robot_hard_stop_blocks_authorization_before_any_debit(lifecycle_repo, field):
    from dataclasses import replace

    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    proof = authorization_proof(saved)
    robot = proof.online_evidence.robot_state.model_copy(update={field: field != "connected"})
    proof = replace(proof, online_evidence=replace(proof.online_evidence, robot_state=robot))
    pool = lifecycle_repo.get_verification_budget("task")
    retry = lifecycle_repo.get_retry_budget("task")
    assert not atomic_authorize(lifecycle_repo, saved, proof).authorized
    assert lifecycle_repo.get_verification_budget("task") == pool
    assert lifecycle_repo.get_retry_budget("task") == retry


def test_authorization_must_cover_full_timeout(lifecycle_repo):
    from dataclasses import replace

    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    proof = authorization_proof(saved)
    proof = replace(proof, action=replace(proof.action, expected_duration_s=1.0))
    assert not atomic_authorize(lifecycle_repo, saved, proof).authorized
    assert lifecycle_repo.get_retry_budget("task").retry_count_used == 0


@pytest.mark.parametrize("field", ["estop_engaged", "collision_detected", "connected"])
def test_robot_hard_stop_blocks_resolution_even_when_object_condition_passes(lifecycle_repo, field):
    from dataclasses import replace

    _, record = executed_recovery(lifecycle_repo)
    source = verification_snapshot(lifecycle_repo, record, "PASS")
    source = replace(
        source, robot_state=source.robot_state.model_copy(update={field: field != "connected"})
    )
    actual = verify_round(lifecycle_repo, record, "PASS", snapshot=source)
    assert actual == record and not actual.resolution_observation_id


def test_grasp_visible_alone_cannot_be_recovery_success(lifecycle_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    proposal = replace(
        detected_record(lifecycle_repo), conditions=(ConditionSpec("target_visible", "obj-1"),)
    )
    saved = lifecycle_repo.initialize_recovery_if_absent(proposal)
    assert not atomic_authorize(lifecycle_repo, saved).authorized


@pytest.mark.parametrize("scope", ["UNAVAILABLE", "ACTUAL_SOURCE"])
def test_unavailable_or_uncertified_actual_source_cannot_authorize_legacy_empty_steps(
    lifecycle_repo, scope
):
    from dataclasses import replace

    saved = lifecycle_repo.initialize_recovery_if_absent(detected_record(lifecycle_repo))
    proof = replace(authorization_proof(saved), evidence_scope=scope)
    assert not atomic_authorize(lifecycle_repo, saved, proof).authorized


def test_absent_current_state_provider_cannot_reserve_recapture(lifecycle_repo):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryLifecycleService

    _, record = executed_recovery(lifecycle_repo)
    pool = lifecycle_repo.get_verification_budget("task")
    service = RecoveryLifecycleService(repository=lifecycle_repo)
    assert service.reserve_reobservation(record.recovery_id) is None
    assert lifecycle_repo.get_verification_budget("task") == pool


def reservation_proof(repo, record, *, robot_changes=None):
    from cloud_edge_robot_arm.contracts.models import RobotState
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryReservationEvidence

    return RecoveryReservationEvidence(
        RobotState(connected=True, **(robot_changes or {})),
        repo.get_latest_execution_checkpoint(record.task_id).checkpoint_hash,
        datetime.now(UTC),
        evidence_scope="SOFTWARE_ONLY",
    )


def test_genuine_software_lifecycle_resolution_cannot_unblock_production_completion(lifecycle_repo):
    from cloud_edge_robot_arm.edge.completion_evaluator import CompletionEvaluator

    _, executed = executed_recovery(lifecycle_repo)
    resolved = verify_round(lifecycle_repo, executed, "PASS")
    contract = lifecycle_repo.get_active_contract("task").contract
    result = CompletionEvaluator(repository=lifecycle_repo).evaluate(
        contract=contract,
        completed_step_ids=[item.step_id for item in contract.steps],
        completion_criteria_results={"object_placed": True},
        final_safety_decision="ALLOW",
        final_robot_state={"connected": True, "gripper_open": True},
        final_target_state={"object_at_target": True},
        last_scene_update_at=datetime.now(UTC),
    )
    assert resolved.state == "VERIFIED_RESOLVED" and resolved.evidence_scope == "SOFTWARE_ONLY"
    assert not result.completed
    assert "CHECK_8_UNRESOLVED_RECOVERIES" in result.failed_checks
    assert result.evidence["unresolved_recoveries"] == [resolved.recovery_id]


@pytest.mark.parametrize(
    "change",
    [
        "estop",
        "collision",
        "disconnected",
        "future",
        "stale",
        "foreign_checkpoint",
        "unavailable_scope",
    ],
)
def test_reservation_requires_current_safe_source_before_capture(lifecycle_repo, change):
    from dataclasses import replace

    _, record = executed_recovery(lifecycle_repo)
    pool = lifecycle_repo.get_verification_budget("task")
    proof = reservation_proof(lifecycle_repo, record)
    if change in {"estop", "collision", "disconnected"}:
        field = {
            "estop": "estop_engaged",
            "collision": "collision_detected",
            "disconnected": "connected",
        }[change]
        proof = replace(
            proof, robot_state=proof.robot_state.model_copy(update={field: field != "connected"})
        )
    elif change in {"future", "stale"}:
        proof = replace(
            proof,
            captured_at=datetime.now(UTC) + timedelta(seconds=1 if change == "future" else -10),
        )
    elif change == "foreign_checkpoint":
        proof = replace(proof, checkpoint_hash="foreign")
    else:
        proof = replace(proof, evidence_scope="UNAVAILABLE")
    result = lifecycle_repo.reserve_reobservation_if_current(
        recovery_id=record.recovery_id,
        expected_revision=record.revision,
        expected_budget_revision=pool.revision,
        reservation=proof,
    )
    assert result is None
    assert lifecycle_repo.get_recovery(record.recovery_id) == record
    assert lifecycle_repo.get_verification_budget("task") == pool


def test_expired_preflight_does_not_acquire_another_evidence_frame(lifecycle_repo, monkeypatch):
    import cloud_edge_robot_arm.edge.recovery.lifecycle as lifecycle

    _, record = executed_recovery(lifecycle_repo)
    source = verification_snapshot(lifecycle_repo, record, "UNKNOWN")
    future = record.budget_state.deadline_at + timedelta(seconds=1)
    monkeypatch.setattr(lifecycle, "_utc_clock", lambda: future)
    calls = []

    def acquire(_):
        calls.append("MOCK acquisition")
        return source

    service = lifecycle.RecoveryLifecycleService(
        repository=lifecycle_repo, evidence_provider=acquire
    )
    service.advance_recovery(record.recovery_id, "RETRY_EXECUTED", "VERIFIED_RESOLVED", ())
    assert calls == []


def test_existing_action_contract_already_isolates_original_nested_condition_maps():
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    repo = InMemoryEventAutonomyRepository()
    record = repo.initialize_recovery_if_absent(detected_record(repo))
    original = authorization_proof(record)
    tolerances = {"nested": {"values": [1, 2]}}
    action = replace(
        original.action, preconditions=(ConditionSpec("target_visible", "obj-1", tolerances),)
    )
    proof = replace(original, action=action)
    tolerances["nested"]["values"][0] = 99
    assert proof.action.preconditions[0].tolerances["nested"]["values"] == (1, 2)
    with pytest.raises(TypeError):
        proof.action.preconditions[0].tolerances["nested"]["values"][0] = 77


def test_original_required_preconditions_cannot_be_dropped(lifecycle_repo):
    saved = lifecycle_repo.initialize_recovery_if_absent(
        detected_record(lifecycle_repo, required_preconditions=("gripper_open",))
    )
    proof = authorization_proof(saved)
    pool = lifecycle_repo.get_verification_budget("task")
    retry = lifecycle_repo.get_retry_budget("task")
    assert not atomic_authorize(lifecycle_repo, saved, proof).authorized
    assert lifecycle_repo.get_verification_budget("task") == pool
    assert lifecycle_repo.get_retry_budget("task") == retry


def test_bound_required_preconditions_are_validated_canonically(lifecycle_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    saved = lifecycle_repo.initialize_recovery_if_absent(
        detected_record(lifecycle_repo, required_preconditions=("gripper_open",))
    )
    proof = authorization_proof(saved)
    proof = replace(
        proof,
        action=replace(
            proof.action,
            preconditions=(
                *proof.action.preconditions,
                ConditionSpec("gripper_open"),
            ),
        ),
    )
    assert atomic_authorize(lifecycle_repo, saved, proof).authorized


@pytest.mark.parametrize("target", [None, "decoy"])
def test_required_precondition_cannot_bind_an_unselected_object(lifecycle_repo, target):
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    saved = lifecycle_repo.initialize_recovery_if_absent(
        detected_record(lifecycle_repo, required_preconditions=("target_visible",))
    )
    proof = authorization_proof(saved)
    proof = replace(
        proof,
        action=replace(proof.action, preconditions=(ConditionSpec("target_visible", target),)),
        online_evidence=replace(
            proof.online_evidence,
            visual_facts={
                "target_visible": {
                    **proof.online_evidence.visual_facts["target_visible"],
                    "target_id": "decoy",
                }
            },
        ),
    )
    assert not atomic_authorize(lifecycle_repo, saved, proof).authorized
    assert lifecycle_repo.get_retry_budget("task").retry_count_used == 0
