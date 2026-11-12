"""Registered model candidates preserve original constraints without execution authority."""

from dataclasses import replace
from datetime import timedelta

import pytest

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.research import native_collection_grounding as collection
from cloud_edge_robot_arm.vision import owner_registration as owner
from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation
from tests.test_registered_object_tracking import STAMP, environment, later
from tests.test_visual_owner_registration import values


def binding_data(tmp_path, monkeypatch, skill=SkillName.MOVE_ABOVE):
    _, ref, reg, root, hashes, clock = environment(tmp_path, monkeypatch)
    tracker = collection.bootstrap_registered_collection_tracker_v1(
        ref, reg, source_root=root, source_hashes=hashes
    )
    current = later(ref, fragment=True)
    clock[0] = current.captured_at
    data = values()
    state = data["online"].robot_state.model_copy(
        update={
            "tcp_pose": data["online"].robot_state.tcp_pose.model_copy(
                update={"x": 0.25, "y": 0.15, "z": 0.2}
            )
        },
        deep=True,
    )
    state = type(state).model_validate(state.model_dump())
    preview = collection.registered_collection_grounding_preview_v1(tracker, current, state)
    assert preview.status == "DERIVED"
    inputs = owner.RegisteredGroundingFrameInputs.from_preview(preview, current, reg)
    before = data["original"]
    aliases = {
        before.contract.task_target.object_id: "object",
        before.contract.task_target.target_region_id: "target_region",
    }
    step = before.contract.steps[0].model_copy(
        update={
            "skill": skill,
            "parameters": {
                k: aliases.get(v, v) if k in {"object_id", "region_id"} else v
                for k, v in before.contract.steps[0].parameters.items()
            },
        },
        deep=True,
    )
    target = before.contract.task_target.model_copy(
        update={"object_id": "object", "target_region_id": "target_region"}
    )
    contract = before.contract.model_copy(
        update={
            "steps": [step],
            "task_target": target,
            "timestamp": STAMP,
            "issued_at": STAMP,
            "valid_until": STAMP + timedelta(seconds=60),
        },
        deep=True,
    )
    lease = WorkerLeaseObservation(
        "job-1",
        "run-1",
        "worker-1",
        "lease-1",
        1,
        STAMP - timedelta(seconds=1),
        current.captured_at,
        STAMP + timedelta(seconds=60),
        "a" * 64,
        "b" * 64,
        "c" * 64,
    )
    identity = lease.identity(
        episode_id=current.episode_id,
        task_id=contract.task_id,
        plan_id=before.identity.plan_id,
        robot_id=before.identity.robot_id,
    )
    requirement = replace(
        before.requirements["move"],
        original_step=step,
        policy_source_hashes=hashes,
        preconditions=tuple(
            replace(
                c,
                target_id=aliases.get(c.target_id, c.target_id)
                if c.target_id is not None
                else None,
            )
            for c in before.requirements["move"].preconditions
        ),
        postconditions=tuple(
            replace(
                c,
                target_id=aliases.get(c.target_id, c.target_id)
                if c.target_id is not None
                else None,
            )
            for c in before.requirements["move"].postconditions
        ),
    )
    original = owner.freeze_original_visual_plan(
        **{
            **before.freeze_inputs(),
            "identity": identity,
            "contract": contract,
            "requirements": {"move": requirement},
            "source_hashes": hashes,
            "compiler_source_hashes": hashes,
            "dependencies": (
                StepDependency("move", (), (current.observation_id,), "move-effect", False),
            ),
            "registered_at": STAMP,
            "task_deadline_at": STAMP + timedelta(seconds=60),
            "verification_deadline_at": STAMP + timedelta(seconds=40),
        }
    )
    cp = data["source_checkpoint"].model_copy(
        update={
            "pending_step_ids": ["move"],
            "created_at": STAMP,
            "updated_at": STAMP,
            "checkpoint_hash": "",
            "robot_state": state.model_dump(mode="json"),
        },
        deep=True,
    )
    cp = cp.model_copy(update={"checkpoint_hash": checkpoint_digest(cp)})
    online = OnlineEvidenceSnapshot(current, state, {}, 1, 1, cp.checkpoint_hash)
    policy = owner.RegisteredGroundingPolicy.for_original(original, hashes)
    return dict(
        original=original,
        original_step_id="move",
        online=online,
        source_checkpoint=cp,
        current_identity=identity,
        owner_revision=1,
        state_generation=2,
        lease_source=lease,
        grounding_inputs=inputs,
        grounding_policy=policy,
        now=current.captured_at,
    )


