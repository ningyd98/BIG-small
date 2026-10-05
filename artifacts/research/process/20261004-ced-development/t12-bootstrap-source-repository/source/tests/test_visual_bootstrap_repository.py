"""BOOTSTRAP_SOURCE_ONLY real repository tests; zero capture/model/physics calls."""

from __future__ import annotations

import importlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
from cloud_edge_robot_arm.contracts.models import RobotState
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation
from tests.test_visual_owner_registration import values


def api():
    return importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap"
    )


def definition_values():
    now = datetime.now(UTC)
    lease = WorkerLeaseObservation(
        "job-1",
        "run-1",
        "worker-1",
        "lease-1",
        1,
        now - timedelta(seconds=2),
        now,
        now + timedelta(seconds=60),
        "1" * 64,
        "2" * 64,
        "3" * 64,
    )
    definition = api().VisualBootstrapDefinition(
        lease=lease,
        episode_id="episode",
        user_instruction="move the visible box",
        task_started_at=now - timedelta(seconds=1),
        task_timeout_s=120.0,
        verification_limits=VerificationBudget(2, 0, 3, 100.0),
        role_bundle_hash="4" * 64,
        model_snapshot_hash="5" * 64,
        source_hashes={"src/software-bootstrap.py": "6" * 64},
        registered_at=now,
    )
    return dict(lease=lease, definition=definition)


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    repo = (
        InMemoryEventAutonomyRepository()
        if request.param == "memory"
        else SQLiteEventAutonomyRepository(tmp_path / "bootstrap.db")
    )
    yield repo, definition_values()
    if request.param == "sqlite":
        repo.close()


def request_for(data, record, kind, **changes):
    body = dict(
        record=record,
        kind=kind,
        event_key=f"{kind}-{record.revision}",
        current_lease=data["lease"],
        robot_state=RobotState(connected=True),
    )
    body.update(changes)
    return api().VisualBootstrapTransitionInput(**body)


def frame(*, identifier="software-frame", episode="episode", captured_at=None):
    # Create a NEW explicitly synthetic frame; no archived actual timestamp is rewritten.
    raw = values()["online"].observation.model_dump(mode="json")
    raw.update(
        frame_id=identifier,
        observation_id=identifier,
        episode_id=episode,
        captured_at=(captured_at or datetime.now(UTC)).isoformat(),
        checksum_sha256="",
    )
    return RGBDObservation.model_validate(raw)


def advance_capture(
    repo, data, record, *, kind="RESERVE_INITIAL_CAPTURE", identifier="software-frame"
):
    reserved = repo.transition_visual_bootstrap_if_current(request=request_for(data, record, kind))
    assert reserved.write_disposition == "NEW_COMMIT"
    observation = frame(identifier=identifier)
    result = repo.transition_visual_bootstrap_if_current(
        request=request_for(
            data,
            reserved.record,
            "COMPLETE_CAPTURE",
            claim_id=reserved.record.pending_claim_id,
            observation=observation,
        )
    )
    return result.record, observation


def complete_unusable_plan(repo, data, record, observation):
    claim = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_PLAN")
    )
    draft = PlannerDraft(
        raw_text="SOFTWARE_ONLY unusable reply",
        parsed_json={"_sentinel": "REQUEST_MORE_OBSERVATION"},
        observation_evidence={
            **observation.evidence(),
            "model_snapshot_hash": data["definition"].model_snapshot_hash,
            "role_bundle_hash": data["definition"].role_bundle_hash,
        },
    )
    result = repo.transition_visual_bootstrap_if_current(
        request=request_for(
            data, claim.record, "COMPLETE_PLAN", claim_id=claim.record.pending_claim_id, draft=draft
        )
    )
    return result.record


def test_missing_bootstrap_storage_then_initialization_is_own_group_not_partial_owner_pool(store):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    assert record.scope == "BOOTSTRAP_SOURCE_ONLY" and record.revision == 0
    assert repo.get_visual_bootstrap(data["definition"].bootstrap_id).digest() == record.digest()
    assert repo.get_verification_budget("episode") is None
    assert repo.get_retry_budget("episode") is None
    assert repo.get_active_contract("episode") is None
    assert repo.get_visual_owner_publication("episode") is None


