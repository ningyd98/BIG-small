"""Planning-only future conditions never grant action or admission."""

import json
from dataclasses import replace
from datetime import timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.contracts import LocalReplanningResponse, SkillName
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec, evaluate_conditions
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from tests.test_visual_owner_registration import values


def api():
    return import_module("cloud_edge_robot_arm.cloud.replanning.conditional_intent")


def inputs():
    data = values()
    owner = import_module("cloud_edge_robot_arm.vision.owner_registration")
    original = data["original"]
    contract = original.contract
    grasp = contract.steps[1].model_copy(update={"step_id": "grasp"}, deep=True)
    lift = contract.steps[1].model_copy(
        update={
            "step_id": "lift",
            "skill": SkillName.LIFT,
            "parameters": {"object_id": contract.task_target.object_id},
            "preconditions": ["gripper_holding"],
            "success_conditions": ["object_lifted"],
        },
        deep=True,
    )
    contract = contract.model_copy(update={"steps": [grasp, lift]}, deep=True)
    requirements = {}
    for step in contract.steps:
        requirements[step.step_id] = owner.OriginalActionRequirements(
            step,
            (ConditionSpec(step.preconditions[0], contract.task_target.object_id),),
            (ConditionSpec(step.success_conditions[0], contract.task_target.object_id),),
            0.01,
            ("rgbd",),
            5.0,
            max(step.timeout_ms, step.expected_duration_ms) / 1000,
            original.source_hashes,
        )
    original = owner.freeze_original_visual_plan(
        **{
            **original.freeze_inputs(),
            "contract": contract,
            "requirements": requirements,
            "dependencies": (
                StepDependency("grasp", (), ("frame",), "grasp-effect", False),
                StepDependency("lift", ("grasp",), ("holding",), "lift-effect", False),
            ),
        }
    )
    checkpoint = data["source_checkpoint"].model_copy(
        update={"current_step_id": "grasp", "pending_step_ids": ["grasp", "lift"]},
        deep=True,
    )
    checkpoint = checkpoint.model_copy(update={"checkpoint_hash": checkpoint_digest(checkpoint)})
    online = replace(data["online"], context_hash=checkpoint.checkpoint_hash)
    return dict(
        original=original,
        current_identity=data["current_identity"],
        source_checkpoint=checkpoint,
        online=online,
        owner_revision=1,
        state_generation=2,
        invalid_evidence_ids={"frame"},
        now=data["now"],
    )


def payload(data=None):
    data = inputs() if data is None else data
    return {
        "schema_version": "conditional.visual-repair-planning-intent.v1",
        "binding_hash": api().conditional_planning_binding(**data),
        "replacements": [
            {
                "step_id": "grasp",
                "skill": "GRASP",
                "target_pixel": [1, 1],
                "destination_pixel": None,
            },
            {"step_id": "lift", "skill": "LIFT", "target_pixel": None, "destination_pixel": None},
        ],
    }


def build(data=None, wire=None):
    data = inputs() if data is None else data
    wire = payload(data) if wire is None else wire
    return api().build_conditional_repair_intent(**data, intent_json=json.dumps(wire))


def test_future_holding_fail_is_preserved_as_requirement_without_action_authority():
    data = inputs()
    assert (
        evaluate_conditions(
            data["original"].requirements["lift"].preconditions, data["online"], now=data["now"]
        )[0].status
        == "FAIL"
    )
    result = build(data)
    assert result.scope == "PLANNING_ONLY"
    assert result.execution_admitted is False and result.method_admitted is False
    assert result.replacements[1].current_preconditions[0][1] == "FAIL"
    assert (
        result.replacements[1].original_requirements.digest()
        == data["original"].requirements["lift"].digest()
    )
    assert result.original_plan_hash == data["original"].digest()
    assert not hasattr(result, "steps") and not hasattr(result, "activation_token")
    with pytest.raises(ValueError):
        LocalReplanningResponse.model_validate(result.to_payload())