def binding_data_v2(tmp_path, monkeypatch, skill=SkillName.MOVE_ABOVE):
    from cloud_edge_robot_arm.research import native_collection_application as application
    from cloud_edge_robot_arm.research.native_calibration_collection import read_protocol
    from cloud_edge_robot_arm.vision import worker_owner
    from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
    from tests.test_registered_grounding_preparation import ROOT, context, v2_region_observation

    protocol_path, args, clock = context(tmp_path, monkeypatch, skill)
    monkeypatch.setattr(collection, "datetime", application.datetime)
    prior = args["original"]
    clock[0] = prior.registered_at
    lease = application._registered_lease(args["repository"], prior.identity)
    original = worker_owner.compile_worker_original_plan_v2(
        lease_source=lease,
        identity=prior.identity,
        contract=prior.contract,
        observation=args["reference_observation"],
        proposal_hash=prior.proposal_hash,
        role_bundle_hash=prior.role_bundle_hash,
        source_hashes=prior.source_hashes,
        registered_at=prior.registered_at,
        task_deadline_at=prior.task_deadline_at,
        verification_deadline_at=prior.verification_deadline_at,
    )
    reg = NativeGeometryRegistration(read_protocol(protocol_path)["geometry"])
    tracker = collection.bootstrap_registered_collection_tracker_v2(
        args["reference_observation"], reg, source_root=ROOT, source_hashes=original.source_hashes
    )
    current = v2_region_observation(args["reference_observation"])
    clock[0] = current.captured_at
    preview = collection.registered_collection_grounding_preview_v2(
        tracker, current, args["robot_state"]
    )
    assert preview.status == "DERIVED"
    input_type = getattr(owner, "RegisteredGroundingFrameInputsV2", None)
    assert input_type is not None, "independent v2 frame inputs missing"
    inputs = input_type.from_preview(preview, current, reg)
    policy = owner.RegisteredGroundingPolicyV2.for_original(original, original.source_hashes)
    online = OnlineEvidenceSnapshot(
        current,
        args["robot_state"],
        {},
        original.contract.plan_version,
        original.contract.command_seq,
        args["source_checkpoint"].checkpoint_hash,
    )
    return dict(
        original=original,
        original_step_id="move",
        online=online,
        source_checkpoint=args["source_checkpoint"],
        current_identity=original.identity,
        owner_revision=1,
        state_generation=2,
        lease_source=lease,
        grounding_inputs=inputs,
        grounding_policy=policy,
        now=current.captured_at,
    )


