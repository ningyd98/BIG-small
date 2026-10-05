"""SOFTWARE_ONLY complete effects in concrete repositories; zero robot actions."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import sleep

import pytest

from cloud_edge_robot_arm.contracts import Pose, RobotState, SkillName
from cloud_edge_robot_arm.contracts.models import RecoveryBudget, SkillExecutionResult
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    ConditionStatus,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import digest
from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
    VisualEffectCompletion,
    VisualVerificationRouteInput,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import StepGroundingBinding
from cloud_edge_robot_arm.vision.worker_owner import compile_worker_original_plan
from tests.test_visual_owner_registration import values
from tests.test_visual_worker_owner import compilation

pytest_plugins = ["tests.test_visual_worker_owner"]


def compiled(running, *, skill=SkillName.LIFT, criteria=None, hold=False):
    data = compilation(running)
    before = data["contract"]
    step = before.steps[0].model_copy(
        update={
            "step_id": "effect",
            "skill": skill,
            "preconditions": ["gripper_holding"],
            "success_conditions": ["tcp_above_safe_height"],
        },
        deep=True,
    )
    steps = [step]
    if hold:
        steps.append(step.model_copy(update={"step_id": "retreat", "skill": SkillName.RETREAT}))
    data["contract"] = before.model_copy(
        update={
            "steps": steps,
            "completion_criteria": criteria
            or ["object_inside_target_region", "gripper_released", "robot_in_safe_pose"],
        },
        deep=True,
    )
    return data, compile_worker_original_plan(**data)


def test_lift_registers_complete_hold_and_original_terminal_criteria(running):
    data, original = compiled(running)
    requirement = original.requirements["effect"]
    names = {spec.name for spec in requirement.postconditions}
    assert {"object_held", "object_lifted", "object_stable"} <= names
    assert {"object_inside_target_region", "gripper_released", "robot_in_safe_pose"} <= names
    assert original.contract == data["contract"]
    assert requirement.original_step.timeout_ms == 10000
    assert requirement.original_step.retry_limit == 0


@pytest.mark.parametrize("field", ["preconditions", "success_conditions", "completion_criteria"])
def test_unknown_original_criterion_fails_registration_without_dropping_it(running, field):
    data = compilation(running)
    contract = data["contract"]
    if field == "completion_criteria":
        contract = contract.model_copy(update={field: ["unregistered_remote_claim"]}, deep=True)
    else:
        step = contract.steps[0].model_copy(
            update={field: ["unregistered_remote_claim"]}, deep=True
        )
        contract = contract.model_copy(update={"steps": [step, *contract.steps[1:]]}, deep=True)
    with pytest.raises(ValueError, match="condition"):
        compile_worker_original_plan(**{**data, "contract": contract})


@pytest.mark.parametrize(
    "feedback, expected",
    [
        ({"connected": True, "gripper_open": False, "holding_object_id": "obj-1"}, "PASS"),
        ({"connected": True, "gripper_open": True, "holding_object_id": "obj-1"}, "FAIL"),
        ({"connected": True, "gripper_open": False, "holding_object_id": "other"}, "FAIL"),
        ({"connected": False, "gripper_open": False, "holding_object_id": "obj-1"}, "UNKNOWN"),
    ],
)
def test_object_held_requires_current_visual_identity_and_proprioception(
    running, feedback, expected
):
    data = compilation(running)
    now = datetime.now(UTC)
    online = values()["online"]
    observation = data["observation"].model_copy(
        update={"captured_at": now, "checksum_sha256": ""}, deep=True
    )
    fact = {
        "source": "rgbd_estimate",
        "observation_id": observation.observation_id,
        "target_id": "obj-1",
        "identity_confirmed": True,
        "pixel": [0, 0],
        "value": True,
    }
    online = replace(
        online,
        observation=observation,
        robot_state=RobotState(**feedback),
        visual_facts={"object_held": fact},
    )
    spec = ConditionSpec("object_held", "obj-1", {"holding_feedback_required": True})
    verdict = evaluate_conditions([spec], online, now=now)[0]
    assert verdict.status.value == expected
    missing = evaluate_conditions(
        [spec],
        replace(online, visual_facts={"target_visible": fact}),
        now=now,
    )[0]
    assert missing.status == ConditionStatus.UNKNOWN
    stale = evaluate_conditions(
        [spec],
        replace(online, visual_facts={"object_held": {**fact, "observation_id": "earlier"}}),
        now=now + timedelta(milliseconds=1),
    )[0]
    assert stale.status == ConditionStatus.UNKNOWN


@pytest.fixture
def effect_skill(request):
    return getattr(request, "param", SkillName.RETREAT)


@pytest.fixture
def effect_ttl(request):
    return getattr(request, "param", 3.0)


@pytest.fixture(params=["memory", "sqlite"])
def effect_source(running, request, tmp_path, effect_skill, effect_ttl):
    data, original = compiled(running, skill=effect_skill, hold=effect_skill == SkillName.LIFT)
    repo = (
        InMemoryEventAutonomyRepository()
        if request.param == "memory"
        else SQLiteEventAutonomyRepository(tmp_path / "effects.db")
    )
    now = datetime.now(UTC)
    source_checkpoint = values()["source_checkpoint"].model_copy(
        update={
            "plan_id": original.identity.plan_id,
            "robot_id": original.identity.robot_id,
            "current_step_id": "effect",
            "pending_step_ids": [s.step_id for s in original.contract.steps],
            "completed_step_ids": [],
            "current_step_index": 0,
            "created_at": data["registered_at"],
            "updated_at": now,
            "checkpoint_hash": "",
        },
        deep=True,
    )
    source_checkpoint = source_checkpoint.model_copy(
        update={"checkpoint_hash": checkpoint_digest(source_checkpoint)}
    )
    retry = RecoveryBudget(
        budget_id="full-effect-software",
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
    prior = repo.initialize_visual_owner_if_absent(original, source_checkpoint, state, retry)
    step = original.contract.steps[0].model_copy(
        update={
            "parameters": {"target_pose": {"x": 0.2, "y": 0.1, "z": 0.16}},
            "preconditions": [],
            "success_conditions": [],
        },
        deep=True,
    )
    receipt = StepGroundingBinding(
        original.digest(),
        original.identity,
        original.requirements["effect"],
        prior.owner_revision,
        1,
        prior.checkpoint.checkpoint_hash,
        data["observation"].observation_id,
        data["observation"].checksum_sha256,
        data["observation"].calibration_version,
        original.contract.plan_version,
        original.contract.command_seq,
        "a" * 64,
        "a" * 64,
        None,
        original.source_hashes,
        step.model_dump_json(),
        original.requirements["effect"].expected_duration_s,
        now,
        now + timedelta(seconds=effect_ttl),
    )
    checkpoint = prior.checkpoint.model_copy(
        update={
            "checkpoint_id": prior.checkpoint.checkpoint_id + "-grounded-effects",
            "updated_at": datetime.now(UTC),
            "safety_state": {
                **prior.checkpoint.safety_state,
                "grounding_binding_hash": receipt.binding_hash,
                "original_requirements_hash": original.requirements["effect"].digest(),
            },
            "checkpoint_hash": "",
        },
        deep=True,
    )
    checkpoint = checkpoint.model_copy(update={"checkpoint_hash": checkpoint_digest(checkpoint)})
    publication = repo.publish_visual_boundary_if_current(
        task_id=original.identity.task_id,
        owner_epoch=original.identity.owner_epoch,
        expected_owner_revision=prior.owner_revision,
        expected_contract_hash=prior.to_payload()["contract_hash"],
        expected_checkpoint_hash=prior.checkpoint.checkpoint_hash,
        checkpoint=checkpoint,
        grounding=receipt,
        state_generation=1,
    )
    assert publication is not None
    execution = original.contract.model_copy(
        update={"steps": [step, *original.contract.steps[1:]]}, deep=True
    )
    yield repo, data, original, publication, receipt, execution
    if request.param == "sqlite":
        repo.close()


def effect_request(
    source,
    *,
    phase="TERMINAL",
    missing=None,
    completion=True,
    same_frame=False,
    receipt=True,
    event_key="terminal",
    wrong_target=False,
):
    _, data, original, publication, binding, contract = source
    returned = datetime.now(UTC)
    observation = RGBDObservation.model_validate(
        {
            **data["observation"].model_dump(),
            "frame_id": event_key,
            "observation_id": event_key,
            "captured_at": datetime.now(UTC),
            "checksum_sha256": "",
        }
    )
    facts = {
        "object_inside_target_region": {
            "source": "rgbd_estimate",
            "observation_id": observation.observation_id,
            "target_id": original.contract.task_target.object_id,
            "identity_confirmed": True,
            "pixel": [0, 0],
            "value": True,
        }
    }
    is_hold = contract.steps[0].skill == SkillName.LIFT
    if is_hold:
        facts = {
            name: {**facts["object_inside_target_region"]}
            for name in ("object_held", "object_lifted", "object_stable")
        }
    if missing:
        facts.pop(missing, None)
    online = replace(
        values()["online"],
        observation=observation,
        visual_facts=facts,
        robot_state=RobotState(
            connected=True,
            gripper_open=not is_hold,
            holding_object_id=original.contract.task_target.object_id if is_hold else None,
            tcp_pose=Pose(x=0.2, y=0.1, z=0.16),
        ),
        context_hash=publication.checkpoint.checkpoint_hash,
    )
    typed = VisualEffectCompletion(
        result=SkillExecutionResult(
            task_id=original.identity.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            timestamp=returned,
            step_id="effect",
            skill=contract.steps[0].skill,
            scene_version=contract.scene_version,
            success=True,
            duration_ms=1,
            details={"fixture_scope": "SOFTWARE_ONLY"},
        ),
        task_id=original.identity.task_id,
        plan_id=original.identity.plan_id,
        robot_id=original.identity.robot_id,
        step_id="effect",
        attempt=1,
        plan_version=contract.plan_version,
        command_seq=contract.command_seq,
        started_at=binding.created_at,
        returned_at=returned,
        before_observation_id=observation.observation_id if same_frame else "before-effect",
        execution_payload_hash=digest(contract.model_dump(mode="json")),
        source_checkpoint_hash=publication.checkpoint.checkpoint_hash,
        source_hashes=original.source_hashes,
    )
    if wrong_target:
        step = contract.steps[0].model_copy(deep=True)
        step.parameters["target_pose"]["x"] = 0.3
        contract = contract.model_copy(update={"steps": [step, *contract.steps[1:]]}, deep=True)
    return VisualVerificationRouteInput(
        original=original,
        publication=publication,
        online=online,
        step_id="effect",
        attempt=1,
        phase=phase,
        event_key=event_key,
        execution_contract=contract,
        completion=typed if completion else None,
        grounding_receipt=binding if receipt else None,
    )


def test_terminal_grounded_payload_verifies_all_original_effects_and_keeps_pools(effect_source):
    repo, _, original, _, _, _ = effect_source
    result = repo.route_visual_verification_if_current(request=effect_request(effect_source))
    assert result.record.route == "CONTINUE"
    verdicts = {v["condition_name"]: v["status"] for v in result.record.to_payload()["verdicts"]}
    assert verdicts == {
        "tcp_above_safe_height": "PASS",
        "gripper_released": "PASS",
        "tcp_at_resolved_target": "PASS",
        "object_inside_target_region": "PASS",
        "robot_in_safe_pose": "PASS",
    }
    current = repo.get_visual_owner_publication(original.identity.task_id)
    assert current.verification_budget.state.remaining_reobservations == 3
    assert current.retry_budget.remaining_retries == 2


@pytest.mark.parametrize("case", ["missing_effect", "no_completion", "same_frame", "wrong_target"])
def test_one_missing_full_effect_or_invalid_completion_cannot_continue(effect_source, case):
    kwargs = {
        "missing_effect": {"missing": "object_inside_target_region"},
        "no_completion": {"completion": False},
        "same_frame": {"same_frame": True},
        "wrong_target": {"wrong_target": True},
    }[case]
    result = effect_source[0].route_visual_verification_if_current(
        request=effect_request(effect_source, **kwargs)
    )
    assert result is None or result.record.route in {"REOBSERVE", "STOP"}
    if case == "missing_effect":
        verdicts = {
            v["condition_name"]: v["status"] for v in result.record.to_payload()["verdicts"]
        }
        assert verdicts["object_inside_target_region"] == "UNKNOWN"


def test_historical_binding_survives_route_clearing_grounding_without_refund(effect_source):
    repo, data, original, _, binding, contract = effect_source
    first = repo.route_visual_verification_if_current(
        request=effect_request(effect_source, missing="object_inside_target_region")
    )
    assert first.record.route == "REOBSERVE"
    publication = repo.get_visual_owner_publication(original.identity.task_id)
    assert publication.to_payload()["grounding"] is None
    resumed = (repo, data, original, publication, binding, contract)
    denied = repo.route_visual_verification_if_current(
        request=effect_request(resumed, receipt=False, event_key="no-receipt")
    )
    assert denied is None
    fresh_action = repo.route_visual_verification_if_current(
        request=effect_request(resumed, phase="NATIVE_PRE_SKILL", event_key="historical-action")
    )
    assert fresh_action is None
    second = repo.route_visual_verification_if_current(
        request=effect_request(resumed, event_key="after-reobserve")
    )
    assert second.record.route == "CONTINUE"
    current = repo.get_visual_owner_publication(original.identity.task_id)
    assert current.verification_budget.state.remaining_reobservations == 2
    assert current.retry_budget.remaining_retries == 2
    assert current.verification_budget.state.deadline_at == original.verification_deadline_at
    assert (
        repo.get_visual_verification_route(original.identity.task_id, "after-reobserve").digest()
        == second.record.digest()
    )


@pytest.mark.parametrize("effect_skill", [SkillName.LIFT], indirect=True)
@pytest.mark.parametrize("missing", [None, "object_held", "object_lifted", "object_stable"])
def test_post_hold_joins_all_current_full_effects_and_cannot_skip_one(effect_source, missing):
    result = effect_source[0].route_visual_verification_if_current(
        request=effect_request(effect_source, phase="POST_HOLD", missing=missing)
    )
    assert result.record.route == ("CONTINUE" if missing is None else "REOBSERVE")
    verdicts = {v["condition_name"]: v["status"] for v in result.record.to_payload()["verdicts"]}
    for name in ("object_held", "object_lifted", "object_stable"):
        assert verdicts[name] == ("UNKNOWN" if name == missing else "PASS")


@pytest.mark.parametrize("effect_ttl", [0.25], indirect=True)
def test_completed_effect_started_valid_can_be_checked_after_grounding_ttl(effect_source):
    sleep(0.3)
    request = effect_request(effect_source)
    binding = effect_source[4]
    assert datetime.now(UTC) >= binding.valid_until
    result = effect_source[0].route_visual_verification_if_current(request=request)
    assert result is not None and result.record.route == "CONTINUE"


@pytest.mark.parametrize("effect_ttl", [0.25], indirect=True)
@pytest.mark.parametrize("invalid", ["native_phase", "expired_start", "wrong_result"])
def test_elapsed_ttl_does_not_admit_fresh_action_or_unbound_completion(effect_source, invalid):
    sleep(0.3)
    request = effect_request(effect_source)
    payload = request.to_payload()
    if invalid == "native_phase":
        payload["phase"] = "NATIVE_PRE_SKILL"
    elif invalid == "expired_start":
        payload["completion"]["started_at"] = effect_source[4].valid_until.isoformat()
    else:
        payload["completion"]["result"]["skill"] = "LIFT"
    changed = VisualVerificationRouteInput.from_payload(payload)
    result = effect_source[0].route_visual_verification_if_current(request=changed)
    assert result is None or result.record.route == "STOP"
