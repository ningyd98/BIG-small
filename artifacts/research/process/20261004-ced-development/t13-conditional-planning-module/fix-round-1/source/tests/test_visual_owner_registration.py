"""SOFTWARE_ONLY pure source bindings; no real owner or physical authority."""

from dataclasses import replace
from datetime import timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from tests.test_visual_repair_builder import NOW, fixture

SHA = "a" * 64
SOURCES = {"src/software_grounding.py": SHA}


def api():
    return import_module("cloud_edge_robot_arm.vision.owner_registration")


def values():
    _, context, _, _ = fixture()
    module = api()
    contract = context.active_contract.model_copy(deep=True)
    move = contract.steps[0].model_copy(
        update={
            "step_id": "move",
            "skill": SkillName.MOVE_ABOVE,
            "parameters": {"object_id": contract.task_target.object_id},
            "preconditions": ["target_visible"],
            "success_conditions": ["tcp_above_target"],
            "retry_limit": 0,
            "timeout_ms": 10000,
        }
    )
    grasp = contract.steps[1].model_copy(
        update={
            "step_id": "grasp",
            "parameters": {"object_id": contract.task_target.object_id},
            "preconditions": ["gripper_open"],
            "success_conditions": ["gripper_holding"],
            "retry_limit": 0,
            "timeout_ms": 1000,
        }
    )
    contract = contract.model_copy(update={"steps": [move, grasp]})
    identity = module.VisualOwnerIdentity(
        "job-1",
        "run-1",
        1,
        "worker-1",
        "lease-1",
        "epoch-1",
        "episode",
        contract.task_id,
        context.checkpoint.plan_id,
        context.checkpoint.robot_id,
    )
    requirements = {}
    for step in contract.steps:
        requirements[step.step_id] = module.OriginalActionRequirements(
            step,
            (
                ConditionSpec(
                    step.preconditions[0],
                    contract.task_target.object_id,
                    {"max_age_s": 5.0, "minimum_safe_height": 0.08},
                ),
            ),
            (ConditionSpec(step.success_conditions[0], contract.task_target.object_id),),
            0.01,
            ("rgbd",),
            5.0,
            max(step.timeout_ms, step.expected_duration_ms) / 1000,
            SOURCES,
        )
    graph = (
        StepDependency("move", (), ("frame",), "move-effect", False),
        StepDependency("grasp", ("move",), ("frame",), "grasp-effect", False),
    )
    original = module.freeze_original_visual_plan(
        identity=identity,
        contract=contract,
        proposal_hash=SHA,
        role_bundle_hash=SHA,
        compiler_source_hashes=SOURCES,
        source_hashes=SOURCES,
        requirements=requirements,
        dependencies=graph,
        task_deadline_at=NOW + timedelta(seconds=60),
        verification_deadline_at=NOW + timedelta(seconds=40),
        registered_at=NOW,
    )
    checkpoint = context.checkpoint.model_copy(
        update={
            "completed_step_ids": [],
            "pending_step_ids": ["move", "grasp"],
            "current_step_id": "move",
            "current_step_index": 0,
            "checkpoint_hash": "",
        },
        deep=True,
    )
    checkpoint = checkpoint.model_copy(update={"checkpoint_hash": checkpoint_digest(checkpoint)})
    online = replace(context.online_evidence, context_hash=checkpoint.checkpoint_hash)
    policy = module.DeterministicGroundingPolicy(
        "rgbd-top-grasp-v1", "software-v1", SOURCES, 0.15, 0.5, 0.10, 0.16
    )
    inputs = module.GroundingFrameInputs(
        online.observation.observation_id,
        online.observation.checksum_sha256,
        online.observation.episode_id,
        online.observation.calibration_version,
        {"x": 0.2, "y": 0.1, "z": 0.06},
        {"x": 0.3, "y": 0.2, "z": 0.0},
        0.035,
        SOURCES,
    )
    grounded = move.model_copy(
        update={
            "parameters": {
                "object_id": contract.task_target.object_id,
                "target_pose": {"x": 0.2, "y": 0.1, "z": 0.16},
                "tcp_velocity": 0.15,
                "acceleration": 0.5,
            },
            "preconditions": [],
            "success_conditions": [],
        },
        deep=True,
    )
    return dict(
        original=original,
        original_step_id="move",
        grounded_step=grounded,
        online=online,
        source_checkpoint=checkpoint,
        current_identity=identity,
        owner_revision=1,
        state_generation=2,
        grounding_inputs=inputs,
        grounding_policy=policy,
        now=NOW + timedelta(seconds=0.2),
    )


