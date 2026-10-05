"""SOFTWARE_ONLY durable bindings, never actual owner/lease or physical admission."""

from __future__ import annotations

import importlib
import sqlite3
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
from cloud_edge_robot_arm.repositories.event_autonomy.hashing import stable_payload_hash
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from tests.test_visual_owner_registration import values


def fresh_source_values():
    """Fresh synthetic clocks only; no saved actual frame is retimestamped."""
    data = values()
    before = data["original"]
    now = datetime.now(UTC)
    contract = before.contract.model_copy(
        update={"issued_at": now, "valid_until": now + timedelta(seconds=60)}, deep=True
    )
    module = importlib.import_module("cloud_edge_robot_arm.vision.owner_registration")
    data["original"] = module.freeze_original_visual_plan(
        **{
            **before.freeze_inputs(),
            "contract": contract,
            "registered_at": now,
            "task_deadline_at": now + timedelta(seconds=60),
            "verification_deadline_at": now + timedelta(seconds=40),
        }
    )
    checkpoint = data["source_checkpoint"].model_copy(
        update={"created_at": now, "updated_at": now, "checkpoint_hash": ""}, deep=True
    )
    data["source_checkpoint"] = checkpoint.model_copy(
        update={"checkpoint_hash": checkpoint_digest(checkpoint)}
    )
    return data


@pytest.fixture(params=["memory", "sqlite"])
def prepared(request, tmp_path):
    repo = (
        InMemoryEventAutonomyRepository()
        if request.param == "memory"
        else SQLiteEventAutonomyRepository(tmp_path / "event.db")
    )
    data = fresh_source_values()
    original, checkpoint = data["original"], data["source_checkpoint"]
    state = VerificationBudgetState(
        3, 2, 0, original.verification_deadline_at, VerificationBudget(3, 2, 3, 40.0)
    )
    retry = RecoveryBudget(
        budget_id="original-retry-pool",
        task_id=original.identity.task_id,
        task_total_retry_limit=2,
        per_step_retry_limit=1,
        per_skill_retry_limit=2,
        effective_retry_limit=2,
        remaining_retries=2,
        retry_deadline=original.verification_deadline_at,
        scene_version=original.contract.scene_version,
        created_at=original.registered_at,
        updated_at=original.registered_at,
    )
    yield repo, original, checkpoint, state, retry
    if request.param == "sqlite":
        repo.close()


def initialize(prepared):
    repo, original, checkpoint, state, retry = prepared
    return repo.initialize_visual_owner_if_absent(original, checkpoint, state, retry)


def boundary(checkpoint, *, suffix="next", completed=()):
    ids = ["move", "grasp"]
    pending = ids[len(completed) :]
    changed = checkpoint.model_copy(
        update={
            "checkpoint_id": checkpoint.checkpoint_id + "-" + suffix,
            "completed_step_ids": list(completed),
            "pending_step_ids": pending,
            "current_step_id": pending[0] if pending else "",
            "current_step_index": len(completed),
            "updated_at": datetime.now(UTC),
            "checkpoint_hash": "",
        },
        deep=True,
    )
    return changed.model_copy(update={"checkpoint_hash": checkpoint_digest(changed)})


def publish(prepared, checkpoint, **overrides):
    repo, original, before, _, _ = prepared
    kwargs = dict(
        task_id=original.identity.task_id,
        owner_epoch=original.identity.owner_epoch,
        expected_owner_revision=1,
        expected_contract_hash=stable_payload_hash(original.contract),
        expected_checkpoint_hash=before.checkpoint_hash,
        checkpoint=checkpoint,
        grounding=None,
        state_generation=1,
    )
    kwargs.update(overrides)
    return repo.publish_visual_boundary_if_current(**kwargs)