def test_exact_definition_idempotence_preserves_spent_pending_and_original_deadline(store):
    repo, data = store
    initial = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    result = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, initial, "RESERVE_INITIAL_CAPTURE")
    )
    current = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    assert current.digest() == result.record.digest()
    assert current.pending_claim_id is not None
    assert current.verification_state.deadline_at == data["definition"].verification_deadline_at
    assert current.task_deadline_at == data["definition"].task_deadline_at


@pytest.mark.parametrize("change", ["episode", "limits", "attempt", "lease", "registration"])
def test_restart_cannot_change_definition_or_refill_by_same_job_run(store, change):
    repo, data = store
    repo.initialize_visual_bootstrap_if_absent(data["definition"])
    definition = data["definition"]
    if change == "episode":
        definition = replace(definition, episode_id="different-episode")
    elif change == "limits":
        definition = replace(definition, verification_limits=VerificationBudget(5, 0, 3, 100))
    elif change == "attempt":
        definition = replace(definition, lease=replace(data["lease"], attempt=2))
    elif change == "lease":
        definition = replace(definition, lease=replace(data["lease"], lease_id="replacement-lease"))
    else:
        definition = replace(
            definition, registered_at=definition.registered_at + timedelta(milliseconds=1)
        )
    with pytest.raises(IdempotencyConflictError):
        repo.initialize_visual_bootstrap_if_absent(definition)
    assert (
        repo.get_visual_bootstrap(
            data["definition"].bootstrap_id
        ).verification_state.remaining_reobservations
        == 2
    )


def test_episode_cannot_alias_other_job_run(store):
    repo, data = store
    repo.initialize_visual_bootstrap_if_absent(data["definition"])
    other = replace(
        data["definition"], lease=replace(data["lease"], job_id="other-job", run_id="other-run")
    )
    with pytest.raises(IdempotencyConflictError):
        repo.initialize_visual_bootstrap_if_absent(other)
    assert repo.get_visual_bootstrap(other.bootstrap_id) is None


def test_lost_initial_claim_or_new_uuid_never_replays_and_exact_duplicate_is_history(store):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    request = request_for(data, record, "RESERVE_INITIAL_CAPTURE")
    claimed = repo.transition_visual_bootstrap_if_current(request=request)
    duplicate = repo.transition_visual_bootstrap_if_current(request=request)
    assert duplicate.write_disposition == "HISTORICAL_DUPLICATE"
    assert duplicate.record.digest() == claimed.record.digest()
    assert (
        repo.transition_visual_bootstrap_if_current(
            request=request_for(
                data, claimed.record, "RESERVE_INITIAL_CAPTURE", event_key="random-new-uuid"
            )
        )
        is None
    )
    assert (
        repo.get_visual_bootstrap(record.definition.bootstrap_id).pending_claim_id
        == claimed.record.pending_claim_id
    )


def test_same_event_key_changed_request_conflicts_without_new_effect(store):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    request = request_for(data, record, "RESERVE_INITIAL_CAPTURE")
    repo.transition_visual_bootstrap_if_current(request=request)
    with pytest.raises(IdempotencyConflictError):
        repo.transition_visual_bootstrap_if_current(
            request=request_for(
                data,
                record,
                "RESERVE_INITIAL_CAPTURE",
                event_key=request.to_payload()["event_key"],
                robot_state=RobotState(connected=False),
            )
        )


def test_stale_cas_late_completion_or_foreign_frame_does_not_return_budget(store):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    claimed = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_INITIAL_CAPTURE")
    )
    assert (
        repo.transition_visual_bootstrap_if_current(
            request=request_for(data, record, "STOP", event_key="stale-stop")
        )
        is None
    )
    for observation in [
        frame(episode="foreign"),
        frame(captured_at=data["definition"].task_started_at),
    ]:
        request = request_for(
            data,
            claimed.record,
            "COMPLETE_CAPTURE",
            claim_id=claimed.record.pending_claim_id,
            observation=observation,
        )
        assert repo.transition_visual_bootstrap_if_current(request=request) is None
    assert (
        repo.get_visual_bootstrap(record.definition.bootstrap_id).digest()
        == claimed.record.digest()
    )