def bind(**changes):
    return api().bind_step_grounding(**{**values(), **changes})


def test_missing_feature_then_pure_binding_has_no_owner_method_or_execution_authority():
    result = bind()
    assert result.binding_scope == "SOURCE_BINDING_ONLY"
    assert result.to_payload()["binding_scope"] == "SOURCE_BINDING_ONLY"
    assert result.digest() == result.binding_hash
    assert result.valid_until == NOW + timedelta(seconds=5.1)
    assert result.original_requirements.preconditions[0].name == "target_visible"
    assert result.grounded_step.preconditions == []
    with pytest.raises(TypeError):
        replace(result, method_admitted=True)


def test_original_requirements_payload_preserves_policy_for_planning_only_carrier():
    original = values()["original"]
    requirement = original.requirements["move"]
    payload = requirement.to_payload()
    assert payload["preconditions"][0] == {
        "name": "target_visible",
        "target_id": "obj-1",
        "tolerances": {"max_age_s": 5.0, "minimum_safe_height": 0.08},
        "sensor_requirements": ["rgbd"],
    }
    assert payload["timeout_ms"] == 10000 and payload["retry_limit"] == 0
    assert payload["allowed_error_m"] == 0.01 and payload["ordinary_ttl_s"] == 5
    assert "evidence" not in payload and "accepted" not in payload


def test_callers_cannot_mutate_original_steps_requirements_or_bound_step_aliases():
    data = values()
    original = data["original"]
    original.contract.steps[0].parameters["object_id"] = "decoy"
    result = api().bind_step_grounding(**data)
    returned = result.grounded_step
    returned.parameters["target_pose"]["z"] = 99
    assert result.grounded_step.parameters["target_pose"]["z"] == 0.16
    with pytest.raises(TypeError):
        original.requirements["move"].preconditions[0].tolerances["max_age_s"] = 600
    payload = original.to_payload()
    payload["contract"]["steps"][0]["parameters"]["object_id"] = "decoy"
    assert original.contract.steps[0].parameters["object_id"] == "obj-1"


@pytest.mark.parametrize(
    "field,value",
    [
        ("robot_id", "robot-unknown"),
        ("owner_epoch", ""),
        ("job_id", "../job"),
        ("attempt", True),
        ("lease_id", "unknown"),
    ],
)
def test_placeholder_invalid_owner_identity_rejects(field, value):
    with pytest.raises((ValueError, TypeError)):
        replace(values()["current_identity"], **{field: value})


@pytest.mark.parametrize(
    "change",
    [
        "job",
        "epoch",
        "robot",
        "plan",
        "seq",
        "frame",
        "checksum",
        "context",
        "checkpoint",
        "naive",
        "late",
    ],
)
def test_current_binding_rejects_foreign_stale_or_malformed_sources(change):
    data = values()
    if change in {"job", "epoch", "robot"}:
        field = {"job": "job_id", "epoch": "owner_epoch", "robot": "robot_id"}[change]
        data["current_identity"] = replace(data["current_identity"], **{field: "another"})
    elif change in {"plan", "seq", "context"}:
        field = {"plan": "plan_version", "seq": "command_seq", "context": "context_hash"}[change]
        data["online"] = replace(data["online"], **{field: "wrong" if change == "context" else 3})
    elif change in {"frame", "checksum"}:
        data["grounding_inputs"] = replace(
            data["grounding_inputs"],
            **{"observation_id" if change == "frame" else "observation_checksum_sha256": "b" * 64},
        )
    elif change == "checkpoint":
        data["source_checkpoint"] = data["source_checkpoint"].model_copy(
            update={"checkpoint_hash": "b" * 64}
        )
    else:
        data["now"] = NOW.replace(tzinfo=None) if change == "naive" else NOW + timedelta(seconds=41)
    with pytest.raises((ValueError, TypeError)):
        api().bind_step_grounding(**data)


@pytest.mark.parametrize("change", ["target", "timeout", "retry", "coordinates", "conditions"])
def test_grounding_cannot_change_original_policy_or_deterministic_recipe(change):
    data = values()
    step = data["grounded_step"]
    update = {
        "target": {"parameters": {**step.parameters, "object_id": "decoy"}},
        "timeout": {"timeout_ms": 12000},
        "retry": {"retry_limit": 1},
        "coordinates": {
            "parameters": {**step.parameters, "target_pose": {"x": 9, "y": 0.1, "z": 0.16}}
        },
        "conditions": {"preconditions": ["gripper_open"]},
    }[change]
    data["grounded_step"] = step.model_copy(update=update)
    with pytest.raises(ValueError):
        api().bind_step_grounding(**data)