@pytest.mark.parametrize(
    "skill",
    [
        SkillName.MOVE_ABOVE,
        SkillName.APPROACH,
        SkillName.GRASP,
        SkillName.LIFT,
        SkillName.MOVE_TO_REGION,
        SkillName.PLACE,
        SkillName.RELEASE,
        SkillName.RETREAT,
    ],
)
def test_v2_binding_keeps_model_basis_and_original_effects(tmp_path, monkeypatch, skill):
    from cloud_edge_robot_arm.edge.evidence.conditions import (
        ConditionSpec,
        evaluate_conditions,
        evaluate_registered_conditions_v2,
    )
    from cloud_edge_robot_arm.vision import worker_owner

    data = binding_data_v2(tmp_path, monkeypatch, skill)
    prepared = owner.prepare_registered_step_binding_v2(**data)
    binding = owner.RegisteredCollectionStepBindingV2.from_prepared(
        prepared, collection_policy_id="registered-model-collection-v2"
    )
    assert not isinstance(prepared, owner.RegisteredPreparedStepBinding)
    assert not isinstance(binding, owner.RegisteredCollectionStepBinding)
    assert binding.to_payload()["execution_authority"] is False
    assert (
        prepared.to_payload()["original_requirements"]
        == data["original"].requirements["move"].to_payload()
    )
    assert binding.grounded_step.preconditions == []
    assert binding.grounded_step.timeout_ms == data["original"].contract.steps[0].timeout_ms
    result = worker_owner.registered_collection_effect_conditions_v2(data["original"], binding)
    assert [c.name for c in result] == [
        c.name for c in data["original"].requirements["move"].postconditions
    ]
    for condition in result:
        if condition.name == "tcp_at_resolved_target":
            assert [condition.tolerances["target_" + a] for a in "xyz"] == [
                binding.grounded_step.parameters["target_pose"][a] for a in "xyz"
            ]
    with pytest.raises(TypeError):
        owner.RegisteredCollectionStepBinding.from_prepared(
            prepared, collection_policy_id="registered-model-collection-v1"
        )
    with pytest.raises(ValueError):
        owner.RegisteredGroundingFrameInputs.from_payload(data["grounding_inputs"].to_payload())
    specs = [
        ConditionSpec(
            name,
            target,
            {
                "condition_registry_version": "registered-model-condition-v2",
                "requirement_origin": "DEFAULT_PRECONDITION",
            },
        )
        for name, target in [
            ("registered_object_pose_available", "object"),
            ("registered_region_model_available", "target_region"),
        ]
    ]
    verdicts = evaluate_registered_conditions_v2(
        specs, data["online"], grounding_inputs=data["grounding_inputs"], now=data["now"]
    )
    assert [v.status.value for v in verdicts] == ["PASS", "PASS"]
    assert all(v.measured_values["placement_clearance"] == "UNKNOWN" for v in verdicts)
    assert (
        evaluate_conditions(
            [ConditionSpec("target_visible", "object")], data["online"], now=data["now"]
        )[0].status.value
        == "UNKNOWN"
    )


@pytest.mark.parametrize("problem", ["frame", "source", "camera", "basis", "schema", "status"])
def test_v2_binding_rejects_resealed_provenance(tmp_path, monkeypatch, problem):
    from cloud_edge_robot_arm.research.native_calibration_collection import digest

    data = binding_data_v2(tmp_path, monkeypatch)
    payload = data["grounding_inputs"].to_payload()
    if problem == "frame":
        payload["observation_id"] = "foreign-current"
    elif problem == "source":
        key = "src/cloud_edge_robot_arm/edge/evidence/conditions.py"
        payload["source_hashes"][key] = "a" * 64
        payload["source_generation"] = digest(payload["source_hashes"])
    elif problem == "camera":
        payload["camera"]["width"] += 1
    elif problem == "basis":
        payload["region_basis"] = "RGBD_COLOR_REGION_UNCALIBRATED"
    elif problem == "schema":
        payload["schema_version"] = "registered.grounding.inputs.v1"
    elif problem == "status":
        payload["region_evidence"]["status"] = "FULL"
    with pytest.raises((ValueError, TypeError)):
        inputs = owner.RegisteredGroundingFrameInputsV2.from_payload(payload)
        owner.prepare_registered_step_binding_v2(**{**data, "grounding_inputs": inputs})


def test_binding_api_has_distinct_types():
    assert hasattr(owner, "RegisteredGroundingFrameInputs"), "registered typed inputs missing"
    assert hasattr(owner, "prepare_registered_step_binding"), "preparation binder missing"