def test_completed_unusable_plan_consumes_reobservations_before_capture_and_preserves_full_state(
    store,
):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    record, observation = advance_capture(repo, data, record)
    record = complete_unusable_plan(repo, data, record, observation)
    before = record.verification_state
    request = request_for(data, record, "RESERVE_REOBSERVATION")
    result = repo.transition_visual_bootstrap_if_current(request=request)
    assert result.record.verification_state.remaining_reobservations == 1
    assert result.record.verification_state.remaining_retries == 0
    assert result.record.verification_state.verification_rounds == 1
    assert result.record.verification_state.previous_conditions == {
        "bootstrap_plan_source": ("UNKNOWN", None)
    }
    assert result.record.verification_state.deadline_at == before.deadline_at
    assert (
        repo.transition_visual_bootstrap_if_current(request=request).write_disposition
        == "HISTORICAL_DUPLICATE"
    )
    assert (
        repo.initialize_visual_bootstrap_if_absent(
            data["definition"]
        ).verification_state.remaining_reobservations
        == 1
    )
    assert repo.get_verification_budget("episode") is None


def test_pending_plan_cannot_retry_or_reserve_capture_after_lost_reply(store):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    record, observation = advance_capture(repo, data, record)
    claimed = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_PLAN")
    )
    assert (
        repo.transition_visual_bootstrap_if_current(
            request=request_for(data, claimed.record, "RESERVE_PLAN", event_key="retry")
        )
        is None
    )
    assert (
        repo.transition_visual_bootstrap_if_current(
            request=request_for(data, claimed.record, "RESERVE_REOBSERVATION")
        )
        is None
    )
    stopped = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, claimed.record, "STOP")
    )
    assert stopped.record.terminal_reason == "bootstrap_stopped"
    assert stopped.record.verification_state.remaining_reobservations == 2


@pytest.mark.parametrize("field", ["estop_engaged", "collision_detected", "connected"])
def test_hard_stop_prevents_claim_and_does_not_debit(store, field):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    state = RobotState(connected=True).model_copy(update={field: field != "connected"})
    result = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_INITIAL_CAPTURE", robot_state=state)
    )
    assert result.record.terminal_reason == "hard_safety_fault"
    assert result.record.pending_claim_id is None
    assert result.record.verification_state.remaining_reobservations == 2


def test_row_codec_recomputes_history_and_rejects_corrupt_revision_or_hash(store):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    if isinstance(repo, InMemoryEventAutonomyRepository):
        raw = json.loads(repo._visual_bootstraps[record.definition.bootstrap_id])
        raw["revision"] = True
        repo._visual_bootstraps[record.definition.bootstrap_id] = json.dumps(raw)
    else:
        repo._conn.execute(
            "UPDATE visual_bootstraps SET revision=99 WHERE bootstrap_id=?",
            (record.definition.bootstrap_id,),
        )
        repo._conn.commit()
    with pytest.raises(ValueError):
        repo.get_visual_bootstrap(record.definition.bootstrap_id)


def test_sqlite_write_failure_rolls_back_whole_bootstrap_transition(store):
    repo, data = store
    if not isinstance(repo, SQLiteEventAutonomyRepository):
        pytest.skip("SQLite storage failure regression")
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    repo._conn.execute(
        "CREATE TRIGGER reject_bootstrap BEFORE UPDATE ON visual_bootstraps "
        "BEGIN SELECT RAISE(ABORT, 'software persistence failure'); END"
    )
    repo._conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        repo.transition_visual_bootstrap_if_current(
            request=request_for(data, record, "RESERVE_INITIAL_CAPTURE")
        )
    assert repo.get_visual_bootstrap(record.definition.bootstrap_id).digest() == record.digest()


def test_two_sqlite_connections_race_and_restart_keep_one_pending_claim(tmp_path):
    path = tmp_path / "race.db"
    repos = [SQLiteEventAutonomyRepository(path), SQLiteEventAutonomyRepository(path)]
    data = definition_values()
    record = repos[0].initialize_visual_bootstrap_if_absent(data["definition"])
    request = request_for(data, record, "RESERVE_INITIAL_CAPTURE")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda repo: repo.transition_visual_bootstrap_if_current(request=request), repos
            )
        )
    assert sorted(r.write_disposition for r in results) == ["HISTORICAL_DUPLICATE", "NEW_COMMIT"]
    for repo in repos:
        repo.close()
    reopened = SQLiteEventAutonomyRepository(path)
    current = reopened.get_visual_bootstrap(record.definition.bootstrap_id)
    assert current.revision == 1 and current.pending_claim_id is not None
    assert (
        reopened.initialize_visual_bootstrap_if_absent(data["definition"]).digest()
        == current.digest()
    )
    assert (
        reopened.transition_visual_bootstrap_if_current(request=request).write_disposition
        == "HISTORICAL_DUPLICATE"
    )
    reopened.close()