def test_longer_horizon_requires_fresh_exact_duration_calculation_binding():
    data = values()
    data["required_duration_s"] = 12.0
    with pytest.raises(ValueError, match="duration"):
        api().bind_step_grounding(**data)
    check = api().GroundingDurationCheck(
        data["grounded_step"],
        data["online"].observation.observation_id,
        data["online"].observation.checksum_sha256,
        data["original"].digest(),
        data["grounding_policy"].digest(),
        12.0,
        data["now"],
        SOURCES,
    )
    result = api().bind_step_grounding(**data, duration_check=check)
    assert result.expected_duration_s == 12
    assert result.valid_until <= data["original"].effective_deadline_at
    with pytest.raises(ValueError):
        api().bind_step_grounding(
            **data, duration_check=replace(check, checked_at=NOW - timedelta(seconds=10))
        )


@pytest.mark.parametrize("kind", ["nonfinite", "empty", "missingname", "modelcopy", "effect"])
def test_original_source_freeze_rejects_malformed_policy_models_and_effect_graph(kind):
    data = values()
    original = data["original"]
    kwargs = original.freeze_inputs()
    if kind == "nonfinite":
        with pytest.raises(ValueError):
            replace(original.requirements["move"], allowed_error_m=float("nan"))
        return
    if kind == "empty":
        kwargs["requirements"] = {}
    elif kind == "missingname":
        with pytest.raises(ValueError):
            replace(original.requirements["move"], preconditions=(ConditionSpec("gripper_open"),))
        return
    elif kind == "modelcopy":
        kwargs["contract"] = original.contract.model_copy(update={"plan_version": True})
    else:
        kwargs["dependencies"] = (
            original.dependencies[0],
            replace(original.dependencies[1], physical_effect_id="move-effect"),
        )
    with pytest.raises((ValueError, TypeError)):
        api().freeze_original_visual_plan(**kwargs)


def test_same_version_original_replacement_rejects_and_deadlines_never_extend():
    original = values()["original"]
    kwargs = original.freeze_inputs()
    altered = original.contract
    altered.steps[0].parameters["different"] = True
    kwargs["contract"] = altered
    with pytest.raises(ValueError):
        api().freeze_original_visual_plan(**kwargs, previous=original)
    assert original.effective_deadline_at == NOW + timedelta(seconds=40)
    with pytest.raises(ValueError):
        api().freeze_original_visual_plan(
            **{**original.freeze_inputs(), "registered_at": NOW.replace(tzinfo=None)}
        )


def test_direct_original_and_binding_constructors_detach_source_maps():
    original = values()["original"]
    source_map = dict(SOURCES)
    rebuilt = replace(original, source_hashes=source_map)
    source_map["src/software_grounding.py"] = "b" * 64
    assert rebuilt.source_hashes == SOURCES
    result = bind()
    another_map = dict(SOURCES)
    rebuilt_result = replace(result, grounding_source_hashes=another_map)
    another_map["src/software_grounding.py"] = "b" * 64
    assert rebuilt_result.grounding_source_hashes == SOURCES


@pytest.mark.parametrize("change", ["plan", "binding", "nestedmodel", "posebool"])
def test_direct_invalid_or_mutated_nested_models_fail_before_binding(change):
    data = values()
    with pytest.raises((ValueError, TypeError)):
        if change == "plan":
            replace(data["original"], task_deadline_at=NOW.replace(tzinfo=None))
        elif change == "binding":
            replace(bind(), valid_until=NOW)
        elif change == "posebool":
            replace(data["grounding_inputs"], grasp_tcp={"x": True, "y": 0.1, "z": 0.06})
        else:
            contract = data["original"].contract
            contract.steps[0] = contract.steps[0].model_copy(update={"actual_owner_accepted": True})
            api().freeze_original_visual_plan(
                **{**data["original"].freeze_inputs(), "contract": contract}
            )


def test_requested_horizon_cannot_shorten_original_frozen_policy():
    data = values()
    original = data["original"]
    requirements = {
        **original.requirements,
        "move": replace(original.requirements["move"], expected_duration_s=12.0),
    }
    data["original"] = api().freeze_original_visual_plan(
        **{**original.freeze_inputs(), "requirements": requirements}
    )
    with pytest.raises(ValueError):
        api().bind_step_grounding(**data, required_duration_s=11.0)


