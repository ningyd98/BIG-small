"""SOFTWARE_ONLY owned claims; no camera, provider, controller or UTC certification."""

from __future__ import annotations

import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from cloud_edge_robot_arm.contracts.models import RecoveryBudget
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import freeze_original_visual_plan
from cloud_edge_robot_arm.vision.role_models import RoleModelBundle, RoleProviderSnapshot
from cloud_edge_robot_arm.vision.supervision import SupervisionContext, SupervisionDecision
from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation
from tests.test_visual_owner_repository import boundary, fresh_source_values


def api():
    return importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision"
    )


def initialize(repo):
    data = fresh_source_values()
    before = data["original"]
    start = datetime.now(UTC) - timedelta(seconds=4)
    registered = start + timedelta(seconds=1)
    lease = WorkerLeaseObservation(
        before.identity.job_id,
        before.identity.run_id,
        before.identity.worker_id,
        before.identity.lease_id,
        before.identity.attempt,
        start - timedelta(seconds=1),
        registered,
        start + timedelta(seconds=100),
        "a" * 64,
        "b" * 64,
        "c" * 64,
    )
    cloud = RoleProviderSnapshot(
        "CLOUD",
        "software-provider",
        "LOCAL_HOST",
        "software-model",
        None,
        None,
        None,
        "d" * 64,
        before.source_hashes,
    )
    bundle = RoleModelBundle(cloud, "software-edge", "e" * 64, "f" * 64)
    identity = lease.identity(
        episode_id=before.identity.episode_id,
        task_id=before.identity.task_id,
        plan_id=before.identity.plan_id,
        robot_id=before.identity.robot_id,
    )
    contract = before.contract.model_copy(
        update={"issued_at": start, "valid_until": start + timedelta(seconds=60)}
    )
    original = freeze_original_visual_plan(
        **{
            **before.freeze_inputs(),
            "identity": identity,
            "contract": contract,
            "role_bundle_hash": bundle.digest(),
            "registered_at": registered,
            "task_deadline_at": start + timedelta(seconds=60),
            "verification_deadline_at": start + timedelta(seconds=40),
        }
    )
    checkpoint = data["source_checkpoint"].model_copy(
        update={"created_at": registered, "updated_at": registered, "checkpoint_hash": ""}
    )
    checkpoint = checkpoint.model_copy(update={"checkpoint_hash": checkpoint_digest(checkpoint)})
    limits = VerificationBudget(3, 2, 3, 40.0)
    state = VerificationBudgetState(3, 2, 0, original.verification_deadline_at, limits)
    retry = RecoveryBudget(
        budget_id="supervision-fixture",
        task_id=identity.task_id,
        task_total_retry_limit=2,
        per_step_retry_limit=1,
        per_skill_retry_limit=2,
        effective_retry_limit=2,
        remaining_retries=2,
        retry_deadline=original.verification_deadline_at,
        scene_version=contract.scene_version,
        created_at=registered,
        updated_at=registered,
    )
    publication = repo.initialize_visual_owner_if_absent(original, checkpoint, state, retry)
    return {
        **data,
        "original": original,
        "publication": publication,
        "lease": lease,
        "role_bundle": bundle,
        "task_started_at": start,
        "task_timeout_s": 60.0,
    }


def definition(data, *, period=1.0):
    return api().VisualSupervisionDefinition(
        original=data["original"],
        publication=data["publication"],
        lease=data["lease"],
        task_started_at=data["task_started_at"],
        task_timeout_s=data["task_timeout_s"],
        supervision_period_s=period,
        model_snapshot_hash="1" * 64,
        role_bundle=data["role_bundle"],
    )


@pytest.fixture(params=["memory", "sqlite"])
def source(request, tmp_path):
    repo = (
        InMemoryEventAutonomyRepository()
        if request.param == "memory"
        else (SQLiteEventAutonomyRepository(tmp_path / "supervision.db"))
    )
    data = initialize(repo)
    data["record"] = repo.initialize_visual_supervision_if_absent(definition(data))
    yield repo, data
    repo.close()


def request_for(data, kind="RESERVE_CAPTURE", *, cursor=1, event_key=None, **changes):
    arguments = dict(
        record=data["record"],
        original=data["original"],
        publication=data["publication"],
        lease=replace(data["lease"], observed_at=datetime.now(UTC)),
        robot_state=data["online"].robot_state,
        step_id="move",
        cursor=cursor,
        kind=kind,
        event_key=event_key or f"{kind.lower()}-{cursor}",
        model_snapshot_hash="1" * 64,
        role_bundle=data["role_bundle"],
    )
    arguments.update(changes)
    return api().VisualSupervisionTransitionInput(**arguments)


