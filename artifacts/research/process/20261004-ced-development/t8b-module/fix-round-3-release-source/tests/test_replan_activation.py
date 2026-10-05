"""Software-only staged replan contracts and persistent recovery-budget boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from cloud_edge_robot_arm.contracts.models import RecoveryBudget
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def spent_budget():
    return RecoveryBudget(
        budget_id="original",
        task_id="task",
        per_step_retry_limit=3,
        per_skill_retry_limit=5,
        task_total_retry_limit=8,
        retry_count_used=2,
        task_retry_count=2,
        step_retry_counts={"step": 2},
        skill_retry_counts={"GRASP": 2},
        event_retry_counts={"event-1": 1, "event-2": 1},
        remaining_retries=1,
        retry_deadline=NOW + timedelta(seconds=60),
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize("sqlite", [False, True])
def test_atomic_budget_initialize_preserves_original_limits_counts_deadline(tmp_path, sqlite):
    repo = (
        SQLiteEventAutonomyRepository(tmp_path / "event.sqlite")
        if sqlite
        else (InMemoryEventAutonomyRepository())
    )
    original = repo.initialize_retry_budget_if_absent(spent_budget())
    if sqlite:
        before_bytes = tuple(
            repo._conn.execute("SELECT * FROM recovery_budgets WHERE task_id='task'").fetchone()
        )
        repo.close()
        repo = SQLiteEventAutonomyRepository(tmp_path / "event.sqlite")
    reset = spent_budget().model_copy(
        update={
            "budget_id": "new",
            "per_step_retry_limit": 99,
            "retry_count_used": 0,
            "task_retry_count": 0,
            "step_retry_counts": {},
            "skill_retry_counts": {},
            "event_retry_counts": {},
            "remaining_retries": 99,
            "retry_deadline": NOW + timedelta(days=1),
            "updated_at": NOW + timedelta(days=1),
        }
    )
    result = repo.initialize_retry_budget_if_absent(reset)
    assert result == original
    assert repo.get_retry_budget("task") == original
    if sqlite:
        assert (
            tuple(
                repo._conn.execute("SELECT * FROM recovery_budgets WHERE task_id='task'").fetchone()
            )
            == before_bytes
        )
        repo.close()


@pytest.mark.parametrize("sqlite", [False, True])
def test_atomic_budget_initialize_returns_an_independent_copy(tmp_path, sqlite):
    repo = (
        SQLiteEventAutonomyRepository(tmp_path / "event.sqlite")
        if sqlite
        else (InMemoryEventAutonomyRepository())
    )
    proposed = spent_budget()
    saved = repo.initialize_retry_budget_if_absent(proposed)
    proposed.event_retry_counts.clear()
    saved.event_retry_counts.clear()
    again = repo.initialize_retry_budget_if_absent(spent_budget())
    again.step_retry_counts.clear()
    assert repo.get_retry_budget("task") == spent_budget()
    if sqlite:
        repo.close()


def test_two_sqlite_initializers_create_one_frozen_budget(tmp_path):
    path = tmp_path / "event.sqlite"
    first = SQLiteEventAutonomyRepository(path)
    second = SQLiteEventAutonomyRepository(path)
    barrier = Barrier(2)

    def initialize(repo, proposal):
        barrier.wait(timeout=5)
        return repo.initialize_retry_budget_if_absent(proposal)

    original = spent_budget()
    competing = original.model_copy(update={"budget_id": "competing", "remaining_retries": 0})
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(initialize, first, original)
        b = pool.submit(initialize, second, competing)
        results = [a.result(timeout=10), b.result(timeout=10)]
    assert results[0] == results[1]
    assert results[0] in (original, competing)
    assert first.get_retry_budget("task") == second.get_retry_budget("task") == results[0]
    assert first._conn.execute("SELECT count(*) FROM recovery_budgets").fetchone()[0] == 1
    first.close()
    second.close()


def setup_replan(repo):
    """Build a software-only failed-contract checkpoint; no robot is invoked."""
    from cloud_edge_robot_arm.contracts.models import (
        EdgeEvent,
        EdgeEventType,
        ExecutionCheckpoint,
        FailureSummary,
        LocalReplanningRequest,
        LocalReplanningResponse,
    )
    from tests.test_phase6_2_replan_resume import _contract

    contract = _contract(task_id="task").model_copy(
        update={
            "timestamp": NOW,
            "issued_at": NOW,
            "valid_until": NOW + timedelta(seconds=60),
        }
    )
    repo.save_active_contract(contract, plan_id="plan", robot_id="robot")
    repo.save_event(
        EdgeEvent(
            task_id="task",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            event_id="failure",
            event_type=EdgeEventType.GRASP_FAILED,
            step_id="grasp",
            severity="ERROR",
        )
    )
    repo.save_failure_summary(
        FailureSummary(
            task_id="task",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            summary_id="summary",
            failure_event_id="failure",
            failed_step_id="grasp",
            completed_step_ids=["approach"],
            reason="software failure fixture",
            local_retry_count=0,
            recovery_hint="repair",
        )
    )
    repo.save_execution_checkpoint(
        ExecutionCheckpoint(
            checkpoint_id="checkpoint",
            task_id="task",
            plan_id="plan",
            robot_id="robot",
            plan_version=1,
            command_seq=1,
            completed_step_ids=["approach"],
            failed_step_id="grasp",
            scene_version=1,
            execution_state="WAITING_CLOUD_REPLAN",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    request = LocalReplanningRequest(
        request_id="request",
        task_id="task",
        plan_id="plan",
        robot_id="robot",
        trigger_event_id="failure",
        failure_summary_id="summary",
        current_plan_version=1,
        current_command_seq=1,
        completed_step_ids=["approach"],
        failed_step_id="grasp",
        current_scene_version=1,
        requested_at=NOW,
    )
    response = LocalReplanningResponse(
        request_id="request",
        new_plan_version=2,
        new_command_seq=2,
        created_at=NOW,
        new_steps=[contract.steps[1].model_copy(update={"step_id": "repair-grasp"}, deep=True)],
    )
    return request, response


@pytest.fixture(params=[False, True], ids=["memory", "sqlite"])
def replan_repo(request, tmp_path):
    repo = (
        SQLiteEventAutonomyRepository(tmp_path / "replan.sqlite")
        if request.param
        else (InMemoryEventAutonomyRepository())
    )
    yield repo
    if request.param:
        repo.close()


class MockStagedGateway:
    """MOCK stage/resume receipts test software boundaries, never physical success."""

    def __init__(self, *, stage_change=None, after_stage=None, resume_timeout=False):
        self.calls = []
        self.stage_change = stage_change or {}
        self.after_stage = after_stage
        self.resume_timeout = resume_timeout
        self.stage_ack = None

    def stage(self, contract, repair_id):
        from cloud_edge_robot_arm.contracts.models import CommandAck
        from cloud_edge_robot_arm.repositories.event_autonomy.hashing import stable_payload_hash

        self.calls.append("stage")
        self.stage_ack = CommandAck(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            timestamp=NOW,
            accepted=True,
            status="ACCEPTED",
            request_id="mock-stage",
            details={
                "source": "MOCK",
                "repair_id": repair_id,
                "activation_token": "mock-token",
                "payload_hash": stable_payload_hash(contract),
                **self.stage_change,
            },
        )
        if self.after_stage:
            self.after_stage()
        return self.stage_ack

    def resume(self, repair_id, activation_token):
        self.calls.append("resume")
        if self.resume_timeout:
            raise TimeoutError("MOCK resume timeout")
        return self.stage_ack.model_copy(
            update={
                "request_id": "mock-resume",
                "details": {
                    **self.stage_ack.details,
                    "repair_id": repair_id,
                    "activation_token": activation_token,
                },
            },
            deep=True,
        )


def submit_proof(record, candidate, checkpoint):
    from dataclasses import replace

    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanSubmitEvidence
    from cloud_edge_robot_arm.edge.evidence.models import (
        ActionEvidenceContract,
        CommitContext,
        DecisionEnvelope,
        VisualEvidence,
    )
    from tests.test_visual_evidence_contract import online_evidence

    online = online_evidence()
    observation = type(online.observation).model_validate(
        {
            **online.observation.model_dump(),
            "captured_at": NOW,
            "episode_id": "episode",
            "checksum_sha256": "",
        }
    )
    online = replace(
        online,
        observation=observation,
        plan_version=2,
        command_seq=2,
        context_hash=record.checkpoint_hash,
    )
    evidence = VisualEvidence(
        observation_id=observation.observation_id,
        calibration_version="cal-1",
        captured_at=NOW,
        geometric_error_bound_m=0.001,
        motion_bound_m_s=0.001,
        identity_status="CONFIRMED",
        sensor_status="VALID",
    )
    action = ActionEvidenceContract(
        evidence,
        6.0,
        0.01,
        ("rgbd",),
        (),
        (),
        2,
        2,
        record.checkpoint_hash,
    )
    decision = DecisionEnvelope(
        "decision",
        "task",
        "episode",
        observation.observation_id,
        2,
        2,
        1,
        record.checkpoint_hash,
        record.payload_hash,
        "LOCAL_RECOVER",
        "policy",
        "provider",
        NOW,
        NOW + timedelta(seconds=2),
    )
    current = CommitContext(
        "task",
        "episode",
        observation.observation_id,
        2,
        2,
        1,
        record.checkpoint_hash,
        record.payload_hash,
        False,
    )
    return ReplanSubmitEvidence(decision, current, action, online)


@pytest.mark.parametrize("dispatch", [False, True])
def test_unavailable_or_dryrun_is_candidate_only_without_any_ack(replan_repo, dispatch):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)

    class LegacyGateway:
        def dispatch(self, contract):
            pytest.fail("legacy dispatch must never be used as staging")

    result = ReplanApplyService(
        repository=replan_repo, dispatcher=LegacyGateway(), clock=lambda: NOW
    ).apply(request=request, response=response, dispatch=dispatch)
    assert result.record.status == "PREPARED"
    assert result.record.candidate_contract.plan_version == 2
    assert result.record.accepted_plan_version is None
    assert result.record.executing_plan_version is None
    assert result.record.activation_token == ""
    assert result.ack is None and not result.applied
    assert replan_repo.get_active_contract("task").plan_version == 1
    assert replan_repo.get_command_ack("request") is None
    assert replan_repo.get_state("task") != "READY_TO_RESUME"


def test_mock_stage_activation_ack_is_not_execution_start_and_retry_does_not_replay(replan_repo):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)
    gateway = MockStagedGateway()
    service = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    )
    result = service.apply(request=request, response=response)
    assert result.record.status == "ACTIVATED"
    assert result.record.stage_ack == gateway.stage_ack
    assert result.record.resume_ack.accepted
    assert result.record.executing_plan_version is None
    assert result.record.start_receipt is None
    assert replan_repo.get_active_contract("task").plan_version == 2
    assert gateway.calls == ["stage", "resume"]
    again = service.apply(request=request, response=response)
    assert again.record == result.record
    assert gateway.calls == ["stage", "resume"]


@pytest.mark.parametrize(
    "details",
    [
        {"activation_token": ""},
        {"repair_id": "other"},
        {"payload_hash": "wrong"},
    ],
)
def test_mock_stage_wrong_binding_does_not_advance_active(replan_repo, details):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)
    gateway = MockStagedGateway(stage_change=details)
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert not result.applied
    assert replan_repo.get_active_contract("task").plan_version == 1
    assert gateway.calls == ["stage"]


@pytest.mark.parametrize("change", ["cancel", "checkpoint"])
def test_late_cancel_or_checkpoint_change_keeps_old_active(replan_repo, change):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)

    def late_change():
        if change == "cancel":
            replan_repo.save_state("task", "CANCELLED", "MOCK cancellation")
        else:
            checkpoint = replan_repo.get_latest_execution_checkpoint("task")
            replan_repo.save_execution_checkpoint(
                checkpoint.model_copy(
                    update={
                        "checkpoint_id": "new-checkpoint",
                        "checkpoint_hash": "",
                        "updated_at": NOW,
                    }
                )
            )

    gateway = MockStagedGateway(after_stage=late_change)
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert not result.applied
    assert replan_repo.get_active_contract("task").plan_version == 1
    assert gateway.calls == ["stage"]


def test_resume_timeout_preserves_activated_version_and_restart_never_replays(tmp_path):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    path = tmp_path / "restart.sqlite"
    repo = SQLiteEventAutonomyRepository(path)
    request, response = setup_replan(repo)
    gateway = MockStagedGateway(resume_timeout=True)
    result = ReplanApplyService(
        repository=repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert result.record.status == "ACTIVATED" and result.record.resume_ack is None
    assert repo.get_active_contract("task").plan_version == 2
    repo.close()
    restarted = SQLiteEventAutonomyRepository(path)
    again = ReplanApplyService(
        repository=restarted, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert again.record == result.record
    assert gateway.calls == ["stage", "resume"]
    restarted.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("new_plan_version", 9),
        ("payload_hash", "forged"),
        ("robot_id", "other"),
        ("status", "ACTIVATED"),
    ],
)
def test_public_save_rejects_mutated_prepared_with_original_hash(replan_repo, field, value):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
    from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError

    request, response = setup_replan(replan_repo)
    original = (
        ReplanApplyService(repository=replan_repo, clock=lambda: NOW)
        .apply(request=request, response=response, dispatch=False)
        .record
    )
    with pytest.raises((ValueError, IdempotencyConflictError)):
        replan_repo.save_replan_apply_record(original.model_copy(update={field: value}))
    assert replan_repo.get_replan_apply_record(original.apply_id) == original


@pytest.mark.parametrize("sqlite", [False, True])
def test_simultaneous_apply_claims_stage_once(tmp_path, monkeypatch, sqlite):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    path = tmp_path / "claim.sqlite"
    first = SQLiteEventAutonomyRepository(path) if sqlite else InMemoryEventAutonomyRepository()
    second = SQLiteEventAutonomyRepository(path) if sqlite else first
    request, response = setup_replan(first)
    barrier = Barrier(2)
    for repo in {first, second}:
        original = repo.get_replan_apply_record_for_request

        def get_before_both_insert(request_id, original=original):
            value = original(request_id)
            barrier.wait(timeout=5)
            return value

        monkeypatch.setattr(repo, "get_replan_apply_record_for_request", get_before_both_insert)
        original_save = repo.save_replan_apply_record

        def save_before_both_stage(record, original_save=original_save):
            saved = original_save(record)
            barrier.wait(timeout=5)
            return saved

        monkeypatch.setattr(repo, "save_replan_apply_record", save_before_both_stage)
    gateway = MockStagedGateway()
    services = [
        ReplanApplyService(
            repository=repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
        )
        for repo in (first, second)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(service.apply, request=request, response=response) for service in services
        ]
        results = [future.result(timeout=10) for future in futures]
    assert gateway.calls.count("stage") == 1
    assert gateway.calls.count("resume") == 1
    assert any(result.record.status == "ACTIVATED" for result in results)
    assert first.get_active_contract("task").plan_version == 2
    if sqlite:
        first.close()
        second.close()


def test_guard_recomputes_actual_bounds_and_does_not_accept_valid_toggle(replan_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
    from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict

    request, response = setup_replan(replan_repo)
    gateway = MockStagedGateway()
    result = ReplanApplyService(
        repository=replan_repo,
        dispatcher=gateway,
        submit_guard=lambda *_: EvidenceVerdict("VALID", ("caller label",)),
        clock=lambda: NOW,
    ).apply(request=request, response=response)
    assert result.record.status == "PREPARED"
    assert gateway.calls == []
    request = request.model_copy(update={"request_id": "bounds-request"})
    response = response.model_copy(update={"request_id": "bounds-request"})

    def missing_motion(*args):
        proof = submit_proof(*args)
        return replace(
            proof,
            action=replace(
                proof.action, evidence=replace(proof.action.evidence, motion_bound_m_s=None)
            ),
        )

    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=missing_motion, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert result.record.status == "PREPARED" and gateway.calls == []


def test_proof_cancelled_after_activation_does_not_resume_or_rollback(replan_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)
    gateway = MockStagedGateway()
    calls = []

    def changing_proof(*args):
        calls.append(args[0].status)
        proof = submit_proof(*args)
        if len(calls) == 3:
            return replace(proof, current=replace(proof.current, cancelled=True))
        return proof

    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=changing_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert calls == ["PREPARED", "EDGE_ACCEPTED", "ACTIVATED"]
    assert result.record.status == "ACTIVATED" and result.record.resume_ack is None
    assert gateway.calls == ["stage"]
    assert replan_repo.get_active_contract("task").plan_version == 2


def test_mock_start_receipt_durable_exact_idempotency_and_conflict(tmp_path):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
    from cloud_edge_robot_arm.contracts.models import ReplanExecutionReceipt

    path = tmp_path / "receipt.sqlite"
    repo = SQLiteEventAutonomyRepository(path)
    request, response = setup_replan(repo)
    result = ReplanApplyService(
        repository=repo,
        dispatcher=MockStagedGateway(),
        submit_guard=submit_proof,
        clock=lambda: NOW,
    ).apply(request=request, response=response)
    receipt = ReplanExecutionReceipt(
        repair_id=result.record.repair_id,
        task_id="task",
        plan_version=2,
        command_seq=2,
        activation_token="mock-token",
        payload_hash=result.record.payload_hash,
        event_id="MOCK-start-event",
        occurred_at=NOW,
    )
    saved_result = ReplanApplyService(repository=repo, clock=lambda: NOW).confirm_execution_started(
        receipt
    )
    saved = saved_result.record
    assert saved.status == "EXECUTION_STARTED" and saved.executing_plan_version == 2
    repo.close()
    restarted = SQLiteEventAutonomyRepository(path)
    service = ReplanApplyService(repository=restarted, clock=lambda: NOW)
    assert service.confirm_execution_started(receipt) == saved_result
    for change in (
        {"event_id": "conflicting-event"},
        {"repair_id": "unknown"},
        {"plan_version": 1},
        {"activation_token": "wrong"},
    ):
        with pytest.raises(ValueError):
            service.confirm_execution_started(receipt.model_copy(update=change))
    assert restarted.get_replan_apply_record(saved.apply_id) == saved
    restarted.close()


def test_start_receipt_for_old_active_version_is_rejected_even_after_previous_start(replan_repo):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
    from cloud_edge_robot_arm.contracts.models import ReplanExecutionReceipt

    request, response = setup_replan(replan_repo)
    service = ReplanApplyService(
        repository=replan_repo,
        dispatcher=MockStagedGateway(),
        submit_guard=submit_proof,
        clock=lambda: NOW,
    )
    result = service.apply(request=request, response=response)
    receipt = ReplanExecutionReceipt(
        repair_id=result.record.repair_id,
        task_id="task",
        plan_version=2,
        command_seq=2,
        activation_token="mock-token",
        payload_hash=result.record.payload_hash,
        event_id="MOCK-start",
        occurred_at=NOW,
    )
    service.confirm_execution_started(receipt)
    replan_repo.save_active_contract(
        result.contract.model_copy(
            update={
                "plan_version": 3,
                "command_seq": 3,
            }
        ),
        plan_id="plan",
        robot_id="robot",
    )
    with pytest.raises(ValueError):
        service.confirm_execution_started(receipt)


@pytest.mark.parametrize("boundary", ["stage", "resume"])
def test_actual_negative_mock_ack_is_preserved_without_claiming_execution(replan_repo, boundary):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)

    class NegativeGateway(MockStagedGateway):
        def stage(self, contract, repair_id):
            ack = super().stage(contract, repair_id)
            if boundary == "stage":
                self.stage_ack = ack.model_copy(
                    update={"accepted": False, "status": "REJECTED_SAFETY_CONFLICT"}
                )
            return self.stage_ack

        def resume(self, repair_id, activation_token):
            ack = super().resume(repair_id, activation_token)
            return ack.model_copy(update={"accepted": False, "status": "REJECTED_SAFETY_CONFLICT"})

    gateway = NegativeGateway()
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert result.record.start_receipt is None and result.record.executing_plan_version is None
    if boundary == "stage":
        assert result.record.status == "REJECTED" and result.record.stage_ack == gateway.stage_ack
        assert result.record.activation_token == "" and result.record.accepted_plan_version is None
        assert replan_repo.get_active_contract("task").plan_version == 1
    else:
        assert result.record.status == "ACTIVATED"
        assert result.record.resume_ack is not None and not result.record.resume_ack.accepted
        assert replan_repo.get_active_contract("task").plan_version == 2


def test_gateway_ancient_or_future_ack_cannot_activate(replan_repo):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)

    class AncientGateway(MockStagedGateway):
        def stage(self, contract, repair_id):
            ack = super().stage(contract, repair_id)
            self.stage_ack = ack.model_copy(update={"timestamp": NOW - timedelta(days=1)})
            return self.stage_ack

    gateway = AncientGateway()
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert not result.applied and replan_repo.get_active_contract("task").plan_version == 1
    assert gateway.calls == ["stage"]


def test_atomic_activation_binds_expected_active_to_frozen_previous_version(replan_repo):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)
    original = replan_repo.get_active_contract("task")

    def regress_active_for_counterexample():
        # Diagnostic repository writer simulates a mismatching active row.
        replan_repo.save_active_contract(
            original.contract.model_copy(update={"plan_version": 0}),
            plan_id="plan",
            robot_id="robot",
        )

    gateway = MockStagedGateway(after_stage=regress_active_for_counterexample)
    service = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    )
    result = service.apply(request=request, response=response)
    assert result.record.status == "EDGE_ACCEPTED"
    activated = service._updated(result.record, status="ACTIVATED")
    changed = replan_repo.advance_active_contract_if_current(
        task_id="task",
        expected_plan_version=0,
        expected_command_seq=1,
        new_contract=result.contract,
        plan_id="plan",
        robot_id="robot",
        based_on_plan_version=1,
        replan_record=activated,
        activation_guard=service._submit_verdict,
    )
    assert changed is None
    assert replan_repo.get_active_contract("task").plan_version == 0
    assert replan_repo.get_replan_apply_record(result.record.apply_id).status == "EDGE_ACCEPTED"


def test_canonical_pass_for_decoy_target_cannot_authorize_candidate(replan_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    request, response = setup_replan(replan_repo)
    response = response.model_copy(
        update={
            "new_steps": [
                response.new_steps[0].model_copy(
                    update={"preconditions": ["target_visible"]}, deep=True
                )
            ]
        },
        deep=True,
    )

    def decoy_proof(*args):
        proof = submit_proof(*args)
        facts = {key: dict(value) for key, value in proof.online_evidence.visual_facts.items()}
        facts["target_visible"]["target_id"] = "decoy"
        return replace(
            proof,
            action=replace(
                proof.action, preconditions=(ConditionSpec("target_visible", target_id="decoy"),)
            ),
            online_evidence=replace(proof.online_evidence, visual_facts=facts),
        )

    gateway = MockStagedGateway()
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=decoy_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert result.record.status == "PREPARED"
    assert gateway.calls == [] and replan_repo.get_active_contract("task").plan_version == 1


def test_stale_supplied_active_record_cannot_stage_an_old_candidate(replan_repo):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)
    old = replan_repo.get_active_contract("task")
    replan_repo.save_active_contract(
        old.contract.model_copy(
            update={
                "plan_version": 2,
                "command_seq": 2,
            }
        ),
        plan_id="plan",
        robot_id="robot",
    )
    gateway = MockStagedGateway()
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response, active_record=old)
    assert not result.applied and gateway.calls == []
    assert replan_repo.get_active_contract("task").plan_version == 2


def test_typed_submit_proof_copy_retains_frozen_facts(replan_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)
    result = ReplanApplyService(repository=replan_repo, clock=lambda: NOW).apply(
        request=request, response=response, dispatch=False
    )
    proof = submit_proof(
        result.record, result.contract, replan_repo.get_latest_execution_checkpoint("task")
    )
    copied = replace(proof, current=replace(proof.current, mode_version=2))
    assert copied.current.mode_version == 2
    with pytest.raises(TypeError):
        copied.online_evidence.visual_facts["target_visible"]["target_id"] = "decoy"


def test_sqlite_activation_rolls_back_active_if_record_write_fails(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    path = tmp_path / "atomic-failure.sqlite"
    repo = SQLiteEventAutonomyRepository(path)
    request, response = setup_replan(repo)
    original_update = repo._update_apply_locked

    def fail_only_activation(record):
        if record.status == "ACTIVATED":
            raise RuntimeError("MOCK interrupted durable activation write")
        return original_update(record)

    monkeypatch.setattr(repo, "_update_apply_locked", fail_only_activation)
    gateway = MockStagedGateway()
    with pytest.raises(RuntimeError, match="interrupted durable"):
        ReplanApplyService(
            repository=repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
        ).apply(request=request, response=response)
    repo.close()
    restarted = SQLiteEventAutonomyRepository(path)
    assert restarted.get_active_contract("task").plan_version == 1
    assert restarted.get_replan_apply_record_for_request("request").status == "EDGE_ACCEPTED"
    assert [record.status for record in restarted.list_contract_versions("task")] == ["ACTIVE"]
    assert gateway.calls == ["stage"]
    restarted.close()


@pytest.mark.parametrize("field", ["candidate", "checkpoint", "record"])
def test_submit_guard_cannot_mutate_frozen_input_to_authorize_changed_action(replan_repo, field):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)

    def mutating_guard(record, candidate, checkpoint):
        proof = submit_proof(record, candidate, checkpoint)
        if field == "candidate":
            candidate.steps[1].parameters["object_id"] = "decoy"
        elif field == "checkpoint":
            checkpoint.robot_state["cancelled"] = True
        else:
            record.completed_step_ids.clear()
        return proof

    gateway = MockStagedGateway()
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=mutating_guard, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert result.record.status == "PREPARED" and gateway.calls == []
    assert replan_repo.get_active_contract("task").plan_version == 1
    assert replan_repo.get_latest_execution_checkpoint("task").robot_state == {}
    assert replan_repo.get_replan_apply_record_for_request("request").completed_step_ids == [
        "approach"
    ]


def test_start_event_identity_cannot_be_reused_for_another_repair(replan_repo):
    from dataclasses import replace

    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
    from cloud_edge_robot_arm.contracts.models import ReplanExecutionReceipt

    request, response = setup_replan(replan_repo)
    service = ReplanApplyService(
        repository=replan_repo,
        dispatcher=MockStagedGateway(),
        submit_guard=submit_proof,
        clock=lambda: NOW,
    )
    first = service.apply(request=request, response=response)
    receipt = ReplanExecutionReceipt(
        repair_id=first.record.repair_id,
        task_id="task",
        plan_version=2,
        command_seq=2,
        activation_token="mock-token",
        payload_hash=first.record.payload_hash,
        event_id="MOCK-unique-start",
        occurred_at=NOW,
    )
    service.confirm_execution_started(receipt)
    event = replan_repo.get_event("failure")
    replan_repo.save_event(
        event.model_copy(
            update={
                "event_id": "failure2",
                "plan_version": 2,
                "command_seq": 2,
                "step_id": "repair-grasp",
            }
        )
    )
    summary = replan_repo.get_failure_summary("summary")
    replan_repo.save_failure_summary(
        summary.model_copy(
            update={
                "summary_id": "summary2",
                "summary_hash": "",
                "failure_event_id": "failure2",
                "plan_version": 2,
                "command_seq": 2,
                "failed_step_id": "repair-grasp",
            }
        )
    )
    checkpoint = replan_repo.get_latest_execution_checkpoint("task")
    replan_repo.save_execution_checkpoint(
        checkpoint.model_copy(
            update={
                "checkpoint_id": "checkpoint2",
                "checkpoint_hash": "",
                "plan_version": 2,
                "command_seq": 2,
                "failed_step_id": "repair-grasp",
            }
        )
    )
    second_request = request.model_copy(
        update={
            "request_id": "request2",
            "current_plan_version": 2,
            "current_command_seq": 2,
            "trigger_event_id": "failure2",
            "failure_summary_id": "summary2",
            "failed_step_id": "repair-grasp",
        }
    )
    second_response = response.model_copy(
        update={
            "request_id": "request2",
            "new_plan_version": 3,
            "new_command_seq": 3,
            "new_steps": [response.new_steps[0].model_copy(update={"step_id": "repair-again"})],
        }
    )

    def version3_proof(*args):
        proof = submit_proof(*args)
        return replace(
            proof,
            decision=replace(proof.decision, plan_version=3, command_seq=3),
            current=replace(proof.current, plan_version=3, command_seq=3),
            action=replace(proof.action, plan_version=3, command_seq=3),
            online_evidence=replace(proof.online_evidence, plan_version=3, command_seq=3),
        )

    second_service = ReplanApplyService(
        repository=replan_repo,
        dispatcher=MockStagedGateway(),
        submit_guard=version3_proof,
        clock=lambda: NOW,
    )
    second = second_service.apply(request=second_request, response=second_response)
    assert second.record.status == "ACTIVATED"
    with pytest.raises(ValueError):
        second_service.confirm_execution_started(
            receipt.model_copy(
                update={
                    "repair_id": second.record.repair_id,
                    "plan_version": 3,
                    "command_seq": 3,
                    "payload_hash": second.record.payload_hash,
                }
            )
        )
    assert replan_repo.get_replan_apply_record(second.record.apply_id).status == "ACTIVATED"


@pytest.mark.parametrize("field", ["event_version", "summary_version", "failed_step"])
def test_failure_sources_must_match_frozen_request_versions_and_step(replan_repo, field):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)
    summary = replan_repo.get_failure_summary("summary")
    changes = {"summary_id": "summary-bad", "summary_hash": ""}
    if field == "event_version":
        event = replan_repo.get_event("failure")
        replan_repo.save_event(
            event.model_copy(update={"event_id": "failure-bad", "plan_version": 2})
        )
        request = request.model_copy(update={"trigger_event_id": "failure-bad"})
        changes["failure_event_id"] = "failure-bad"
    elif field == "summary_version":
        changes["plan_version"] = 2
    else:
        changes["failed_step_id"] = "place"
    replan_repo.save_failure_summary(summary.model_copy(update=changes))
    request = request.model_copy(update={"failure_summary_id": "summary-bad"})
    gateway = MockStagedGateway()
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert not result.applied and gateway.calls == []
    assert replan_repo.get_active_contract("task").plan_version == 1


@pytest.mark.parametrize("change", ["cancel", "checkpoint"])
def test_change_during_durable_stage_claim_is_rechecked_before_gateway(
    replan_repo, monkeypatch, change
):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(replan_repo)
    original_update = replan_repo.update_replan_apply_record_if_current

    def claim_then_change(record, *, expected_status):
        result = original_update(record, expected_status=expected_status)
        if result is not None and record.status == "PREPARED":
            if change == "cancel":
                replan_repo.save_state("task", "CANCELLED", "MOCK cancellation after claim")
            else:
                checkpoint = replan_repo.get_latest_execution_checkpoint("task")
                replan_repo.save_execution_checkpoint(
                    checkpoint.model_copy(
                        update={
                            "checkpoint_id": "changed-during-claim",
                            "checkpoint_hash": "",
                        }
                    )
                )
        return result

    monkeypatch.setattr(replan_repo, "update_replan_apply_record_if_current", claim_then_change)
    gateway = MockStagedGateway()
    result = ReplanApplyService(
        repository=replan_repo, dispatcher=gateway, submit_guard=submit_proof, clock=lambda: NOW
    ).apply(request=request, response=response)
    assert not result.applied and gateway.calls == []
    assert result.record.status == "PREPARED" and result.record.stage_attempt_id
    assert replan_repo.get_active_contract("task").plan_version == 1


def test_receipt_uses_planned_started_at_and_canonical_serialization():
    from cloud_edge_robot_arm.contracts.models import ReplanExecutionReceipt
    receipt = ReplanExecutionReceipt(
        repair_id="repair", task_id="task", plan_version=2, command_seq=2,
        activation_token="MOCK-token", payload_hash="a" * 64, event_id="MOCK-event",
        started_at=NOW,
    )
    assert receipt.started_at == NOW
    assert receipt.model_dump(mode="json")["started_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert "occurred_at" not in receipt.model_dump(mode="json")
    compatibility = ReplanExecutionReceipt.model_validate({
        **receipt.model_dump(exclude={"started_at"}), "occurred_at": NOW,
    })
    assert compatibility == receipt
    assert "occurred_at" not in compatibility.model_dump(mode="json")


def test_confirm_started_returns_planned_replan_apply_result(replan_repo):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import (
        ReplanApplyResult,
        ReplanApplyService,
    )
    from cloud_edge_robot_arm.contracts.models import ReplanExecutionReceipt
    request, response = setup_replan(replan_repo)
    service = ReplanApplyService(repository=replan_repo, dispatcher=MockStagedGateway(),
                                submit_guard=submit_proof, clock=lambda: NOW)
    activated = service.apply(request=request, response=response)
    receipt = ReplanExecutionReceipt(
        repair_id=activated.record.repair_id, task_id="task", plan_version=2, command_seq=2,
        activation_token="mock-token", payload_hash=activated.record.payload_hash,
        event_id="MOCK-planned-return", occurred_at=NOW,
    )
    result = service.confirm_execution_started(receipt)
    assert isinstance(result, ReplanApplyResult)
    assert result.applied and result.record.status == "EXECUTION_STARTED"
    assert result.contract == activated.contract
    assert result.ack == activated.record.resume_ack and result.errors == []
    assert service.confirm_execution_started(receipt) == result


@pytest.mark.parametrize("condition,target_id,expected_staged", [
    ("object_inside_target_region", "obj-1", True),
    ("object_inside_target_region", "bin-a", False),
    ("object_inside_target_region", "decoy", False),
    ("tcp_above_region", "bin-a", True),
    ("tcp_above_region", "obj-1", False),
])
def test_placement_binds_object_extent_and_region_tcp_to_distinct_targets(
    replan_repo, condition, target_id, expected_staged,
):
    from dataclasses import replace

    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
    request, response = setup_replan(replan_repo)
    response = response.model_copy(update={"new_steps": [response.new_steps[0].model_copy(
        update={"preconditions": [condition]}, deep=True)]}, deep=True)
    def placement_proof(*args):
        proof = submit_proof(*args)
        base = dict(proof.online_evidence.visual_facts["target_visible"])
        online = replace(proof.online_evidence, visual_facts={
            condition: {**base, "target_id": target_id, "value": True},
        })
        action = replace(
            proof.action, preconditions=(ConditionSpec(condition, target_id=target_id),)
        )
        proof = replace(proof, action=action, online_evidence=online)
        assert validate_evidence(action, NOW, args[0].checkpoint_hash, "cal-1",
                                 online_evidence=online).status == "VALID"
        return proof
    gateway = MockStagedGateway()
    result = ReplanApplyService(repository=replan_repo, dispatcher=gateway,
                                submit_guard=placement_proof, clock=lambda: NOW).apply(
        request=request, response=response)
    assert bool(gateway.calls) is expected_staged
    assert result.applied is expected_staged
    assert replan_repo.get_active_contract("task").plan_version == (2 if expected_staged else 1)


class MockTemporalGateway(MockStagedGateway):
    """Software source-clock fixture; never invokes a real edge or robot."""

    def __init__(self, clock_state, *, resume_offset=.75, resume_accepted=True, timeout=False):
        super().__init__(resume_timeout=timeout)
        self.clock_state = clock_state
        self.resume_offset = resume_offset
        self.resume_accepted = resume_accepted

    def stage(self, contract, repair_id):
        ack = super().stage(contract, repair_id)
        self.clock_state["now"] = NOW + timedelta(seconds=.5)
        self.stage_ack = ack.model_copy(update={"timestamp": self.clock_state["now"]}, deep=True)
        return self.stage_ack

    def resume(self, repair_id, activation_token):
        self.clock_state["now"] = NOW + timedelta(seconds=1)
        ack = super().resume(repair_id, activation_token)
        return ack.model_copy(update={
            "timestamp": NOW + timedelta(seconds=self.resume_offset),
            "accepted": self.resume_accepted,
            "status": "ACCEPTED" if self.resume_accepted else "REJECTED",
        }, deep=True)


def temporal_activation(repo, **gateway_options):
    from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService

    request, response = setup_replan(repo)
    clock_state = {"now": NOW}
    service = ReplanApplyService(
        repository=repo, dispatcher=MockTemporalGateway(clock_state, **gateway_options),
        submit_guard=submit_proof, clock=lambda: clock_state["now"],
    )
    return service, service.apply(request=request, response=response)


def temporal_receipt(record, offset):
    from cloud_edge_robot_arm.contracts.models import ReplanExecutionReceipt

    return ReplanExecutionReceipt(
        repair_id=record.repair_id, task_id="task", plan_version=2, command_seq=2,
        activation_token=record.activation_token, payload_hash=record.payload_hash,
        event_id="MOCK-source-time-start", started_at=NOW + timedelta(seconds=offset),
    )


@pytest.mark.parametrize("start_offset", [0., .6])
def test_start_cannot_precede_actual_stage_or_resume_ack(replan_repo, start_offset):
    service, result = temporal_activation(replan_repo)
    assert result.record.status == "ACTIVATED"
    with pytest.raises(ValueError):
        service.confirm_execution_started(temporal_receipt(result.record, start_offset))
    saved = replan_repo.get_replan_apply_record(result.record.apply_id)
    assert saved.status == "ACTIVATED" and saved.start_receipt is None
    assert saved.stage_ack.timestamp == NOW + timedelta(seconds=.5)
    assert saved.resume_ack.timestamp == NOW + timedelta(seconds=.75)


@pytest.mark.parametrize("resume_accepted", [False, True])
def test_actual_resume_ack_cannot_precede_stage_ack(replan_repo, resume_accepted):
    _, result = temporal_activation(replan_repo, resume_offset=0.,
                                    resume_accepted=resume_accepted)
    assert result.applied and result.record.status == "ACTIVATED"
    assert result.errors and result.record.resume_ack is None
    assert replan_repo.get_active_contract("task").plan_version == 2
    assert replan_repo.get_replan_apply_record(result.record.apply_id).resume_ack is None


@pytest.mark.parametrize("start_offset", [0., .6])
def test_repository_cannot_accept_rehashed_start_before_ack(replan_repo, start_offset):
    _, result = temporal_activation(replan_repo)
    record = result.record.model_copy(update={
        "status": "EXECUTION_STARTED",
        "start_receipt": temporal_receipt(result.record, start_offset),
        "executing_plan_version": 2, "executing_command_seq": 2, "apply_hash": "",
    }, deep=True)
    record = record.model_copy(update={"apply_hash": record.content_hash()}, deep=True)
    with pytest.raises(ValueError):
        replan_repo.update_replan_apply_record_if_current(record, expected_status="ACTIVATED")
    assert replan_repo.get_replan_apply_record(record.apply_id).status == "ACTIVATED"


def test_repository_cannot_accept_rehashed_resume_before_stage(replan_repo):
    _, result = temporal_activation(replan_repo, timeout=True)
    assert result.record.resume_ack is None
    record = result.record.model_copy(update={
        "resume_ack": result.record.stage_ack.model_copy(update={"timestamp": NOW}),
        "apply_hash": "",
    }, deep=True)
    record = record.model_copy(update={"apply_hash": record.content_hash()}, deep=True)
    with pytest.raises(ValueError):
        replan_repo.update_replan_apply_record_if_current(record, expected_status="ACTIVATED")
    assert replan_repo.get_replan_apply_record(record.apply_id).resume_ack is None


def test_start_at_actual_resume_time_remains_idempotent(replan_repo):
    service, result = temporal_activation(replan_repo)
    receipt = temporal_receipt(result.record, .75)
    started = service.confirm_execution_started(receipt)
    assert started.record.status == "EXECUTION_STARTED"
    assert started.record.start_receipt.started_at == result.record.resume_ack.timestamp
    assert service.confirm_execution_started(receipt) == started


def test_resume_timeout_does_not_fabricate_ack_or_start_time(replan_repo):
    service, result = temporal_activation(replan_repo, timeout=True)
    saved = replan_repo.get_replan_apply_record(result.record.apply_id)
    assert saved.status == "ACTIVATED" and saved.resume_ack is None and saved.start_receipt is None
    with pytest.raises(ValueError):
        service.confirm_execution_started(temporal_receipt(saved, 0.))
    assert replan_repo.get_replan_apply_record(saved.apply_id).start_receipt is None
    # An explicitly received MOCK source receipt after staging is evidence of
    # start even if a transport lost the resume ACK; no timestamp is invented.
    receipt = temporal_receipt(saved, .6)
    started = service.confirm_execution_started(receipt)
    assert started.record.start_receipt == receipt and started.record.resume_ack is None
