"""Source-bound action references; none of these software tests admit native motion."""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from importlib import import_module, util
from math import dist, sqrt
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.contracts import Pose, TaskTarget
from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.vision.execution import resolved_step
from cloud_edge_robot_arm.vision.role_models import configuration_hash
from tests.test_ced_runtime_binding import role_binding
from tests.test_phase6_2_replan_resume import _contract
from tests.test_visual_evidence_contract import NOW, online_evidence
from tests.test_visual_evidence_contract import contract as evidence_contract

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "src/cloud_edge_robot_arm/vision/native_references.py",
    "src/cloud_edge_robot_arm/vision/execution.py",
    "src/cloud_edge_robot_arm/vision/runtime_binding.py",
    "src/cloud_edge_robot_arm/vision/role_models.py",
    "src/cloud_edge_robot_arm/vision/observations.py",
    "src/cloud_edge_robot_arm/contracts/models.py",
    "src/cloud_edge_robot_arm/edge/runtime/skill_registry.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py",
)


def api():
    name = "cloud_edge_robot_arm.vision.native_references"
    assert util.find_spec(name) is not None, "missing production native reference resolver"
    return import_module(name)


def sample(tmp_path, skill="LIFT"):
    _, binding = role_binding(tmp_path)
    device = dict(binding.device_source_hashes)
    for name in SOURCES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        device[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    binding = replace(
        binding,
        edge_policy=binding.evidence()["edge_policy"],
        device_source_hashes=device,
        bundle=replace(binding.bundle, device_pipeline_hash=configuration_hash(device)),
    )
    contract = _contract().model_copy(
        update={
            "task_target": TaskTarget(
                object_id="object", object_class="cube", target_region_id="target_region"
            )
        }
    )
    step = next(s for s in contract.steps if s.skill.value == skill)
    online = online_evidence()
    state = online.robot_state.model_copy(
        update={"tcp_pose": Pose(x=0.45, y=0.0, z=0.04), "holding_object_id": "object"}
    )
    online = replace(online, robot_state=state, context_hash="owned-checkpoint-context")
    grounding = {
        "resolved_top_grasp_tcp": {"x": 0.45, "y": 0.0, "z": 0.04},
        "grounded_destination": {"x": 0.2, "y": 0.25, "z": 0.004},
        "top_grasp_support_height_m": 0.0,
    }
    resolved = resolved_step(step, SimpleNamespace(get_state=lambda: state), grounding)
    return dict(
        online=online,
        contract=contract,
        step=step,
        resolved=resolved,
        grounding=grounding,
        role_binding=binding,
        effective_duration_s=12.0,
    )


@pytest.mark.parametrize(
    "skill,endpoint",
    [
        ("LIFT", (0.45, 0.0, 0.16)),
        ("MOVE_TO_REGION", (0.2, 0.25, 0.16)),
        ("PLACE", (0.2, 0.25, 0.044)),
    ],
)
def test_original_resolver_and_registered_handler_forward_exact_fixed_endpoint(
    tmp_path,
    skill,
    endpoint,
):
    module = api()
    inputs = sample(tmp_path, skill)
    reference = module.resolve_native_reference(**inputs)
    assert reference.kind == "FIXED_WORLD_TCP_GOAL"
    assert reference.endpoint_xyz == endpoint
    assert reference.orientation_wxyz == (sqrt(0.5), 0.0, sqrt(0.5), 0.0)
    assert reference.full_horizon_s == 12.0
    # Exercise the real registry's endpoint forwarding, without any robot/controller run.
    captured = {}

    def record(*args, **kwargs):
        captured.update(kwargs)

    robot = SimpleNamespace(lift=record, move_to_region=record, place=record)
    definition = SkillRegistry.default().definition_for(inputs["step"].skill)
    definition.handler(
        robot, definition.validate(inputs["resolved"].parameters), inputs["resolved"].timeout_ms
    )
    assert tuple(captured["resolved_target"].model_dump().values()) == endpoint
    assert captured["timeout_ms"] == 10000
    assert captured["tcp_velocity"] == 0.15
    assert captured["acceleration"] == 0.5
    module.validate_native_reference(reference, **inputs)


@pytest.mark.parametrize(
    "change",
    [
        "tcp",
        "height",
        "region",
        "support",
        "target_pose",
        "contract",
        "step",
        "role",
        "context",
        "frame",
        "horizon",
        "compiled_velocity",
    ],
)
def test_recomputed_reference_rejects_changed_resolution_or_ownership(tmp_path, change):
    module = api()
    inputs = sample(tmp_path, "PLACE")
    reference = module.resolve_native_reference(**inputs)
    if change == "tcp":
        state = inputs["online"].robot_state.model_copy(
            update={"tcp_pose": Pose(x=0.46, y=0, z=0.04)}
        )
        inputs["online"] = replace(inputs["online"], robot_state=state)
    elif change in {"height", "region", "support"}:
        grounding = json.loads(json.dumps(inputs["grounding"]))
        if change == "height":
            grounding["resolved_top_grasp_tcp"]["z"] = 0.05
        elif change == "region":
            grounding["grounded_destination"]["x"] = 0.21
        else:
            grounding["top_grasp_support_height_m"] = 0.01
        inputs["grounding"] = grounding
    elif change in {"target_pose", "compiled_velocity"}:
        parameters = json.loads(json.dumps(inputs["resolved"].parameters))
        if change == "target_pose":
            parameters["target_pose"]["x"] = 0.21
        else:
            parameters["tcp_velocity"] = 0.16
        inputs["resolved"] = inputs["resolved"].model_copy(update={"parameters": parameters})
    elif change == "contract":
        inputs["contract"] = inputs["contract"].model_copy(update={"user_instruction": "changed"})
    elif change == "step":
        inputs["step"] = inputs["step"].model_copy(update={"parameters": {"region_id": "changed"}})
    elif change == "role":
        binding = inputs["role_binding"]
        inputs["role_binding"] = replace(
            binding,
            edge_policy=binding.evidence()["edge_policy"],
            bundle=replace(
                binding.bundle,
                cloud_snapshot=replace(binding.bundle.cloud_snapshot, provider_id="changed-cloud"),
            ),
        )
    elif change == "context":
        inputs["online"] = replace(inputs["online"], context_hash="another-checkpoint")
    elif change == "frame":
        observation = inputs["online"].observation.model_copy(
            update={"frame_id": "new-frame", "observation_id": "new-frame", "checksum_sha256": ""}
        )
        inputs["online"] = replace(inputs["online"], observation=observation)
    else:
        inputs["effective_duration_s"] = 13.0
    with pytest.raises(ValueError):
        module.validate_native_reference(reference, **inputs)


@pytest.mark.parametrize("change", ["missing", "modified", "rehashed"])
def test_source_identity_checks_current_executing_code_not_rehashed_caller_copy(tmp_path, change):
    module = api()
    inputs = sample(tmp_path)
    binding = inputs["role_binding"]
    device = dict(binding.device_source_hashes)
    name = "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py"
    if change == "missing":
        device.pop(name)
    else:
        path = tmp_path / name
        path.write_bytes(path.read_bytes() + b"\n# changed controller source\n")
        if change == "rehashed":
            device[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    inputs["role_binding"] = replace(
        binding,
        edge_policy=binding.evidence()["edge_policy"],
        device_source_hashes=device,
        bundle=replace(binding.bundle, device_pipeline_hash=configuration_hash(device)),
    )
    with pytest.raises(ValueError):
        module.resolve_native_reference(**inputs)


def test_inputs_are_detached_and_no_nested_alias_can_change_old_reference(tmp_path):
    module = api()
    inputs = sample(tmp_path)
    reference = module.resolve_native_reference(**inputs)
    endpoint = reference.endpoint_xyz
    inputs["grounding"]["resolved_top_grasp_tcp"]["z"] = 99
    inputs["resolved"].parameters["target_pose"]["z"] = 99
    inputs["online"].robot_state.tcp_pose.z = 99
    assert reference.endpoint_xyz == endpoint == (0.45, 0.0, 0.16)
    with pytest.raises(ValueError):
        module.validate_native_reference(reference, **inputs)
    with pytest.raises(FrozenInstanceError):
        reference.kind = "OBJECT_CONTACT"
    with pytest.raises(TypeError):
        inputs["role_binding"].device_source_hashes[SOURCES[0]] = "f" * 64
    with pytest.raises(TypeError):
        inputs["role_binding"].edge_policy["verification_budget"]["x"] = 1


@pytest.mark.parametrize("skill", ["GRASP", "APPROACH"])
def test_contact_reference_cannot_be_relabelled_as_fixed_goal(tmp_path, skill):
    module = api()
    inputs = sample(tmp_path, skill)
    reference = module.resolve_native_reference(**inputs)
    assert reference.kind == "OBJECT_CONTACT"
    assert reference.fixed_goal_coordinate_invariant is False
    assert reference.full_horizon_s == 12
    assert not hasattr(reference, "motion_bound_m_s")
    assert not hasattr(reference, "geometric_error_bound_m")
    with pytest.raises(ValueError):
        module.validate_native_reference(
            replace(reference, kind="FIXED_WORLD_TCP_GOAL", fixed_goal_coordinate_invariant=True),
            **inputs,
        )


@pytest.mark.parametrize("duration", [0, 7, float("nan"), True])
def test_effective_owner_horizon_cannot_shorten_resolved_timeout(tmp_path, duration):
    module = api()
    inputs = sample(tmp_path)
    inputs["effective_duration_s"] = duration
    with pytest.raises(ValueError):
        module.resolve_native_reference(**inputs)


def test_public_role_like_object_is_not_a_registered_runtime_binding(tmp_path):
    module = api()
    inputs = sample(tmp_path)
    binding = inputs["role_binding"]
    inputs["role_binding"] = SimpleNamespace(**binding.__dict__)
    with pytest.raises(ValueError):
        module.resolve_native_reference(**inputs)


@pytest.mark.parametrize(
    "start,end,duration,displacement",
    [
        (1534, 2229, 2.8958333565, 0.0878292524),
        (2349, 3554, 5.0208333735, 0.3452214690),
    ],
)
def test_actual_transport_displacement_cannot_meet_original_total_motion_gate(
    start,
    end,
    duration,
    displacement,
):
    api()
    path = (
        ROOT
        / "artifacts/research/process/20261004-ced-development"
        / "t7b-visible-marker-next/attempt-1/raw-physics.jsonl"
    )
    endpoints = {}
    for line in path.open():
        row = json.loads(line)
        if row["physics_step"] in {start, end}:
            endpoints[row["physics_step"]] = row
        if row["physics_step"] == end:
            break
    observed_duration = endpoints[end]["sim_time_s"] - endpoints[start]["sim_time_s"]
    observed_displacement = dist(
        endpoints[start]["object_position_m"], endpoints[end]["object_position_m"]
    )
    assert observed_duration == pytest.approx(duration, abs=1e-10)
    assert observed_displacement == pytest.approx(displacement, abs=1e-10)
    # Endpoint displacement / duration is only a necessary lower bound, not a certificate.
    minimum_speed = observed_displacement / observed_duration
    action = evidence_contract(duration=10)
    action = replace(
        action,
        evidence=replace(
            action.evidence,
            captured_at=NOW,
            geometric_error_bound_m=0,
            motion_bound_m_s=minimum_speed,
        ),
    )
    verdict = validate_evidence(action, NOW, "context-1", "cal-1")
    assert verdict.status == "INVALID"
    assert verdict.bound_at_completion_m > 0.30


def test_read_only_nested_input_mappings_rebuild_the_same_reference(tmp_path):
    from types import MappingProxyType

    module = api()
    inputs = sample(tmp_path)
    reference = module.resolve_native_reference(**inputs)
    inputs["grounding"] = MappingProxyType(
        {
            key: MappingProxyType(value) if isinstance(value, dict) else value
            for key, value in inputs["grounding"].items()
        }
    )
    facts = MappingProxyType(
        {key: MappingProxyType(value) for key, value in inputs["online"].visual_facts.items()}
    )
    inputs["online"] = replace(inputs["online"], visual_facts=facts)
    assert module.resolve_native_reference(**inputs) == reference