def transition(repo, data, kind="RESERVE_CAPTURE", **changes):
    result = repo.transition_visual_supervision_if_current(
        request=request_for(data, kind, **changes)
    )
    if result is not None:
        data["record"] = result.record
    return result


def frame(data, observation_id="supervision-1"):
    raw = data["online"].observation.model_dump(mode="json")
    raw.update(
        observation_id=observation_id,
        frame_id=observation_id,
        episode_id=data["original"].identity.episode_id,
        captured_at=datetime.now(UTC).isoformat(),
        checksum_sha256="",
    )
    observation = RGBDObservation.model_validate(raw)
    context = SupervisionContext(
        episode_id=observation.episode_id,
        plan_version=data["original"].contract.plan_version,
        state_version=data["publication"].state_generation,
        next_step_id="move",
        next_skill="MOVE_ABOVE",
        task_instruction="synthetic original instruction",
        observation_id=observation.observation_id,
        captured_at=observation.captured_at,
        proprioception={"estop_engaged": False, "collision_detected": False},
    )
    return observation, context


def capture(repo, data, *, cursor=1):
    reservation = transition(repo, data, cursor=cursor)
    observation, context = frame(data, f"supervision-{cursor}")
    completion = transition(
        repo,
        data,
        "COMPLETE_CAPTURE",
        cursor=cursor,
        claim_id=reservation.claim_id,
        observation=observation,
        context=context,
    )
    assert completion is not None
    return reservation.claim_id, observation, context


def test_original_time_period_quota_is_separate_from_reactive_observation_pool(source):
    repo, data = source
    record = data["record"]
    assert record.scope == "SUPERVISION_SOURCE_ONLY"
    # Forty original seconds; first tick at one, expiry at forty: 39 candidates.
    assert record.to_payload()["max_periodic_captures"] == 39
    assert record.to_payload()["max_supervisor_calls"] == 39
    first = transition(repo, data)
    assert first.write_disposition == "NEW_COMMIT"
    assert first.record.to_payload()["captures_reserved"] == 1
    current = repo.get_visual_owner_publication(data["original"].identity.task_id)
    assert current.digest() == data["publication"].digest()
    assert current.verification_budget.state.remaining_reobservations == 3
    assert current.retry_budget.remaining_retries == 2
    assert first.record.to_payload()["deadline_at"] == (
        data["original"].verification_deadline_at.isoformat()
    )


def test_exact_capture_and_provider_receipt_are_immutable_and_never_action_permission(source):
    repo, data = source
    claim_id, observation, context = capture(repo, data)
    planned = transition(repo, data, "RESERVE_PLAN", claim_id=claim_id)
    assert planned.record.to_payload()["supervisor_calls_reserved"] == 1
    decision = SupervisionDecision(
        episode_id=context.episode_id,
        plan_version=context.plan_version,
        state_version=context.state_version,
        observation_id=context.observation_id,
        next_step_id=context.next_step_id,
        recommendation="CONTINUE",
        reason="software source",
    )
    result = transition(repo, data, "COMPLETE_PLAN", claim_id=planned.claim_id, decision=decision)
    receipt = result.record.to_payload()["claims"][claim_id]
    assert receipt["decision"]["recommendation"] == "CONTINUE"
    assert receipt["observation"]["observation_id"] == observation.observation_id
    assert receipt["context"]["next_step_id"] == "move"
    assert receipt["cloud_snapshot"]["model_id"] == "software-model"
    assert not hasattr(result.record, "execution_admitted")
    assert not hasattr(result, "action_permission")
    body = result.record.to_payload()
    body["claims"][claim_id]["decision"]["recommendation"] = "STOP"
    assert repo.get_visual_supervision(data["original"].identity.task_id).digest() == (
        result.record.digest()
    )


def test_pending_capture_has_one_local_commit_duplicate_never_replays_or_refunds(source):
    repo, data = source
    request = request_for(data)
    first = repo.transition_visual_supervision_if_current(request=request)
    second = repo.transition_visual_supervision_if_current(request=request)
    assert [first.write_disposition, second.write_disposition] == [
        "NEW_COMMIT",
        "HISTORICAL_DUPLICATE",
    ]
    assert second.claim_id == first.claim_id
    data["record"] = first.record
    randomized = request_for(data, event_key="randomized-new-key")
    third = repo.transition_visual_supervision_if_current(request=randomized)
    assert third.write_disposition == "HISTORICAL_DUPLICATE"
    assert third.record.to_payload()["captures_reserved"] == 1
    assert third.record.to_payload()["claims"][first.claim_id]["status"] == "CAPTURE_PENDING"


