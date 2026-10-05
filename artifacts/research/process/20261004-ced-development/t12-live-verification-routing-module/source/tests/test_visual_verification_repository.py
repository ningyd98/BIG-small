"""SOFTWARE_ONLY real repositories; zero source authentication or physical actions."""

from __future__ import annotations

import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from cloud_edge_robot_arm.contracts.models import RecoveryBudget
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_visual_owner_repository import fresh_source_values


def api():
    return importlib.import_module(
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_verification"
    )


@pytest.fixture(params=["memory", "sqlite"])
def source(request, tmp_path):
    repo = (
        InMemoryEventAutonomyRepository()
        if request.param == "memory"
        else SQLiteEventAutonomyRepository(tmp_path / "event.db")
    )
    data = fresh_source_values()
    original = data["original"]
    retry = RecoveryBudget(
        budget_id="routing-fixture",
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
    state = VerificationBudgetState(
        3, 2, 0, original.verification_deadline_at, VerificationBudget(3, 2, 3, 40.0)
    )
    publication = repo.initialize_visual_owner_if_absent(
        original, data["source_checkpoint"], state, retry
    )
    data["publication"] = publication
    # This creates a NEW synthetic input; never retimestamps a saved real image.
    raw = data["online"].observation.model_dump(mode="json")
    raw.update(captured_at=datetime.now(UTC).isoformat(), checksum_sha256="")
    data["online"] = replace(
        data["online"],
        observation=RGBDObservation.model_validate(raw),
        context_hash=publication.checkpoint.checkpoint_hash,
    )
    yield repo, data
    if request.param == "sqlite":
        repo.close()


def request_for(data, *, unknown=True, event_key="route-1", phase="PRECONDITION", **changes):
    online = data["online"]
    if unknown:
        online = replace(online, visual_facts={})
    arguments = dict(
        original=data["original"],
        publication=data["publication"],
        online=online,
        step_id="move",
        attempt=1,
        phase=phase,
        event_key=event_key,
        execution_contract=data["original"].contract,
        completion=None,
    )
    arguments.update(changes)
    return api().VisualVerificationRouteInput(**arguments)


def next_frame(data, publication, index):
    raw = data["online"].observation.model_dump(mode="json")
    raw.update(
        frame_id=f"frame-{index}",
        observation_id=f"frame-{index}",
        captured_at=datetime.now(UTC).isoformat(),
        checksum_sha256="",
    )
    return {
        **data,
        "publication": publication,
        "online": replace(
            data["online"],
            observation=RGBDObservation.model_validate(raw),
            context_hash=publication.checkpoint.checkpoint_hash,
        ),
    }


def test_missing_api_then_unknown_debits_pool_and_publication_atomically(source):
    repo, data = source
    result = repo.route_visual_verification_if_current(request=request_for(data))
    assert result.write_disposition == "NEW_COMMIT"
    assert result.record.scope == "SOURCE_ROUTE_ONLY"
    assert result.record.route == "REOBSERVE"
    current = repo.get_visual_owner_publication(data["original"].identity.task_id)
    assert current.owner_revision == 2 and current.state_generation == 1
    assert current.verification_budget.state.remaining_reobservations == 2
    assert current.verification_budget.state.remaining_retries == 2
    assert current.retry_budget.remaining_retries == 2
    assert (
        current.verification_budget.state.deadline_at == data["original"].verification_deadline_at
    )
    assert (
        repo.get_verification_budget(current.identity.task_id).content_hash
        == current.verification_budget.content_hash
    )
    assert result.record.to_payload()["produced_publication_hash"] == current.digest()
    assert (
        repo.get_visual_verification_route(current.identity.task_id, "route-1").digest()
        == result.record.digest()
    )


def test_pass_is_local_only_does_not_refund_or_debit_retry(source):
    repo, data = source
    result = repo.route_visual_verification_if_current(request=request_for(data, unknown=False))
    assert result.record.route == "CONTINUE"
    assert result.record.scope == "SOURCE_ROUTE_ONLY"
    assert not hasattr(result.record, "execution_admitted")
    current = repo.get_visual_owner_publication(data["original"].identity.task_id)
    assert current.verification_budget.state.remaining_reobservations == 3
    assert current.verification_budget.state.remaining_retries == 2
    assert current.retry_budget.remaining_retries == 2


def test_identical_retry_and_random_key_new_generation_cannot_charge_twice(source):
    repo, data = source
    request = request_for(data)
    first = repo.route_visual_verification_if_current(request=request)
    repeated = repo.route_visual_verification_if_current(request=request)
    assert repeated.write_disposition == "HISTORICAL_DUPLICATE"
    assert repeated.record.digest() == first.record.digest()
    current = repo.get_visual_owner_publication(data["original"].identity.task_id)
    changed = {**data, "publication": current}
    repeated = repo.route_visual_verification_if_current(
        request=request_for(changed, event_key="new-uuid")
    )
    assert repeated.write_disposition == "HISTORICAL_DUPLICATE"
    assert (
        repo.get_verification_budget(current.identity.task_id).state.remaining_reobservations == 2
    )


def test_same_key_changed_payload_or_same_frame_changed_facts_conflicts(source):
    repo, data = source
    repo.route_visual_verification_if_current(request=request_for(data))
    with pytest.raises(IdempotencyConflictError):
        repo.route_visual_verification_if_current(request=request_for(data, unknown=False))
    with pytest.raises(IdempotencyConflictError):
        repo.route_visual_verification_if_current(
            request=request_for(data, unknown=False, event_key="new-key")
        )


@pytest.mark.parametrize("field", ["estop_engaged", "collision_detected", "connected"])
def test_hard_stop_precedes_observation_debit_even_with_unknown_conditions(source, field):
    repo, data = source
    robot = data["online"].robot_state.model_copy(update={field: field != "connected"})
    online = replace(data["online"], robot_state=robot, visual_facts={})
    result = repo.route_visual_verification_if_current(request=request_for(data, online=online))
    assert result.record.route == "STOP"
    assert "hard_safety_fault" in result.record.reasons
    assert (
        repo.get_verification_budget(
            data["original"].identity.task_id
        ).state.remaining_reobservations
        == 3
    )


def test_future_frame_or_wrong_context_or_versions_do_not_write(source):
    repo, data = source
    raw = data["online"].observation.model_dump(mode="json")
    raw.update(
        captured_at=(datetime.now(UTC) + timedelta(seconds=2)).isoformat(), checksum_sha256=""
    )
    bad = replace(data["online"], observation=RGBDObservation.model_validate(raw))
    for online in [
        bad,
        replace(data["online"], context_hash="b" * 64),
        replace(data["online"], plan_version=99),
    ]:
        result = repo.route_visual_verification_if_current(request=request_for(data, online=online))
        assert result is None
    assert repo.get_visual_owner_publication(data["original"].identity.task_id).owner_revision == 1


def test_expired_frame_stops_without_spending_a_capture(source):
    repo, data = source
    raw = data["online"].observation.model_dump(mode="json")
    raw.update(
        captured_at=(datetime.now(UTC) - timedelta(seconds=6)).isoformat(), checksum_sha256=""
    )
    online = replace(data["online"], observation=RGBDObservation.model_validate(raw))
    result = repo.route_visual_verification_if_current(request=request_for(data, online=online))
    assert result.record.route == "STOP"
    assert "frame_ttl_expired" in result.record.reasons
    assert (
        repo.get_verification_budget(
            data["original"].identity.task_id
        ).state.remaining_reobservations
        == 3
    )


def test_three_allowances_then_sticky_exhaustion_no_restart_or_frame_refund(source):
    repo, data = source
    for index, expected in [(1, 2), (2, 1), (3, 0), (4, 0), (5, 0)]:
        result = repo.route_visual_verification_if_current(
            request=request_for(data, event_key=f"route-{index}")
        )
        assert result.record.route == ("REOBSERVE" if index <= 3 else "STOP")
        publication = repo.get_visual_owner_publication(data["original"].identity.task_id)
        assert publication.verification_budget.state.remaining_reobservations == expected
        data = next_frame(data, publication, index + 1)
    assert publication.verification_budget.state.exhausted_reason == "no_progress_exhausted"
    assert (
        publication.verification_budget.state.deadline_at
        == data["original"].verification_deadline_at
    )


@pytest.mark.parametrize("phase", ["NATIVE_PRE_SAFETY", "NATIVE_PRE_SKILL", "CLOUD_RETURN"])
def test_native_bounds_remain_unknown_and_pre_skill_cannot_recapture_into_old_safety_context(
    source, phase
):
    repo, data = source
    result = repo.route_visual_verification_if_current(
        request=request_for(data, unknown=False, phase=phase)
    )
    assert result.record.route == ("STOP" if phase == "NATIVE_PRE_SKILL" else "REOBSERVE")
    assert result.record.scope == "SOURCE_ROUTE_ONLY"
    assert (
        result.record.to_payload()["native_context_hash"]
        != result.record.to_payload()["source_context_hash"]
    )


@pytest.mark.parametrize("phase", ["AFTER_EFFECT", "POST_HOLD", "TERMINAL"])
def test_future_effect_requirements_without_actual_completion_source_cannot_pass(source, phase):
    repo, data = source
    result = repo.route_visual_verification_if_current(
        request=request_for(data, unknown=False, phase=phase)
    )
    assert result.record.route == "STOP"
    assert "effect_completion_source_unavailable" in result.record.reasons


def test_external_legal_retry_debit_invalidates_old_source_no_pool_reconstruction(source):
    repo, data = source
    assert repo.consume_retry_if_available(
        data["original"].identity.task_id, "move", "MOVE_ABOVE", 0, "event"
    )[0]
    assert repo.route_visual_verification_if_current(request=request_for(data)) is None
    assert (
        repo.get_verification_budget(
            data["original"].identity.task_id
        ).state.remaining_reobservations
        == 3
    )


def test_full_execution_policy_cannot_weaken_original_timeout_or_conditions(source):
    repo, data = source
    contract = data["original"].contract
    changed_step = contract.steps[0].model_copy(update={"timeout_ms": 20000})
    bad = contract.model_copy(update={"steps": [changed_step, *contract.steps[1:]]})
    request = request_for(data, execution_contract=bad)
    assert repo.route_visual_verification_if_current(request=request) is None


def test_input_snapshot_and_detached_history_ignore_caller_mutations(source):
    repo, data = source
    request = request_for(data)
    original_hash = request.digest()
    data["online"].visual_facts["extra"] = {"caller": True}
    data["publication"].verification_budget.state.remaining_reobservations = 0
    assert request.digest() == original_hash
    result = repo.route_visual_verification_if_current(request=request)
    payload = result.record.to_payload()
    payload["route"] = "CONTINUE"
    assert (
        repo.get_visual_verification_route(data["original"].identity.task_id, "route-1").route
        == "REOBSERVE"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(scope="ACTUAL_SOURCE"),
        lambda p: p.update(attempt=True),
        lambda p: p.update(attempt=1.0),
        lambda p: p.update(accepted=True),
        lambda p: p["publication"]["checkpoint"].update(plan_version=True),
        lambda p: p["publication"]["retry_budget"].update(retry_count_used=False),
        lambda p: p["online"]["robot_state"].update(connected=1),
        lambda p: p["online"].update(plan_version=True),
        lambda p: p["online"]["visual_facts"].update(bad=float("nan")),
    ],
)
def test_raw_schema_rejects_coercion_unknown_fields_and_scope_forgery(source, mutation):
    _, data = source
    payload = request_for(data).to_payload()
    mutation(payload)
    with pytest.raises(ValueError):
        api().VisualVerificationRouteInput.from_json(json.dumps(payload))