def test_initializes_exact_original_active_checkpoint_pools_without_authority(prepared):
    repo, original, checkpoint, _, retry = prepared
    record = initialize(prepared)
    assert record.binding_scope == "DURABLE_BINDING_ONLY"
    assert record.mode_scope == "NOT_INCLUDED"
    assert not hasattr(record, "method_admitted") and not hasattr(record, "execution_admitted")
    assert record.owner_revision == 1 and record.state_generation == 0
    assert record.original_plan_hash == original.digest()
    assert record.checkpoint.checkpoint_hash == checkpoint.checkpoint_hash
    assert repo.get_active_contract(original.identity.task_id).contract_hash == stable_payload_hash(
        original.contract
    )
    assert repo.get_retry_budget(original.identity.task_id) == retry
    assert (
        repo.get_verification_budget(original.identity.task_id).state.deadline_at
        == original.verification_deadline_at
    )
    assert repo.get_visual_original_plan(original.identity.task_id, 1).digest() == original.digest()
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == record.digest()
    assert repo.get_visual_owner_publication("foreign-task") is None
    assert repo.get_visual_original_plan(original.identity.task_id, 99) is None


def test_same_initialization_is_idempotent_and_nested_outputs_are_detached(prepared):
    repo, original, checkpoint, state, retry = prepared
    first = initialize(prepared)
    second = initialize(prepared)
    assert first.digest() == second.digest()
    checkpoint.robot_state["external"] = {"mutable": True}
    state.remaining_reobservations = 0
    retry.remaining_retries = 0
    first.checkpoint.robot_state["caller"] = True
    first.verification_budget.state.remaining_reobservations = 0
    first.retry_budget.remaining_retries = 0
    returned = repo.get_visual_owner_publication(original.identity.task_id)
    assert returned.checkpoint.robot_state.get("external") is None
    assert returned.checkpoint.robot_state.get("caller") is None
    assert returned.verification_budget.state.remaining_reobservations == 3
    assert returned.retry_budget.remaining_retries == 2
    detached = repo.get_visual_original_plan(original.identity.task_id, 1)
    detached.contract.steps[0].parameters["object_id"] = "decoy"
    assert (
        repo.get_visual_original_plan(original.identity.task_id, 1)
        .contract.steps[0]
        .parameters["object_id"]
        != "decoy"
    )


@pytest.mark.parametrize("change", ["epoch", "proposal", "checkpoint"])
def test_same_original_key_rejects_changed_initial_identity_or_content(prepared, change):
    repo, original, checkpoint, state, retry = prepared
    first = initialize(prepared)
    if change == "epoch":
        original = replace(
            original, identity=replace(original.identity, owner_epoch="foreign-epoch")
        )
    elif change == "proposal":
        original = replace(original, proposal_hash="b" * 64)
    else:
        checkpoint = boundary(checkpoint)
    with pytest.raises(IdempotencyConflictError):
        repo.initialize_visual_owner_if_absent(original, checkpoint, state, retry)
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == first.digest()


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_epoch", "foreign"),
        ("expected_owner_revision", 99),
        ("expected_contract_hash", "b" * 64),
        ("expected_checkpoint_hash", "b" * 64),
        ("state_generation", 0),
    ],
)
def test_stale_or_foreign_publication_cas_writes_nothing(prepared, field, value):
    repo, original, checkpoint, _, _ = prepared
    first = initialize(prepared)
    assert publish(prepared, boundary(checkpoint), **{field: value}) is None
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == first.digest()
    assert (
        repo.get_latest_execution_checkpoint(original.identity.task_id).checkpoint_hash
        == checkpoint.checkpoint_hash
    )


def test_publish_atomic_checkpoint_revision_exact_retry_and_stale_conflict(prepared):
    repo, original, checkpoint, _, _ = prepared
    initialize(prepared)
    next_checkpoint = boundary(checkpoint)
    result = publish(prepared, next_checkpoint)
    assert result.owner_revision == 2 and result.state_generation == 1
    assert (
        repo.get_latest_execution_checkpoint(original.identity.task_id).checkpoint_hash
        == next_checkpoint.checkpoint_hash
    )
    assert publish(prepared, next_checkpoint).digest() == result.digest()
    assert publish(prepared, boundary(checkpoint, suffix="changed")) is None
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == result.digest()


