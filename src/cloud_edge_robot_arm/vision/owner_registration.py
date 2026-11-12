"""Pure immutable source bindings, never actual owner/method/physical admission.

No repository, worker, executor, stage/resume, provider or live evidence certificate
is created here. JSON-backed model properties return fresh detached copies.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import BaseModel

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import (
    StepDependency,
    find_repair_window,
)
from cloud_edge_robot_arm.contracts import ExecutionCheckpoint, Pose, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import (
    _ROBOT_CONDITIONS,
    _VISUAL_CONDITIONS,
    ConditionSpec,
    OnlineEvidenceSnapshot,
)
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.vision.local_temporal import (
    JSONValue,
    LocalDomainEnvelope,
)
from cloud_edge_robot_arm.vision.local_temporal import (
    _array as local_array,
)
from cloud_edge_robot_arm.vision.local_temporal import (
    _integer as local_integer,
)
from cloud_edge_robot_arm.vision.local_temporal import (
    _object as local_object,
)
from cloud_edge_robot_arm.vision.local_temporal import (
    _text as local_text,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("binding timestamps require an aware clock")
    return value


def _positive(value: float) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        raise ValueError("policy values must be finite and positive")
    return float(value)


def _counter(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("versions/generations require nonnegative integers")
    return value


def _sha(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("full SHA256 source identity required")
    return value


def _sources(value: Mapping[str, str]) -> Mapping[str, str]:
    if not value:
        raise ValueError("explicit source inventory required")
    copied = {}
    for name, digest in value.items():
        if not isinstance(name, str) or not name or name.startswith("/") or ".." in name.split("/"):
            raise ValueError("source names must be registered relative paths")
        copied[name] = _sha(digest)
    return MappingProxyType(copied)


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ValueError("source payload keys must be strings")
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if type(value) is float and not math.isfinite(value):
        raise ValueError("nonfinite source payload")
    if value is None or type(value) in {str, bool, int, float}:
        return value
    raise ValueError("source payload must contain bounded JSON data")


def _freeze(value: Any) -> Any:
    plain = _plain(value)
    if isinstance(plain, dict):
        return MappingProxyType({k: _freeze(v) for k, v in plain.items()})
    if isinstance(plain, list):
        return tuple(_freeze(v) for v in plain)
    return plain


def _json(value: Any) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _strict_model_tree(value: Any) -> None:
    if isinstance(value, BaseModel):
        if set(vars(value)) - set(type(value).model_fields):
            raise ValueError("undeclared nested source model field")
        for name in (
            "plan_version",
            "command_seq",
            "expected_duration_ms",
            "timeout_ms",
            "retry_limit",
            "current_step_index",
            "scene_version",
            "expected_scene_version",
        ):
            if hasattr(value, name) and type(getattr(value, name)) is not int:
                raise ValueError("strict nested integer fields required")
        for name, definition in type(value).model_fields.items():
            item = getattr(value, name)
            if definition.annotation is bool and type(item) is not bool:
                raise ValueError("strict source booleans required")
            _strict_model_tree(item)
    elif isinstance(value, Mapping):
        for item in value.values():
            _strict_model_tree(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _strict_model_tree(item)


def _from_json[Model: BaseModel](stored: str, model: type[Model]) -> Model:
    raw = json.loads(stored)
    if not isinstance(raw, dict) or set(raw) - set(model.model_fields):
        raise ValueError("undeclared stored source fields")

    def integers(value: Any) -> None:
        if isinstance(value, dict):
            for name, item in value.items():
                if (
                    name
                    in {
                        "plan_version",
                        "command_seq",
                        "expected_duration_ms",
                        "timeout_ms",
                        "retry_limit",
                        "current_step_index",
                        "scene_version",
                        "expected_scene_version",
                    }
                    and type(item) is not int
                ):
                    raise ValueError("stored integer source fields cannot be coerced")
                integers(item)
        elif isinstance(value, list):
            for item in value:
                integers(item)

    integers(raw)
    if model is TaskContract:
        for step in raw.get("steps", []):
            if not isinstance(step, dict) or set(step) - set(TaskStep.model_fields):
                raise ValueError("undeclared stored original step fields")
    return model.model_validate(raw)


def _model_json(value: BaseModel, model: type[BaseModel]) -> str:
    _strict_model_tree(value)
    if not isinstance(value, model) or set(vars(value)) - set(model.model_fields):
        raise ValueError("undeclared or wrong source model")
    for name in (
        "plan_version",
        "command_seq",
        "expected_duration_ms",
        "timeout_ms",
        "retry_limit",
        "current_step_index",
        "scene_version",
        "expected_scene_version",
    ):
        if hasattr(value, name) and type(getattr(value, name)) is not int:
            raise ValueError("model_copy cannot substitute coerced integer source fields")
    payload = value.model_dump(mode="json")
    result = model.model_validate(payload)
    return _json(result.model_dump(mode="json"))


def _condition(condition: ConditionSpec) -> ConditionSpec:
    if not isinstance(condition, ConditionSpec):
        raise ValueError("canonical declared condition required")
    name = condition.name
    if type(name) is str and name in {
        "registered_object_pose_available",
        "registered_region_model_available",
    }:
        tolerances = condition.tolerances
        if not isinstance(tolerances, Mapping):
            raise ValueError("canonical declared condition required")
        version = tolerances.get("condition_registry_version")
        origin = tolerances.get("requirement_origin")
        if (
            type(version) is not str
            or version != "registered-model-condition-v2"
            or type(origin) is not str
            or origin
            not in {
                "DEFAULT_PRECONDITION",
                "EXPLICIT_PRECONDITION",
                "DEFAULT_POSTCONDITION",
                "EXPLICIT_SUCCESS",
                "EXPLICIT_COMPLETION",
            }
        ):
            raise ValueError("canonical declared condition required")
    elif name not in (_VISUAL_CONDITIONS | _ROBOT_CONDITIONS):
        raise ValueError("canonical declared condition required")
    if condition.target_id is not None and (
        not isinstance(condition.target_id, str) or not condition.target_id
    ):
        raise ValueError("condition target identity required")
    if isinstance(condition.sensor_requirements, str):
        raise ValueError("condition sensor requirements must be an explicit sequence")
    sensors = tuple(condition.sensor_requirements)
    if not sensors or any(not isinstance(s, str) or not s for s in sensors):
        raise ValueError("condition sensors required")
    return ConditionSpec(
        condition.name, condition.target_id, _freeze(condition.tolerances), sensors
    )


def _condition_payload(condition: ConditionSpec) -> dict[str, Any]:
    return {
        "name": condition.name,
        "target_id": condition.target_id,
        "tolerances": _plain(condition.tolerances),
        "sensor_requirements": list(condition.sensor_requirements),
    }


@dataclass(frozen=True)
class VisualOwnerIdentity:
    job_id: str
    run_id: str
    attempt: int
    worker_id: str
    lease_id: str
    owner_epoch: str
    episode_id: str
    task_id: str
    plan_id: str
    robot_id: str

    def __post_init__(self) -> None:
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("explicit positive attempt required")
        for item in fields(self):
            if item.name == "attempt":
                continue
            value = getattr(self, item.name)
            if (
                not isinstance(value, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is None
                or value.lower() in {"unknown", "robot-unknown", "placeholder", "none"}
            ):
                raise ValueError("nonplaceholder factory identity required")

    def to_payload(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass(frozen=True, init=False)
class OriginalActionRequirements:
    _original_step_json: str
    preconditions: tuple[ConditionSpec, ...]
    postconditions: tuple[ConditionSpec, ...]
    allowed_error_m: float
    sensor_requirements: tuple[str, ...]
    ordinary_ttl_s: float
    expected_duration_s: float
    policy_source_hashes: Mapping[str, str]

    def __init__(
        self,
        original_step: TaskStep | None = None,
        preconditions: Sequence[ConditionSpec] = (),
        postconditions: Sequence[ConditionSpec] = (),
        allowed_error_m: float = 0.01,
        sensor_requirements: Sequence[str] = ("rgbd",),
        ordinary_ttl_s: float = 5.0,
        expected_duration_s: float = 1.0,
        policy_source_hashes: Mapping[str, str] | None = None,
        *,
        _original_step_json: str | None = None,
    ) -> None:
        step = (
            original_step
            if original_step is not None
            else TaskStep.model_validate_json(_original_step_json or "null")
        )
        stored = _model_json(step, TaskStep)
        pre, post = (
            tuple(_condition(c) for c in preconditions),
            tuple(_condition(c) for c in postconditions),
        )
        if not pre or not post:
            raise ValueError("original canonical pre/effect requirements cannot be empty")
        if not set(step.preconditions) <= {c.name for c in pre} or not set(
            step.success_conditions
        ) <= {c.name for c in post}:
            raise ValueError("original condition names cannot be removed")
        if isinstance(sensor_requirements, str):
            raise ValueError("original sensor requirements must be an explicit sequence")
        sensors = tuple(sensor_requirements)
        if (
            not sensors
            or len(sensors) != len(set(sensors))
            or any(not isinstance(s, str) or not s for s in sensors)
        ):
            raise ValueError("explicit original sensor policy required")
        duration = _positive(expected_duration_s)
        if duration < max(step.expected_duration_ms, step.timeout_ms) / 1000:
            raise ValueError("original duration must cover original timeout/expected horizon")
        for name, value in {
            "_original_step_json": stored,
            "preconditions": pre,
            "postconditions": post,
            "allowed_error_m": _positive(allowed_error_m),
            "sensor_requirements": sensors,
            "ordinary_ttl_s": _positive(ordinary_ttl_s),
            "expected_duration_s": duration,
            "policy_source_hashes": _sources(policy_source_hashes or {}),
        }.items():
            object.__setattr__(self, name, value)

    @property
    def original_step(self) -> TaskStep:
        return TaskStep.model_validate_json(self._original_step_json)

    def to_payload(self) -> dict[str, Any]:
        step = self.original_step
        return {
            "original_step": json.loads(self._original_step_json),
            "original_step_hash": _digest(json.loads(self._original_step_json)),
            "preconditions": [_condition_payload(c) for c in self.preconditions],
            "postconditions": [_condition_payload(c) for c in self.postconditions],
            "allowed_error_m": self.allowed_error_m,
            "sensor_requirements": list(self.sensor_requirements),
            "ordinary_ttl_s": self.ordinary_ttl_s,
            "expected_duration_s": self.expected_duration_s,
            "timeout_ms": step.timeout_ms,
            "retry_limit": step.retry_limit,
            "policy_source_hashes": dict(self.policy_source_hashes),
        }

    def digest(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True)
class VisualOriginalPlan:
    identity: VisualOwnerIdentity
    _contract_json: str
    proposal_hash: str
    role_bundle_hash: str
    compiler_source_hashes: Mapping[str, str]
    source_hashes: Mapping[str, str]
    requirements: Mapping[str, OriginalActionRequirements]
    dependencies: tuple[StepDependency, ...]
    task_deadline_at: datetime
    verification_deadline_at: datetime
    registered_at: datetime
    binding_scope: ClassVar[str] = "SOURCE_BINDING_ONLY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", VisualOwnerIdentity(**self.identity.to_payload()))
        contract = _from_json(self._contract_json, TaskContract)
        object.__setattr__(self, "_contract_json", _model_json(contract, TaskContract))
        object.__setattr__(self, "proposal_hash", _sha(self.proposal_hash))
        object.__setattr__(self, "role_bundle_hash", _sha(self.role_bundle_hash))
        for name in ("compiler_source_hashes", "source_hashes"):
            object.__setattr__(self, name, _sources(getattr(self, name)))
        copied = {
            name: OriginalActionRequirements(
                r.original_step,
                r.preconditions,
                r.postconditions,
                r.allowed_error_m,
                r.sensor_requirements,
                r.ordinary_ttl_s,
                r.expected_duration_s,
                r.policy_source_hashes,
            )
            for name, r in self.requirements.items()
        }
        object.__setattr__(self, "requirements", MappingProxyType(copied))
        if self.identity.task_id != contract.task_id or set(copied) != {
            step.step_id for step in contract.steps
        }:
            raise ValueError("complete original identity/requirement coverage required")
        for step in contract.steps:
            requirement = copied[step.step_id]
            if _model_json(requirement.original_step, TaskStep) != _model_json(step, TaskStep):
                raise ValueError("direct original requirements differ from original step")
            if any(
                self.source_hashes.get(k) != v for k, v in requirement.policy_source_hashes.items()
            ):
                raise ValueError("direct original policy/source mismatch")
            if any(
                c.target_id is not None
                and c.target_id
                not in {contract.task_target.object_id, contract.task_target.target_region_id}
                for c in (*requirement.preconditions, *requirement.postconditions)
            ):
                raise ValueError("direct original condition target mismatch")
        if any(self.source_hashes.get(k) != v for k, v in self.compiler_source_hashes.items()):
            raise ValueError("direct compiler/source mismatch")
        graph = tuple(
            StepDependency(
                d.step_id, d.depends_on, d.evidence_ids, d.physical_effect_id, d.completed
            )
            for d in self.dependencies
        )
        if [d.step_id for d in graph] != [step.step_id for step in contract.steps]:
            raise ValueError("direct original graph coverage mismatch")
        find_repair_window(
            graph,
            set(),
            expected_plan_version=contract.plan_version,
            expected_command_seq=contract.command_seq,
        )
        object.__setattr__(self, "dependencies", graph)
        for name in ("task_deadline_at", "verification_deadline_at", "registered_at"):
            _aware(getattr(self, name))
        if (
            self.effective_deadline_at <= self.registered_at
            or self.registered_at < contract.issued_at
        ):
            raise ValueError("direct original deadline invalid")

    @property
    def contract(self) -> TaskContract:
        return TaskContract.model_validate_json(self._contract_json)

    @property
    def effective_deadline_at(self) -> datetime:
        return min(self.task_deadline_at, self.verification_deadline_at, self.contract.valid_until)

    def freeze_inputs(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "contract": self.contract,
            "proposal_hash": self.proposal_hash,
            "role_bundle_hash": self.role_bundle_hash,
            "compiler_source_hashes": self.compiler_source_hashes,
            "source_hashes": self.source_hashes,
            "requirements": self.requirements,
            "dependencies": self.dependencies,
            "task_deadline_at": self.task_deadline_at,
            "verification_deadline_at": self.verification_deadline_at,
            "registered_at": self.registered_at,
        }

    def to_payload(self) -> dict[str, Any]:
        return {
            "binding_scope": self.binding_scope,
            "identity": self.identity.to_payload(),
            "contract": json.loads(self._contract_json),
            "proposal_hash": self.proposal_hash,
            "role_bundle_hash": self.role_bundle_hash,
            "compiler_source_hashes": dict(self.compiler_source_hashes),
            "source_hashes": dict(self.source_hashes),
            "requirements": {k: v.to_payload() for k, v in self.requirements.items()},
            "dependencies": [
                {f.name: _plain(getattr(d, f.name)) for f in fields(d)} for d in self.dependencies
            ],
            "task_deadline_at": self.task_deadline_at.isoformat(),
            "verification_deadline_at": self.verification_deadline_at.isoformat(),
            "registered_at": self.registered_at.isoformat(),
        }

    def digest(self) -> str:
        return _digest(self.to_payload())


def local_owner_identity(payload: Mapping[str, JSONValue]) -> VisualOwnerIdentity:
    values = local_object(
        payload,
        frozenset(
            (
                "job_id run_id attempt worker_id lease_id owner_epoch "
                "episode_id task_id plan_id robot_id"
            ).split()
        ),
    )
    return VisualOwnerIdentity(
        local_text(values["job_id"]),
        local_text(values["run_id"]),
        local_integer(values["attempt"], positive=True),
        local_text(values["worker_id"]),
        local_text(values["lease_id"]),
        local_text(values["owner_epoch"]),
        local_text(values["episode_id"]),
        local_text(values["task_id"]),
        local_text(values["plan_id"]),
        local_text(values["robot_id"]),
    )


class LocalVisualOriginalPlan(LocalDomainEnvelope, VisualOriginalPlan):
    _tag = "visual.owner.original.local.v1"

    @property
    def identity(self) -> VisualOwnerIdentity:
        return local_owner_identity(self.object("identity"))

    @property
    def contract(self) -> TaskContract:
        return self.model("contract", TaskContract)

    @property
    def proposal_hash(self) -> str:
        return self.string("proposal_hash")

    @property
    def role_bundle_hash(self) -> str:
        return self.string("role_bundle_hash")

    @property
    def compiler_source_hashes(self) -> Mapping[str, str]:
        return self.hashes("compiler_source_hashes")

    @property
    def source_hashes(self) -> Mapping[str, str]:
        return self.hashes("source_hashes")

    @property
    def requirements(self) -> Mapping[str, OriginalActionRequirements]:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            requirement_from_payload,
        )

        return {
            key: requirement_from_payload(local_object(value))
            for key, value in self.object("requirements").items()
        }

    @property
    def dependencies(self) -> tuple[StepDependency, ...]:
        result: list[StepDependency] = []
        for raw in local_array(self.semantic["dependencies"]):
            item = local_object(raw)
            completed = item["completed"]
            if type(completed) is not bool:
                raise ValueError("strict dependency completion flag required")
            effect = item["physical_effect_id"]
            result.append(
                StepDependency(
                    local_text(item["step_id"]),
                    tuple(local_text(value) for value in local_array(item["depends_on"])),
                    tuple(local_text(value) for value in local_array(item["evidence_ids"])),
                    None if effect is None else local_text(effect),
                    completed,
                )
            )
        return tuple(result)

    @property
    def task_deadline_at(self) -> datetime:
        return self.legacy_deadline()

    @property
    def verification_deadline_at(self) -> datetime:
        return self.legacy_deadline()

    @property
    def registered_at(self) -> datetime:
        return self.legacy_deadline()

    @property
    def effective_deadline_at(self) -> datetime:
        return self.legacy_deadline()


def freeze_original_visual_plan(
    *,
    identity: VisualOwnerIdentity,
    contract: TaskContract,
    proposal_hash: str,
    role_bundle_hash: str,
    compiler_source_hashes: Mapping[str, str],
    source_hashes: Mapping[str, str],
    requirements: Mapping[str, OriginalActionRequirements],
    dependencies: Sequence[StepDependency],
    task_deadline_at: datetime,
    verification_deadline_at: datetime,
    registered_at: datetime,
    previous: VisualOriginalPlan | None = None,
) -> VisualOriginalPlan:
    identity = VisualOwnerIdentity(**identity.to_payload())
    stored = _model_json(contract, TaskContract)
    steps = contract.steps
    if identity.task_id != contract.task_id or set(requirements) != {s.step_id for s in steps}:
        raise ValueError("original identity/complete requirement coverage mismatch")
    sources, compiler = _sources(source_hashes), _sources(compiler_source_hashes)
    copied = {}
    for step in steps:
        r = requirements[step.step_id]
        if not isinstance(r, OriginalActionRequirements) or _model_json(
            r.original_step, TaskStep
        ) != _model_json(step, TaskStep):
            raise ValueError("requirements must preserve the complete original step")
        copied[step.step_id] = OriginalActionRequirements(
            r.original_step,
            r.preconditions,
            r.postconditions,
            r.allowed_error_m,
            r.sensor_requirements,
            r.ordinary_ttl_s,
            r.expected_duration_s,
            r.policy_source_hashes,
        )
        for name, digest in r.policy_source_hashes.items():
            if sources.get(name) != digest:
                raise ValueError("original requirement policy source differs")
        for condition in (*r.preconditions, *r.postconditions):
            if condition.target_id is not None and condition.target_id not in {
                contract.task_target.object_id,
                contract.task_target.target_region_id,
            }:
                raise ValueError("canonical target must remain bound to original task")
    if any(sources.get(k) != v for k, v in compiler.items()):
        raise ValueError("compiler source not bound to complete original inventory")
    graph = tuple(
        StepDependency(d.step_id, d.depends_on, d.evidence_ids, d.physical_effect_id, d.completed)
        for d in dependencies
    )
    if [d.step_id for d in graph] != [s.step_id for s in steps]:
        raise ValueError("complete ordered dependency graph required")
    find_repair_window(
        graph,
        set(),
        expected_plan_version=contract.plan_version,
        expected_command_seq=contract.command_seq,
    )
    start, task_end, verify_end = (
        _aware(registered_at),
        _aware(task_deadline_at),
        _aware(verification_deadline_at),
    )
    if min(task_end, verify_end, contract.valid_until) <= start or start < contract.issued_at:
        raise ValueError("original absolute deadline invalid")
    result = VisualOriginalPlan(
        identity,
        stored,
        _sha(proposal_hash),
        _sha(role_bundle_hash),
        compiler,
        sources,
        MappingProxyType(copied),
        graph,
        task_end,
        verify_end,
        start,
    )
    if previous is not None:
        if previous.identity != identity:
            raise ValueError("original owner identity cannot be replaced")
        old = previous.contract
        if contract.plan_version == old.plan_version:
            if result.digest() != previous.digest():
                raise ValueError("same-version original content is immutable")
        elif contract.plan_version <= old.plan_version or contract.command_seq <= old.command_seq:
            raise ValueError("replacement original versions must advance")
        if task_end > previous.task_deadline_at or verify_end > previous.verification_deadline_at:
            raise ValueError("original deadlines cannot be extended")
    return result


@dataclass(frozen=True)
class DeterministicGroundingPolicy:
    policy_id: str
    version: str
    source_hashes: Mapping[str, str]
    tcp_velocity: float
    acceleration: float
    clearance_m: float
    minimum_height_m: float

    def __post_init__(self) -> None:
        if self.policy_id != "rgbd-top-grasp-v1" or not self.version:
            raise ValueError("explicit deterministic grounding recipe required")
        object.__setattr__(self, "source_hashes", _sources(self.source_hashes))
        for name in ("tcp_velocity", "acceleration", "clearance_m", "minimum_height_m"):
            object.__setattr__(self, name, _positive(getattr(self, name)))

    def to_payload(self) -> dict[str, Any]:
        return {f.name: _plain(getattr(self, f.name)) for f in fields(self)}

    def digest(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True)
class GroundingFrameInputs:
    observation_id: str
    observation_checksum_sha256: str
    episode_id: str
    calibration_version: str
    grasp_tcp: Mapping[str, float]
    destination: Mapping[str, float]
    support_height_m: float
    source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        _sha(self.observation_checksum_sha256)
        if not self.observation_id or not self.episode_id or not self.calibration_version:
            raise ValueError("current frame/calibration identity required")
        for name in ("grasp_tcp", "destination"):
            supplied = getattr(self, name)
            if set(supplied) != {"x", "y", "z"} or any(
                type(v) not in {float, int} or not math.isfinite(v) for v in supplied.values()
            ):
                raise ValueError("strict finite current grounding coordinates required")
            pose = Pose.model_validate(supplied)
            object.__setattr__(self, name, MappingProxyType(pose.model_dump()))
        if type(self.support_height_m) not in {float, int} or not math.isfinite(
            self.support_height_m
        ):
            raise ValueError("finite measured support height required")
        object.__setattr__(self, "source_hashes", _sources(self.source_hashes))

    def to_payload(self) -> dict[str, Any]:
        return {f.name: _plain(getattr(self, f.name)) for f in fields(self)}

    def digest(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True, init=False)
class GroundingDurationCheck:
    _grounded_step_json: str
    observation_id: str
    observation_checksum_sha256: str
    original_plan_hash: str
    grounding_policy_hash: str
    expected_duration_s: float
    checked_at: datetime
    source_hashes: Mapping[str, str]

    def __init__(
        self,
        grounded_step: TaskStep | None = None,
        observation_id: str = "",
        observation_checksum_sha256: str = "",
        original_plan_hash: str = "",
        grounding_policy_hash: str = "",
        expected_duration_s: float = 0,
        checked_at: datetime | None = None,
        source_hashes: Mapping[str, str] | None = None,
        *,
        _grounded_step_json: str | None = None,
    ) -> None:
        step = (
            grounded_step
            if grounded_step is not None
            else TaskStep.model_validate_json(_grounded_step_json or "null")
        )
        values = {
            "_grounded_step_json": _model_json(step, TaskStep),
            "observation_id": observation_id,
            "observation_checksum_sha256": _sha(observation_checksum_sha256),
            "original_plan_hash": _sha(original_plan_hash),
            "grounding_policy_hash": _sha(grounding_policy_hash),
            "expected_duration_s": _positive(expected_duration_s),
            "checked_at": _aware(checked_at),
            "source_hashes": _sources(source_hashes or {}),
        }
        if not observation_id:
            raise ValueError("duration calculation requires current frame")
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def to_payload(self) -> dict[str, Any]:
        return {
            "grounded_step": json.loads(self._grounded_step_json),
            **{
                f.name: _plain(getattr(self, f.name))
                for f in fields(self)
                if f.name != "_grounded_step_json"
            },
        }

    def digest(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True)
class StepGroundingBinding:
    original_plan_hash: str
    current_identity: VisualOwnerIdentity
    original_requirements: OriginalActionRequirements
    owner_revision: int
    state_generation: int
    source_checkpoint_hash: str
    observation_id: str
    observation_checksum_sha256: str
    calibration_version: str
    plan_version: int
    command_seq: int
    grounding_policy_hash: str
    grounding_inputs_hash: str
    duration_check_hash: str | None
    grounding_source_hashes: Mapping[str, str]
    _grounded_step_json: str
    expected_duration_s: float
    created_at: datetime
    valid_until: datetime
    binding_scope: ClassVar[str] = "SOURCE_BINDING_ONLY"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "current_identity", VisualOwnerIdentity(**self.current_identity.to_payload())
        )
        r = self.original_requirements
        object.__setattr__(
            self,
            "original_requirements",
            OriginalActionRequirements(
                r.original_step,
                r.preconditions,
                r.postconditions,
                r.allowed_error_m,
                r.sensor_requirements,
                r.ordinary_ttl_s,
                r.expected_duration_s,
                r.policy_source_hashes,
            ),
        )
        step = _from_json(self._grounded_step_json, TaskStep)
        object.__setattr__(self, "_grounded_step_json", _model_json(step, TaskStep))
        expected = r.original_step
        if (
            step.step_id != expected.step_id
            or step.skill != expected.skill
            or step.timeout_ms != expected.timeout_ms
            or step.retry_limit != expected.retry_limit
            or step.expected_duration_ms != expected.expected_duration_ms
            or step.preconditions
            or step.success_conditions
        ):
            raise ValueError("direct binding cannot replace original semantic/action policy")
        for name in (
            "original_plan_hash",
            "source_checkpoint_hash",
            "observation_checksum_sha256",
            "grounding_policy_hash",
            "grounding_inputs_hash",
        ):
            _sha(getattr(self, name))
        if self.duration_check_hash is not None:
            _sha(self.duration_check_hash)
        for name in ("owner_revision", "state_generation", "plan_version", "command_seq"):
            _counter(getattr(self, name))
        if not self.observation_id or not self.calibration_version:
            raise ValueError("direct binding requires current observation/calibration")
        object.__setattr__(self, "grounding_source_hashes", _sources(self.grounding_source_hashes))
        if _positive(self.expected_duration_s) < r.expected_duration_s:
            raise ValueError("direct binding cannot shorten original horizon")
        if _aware(self.valid_until) <= _aware(self.created_at):
            raise ValueError("direct binding expired")

    @property
    def grounded_step(self) -> TaskStep:
        return TaskStep.model_validate_json(self._grounded_step_json)

    def to_payload(self) -> dict[str, Any]:
        result = {
            f.name: _plain(getattr(self, f.name))
            for f in fields(self)
            if f.name not in {"current_identity", "original_requirements", "_grounded_step_json"}
        }
        result.update(
            binding_scope=self.binding_scope,
            current_identity=self.current_identity.to_payload(),
            original_requirements=self.original_requirements.to_payload(),
            grounded_step=json.loads(self._grounded_step_json),
        )
        return result

    @property
    def binding_hash(self) -> str:
        return self.digest()

    def digest(self) -> str:
        return _digest(self.to_payload())


class LocalStepGroundingBinding(LocalDomainEnvelope, StepGroundingBinding):
    _tag = "visual.owner.grounding.local.v1"

    @property
    def current_identity(self) -> VisualOwnerIdentity:
        return local_owner_identity(self.object("current_identity"))

    @property
    def original_requirements(self) -> OriginalActionRequirements:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            requirement_from_payload,
        )

        return requirement_from_payload(self.object("original_requirements"))

    @property
    def grounded_step(self) -> TaskStep:
        return self.model("grounded_step", TaskStep)

    @property
    def original_plan_hash(self) -> str:
        return self.string("original_plan_hash")

    @property
    def source_checkpoint_hash(self) -> str:
        return self.string("source_checkpoint_hash")

    @property
    def observation_id(self) -> str:
        return self.string("observation_id")

    @property
    def observation_checksum_sha256(self) -> str:
        return self.string("observation_checksum_sha256")

    @property
    def calibration_version(self) -> str:
        return self.string("calibration_version")

    @property
    def grounding_policy_hash(self) -> str:
        return self.string("grounding_policy_hash")

    @property
    def grounding_inputs_hash(self) -> str:
        return self.string("grounding_inputs_hash")

    @property
    def owner_revision(self) -> int:
        return self.counter("owner_revision")

    @property
    def state_generation(self) -> int:
        return self.counter("state_generation")

    @property
    def plan_version(self) -> int:
        return self.counter("plan_version")

    @property
    def command_seq(self) -> int:
        return self.counter("command_seq")

    @property
    def duration_check_hash(self) -> str | None:
        return self.optional_string("duration_check_hash")

    @property
    def grounding_source_hashes(self) -> Mapping[str, str]:
        return self.hashes("grounding_source_hashes")

    @property
    def expected_duration_s(self) -> float:
        return self.number("expected_duration_s", positive=True)

    @property
    def created_at(self) -> datetime:
        return self.legacy_deadline()

    @property
    def valid_until(self) -> datetime:
        return self.legacy_deadline()


def _resolved_parameters(
    step: TaskStep,
    original: VisualOriginalPlan,
    online: OnlineEvidenceSnapshot,
    inputs: GroundingFrameInputs,
    policy: DeterministicGroundingPolicy,
) -> dict[str, Any]:
    grasp, destination = (
        Pose.model_validate(inputs.grasp_tcp),
        Pose.model_validate(inputs.destination),
    )
    current = online.robot_state.tcp_pose
    skill = step.skill.value
    target = None
    params: dict[str, Any] = {}
    if skill in {"MOVE_ABOVE", "APPROACH", "GRASP"}:
        params["object_id"] = original.contract.task_target.object_id
    if skill == "MOVE_ABOVE":
        target = Pose(
            x=grasp.x, y=grasp.y, z=max(policy.minimum_height_m, grasp.z + policy.clearance_m)
        )
    elif skill == "APPROACH":
        target = grasp
    elif skill in {"LIFT", "RETREAT"}:
        target = Pose(
            x=current.x, y=current.y, z=max(current.z + policy.clearance_m, policy.minimum_height_m)
        )
        params["height_m" if skill == "LIFT" else "distance_m"] = target.z - current.z
    elif skill in {"MOVE_TO_REGION", "PLACE"}:
        params["region_id"] = original.contract.task_target.target_region_id
        z = (
            max(policy.minimum_height_m, grasp.z + policy.clearance_m)
            if skill == "MOVE_TO_REGION"
            else destination.z + grasp.z - inputs.support_height_m
        )
        target = Pose(x=destination.x, y=destination.y, z=z)
    elif skill not in {"GRASP", "RELEASE"}:
        raise ValueError("unsupported deterministic visual grounding skill")
    if target is not None:
        params.update(
            target_pose=target.model_dump(),
            tcp_velocity=policy.tcp_velocity,
            acceleration=policy.acceleration,
        )
    return params


_REGISTERED_FLAGS = {
    "prepare_only": True,
    "execution_allowed": False,
    "geometry_basis": "REGISTERED_RIGID_MODEL",
    "object_surface_visibility": "UNKNOWN",
    "geometric_error_bound_m": None,
    "region_geometric_error_bound_m": None,
    "native_authority": "UNAVAILABLE",
}


def _registered_object(payload, keys, constants):
    if type(payload) is not dict or set(payload) != set(keys) | set(constants):
        raise ValueError("exact registered preparation field set required")
    for key, expected in constants.items():
        actual = payload[key]
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError("registered preparation constants cannot confer authority")
    return json.loads(_json(payload))


def _registered_vector(value, length):
    if (
        type(value) is not list
        or len(value) != length
        or any(type(v) not in {int, float} or not math.isfinite(v) for v in value)
    ):
        raise ValueError("strict finite registered geometry array required")


class _RegisteredPayload:
    __slots__ = ("_payload_json",)

    def __init__(self, payload):
        object.__setattr__(self, "_payload_json", _json(self._validate(payload)))

    def __setattr__(self, name, value):
        raise AttributeError("immutable registered preparation source")

    @classmethod
    def from_payload(cls, payload):
        """严格重建独立准备值；内容校验不证明事件来源。"""
        return cls(payload)

    def to_payload(self):
        """返回独立JSON值，避免调用方改写已绑定内容。"""
        return json.loads(self._payload_json)

    def digest(self):
        """将版本、来源、未知量及不可执行标记一起散列。"""
        return hashlib.sha256(self._payload_json.encode()).hexdigest()


class RegisteredGroundingFrameInputs(_RegisteredPayload):
    """注册刚体模型与当前区域的准备输入，不冒充完整表面测量。"""

    __slots__ = ()
    _constants = {
        **_REGISTERED_FLAGS,
        "schema_version": "registered.grounding.inputs.v1",
        "support_basis": "REGISTERED_NOMINAL",
        "region_basis": "RGBD_COLOR_REGION_UNCALIBRATED",
        "wrapper_freshness": "CHECKED",
        "wrapper_asset_validation": "VERIFIED_LOCAL_BYTES",
        "source_validation": "LOCAL_BYTE_CONSISTENCY_ONLY",
    }
    _keys = {
        "observation_id",
        "observation_checksum_sha256",
        "captured_at",
        "scene_id",
        "object_id",
        "target_region_id",
        "episode_id",
        "calibration_version",
        "camera",
        "source_hashes",
        "source_generation",
        "asset_path",
        "asset_sha256",
        "marker_family_id",
        "registration_sha256",
        "marker_registration_hash",
        "marker_estimate_sha256",
        "preview_sha256",
        "grasp_tcp_world_m",
        "object_center_world_m",
        "rotation_object_to_world",
        "destination_world_m",
        "nominal_support_height_m",
    }

    @classmethod
    def _validate(cls, payload):
        p = _registered_object(payload, cls._keys, cls._constants)
        for name in (
            "observation_id",
            "scene_id",
            "episode_id",
            "calibration_version",
            "object_id",
            "target_region_id",
            "asset_path",
            "marker_family_id",
        ):
            if type(p[name]) is not str or not p[name]:
                raise ValueError("explicit registered frame/asset identity required")
        for name in (
            "observation_checksum_sha256",
            "source_generation",
            "asset_sha256",
            "registration_sha256",
            "marker_registration_hash",
            "marker_estimate_sha256",
            "preview_sha256",
        ):
            _sha(p[name])
        _aware(datetime.fromisoformat(p["captured_at"]))
        sources = _sources(p["source_hashes"])
        if (
            _digest(sources) != p["source_generation"]
            or sources.get(p["asset_path"]) != p["asset_sha256"]
        ):
            raise ValueError("registered source/asset generation mismatch")
        camera = p["camera"]
        if type(camera) is not dict or set(camera) != {
            "source",
            "width",
            "height",
            "intrinsics",
            "camera_to_world",
        }:
            raise ValueError("complete registered camera descriptor required")
        if (
            type(camera["source"]) is not str
            or not camera["source"]
            or any(type(camera[n]) is not int or camera[n] < 1 for n in ("width", "height"))
        ):
            raise ValueError("strict registered camera identity required")
        _registered_vector(camera["intrinsics"], 4)
        _registered_vector(camera["camera_to_world"], 16)
        for name in ("grasp_tcp_world_m", "object_center_world_m", "destination_world_m"):
            _registered_vector(p[name], 3)
        r = p["rotation_object_to_world"]
        _registered_vector(r, 9)
        if any(
            abs(sum(r[3 * i + k] * r[3 * j + k] for k in range(3)) - (i == j)) > 1e-6
            for i in range(3)
            for j in range(3)
        ):
            raise ValueError("registered rotation must be orthonormal")
        determinant = (
            r[0] * (r[4] * r[8] - r[5] * r[7])
            - r[1] * (r[3] * r[8] - r[5] * r[6])
            + r[2] * (r[3] * r[7] - r[4] * r[6])
        )
        if abs(determinant - 1) > 1e-6:
            raise ValueError("registered rotation must be proper")
        value = p["nominal_support_height_m"]
        if type(value) not in {int, float} or not math.isfinite(value):
            raise ValueError("finite registered nominal support required")
        return p

    @classmethod
    def from_preview(cls, preview, observation, registration):
        """仅从精确当前准备结果构建输入，并检查帧、注册和区域关联。"""
        from dataclasses import asdict

        from cloud_edge_robot_arm.research.native_collection_grounding import (
            RegisteredCollectionGroundingPreviewV1,
        )
        from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration

        if (
            type(preview) is not RegisteredCollectionGroundingPreviewV1
            or type(observation) is not RGBDObservation
            or type(registration) is not NativeGeometryRegistration
        ):
            raise TypeError("exact current registered preview, frame and registration required")
        obs = RGBDObservation.model_validate_json(_model_json(observation, RGBDObservation))
        reg = NativeGeometryRegistration(registration.to_payload())
        registration_sha256 = _digest(reg.to_payload())
        p, track = preview.to_payload(), preview.track
        geometry = track.geometry
        if (
            p["schema_version"] != "native.collection.registered-preview.v1"
            or preview.status != "DERIVED"
            or track.status != "DERIVED"
            or geometry is None
            or geometry.status != "DERIVED"
            or track.wrapper_freshness != "CHECKED"
            or track.wrapper_asset_validation != "VERIFIED_LOCAL_BYTES"
            or track.source_validation != "LOCAL_BYTE_CONSISTENCY_ONLY"
            or any(
                type(p.get(k)) is not type(v) or p.get(k) != v for k, v in _REGISTERED_FLAGS.items()
            )
            or preview.registration_sha256 != registration_sha256
            or track.registration_sha256 != registration_sha256
            or preview.source_sha256 != track.source_sha256
            or preview.grasp_tcp_world_m != geometry.grasp_tcp_world_m
            or preview.object_center_world_m != geometry.object_center_world_m
            or preview.rotation_object_to_world != geometry.rotation_object_to_world
            or preview.destination_observation_id != obs.observation_id
            or preview.destination_observation_checksum_sha256 != obs.checksum_sha256
        ):
            raise ValueError("current registered preview unavailable or relabelled")
        camera = {
            n: getattr(obs, n)
            for n in ("source", "width", "height", "intrinsics", "camera_to_world")
        }
        if (
            any(
                getattr(track, n) != getattr(obs, n)
                for n in (
                    "observation_id",
                    "captured_at",
                    "scene_id",
                    "episode_id",
                    "calibration_version",
                )
            )
            or track.observation_checksum_sha256 != obs.checksum_sha256
            or any(_plain(getattr(track, n)) != _plain(v) for n, v in camera.items())
            or any(_plain(v) != reg.to_payload()["camera"][n] for n, v in camera.items())
            or geometry.observation_id != obs.observation_id
            or geometry.observation_checksum_sha256 != obs.checksum_sha256
            or geometry.object_id != reg.to_payload()["object_id"]
            or geometry.marker_estimate is None
            or geometry.marker_estimate.status != "OBSERVED"
            or geometry.marker_estimate.observed_marker_ids
            != (reg.to_payload()["pose_marker"]["marker_id"],)
            or geometry.marker_estimate.registration_hash != track.marker_registration_hash
        ):
            raise ValueError("registered preview frame/camera/marker cross-link mismatch")
        return cls(
            {
                **cls._constants,
                "observation_id": obs.observation_id,
                "observation_checksum_sha256": obs.checksum_sha256,
                "captured_at": obs.captured_at.isoformat(),
                "scene_id": obs.scene_id,
                "object_id": reg.to_payload()["object_id"],
                "target_region_id": reg.to_payload()["target_region_id"],
                "episode_id": obs.episode_id,
                "calibration_version": obs.calibration_version,
                "camera": _plain(camera),
                "source_hashes": dict(track.source_hashes),
                "source_generation": track.source_sha256,
                "asset_path": track.asset_path,
                "asset_sha256": track.asset_sha256,
                "marker_family_id": track.marker_family_id,
                "registration_sha256": registration_sha256,
                "marker_registration_hash": track.marker_registration_hash,
                "marker_estimate_sha256": _digest(asdict(geometry.marker_estimate)),
                "preview_sha256": preview.digest(),
                "grasp_tcp_world_m": list(preview.grasp_tcp_world_m),
                "object_center_world_m": list(preview.object_center_world_m),
                "rotation_object_to_world": list(preview.rotation_object_to_world),
                "destination_world_m": list(preview.destination_world_m),
                "nominal_support_height_m": reg.to_payload()["support_height_m"],
            }
        )

    def matches_observation(self, observation):
        """比对完整帧与相机身份；不把散列一致解释为来源认证。"""
        p = self.to_payload()
        return (
            type(observation) is RGBDObservation
            and all(
                p[n] == _plain(getattr(observation, n))
                for n in (
                    "observation_id",
                    "captured_at",
                    "episode_id",
                    "scene_id",
                    "calibration_version",
                )
            )
            and p["observation_checksum_sha256"] == observation.checksum_sha256
            and all(p["camera"][n] == _plain(getattr(observation, n)) for n in p["camera"])
        )

    @property
    def source_hashes(self):
        return _sources(self.to_payload()["source_hashes"])

    @property
    def grasp_tcp(self):
        return dict(zip("xyz", self.to_payload()["grasp_tcp_world_m"], strict=True))

    @property
    def destination(self):
        return dict(zip("xyz", self.to_payload()["destination_world_m"], strict=True))

    @property
    def support_height_m(self):
        return self.to_payload()["nominal_support_height_m"]


class RegisteredGroundingPolicy(_RegisteredPayload):
    """固定版本的准备数值配方，不配置控制器或授予动作权限。"""

    __slots__ = ()
    _constants = {
        "policy_id": "registered-model-grounding-prepare-v1",
        "version": "registered-model-grounding-prepare-v1",
    }

    @classmethod
    def _validate(cls, payload):
        p = _registered_object(
            payload,
            {"source_hashes", "tcp_velocity", "acceleration", "clearance_m", "minimum_height_m"},
            cls._constants,
        )
        _sources(p["source_hashes"])
        for n in ("tcp_velocity", "acceleration", "clearance_m", "minimum_height_m"):
            _positive(p[n])
        return p

    @classmethod
    def for_original(cls, original, source_hashes):
        """按原始安全上限生成固定准备配方，保留最小高度。"""
        if type(original) is not VisualOriginalPlan:
            raise TypeError("UTC original source plan required; no local runtime authority")
        safety = original.contract.safety_constraints
        return cls(
            {
                **cls._constants,
                "source_hashes": dict(_sources(source_hashes)),
                "tcp_velocity": min(0.15, safety.max_tcp_velocity),
                "acceleration": 0.5,
                "clearance_m": 0.10,
                "minimum_height_m": max(0.16, safety.minimum_safe_height),
            }
        )

    @property
    def source_hashes(self):
        return _sources(self.to_payload()["source_hashes"])

    @property
    def tcp_velocity(self):
        return self.to_payload()["tcp_velocity"]

    @property
    def acceleration(self):
        return self.to_payload()["acceleration"]

    @property
    def clearance_m(self):
        return self.to_payload()["clearance_m"]

    @property
    def minimum_height_m(self):
        return self.to_payload()["minimum_height_m"]


def _registered_requirement_family(requirement, *, v2):
    """Version tags on a binding cannot change the retained requirement family."""
    step = requirement.original_step
    for phase, conditions in (
        ("PRE", requirement.preconditions),
        ("POST", requirement.postconditions),
    ):
        for condition in conditions:
            version = condition.tolerances.get("condition_registry_version")
            origin = condition.tolerances.get("requirement_origin")
            if not v2:
                if version == "registered-model-condition-v2" or origin in {
                    "DEFAULT_PRECONDITION",
                    "EXPLICIT_PRECONDITION",
                    "DEFAULT_POSTCONDITION",
                    "EXPLICIT_SUCCESS",
                    "EXPLICIT_COMPLETION",
                }:
                    raise ValueError("v2 requirement cannot be relabeled as legacy")
                continue
            if (
                type(version) is not str
                or version != "registered-model-condition-v2"
                or type(origin) is not str
            ):
                raise ValueError("v2 condition family and origin required")
            if phase == "PRE":
                expected = (
                    "EXPLICIT_PRECONDITION"
                    if condition.name in step.preconditions
                    else "DEFAULT_PRECONDITION"
                )
                if origin != expected:
                    raise ValueError("v2 PRE requirement origin differs")
            elif condition.name in step.success_conditions:
                if origin != "EXPLICIT_SUCCESS":
                    raise ValueError("v2 explicit success origin differs")
            elif origin not in {"DEFAULT_POSTCONDITION", "EXPLICIT_COMPLETION"}:
                raise ValueError("v2 POST requirement origin differs")
    if v2:
        mandatory = {"registered_region_model_available"}
        if step.skill.value in {"MOVE_ABOVE", "APPROACH", "GRASP"}:
            mandatory.add("registered_object_pose_available")
        if not mandatory <= {condition.name for condition in requirement.preconditions}:
            raise ValueError("v2 mandatory registered-model requirement missing")


class RegisteredPreparedStepBinding(_RegisteredPayload):
    """保存原始约束和候选步骤的纯准备绑定，旧执行绑定不接受此类型。"""

    __slots__ = ()
    _constants = {
        **_REGISTERED_FLAGS,
        "schema_version": "registered.grounding.prepared-step.v1",
        "binding_scope": "REGISTERED_MODEL_PREPARATION_ONLY",
    }
    _keys = {
        "original_plan_hash",
        "original_requirements",
        "current_identity",
        "owner_revision",
        "state_generation",
        "lease_source_hash",
        "source_checkpoint_hash",
        "observation_id",
        "observation_checksum_sha256",
        "calibration_version",
        "plan_version",
        "command_seq",
        "grounding_policy_hash",
        "grounding_inputs_hash",
        "grounding_source_hashes",
        "grounded_step",
        "expected_duration_s",
        "created_at",
        "valid_until",
    }

    @classmethod
    def _validate(cls, payload):
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            requirement_from_payload,
        )

        p = _registered_object(payload, cls._keys, cls._constants)
        identity = VisualOwnerIdentity(**p["current_identity"])
        requirement = requirement_from_payload(p["original_requirements"])
        _registered_requirement_family(requirement, v2=False)
        step = _from_json(_json(p["grounded_step"]), TaskStep)
        source = requirement.original_step
        if (
            step.step_id != source.step_id
            or step.skill != source.skill
            or step.timeout_ms != source.timeout_ms
            or step.retry_limit != source.retry_limit
            or step.expected_duration_ms != source.expected_duration_ms
            or step.preconditions
            or step.success_conditions
        ):
            raise ValueError("prepared step cannot replace original action policy")
        for n in ("owner_revision", "state_generation", "plan_version", "command_seq"):
            _counter(p[n])
        for n in (
            "original_plan_hash",
            "lease_source_hash",
            "source_checkpoint_hash",
            "observation_checksum_sha256",
            "grounding_policy_hash",
            "grounding_inputs_hash",
        ):
            _sha(p[n])
        _sources(p["grounding_source_hashes"])
        if (
            not p["observation_id"]
            or not p["calibration_version"]
            or identity.episode_id == ""
            or _positive(p["expected_duration_s"]) != requirement.expected_duration_s
            or _aware(datetime.fromisoformat(p["created_at"]))
            >= _aware(datetime.fromisoformat(p["valid_until"]))
        ):
            raise ValueError("prepared binding duration/frame/time invalid")
        return p

    @property
    def grounded_step(self):
        return TaskStep.model_validate(self.to_payload()["grounded_step"])

    @property
    def valid_until(self):
        return datetime.fromisoformat(self.to_payload()["valid_until"])


class RegisteredCollectionStepBinding(_RegisteredPayload):
    """注册模型采集来源绑定；不提供普通执行或native权限。"""

    __slots__ = ()
    _constants = {
        "schema_version": "registered.collection.binding.v1",
        "binding_scope": "REGISTERED_MODEL_COLLECTION_SOURCE_ONLY",
        "collection_policy_id": "registered-model-collection-v1",
        "execution_authority": False,
        "ordinary_execution_allowed": False,
        "native_authority": "UNAVAILABLE",
    }

    @classmethod
    def _validate(cls, payload):
        p = _registered_object(payload, {"prepared"}, cls._constants)
        prepared = RegisteredPreparedStepBinding.from_payload(p["prepared"])
        if prepared.to_payload() != p["prepared"]:
            raise ValueError("exact registered preparation payload required")
        return p

    @classmethod
    def from_prepared(cls, prepared, *, collection_policy_id):
        """保留内层准备语义；实际采集许可仍由私有应用独立判定。"""
        if type(prepared) is not RegisteredPreparedStepBinding:
            raise TypeError("exact registered preparation binding required")
        return cls(
            {
                **cls._constants,
                "collection_policy_id": collection_policy_id,
                "prepared": prepared.to_payload(),
            }
        )

    @property
    def prepared(self):
        return RegisteredPreparedStepBinding.from_payload(self.to_payload()["prepared"])

    @property
    def grounded_step(self):
        return self.prepared.grounded_step

    @property
    def valid_until(self):
        return self.prepared.valid_until


def _registered_preparation_deadline(original, *, original_step_id, observation, lease_source=None):
    """计算新准备路径共同截止时间；UNKNOWN也不得绕过原条件时效。"""
    requirement = original.requirements.get(original_step_id)
    if requirement is None:
        raise ValueError("registered preparation pending step required")
    ttl = _positive(requirement.ordinary_ttl_s)
    ages = [
        _positive(c.tolerances.get("max_age_s", ttl))
        for c in (*requirement.preconditions, *requirement.postconditions)
    ]
    deadline = min(
        original.effective_deadline_at,
        observation.captured_at + timedelta(seconds=min(5.0, ttl, *ages)),
    )
    return deadline if lease_source is None else min(deadline, _aware(lease_source.expires_at))


def prepare_registered_step_binding(
    original,
    *,
    original_step_id,
    online,
    source_checkpoint,
    current_identity,
    owner_revision,
    state_generation,
    lease_source,
    grounding_inputs,
    grounding_policy,
    now,
):
    """以当前租约和原始检查点准备候选步骤；不创建任何可执行能力。"""
    from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation

    if (
        type(original) is not VisualOriginalPlan
        or type(grounding_inputs) is not RegisteredGroundingFrameInputs
        or type(grounding_policy) is not RegisteredGroundingPolicy
        or type(lease_source) is not WorkerLeaseObservation
        or type(current_identity) is not VisualOwnerIdentity
        or type(online) is not OnlineEvidenceSnapshot
    ):
        raise TypeError("exact registered preparation source types required")
    original, now, cp, contract, observation, requirement, _ = _current_grounding_context(
        original,
        original_step_id=original_step_id,
        online=online,
        source_checkpoint=source_checkpoint,
        current_identity=current_identity,
        owner_revision=owner_revision,
        state_generation=state_generation,
        now=now,
    )
    inputs = RegisteredGroundingFrameInputs.from_payload(grounding_inputs.to_payload())
    policy = RegisteredGroundingPolicy.from_payload(grounding_policy.to_payload())
    identities = inputs.to_payload()
    if (
        identities["object_id"] != contract.task_target.object_id
        or identities["target_region_id"] != contract.task_target.target_region_id
    ):
        raise ValueError("registered preparation target identity mismatch")
    lease = WorkerLeaseObservation(**vars(lease_source))
    if (
        lease.identity(
            episode_id=current_identity.episode_id,
            task_id=current_identity.task_id,
            plan_id=current_identity.plan_id,
            robot_id=current_identity.robot_id,
        )
        != current_identity
        or not lease.observed_at <= now < lease.expires_at
        or not inputs.matches_observation(observation)
    ):
        raise ValueError("registered current frame or lease owner mismatch/expired")
    if any(
        c.tolerances.get("calibration_version", observation.calibration_version)
        != observation.calibration_version
        for c in (*requirement.preconditions, *requirement.postconditions)
    ):
        raise ValueError("original calibrated frame differs")
    for sources in (inputs.source_hashes, policy.source_hashes):
        if any(original.source_hashes.get(k) != v for k, v in sources.items()):
            raise ValueError("registered preparation source identity mismatch")
    if (
        policy.to_payload()
        != RegisteredGroundingPolicy.for_original(original, policy.source_hashes).to_payload()
    ):
        raise ValueError("registered preparation fixed safety recipe changed")
    expires = _registered_preparation_deadline(
        original,
        original_step_id=original_step_id,
        observation=observation,
        lease_source=lease,
    )
    if not original.registered_at <= observation.captured_at <= now < expires:
        raise ValueError("registered original/frame deadline expired or future")
    source = requirement.original_step
    step = source.model_copy(
        update={
            "parameters": _resolved_parameters(source, original, online, inputs, policy),
            "preconditions": [],
            "success_conditions": [],
        },
        deep=True,
    )
    return RegisteredPreparedStepBinding(
        {
            **RegisteredPreparedStepBinding._constants,
            "original_plan_hash": original.digest(),
            "original_requirements": requirement.to_payload(),
            "current_identity": current_identity.to_payload(),
            "owner_revision": owner_revision,
            "state_generation": state_generation,
            "lease_source_hash": lease.digest(),
            "source_checkpoint_hash": checkpoint_digest(cp),
            "observation_id": observation.observation_id,
            "observation_checksum_sha256": observation.checksum_sha256,
            "calibration_version": observation.calibration_version,
            "plan_version": contract.plan_version,
            "command_seq": contract.command_seq,
            "grounding_policy_hash": policy.digest(),
            "grounding_inputs_hash": inputs.digest(),
            "grounding_source_hashes": {
                **inputs.source_hashes,
                **policy.source_hashes,
            },
            "grounded_step": step.model_dump(mode="json"),
            "expected_duration_s": requirement.expected_duration_s,
            "created_at": now.isoformat(),
            "valid_until": expires.isoformat(),
        }
    )


def _current_grounding_context(
    original,
    *,
    original_step_id,
    online,
    source_checkpoint,
    current_identity,
    owner_revision,
    state_generation,
    now,
):
    """共用原始身份、检查点和帧校验，不决定几何依据或执行权限。"""
    local = type(original) is LocalVisualOriginalPlan
    original = (
        LocalVisualOriginalPlan.from_payload(original.to_payload())
        if local
        else freeze_original_visual_plan(**original.freeze_inputs())
    )
    now = _aware(now)
    if current_identity != original.identity:
        raise ValueError("foreign job/epoch/robot owner identity")
    _counter(owner_revision)
    _counter(state_generation)
    _counter(online.plan_version)
    _counter(online.command_seq)
    cp = ExecutionCheckpoint.model_validate_json(
        _model_json(source_checkpoint, ExecutionCheckpoint)
    )
    cp_hash = checkpoint_digest(cp)
    if not _aware(cp.created_at) <= _aware(cp.updated_at) or (
        not local and _aware(cp.updated_at) > now
    ):
        raise ValueError("current checkpoint timestamp is future or reversed")
    contract = original.contract
    observation = RGBDObservation.model_validate_json(
        _model_json(online.observation, RGBDObservation)
    )
    _model_json(online.robot_state, type(online.robot_state))
    if (
        cp.checkpoint_hash != cp_hash
        or online.context_hash != cp_hash
        or cp.task_id != contract.task_id
        or cp.plan_id != current_identity.plan_id
        or cp.robot_id != current_identity.robot_id
        or (cp.plan_version, cp.command_seq) != (contract.plan_version, contract.command_seq)
        or (online.plan_version, online.command_seq)
        != (contract.plan_version, contract.command_seq)
        or observation.episode_id != current_identity.episode_id
    ):
        raise ValueError("current checkpoint/version/episode/context mismatch")
    ids = [s.step_id for s in contract.steps]
    completed = cp.completed_step_ids
    if (
        ids[: len(completed)] != completed
        or cp.pending_step_ids != ids[len(completed) :]
        or cp.current_step_index != len(completed)
        or not cp.pending_step_ids
        or cp.current_step_id != cp.pending_step_ids[0]
        or original_step_id != cp.current_step_id
        or cp.execution_state in {"COMPLETED", "SAFETY_STOPPED"}
    ):
        raise ValueError("current pending cursor or completed effects mismatch")
    requirement = original.requirements[original_step_id]
    return original, now, cp, contract, observation, requirement, local


def bind_step_grounding(
    original: VisualOriginalPlan,
    *,
    original_step_id: str,
    grounded_step: TaskStep,
    online: OnlineEvidenceSnapshot,
    source_checkpoint: ExecutionCheckpoint,
    current_identity: VisualOwnerIdentity,
    owner_revision: int,
    state_generation: int,
    grounding_inputs: GroundingFrameInputs,
    grounding_policy: DeterministicGroundingPolicy,
    now: datetime,
    required_duration_s: float | None = None,
    duration_check: GroundingDurationCheck | None = None,
) -> StepGroundingBinding:
    if (
        type(grounding_inputs) is not GroundingFrameInputs
        or type(grounding_policy) is not DeterministicGroundingPolicy
    ):
        raise TypeError("exact legacy grounding input and policy family required")
    original, now, cp, contract, observation, requirement, local = _current_grounding_context(
        original,
        original_step_id=original_step_id,
        online=online,
        source_checkpoint=source_checkpoint,
        current_identity=current_identity,
        owner_revision=owner_revision,
        state_generation=state_generation,
        now=now,
    )
    cp_hash = checkpoint_digest(cp)
    inputs, policy = grounding_inputs, grounding_policy
    if (
        inputs.observation_id != observation.observation_id
        or inputs.observation_checksum_sha256 != observation.checksum_sha256
        or inputs.episode_id != observation.episode_id
        or inputs.calibration_version != observation.calibration_version
    ):
        raise ValueError("grounding frame/checksum/calibration binding mismatch")
    if any(
        c.tolerances.get("calibration_version", observation.calibration_version)
        != observation.calibration_version
        for c in (*requirement.preconditions, *requirement.postconditions)
    ):
        raise ValueError("registered canonical calibration differs from current frame")
    for sources in (inputs.source_hashes, policy.source_hashes):
        if any(original.source_hashes.get(k) != v for k, v in sources.items()):
            raise ValueError("deterministic grounding source identity mismatch")
    if (
        policy.tcp_velocity > contract.safety_constraints.max_tcp_velocity
        or policy.minimum_height_m < contract.safety_constraints.minimum_safe_height
    ):
        raise ValueError("grounding cannot relax original safety policy")
    stored = _model_json(grounded_step, TaskStep)
    step, expected = TaskStep.model_validate_json(stored), requirement.original_step
    if (
        step.step_id != expected.step_id
        or step.skill != expected.skill
        or step.expected_duration_ms != expected.expected_duration_ms
        or step.timeout_ms != expected.timeout_ms
        or step.retry_limit != expected.retry_limit
        or step.preconditions
        or step.success_conditions
        or step.parameters != _resolved_parameters(expected, original, online, inputs, policy)
    ):
        raise ValueError("grounded view changed original policy or deterministic parameters")
    max_ages = [
        _positive(c.tolerances.get("max_age_s", requirement.ordinary_ttl_s))
        for c in (*requirement.preconditions, *requirement.postconditions)
    ]
    if not local:
        expires = min(
            original.effective_deadline_at,
            observation.captured_at + timedelta(seconds=min(requirement.ordinary_ttl_s, *max_ages)),
        )
        if not original.registered_at <= observation.captured_at <= now < expires:
            raise ValueError("original absolute/frame deadline expired or future")
    duration = (
        requirement.expected_duration_s
        if required_duration_s is None
        else _positive(required_duration_s)
    )
    if duration < max(
        requirement.expected_duration_s, max(step.expected_duration_ms, step.timeout_ms) / 1000
    ):
        raise ValueError("duration cannot understate checked original horizon")
    if duration > requirement.expected_duration_s:
        check = duration_check
        if (
            not isinstance(check, GroundingDurationCheck)
            or check._grounded_step_json != stored
            or check.observation_id != observation.observation_id
            or check.observation_checksum_sha256 != observation.checksum_sha256
            or check.original_plan_hash != original.digest()
            or check.grounding_policy_hash != policy.digest()
            or check.expected_duration_s != duration
            or not observation.captured_at <= check.checked_at <= now
            or any(original.source_hashes.get(k) != v for k, v in check.source_hashes.items())
        ):
            raise ValueError("longer duration requires fresh exact source calculation binding")
    calculation = duration_check if duration > requirement.expected_duration_s else None
    bound_sources = {**policy.source_hashes, **grounding_inputs.source_hashes}
    if calculation is not None:
        bound_sources.update(calculation.source_hashes)
    if local:
        import threading

        from cloud_edge_robot_arm.vision.operational_windows import (
            _LOCAL_ORIGINALS,
            _LOCAL_RUNTIMES,
            _OWNERS,
            OperationalWindowOwner,
        )
        from cloud_edge_robot_arm.vision.operational_windows import (
            _json as _window_json,
        )
        from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime

        desired = _window_json(original.local_time.to_payload())
        candidates = [
            (owner, runtime)
            for owner, runtime in tuple(_LOCAL_RUNTIMES.items())
            if _LOCAL_ORIGINALS.get(owner) == desired
        ]
        if len(candidates) != 1:
            raise ValueError("grounding requires the unique original private runtime")
        owner, runtime = candidates[0]
        if (
            type(owner) is not OperationalWindowOwner
            or type(runtime) is not VisualWorkerRuntime
            or runtime._operational_owner is not owner
            or owner._closed
            or _LOCAL_RUNTIMES.get(owner) is not runtime
            or _LOCAL_ORIGINALS.get(owner) != desired
        ):
            raise ValueError("grounding selected original owner/runtime registry changed")
        startup = owner._startup
        worker = startup.worker
        if (
            _OWNERS.get(worker) is not owner
            or startup.mode != "LOCAL_TEMPORAL_PUBLICATION_V1"
            or startup.thread_id != threading.get_ident()
            or (startup.job_id, startup.run_id, startup.attempt, startup.lease_id, worker.worker_id)
            != (
                current_identity.job_id,
                current_identity.run_id,
                current_identity.attempt,
                current_identity.lease_id,
                current_identity.worker_id,
            )
            or worker.repository is not startup.repository
            or runtime.source.job_repository is not startup.repository
            or (
                runtime.source.job_id,
                runtime.source.run_id,
                runtime.source.worker_id,
                runtime.source.lease_id,
            )
            != (startup.job_id, startup.run_id, worker.worker_id, startup.lease_id)
            or runtime.role_binding is not startup.binding
            or worker.visual_role_binding is not startup.binding
            or runtime._local_session is not worker._operational_lease_session
            or _window_json(owner._local_original) != desired
            or _window_json(runtime._local_original) != desired
            or dict(original.source_hashes) != dict(runtime.source.source_hashes)
        ):
            raise ValueError("grounding selected original startup/source/thread differs")
        owner._check_app_live()
        selected_original = runtime.original
        if (
            type(selected_original) is not LocalVisualOriginalPlan
            or selected_original.identity != current_identity
            or selected_original.identity != original.identity
            or selected_original.digest() != original.digest()
            or _window_json(selected_original.local_time.to_payload()) != desired
            or dict(selected_original.source_hashes) != dict(original.source_hashes)
        ):
            raise ValueError("grounding selected durable original source differs")
        return runtime._local_bind_grounding(
            {
                "binding_scope": "SOURCE_BINDING_ONLY",
                "original_plan_hash": original.digest(),
                "current_identity": current_identity.to_payload(),
                "original_requirements": requirement.to_payload(),
                "owner_revision": owner_revision,
                "state_generation": state_generation,
                "source_checkpoint_hash": cp_hash,
                "observation_id": observation.observation_id,
                "observation_checksum_sha256": observation.checksum_sha256,
                "calibration_version": observation.calibration_version or "",
                "plan_version": contract.plan_version,
                "command_seq": contract.command_seq,
                "grounding_policy_hash": policy.digest(),
                "grounding_inputs_hash": grounding_inputs.digest(),
                "duration_check_hash": calculation.digest() if calculation is not None else None,
                "grounding_source_hashes": bound_sources,
                "grounded_step": json.loads(stored),
                "expected_duration_s": duration,
            },
            observation,
        )
    return StepGroundingBinding(
        original.digest(),
        current_identity,
        requirement,
        owner_revision,
        state_generation,
        cp_hash,
        observation.observation_id,
        observation.checksum_sha256,
        observation.calibration_version or "",
        contract.plan_version,
        contract.command_seq,
        policy.digest(),
        grounding_inputs.digest(),
        calculation.digest() if calculation is not None else None,
        MappingProxyType(bound_sources),
        stored,
        duration,
        now,
        expires,
    )


def _validate_registered_region_evidence_v2(evidence, frame):
    """校验独立参考与当前帧的结构关联，不将序列化声明认证为真实观测。"""
    keys = {
        "schema_version",
        "policy_id",
        "depth_policy",
        "status",
        "reference_observation_id",
        "reference_observation_checksum_sha256",
        "reference_captured_at",
        "reference_region_mask_sha256",
        "reference_region_depth_sha256",
        "reference_camera_sha256",
        "current_observation_id",
        "current_observation_checksum_sha256",
        "current_visible_mask_sha256",
        "current_missing_mask_sha256",
        "region_pixels",
        "visible_pixels",
        "missing_pixels",
        "destination_world_m",
        "geometric_error_bound_m",
        "placement_clearance",
    }
    nominal = (
        type(evidence) is dict
        and evidence.get("policy_id") == "registered-self-occlusion-nominal-v1"
    )
    if nominal:
        keys |= {
            "nominal_policy",
            "primitive_sha256",
            "object_geometry_sha256",
            "predicted_depth_sha256",
            "predicted_foreground_mask_sha256",
            "maximum_visible_residual_m",
            "maximum_model_residual_m",
            "missing_boundary_pixels",
            "visible_corners",
            "visible_sides",
        }
    if type(evidence) is not dict or set(evidence) != keys:
        raise ValueError("complete v2 reference/current region evidence required")
    expected = {
        "schema_version": "registered.region.reference-evidence.v2",
        "policy_id": "fixed-reference-internal-foreground-v2",
        "depth_policy": "EXACT_VISIBLE_REFERENCE_STRICT_POSITIVE_FOREGROUND",
        "geometric_error_bound_m": None,
        "placement_clearance": "UNKNOWN",
    }
    if nominal:
        from cloud_edge_robot_arm.research.native_collection_grounding import (
            registered_nominal_region_policy_v1,
        )

        policy = registered_nominal_region_policy_v1(frame["source_hashes"])
        if (
            type(evidence["nominal_policy"]) is not dict
            or set(evidence["nominal_policy"]) != set(policy)
            or any(
                type(evidence["nominal_policy"][k]) is not type(v)
                or evidence["nominal_policy"][k] != v
                for k, v in policy.items()
            )
        ):
            raise ValueError("source-bound nominal policy changed")
        expected.update(
            policy_id="registered-self-occlusion-nominal-v1",
            depth_policy="ALL_PIXELS_NOMINAL_REGISTERED_FIRST_HIT",
        )
        for key in (
            "primitive_sha256",
            "object_geometry_sha256",
            "predicted_depth_sha256",
            "predicted_foreground_mask_sha256",
        ):
            _sha(evidence[key])
        for key, maximum in (
            ("maximum_visible_residual_m", 0.010),
            ("maximum_model_residual_m", 0.010),
        ):
            value = evidence[key]
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 <= value <= maximum
            ):
                raise ValueError("nominal residual outside experiment policy")
        if (
            type(evidence["missing_boundary_pixels"]) is not int
            or not 0 <= evidence["missing_boundary_pixels"] <= evidence["missing_pixels"]
            or type(evidence["visible_corners"]) is not int
            or not 3 <= evidence["visible_corners"] <= 4
            or type(evidence["visible_sides"]) is not list
            or len(evidence["visible_sides"]) != 4
            or any(type(v) is not bool or not v for v in evidence["visible_sides"])
        ):
            raise ValueError("nominal reference anchors invalid")
    if any(type(evidence[k]) is not type(v) or evidence[k] != v for k, v in expected.items()):
        raise ValueError("v2 region evidence cannot confer measured clearance or accuracy")
    for key in (
        "reference_observation_checksum_sha256",
        "reference_region_mask_sha256",
        "reference_region_depth_sha256",
        "reference_camera_sha256",
        "current_observation_checksum_sha256",
        "current_visible_mask_sha256",
        "current_missing_mask_sha256",
    ):
        _sha(evidence[key])
    for key in ("reference_observation_id", "current_observation_id", "reference_captured_at"):
        if type(evidence[key]) is not str or not evidence[key]:
            raise ValueError("v2 region reference identity/time required")
    if (
        evidence["current_observation_id"] != frame["observation_id"]
        or evidence["current_observation_checksum_sha256"] != frame["observation_checksum_sha256"]
        or evidence["destination_world_m"] != frame["destination_world_m"]
        or evidence["reference_camera_sha256"]
        != _digest({**frame["camera"], "calibration_version": frame["calibration_version"]})
        or _aware(datetime.fromisoformat(evidence["reference_captured_at"]))
        > _aware(datetime.fromisoformat(frame["captured_at"]))
    ):
        raise ValueError("v2 region reference/current frame crosslink mismatch")
    if evidence["reference_observation_id"] == frame["observation_id"] and (
        evidence["reference_observation_checksum_sha256"] != frame["observation_checksum_sha256"]
    ):
        raise ValueError("v2 same-frame reference checksum mismatch")
    _registered_vector(evidence["destination_world_m"], 3)
    total, visible, missing = (
        evidence[n] for n in ("region_pixels", "visible_pixels", "missing_pixels")
    )
    if (
        any(type(n) is not int for n in (total, visible, missing))
        or total < 8
        or visible < 1
        or missing < 0
        or total != visible + missing
        or total > frame["camera"]["width"] * frame["camera"]["height"]
        or evidence["status"]
        != (
            ("FULL_NOMINAL" if missing == 0 else "PARTIAL_REGISTERED_NOMINAL")
            if nominal
            else ("FULL" if missing == 0 else "PARTIAL_FOREGROUND_SUPPORTED")
        )
    ):
        raise ValueError("v2 region evidence pixel classification invalid")


class RegisteredGroundingFrameInputsV2(_RegisteredPayload):
    """注册刚体模型与当前区域的准备输入，不冒充完整表面测量。"""

    __slots__ = ()
    _constants = {
        **_REGISTERED_FLAGS,
        "schema_version": "registered.grounding.inputs.v2",
        "condition_registry_version": "registered-model-condition-v2",
        "support_basis": "REGISTERED_NOMINAL",
        "region_basis": "FIXED_REFERENCE_CURRENT_RGBD_UNCALIBRATED",
        "wrapper_freshness": "CHECKED",
        "wrapper_asset_validation": "VERIFIED_LOCAL_BYTES",
        "source_validation": "LOCAL_BYTE_CONSISTENCY_ONLY",
    }
    _keys = {
        "observation_id",
        "observation_checksum_sha256",
        "captured_at",
        "scene_id",
        "object_id",
        "target_region_id",
        "episode_id",
        "calibration_version",
        "camera",
        "source_hashes",
        "source_generation",
        "asset_path",
        "asset_sha256",
        "marker_family_id",
        "registration_sha256",
        "marker_registration_hash",
        "marker_estimate_sha256",
        "preview_sha256",
        "grasp_tcp_world_m",
        "object_center_world_m",
        "rotation_object_to_world",
        "destination_world_m",
        "nominal_support_height_m",
        "region_evidence",
    }

    @classmethod
    def _validate(cls, payload):
        p = _registered_object(payload, cls._keys, cls._constants)
        for name in (
            "observation_id",
            "scene_id",
            "episode_id",
            "calibration_version",
            "object_id",
            "target_region_id",
            "asset_path",
            "marker_family_id",
        ):
            if type(p[name]) is not str or not p[name]:
                raise ValueError("explicit registered frame/asset identity required")
        for name in (
            "observation_checksum_sha256",
            "source_generation",
            "asset_sha256",
            "registration_sha256",
            "marker_registration_hash",
            "marker_estimate_sha256",
            "preview_sha256",
        ):
            _sha(p[name])
        _aware(datetime.fromisoformat(p["captured_at"]))
        sources = _sources(p["source_hashes"])
        if (
            _digest(sources) != p["source_generation"]
            or sources.get(p["asset_path"]) != p["asset_sha256"]
        ):
            raise ValueError("registered source/asset generation mismatch")
        camera = p["camera"]
        if type(camera) is not dict or set(camera) != {
            "source",
            "width",
            "height",
            "intrinsics",
            "camera_to_world",
        }:
            raise ValueError("complete registered camera descriptor required")
        if (
            type(camera["source"]) is not str
            or not camera["source"]
            or any(type(camera[n]) is not int or camera[n] < 1 for n in ("width", "height"))
        ):
            raise ValueError("strict registered camera identity required")
        _registered_vector(camera["intrinsics"], 4)
        _registered_vector(camera["camera_to_world"], 16)
        for name in ("grasp_tcp_world_m", "object_center_world_m", "destination_world_m"):
            _registered_vector(p[name], 3)
        r = p["rotation_object_to_world"]
        _registered_vector(r, 9)
        if any(
            abs(sum(r[3 * i + k] * r[3 * j + k] for k in range(3)) - (i == j)) > 1e-6
            for i in range(3)
            for j in range(3)
        ):
            raise ValueError("registered rotation must be orthonormal")
        determinant = (
            r[0] * (r[4] * r[8] - r[5] * r[7])
            - r[1] * (r[3] * r[8] - r[5] * r[6])
            + r[2] * (r[3] * r[7] - r[4] * r[6])
        )
        if abs(determinant - 1) > 1e-6:
            raise ValueError("registered rotation must be proper")
        value = p["nominal_support_height_m"]
        if type(value) not in {int, float} or not math.isfinite(value):
            raise ValueError("finite registered nominal support required")
        _validate_registered_region_evidence_v2(p["region_evidence"], p)
        return p

    @classmethod
    def from_preview(cls, preview, observation, registration):
        """仅从精确当前准备结果构建输入，并检查帧、注册和区域关联。"""
        from dataclasses import asdict

        from cloud_edge_robot_arm.research.native_collection_grounding import (
            RegisteredCollectionGroundingPreviewV2,
        )
        from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration

        if (
            type(preview) is not RegisteredCollectionGroundingPreviewV2
            or type(observation) is not RGBDObservation
            or type(registration) is not NativeGeometryRegistration
        ):
            raise TypeError("exact current registered preview, frame and registration required")
        obs = RGBDObservation.model_validate_json(_model_json(observation, RGBDObservation))
        reg = NativeGeometryRegistration(registration.to_payload())
        registration_sha256 = _digest(reg.to_payload())
        p, track = preview.to_payload(), preview.track
        geometry = track.geometry
        if (
            p["schema_version"] != "native.collection.registered-preview.v2"
            or p["region_basis"] != cls._constants["region_basis"]
            or preview.status != "DERIVED"
            or track.status != "DERIVED"
            or geometry is None
            or geometry.status != "DERIVED"
            or track.wrapper_freshness != "CHECKED"
            or track.wrapper_asset_validation != "VERIFIED_LOCAL_BYTES"
            or track.source_validation != "LOCAL_BYTE_CONSISTENCY_ONLY"
            or any(
                type(p.get(k)) is not type(v) or p.get(k) != v for k, v in _REGISTERED_FLAGS.items()
            )
            or preview.registration_sha256 != registration_sha256
            or track.registration_sha256 != registration_sha256
            or preview.source_sha256 != track.source_sha256
            or preview.grasp_tcp_world_m != geometry.grasp_tcp_world_m
            or preview.object_center_world_m != geometry.object_center_world_m
            or preview.rotation_object_to_world != geometry.rotation_object_to_world
            or preview.destination_observation_id != obs.observation_id
            or preview.destination_observation_checksum_sha256 != obs.checksum_sha256
        ):
            raise ValueError("current registered preview unavailable or relabelled")
        camera = {
            n: getattr(obs, n)
            for n in ("source", "width", "height", "intrinsics", "camera_to_world")
        }
        if (
            any(
                getattr(track, n) != getattr(obs, n)
                for n in (
                    "observation_id",
                    "captured_at",
                    "scene_id",
                    "episode_id",
                    "calibration_version",
                )
            )
            or track.observation_checksum_sha256 != obs.checksum_sha256
            or any(_plain(getattr(track, n)) != _plain(v) for n, v in camera.items())
            or any(_plain(v) != reg.to_payload()["camera"][n] for n, v in camera.items())
            or geometry.observation_id != obs.observation_id
            or geometry.observation_checksum_sha256 != obs.checksum_sha256
            or geometry.object_id != reg.to_payload()["object_id"]
            or geometry.marker_estimate is None
            or geometry.marker_estimate.status != "OBSERVED"
            or geometry.marker_estimate.observed_marker_ids
            != (reg.to_payload()["pose_marker"]["marker_id"],)
            or geometry.marker_estimate.registration_hash != track.marker_registration_hash
        ):
            raise ValueError("registered preview frame/camera/marker cross-link mismatch")
        return cls(
            {
                **cls._constants,
                "observation_id": obs.observation_id,
                "observation_checksum_sha256": obs.checksum_sha256,
                "captured_at": obs.captured_at.isoformat(),
                "scene_id": obs.scene_id,
                "object_id": reg.to_payload()["object_id"],
                "target_region_id": reg.to_payload()["target_region_id"],
                "episode_id": obs.episode_id,
                "calibration_version": obs.calibration_version,
                "camera": _plain(camera),
                "source_hashes": dict(track.source_hashes),
                "source_generation": track.source_sha256,
                "asset_path": track.asset_path,
                "asset_sha256": track.asset_sha256,
                "marker_family_id": track.marker_family_id,
                "registration_sha256": registration_sha256,
                "marker_registration_hash": track.marker_registration_hash,
                "marker_estimate_sha256": _digest(asdict(geometry.marker_estimate)),
                "preview_sha256": preview.digest(),
                "grasp_tcp_world_m": list(preview.grasp_tcp_world_m),
                "object_center_world_m": list(preview.object_center_world_m),
                "rotation_object_to_world": list(preview.rotation_object_to_world),
                "destination_world_m": list(preview.destination_world_m),
                "nominal_support_height_m": reg.to_payload()["support_height_m"],
                "region_evidence": p["region_evidence"],
            }
        )

    def matches_observation(self, observation):
        """比对完整帧与相机身份；不把散列一致解释为来源认证。"""
        p = self.to_payload()
        return (
            type(observation) is RGBDObservation
            and all(
                p[n] == _plain(getattr(observation, n))
                for n in (
                    "observation_id",
                    "captured_at",
                    "episode_id",
                    "scene_id",
                    "calibration_version",
                )
            )
            and p["observation_checksum_sha256"] == observation.checksum_sha256
            and all(p["camera"][n] == _plain(getattr(observation, n)) for n in p["camera"])
        )

    @property
    def source_hashes(self):
        return _sources(self.to_payload()["source_hashes"])

    @property
    def grasp_tcp(self):
        return dict(zip("xyz", self.to_payload()["grasp_tcp_world_m"], strict=True))

    @property
    def destination(self):
        return dict(zip("xyz", self.to_payload()["destination_world_m"], strict=True))

    @property
    def support_height_m(self):
        return self.to_payload()["nominal_support_height_m"]


class RegisteredGroundingPolicyV2(_RegisteredPayload):
    """固定版本的准备数值配方，不配置控制器或授予动作权限。"""

    __slots__ = ()
    _constants = {
        "policy_id": "registered-model-grounding-prepare-v2",
        "version": "registered-model-grounding-prepare-v2",
    }

    @classmethod
    def _validate(cls, payload):
        extra = {"region_policy"} if type(payload) is dict and "region_policy" in payload else set()
        p = _registered_object(
            payload,
            {"source_hashes", "tcp_velocity", "acceleration", "clearance_m", "minimum_height_m"}
            | extra,
            cls._constants,
        )
        _sources(p["source_hashes"])
        for n in ("tcp_velocity", "acceleration", "clearance_m", "minimum_height_m"):
            _positive(p[n])
        if extra:
            from cloud_edge_robot_arm.research.native_collection_grounding import (
                registered_nominal_region_policy_v1,
            )

            expected = registered_nominal_region_policy_v1(p["source_hashes"])
            if (
                type(p["region_policy"]) is not dict
                or set(p["region_policy"]) != set(expected)
                or any(
                    type(p["region_policy"][k]) is not type(v) or p["region_policy"][k] != v
                    for k, v in expected.items()
                )
            ):
                raise ValueError("exact nominal region policy required")
        return p

    @classmethod
    def for_original(cls, original, source_hashes, *, region_policy=None):
        """按原始安全上限生成固定准备配方，保留最小高度。"""
        if type(original) is not VisualOriginalPlan:
            raise TypeError("UTC original source plan required; no local runtime authority")
        for requirement in original.requirements.values():
            if "registered_region_model_available" not in {
                c.name for c in requirement.preconditions
            } or any(
                c.tolerances.get("condition_registry_version") != "registered-model-condition-v2"
                for c in (*requirement.preconditions, *requirement.postconditions)
            ):
                raise ValueError("explicit v2 original condition recipe required")
        safety = original.contract.safety_constraints
        return cls(
            {
                **cls._constants,
                **({"region_policy": region_policy} if region_policy is not None else {}),
                "source_hashes": dict(_sources(source_hashes)),
                "tcp_velocity": min(0.15, safety.max_tcp_velocity),
                "acceleration": 0.5,
                "clearance_m": 0.10,
                "minimum_height_m": max(0.16, safety.minimum_safe_height),
            }
        )

    @property
    def source_hashes(self):
        return _sources(self.to_payload()["source_hashes"])

    @property
    def tcp_velocity(self):
        return self.to_payload()["tcp_velocity"]

    @property
    def acceleration(self):
        return self.to_payload()["acceleration"]

    @property
    def clearance_m(self):
        return self.to_payload()["clearance_m"]

    @property
    def minimum_height_m(self):
        return self.to_payload()["minimum_height_m"]


class RegisteredPreparedStepBindingV2(_RegisteredPayload):
    """保存原始约束和候选步骤的纯准备绑定，旧执行绑定不接受此类型。"""

    __slots__ = ()
    _constants = {
        **_REGISTERED_FLAGS,
        "schema_version": "registered.grounding.prepared-step.v2",
        "binding_scope": "REGISTERED_MODEL_PREPARATION_ONLY",
    }
    _keys = {
        "original_plan_hash",
        "original_requirements",
        "current_identity",
        "owner_revision",
        "state_generation",
        "lease_source_hash",
        "source_checkpoint_hash",
        "observation_id",
        "observation_checksum_sha256",
        "calibration_version",
        "plan_version",
        "command_seq",
        "grounding_policy_hash",
        "grounding_inputs_hash",
        "grounding_source_hashes",
        "grounded_step",
        "expected_duration_s",
        "created_at",
        "valid_until",
    }

    @classmethod
    def _validate(cls, payload):
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            requirement_from_payload,
        )

        p = _registered_object(payload, cls._keys, cls._constants)
        identity = VisualOwnerIdentity(**p["current_identity"])
        requirement = requirement_from_payload(p["original_requirements"])
        _registered_requirement_family(requirement, v2=True)
        step = _from_json(_json(p["grounded_step"]), TaskStep)
        source = requirement.original_step
        if (
            step.step_id != source.step_id
            or step.skill != source.skill
            or step.timeout_ms != source.timeout_ms
            or step.retry_limit != source.retry_limit
            or step.expected_duration_ms != source.expected_duration_ms
            or step.preconditions
            or step.success_conditions
        ):
            raise ValueError("prepared step cannot replace original action policy")
        for n in ("owner_revision", "state_generation", "plan_version", "command_seq"):
            _counter(p[n])
        for n in (
            "original_plan_hash",
            "lease_source_hash",
            "source_checkpoint_hash",
            "observation_checksum_sha256",
            "grounding_policy_hash",
            "grounding_inputs_hash",
        ):
            _sha(p[n])
        _sources(p["grounding_source_hashes"])
        if (
            not p["observation_id"]
            or not p["calibration_version"]
            or identity.episode_id == ""
            or _positive(p["expected_duration_s"]) != requirement.expected_duration_s
            or _aware(datetime.fromisoformat(p["created_at"]))
            >= _aware(datetime.fromisoformat(p["valid_until"]))
        ):
            raise ValueError("prepared binding duration/frame/time invalid")
        return p

    @property
    def grounded_step(self):
        return TaskStep.model_validate(self.to_payload()["grounded_step"])

    @property
    def valid_until(self):
        return datetime.fromisoformat(self.to_payload()["valid_until"])


class RegisteredCollectionStepBindingV2(_RegisteredPayload):
    """注册模型采集来源绑定；不提供普通执行或native权限。"""

    __slots__ = ()
    _constants = {
        "schema_version": "registered.collection.binding.v2",
        "binding_scope": "REGISTERED_MODEL_COLLECTION_SOURCE_ONLY",
        "collection_policy_id": "registered-model-collection-v2",
        "execution_authority": False,
        "ordinary_execution_allowed": False,
        "native_authority": "UNAVAILABLE",
    }

    @classmethod
    def _validate(cls, payload):
        p = _registered_object(payload, {"prepared"}, cls._constants)
        prepared = RegisteredPreparedStepBindingV2.from_payload(p["prepared"])
        if prepared.to_payload() != p["prepared"]:
            raise ValueError("exact registered preparation payload required")
        return p

    @classmethod
    def from_prepared(cls, prepared, *, collection_policy_id):
        """保留内层准备语义；实际采集许可仍由私有应用独立判定。"""
        if type(prepared) is not RegisteredPreparedStepBindingV2:
            raise TypeError("exact registered preparation binding required")
        return cls(
            {
                **cls._constants,
                "collection_policy_id": collection_policy_id,
                "prepared": prepared.to_payload(),
            }
        )

    @property
    def prepared(self):
        return RegisteredPreparedStepBindingV2.from_payload(self.to_payload()["prepared"])

    @property
    def grounded_step(self):
        return self.prepared.grounded_step

    @property
    def valid_until(self):
        return self.prepared.valid_until


def prepare_registered_step_binding_v2(
    original,
    *,
    original_step_id,
    online,
    source_checkpoint,
    current_identity,
    owner_revision,
    state_generation,
    lease_source,
    grounding_inputs,
    grounding_policy,
    now,
):
    """以当前租约和原始检查点准备候选步骤；不创建任何可执行能力。"""
    from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation

    if (
        type(original) is not VisualOriginalPlan
        or type(grounding_inputs) is not RegisteredGroundingFrameInputsV2
        or type(grounding_policy) is not RegisteredGroundingPolicyV2
        or type(lease_source) is not WorkerLeaseObservation
        or type(current_identity) is not VisualOwnerIdentity
        or type(online) is not OnlineEvidenceSnapshot
    ):
        raise TypeError("exact registered preparation source types required")
    original, now, cp, contract, observation, requirement, _ = _current_grounding_context(
        original,
        original_step_id=original_step_id,
        online=online,
        source_checkpoint=source_checkpoint,
        current_identity=current_identity,
        owner_revision=owner_revision,
        state_generation=state_generation,
        now=now,
    )
    inputs = RegisteredGroundingFrameInputsV2.from_payload(grounding_inputs.to_payload())
    policy = RegisteredGroundingPolicyV2.from_payload(grounding_policy.to_payload())
    identities = inputs.to_payload()
    if (
        identities["object_id"] != contract.task_target.object_id
        or identities["target_region_id"] != contract.task_target.target_region_id
    ):
        raise ValueError("registered preparation target identity mismatch")
    lease = WorkerLeaseObservation(**vars(lease_source))
    if (
        lease.identity(
            episode_id=current_identity.episode_id,
            task_id=current_identity.task_id,
            plan_id=current_identity.plan_id,
            robot_id=current_identity.robot_id,
        )
        != current_identity
        or not lease.observed_at <= now < lease.expires_at
        or not inputs.matches_observation(observation)
    ):
        raise ValueError("registered current frame or lease owner mismatch/expired")
    if any(
        c.tolerances.get("calibration_version", observation.calibration_version)
        != observation.calibration_version
        for c in (*requirement.preconditions, *requirement.postconditions)
    ):
        raise ValueError("original calibrated frame differs")
    for sources in (inputs.source_hashes, policy.source_hashes):
        if any(original.source_hashes.get(k) != v for k, v in sources.items()):
            raise ValueError("registered preparation source identity mismatch")
    if (
        policy.to_payload()
        != RegisteredGroundingPolicyV2.for_original(
            original, policy.source_hashes, region_policy=policy.to_payload().get("region_policy")
        ).to_payload()
    ):
        raise ValueError("registered preparation fixed safety recipe changed")
    if inputs.to_payload()["region_evidence"].get("nominal_policy") != policy.to_payload().get(
        "region_policy"
    ):
        raise ValueError("registered input and policy comparison recipe differ")
    expires = _registered_preparation_deadline(
        original,
        original_step_id=original_step_id,
        observation=observation,
        lease_source=lease,
    )
    if not original.registered_at <= observation.captured_at <= now < expires:
        raise ValueError("registered original/frame deadline expired or future")
    source = requirement.original_step
    step = source.model_copy(
        update={
            "parameters": _resolved_parameters(source, original, online, inputs, policy),
            "preconditions": [],
            "success_conditions": [],
        },
        deep=True,
    )
    return RegisteredPreparedStepBindingV2(
        {
            **RegisteredPreparedStepBindingV2._constants,
            "original_plan_hash": original.digest(),
            "original_requirements": requirement.to_payload(),
            "current_identity": current_identity.to_payload(),
            "owner_revision": owner_revision,
            "state_generation": state_generation,
            "lease_source_hash": lease.digest(),
            "source_checkpoint_hash": checkpoint_digest(cp),
            "observation_id": observation.observation_id,
            "observation_checksum_sha256": observation.checksum_sha256,
            "calibration_version": observation.calibration_version,
            "plan_version": contract.plan_version,
            "command_seq": contract.command_seq,
            "grounding_policy_hash": policy.digest(),
            "grounding_inputs_hash": inputs.digest(),
            "grounding_source_hashes": {
                **inputs.source_hashes,
                **policy.source_hashes,
            },
            "grounded_step": step.model_dump(mode="json"),
            "expected_duration_s": requirement.expected_duration_s,
            "created_at": now.isoformat(),
            "valid_until": expires.isoformat(),
        }
    )