def test_binding_preserves_original_horizon_and_detached_source_values(tmp_path, monkeypatch):
    data = binding_data(tmp_path, monkeypatch)
    result = owner.prepare_registered_step_binding(**data)
    payload = result.to_payload()
    assert payload["binding_scope"] == "REGISTERED_MODEL_PREPARATION_ONLY"
    assert payload["execution_allowed"] is False and payload["prepare_only"] is True
    assert payload["geometric_error_bound_m"] is None
    assert payload["object_surface_visibility"] == "UNKNOWN"
    assert payload["expected_duration_s"] == 10
    assert result.valid_until == STAMP + timedelta(seconds=5.1)
    assert result.grounded_step.timeout_ms == 10000
    assert result.grounded_step.retry_limit == 0
    original_hash = result.digest()
    payload["grounded_step"]["parameters"]["target_pose"]["z"] = 99
    assert result.digest() == original_hash
    assert type(result).from_payload(result.to_payload()).digest() == original_hash
    assert not isinstance(result, owner.StepGroundingBinding)
    assert data["grounding_inputs"].to_payload()["support_basis"] == "REGISTERED_NOMINAL"
    assert data["grounding_inputs"].digest() != data["grounding_policy"].digest()


@pytest.mark.parametrize(
    "skill",
    [
        SkillName.MOVE_ABOVE,
        SkillName.APPROACH,
        SkillName.GRASP,
        SkillName.LIFT,
        SkillName.MOVE_TO_REGION,
        SkillName.PLACE,
        SkillName.RELEASE,
        SkillName.RETREAT,
    ],
)
def test_binding_all_eight_candidates_use_current_model_and_nominal_support(
    tmp_path, monkeypatch, skill
):
    data = binding_data(tmp_path, monkeypatch, skill)
    result = owner.prepare_registered_step_binding(**data)
    inputs = data["grounding_inputs"].to_payload()
    gx, gy, gz = inputs["grasp_tcp_world_m"]
    dx, dy, dz = inputs["destination_world_m"]
    targets = {
        SkillName.MOVE_ABOVE: {"x": gx, "y": gy, "z": max(0.16, gz + 0.10)},
        SkillName.APPROACH: {"x": gx, "y": gy, "z": gz},
        SkillName.LIFT: {"x": 0.25, "y": 0.15, "z": 0.30},
        SkillName.MOVE_TO_REGION: {"x": dx, "y": dy, "z": max(0.16, gz + 0.10)},
        SkillName.PLACE: {"x": dx, "y": dy, "z": dz + gz - inputs["nominal_support_height_m"]},
        SkillName.RETREAT: {"x": 0.25, "y": 0.15, "z": 0.30},
    }
    params = result.grounded_step.parameters
    if skill in targets:
        assert params["target_pose"] == pytest.approx(targets[skill])
        assert params["tcp_velocity"] == 0.15 and params["acceleration"] == 0.5
    else:
        assert "target_pose" not in params
    assert result.grounded_step.skill == skill
    assert result.to_payload()["original_requirements"] == (
        data["original"].requirements["move"].to_payload()
    )