def test_partial_ordinary_pool_cannot_become_bootstrap_then_receive_new_limits(store):
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget

    repo, data = store
    existing = RecoveryBudget(
        task_id="episode",
        budget_id="already-spent",
        remaining_retries=0,
        retry_deadline=data["definition"].verification_deadline_at,
    )
    repo.save_retry_budget(existing)
    with pytest.raises(IdempotencyConflictError):
        repo.initialize_visual_bootstrap_if_absent(data["definition"])
    assert repo.get_visual_bootstrap(data["definition"].bootstrap_id) is None
    assert repo.get_retry_budget("episode").remaining_retries == 0


def test_detached_sources_cannot_refill_persisted_pending_or_history(store):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    request = request_for(data, record, "RESERVE_INITIAL_CAPTURE")
    claimed = repo.transition_visual_bootstrap_if_current(request=request)
    raw = claimed.record.to_payload()
    raw["state"]["remaining_reobservations"] = 900
    raw["pending"] = None
    assert (
        repo.get_visual_bootstrap(record.definition.bootstrap_id).digest()
        == claimed.record.digest()
    )
    # Detached state and mutable caller payload must not change the stored JSON.
    state = claimed.record.verification_state
    state.remaining_reobservations = 900
    assert (
        repo.get_visual_bootstrap(
            record.definition.bootstrap_id
        ).verification_state.remaining_reobservations
        == 2
    )
    assert not hasattr(claimed, "execution_permission")
    assert not hasattr(claimed, "accepted")


def test_clock_rollback_stays_unavailable_and_deadline_stops_without_refund(store, monkeypatch):
    repo, data = store
    record = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    if isinstance(repo, InMemoryEventAutonomyRepository):
        module = importlib.import_module("cloud_edge_robot_arm.repositories.event_autonomy.memory")

        def set_clock(at):
            monkeypatch.setattr(module, "_utc_now", lambda: at)
    else:
        module = importlib.import_module("cloud_edge_robot_arm.repositories.event_autonomy.sqlite")

        class Clock:
            value = data["definition"].registered_at

            @classmethod
            def now(cls, *args):
                return cls.value

        monkeypatch.setattr(module, "datetime", Clock)

        def set_clock(at):
            Clock.value = at

    set_clock(data["definition"].registered_at - timedelta(seconds=1))
    assert (
        repo.transition_visual_bootstrap_if_current(
            request=request_for(data, record, "RESERVE_INITIAL_CAPTURE")
        )
        is None
    )
    set_clock(data["definition"].verification_deadline_at)
    stopped = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_INITIAL_CAPTURE")
    )
    assert stopped.record.terminal_reason == "deadline_exhausted"
    assert stopped.record.pending_claim_id is None
    assert stopped.record.verification_state.remaining_reobservations == 2


@pytest.mark.parametrize("alias", ["both", "job_run", "episode"])
def test_existing_bootstrap_cannot_be_bypassed_by_old_owner_initializer(store, alias):
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget
    from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudgetState
    from tests.test_visual_owner_repository import fresh_source_values

    repo, data = store
    definition = data["definition"]
    if alias == "job_run":
        definition = replace(definition, episode_id="different-bootstrap-episode")
    elif alias == "episode":
        definition = replace(
            definition, lease=replace(data["lease"], job_id="other-job", run_id="other-run")
        )
    bootstrap = repo.initialize_visual_bootstrap_if_absent(definition)
    fixture = fresh_source_values()
    original = fixture["original"]
    state = VerificationBudgetState.start(VerificationBudget(3, 2, 3, 40))
    state.deadline_at = original.verification_deadline_at
    retry = RecoveryBudget(
        budget_id="legacy-init",
        task_id=original.identity.task_id,
        scene_version=original.contract.scene_version,
        remaining_retries=2,
        retry_deadline=original.verification_deadline_at,
    )
    with pytest.raises(IdempotencyConflictError):
        repo.initialize_visual_owner_if_absent(original, fixture["source_checkpoint"], state, retry)
    assert (
        repo.get_visual_bootstrap(bootstrap.definition.bootstrap_id).digest() == bootstrap.digest()
    )
    assert repo.get_active_contract(original.identity.task_id) is None