def test_completed_prefix_cannot_be_replayed_by_later_boundary(prepared):
    repo, original, checkpoint, _, _ = prepared
    initialize(prepared)
    advanced = boundary(checkpoint, completed=("move",))
    record = publish(prepared, advanced)
    assert record is not None
    assert (
        publish(
            prepared,
            boundary(advanced),
            expected_owner_revision=2,
            expected_checkpoint_hash=advanced.checkpoint_hash,
            state_generation=2,
        )
        is None
    )
    assert repo.get_visual_owner_publication(
        original.identity.task_id
    ).checkpoint.completed_step_ids == ["move"]


def test_partial_existing_task_group_cannot_be_completed_from_caller_assertions(prepared):
    repo, original, _, _, retry = prepared
    repo.initialize_retry_budget_if_absent(retry)
    with pytest.raises(IdempotencyConflictError):
        initialize(prepared)
    assert repo.get_active_contract(original.identity.task_id) is None
    assert repo.get_latest_execution_checkpoint(original.identity.task_id) is None
    assert repo.get_verification_budget(original.identity.task_id) is None
    assert repo.get_visual_original_plan(original.identity.task_id, 1) is None
    assert repo.get_retry_budget(original.identity.task_id) == retry


def test_legal_retry_debit_invalidates_old_snapshot_then_fresh_publication_preserves_pool(prepared):
    repo, original, checkpoint, _, _ = prepared
    initialize(prepared)
    success, retry = repo.consume_retry_if_available(
        original.identity.task_id, "move", "MOVE_ABOVE", 0, "event-original"
    )
    assert success and retry.remaining_retries == 1
    assert repo.get_visual_owner_publication(original.identity.task_id) is None
    record = publish(prepared, boundary(checkpoint))
    assert record.retry_budget.remaining_retries == 1
    assert record.retry_budget.event_retry_counts == {"event-original": 1}
    assert record.effective_deadline_at <= original.verification_deadline_at
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == record.digest()


def test_external_checkpoint_hash_drift_does_not_get_relabelled_current(prepared):
    repo, original, checkpoint, _, _ = prepared
    initialize(prepared)
    repo.save_execution_checkpoint(boundary(checkpoint))
    assert repo.get_visual_owner_publication(original.identity.task_id) is None
    assert publish(prepared, boundary(checkpoint, suffix="owner-return")) is None


def test_software_record_constructor_cannot_claim_method_or_actual_scope(prepared):
    record = initialize(prepared)
    payload = record.to_payload()
    payload["binding_scope"] = "ACTUAL_OWNER"
    module = importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_owner"
    )
    with pytest.raises(ValueError):
        module.VisualOwnerPublicationRecord.from_payload(payload)


def test_two_sqlite_connections_restart_and_conflicting_owner_race(tmp_path):
    path = tmp_path / "event.db"
    first, second = SQLiteEventAutonomyRepository(path), SQLiteEventAutonomyRepository(path)
    data = fresh_source_values()
    original, checkpoint = data["original"], data["source_checkpoint"]
    state = VerificationBudgetState(
        3, 2, 0, original.verification_deadline_at, VerificationBudget(3, 2, 3, 40.0)
    )
    retry = RecoveryBudget(
        budget_id="pool",
        task_id=original.identity.task_id,
        remaining_retries=2,
        retry_deadline=original.verification_deadline_at,
        scene_version=original.contract.scene_version,
    )
    alternate = replace(original, identity=replace(original.identity, owner_epoch="epoch-2"))

    def race(repo, source):
        try:
            return repo.initialize_visual_owner_if_absent(source, checkpoint, state, retry)
        except IdempotencyConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(race, first, original), workers.submit(race, second, alternate)]
        results = [future.result() for future in futures]
    assert sum(result is not None for result in results) == 1
    winner = next(result for result in results if result is not None)
    first.close()
    second.close()
    reopened = SQLiteEventAutonomyRepository(path)
    try:
        assert (
            reopened.get_visual_owner_publication(original.identity.task_id).digest()
            == winner.digest()
        )
        assert (
            reopened.get_visual_original_plan(original.identity.task_id, 1).identity
            == winner.identity
        )
    finally:
        reopened.close()