def test_duplicate_json_and_unknown_phase_cannot_construct_input(source):
    _, data = source
    raw = json.dumps(request_for(data).to_payload())
    with pytest.raises(ValueError):
        api().VisualVerificationRouteInput.from_json(raw[:-1] + ',"attempt":1}')
    with pytest.raises(ValueError):
        request_for(data, phase="ACCEPTED_EXECUTION")


def test_two_sqlite_connections_commit_one_capture_claim_and_restart_preserves_history(tmp_path):
    path = tmp_path / "race.db"
    repos = [SQLiteEventAutonomyRepository(path), SQLiteEventAutonomyRepository(path)]
    data = fresh_source_values()
    original = data["original"]
    state = VerificationBudgetState(
        3, 2, 0, original.verification_deadline_at, VerificationBudget(3, 2, 3, 40)
    )
    retry = RecoveryBudget(
        budget_id="race",
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
    data["publication"] = repos[0].initialize_visual_owner_if_absent(
        original, data["source_checkpoint"], state, retry
    )
    raw = data["online"].observation.model_dump(mode="json")
    raw.update(captured_at=datetime.now(UTC).isoformat(), checksum_sha256="")
    data["online"] = replace(
        data["online"],
        observation=RGBDObservation.model_validate(raw),
        context_hash=data["source_checkpoint"].checkpoint_hash,
    )
    request = request_for(data)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda repo: repo.route_visual_verification_if_current(request=request), repos)
        )
    assert sorted(r.write_disposition for r in results) == ["HISTORICAL_DUPLICATE", "NEW_COMMIT"]
    for repo in repos:
        repo.close()
    reopened = SQLiteEventAutonomyRepository(path)
    assert (
        reopened.get_verification_budget(original.identity.task_id).state.remaining_reobservations
        == 2
    )
    assert (
        reopened.route_visual_verification_if_current(request=request).write_disposition
        == "HISTORICAL_DUPLICATE"
    )
    assert reopened.get_visual_verification_route("foreign-task", "route-1") is None
    reopened.close()