def test_changed_event_key_source_conflicts_without_spending_again(source):
    repo, data = source
    transition(repo, data)
    with pytest.raises(IdempotencyConflictError):
        transition(repo, data, cursor=2, event_key="reserve_capture-1")
    assert data["record"].to_payload()["captures_reserved"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"model_snapshot_hash": "9" * 64},
        {"step_id": "grasp"},
        {"cursor": 39},
    ],
)
def test_stale_step_future_period_or_model_source_cannot_reserve(source, change):
    repo, data = source
    assert transition(repo, data, **change) is None
    assert repo.get_visual_supervision(data["original"].identity.task_id).revision == 0


@pytest.mark.parametrize("field", ["estop_engaged", "collision_detected", "connected"])
def test_hard_stop_is_checked_before_claim_or_call_budget(source, field):
    repo, data = source
    state = data["online"].robot_state.model_copy(update={field: field != "connected"})
    assert transition(repo, data, robot_state=state) is None
    assert data["record"].to_payload()["captures_reserved"] == 0


def test_completed_step_or_new_publication_discards_old_return_with_real_cost_retained(source):
    repo, data = source
    claim_id, _, context = capture(repo, data)
    planned = transition(repo, data, "RESERVE_PLAN", claim_id=claim_id)
    pub = data["publication"]
    advanced = boundary(pub.checkpoint, completed=("move",))
    assert (
        repo.publish_visual_boundary_if_current(
            task_id=pub.identity.task_id,
            owner_epoch=pub.identity.owner_epoch,
            expected_owner_revision=pub.owner_revision,
            expected_contract_hash=pub.to_payload()["contract_hash"],
            expected_checkpoint_hash=pub.checkpoint.checkpoint_hash,
            checkpoint=advanced,
            grounding=None,
            state_generation=pub.state_generation + 1,
        )
        is not None
    )
    decision = SupervisionDecision(
        episode_id=context.episode_id,
        plan_version=context.plan_version,
        state_version=context.state_version,
        observation_id=context.observation_id,
        next_step_id="move",
        recommendation="CONTINUE",
        reason="late old source",
    )
    assert (
        transition(repo, data, "COMPLETE_PLAN", claim_id=planned.claim_id, decision=decision)
        is None
    )
    assert data["record"].to_payload()["supervisor_calls_reserved"] == 1


def test_wait_allocation_is_original_bounded_and_lost_pending_is_never_refunded(source):
    repo, data = source
    first = transition(repo, data, "RESERVE_WAIT", wait_duration_s=30.0)
    assert first.record.to_payload()["wait_seconds_reserved"] == 30.0
    assert transition(repo, data, "RESERVE_WAIT", cursor=2, wait_duration_s=11.0) is None
    second = transition(repo, data, "RESERVE_WAIT", cursor=2, wait_duration_s=10.0)
    assert second.record.to_payload()["wait_seconds_reserved"] == 40.0
    assert transition(repo, data, "RESERVE_WAIT", cursor=3, wait_duration_s=0.001) is None
    complete = transition(
        repo, data, "COMPLETE_WAIT", cursor=2, claim_id=second.claim_id, wait_elapsed_s=0.002
    )
    assert complete.record.to_payload()["wait_seconds_reserved"] == 40.0
    assert complete.record.to_payload()["claims"][first.claim_id]["status"] == "WAIT_PENDING"


def test_cancelled_or_tampered_current_pools_are_not_valid_original_source(source):
    repo, data = source
    repo.save_state(data["original"].identity.task_id, "CANCELLED", "source test")
    assert transition(repo, data) is None