@pytest.mark.parametrize(
    "field,value",
    [("binding_hash", "0" * 64), ("schema_version", "executable.v1"), ("execution_admitted", True)],
)
def test_unbound_or_executable_response_fields_reject(field, value):
    data = inputs()
    wire = payload(data)
    wire[field] = value
    with pytest.raises(ValueError):
        build(data, wire)


@pytest.mark.parametrize(
    "change", ["unauthorized", "duplicate", "reordered", "missing", "skill", "command", "pixel"]
)
def test_replacement_window_skills_and_pixel_only_payload_are_exact(change):
    data = inputs()
    wire = payload(data)
    if change == "unauthorized":
        wire["replacements"][0]["step_id"] = "new-effect"
    elif change == "duplicate":
        wire["replacements"][1] = dict(wire["replacements"][0])
    elif change == "reordered":
        wire["replacements"].reverse()
    elif change == "missing":
        wire["replacements"].pop()
    elif change == "skill":
        wire["replacements"][1]["skill"] = "RELEASE"
    elif change == "command":
        wire["replacements"][0]["joint_positions"] = [0] * 7
    else:
        wire["replacements"][0]["target_pixel"] = [True, -1]
    with pytest.raises(ValueError):
        build(data, wire)


@pytest.mark.parametrize(
    "kind",
    ["version", "foreign", "stale", "future", "deadline", "checkpoint_hash", "bool_generation"],
)
def test_current_source_bindings_and_absolute_deadline_cannot_be_relaxed(kind):
    data = inputs()
    if kind == "version":
        data["online"] = replace(data["online"], command_seq=data["online"].command_seq + 1)
    elif kind == "foreign":
        data["current_identity"] = replace(data["current_identity"], owner_epoch="new-epoch")
    elif kind in {"stale", "future"}:
        delta = 6 if kind == "stale" else -1
        data["now"] = data["online"].observation.captured_at + timedelta(seconds=delta)
    elif kind == "deadline":
        data["now"] = data["original"].effective_deadline_at
    elif kind == "checkpoint_hash":
        data["source_checkpoint"] = data["source_checkpoint"].model_copy(
            update={"checkpoint_hash": "0" * 64}
        )
    else:
        data["state_generation"] = True
    with pytest.raises(ValueError):
        api().conditional_planning_binding(**data)


def test_completed_effect_is_preserved_and_cannot_enter_replacement_window():
    data = inputs()
    cp = data["source_checkpoint"].model_copy(
        update={
            "completed_step_ids": ["grasp"],
            "pending_step_ids": ["lift"],
            "current_step_index": 1,
            "current_step_id": "lift",
        },
        deep=True,
    )
    cp = cp.model_copy(update={"checkpoint_hash": checkpoint_digest(cp)})
    data["source_checkpoint"] = cp
    data["online"] = replace(data["online"], context_hash=cp.checkpoint_hash)
    wire = payload(data)
    with pytest.raises(ValueError):
        build(data, wire)
    wire["replacements"] = wire["replacements"][1:]
    result = build(data, wire)
    assert result.preserved_original_steps["grasp"] == data["original"].contract.steps[
        0
    ].model_dump(mode="json")


def test_planning_result_is_detached_and_cannot_request_admitted_scope():
    data = inputs()
    result = build(data)
    digest = result.digest()
    data["original"].contract.steps[0].parameters["object_id"] = "changed"
    view = result.to_payload()
    view["replacements"][0]["original_requirements"]["allowed_error_m"] = 1
    assert result.digest() == digest
    for field, value in [
        ("scope", "EXECUTABLE"),
        ("execution_admitted", True),
        ("method_admitted", True),
    ]:
        with pytest.raises(ValueError):
            replace(result, **{field: value})


def test_duplicate_wire_keys_do_not_override_original_binding():
    data = inputs()
    wire = json.dumps(payload(data))
    wire = wire.replace(
        '{"schema_version"', '{"binding_hash":"' + "0" * 64 + '","schema_version"', 1
    )
    with pytest.raises(ValueError):
        api().build_conditional_repair_intent(**data, intent_json=wire)
