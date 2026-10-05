"""Actual repository coordination, using explicitly synthetic RGB-D/model sources."""

from __future__ import annotations

import hashlib
import importlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import pytest

from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
from cloud_edge_robot_arm.contracts.models import RobotState, SkillExecutionResult
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import digest
from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
    VisualEffectCompletion,
)
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import StepGroundingBinding
from tests.test_ced_runtime_binding import role_binding
from tests.test_visual_owner_registration import values


def api():
    return importlib.import_module("cloud_edge_robot_arm.vision.worker_runtime")


@pytest.fixture(params=["memory", "sqlite"])
def runtime_source(request, tmp_path):
    module = api()
    jobs = SQLiteSimulationJobRepository(tmp_path / "jobs.db")
    job = jobs.create_job(
        run_id="software-runtime-run",
        batch_id="",
        backend="MUJOCO",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="CLOUD",
        seed=0,
        manifest_id="software-manifest",
        reproducibility_hash="a" * 64,
        draft={},
        timeout_seconds=120,
        max_attempts=2,
        artifact_root="software-only",
        source_commit="software-only",
        source_tree_hash="b" * 64,
    )
    jobs.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="software",
        worker_id="",
        lease_id="",
    )
    lease = jobs.acquire_lease(worker_id="runtime-worker", backend="MUJOCO", lease_ttl_seconds=120)
    assert lease is not None
    attempt = jobs.start_attempt(job.job_id, worker_id=lease.worker_id)
    for old, new in [
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ]:
        assert jobs.update_status_cas(
            job.job_id,
            expected=old,
            next_status=new,
            reason_code="software",
            worker_id=lease.worker_id,
            lease_id=lease.lease_id,
            expected_lease_id=lease.lease_id,
        )
    events = (
        InMemoryEventAutonomyRepository()
        if request.param == "memory"
        else SQLiteEventAutonomyRepository(tmp_path / "events.db")
    )
    (tmp_path / "sources").mkdir()
    _, binding = role_binding(tmp_path / "sources")
    root = binding.root
    repository_root = Path(__file__).resolve().parents[1]
    for name in module.REQUIRED_WORKER_RUNTIME_SOURCES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((repository_root / name).read_bytes())
    names = set(module.REQUIRED_WORKER_RUNTIME_SOURCES)
    for hashes in (
        binding.bundle.cloud_snapshot.source_hashes,
        binding.edge_snapshot.source_hashes,
        binding.device_source_hashes,
    ):
        names.update(hashes)
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}
    source = module.WorkerRuntimeSource(
        job_repository=jobs,
        event_repository=events,
        job_id=job.job_id,
        run_id=job.run_id,
        worker_id=lease.worker_id,
        lease_id=lease.lease_id,
        source_root=root,
        source_hashes=hashes,
        robot_id="software-robot-instance",
        plan_id="software-runtime-plan",
        task_started_at=attempt.started_at,
        task_timeout_s=120.0,
    )
    data = dict(source=source, binding=binding, jobs=jobs, events=events)
    yield data
    if request.param == "sqlite":
        events.close()


def runtime(data, **changes):
    kwargs = dict(
        episode_id="software-runtime-episode",
        instruction="move the visible box",
        role_binding=data["binding"],
        model_snapshot_hash="5" * 64,
        verification_limits=VerificationBudget(2, 0, 3, 120.0),
    )
    kwargs.update(changes)
    return api().VisualWorkerRuntime(data["source"], **kwargs)


def frame(identifier="software-frame"):
    payload = values()["online"].observation.model_dump(mode="json")
    payload.update(
        frame_id=identifier,
        observation_id=identifier,
        episode_id="software-runtime-episode",
        captured_at=datetime.now(UTC).isoformat(),
        checksum_sha256="",
    )
    return RGBDObservation.model_validate(payload)


def capture(owner, *, initial=False, identifier="software-frame"):
    robot = RobotState(connected=True)
    claim = owner.reserve_capture(robot, initial=initial)
    observation = frame(identifier)
    owner.complete_capture(claim, observation, robot)
    return observation


def plan(owner, observation, *, usable=True):
    robot = RobotState(connected=True)
    claim = owner.reserve_plan(robot)
    parsed = (
        {
            **values()["original"].contract.model_dump(mode="json"),
            "user_instruction": "move the visible box",
        }
        if usable
        else {"_sentinel": "REQUEST_MORE_OBSERVATION"}
    )
    draft = PlannerDraft(
        raw_text="SOFTWARE_ONLY reply",
        parsed_json=parsed,
        observation_evidence={
            **observation.evidence(),
            "model_snapshot_hash": "5" * 64,
            "role_bundle_hash": owner.bootstrap.definition.role_bundle_hash,
        },
    )
    owner.complete_plan(claim, draft, robot)
    return draft