def test_sticky_canonical_verification_stop_cannot_allocate_periodic_or_wait_effect(source):
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
        VisualVerificationRouteInput,
    )

    repo, data = source
    observation, _ = frame(data)
    online = replace(
        data["online"],
        observation=observation,
        robot_state=data["online"].robot_state.model_copy(update={"estop_engaged": True}),
        context_hash=data["publication"].checkpoint.checkpoint_hash,
    )
    stopped = repo.route_visual_verification_if_current(
        request=VisualVerificationRouteInput(
            original=data["original"],
            publication=data["publication"],
            online=online,
            step_id="move",
            attempt=1,
            phase="PRECONDITION",
            event_key="sticky-stop",
            execution_contract=data["original"].contract,
            completion=None,
        )
    )
    assert stopped.record.route == "STOP"
    data["publication"] = repo.get_visual_owner_publication(data["original"].identity.task_id)
    assert data["publication"].verification_budget.state.exhausted_reason == "hard_safety_fault"
    assert transition(repo, data) is None
    assert transition(repo, data, "RESERVE_WAIT", wait_duration_s=0.01) is None
    assert data["record"].to_payload()["captures_reserved"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(scope="EXECUTION_ADMITTED"),
        lambda p: p.update(cursor=True),
        lambda p: p.update(cursor=1.0),
        lambda p: p.update(accepted=True),
        lambda p: p["robot_state"].update(connected=1),
        lambda p: p["publication"]["checkpoint"].update(command_seq=True),
        lambda p: p["lease"].update(attempt=True),
        lambda p: p.update(wait_duration_s=float("nan")),
    ],
)
def test_raw_input_refuses_coercion_unknown_fields_and_scope_forgery(source, mutation):
    _, data = source
    payload = request_for(data).to_payload()
    mutation(payload)
    with pytest.raises(ValueError):
        api().VisualSupervisionTransitionInput.from_json(json.dumps(payload))


def test_record_recomputed_from_history_refuses_rehashed_budget_or_receipt_forgery(source):
    repo, data = source
    result = transition(repo, data)
    payload = result.record.to_payload()
    payload["captures_reserved"] = 0
    with pytest.raises(ValueError):
        api().VisualSupervisionRecord.from_payload(payload)


@pytest.mark.parametrize("mutation", ["payload", "index"])
def test_cached_immutable_history_never_hides_changed_stored_bytes_or_index_hash(source, mutation):
    repo, data = source
    result = transition(repo, data)
    task = data["original"].identity.task_id
    assert repo.get_visual_supervision(task).digest() == result.record.digest()
    raw = result.record.to_payload()
    raw["captures_reserved"] = 0
    if isinstance(repo, SQLiteEventAutonomyRepository):
        if mutation == "payload":
            repo._conn.execute(
                "UPDATE visual_supervision SET payload_json=? WHERE task_id=?",
                (json.dumps(raw), task),
            )
        else:
            repo._conn.execute(
                "UPDATE visual_supervision SET record_hash=? WHERE task_id=?", ("0" * 64, task)
            )
        repo._conn.commit()
    else:
        if mutation == "payload":
            repo._visual_supervision[task] = json.dumps(raw)
        else:
            repo._visual_supervision["foreign-task"] = repo._visual_supervision[task]
            task = "foreign-task"
    with pytest.raises(ValueError):
        repo.get_visual_supervision(task)


def test_sqlite_race_restart_retains_spent_claim_and_original_period_deadline(tmp_path):
    path = tmp_path / "race.db"
    repos = [SQLiteEventAutonomyRepository(path), SQLiteEventAutonomyRepository(path)]
    data = initialize(repos[0])
    frozen = definition(data)
    data["record"] = repos[0].initialize_visual_supervision_if_absent(frozen)
    request = request_for(data)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda repo: repo.transition_visual_supervision_if_current(request=request), repos
            )
        )
    assert sorted(r.write_disposition for r in results) == ["HISTORICAL_DUPLICATE", "NEW_COMMIT"]
    for repo in repos:
        repo.close()
    reopened = SQLiteEventAutonomyRepository(path)
    restored = reopened.initialize_visual_supervision_if_absent(frozen)
    assert restored.to_payload()["captures_reserved"] == 1
    assert restored.to_payload()["max_periodic_captures"] == 39
    assert (
        restored.to_payload()["deadline_at"]
        == data["original"].verification_deadline_at.isoformat()
    )
    assert (
        reopened.transition_visual_supervision_if_current(request=request).write_disposition
        == "HISTORICAL_DUPLICATE"
    )
    with pytest.raises(IdempotencyConflictError):
        reopened.initialize_visual_supervision_if_absent(definition(data, period=0.5))
    reopened.close()


def test_owned_supervision_repository_api_exists_before_optional_effects_can_be_enabled():
    assert (
        importlib.util.find_spec(
            "cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision"
        )
        is not None
    ), "persistent supervision capture/provider/wait claim implementation missing"
