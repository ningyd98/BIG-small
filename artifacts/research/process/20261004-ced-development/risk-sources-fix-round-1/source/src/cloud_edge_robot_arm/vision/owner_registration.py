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
    if not isinstance(condition, ConditionSpec) or condition.name not in (
        _VISUAL_CONDITIONS | _ROBOT_CONDITIONS
    ):
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
        ):
            _sha(getattr(self, name))
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
    original = freeze_original_visual_plan(**original.freeze_inputs())
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
    if not _aware(cp.created_at) <= _aware(cp.updated_at) <= now:
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
        MappingProxyType(dict(policy.source_hashes)),
        stored,
        duration,
        now,
        expires,
    )