def test_all_reobservations_are_spent_before_effect_and_restart_never_refills(store):
    repo, data = store
    initial = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    record, observation = advance_capture(repo, data, initial)
    record = complete_unusable_plan(repo, data, record, observation)
    for number in range(2):
        record, observation = advance_capture(
            repo,
            data,
            record,
            kind="RESERVE_REOBSERVATION",
            identifier=f"software-reobservation-{number}",
        )
        record = complete_unusable_plan(repo, data, record, observation)
    stopped = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_REOBSERVATION")
    )
    assert stopped.record.pending_claim_id is None
    assert stopped.record.verification_state.remaining_reobservations == 0
    assert stopped.record.terminal_reason == "reobservation_exhausted"
    assert stopped.record.verification_state.deadline_at == initial.verification_state.deadline_at
    assert (
        repo.initialize_visual_bootstrap_if_absent(data["definition"]).digest()
        == stopped.record.digest()
    )
    assert (
        repo.transition_visual_bootstrap_if_current(
            request=request_for(data, stopped.record, "RESERVE_INITIAL_CAPTURE")
        )
        is None
    )


def test_two_connections_initialization_has_one_original_definition(tmp_path):
    path = tmp_path / "init-race.db"
    repos = [SQLiteEventAutonomyRepository(path), SQLiteEventAutonomyRepository(path)]
    data = definition_values()
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(
            pool.map(
                lambda repo: repo.initialize_visual_bootstrap_if_absent(data["definition"]), repos
            )
        )
    assert records[0].digest() == records[1].digest()
    assert repos[0]._conn.execute("SELECT count(*) FROM visual_bootstraps").fetchone()[0] == 1
    for repo in repos:
        repo.close()


def test_two_connection_different_keys_cannot_both_claim_same_original(tmp_path):
    path = tmp_path / "distinct-claims.db"
    repos = [SQLiteEventAutonomyRepository(path), SQLiteEventAutonomyRepository(path)]
    data = definition_values()
    initial = repos[0].initialize_visual_bootstrap_if_absent(data["definition"])
    requests = [
        request_for(data, initial, "RESERVE_INITIAL_CAPTURE", event_key=f"event-{n}")
        for n in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda pair: pair[0].transition_visual_bootstrap_if_current(request=pair[1]),
                zip(repos, requests, strict=True),
            )
        )
    assert sum(result is not None for result in results) == 1
    assert (
        next(result for result in results if result is not None).write_disposition == "NEW_COMMIT"
    )
    current = repos[0].get_visual_bootstrap(initial.definition.bootstrap_id)
    assert current.revision == 1 and len(current.to_payload()["history"]) == 1
    for repo in repos:
        repo.close()


def test_reobservation_camera_source_change_keeps_spent_claim_without_refund(store):
    repo, data = store
    initial = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    record, observation = advance_capture(repo, data, initial)
    record = complete_unusable_plan(repo, data, record, observation)
    claimed = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_REOBSERVATION")
    )
    new = frame(identifier="changed-camera-software-frame")
    raw = new.model_dump(mode="json")
    raw.update(calibration_version=new.calibration_version + "-changed", checksum_sha256="")
    new = RGBDObservation.model_validate(raw)
    result = repo.transition_visual_bootstrap_if_current(
        request=request_for(
            data,
            claimed.record,
            "COMPLETE_CAPTURE",
            claim_id=claimed.record.pending_claim_id,
            observation=new,
        )
    )
    assert result is None
    current = repo.get_visual_bootstrap(initial.definition.bootstrap_id)
    assert current.digest() == claimed.record.digest()
    assert current.verification_state.remaining_reobservations == 1
    assert current.pending_claim_id is not None


def test_ordinary_api_has_no_adoption_kind_or_caller_accepted_flag(store):
    repo, data = store
    initial = repo.initialize_visual_bootstrap_if_absent(data["definition"])
    with pytest.raises(ValueError):
        request_for(data, initial, "ADOPT_ORIGINAL")
    with pytest.raises(TypeError):
        request_for(data, initial, "RESERVE_INITIAL_CAPTURE", accepted=True)
    assert repo.get_visual_bootstrap(initial.definition.bootstrap_id).digest() == initial.digest()