@pytest.mark.parametrize(
    "kind",
    [
        "identity",
        "episode",
        "checksum",
        "context",
        "checkpoint",
        "cursor",
        "source",
        "future",
        "stale",
        "lease",
        "lease_epoch",
        "revision",
        "local_original",
    ],
)
def test_binding_rejects_foreign_stale_or_unsupported_context(tmp_path, monkeypatch, kind):
    data = binding_data(tmp_path, monkeypatch)
    if kind == "identity":
        data["current_identity"] = replace(data["current_identity"], robot_id="another-robot")
    elif kind in {"episode", "checksum", "source"}:
        payload = data["grounding_inputs"].to_payload()
        if kind == "episode":
            payload["episode_id"] = "other-episode"
        elif kind == "checksum":
            payload["observation_checksum_sha256"] = "e" * 64
        else:
            payload["source_hashes"]["src/cloud_edge_robot_arm/vision/owner_registration.py"] = (
                "e" * 64
            )
            payload["source_generation"] = owner._digest(payload["source_hashes"])
        data["grounding_inputs"] = owner.RegisteredGroundingFrameInputs.from_payload(payload)
    elif kind == "context":
        data["online"] = replace(data["online"], context_hash="e" * 64)
    elif kind in {"checkpoint", "cursor"}:
        cp = data["source_checkpoint"].model_copy(
            update={"checkpoint_hash": "e" * 64}
            if kind == "checkpoint"
            else {"completed_step_ids": ["move"]}
        )
        data["source_checkpoint"] = cp
    elif kind in {"future", "stale"}:
        data["now"] += timedelta(seconds=-0.01 if kind == "future" else 5.01)
    elif kind == "lease":
        data["lease_source"] = replace(
            data["lease_source"], observed_at=STAMP, expires_at=data["now"]
        )
    elif kind == "lease_epoch":
        data["lease_source"] = replace(data["lease_source"], lease_id="another-lease")
    elif kind == "revision":
        data["owner_revision"] = True
    else:
        data["original"] = object()
    with pytest.raises((ValueError, TypeError)):
        owner.prepare_registered_step_binding(**data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("geometry_basis", "MEASURED"),
        ("geometric_error_bound_m", 0.001),
        ("region_geometric_error_bound_m", 0.001),
        ("object_surface_visibility", "PASS"),
        ("execution_allowed", True),
        ("prepare_only", 1),
        ("nominal_support_height_m", True),
        ("rotation_object_to_world", [1] * 9),
        ("extra", "undeclared"),
    ],
)
def test_binding_input_schema_rejects_authority_and_numeric_coercion(
    tmp_path, monkeypatch, field, value
):
    payload = binding_data(tmp_path, monkeypatch)["grounding_inputs"].to_payload()
    payload[field] = value
    with pytest.raises((ValueError, TypeError)):
        owner.RegisteredGroundingFrameInputs.from_payload(payload)


def test_binding_families_policy_and_duration_cannot_be_relabelled(tmp_path, monkeypatch):
    data = binding_data(tmp_path, monkeypatch)
    with pytest.raises((ValueError, TypeError)):
        owner.prepare_registered_step_binding(
            **{**data, "grounding_inputs": values()["grounding_inputs"]}
        )
    with pytest.raises((ValueError, TypeError)):
        owner.bind_step_grounding(
            **{
                **values(),
                "grounding_inputs": data["grounding_inputs"],
                "grounding_policy": data["grounding_policy"],
            }
        )
    policy = data["grounding_policy"].to_payload()
    policy["tcp_velocity"] = 0.2
    with pytest.raises((ValueError, TypeError)):
        owner.prepare_registered_step_binding(
            **{**data, "grounding_policy": owner.RegisteredGroundingPolicy.from_payload(policy)}
        )
    with pytest.raises((ValueError, TypeError)):
        owner.prepare_registered_step_binding(**{**data, "required_duration_s": 20})


@pytest.mark.parametrize("field", ["object_id", "target_region_id"])
def test_binding_rejects_foreign_registered_target(tmp_path, monkeypatch, field):
    data = binding_data(tmp_path, monkeypatch)
    original = data["original"]
    contract = original.contract
    target = contract.task_target.model_copy(update={field: "other-target"})
    previous = getattr(contract.task_target, field)
    source_step = contract.steps[0]
    step = source_step.model_copy(
        update={
            "parameters": {
                k: ("other-target" if v == previous else v)
                if k in {"object_id", "region_id"}
                else v
                for k, v in source_step.parameters.items()
            }
        },
        deep=True,
    )
    r = original.requirements["move"]
    requirement = replace(
        r,
        original_step=step,
        preconditions=tuple(
            replace(c, target_id="other-target") if c.target_id == previous else c
            for c in r.preconditions
        ),
        postconditions=tuple(
            replace(c, target_id="other-target") if c.target_id == previous else c
            for c in r.postconditions
        ),
    )
    data["original"] = owner.freeze_original_visual_plan(
        **{
            **original.freeze_inputs(),
            "contract": contract.model_copy(update={"task_target": target, "steps": [step]}),
            "requirements": {"move": requirement},
        }
    )
    with pytest.raises(ValueError):
        owner.prepare_registered_step_binding(**data)