def software_completion(data, *, success=True):
    """Synthetic typed result, never actual execution source authentication."""
    from cloud_edge_robot_arm.contracts.models import SkillExecutionResult
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import digest

    original = data["original"]
    observation = data["online"].observation
    returned = observation.captured_at - timedelta(milliseconds=1)
    result = SkillExecutionResult(
        task_id=original.identity.task_id,
        plan_version=original.contract.plan_version,
        command_seq=original.contract.command_seq,
        timestamp=returned,
        step_id="move",
        skill=original.contract.steps[0].skill,
        scene_version=original.contract.scene_version,
        success=success,
        duration_ms=1,
        details={"fixture_scope": "SOFTWARE_ONLY"},
    )
    return api().VisualEffectCompletion(
        result=result,
        task_id=original.identity.task_id,
        plan_id=original.identity.plan_id,
        robot_id=original.identity.robot_id,
        step_id="move",
        attempt=1,
        plan_version=original.contract.plan_version,
        command_seq=original.contract.command_seq,
        started_at=original.registered_at,
        returned_at=returned,
        before_observation_id="before-software-attempt",
        execution_payload_hash=digest(original.contract.model_dump(mode="json")),
        source_checkpoint_hash=data["publication"].checkpoint.checkpoint_hash,
        source_hashes=original.source_hashes,
    )