def test_registered_calibration_requirement_must_match_current_frame():
    data = values()
    original = data["original"]
    requirement = original.requirements["move"]
    requirements = {
        **original.requirements,
        "move": replace(
            requirement,
            preconditions=(
                replace(
                    requirement.preconditions[0],
                    tolerances={
                        **requirement.preconditions[0].tolerances,
                        "calibration_version": "another",
                    },
                ),
            ),
        ),
    }
    data["original"] = api().freeze_original_visual_plan(
        **{**original.freeze_inputs(), "requirements": requirements}
    )
    with pytest.raises(ValueError):
        api().bind_step_grounding(**data)


@pytest.mark.parametrize(
    "change", ["onlinebool", "checkpointbool", "robotbool", "source", "authorityscope"]
)
def test_typed_source_bools_drift_or_scope_flags_cannot_be_coerced(change):
    data = values()
    with pytest.raises((TypeError, ValueError)):
        if change == "onlinebool":
            api().bind_step_grounding(
                **{**data, "online": replace(data["online"], plan_version=True)}
            )
        elif change == "checkpointbool":
            cp = data["source_checkpoint"].model_copy(update={"current_step_index": False})
            cp = cp.model_copy(update={"checkpoint_hash": checkpoint_digest(cp)})
            api().bind_step_grounding(
                **{
                    **data,
                    "source_checkpoint": cp,
                    "online": replace(data["online"], context_hash=cp.checkpoint_hash),
                }
            )
        elif change == "robotbool":
            robot = data["online"].robot_state.model_copy(update={"connected": 1})
            api().bind_step_grounding(
                **{**data, "online": replace(data["online"], robot_state=robot)}
            )
        elif change == "source":
            changed = replace(
                data["grounding_policy"], source_hashes={"src/software_grounding.py": "b" * 64}
            )
            api().bind_step_grounding(**{**data, "grounding_policy": changed})
        else:
            replace(bind(), binding_scope="ACTUAL_OWNER_ACCEPTED")


@pytest.mark.parametrize("change", ["futurecheckpoint", "conditionage", "stringsensors"])
def test_source_time_and_explicit_sensor_sequences_are_checked(change):
    data = values()
    with pytest.raises(ValueError):
        if change == "futurecheckpoint":
            cp = data["source_checkpoint"].model_copy(
                update={"updated_at": NOW + timedelta(seconds=1)}
            )
            cp = cp.model_copy(update={"checkpoint_hash": checkpoint_digest(cp)})
            api().bind_step_grounding(
                **{
                    **data,
                    "source_checkpoint": cp,
                    "online": replace(data["online"], context_hash=cp.checkpoint_hash),
                }
            )
        elif change == "conditionage":
            original = data["original"]
            r = original.requirements["move"]
            requirements = {
                **original.requirements,
                "move": replace(
                    r, preconditions=(replace(r.preconditions[0], tolerances={"max_age_s": 0.05}),)
                ),
            }
            rebuilt = api().freeze_original_visual_plan(
                **{**original.freeze_inputs(), "requirements": requirements}
            )
            api().bind_step_grounding(**{**data, "original": rebuilt})
        else:
            replace(data["original"].requirements["move"], sensor_requirements="rgbd")


def test_binding_retains_all_grounding_sources_and_complete_input_hash():
    data = values()
    more_sources = {**SOURCES, "src/software_measurement.py": "b" * 64}
    data["original"] = replace(data["original"], source_hashes=more_sources)
    data["grounding_inputs"] = replace(
        data["grounding_inputs"], source_hashes={"src/software_measurement.py": "b" * 64}
    )
    result = api().bind_step_grounding(**data)
    assert result.grounding_source_hashes == more_sources
    assert result.grounding_inputs_hash == data["grounding_inputs"].digest()
    changed = replace(data["grounding_inputs"], destination={"x": 0.31, "y": 0.2, "z": 0.0})
    other = api().bind_step_grounding(**{**data, "grounding_inputs": changed})
    assert other.grounded_step == result.grounded_step
    assert other.binding_hash != result.binding_hash


def test_binding_retains_exact_fresh_duration_check_provenance():
    data = values()
    data["required_duration_s"] = 12.0
    check = api().GroundingDurationCheck(
        data["grounded_step"],
        data["online"].observation.observation_id,
        data["online"].observation.checksum_sha256,
        data["original"].digest(),
        data["grounding_policy"].digest(),
        12.0,
        data["now"],
        SOURCES,
    )
    first = api().bind_step_grounding(**data, duration_check=check)
    earlier = replace(check, checked_at=data["now"] - timedelta(seconds=0.01))
    second = api().bind_step_grounding(**data, duration_check=earlier)
    assert first.binding_hash != second.binding_hash
    assert first.duration_check_hash == check.digest()
    assert second.duration_check_hash == earlier.digest()
    assert bind().duration_check_hash is None