def test_binding_pose_wrong_target_remains_unknown(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.edge.evidence.conditions import evaluate_registered_pose_available

    data = binding_data(tmp_path, monkeypatch)
    result = evaluate_registered_pose_available(
        data["grounding_inputs"],
        data["online"].observation,
        target_id="other-target",
        now=data["now"],
    )
    assert result.status == "UNKNOWN"


@pytest.mark.parametrize("source_v2", [False, True])
def test_r668_relabelled_prepared_and_collection_families_rejected(
    tmp_path, monkeypatch, source_v2
):
    data = (binding_data_v2 if source_v2 else binding_data)(tmp_path, monkeypatch)
    prepare = (
        owner.prepare_registered_step_binding_v2
        if source_v2
        else owner.prepare_registered_step_binding
    )
    prepared = prepare(**data)
    source_collection = (
        owner.RegisteredCollectionStepBindingV2
        if source_v2
        else owner.RegisteredCollectionStepBinding
    )
    target_prepared = (
        owner.RegisteredPreparedStepBinding if source_v2 else owner.RegisteredPreparedStepBindingV2
    )
    target_collection = (
        owner.RegisteredCollectionStepBinding
        if source_v2
        else owner.RegisteredCollectionStepBindingV2
    )
    policy = "registered-model-collection-v2" if source_v2 else "registered-model-collection-v1"
    collection = source_collection.from_prepared(prepared, collection_policy_id=policy)
    assert (
        source_collection.from_payload(collection.to_payload()).to_payload()
        == collection.to_payload()
    )
    renamed = prepared.to_payload()
    renamed["schema_version"] = (
        "registered.grounding.prepared-step.v1"
        if source_v2
        else "registered.grounding.prepared-step.v2"
    )
    with pytest.raises((ValueError, TypeError)):
        target_prepared.from_payload(renamed)
    renamed = collection.to_payload()
    renamed.update(
        schema_version="registered.collection.binding.v1"
        if source_v2
        else "registered.collection.binding.v2",
        collection_policy_id="registered-model-collection-v1"
        if source_v2
        else "registered-model-collection-v2",
    )
    renamed["prepared"]["schema_version"] = (
        "registered.grounding.prepared-step.v1"
        if source_v2
        else "registered.grounding.prepared-step.v2"
    )
    with pytest.raises((ValueError, TypeError)):
        target_collection.from_payload(renamed)


@pytest.mark.parametrize("mutation", ["post_origin", "post_registry", "mandatory_model"])
def test_r668_v2_requirement_provenance_is_structural(tmp_path, monkeypatch, mutation):
    data = binding_data_v2(tmp_path, monkeypatch)
    payload = owner.prepare_registered_step_binding_v2(**data).to_payload()
    requirement = payload["original_requirements"]
    if mutation == "post_origin":
        requirement["postconditions"][0]["tolerances"]["requirement_origin"] = (
            "DEFAULT_PRECONDITION"
        )
    elif mutation == "post_registry":
        requirement["postconditions"][0]["tolerances"]["condition_registry_version"] = "foreign"
    else:
        requirement["preconditions"] = [
            c
            for c in requirement["preconditions"]
            if c["name"] != "registered_region_model_available"
        ]
    with pytest.raises((ValueError, TypeError)):
        owner.RegisteredPreparedStepBindingV2.from_payload(payload)