def test_after_effect_with_full_typed_software_completion_recomputes_missing_effect_as_unknown(
    source,
):
    repo, data = source
    request = request_for(
        data, unknown=False, phase="AFTER_EFFECT", completion=software_completion(data)
    )
    result = repo.route_visual_verification_if_current(request=request)
    assert result.record.route == "REOBSERVE"
    assert result.record.scope == "SOURCE_ROUTE_ONLY"
    assert result.record.to_payload()["verdicts"][0]["status"] == "UNKNOWN"


def test_failed_completion_or_registered_hold_mapping_gap_cannot_be_positive(source):
    repo, data = source
    completion = software_completion(data, success=False)
    result = repo.route_visual_verification_if_current(
        request=request_for(data, phase="AFTER_EFFECT", completion=completion)
    )
    assert result.record.route == "STOP" and "effect_execution_failed" in result.record.reasons


def test_history_route_cannot_be_rehashed_to_continue_without_recomputing_native_or_canonical_state(
    source,
):
    repo, data = source
    result = repo.route_visual_verification_if_current(
        request=request_for(data, phase="NATIVE_PRE_SKILL")
    )
    payload = result.record.to_payload()
    payload["route"] = "CONTINUE"
    with pytest.raises(ValueError):
        api().VisualVerificationRouteRecord(payload)


def test_sqlite_insert_failure_rolls_back_pool_publication_and_claim(source):
    import sqlite3

    repo, data = source
    if not isinstance(repo, SQLiteEventAutonomyRepository):
        pytest.skip("SQLite trigger covers transactional persistence; memory pre-encodes rows")
    repo._conn.execute(
        "CREATE TRIGGER reject_route BEFORE INSERT ON visual_verification_routes "
        "BEGIN SELECT RAISE(ABORT, 'fixture write fault'); END"
    )
    repo._conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        repo.route_visual_verification_if_current(request=request_for(data))
    assert repo.get_visual_owner_publication(data["original"].identity.task_id).owner_revision == 1
    assert (
        repo.get_verification_budget(
            data["original"].identity.task_id
        ).state.remaining_reobservations
        == 3
    )
    assert repo.get_visual_verification_route(data["original"].identity.task_id, "route-1") is None