def test_runtime_joins_real_attempt_and_original_deadlines_before_any_effect(runtime_source):
    owner = runtime(runtime_source)
    assert owner.bootstrap.definition.lease.attempt == 1
    assert owner.bootstrap.definition.task_started_at == runtime_source["source"].task_started_at
    assert owner.verification_state.remaining_reobservations == 2
    assert not owner.is_adopted
    assert owner.episode_id == "software-runtime-episode"
    assert not hasattr(owner, "execution_permission")


def test_capture_plan_adoption_preserves_full_original_and_persisted_pools(runtime_source):
    owner = runtime(runtime_source)
    observation = capture(owner, initial=True)
    draft = plan(owner, observation)
    contract, publication = owner.adopt_plan(RobotState(connected=True))
    assert contract.safety_constraints.model_dump() == draft.parsed_json["safety_constraints"]
    assert [step.model_dump(mode="json") for step in contract.steps] == draft.parsed_json["steps"]
    assert publication.identity.job_id == runtime_source["source"].job_id
    assert publication.checkpoint.completed_step_ids == []
    assert publication.checkpoint.pending_step_ids == [step.step_id for step in contract.steps]
    assert (
        publication.verification_budget.state.deadline_at
        == owner.bootstrap.verification_state.deadline_at
    )
    assert owner.is_adopted and owner.original.digest() == publication.original_plan_hash
    assert owner.publication.digest() == publication.digest()


def test_unusable_replies_spend_reobservations_before_capture_then_adopt_without_reset(
    runtime_source,
):
    owner = runtime(runtime_source)
    observation = capture(owner, initial=True)
    for number in (1, 2):
        plan(owner, observation, usable=False)
        observation = capture(owner, identifier=f"software-frame-{number}")
        assert owner.verification_state.remaining_reobservations == 2 - number
    plan(owner, observation)
    before = asdict(owner.verification_state)
    _, publication = owner.adopt_plan(RobotState(connected=True))
    assert asdict(publication.verification_budget.state) == before


def test_restart_cannot_repeat_or_complete_lost_pending_capture(runtime_source):
    owner = runtime(runtime_source)
    claim = owner.reserve_capture(RobotState(connected=True), initial=True)
    restarted = runtime(runtime_source)
    assert restarted.bootstrap.pending_claim_id == claim
    with pytest.raises(RuntimeError):
        restarted.reserve_capture(RobotState(connected=True), initial=True)
    with pytest.raises(RuntimeError):
        restarted.complete_capture(claim, frame(), RobotState(connected=True))
    assert restarted.bootstrap.pending_claim_id == claim


def test_cancel_between_claim_and_actual_return_rejects_receipt_without_replay(runtime_source):
    owner = runtime(runtime_source)
    claim = owner.reserve_capture(RobotState(connected=True), initial=True)
    observation = frame()
    runtime_source["jobs"].request_cancel(runtime_source["source"].job_id)
    with pytest.raises(RuntimeError, match="lease"):
        owner.complete_capture(claim, observation, RobotState(connected=True))
    assert owner.bootstrap.pending_claim_id == claim
    assert owner.bootstrap.observation is None


def test_source_drift_after_request_claim_rejects_completion(runtime_source):
    owner = runtime(runtime_source)
    observation = capture(owner, initial=True)
    claim = owner.reserve_plan(RobotState(connected=True))
    path = (
        runtime_source["source"].source_root / "src/cloud_edge_robot_arm/vision/worker_runtime.py"
    )
    path.write_text("# source changed during provider request\n")
    with pytest.raises(RuntimeError, match="source"):
        owner.complete_plan(
            claim, PlannerDraft(raw_text="reply", parsed_json={}), RobotState(connected=True)
        )
    assert owner.bootstrap.pending_claim_id == claim
    assert owner.bootstrap.draft is None and observation is not None


@pytest.mark.parametrize("field", ["estop_engaged", "collision_detected", "connected"])
def test_hard_stop_prevents_allocating_any_capture(runtime_source, field):
    owner = runtime(runtime_source)
    robot = RobotState(connected=True).model_copy(update={field: field != "connected"})
    with pytest.raises(RuntimeError, match="safety"):
        owner.reserve_capture(robot, initial=True)
    assert owner.bootstrap.pending_claim_id is None
    assert owner.verification_state.remaining_reobservations == 2


def test_two_live_coordinators_cannot_both_receive_same_effect_claim(runtime_source):
    owners = [runtime(runtime_source), runtime(runtime_source)]

    def reserve(owner):
        try:
            return owner.reserve_capture(RobotState(connected=True), initial=True)
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(reserve, owners))
    assert sum(claim is not None for claim in claims) == 1