def test_global_checkpoint_identity_collision_cannot_overwrite_another_task(prepared):
    repo, original, checkpoint, _, _ = prepared
    foreign = checkpoint.model_copy(
        update={"task_id": "other-task", "checkpoint_hash": ""}, deep=True
    )
    foreign = foreign.model_copy(update={"checkpoint_hash": checkpoint_digest(foreign)})
    repo.save_execution_checkpoint(foreign)
    with pytest.raises(IdempotencyConflictError):
        initialize(prepared)
    assert repo.get_checkpoint(foreign.checkpoint_id).task_id == "other-task"
    assert repo.get_active_contract(original.identity.task_id) is None


def test_publication_scope_subclass_cannot_create_an_actual_authority_envelope(prepared):
    record = initialize(prepared)
    module = importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_owner"
    )

    class CallerActualScope(module.VisualOwnerPublicationRecord):
        binding_scope = "ACTUAL_OWNER"

    payload = record.to_payload()
    payload["binding_scope"] = "ACTUAL_OWNER"
    payload.pop("publication_hash")
    payload["publication_hash"] = module.digest(payload)
    with pytest.raises(ValueError):
        CallerActualScope.from_payload(payload)


def test_foreign_checkpoint_cannot_alias_a_publication_via_a_declared_hash(prepared):
    repo, original, checkpoint, _, _ = prepared
    initialize(prepared)
    next_checkpoint = boundary(checkpoint)
    # Existing legacy diagnostic save accepts a caller-declared hash; the new boundary must not.
    foreign = next_checkpoint.model_copy(update={"task_id": "other-task"}, deep=True)
    repo.save_execution_checkpoint(foreign)
    assert publish(prepared, next_checkpoint) is None
    assert repo.get_checkpoint(foreign.checkpoint_id).task_id == "other-task"
    assert repo.get_visual_owner_publication(original.identity.task_id).owner_revision == 1


@pytest.mark.parametrize("change", ["limits", "deadline", "refill"])
def test_changed_pool_definition_or_refilled_history_cannot_be_published(prepared, change):
    repo, original, checkpoint, _, _ = prepared
    initialize(prepared)
    _, used = repo.consume_retry_if_available(
        original.identity.task_id, "move", "MOVE_ABOVE", 0, "event"
    )
    record = publish(prepared, boundary(checkpoint))
    assert record is not None
    if change == "limits":
        altered = used.model_copy(update={"task_total_retry_limit": 3}, deep=True)
    elif change == "deadline":
        altered = used.model_copy(
            update={"retry_deadline": used.retry_deadline + timedelta(seconds=1)}, deep=True
        )
    else:
        altered = used.model_copy(
            update={
                "remaining_retries": 2,
                "retry_count_used": 0,
                "task_retry_count": 0,
                "step_retry_counts": {},
                "skill_retry_counts": {},
                "event_retry_counts": {},
            },
            deep=True,
        )
    repo.save_retry_budget(altered)
    assert repo.get_visual_owner_publication(original.identity.task_id) is None
    assert (
        publish(
            prepared,
            boundary(record.checkpoint, suffix="after-drift"),
            expected_owner_revision=2,
            expected_checkpoint_hash=record.checkpoint.checkpoint_hash,
            state_generation=2,
        )
        is None
    )


def test_sqlite_failure_after_candidate_writes_rolls_back_entire_initial_group(prepared):
    repo, original, _, _, _ = prepared
    if not isinstance(repo, SQLiteEventAutonomyRepository):
        pytest.skip("SQLite transaction failure only")
    repo._conn.execute(
        "CREATE TRIGGER fail_visual_publication BEFORE INSERT ON visual_owner_publications "
        "BEGIN SELECT RAISE(ABORT, 'qualified-storage-failure'); END"
    )
    repo._conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="qualified-storage-failure"):
        initialize(prepared)
    task = original.identity.task_id
    assert repo.get_active_contract(task) is None
    assert repo.get_latest_execution_checkpoint(task) is None
    assert repo.get_retry_budget(task) is None and repo.get_verification_budget(task) is None
    assert repo.get_visual_original_plan(task, 1) is None
    assert repo.get_visual_owner_publication(task) is None