def test_camera_descriptor_given_in_full_registered_specs_must_match_exact_rgbd(source):
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.vision.owner_registration import (
        OriginalActionRequirements,
        freeze_original_visual_plan,
    )

    repo, data = source
    original = data["original"]
    requirements = dict(original.requirements)
    requirement = requirements["move"]
    pre = tuple(
        ConditionSpec(
            c.name,
            c.target_id,
            {**dict(c.tolerances), "camera_source_descriptor_sha256": "b" * 64},
            c.sensor_requirements,
        )
        for c in requirement.preconditions
    )
    requirements["move"] = OriginalActionRequirements(
        requirement.original_step,
        pre,
        requirement.postconditions,
        requirement.allowed_error_m,
        requirement.sensor_requirements,
        requirement.ordinary_ttl_s,
        requirement.expected_duration_s,
        requirement.policy_source_hashes,
    )
    changed = freeze_original_visual_plan(
        **{**original.freeze_inputs(), "requirements": requirements}
    )
    # Isolate a NEW coherent source registration; changing an initialized original is forbidden.
    other = InMemoryEventAutonomyRepository()
    state = data["publication"].verification_budget.state
    pub = other.initialize_visual_owner_if_absent(
        changed, data["source_checkpoint"], state, data["publication"].retry_budget
    )
    request = request_for({**data, "original": changed, "publication": pub})
    assert other.route_visual_verification_if_current(request=request) is None


def test_pass_preserves_old_no_progress_and_budgets_while_keeping_best_history(source):
    repo, data = source
    first = repo.route_visual_verification_if_current(request=request_for(data))
    assert first.record.route == "REOBSERVE"
    pub = repo.get_visual_owner_publication(data["original"].identity.task_id)
    data = next_frame(data, pub, 2)
    second = repo.route_visual_verification_if_current(
        request=request_for(data, event_key="second")
    )
    assert second.record.route == "REOBSERVE"
    pub = repo.get_visual_owner_publication(data["original"].identity.task_id)
    assert pub.verification_budget.state.consecutive_no_progress == 1
    data = next_frame(data, pub, 3)
    observation = data["online"].observation
    facts = {
        "target_visible": {
            "source": "rgbd_estimate",
            "observation_id": observation.observation_id,
            "target_id": "obj-1",
            "identity_confirmed": True,
            "value": True,
            "pixel": [0, 0],
        }
    }
    data["online"] = replace(data["online"], visual_facts=facts)
    result = repo.route_visual_verification_if_current(
        request=request_for(data, unknown=False, event_key="pass")
    )
    assert result.record.route == "CONTINUE"
    state = repo.get_verification_budget(data["original"].identity.task_id).state
    assert state.consecutive_no_progress == 1 and state.remaining_reobservations == 1
    assert any(status == "PASS" for status, _ in state.previous_conditions.values())


@pytest.mark.parametrize("row_kind", ["checkpoint", "active"])
def test_current_repository_source_rows_cannot_hide_unknown_serialized_fields(source, row_kind):
    repo, data = source
    task = data["original"].identity.task_id
    if isinstance(repo, InMemoryEventAutonomyRepository):
        if row_kind == "checkpoint":
            checkpoint = repo._checkpoints[data["source_checkpoint"].checkpoint_id]
            repo._checkpoints[checkpoint.checkpoint_id] = checkpoint.model_copy(
                update={"undeclared_source": True}
            )
        else:
            repo._active_contracts[task] = repo._active_contracts[task].model_copy(
                update={"undeclared_source": True}
            )
    else:
        table, column = (
            ("execution_checkpoints", "payload_json")
            if row_kind == "checkpoint"
            else ("active_task_contracts", "record_json")
        )
        row = repo._conn.execute(
            f"SELECT {column} FROM {table} WHERE task_id=?", (task,)
        ).fetchone()
        payload = json.loads(row[0])
        payload["undeclared_source"] = True
        repo._conn.execute(
            f"UPDATE {table} SET {column}=? WHERE task_id=?", (json.dumps(payload), task)
        )
        repo._conn.commit()
    assert repo.route_visual_verification_if_current(request=request_for(data)) is None
    assert repo.get_verification_budget(task).state.remaining_reobservations == 3