def promotion_ready(repo, data, *, spent=True):
    from cloud_edge_robot_arm.contracts.models import ExecutionCheckpoint
    from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
    from cloud_edge_robot_arm.vision.worker_owner import REQUIRED_COMPILER_SOURCES

    definition = replace(
        data["definition"],
        source_hashes={
            name: "6" * 64 for name in (*REQUIRED_COMPILER_SOURCES, api().BOOTSTRAP_SOURCE_PATH)
        },
    )
    data = {**data, "definition": definition}
    record = repo.initialize_visual_bootstrap_if_absent(definition)
    record, observation = advance_capture(repo, data, record)
    if spent:
        record = complete_unusable_plan(repo, data, record, observation)
        record, observation = advance_capture(
            repo, data, record, kind="RESERVE_REOBSERVATION", identifier="promotion-spent-1"
        )
        record = complete_unusable_plan(repo, data, record, observation)
        record, observation = advance_capture(
            repo, data, record, kind="RESERVE_REOBSERVATION", identifier="promotion-spent-2"
        )
    claim = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_PLAN")
    )
    draft = PlannerDraft(
        raw_text="SOFTWARE_ONLY canonical proposal",
        parsed_json={
            **values()["original"].contract.model_dump(mode="json"),
            "user_instruction": definition.user_instruction,
        },
        observation_evidence={
            **observation.evidence(),
            "model_snapshot_hash": definition.model_snapshot_hash,
            "role_bundle_hash": definition.role_bundle_hash,
        },
    )
    result = repo.transition_visual_bootstrap_if_current(
        request=request_for(
            data, claim.record, "COMPLETE_PLAN", claim_id=claim.record.pending_claim_id, draft=draft
        )
    )
    record = result.record
    now = datetime.now(UTC)
    original = api().compile_bootstrap_original_plan(
        record,
        current_lease=data["lease"],
        plan_id="software-bootstrap-plan",
        robot_id="software-bootstrap-robot",
        registered_at=now,
    )
    retry = api().bootstrap_retry_budget(record, original, created_at=now)
    checkpoint = ExecutionCheckpoint(
        checkpoint_id="software-bootstrap-initial",
        task_id=original.identity.task_id,
        plan_id=original.identity.plan_id,
        robot_id=original.identity.robot_id,
        plan_version=original.contract.plan_version,
        command_seq=original.contract.command_seq,
        scene_version=original.contract.scene_version,
        current_step_id=original.contract.steps[0].step_id,
        current_step_index=0,
        pending_step_ids=[step.step_id for step in original.contract.steps],
        completed_step_ids=[],
        created_at=now,
        updated_at=now,
    )
    checkpoint = checkpoint.model_copy(update={"checkpoint_hash": checkpoint_digest(checkpoint)})
    promotion = api().VisualBootstrapPromotionInput(
        record=record,
        original=original,
        event_key="promote",
        current_lease=data["lease"],
        robot_state=RobotState(connected=True),
    )
    return record, original, checkpoint, record.verification_state, retry, promotion


def adopt(repo, source, **changes):
    record, original, checkpoint, state, retry, promotion = source
    return repo.initialize_visual_owner_if_absent(
        changes.get("original", original),
        changes.get("checkpoint", checkpoint),
        changes.get("state", state),
        changes.get("retry", retry),
        bootstrap_promotion=changes.get("promotion", promotion),
    )


def test_promotion_commits_entire_spent_pool_original_checkpoint_and_bootstrap_once(store):
    from dataclasses import asdict

    repo, data = store
    source = promotion_ready(repo, data)
    record, original, checkpoint, state, retry, promotion = source
    saved = adopt(repo, source)
    promoted = repo.get_visual_bootstrap(record.definition.bootstrap_id)
    assert promoted.terminal_reason == "original_adopted"
    assert asdict(promoted.verification_state) == asdict(state)
    assert asdict(saved.verification_budget.state) == asdict(state)
    assert state.remaining_reobservations == 0 and state.verification_rounds == 2
    assert state.consecutive_no_progress == 1
    assert saved.retry_budget == retry
    assert repo.get_visual_original_plan(original.identity.task_id, 1).digest() == original.digest()
    assert repo.get_active_contract(original.identity.task_id).contract == original.contract
    assert (
        repo.get_latest_execution_checkpoint(original.identity.task_id).checkpoint_hash
        == checkpoint.checkpoint_hash
    )
    assert adopt(repo, source).digest() == saved.digest()
    assert repo.get_visual_bootstrap(record.definition.bootstrap_id).digest() == promoted.digest()
    assert (
        repo.transition_visual_bootstrap_if_current(
            request=request_for(data, promoted, "STOP", event_key="post-adoption")
        )
        is None
    )
    assert saved.binding_scope == "DURABLE_BINDING_ONLY"