def test_complete_legacy_group_adoption_preserves_spent_counts_and_original_deadline(prepared):
    repo, original, checkpoint, state, retry = prepared
    repo.save_active_contract(
        original.contract, plan_id=original.identity.plan_id, robot_id=original.identity.robot_id
    )
    repo.save_execution_checkpoint(checkpoint)
    repo.initialize_retry_budget_if_absent(retry)
    repo.initialize_verification_budget_if_absent(original.identity.task_id, state)
    _, spent = repo.consume_retry_if_available(
        original.identity.task_id, "move", "MOVE_ABOVE", 0, "old-event"
    )
    old_pool = repo.get_verification_budget(original.identity.task_id).to_payload()
    record = initialize(prepared)
    assert record.retry_budget == spent
    assert repo.get_retry_budget(original.identity.task_id) == spent
    assert repo.get_verification_budget(original.identity.task_id).to_payload() == old_pool
    assert record.effective_deadline_at <= original.verification_deadline_at


def test_initial_expired_source_rolls_back_without_a_fresh_timeout(prepared):
    repo, original, checkpoint, state, retry = prepared
    before = original.registered_at - timedelta(seconds=80)
    contract = original.contract.model_copy(
        update={"issued_at": before, "valid_until": before + timedelta(seconds=60)}, deep=True
    )
    module = importlib.import_module("cloud_edge_robot_arm.vision.owner_registration")
    original = module.freeze_original_visual_plan(
        **{
            **original.freeze_inputs(),
            "contract": contract,
            "registered_at": before,
            "task_deadline_at": before + timedelta(seconds=60),
            "verification_deadline_at": before + timedelta(seconds=40),
        }
    )
    checkpoint = checkpoint.model_copy(
        update={"created_at": before, "updated_at": before, "checkpoint_hash": ""}, deep=True
    )
    checkpoint = checkpoint.model_copy(update={"checkpoint_hash": checkpoint_digest(checkpoint)})
    state.deadline_at = original.verification_deadline_at
    retry = retry.model_copy(update={"retry_deadline": original.verification_deadline_at})
    with pytest.raises(ValueError, match="expired"):
        repo.initialize_visual_owner_if_absent(original, checkpoint, state, retry)
    assert repo.get_active_contract(original.identity.task_id) is None
    assert repo.get_retry_budget(original.identity.task_id) is None


def test_two_memory_publishers_race_only_one_revision_and_checkpoint(prepared):
    repo, original, checkpoint, _, _ = prepared
    if not isinstance(repo, InMemoryEventAutonomyRepository):
        pytest.skip("memory concurrency case; SQLite distinct connection case below")
    initialize(prepared)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(publish, prepared, boundary(checkpoint, suffix=name))
            for name in ("race-a", "race-b")
        ]
        results = [future.result() for future in futures]
    assert sum(record is not None for record in results) == 1
    winner = next(record for record in results if record is not None)
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == winner.digest()
    assert (
        repo.get_latest_execution_checkpoint(original.identity.task_id).checkpoint_hash
        == winner.checkpoint.checkpoint_hash
    )


def test_two_sqlite_boundary_publishers_one_committed_revision(prepared):
    first, original, checkpoint, state, retry = prepared
    if not isinstance(first, SQLiteEventAutonomyRepository):
        pytest.skip("SQLite distinct connections only")
    initialize(prepared)
    second = SQLiteEventAutonomyRepository(first.path)
    try:
        other_prepared = (second, original, checkpoint, state, retry)
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [
                workers.submit(publish, source, boundary(checkpoint, suffix=suffix))
                for source, suffix in ((prepared, "race-a"), (other_prepared, "race-b"))
            ]
            results = [future.result() for future in futures]
        assert sum(record is not None for record in results) == 1
        winner = next(record for record in results if record is not None)
        assert (
            first.get_visual_owner_publication(original.identity.task_id).digest()
            == winner.digest()
        )
        assert (
            second.get_latest_execution_checkpoint(original.identity.task_id).checkpoint_hash
            == winner.checkpoint.checkpoint_hash
        )
        assert (
            first._conn.execute("SELECT COUNT(*) FROM visual_owner_publications").fetchone()[0] == 2
        )
    finally:
        second.close()