def test_restart_changed_original_limits_rejected_without_refilling(runtime_source):
    owner = runtime(runtime_source)
    owner.reserve_capture(RobotState(connected=True), initial=True)
    with pytest.raises((RuntimeError, ValueError)):
        runtime(runtime_source, verification_limits=VerificationBudget(3, 0, 3, 120.0))
    assert owner.bootstrap.pending_claim_id is not None


def test_root_source_inventory_must_include_exact_role_sources(runtime_source):
    source = runtime_source["source"]
    missing = dict(source.source_hashes)
    missing.pop("cloud.py")
    runtime_source["source"] = replace(source, source_hashes=missing)
    with pytest.raises((RuntimeError, ValueError), match="role"):
        runtime(runtime_source)


def adopted_owner(data):
    owner = runtime(data)
    observation = capture(owner, initial=True)
    plan(owner, observation)
    contract, publication = owner.adopt_plan(RobotState(connected=True))
    return owner, observation, contract, publication


def online_for(owner, observation):
    publication = owner.publication
    return OnlineEvidenceSnapshot(
        observation,
        RobotState(connected=True),
        values()["online"].visual_facts,
        publication.checkpoint.plan_version,
        publication.checkpoint.command_seq,
        publication.checkpoint.checkpoint_hash,
    )


def test_durable_unknown_route_claim_allows_exactly_one_owned_reobservation(runtime_source):
    owner, observation, contract, _ = adopted_owner(runtime_source)
    before = owner.verification_state.remaining_reobservations
    result = owner.route(
        online_for(owner, observation),
        step_id=contract.steps[0].step_id,
        phase="CLOUD_RETURN",
        execution_contract=contract,
    )
    assert result.write_disposition == "NEW_COMMIT" and result.record.route == "REOBSERVE"
    assert owner.verification_state.remaining_reobservations == before - 1
    claim = owner.reserve_capture(RobotState(connected=True))
    fresh = frame("software-ordinary-fresh")
    owner.complete_capture(claim, fresh, RobotState(connected=True))
    with pytest.raises(RuntimeError):
        owner.reserve_capture(RobotState(connected=True))
    assert owner.verification_state.remaining_reobservations == before - 1


def test_restart_does_not_recover_durable_reobservation_as_effect_permission(runtime_source):
    owner, observation, contract, _ = adopted_owner(runtime_source)
    owner.route(
        online_for(owner, observation),
        step_id=contract.steps[0].step_id,
        phase="CLOUD_RETURN",
        execution_contract=contract,
    )
    restarted = runtime(runtime_source)
    assert restarted.verification_state.remaining_reobservations == 1
    with pytest.raises(RuntimeError):
        restarted.reserve_capture(RobotState(connected=True))


def test_historical_route_never_reauthorizes_consumed_reobservation(runtime_source):
    owner, observation, contract, _ = adopted_owner(runtime_source)
    owner.route(
        online_for(owner, observation),
        step_id=contract.steps[0].step_id,
        phase="CLOUD_RETURN",
        execution_contract=contract,
    )
    claim = owner.reserve_capture(RobotState(connected=True))
    owner.complete_capture(claim, frame("software-once"), RobotState(connected=True))
    with pytest.raises(RuntimeError, match="historical"):
        owner.route(
            online_for(owner, observation),
            step_id=contract.steps[0].step_id,
            phase="CLOUD_RETURN",
            execution_contract=contract,
        )
    assert owner.verification_state.remaining_reobservations == 1


def completion_for(owner, observation, contract):
    original, publication = owner.original, owner.publication
    step = contract.steps[0]
    started = datetime.now(UTC)
    result = SkillExecutionResult(
        task_id=contract.task_id,
        plan_version=contract.plan_version,
        command_seq=contract.command_seq,
        timestamp=datetime.now(UTC),
        step_id=step.step_id,
        skill=step.skill,
        scene_version=contract.scene_version,
        success=True,
        duration_ms=0,
        details={"scope": "SOFTWARE_ONLY"},
    )
    return VisualEffectCompletion(
        result=result,
        task_id=contract.task_id,
        plan_id=original.identity.plan_id,
        robot_id=original.identity.robot_id,
        step_id=step.step_id,
        attempt=1,
        plan_version=contract.plan_version,
        command_seq=contract.command_seq,
        started_at=started,
        returned_at=datetime.now(UTC),
        before_observation_id=observation.observation_id,
        execution_payload_hash=digest(contract.model_dump(mode="json")),
        source_checkpoint_hash=publication.checkpoint.checkpoint_hash,
        source_hashes=owner.source.source_hashes,
    )


