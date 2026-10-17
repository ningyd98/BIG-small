"""Versioned source binding for the existing native action's reference coordinates.

These records are inspectable command invariants, not authenticated calibration
providers, native admission proofs, physical tracking bounds or speed certificates.
The caller's grounding and effective owner duration still require independent
registration/owner revalidation before a future calibration consumer can use them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from cloud_edge_robot_arm.contracts import Pose, RobotState, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.runtime.skill_registry import MotionParams, SkillRegistry
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

if TYPE_CHECKING:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

_REFERENCE_SOURCES = (
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
_FIXED_SKILLS = frozenset({"LIFT", "RETREAT", "MOVE_TO_REGION", "PLACE"})
_CONTACT_SKILLS = frozenset({"MOVE_ABOVE", "APPROACH", "GRASP"})


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("native reference data requires string mapping keys")
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _json(value: object) -> str:
    try:
        return json.dumps(
            _plain_json(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("native reference inputs require detached finite JSON data") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class NativeActionReference:
    semantics_version: Literal["native.action_reference.v1"]
    kind: Literal["OBJECT_CONTACT", "FIXED_WORLD_TCP_GOAL"]
    reference_id: str
    reference_digest: str
    execution_payload_digest: str
    contract_digest: str
    grounding_digest: str
    online_digest: str
    source_digest: str
    observation_id: str
    observation_sha256: str
    plan_version: int
    command_seq: int
    context_hash: str
    role_bundle_hash: str
    full_horizon_s: float
    endpoint_xyz: tuple[float, float, float] | None
    orientation_wxyz: tuple[float, float, float, float] | None
    fixed_goal_coordinate_invariant: bool


@dataclass(frozen=True)
class _SnapshotRobot:
    state: RobotState

    def get_state(self) -> RobotState:
        return self.state


def _current_sources(binding: RoleRuntimeBinding) -> dict[str, str]:
    if type(binding) is not RoleRuntimeBinding:
        raise ValueError("exact registered role runtime binding required")
    # Reconstruct nested source/policy data; public dataclasses are not acceptance tokens.
    copied = RoleRuntimeBinding(
        binding.bundle,
        binding.edge_snapshot,
        dict(binding.device_source_hashes),
        binding.evidence()["edge_policy"],
        root=binding.root,
    )
    for inventory in (
        copied.bundle.cloud_snapshot.source_hashes,
        copied.edge_snapshot.source_hashes,
        copied.device_source_hashes,
    ):
        copied._validate_sources(inventory)
    root = Path(__file__).resolve().parents[3]
    sources = {}
    for name in _REFERENCE_SOURCES:
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if copied.device_source_hashes.get(name) != actual:
            raise ValueError("reference source missing or differs from currently executing code")
        sources[name] = actual
    return sources


def resolve_native_reference(
    online: OnlineEvidenceSnapshot,
    contract: TaskContract,
    step: TaskStep,
    *,
    resolved: TaskStep,
    grounding: Mapping[str, Any],
    role_binding: RoleRuntimeBinding,
    effective_duration_s: float | None = None,
) -> NativeActionReference:
    """Rebuild original resolution and bind the registry's detached exact endpoint.

    ``effective_duration_s`` preserves a longer checked owner horizon. Its scalar
    alone does not authenticate an owner receipt; a downstream source must recheck
    the original receipt/duration calculation. No input or output here admits action.
    Context and role identities are distinct: an owner context may be a checkpoint.
    """
    from cloud_edge_robot_arm.vision.execution import resolved_step

    sources = _current_sources(role_binding)
    if (
        any(
            type(v) is not int
            for v in (
                online.plan_version,
                online.command_seq,
                contract.plan_version,
                contract.command_seq,
            )
        )
        or (online.plan_version, online.command_seq)
        != (
            contract.plan_version,
            contract.command_seq,
        )
        or not isinstance(online.context_hash, str)
        or not online.context_hash
    ):
        raise ValueError("current native context/version mismatch")
    # Validation from serialized originals breaks all nested BaseModel/dict aliases.
    command = TaskContract.model_validate_json(_json(contract.model_dump(mode="json")))
    original = TaskStep.model_validate_json(_json(step.model_dump(mode="json")))
    compiled = TaskStep.model_validate_json(_json(resolved.model_dump(mode="json")))
    if not any(
        s.model_dump(mode="json") == original.model_dump(mode="json") for s in command.steps
    ):
        raise ValueError("original step does not belong to exact contract")
    if (command.task_target.object_id, command.task_target.target_region_id) != (
        "object",
        "target_region",
    ):
        raise ValueError("existing resolver supports only its exact native target identities")
    skill = original.skill.value
    if skill not in _FIXED_SKILLS | _CONTACT_SKILLS:
        raise ValueError("unsupported native reference skill")
    observation = RGBDObservation.model_validate_json(
        _json(online.observation.model_dump(mode="json"))
    )
    state = RobotState.model_validate_json(_json(online.robot_state.model_dump(mode="json")))
    detached_grounding = json.loads(_json(dict(grounding)))
    expected = resolved_step(
        original, cast("MuJoCoSkillRobot", _SnapshotRobot(state)), detached_grounding
    )
    if expected.model_dump(mode="json") != compiled.model_dump(mode="json"):
        raise ValueError("resolved payload differs from original source-derived endpoint")
    minimum_horizon = (
        max(
            original.timeout_ms,
            original.expected_duration_ms,
            compiled.timeout_ms,
            compiled.expected_duration_ms,
        )
        / 1000
    )
    horizon = minimum_horizon if effective_duration_s is None else effective_duration_s
    if type(horizon) not in (int, float) or not isfinite(horizon) or horizon < minimum_horizon:
        raise ValueError("effective owner horizon must be finite and cannot shorten full action")
    definition = SkillRegistry.default().definition_for(compiled.skill)
    if definition is None:
        raise ValueError("native skill compiler unavailable")
    parameters = definition.validate(compiled.parameters)
    endpoint = None
    orientation = None
    if isinstance(parameters, MotionParams) and parameters.target_pose is not None:
        motion = MotionTarget(Pose.model_validate(parameters.target_pose), _DOWNWARD)
        endpoint = (motion.position.x, motion.position.y, motion.position.z)
        orientation = motion.orientation_wxyz
    fixed = skill in _FIXED_SKILLS
    if fixed and endpoint is None:
        raise ValueError("fixed reference requires the exact compiled motion endpoint")
    payload = {
        "step": compiled.model_dump(mode="json"),
        "validated_parameters": parameters.model_dump(mode="json"),
        "motion_target": {"position": endpoint, "orientation_wxyz": orientation},
    }
    values = dict(
        semantics_version="native.action_reference.v1",
        kind="FIXED_WORLD_TCP_GOAL" if fixed else "OBJECT_CONTACT",
        reference_id=f"{command.task_id}:{original.step_id}:{command.plan_version}:{command.command_seq}",
        execution_payload_digest=_digest(payload),
        contract_digest=_digest(command.model_dump(mode="json")),
        grounding_digest=_digest(detached_grounding),
        online_digest=_digest(
            {
                "observation": observation.checksum_sha256,
                "robot_state": state.model_dump(mode="json"),
                "visual_facts": online.visual_facts,
            }
        ),
        source_digest=_digest(sources),
        observation_id=observation.observation_id,
        observation_sha256=observation.checksum_sha256,
        plan_version=command.plan_version,
        command_seq=command.command_seq,
        context_hash=online.context_hash,
        role_bundle_hash=role_binding.bundle.digest(),
        full_horizon_s=float(horizon),
        endpoint_xyz=endpoint,
        orientation_wxyz=orientation,
        fixed_goal_coordinate_invariant=fixed,
    )
    return NativeActionReference(reference_digest=_digest(values), **values)


def validate_native_reference(
    reference: NativeActionReference,
    online: OnlineEvidenceSnapshot,
    contract: TaskContract,
    step: TaskStep,
    *,
    resolved: TaskStep,
    grounding: Mapping[str, Any],
    role_binding: RoleRuntimeBinding,
    effective_duration_s: float | None = None,
) -> None:
    """Reject stale/relabelled references by exact current reconstruction, without admission."""
    current = resolve_native_reference(
        online,
        contract,
        step,
        resolved=resolved,
        grounding=grounding,
        role_binding=role_binding,
        effective_duration_s=effective_duration_s,
    )
    if type(reference) is not NativeActionReference or asdict(reference) != asdict(current):
        raise ValueError("native reference differs from exact current reconstruction")