@pytest.mark.parametrize("field", ["owner_epoch", "contract_hash"])
def test_rehashed_publication_must_still_bind_the_original_owner_and_contract(prepared, field):
    repo, original, _, _, _ = prepared
    record = initialize(prepared)
    module = importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_owner"
    )
    payload = record.to_payload()
    if field == "owner_epoch":
        payload["identity"]["owner_epoch"] = "foreign-epoch"
    else:
        payload["contract_hash"] = "b" * 64
    payload.pop("publication_hash")
    payload["publication_hash"] = module.digest(payload)
    encoded = module.canonical(payload)
    if isinstance(repo, InMemoryEventAutonomyRepository):
        repo._visual_publications[(original.identity.task_id, 1)] = encoded
    else:
        repo._conn.execute(
            "UPDATE visual_owner_publications SET payload_json=?, publication_hash=?, "
            "owner_epoch=? WHERE task_id=?",
            (
                encoded,
                payload["publication_hash"],
                payload["identity"]["owner_epoch"],
                original.identity.task_id,
            ),
        )
        repo._conn.commit()
    assert repo.get_visual_owner_publication(original.identity.task_id) is None


def test_missing_active_version_history_is_an_incomplete_source_group(prepared):
    repo, original, _, _, _ = prepared
    initialize(prepared)
    if isinstance(repo, InMemoryEventAutonomyRepository):
        repo._contract_versions.pop(original.identity.task_id)
    else:
        repo._conn.execute(
            "DELETE FROM task_contract_versions WHERE task_id=?", (original.identity.task_id,)
        )
        repo._conn.commit()
    assert repo.get_visual_owner_publication(original.identity.task_id) is None


def source_grounding(prepared):
    """SOFTWARE_ONLY carrier, with no real frame/geometry/verdict or lease authority."""
    _, original, checkpoint, _, _ = prepared
    module = importlib.import_module("cloud_edge_robot_arm.vision.owner_registration")
    now = datetime.now(UTC)
    grounded = original.contract.steps[0].model_copy(
        update={"preconditions": [], "success_conditions": []}, deep=True
    )
    return module.StepGroundingBinding(
        original.digest(),
        original.identity,
        original.requirements["move"],
        1,
        2,
        checkpoint.checkpoint_hash,
        "software-frame-carrier",
        "a" * 64,
        "software-calibration",
        checkpoint.plan_version,
        checkpoint.command_seq,
        "a" * 64,
        "a" * 64,
        None,
        original.source_hashes,
        grounded.model_dump_json(),
        original.requirements["move"].expected_duration_s,
        now,
        now + timedelta(seconds=3),
    )


def publish_source_grounding(prepared):
    repo, original, checkpoint, _, _ = prepared
    initialize(prepared)
    grounding = source_grounding(prepared)
    changed = boundary(checkpoint).model_copy(
        update={
            "safety_state": {
                **checkpoint.safety_state,
                "grounding_binding_hash": grounding.binding_hash,
                "original_requirements_hash": original.requirements["move"].digest(),
            },
            "checkpoint_hash": "",
        },
        deep=True,
    )
    changed = changed.model_copy(update={"checkpoint_hash": checkpoint_digest(changed)})
    return publish(prepared, changed, grounding=grounding, state_generation=2)


def test_optional_grounding_preserves_original_requirements_without_geometry_admission(prepared):
    repo, original, _, _, _ = prepared
    record = publish_source_grounding(prepared)
    assert record is not None and record.binding_scope == "DURABLE_BINDING_ONLY"
    payload = record.to_payload()["grounding"]
    assert payload["binding_scope"] == "SOURCE_BINDING_ONLY"
    assert payload["original_requirements"] == original.requirements["move"].to_payload()
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == record.digest()