def test_typed_result_source_allows_one_effect_frame_without_refilling_or_debit(runtime_source):
    owner, observation, contract, _ = adopted_owner(runtime_source)
    completion = completion_for(owner, observation, contract)
    before = asdict(owner.verification_state)
    claim = owner.reserve_effect_capture(
        completion, RobotState(connected=True), purpose="AFTER_EFFECT"
    )
    owner.complete_capture(claim, frame("software-effect-frame"), RobotState(connected=True))
    assert asdict(owner.verification_state) == before
    with pytest.raises(RuntimeError):
        owner.reserve_effect_capture(completion, RobotState(connected=True), purpose="AFTER_EFFECT")


def test_changed_or_failed_result_does_not_allocate_effect_frame(runtime_source):
    owner, observation, contract, _ = adopted_owner(runtime_source)
    completion = completion_for(owner, observation, contract)
    raw = completion.to_payload()
    raw["result"]["success"] = False
    failed = VisualEffectCompletion.from_payload(raw)
    with pytest.raises(RuntimeError):
        owner.reserve_effect_capture(failed, RobotState(connected=True), purpose="AFTER_EFFECT")
    raw = completion.to_payload()
    raw["source_checkpoint_hash"] = "f" * 64
    changed = VisualEffectCompletion.from_payload(raw)
    with pytest.raises(RuntimeError):
        owner.reserve_effect_capture(changed, RobotState(connected=True), purpose="AFTER_EFFECT")


def test_completion_cursor_does_not_advance_from_caller_success_or_missing_canonical_routes(
    runtime_source,
):
    owner, _, contract, publication = adopted_owner(runtime_source)
    with pytest.raises(RuntimeError, match="canonical"):
        owner.complete_step(contract.steps[0].step_id, RobotState(connected=True))
    assert owner.publication.checkpoint.checkpoint_hash == publication.checkpoint.checkpoint_hash
    assert owner.publication.checkpoint.completed_step_ids == []


def test_grounding_publication_binds_exact_original_and_rejects_stale_binding(runtime_source):
    owner, observation, contract, publication = adopted_owner(runtime_source)
    step = contract.steps[0].model_copy(
        update={"preconditions": [], "success_conditions": []}, deep=True
    )
    now = datetime.now(UTC)
    binding = StepGroundingBinding(
        owner.original.digest(),
        owner.original.identity,
        owner.original.requirements[step.step_id],
        publication.owner_revision,
        publication.state_generation + 1,
        publication.checkpoint.checkpoint_hash,
        observation.observation_id,
        observation.checksum_sha256,
        observation.calibration_version,
        contract.plan_version,
        contract.command_seq,
        "6" * 64,
        "7" * 64,
        None,
        owner.source.source_hashes,
        step.model_dump_json(),
        owner.original.requirements[step.step_id].expected_duration_s,
        now,
        now + timedelta(seconds=3),
    )
    published = owner.publish_grounding(binding, RobotState(connected=True))
    assert digest(published.to_payload()["grounding"]) == binding.binding_hash
    assert (
        published.checkpoint.safety_state["original_requirements_hash"]
        == binding.original_requirements.digest()
    )
    with pytest.raises(RuntimeError):
        owner.publish_grounding(binding, RobotState(connected=True))


def test_changed_role_policy_cannot_keep_old_bundle_hash_and_allocate_capture(runtime_source):
    owner = runtime(runtime_source)
    changed = dict(owner.role_binding.edge_policy)
    changed["local_recover_enabled"] = True
    object.__setattr__(owner.role_binding, "edge_policy", MappingProxyType(changed))
    with pytest.raises(RuntimeError, match="role policy"):
        owner.reserve_capture(RobotState(connected=True), initial=True)
    assert owner.bootstrap.pending_claim_id is None


def test_unconsumed_reobservation_claim_prevents_a_second_route_debit(runtime_source):
    owner, observation, contract, _ = adopted_owner(runtime_source)
    owner.route(
        online_for(owner, observation),
        step_id=contract.steps[0].step_id,
        phase="CLOUD_RETURN",
        execution_contract=contract,
    )
    before = asdict(owner.verification_state)
    with pytest.raises(RuntimeError, match="unconsumed"):
        owner.route(
            online_for(owner, frame("software-too-soon")),
            step_id=contract.steps[0].step_id,
            phase="CLOUD_RETURN",
            execution_contract=contract,
        )
    assert asdict(owner.verification_state) == before


def test_restart_never_reconstructs_typed_effect_capture_permission(runtime_source):
    owner, observation, contract, _ = adopted_owner(runtime_source)
    completion = completion_for(owner, observation, contract)
    restarted = runtime(runtime_source)
    with pytest.raises(RuntimeError, match="live owner"):
        restarted.reserve_effect_capture(completion, RobotState(connected=True))