def test_changed_camera_descriptor_and_calibration_are_bound_to_original_full_specs(source):
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.vision.owner_registration import (
        OriginalActionRequirements,
        freeze_original_visual_plan,
    )

    _, data = source
    original = data["original"]
    old = original.requirements["move"]
    descriptor = api().camera_source_descriptor_sha256(data["online"].observation)
    pre = tuple(
        ConditionSpec(
            c.name,
            c.target_id,
            {
                **dict(c.tolerances),
                "camera_source_descriptor_sha256": descriptor,
                "calibration_version": data["online"].observation.calibration_version,
            },
            c.sensor_requirements,
        )
        for c in old.preconditions
    )
    requirements = {
        **dict(original.requirements),
        "move": OriginalActionRequirements(
            old.original_step,
            pre,
            old.postconditions,
            old.allowed_error_m,
            old.sensor_requirements,
            old.ordinary_ttl_s,
            old.expected_duration_s,
            old.policy_source_hashes,
        ),
    }
    original = freeze_original_visual_plan(
        **{**original.freeze_inputs(), "requirements": requirements}
    )
    repo = InMemoryEventAutonomyRepository()
    pub = repo.initialize_visual_owner_if_absent(
        original,
        data["source_checkpoint"],
        data["publication"].verification_budget.state,
        data["publication"].retry_budget,
    )
    data = {**data, "original": original, "publication": pub}
    assert repo.route_visual_verification_if_current(request=request_for(data)) is not None
    # Same descriptor-inventory source, NEW synthetic frame with changed intrinsics.
    pub = repo.get_visual_owner_publication(original.identity.task_id)
    data = next_frame(data, pub, 8)
    raw = data["online"].observation.model_dump(mode="json")
    raw.update(intrinsics=[120.0, 120.0, 1.0, 1.0], checksum_sha256="")
    online = replace(data["online"], observation=RGBDObservation.model_validate(raw))
    assert (
        repo.route_visual_verification_if_current(
            request=request_for(data, online=online, event_key="changed-camera")
        )
        is None
    )


def test_stale_pool_cancel_and_completed_step_do_not_authorize_new_route(source):
    repo, data = source
    task = data["original"].identity.task_id
    repo.save_state(task, "CANCELLED", "software cancel")
    assert repo.route_visual_verification_if_current(request=request_for(data)) is None
    assert repo.get_verification_budget(task).state.remaining_reobservations == 3


def test_transaction_clock_requires_aware_domain_without_writing(source):
    repo, data = source
    m = api()
    publication = data["publication"]
    with pytest.raises(ValueError):
        m.derive_route(
            request_for(data),
            data["original"],
            publication,
            None,
            repo.get_active_contract(data["original"].identity.task_id),
            data["source_checkpoint"],
            repo.get_verification_budget(data["original"].identity.task_id),
            publication.retry_budget,
            cancelled=False,
            now=datetime(2026, 10, 5),
        )
    assert repo.get_verification_budget(data["original"].identity.task_id).revision == 0


def test_same_named_conditions_keep_separate_target_spec_progress_histories(source):
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.vision.owner_registration import (
        OriginalActionRequirements,
        freeze_original_visual_plan,
    )

    _, data = source
    original = data["original"]
    old = original.requirements["move"]
    pre = (
        *old.preconditions,
        ConditionSpec("target_visible", original.contract.task_target.target_region_id),
    )
    requirements = {
        **dict(original.requirements),
        "move": OriginalActionRequirements(
            old.original_step,
            pre,
            old.postconditions,
            old.allowed_error_m,
            old.sensor_requirements,
            old.ordinary_ttl_s,
            old.expected_duration_s,
            old.policy_source_hashes,
        ),
    }
    original = freeze_original_visual_plan(
        **{**original.freeze_inputs(), "requirements": requirements}
    )
    repo = InMemoryEventAutonomyRepository()
    pub = repo.initialize_visual_owner_if_absent(
        original,
        data["source_checkpoint"],
        data["publication"].verification_budget.state,
        data["publication"].retry_budget,
    )
    result = repo.route_visual_verification_if_current(
        request=request_for({**data, "original": original, "publication": pub})
    )
    assert result.record.route == "REOBSERVE"
    state = repo.get_verification_budget(original.identity.task_id).state
    assert len(state.previous_conditions) == 2