def test_rehashed_grounding_cannot_weaken_registered_requirements_on_read(prepared):
    repo, original, _, _, _ = prepared
    record = publish_source_grounding(prepared)
    assert record is not None
    module = importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_owner"
    )
    payload = record.to_payload()
    payload["grounding"]["original_requirements"]["allowed_error_m"] = 0.1
    payload.pop("publication_hash")
    payload["publication_hash"] = module.digest(payload)
    encoded = module.canonical(payload)
    if isinstance(repo, InMemoryEventAutonomyRepository):
        repo._visual_publications[(original.identity.task_id, 2)] = encoded
    else:
        repo._conn.execute(
            "UPDATE visual_owner_publications SET payload_json=?,publication_hash=? "
            "WHERE task_id=? AND owner_revision=2",
            (encoded, payload["publication_hash"], original.identity.task_id),
        )
        repo._conn.commit()
    assert repo.get_visual_owner_publication(original.identity.task_id) is None


def test_expired_prior_grounding_remains_history_and_allows_fresh_boundary(prepared, monkeypatch):
    """A synthetic clock advance never retimestamps an actual observation."""
    repo, original, _, _, _ = prepared
    previous = publish_source_grounding(prepared)
    assert previous is not None
    module = importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_owner"
    )
    advanced = datetime.fromisoformat(previous.to_payload()["grounding"]["valid_until"])

    class SoftwareClockType(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)

    class LaterSoftwareClock(datetime, metaclass=SoftwareClockType):
        @classmethod
        def now(cls, tz=None):
            return advanced if tz is None else advanced.astimezone(tz)

    monkeypatch.setattr(module, "datetime", LaterSoftwareClock)
    assert repo.get_visual_owner_publication(original.identity.task_id) is None
    refreshed = publish(
        prepared,
        boundary(previous.checkpoint, suffix="fresh-without-old-grounding"),
        expected_owner_revision=2,
        expected_checkpoint_hash=previous.checkpoint.checkpoint_hash,
        state_generation=3,
    )
    assert refreshed is not None and refreshed.owner_revision == 3
    assert refreshed.to_payload()["grounding"] is None
    assert (
        repo.get_visual_owner_publication(original.identity.task_id).digest() == refreshed.digest()
    )


@pytest.mark.parametrize(
    "branch,key,value",
    [
        ("checkpoint", "plan_version", True),
        ("checkpoint", "command_seq", 1.0),
        ("checkpoint", "unregistered_policy", "ignored"),
        ("retry_budget", "retry_count_used", False),
        ("retry_budget", "unregistered_policy", "ignored"),
    ],
)
@pytest.mark.parametrize("boundary_kind", ["constructor", "stored_getter"])
def test_serialized_nested_source_cannot_coerce_or_hide_fields(
    prepared, branch, key, value, boundary_kind
):
    repo, original, _, _, _ = prepared
    record = initialize(prepared)
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == record.digest()
    module = importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_owner"
    )
    payload = record.to_payload()
    payload[branch][key] = value
    payload.pop("publication_hash")
    payload["publication_hash"] = module.digest(payload)
    if boundary_kind == "constructor":
        with pytest.raises((ValueError, TypeError)):
            module.VisualOwnerPublicationRecord.from_payload(payload)
    else:
        if isinstance(repo, InMemoryEventAutonomyRepository):
            repo._visual_publications[(original.identity.task_id, 1)] = module.canonical(payload)
        else:
            repo._conn.execute(
                "UPDATE visual_owner_publications SET payload_json=?,publication_hash=? "
                "WHERE task_id=? AND owner_revision=1",
                (module.canonical(payload), payload["publication_hash"], original.identity.task_id),
            )
            repo._conn.commit()
        with pytest.raises((ValueError, TypeError)):
            repo.get_visual_owner_publication(original.identity.task_id)


def test_registered_freeform_checkpoint_boolean_roundtrips_without_coercion(prepared):
    repo, original, checkpoint, state, retry = prepared
    checkpoint = checkpoint.model_copy(
        update={"safety_state": {"diagnostic": {"guard_closed": True}}, "checkpoint_hash": ""},
        deep=True,
    )
    checkpoint = checkpoint.model_copy(update={"checkpoint_hash": checkpoint_digest(checkpoint)})
    record = repo.initialize_visual_owner_if_absent(original, checkpoint, state, retry)
    assert record.to_payload()["checkpoint"]["safety_state"]["diagnostic"]["guard_closed"] is True
    assert repo.get_visual_owner_publication(original.identity.task_id).digest() == record.digest()