@pytest.mark.parametrize(
    "change", ["quota", "rounds", "history", "deadline", "retry", "original", "checkpoint"]
)
def test_promotion_changed_source_or_pool_does_not_create_any_partial_owner_rows(store, change):
    from cloud_edge_robot_arm.vision.owner_registration import freeze_original_visual_plan

    repo, data = store
    source = promotion_ready(repo, data)
    record, original, checkpoint, state, retry, promotion = source
    changes = {}
    if change == "quota":
        state.remaining_reobservations = state.limits.max_reobservations
    elif change == "rounds":
        state.verification_rounds = 0
    elif change == "history":
        state.previous_conditions.clear()
    elif change == "deadline":
        state.deadline_at += timedelta(seconds=1)
    elif change == "retry":
        changes["retry"] = retry.model_copy(update={"remaining_retries": 1})
    elif change == "original":
        changes["original"] = freeze_original_visual_plan(
            **{**original.freeze_inputs(), "proposal_hash": "f" * 64}
        )
    else:
        changes["checkpoint"] = checkpoint.model_copy(update={"current_step_id": "wrong-step"})
    with pytest.raises((IdempotencyConflictError, ValueError)):
        adopt(repo, source, **changes)
    assert repo.get_visual_bootstrap(record.definition.bootstrap_id).digest() == record.digest()
    assert repo.get_active_contract(original.identity.task_id) is None
    assert repo.get_verification_budget(original.identity.task_id) is None
    assert repo.get_retry_budget(original.identity.task_id) is None
    assert repo.get_visual_owner_publication(original.identity.task_id) is None


def test_promotion_storage_failure_rolls_back_bootstrap_and_all_owner_rows(store):
    repo, data = store
    if not isinstance(repo, SQLiteEventAutonomyRepository):
        pytest.skip("SQLite transaction failure")
    source = promotion_ready(repo, data)
    record, original, *_ = source
    repo._conn.execute(
        "CREATE TRIGGER reject_adoption BEFORE UPDATE ON visual_bootstraps "
        "BEGIN SELECT RAISE(ABORT, 'software adoption storage failure'); END"
    )
    repo._conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        adopt(repo, source)
    assert repo.get_visual_bootstrap(record.definition.bootstrap_id).digest() == record.digest()
    for table in (
        "visual_original_plans",
        "visual_owner_publications",
        "active_task_contracts",
        "execution_checkpoints",
        "verification_budgets",
        "recovery_budgets",
        "task_contract_versions",
        "plan_versions",
    ):
        assert repo._conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_two_sqlite_connections_promotion_race_and_restart_preserve_spent_state(tmp_path):
    path = tmp_path / "adoption-race.db"
    repos = [SQLiteEventAutonomyRepository(path), SQLiteEventAutonomyRepository(path)]
    source = promotion_ready(repos[0], definition_values())
    with ThreadPoolExecutor(max_workers=2) as pool:
        saved = list(pool.map(lambda repo: adopt(repo, source), repos))
    assert saved[0].digest() == saved[1].digest()
    for repo in repos:
        repo.close()
    reopened = SQLiteEventAutonomyRepository(path)
    assert adopt(reopened, source).digest() == saved[0].digest()
    record = source[0]
    assert (
        reopened.get_visual_bootstrap(
            record.definition.bootstrap_id
        ).verification_state.remaining_reobservations
        == 0
    )
    assert (
        reopened.get_verification_budget(source[1].identity.task_id).state.remaining_reobservations
        == 0
    )
    reopened.close()


def test_historical_promotion_cannot_refund_later_ordinary_route_consumption(store):
    from tests.test_visual_verification_repository import request_for as ordinary_request

    repo, data = store
    source = promotion_ready(repo, data, spent=False)
    record, original, checkpoint, state, retry, promotion = source
    first = adopt(repo, source)
    online = replace(
        values()["online"],
        observation=record.observation,
        context_hash=first.checkpoint.checkpoint_hash,
    )
    route = repo.route_visual_verification_if_current(
        request=ordinary_request(
            {"original": original, "publication": first, "online": online},
            step_id=original.contract.steps[0].step_id,
        )
    )
    assert route.record.route == "REOBSERVE" and route.record.scope == "SOURCE_ROUTE_ONLY"
    current = repo.get_visual_owner_publication(original.identity.task_id)
    assert current.verification_budget.state.remaining_reobservations == 1
    assert adopt(repo, source).digest() == current.digest()
    assert (
        repo.get_verification_budget(original.identity.task_id).state.remaining_reobservations == 1
    )
    assert (
        repo.get_visual_bootstrap(
            record.definition.bootstrap_id
        ).verification_state.remaining_reobservations
        == 2
    )


def test_adopted_bootstrap_with_missing_owner_row_cannot_recreate_group_from_history(store):
    repo, data = store
    source = promotion_ready(repo, data)
    record, original, *_ = source
    adopt(repo, source)
    if isinstance(repo, InMemoryEventAutonomyRepository):
        del repo._visual_publications[(original.identity.task_id, 1)]
    else:
        repo._conn.execute(
            "DELETE FROM visual_owner_publications WHERE task_id=?", (original.identity.task_id,)
        )
        repo._conn.commit()
    promoted = repo.get_visual_bootstrap(record.definition.bootstrap_id)
    with pytest.raises(IdempotencyConflictError):
        adopt(repo, source)
    assert repo.get_visual_bootstrap(record.definition.bootstrap_id).digest() == promoted.digest()


@pytest.mark.parametrize("fault", ["hard_stop", "foreign_lease", "event_key"])
def test_promotion_rejects_boundary_fault_before_any_owner_writes(store, fault):
    repo, data = store
    source = promotion_ready(repo, data)
    record, original, *_ = source
    robot = RobotState(connected=True, estop_engaged=fault == "hard_stop")
    lease = (
        replace(data["lease"], lease_id="foreign-lease")
        if fault == "foreign_lease"
        else data["lease"]
    )
    event = (
        record.to_payload()["history"][0]["request"]["event_key"]
        if fault == "event_key"
        else "promotion-fault"
    )
    promotion = api().VisualBootstrapPromotionInput(
        record=record, original=original, event_key=event, current_lease=lease, robot_state=robot
    )
    with pytest.raises(IdempotencyConflictError):
        adopt(repo, source, promotion=promotion)
    assert repo.get_visual_bootstrap(record.definition.bootstrap_id).digest() == record.digest()
    assert repo.get_active_contract(original.identity.task_id) is None


def test_partial_existing_rows_prevent_new_adoption_instead_of_stitching_source_group(store):
    repo, data = store
    source = promotion_ready(repo, data)
    record, original, _, _, retry, _ = source
    repo.save_retry_budget(retry)
    with pytest.raises(IdempotencyConflictError):
        adopt(repo, source)
    assert repo.get_visual_bootstrap(record.definition.bootstrap_id).digest() == record.digest()
    assert repo.get_active_contract(original.identity.task_id) is None
    assert repo.get_visual_owner_publication(original.identity.task_id) is None


def test_no_progress_limit_stops_without_spending_remaining_reobservations_or_resetting_history(
    store,
):
    repo, data = store
    definition = replace(data["definition"], verification_limits=VerificationBudget(4, 0, 1, 100))
    data = {**data, "definition": definition}
    record = repo.initialize_visual_bootstrap_if_absent(definition)
    record, observation = advance_capture(repo, data, record)
    record = complete_unusable_plan(repo, data, record, observation)
    record, observation = advance_capture(
        repo, data, record, kind="RESERVE_REOBSERVATION", identifier="software-no-progress"
    )
    record = complete_unusable_plan(repo, data, record, observation)
    before = record.verification_state
    stopped = repo.transition_visual_bootstrap_if_current(
        request=request_for(data, record, "RESERVE_REOBSERVATION")
    )
    assert stopped.record.terminal_reason == "no_progress_exhausted"
    assert stopped.record.pending_claim_id is None
    assert stopped.record.verification_state.remaining_reobservations == 3
    assert stopped.record.verification_state.previous_conditions == before.previous_conditions
    assert stopped.record.verification_state.deadline_at == before.deadline_at
    assert (
        repo.initialize_visual_bootstrap_if_absent(definition).digest() == stopped.record.digest()
    )
