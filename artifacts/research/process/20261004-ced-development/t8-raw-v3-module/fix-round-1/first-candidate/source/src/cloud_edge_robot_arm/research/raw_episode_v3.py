"""Immutable recorded source structure; never clock, owner or execution authority.

No sampling, IO, callbacks, simulator stepping, provider calls or admission flags.
COMPLETE describes the supplied recorded graph, not authenticity or continuous motion.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import struct
import types
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, ClassVar, Literal, Union, cast, get_args, get_origin, get_type_hints

import numpy as np
from PIL import Image

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.contracts import ActionResult, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    ActuatorStepObservation,
    PhysicsStepObservation,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    OriginalActionRequirements,
    StepGroundingBinding,
    VisualOriginalPlan,
    VisualOwnerIdentity,
    _from_json,
)

_MAX_INT = 2**63 - 1
_OWNERS = (
    VisualOwnerIdentity,
    OriginalActionRequirements,
    VisualOriginalPlan,
    StepGroundingBinding,
)
_PURPOSES = {"SETTLE", "WAIT", "VERIFY_ADVANCE", "HOLD", "TERMINATION", "EXECUTOR_ATTEMPT"}


def _integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= _MAX_INT:
        raise ValueError("strict bounded integer required")
    return value


def _number(value: Any) -> float:
    if type(value) not in {int, float}:
        raise ValueError("strict finite number required")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError("numeric floating range exceeded") from error
    if not math.isfinite(result):
        raise ValueError("finite number required")
    return result


def _identifier(value: Any) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", value) is None
        or value.lower() in {"unknown", "none", "placeholder", "robot-unknown"}
    ):
        raise ValueError("explicit nonplaceholder identity required")
    return value


def _sha(value: Any) -> str:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("full SHA256 identity required")
    return value


def _aware(value: Any) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware UTC timestamp required")
    return value.astimezone(UTC)


def _plain(value: Any) -> Any:
    if isinstance(value, _OWNERS):
        return _clone_owner(value, next(t for t in _OWNERS if isinstance(value, t))).to_payload()
    if isinstance(value, _Record):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(cast(Any, value))}
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, Mapping):
        if any(type(k) is not str for k in value):
            raise ValueError("JSON keys require strings")
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if type(value) is int:
        _integer(abs(value))
    elif type(value) is float:
        _number(value)
    elif value is not None and type(value) not in {str, bool}:
        raise ValueError("bounded JSON source data required")
    return value


def _frozen(value: Any) -> Any:
    plain = _plain(value)
    if isinstance(plain, dict):
        return MappingProxyType({k: _frozen(v) for k, v in plain.items()})
    if isinstance(plain, list):
        return tuple(_frozen(v) for v in plain)
    return plain


def _json(value: Any) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _load(stored: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate JSON key")
            result[name] = value
        return result

    if type(stored) is not str:
        raise ValueError("JSON text required")
    value = json.loads(
        stored,
        object_pairs_hook=unique,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f"nonfinite JSON {v}")),
    )
    return _plain(value)


def _sources(value: Mapping[str, str], *, allow_empty: bool = False) -> None:
    if not value and not allow_empty:
        raise ValueError("complete source inventory required")
    for name, digest in value.items():
        if (
            type(name) is not str
            or not name
            or name.startswith("/")
            or ".." in PurePosixPath(name).parts
            or str(PurePosixPath(name)) != name
        ):
            raise ValueError("canonical relative source path required")
        _sha(digest)


def _owner_decode(typ: Any, raw: Any) -> Any:
    if not isinstance(raw, Mapping):
        raise ValueError("complete original source payload required")
    raw = _plain(raw)
    result: OriginalActionRequirements | VisualOriginalPlan | StepGroundingBinding
    if typ is VisualOwnerIdentity:
        return VisualOwnerIdentity(**raw)
    if typ is OriginalActionRequirements:
        keys = {
            "original_step",
            "original_step_hash",
            "preconditions",
            "postconditions",
            "allowed_error_m",
            "sensor_requirements",
            "ordinary_ttl_s",
            "expected_duration_s",
            "timeout_ms",
            "retry_limit",
            "policy_source_hashes",
        }
        if set(raw) != keys:
            raise ValueError("full original action requirements schema required")
        step = _from_json(_json(raw["original_step"]), TaskStep)
        conditions = []
        for key in ("preconditions", "postconditions"):
            conditions.append(tuple(ConditionSpec(**c) for c in raw[key]))
        result = OriginalActionRequirements(
            step,
            conditions[0],
            conditions[1],
            raw["allowed_error_m"],
            raw["sensor_requirements"],
            raw["ordinary_ttl_s"],
            raw["expected_duration_s"],
            raw["policy_source_hashes"],
        )
    elif typ is VisualOriginalPlan:
        keys = {
            "binding_scope",
            "identity",
            "contract",
            "proposal_hash",
            "role_bundle_hash",
            "compiler_source_hashes",
            "source_hashes",
            "requirements",
            "dependencies",
            "task_deadline_at",
            "verification_deadline_at",
            "registered_at",
        }
        if set(raw) != keys or raw["binding_scope"] != "SOURCE_BINDING_ONLY":
            raise ValueError("full original plan schema required")
        contract = _from_json(_json(raw["contract"]), TaskContract)
        result = VisualOriginalPlan(
            _owner_decode(VisualOwnerIdentity, raw["identity"]),
            _json(contract.model_dump(mode="json")),
            raw["proposal_hash"],
            raw["role_bundle_hash"],
            raw["compiler_source_hashes"],
            raw["source_hashes"],
            {
                k: _owner_decode(OriginalActionRequirements, v)
                for k, v in raw["requirements"].items()
            },
            tuple(StepDependency(**v) for v in raw["dependencies"]),
            *(
                datetime.fromisoformat(raw[k])
                for k in ("task_deadline_at", "verification_deadline_at", "registered_at")
            ),
        )
    elif typ is StepGroundingBinding:
        keys = {f.name for f in fields(StepGroundingBinding)} - {"_grounded_step_json"}
        keys |= {"grounded_step", "binding_scope"}
        if set(raw) != keys or raw["binding_scope"] != "SOURCE_BINDING_ONLY":
            raise ValueError("full grounding binding schema required")
        values = {k: raw[k] for k in keys - {"grounded_step", "binding_scope"}}
        values["current_identity"] = _owner_decode(VisualOwnerIdentity, raw["current_identity"])
        values["original_requirements"] = _owner_decode(
            OriginalActionRequirements, raw["original_requirements"]
        )
        values["_grounded_step_json"] = _json(
            _from_json(_json(raw["grounded_step"]), TaskStep).model_dump(mode="json")
        )
        for k in ("created_at", "valid_until"):
            values[k] = datetime.fromisoformat(raw[k])
        result = StepGroundingBinding(**values)
    else:
        raise ValueError("unsupported original source type")
    if _json(result.to_payload()) != _json(raw):
        raise ValueError("original requirement/policy payload changed during validation")
    return result


def _clone_owner(value: Any, typ: Any) -> Any:
    if not isinstance(value, typ):
        raise ValueError("typed concrete owner source required")
    # Read declared fields and reconstruct concrete base types; subclass methods
    # and digest/to_payload overrides cannot determine the copied source.
    if typ is VisualOwnerIdentity:
        return VisualOwnerIdentity(**{f.name: getattr(value, f.name) for f in fields(typ)})
    if typ is OriginalActionRequirements:
        for k in ("allowed_error_m", "ordinary_ttl_s", "expected_duration_s"):
            _number(getattr(value, k))
        for c in (*value.preconditions, *value.postconditions):
            _plain(c.tolerances)
            for key, item in c.tolerances.items():
                if key in {
                    "max_age_s",
                    "tolerance_m",
                    "minimum_safe_height",
                    "maximum_velocity",
                    "min_height_m",
                }:
                    _number(item)
        step = _from_json(_json(_load(value._original_step_json)), TaskStep)
        return OriginalActionRequirements(
            step,
            value.preconditions,
            value.postconditions,
            value.allowed_error_m,
            value.sensor_requirements,
            value.ordinary_ttl_s,
            value.expected_duration_s,
            value.policy_source_hashes,
        )
    values = {f.name: getattr(value, f.name) for f in fields(typ)}
    if typ is VisualOriginalPlan:
        values["identity"] = _clone_owner(values["identity"], VisualOwnerIdentity)
        values["requirements"] = {
            k: _clone_owner(v, OriginalActionRequirements)
            for k, v in values["requirements"].items()
        }
        values["_contract_json"] = _json(
            _from_json(_json(_load(values["_contract_json"])), TaskContract).model_dump(mode="json")
        )
    else:
        values["current_identity"] = _clone_owner(values["current_identity"], VisualOwnerIdentity)
        values["original_requirements"] = _clone_owner(
            values["original_requirements"], OriginalActionRequirements
        )
        values["_grounded_step_json"] = _json(
            _from_json(_json(_load(values["_grounded_step_json"])), TaskStep).model_dump(
                mode="json"
            )
        )
    _plain(
        {
            k: v
            for k, v in values.items()
            if k
            not in {
                "identity",
                "current_identity",
                "requirements",
                "original_requirements",
                "dependencies",
            }
        }
    )
    return typ(**values)


def _checked(value: Any, typ: Any, *, decode: bool = False) -> Any:
    origin, args = get_origin(typ), get_args(typ)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        return _checked(value, next(t for t in args if t is not type(None)), decode=decode)
    if origin is Literal:
        if type(value) is not str or value not in args:
            raise ValueError("declared source enum required")
        return value
    if typ is Any:
        return _frozen(value)
    if typ is datetime:
        return _aware(datetime.fromisoformat(value) if decode and type(value) is str else value)
    if typ is str:
        if type(value) is not str:
            raise ValueError("strict string required")
        return value
    if typ is int:
        return _integer(value)
    if typ is float:
        return _number(value)
    if typ is bool:
        if type(value) is not bool:
            raise ValueError("strict bool required")
        return value
    if origin is Mapping:
        if not isinstance(value, Mapping):
            raise ValueError("explicit source mapping required")
        return MappingProxyType(
            {
                _checked(k, args[0], decode=decode): _checked(v, args[1], decode=decode)
                for k, v in value.items()
            }
        )
    if origin is tuple:
        if not isinstance(value, (tuple, list)):
            raise ValueError("explicit record sequence required")
        if len(args) != 2 or args[1] is not Ellipsis:
            raise ValueError("unsupported sequence shape")
        return tuple(_checked(v, args[0], decode=decode) for v in value)
    if typ in _OWNERS:
        return _owner_decode(typ, value) if decode else _clone_owner(value, typ)
    if isinstance(typ, type) and is_dataclass(typ):
        if decode:
            if typ is RawEpisodeEnvelopeV3:
                if (
                    not isinstance(value, Mapping)
                    or value.get("schema_version") != "rgbd.raw-episode.v3"
                    or value.get("scope") != "SOURCE_CONSISTENCY_ONLY"
                ):
                    raise ValueError("fixed source-consistency schema required")
                value = {k: v for k, v in value.items() if k not in {"schema_version", "scope"}}
            if not isinstance(value, Mapping) or set(value) != {f.name for f in fields(typ)}:
                raise ValueError("full exact record schema required")
            annotations = _annotations(typ)
            return typ(
                **{
                    f.name: _checked(value[f.name], annotations[f.name], decode=True)
                    for f in fields(typ)
                }
            )
        if not isinstance(value, typ):
            raise ValueError("typed record required")
        return typ(**{f.name: getattr(value, f.name) for f in fields(typ)})
    raise ValueError("undeclared source type")


@cache
def _annotations(typ: type[Any]) -> Mapping[str, Any]:
    return get_type_hints(typ)


class _Record:
    def __post_init__(self) -> None:
        annotations = _annotations(cast(Any, type(self)))
        for f in fields(cast(Any, self)):
            object.__setattr__(self, f.name, _checked(getattr(self, f.name), annotations[f.name]))
        if hasattr(self, "record_seq"):
            _integer(self.record_seq, 1)

    def to_payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], _plain(self))

    def digest(self) -> str:
        return _digest(self)

    @classmethod
    def from_json(cls, stored: str) -> Any:
        return _checked(_load(stored), cls, decode=True)


@dataclass(frozen=True)
class RawEpisodeIdentityV3(_Record):
    attempt_id: str
    assignment_id: str
    assignment_hash: str
    episode_id: str
    source_kind: Literal["SOFTWARE_ONLY", "ONLINE_CED", "GROUND_TRUTH_TEACHER"]
    owner_identity: VisualOwnerIdentity
    scene_hash: str
    asset_hash: str
    config_hash: str
    role_bundle_hash: str | None
    model_snapshot_hash: str | None
    source_hashes: Mapping[str, str]
    clock_domain_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        for k in ("attempt_id", "assignment_id", "episode_id", "clock_domain_id"):
            _identifier(getattr(self, k))
        for k in ("assignment_hash", "scene_hash", "asset_hash", "config_hash"):
            _sha(getattr(self, k))
        for k in ("role_bundle_hash", "model_snapshot_hash"):
            if getattr(self, k) is not None:
                _sha(getattr(self, k))
            elif self.source_kind == "ONLINE_CED":
                raise ValueError("online CED complete role/model identity required")
        if self.owner_identity.episode_id != self.episode_id:
            raise ValueError("owner/episode identity differs")
        _sources(self.source_hashes)


@dataclass(frozen=True)
class ClockDescriptorV3(_Record):
    clock_domain_id: str
    owner_epoch: str
    monotonic_implementation: str
    utc_implementation: str
    monotonic_resolution_ns: int
    utc_resolution_ns: int
    utc_uncertainty_ns: int | None
    source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        super().__post_init__()
        for k in (
            "clock_domain_id",
            "owner_epoch",
            "monotonic_implementation",
            "utc_implementation",
        ):
            _identifier(getattr(self, k))
        _integer(self.monotonic_resolution_ns, 1)
        _integer(self.utc_resolution_ns, 1)
        _sources(self.source_hashes)


@dataclass(frozen=True)
class ClockPairV3(_Record):
    clock_domain_id: str
    descriptor_hash: str
    sequence: int
    mono_before_ns: int
    utc_at: datetime
    mono_after_ns: int

    def __post_init__(self) -> None:
        super().__post_init__()
        _identifier(self.clock_domain_id)
        _sha(self.descriptor_hash)
        _integer(self.sequence, 1)
        if self.mono_after_ns < self.mono_before_ns:
            raise ValueError("reversed monotonic bracket")


@dataclass(frozen=True)
class RawIntervalV3(_Record):
    interval_id: str
    record_seq: int
    identity: RawEpisodeIdentityV3
    kind: Literal[
        "PHYSICS_STEP",
        "CONTROL_APPLY",
        "COMMAND",
        "ACQUISITION",
        "EXECUTOR_ATTEMPT",
        "SETTLE",
        "WAIT",
        "VERIFY_ADVANCE",
        "HOLD",
        "TERMINATION",
    ]
    start: ClockPairV3
    end: ClockPairV3 | None
    start_step: int
    end_step: int | None
    start_sim_time_s: float
    end_sim_time_s: float | None
    disposition: Literal["COMPLETE", "PARTIAL", "ABORTED"]
    error: str | None

    def __post_init__(self) -> None:
        super().__post_init__()
        _identifier(self.interval_id)
        if self.start_sim_time_s < 0:
            raise ValueError("negative simulation time")
        if self.end is None or self.end_step is None or self.end_sim_time_s is None:
            if self.disposition == "COMPLETE" or any(
                v is not None for v in (self.end, self.end_step, self.end_sim_time_s)
            ):
                raise ValueError("partial interval end fields must be absent together")
        elif (
            self.end_step < self.start_step
            or self.end_sim_time_s < self.start_sim_time_s
            or self.end.mono_before_ns < self.start.mono_after_ns
        ):
            raise ValueError("reversed recorded interval")
        if self.disposition != "COMPLETE" and not self.error:
            raise ValueError("partial/aborted reason required")


def _vector(value: Any, length: int) -> None:
    if not isinstance(value, (tuple, list)) or len(value) != length:
        raise ValueError("complete numeric vector required")
    for item in value:
        _number(item)


def _snapshot(raw: Mapping[str, Any], control: bool = False) -> None:
    typ = ActuatorStepObservation if control else PhysicsStepObservation
    if set(raw) != {f.name for f in fields(typ)}:
        raise ValueError("full exact detached raw payload schema required")
    _identifier(raw["episode_id"])
    _integer(raw["physics_step"])
    if _number(raw["sim_time_s"]) < 0:
        raise ValueError("negative raw simulation time")
    shapes = (
        {
            "applied_joint_targets_rad": 7,
            "pre_joint_positions_rad": 7,
            "pre_gravity_bias_nm": 7,
            "control_rad": 7,
            "finger_control_targets_m": 2,
            "actuator_gains": 7,
        }
        if control
        else {
            "object_position_m": 3,
            "object_geom_position_m": 3,
            "object_geom_rotation_row_major": 9,
            "object_half_extent_m": 3,
            "object_linear_velocity_m_s": 3,
            "object_angular_velocity_rad_s": 3,
            "region_center_m": 3,
            "region_half_extent_m": 3,
            "tcp_position_m": 3,
            "finger_positions_m": 2,
            "finger_velocities_m_s": 2,
            "joint_positions_rad": 7,
            "joint_velocities_rad_s": 7,
        }
    )
    for k, size in shapes.items():
        _vector(raw[k], size)
    for k, size in (
        (("actuator_ctrl_ranges", 7),)
        if control
        else (("finger_ranges_m", 2), ("joint_ranges_rad", 7))
    ):
        if len(raw[k]) != size:
            raise ValueError("complete range matrix required")
        for row in raw[k]:
            _vector(row, 2)
            if row[0] >= row[1]:
                raise ValueError("ordered raw limits required")
    if not control:
        for k in ("object_bottom_z_m", "table_top_m"):
            _number(raw[k])
        for k in ("gripper_open", "estop_engaged"):
            if type(raw[k]) is not bool:
                raise ValueError("strict raw boolean required")
        for k, size in (("contact_pairs", 2), ("self_collision_distances_m", 3)):
            for row in raw[k]:
                if len(row) != size or any(type(v) is not str or not v for v in row[:2]):
                    raise ValueError("complete raw contact pair required")
                if size == 3:
                    _number(row[2])


@dataclass(frozen=True)
class RawPhysicsStepV3(_Record):
    record_seq: int
    identity: RawEpisodeIdentityV3
    physics_step: int
    previous_state_hash: str
    post_state_payload: Mapping[str, Any]
    control_payload: Mapping[str, Any]
    physics_interval_id: str
    control_interval_id: str
    purpose_interval_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        _integer(self.physics_step, 1)
        _sha(self.previous_state_hash)
        _snapshot(self.post_state_payload)
        _snapshot(self.control_payload, True)
        for name in ("physics_interval_id", "control_interval_id", "purpose_interval_id"):
            _identifier(getattr(self, name))


@dataclass(frozen=True)
class RawCommandV3(_Record):
    record_seq: int
    identity: RawEpisodeIdentityV3
    command_seq: int
    command_payload: Mapping[str, Any]
    interval_id: str
    parent_interval_id: str
    owner_action_span_id: str | None
    effective_from_step: int | None

    def __post_init__(self) -> None:
        super().__post_init__()
        _integer(self.command_seq, 1)
        for name in ("interval_id", "parent_interval_id"):
            _identifier(getattr(self, name))
        if self.owner_action_span_id is not None:
            _identifier(self.owner_action_span_id)
        row = self.command_payload
        common = {
            "type",
            "accepted",
            "reason",
            "after_emergency_stop",
            "sim_time_s",
            "episode_id",
            "physics_step",
            "command_seq",
        }
        kind = row.get("type")
        extra = (
            {"target_positions_rad", "applied_target_positions_rad"}
            if kind in {"joint_target", "hold_current_joints"}
            else {"target_open"}
            if kind == "gripper"
            else set()
            if kind == "emergency_stop"
            else None
        )
        if (
            extra is None
            or type(row.get("accepted")) is not bool
            or type(row.get("after_emergency_stop")) is not bool
            or type(row.get("reason")) is not str
        ):
            raise ValueError("typed original command schema required")
        if not row["accepted"] and kind == "joint_target":
            extra = {"target_positions_rad"}
        if set(row) != common | extra:
            raise ValueError("unknown/missing original command fields")
        _integer(row["physics_step"])
        _integer(row["command_seq"], 1)
        _number(row["sim_time_s"])
        _identifier(row["episode_id"])
        if kind == "gripper":
            if type(row["target_open"]) is not bool:
                raise ValueError("strict gripper command boolean required")
        for k in extra - {"target_open"}:
            _vector(row[k], 7)
        if self.effective_from_step is not None and not row["accepted"]:
            raise ValueError("rejected command cannot have effective step")


@dataclass(frozen=True)
class TypedActionSpanV3(_Record):
    record_seq: int
    identity: RawEpisodeIdentityV3
    span_id: str
    original_plan: VisualOriginalPlan
    step_id: str
    attempt: int
    grounding: StepGroundingBinding | None
    interval_id: str
    command_seq_start: int
    command_seq_end: int
    returned_result: Mapping[str, Any] | None
    disposition: Literal["RETURNED", "REJECTED", "PARTIAL", "ABORTED"]
    error: str | None
    executed_step_payload: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        super().__post_init__()
        for k in ("span_id", "step_id", "interval_id"):
            _identifier(getattr(self, k))
        _integer(self.attempt, 1)
        _integer(self.command_seq_start, 1)
        if self.command_seq_end < self.command_seq_start:
            raise ValueError("reversed half-open command range")
        if self.step_id not in self.original_plan.requirements:
            raise ValueError("original step requirements unavailable")
        if self.executed_step_payload is not None:
            _from_json(_json(self.executed_step_payload), TaskStep)
        if self.returned_result is not None:
            raw = _plain(self.returned_result)
            if (
                set(raw) != set(ActionResult.model_fields)
                or type(raw.get("success")) is not bool
                or type(raw.get("duration_ms")) is not int
            ):
                raise ValueError("full strict original action result required")
            for name in ("started_at", "finished_at"):
                _aware(datetime.fromisoformat(raw[name]))
            if "physics_steps" in raw["details"]:
                _integer(raw["details"]["physics_steps"])
            ActionResult.model_validate(raw)
        if self.disposition in {"PARTIAL", "ABORTED", "REJECTED"} and not self.error:
            raise ValueError("incomplete/rejected attempt reason required")


@dataclass(frozen=True)
class FrameAcquisitionV3(_Record):
    record_seq: int
    identity: RawEpisodeIdentityV3
    acquisition_id: str
    interval_id: str
    observation_payload: Mapping[str, Any] | None
    camera_state_payload: Mapping[str, Any] | None
    joined_physics_observation_hash: str | None
    pass_state_hashes: tuple[str, ...]
    file_hashes: Mapping[str, str]
    input_role: Literal["SOURCE", "ONLINE"]
    source_acquisition_id: str | None
    transform_payload: Mapping[str, Any] | None
    transform_source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        super().__post_init__()
        _identifier(self.acquisition_id)
        _identifier(self.interval_id)
        if self.camera_state_payload is not None:
            _camera_hash(self.camera_state_payload)
        if self.joined_physics_observation_hash is not None:
            _sha(self.joined_physics_observation_hash)
        for digest in self.pass_state_hashes:
            _sha(digest)
        _sources(self.file_hashes, allow_empty=True)
        _sources(self.transform_source_hashes, allow_empty=True)
        if self.observation_payload is not None:
            raw = _plain(self.observation_payload)
            if (
                set(raw) != set(RGBDObservation.model_fields)
                or type(raw["width"]) is not int
                or type(raw["height"]) is not int
            ):
                raise ValueError("complete strict RGBD observation required")
            _number(raw["sim_time_s"])
            for k in ("intrinsics", "camera_to_world"):
                for v in raw[k]:
                    _number(v)
            RGBDObservation.model_validate(raw)
        if self.source_acquisition_id is not None:
            _identifier(self.source_acquisition_id)
            if (
                self.input_role != "ONLINE"
                or not self.transform_payload
                or not self.transform_source_hashes
            ):
                raise ValueError("derived online input requires full transform/source")
            _transform(self.transform_payload)
        elif self.transform_payload is not None or self.transform_source_hashes:
            raise ValueError("transform cannot lack original source acquisition")


@dataclass(frozen=True)
class ActionFrameJoinV3(_Record):
    record_seq: int
    identity: RawEpisodeIdentityV3
    span_id: str
    acquisition_id: str
    relation: Literal["BEFORE_SUBMIT", "DURING_ACTION", "AFTER_RETURN", "TERMINAL"]
    observation_id: str
    checksum_sha256: str

    def __post_init__(self) -> None:
        super().__post_init__()
        for k in ("span_id", "acquisition_id", "observation_id"):
            _identifier(getattr(self, k))
        _sha(self.checksum_sha256)


@dataclass(frozen=True)
class RawEpisodeRecordsV3(_Record):
    intervals: tuple[RawIntervalV3, ...]
    physics: tuple[RawPhysicsStepV3, ...]
    commands: tuple[RawCommandV3, ...]
    actions: tuple[TypedActionSpanV3, ...]
    frames: tuple[FrameAcquisitionV3, ...]
    joins: tuple[ActionFrameJoinV3, ...]


@dataclass(frozen=True)
class RawEpisodeEnvelopeV3(_Record):
    identity: RawEpisodeIdentityV3
    clock_descriptor: ClockDescriptorV3
    reset_state_payload: Mapping[str, Any]
    terminal_state_payload: Mapping[str, Any]
    evaluation_start_step: int
    physics_dt_s: float
    terminal_command_seq: int
    allocated_action_span_ids: tuple[str, ...]
    allocated_acquisition_ids: tuple[str, ...]
    original_file_hashes: Mapping[str, str]
    task_deadline_at: datetime
    verification_deadline_at: datetime
    contract_deadline_at: datetime
    initial_controller_targets: Mapping[str, Any]
    actuator_delay_steps: int
    schema_version: ClassVar[str] = "rgbd.raw-episode.v3"
    scope: ClassVar[str] = "SOURCE_CONSISTENCY_ONLY"

    def __post_init__(self) -> None:
        super().__post_init__()
        _snapshot(self.reset_state_payload)
        _snapshot(self.terminal_state_payload)
        if (
            self.evaluation_start_step != 120
            or self.physics_dt_s <= 0
            or self.reset_state_payload["physics_step"] != 0
            or self.reset_state_payload["sim_time_s"] != 0
        ):
            raise ValueError("exact reset/start120 and positive simulation timestep required")
        for ids in (self.allocated_action_span_ids, self.allocated_acquisition_ids):
            for item in ids:
                _identifier(item)
            if len(ids) != len(set(ids)):
                raise ValueError("unique complete original allocations required")
        _sources(self.original_file_hashes, allow_empty=True)
        if set(self.initial_controller_targets) != {"joints_rad", "fingers_m"}:
            raise ValueError("full original controller target inventory required")
        _vector(self.initial_controller_targets["joints_rad"], 7)
        _vector(self.initial_controller_targets["fingers_m"], 2)

    def to_payload(self) -> dict[str, Any]:
        return {
            **super().to_payload(),
            "schema_version": "rgbd.raw-episode.v3",
            "scope": "SOURCE_CONSISTENCY_ONLY",
        }


@dataclass(frozen=True)
class RawV3ConsistencyView(_Record):
    status: Literal["COMPLETE", "INCOMPLETE", "INVALID"]
    counts: Mapping[str, int]
    reasons: tuple[str, ...]
    monotonic_coverage: Literal["COMPLETE", "INCOMPLETE"]
    utc_mapping: Literal["BRACKETED", "UNAVAILABLE"]
    source_digest: str
    scope: ClassVar[str] = "SOURCE_CONSISTENCY_ONLY"
    continuous_motion: ClassVar[str] = "NOT_CERTIFIED"

    def to_payload(self) -> dict[str, Any]:
        return {
            **super().to_payload(),
            "scope": "SOURCE_CONSISTENCY_ONLY",
            "continuous_motion": "NOT_CERTIFIED",
        }


def _transform(raw: Mapping[str, Any]) -> None:
    if (
        set(raw)
        != {
            "schema_version",
            "perturbation_seed",
            "frame_count",
            "noise_m",
            "invalid_fraction",
            "occlusion_fraction",
        }
        or raw["schema_version"] != "rgbd.fixed-corruption.v1"
    ):
        raise ValueError("full original fixed corruption policy required")
    _integer(raw["perturbation_seed"])
    _integer(raw["frame_count"], 1)
    if _number(raw["noise_m"]) < 0 or any(
        not 0 <= _number(raw[k]) <= 1 for k in ("invalid_fraction", "occlusion_fraction")
    ):
        raise ValueError("bounded fixed corruption policy required")


def _replay_transform(source: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    """Replay only the frozen fixed-corruption recipe on already recorded pixels."""
    _transform(policy)
    observation = RGBDObservation.model_validate(_plain(source))
    if not any(policy[k] for k in ("noise_m", "invalid_fraction", "occlusion_fraction")):
        return observation.model_dump(mode="json")
    rng = np.random.default_rng(policy["perturbation_seed"] + policy["frame_count"])
    depth = np.asarray(observation.depth_values(), dtype="<f4").reshape(
        observation.height, observation.width
    )
    valid = depth > 0
    with np.errstate(over="raise", invalid="raise"):
        depth[valid] += rng.normal(0, policy["noise_m"], int(valid.sum()))
    depth[rng.random(depth.shape) < policy["invalid_fraction"]] = 0
    depth[depth < 0] = 0
    with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as image:
        rgb = np.asarray(image.convert("RGB")).copy()
    width = round(observation.width * policy["occlusion_fraction"])
    if width:
        start = (observation.width - width) // 2
        rgb[:, start : start + width] = 0
        depth[:, start : start + width] = 0
    encoded = io.BytesIO()
    Image.fromarray(rgb).save(encoded, format="PNG")
    payload = observation.model_dump(mode="json")
    payload.update(
        rgb_png_base64=base64.b64encode(encoded.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
        checksum_sha256="",
    )
    return RGBDObservation.model_validate(payload).model_dump(mode="json")


def _camera_hash(raw: Mapping[str, Any]) -> str:
    if set(raw) != {"sim_time_s", "qpos", "qvel", "act", "ctrl"}:
        raise ValueError("complete original camera physics-state payload required")
    result = hashlib.sha256(struct.pack("<d", _number(raw["sim_time_s"])))
    for k in ("qpos", "qvel", "act", "ctrl"):
        values = raw[k]
        if not isinstance(values, (tuple, list)):
            raise ValueError("complete camera state vector required")
        if k in {"qpos", "qvel"} and len(values) < 9 or k == "ctrl" and len(values) != 9:
            raise ValueError("registered arm/finger camera state shape missing")
        result.update(struct.pack("<I", len(values)))
        result.update(struct.pack(f"<{len(values)}d", *(_number(v) for v in values)))
    return result.hexdigest()


def validate_raw_episode_v3(
    envelope: RawEpisodeEnvelopeV3, records: RawEpisodeRecordsV3
) -> RawV3ConsistencyView:
    """Rebuild the supplied immutable graph; never verify live source authenticity."""
    envelope = _checked(envelope, RawEpisodeEnvelopeV3)
    records = _checked(records, RawEpisodeRecordsV3)
    identity, descriptor = envelope.identity, envelope.clock_descriptor
    terminal = envelope.terminal_state_payload["physics_step"]
    counts = {
        "allocated_episodes": 1,
        "allocated_actions": len(envelope.allocated_action_span_ids),
        "recorded_actions": len(records.actions),
        "missing_actions": len(
            set(envelope.allocated_action_span_ids) - {a.span_id for a in records.actions}
        ),
        "partial_actions": sum(a.disposition in {"PARTIAL", "ABORTED"} for a in records.actions),
        "rejected_actions": sum(a.disposition == "REJECTED" for a in records.actions),
        "allocated_acquisitions": len(envelope.allocated_acquisition_ids),
        "recorded_acquisitions": len(records.frames),
        "recorded_acquisition_records": len(records.frames),
        "distinct_acquisition_intervals": len(
            {f.interval_id for f in records.frames if f.source_acquisition_id is None}
        ),
        "derived_online_inputs": sum(f.source_acquisition_id is not None for f in records.frames),
        "missing_acquisitions": len(
            set(envelope.allocated_acquisition_ids) - {f.acquisition_id for f in records.frames}
        ),
        "physics_expected": terminal,
        "physics_recorded": len(records.physics),
        "commands_expected": envelope.terminal_command_seq,
        "commands_recorded": len(records.commands),
    }
    reasons: list[str] = []
    invalid, incomplete = False, False

    def issue(reason: str, *, missing: bool = False) -> None:
        nonlocal invalid, incomplete
        if reason not in reasons:
            reasons.append(reason)
        if missing:
            incomplete = True
        else:
            invalid = True

    if any(identity.source_hashes.get(k) != v for k, v in descriptor.source_hashes.items()):
        issue("clock_current_source_inventory_mismatch")
    if (
        identity.clock_domain_id != descriptor.clock_domain_id
        or identity.owner_identity.owner_epoch != descriptor.owner_epoch
    ):
        issue("clock_descriptor_domain_or_epoch_mismatch")
    all_rows: tuple[Any, ...] = (
        *records.intervals,
        *records.physics,
        *records.commands,
        *records.actions,
        *records.frames,
        *records.joins,
    )
    if any(r.identity != identity for r in all_rows):
        issue("foreign_record_identity")
    sequences = [r.record_seq for r in all_rows]
    if len(sequences) != len(set(sequences)):
        issue("duplicate_record_sequence")
    elif sorted(sequences) != list(range(1, len(sequences) + 1)):
        issue("missing_record_sequence", missing=True)
    for group in (
        records.intervals,
        records.physics,
        records.commands,
        records.actions,
        records.frames,
        records.joins,
    ):
        if [r.record_seq for r in group] != sorted(r.record_seq for r in group):
            issue("reordered_original_record_sequence")
    intervals = {i.interval_id: i for i in records.intervals}
    if len(intervals) != len(records.intervals):
        issue("duplicate_interval_identity")
    clock_pairs: dict[int, ClockPairV3] = {}
    for recorded_interval in records.intervals:
        for pair in (recorded_interval.start, recorded_interval.end):
            if pair is None:
                continue
            if (
                pair.clock_domain_id != identity.clock_domain_id
                or pair.descriptor_hash != descriptor.digest()
            ):
                issue("clock_pair_source_domain_mismatch")
            previous_pair = clock_pairs.get(pair.sequence)
            if previous_pair is not None and previous_pair != pair:
                issue("clock_sequence_changed_content")
            clock_pairs[pair.sequence] = pair
        if recorded_interval.disposition != "COMPLETE":
            issue("partial_original_interval", missing=True)
    ordered_pairs = [clock_pairs[k] for k in sorted(clock_pairs)]
    if any(
        a.mono_after_ns > b.mono_before_ns
        for a, b in zip(ordered_pairs, ordered_pairs[1:], strict=False)
    ):
        issue("clock_monotonic_order_invalid")
    utc_mapping: Literal["BRACKETED", "UNAVAILABLE"] = (
        "UNAVAILABLE" if descriptor.utc_uncertainty_ns is None else "BRACKETED"
    )
    if ordered_pairs:
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        offsets = []
        padding = descriptor.utc_resolution_ns + (descriptor.utc_uncertainty_ns or 0)
        for pair in ordered_pairs:
            delta = pair.utc_at - epoch
            utc_ns = (delta.days * 86400 + delta.seconds) * 10**9 + delta.microseconds * 1000
            offsets.append(
                (utc_ns - pair.mono_after_ns - padding, utc_ns - pair.mono_before_ns + padding)
            )
        if max(lo for lo, _ in offsets) > min(hi for _, hi in offsets):
            utc_mapping = "UNAVAILABLE"
            issue("utc_clock_discontinuity")
    else:
        issue("clock_samples_unavailable", missing=True)

    def interval_for(key: str, kind: str | None = None) -> RawIntervalV3 | None:
        result = intervals.get(key)
        if result is None:
            issue("referenced_interval_missing", missing=True)
        elif kind is not None and result.kind != kind:
            issue("referenced_interval_kind_mismatch")
        return result

    def within(child: RawIntervalV3, parent: RawIntervalV3) -> bool:
        if child.start.mono_before_ns < parent.start.mono_after_ns:
            return False
        return (
            parent.end is None
            or child.end is None
            or child.end.mono_after_ns <= parent.end.mono_before_ns
        )

    raw = {p.physics_step: p.post_state_payload for p in records.physics}
    if len(raw) != len(records.physics):
        issue("duplicate_physics_step")
    if list(raw) != sorted(raw):
        issue("reordered_physics_steps")
    if len(raw) != terminal or sorted(raw) != list(range(1, len(raw) + 1)):
        issue("physics_step_coverage_missing", missing=True)
    raw[0] = envelope.reset_state_payload
    if terminal < 120:
        issue("evaluation_start_not_reached", missing=True)
    if terminal in raw and _digest(raw[terminal]) != _digest(envelope.terminal_state_payload):
        issue("terminal_snapshot_mismatch")
    for n, snapshot in raw.items():
        if (
            snapshot["episode_id"] != identity.episode_id
            or snapshot["physics_step"] != n
            or not math.isclose(
                snapshot["sim_time_s"], n * envelope.physics_dt_s, abs_tol=1e-9, rel_tol=1e-9
            )
        ):
            issue("physics_identity_simulation_grid_mismatch")
    previous_physics_end: ClockPairV3 | None = None
    for physical_record in records.physics:
        n = physical_record.physics_step
        previous_snapshot = raw.get(n - 1)
        if previous_snapshot is None:
            continue
        if physical_record.previous_state_hash != _digest(previous_snapshot):
            issue("previous_physics_state_hash_mismatch")
        physical_control = physical_record.control_payload
        if (
            physical_control["episode_id"] != identity.episode_id
            or physical_control["physics_step"] != n
            or not math.isclose(
                physical_control["sim_time_s"], previous_snapshot["sim_time_s"], abs_tol=1e-9
            )
        ):
            issue("control_pre_step_identity_mismatch")
        if physical_control["pre_joint_positions_rad"] != previous_snapshot["joint_positions_rad"]:
            issue("control_pre_joint_state_mismatch")
        for target, bias, gain, output, bounds in zip(
            physical_control["applied_joint_targets_rad"],
            physical_control["pre_gravity_bias_nm"],
            physical_control["actuator_gains"],
            physical_control["control_rad"],
            physical_control["actuator_ctrl_ranges"],
            strict=True,
        ):
            if gain <= 0 or not math.isclose(
                output, min(bounds[1], max(bounds[0], target + bias / gain)), abs_tol=1e-9
            ):
                issue("recorded_control_equation_mismatch")
        physics_interval = interval_for(physical_record.physics_interval_id, "PHYSICS_STEP")
        control_interval = interval_for(physical_record.control_interval_id, "CONTROL_APPLY")
        purpose = interval_for(physical_record.purpose_interval_id)
        if physics_interval:
            if (
                previous_physics_end
                and physics_interval.start.mono_before_ns < previous_physics_end.mono_after_ns
            ):
                issue("physics_step_clock_order_mismatch")
            previous_physics_end = physics_interval.end
        if physics_interval and (
            physics_interval.start_step != n - 1 or physics_interval.end_step != n
        ):
            issue("physics_interval_step_range_mismatch")
        if control_interval and (
            control_interval.start_step != n - 1 or control_interval.end_step != n - 1
        ):
            issue("control_interval_step_range_mismatch")
        if (
            physics_interval
            and control_interval
            and control_interval.end
            and control_interval.end.mono_after_ns > physics_interval.start.mono_before_ns
        ):
            issue("control_after_physics_start")
        if purpose:
            if (
                purpose.kind not in _PURPOSES
                or n <= purpose.start_step
                or (purpose.end_step is not None and n > purpose.end_step)
            ):
                issue("physics_purpose_range_mismatch")
            if physics_interval and not within(physics_interval, purpose):
                issue("physics_outside_purpose_clock_interval")
            if n <= 120 and purpose.kind != "SETTLE":
                issue("settle120_purpose_mismatch")
    for i in records.intervals:
        start = raw.get(i.start_step)
        end = raw.get(i.end_step) if i.end_step is not None else None
        if start and not math.isclose(i.start_sim_time_s, start["sim_time_s"], abs_tol=1e-9):
            issue("interval_start_state_time_mismatch")
        if (
            end
            and i.end_sim_time_s is not None
            and not math.isclose(i.end_sim_time_s, end["sim_time_s"], abs_tol=1e-9)
        ):
            issue("interval_end_state_time_mismatch")
        if i.start_step > terminal or (i.end_step is not None and i.end_step > terminal):
            issue("interval_outside_original_terminal")

    commands = {c.command_seq: c for c in records.commands}
    if len(commands) != len(records.commands):
        issue("duplicate_command_sequence")
    if list(commands) != sorted(commands):
        issue("reordered_commands")
    if len(commands) != envelope.terminal_command_seq or sorted(commands) != list(
        range(1, len(commands) + 1)
    ):
        issue("command_coverage_missing", missing=True)
    state_events: list[tuple[int, int, bool]] = []
    for physical_record in records.physics:
        state_interval = intervals.get(physical_record.physics_interval_id)
        if state_interval is not None and state_interval.end is not None:
            state_events.append(
                (
                    state_interval.end.mono_after_ns,
                    state_interval.start.mono_before_ns,
                    physical_record.post_state_payload["estop_engaged"],
                )
            )
    state_events.sort()
    state_cursor = 0
    stop_latched: bool = envelope.reset_state_payload["estop_engaged"]
    latch_known_after_ns: int | None = None

    def advance_available_states(until_ns: int | None = None) -> None:
        nonlocal state_cursor, stop_latched, latch_known_after_ns
        while state_cursor < len(state_events):
            end_ns, start_ns, engaged = state_events[state_cursor]
            if until_ns is not None and end_ns > until_ns:
                break
            if engaged and not stop_latched:
                stop_latched = True
                latch_known_after_ns = end_ns
            elif not engaged and stop_latched:
                if latch_known_after_ns is None or start_ns >= latch_known_after_ns:
                    issue("recorded_stop_latch_state_cleared")
                else:
                    issue("stop_state_sampling_overlaps_latch_transition", missing=True)
            state_cursor += 1

    previous_command_end: ClockPairV3 | None = None
    for command in records.commands:
        command_payload = command.command_payload
        n = command_payload["physics_step"]
        if (
            command_payload["episode_id"] != identity.episode_id
            or command_payload["command_seq"] != command.command_seq
            or n not in raw
        ):
            issue("command_source_identity_mismatch")
        elif not math.isclose(command_payload["sim_time_s"], raw[n]["sim_time_s"], abs_tol=1e-9):
            issue("command_dispatch_sim_time_mismatch")
        interval = interval_for(command.interval_id, "COMMAND")
        parent = interval_for(command.parent_interval_id)
        if interval:
            advance_available_states(interval.start.mono_before_ns)
            if (
                previous_command_end
                and interval.start.mono_before_ns < previous_command_end.mono_after_ns
            ):
                issue("command_dispatch_clock_order_mismatch")
            previous_command_end = interval.end
        kind = command_payload["type"]
        if kind == "emergency_stop":
            if command_payload["after_emergency_stop"]:
                issue("emergency_stop_own_flag_mismatch")
            if command_payload["accepted"] and not stop_latched:
                stop_latched = True
                latch_known_after_ns = (
                    interval.end.mono_after_ns if interval and interval.end else None
                )
        else:
            if command_payload["after_emergency_stop"] != stop_latched:
                issue("command_stop_flag_latch_mismatch")
            if command_payload["accepted"] and stop_latched and kind != "hold_current_joints":
                issue("ordinary_command_accepted_after_emergency_stop")
        if interval and (interval.start_step != n or interval.end_step != n):
            issue("command_interval_dispatch_step_mismatch")
        if interval and parent and not within(interval, parent):
            issue("command_outside_parent_interval")
        if parent and parent.kind not in _PURPOSES:
            issue("command_parent_purpose_missing")
        if command.effective_from_step is not None and command.effective_from_step <= n:
            issue("command_effect_precedes_dispatch")
        if (
            command_payload["type"] == "hold_current_joints"
            and n in raw
            and (
                command_payload["target_positions_rad"] != raw[n]["joint_positions_rad"]
                or command_payload["applied_target_positions_rad"]
                != command_payload["target_positions_rad"]
            )
        ):
            issue("hold_target_not_measured_dispatch_q")
    advance_available_states()

    arm_targets = tuple(envelope.initial_controller_targets["joints_rad"])
    finger_targets = tuple(envelope.initial_controller_targets["fingers_m"])
    pending: list[tuple[int, tuple[Any, ...]]] = []
    controls_by_step = {p.physics_step: p.control_payload for p in records.physics}
    for n in sorted(controls_by_step):
        for c in records.commands:
            replay_payload = c.command_payload
            if replay_payload["physics_step"] != n - 1 or not replay_payload["accepted"]:
                continue
            kind = replay_payload["type"]
            expected_effect = n + (envelope.actuator_delay_steps if kind == "joint_target" else 0)
            if c.effective_from_step is None:
                issue("accepted_command_effect_source_missing", missing=True)
            elif c.effective_from_step != expected_effect:
                issue("command_effect_delay_source_mismatch")
            if kind == "joint_target":
                clipped = tuple(
                    max(-2.8, min(2.8, v)) for v in replay_payload["target_positions_rad"]
                )
                if clipped != replay_payload["applied_target_positions_rad"]:
                    issue("joint_command_clip_mismatch")
                if envelope.actuator_delay_steps:
                    pending.append((expected_effect, clipped))
                else:
                    arm_targets = clipped
            elif kind == "hold_current_joints":
                pending.clear()
                arm_targets = tuple(replay_payload["applied_target_positions_rad"])
            elif kind == "gripper":
                finger_targets = (0.039, 0.039) if replay_payload["target_open"] else (0.0, 0.0)
        for effect, targets in pending:
            if effect <= n:
                arm_targets = targets
        pending = [(effect, target) for effect, target in pending if effect > n]
        replay_control = controls_by_step[n]
        if (
            replay_control["applied_joint_targets_rad"] != arm_targets
            or replay_control["finger_control_targets_m"] != finger_targets
        ):
            issue("applied_controller_target_replay_mismatch")

    actions = {a.span_id: a for a in records.actions}
    if len(actions) != len(records.actions):
        issue("duplicate_action_span")
    if set(actions) - set(envelope.allocated_action_span_ids):
        issue("unallocated_action_span")
    if counts["missing_actions"]:
        issue("allocated_action_record_missing", missing=True)
    plan_versions: dict[int, str] = {}
    step_attempts: dict[tuple[int, str], int] = {}
    returned_action_ids: set[str] = set()
    action_intervals: set[str] = set()
    deadlines = min(
        envelope.task_deadline_at, envelope.verification_deadline_at, envelope.contract_deadline_at
    )
    for action in records.actions:
        original = action.original_plan
        if any(identity.source_hashes.get(k) != v for k, v in original.source_hashes.items()):
            issue("original_plan_current_source_inventory_mismatch")
        contract = original.contract
        version = contract.plan_version
        retry_key = (version, action.step_id)
        prior_attempt = step_attempts.get(retry_key, 0)
        if (
            action.attempt != prior_attempt + 1
            or action.attempt > original.requirements[action.step_id].original_step.retry_limit + 1
        ):
            issue("original_retry_policy_or_attempt_order_mismatch")
        step_attempts[retry_key] = action.attempt
        if (
            envelope.task_deadline_at > original.task_deadline_at
            or envelope.verification_deadline_at > original.verification_deadline_at
            or envelope.contract_deadline_at > contract.valid_until
        ):
            issue("original_absolute_deadline_extended")
        if action.executed_step_payload is None:
            issue("executed_step_arguments_missing", missing=True)
        else:
            expected_step = (
                action.grounding.grounded_step
                if action.grounding
                else original.requirements[action.step_id].original_step
            )
            if _json(action.executed_step_payload) != _json(expected_step.model_dump(mode="json")):
                issue("executor_payload_original_binding_mismatch")
        if (
            original.identity != identity.owner_identity
            or original.role_bundle_hash != identity.role_bundle_hash
        ):
            issue("action_original_owner_role_mismatch")
        if version in plan_versions and plan_versions[version] != original.digest():
            issue("same_version_original_plan_changed")
        plan_versions[version] = original.digest()
        interval = interval_for(action.interval_id, "EXECUTOR_ATTEMPT")
        if action.interval_id in action_intervals:
            issue("duplicate_executor_attempt_interval")
        action_intervals.add(action.interval_id)
        if interval:
            if interval.start_step < 120 or interval.start.utc_at >= min(
                deadlines, original.effective_deadline_at
            ):
                issue("action_start_outside_original_deadline_or_evaluation")
            if interval.start.utc_at < original.registered_at:
                issue("action_precedes_original_plan_registration")
            if action.disposition == "REJECTED" and (
                interval.end_step != interval.start_step
                or action.command_seq_end != action.command_seq_start
            ):
                issue("rejected_attempt_contains_effects")
            if action.disposition in {"PARTIAL", "ABORTED"}:
                issue("partial_action_attempt", missing=True)
            elif action.disposition == "RETURNED" and action.returned_result is None:
                issue("actual_action_return_missing", missing=True)
            if action.returned_result is not None:
                result = action.returned_result
                if result["action_id"] in returned_action_ids:
                    issue("duplicate_returned_action_identity")
                returned_action_ids.add(result["action_id"])
                if (
                    result["action_type"]
                    != original.requirements[action.step_id].original_step.skill.value
                ):
                    issue("action_result_skill_mismatch")
                observed_steps = (
                    None if interval.end_step is None else interval.end_step - interval.start_step
                )
                if "physics_steps" not in result["details"]:
                    issue("action_result_step_source_missing", missing=True)
                elif (
                    observed_steps is not None
                    and result["details"]["physics_steps"] != observed_steps
                ):
                    issue("action_result_step_count_mismatch")
        if action.command_seq_end > envelope.terminal_command_seq + 1:
            issue("action_command_tail_outside_original")
        for c in records.commands:
            in_range = action.command_seq_start <= c.command_seq < action.command_seq_end
            if in_range != (c.owner_action_span_id == action.span_id):
                issue("action_command_ownership_range_mismatch")
            if (
                in_range
                and interval
                and (
                    c.parent_interval_id != action.interval_id
                    or c.command_payload["physics_step"] < interval.start_step
                    or (
                        interval.end_step is not None
                        and c.command_payload["physics_step"] > interval.end_step
                    )
                )
            ):
                issue("action_command_outside_step_interval")
        if (
            identity.source_kind == "ONLINE_CED"
            and action.disposition != "REJECTED"
            and action.grounding is None
        ):
            issue("online_grounding_source_missing", missing=True)
        if action.grounding is not None:
            grounding = action.grounding
            if any(
                identity.source_hashes.get(k) != v
                for k, v in grounding.grounding_source_hashes.items()
            ):
                issue("grounding_current_source_inventory_mismatch")
            requirement = original.requirements[action.step_id]
            if (
                grounding.current_identity != original.identity
                or grounding.original_plan_hash != original.digest()
                or grounding.original_requirements.digest() != requirement.digest()
                or grounding.plan_version != contract.plan_version
                or grounding.command_seq != contract.command_seq
            ):
                issue("original_requirement_grounding_binding_mismatch")
            if (
                grounding.expected_duration_s > requirement.expected_duration_s
                and grounding.duration_check_hash is None
            ):
                issue("extended_horizon_duration_source_missing", missing=True)
            if grounding.valid_until > min(deadlines, original.effective_deadline_at) or (
                interval
                and not grounding.created_at <= interval.start.utc_at < grounding.valid_until
            ):
                issue("grounding_deadline_or_current_start_mismatch")
    for c in records.commands:
        if c.owner_action_span_id is not None and c.owner_action_span_id not in actions:
            issue("command_action_source_missing", missing=True)
        if c.owner_action_span_id is None:
            parent = intervals.get(c.parent_interval_id)
            if parent and parent.kind == "EXECUTOR_ATTEMPT":
                issue("executor_command_lacks_action_owner")
    for p in records.physics:
        purpose = intervals.get(p.purpose_interval_id)
        if (
            purpose
            and purpose.kind == "EXECUTOR_ATTEMPT"
            and purpose.interval_id not in action_intervals
        ):
            issue("physics_executor_action_source_missing", missing=True)

    terminal_boundary_ns: int | None = None
    if any(join.relation == "TERMINAL" for join in records.joins):
        terminal_physics = next((p for p in records.physics if p.physics_step == terminal), None)
        terminal_interval = (
            intervals.get(terminal_physics.physics_interval_id) if terminal_physics else None
        )
        if terminal_interval is None or terminal_interval.end is None:
            issue("terminal_physics_boundary_unavailable", missing=True)
        else:
            terminal_boundary_ns = terminal_interval.end.mono_after_ns
        completion_ends: list[int] = []
        all_actions_closed = counts["missing_actions"] == 0
        for recorded_action in records.actions:
            completion = intervals.get(recorded_action.interval_id)
            if completion is not None and completion.end is not None:
                completion_ends.append(completion.end.mono_after_ns)
            if (
                completion is None
                or completion.end is None
                or completion.disposition != "COMPLETE"
                or recorded_action.disposition not in {"RETURNED", "REJECTED"}
                or (
                    recorded_action.disposition == "RETURNED"
                    and recorded_action.returned_result is None
                )
            ):
                all_actions_closed = False
        terminations = [row for row in records.intervals if row.kind == "TERMINATION"]
        final_termination = max(
            terminations, key=lambda row: row.start.mono_before_ns, default=None
        )
        termination_closed = (
            final_termination is not None
            and final_termination.disposition == "COMPLETE"
            and final_termination.end is not None
        )
        if final_termination is not None and not termination_closed:
            issue("terminal_termination_boundary_unavailable", missing=True)
        if not all_actions_closed and not termination_closed:
            issue("terminal_action_completion_boundary_unavailable", missing=True)
        if (
            termination_closed
            and final_termination is not None
            and final_termination.end is not None
        ):
            if final_termination.end_step != terminal:
                issue("termination_terminal_physics_mismatch")
            if terminal_boundary_ns is not None and final_termination.end.mono_after_ns < max(
                [terminal_boundary_ns, *completion_ends]
            ):
                issue("termination_precedes_recorded_completion")
        completion_ends.extend(
            termination.end.mono_after_ns
            for termination in terminations
            if termination.disposition == "COMPLETE" and termination.end is not None
        )
        if terminal_boundary_ns is not None:
            terminal_boundary_ns = max([terminal_boundary_ns, *completion_ends])

    frames = {f.acquisition_id: f for f in records.frames}
    if len(frames) != len(records.frames):
        issue("duplicate_acquisition")
    if set(frames) - set(envelope.allocated_acquisition_ids):
        issue("unallocated_acquisition")
    if counts["missing_acquisitions"]:
        issue("allocated_acquisition_record_missing", missing=True)
    file_inventory: dict[str, str] = {}
    frame_ids: dict[str, str] = {}
    for frame in records.frames:
        interval = interval_for(frame.interval_id, "ACQUISITION")
        if frame.observation_payload is None:
            issue("failed_acquisition_observation_missing", missing=True)
            if interval and interval.disposition == "COMPLETE":
                issue("complete_acquisition_has_no_observation")
            continue
        obs = RGBDObservation.model_validate(_plain(frame.observation_payload))
        prior_acquisition = frame_ids.get(obs.observation_id)
        if prior_acquisition is not None and frame.source_acquisition_id != prior_acquisition:
            issue("reused_observation_identity_without_derivation")
        frame_ids[obs.observation_id] = frame.source_acquisition_id or frame.acquisition_id
        if obs.episode_id != identity.episode_id:
            issue("frame_foreign_episode")
        if interval:
            if (
                interval.start_step != interval.end_step
                or interval.start_sim_time_s != interval.end_sim_time_s
            ):
                issue("acquisition_crossed_physics_state")
            if (
                not math.isclose(obs.sim_time_s, interval.start_sim_time_s, abs_tol=1e-9)
                or obs.captured_at != interval.start.utc_at
            ):
                issue("frame_acquisition_time_join_mismatch")
            if frame.camera_state_payload is None or frame.joined_physics_observation_hash is None:
                issue("camera_full_state_source_missing", missing=True)
            else:
                camera_hash = _camera_hash(frame.camera_state_payload)
                if len(frame.pass_state_hashes) < 2 or set(frame.pass_state_hashes) != {
                    camera_hash
                }:
                    issue("camera_pass_state_hash_mismatch")
                if interval.start_step in raw:
                    snapshot = raw[interval.start_step]
                    if frame.joined_physics_observation_hash != _digest(snapshot):
                        issue("frame_render_pass_state_join_mismatch")
                    if (
                        not math.isclose(
                            frame.camera_state_payload["sim_time_s"],
                            snapshot["sim_time_s"],
                            abs_tol=1e-9,
                        )
                        or frame.camera_state_payload["qpos"][:7] != snapshot["joint_positions_rad"]
                        or frame.camera_state_payload["qpos"][7:9] != snapshot["finger_positions_m"]
                        or frame.camera_state_payload["qvel"][:7]
                        != snapshot["joint_velocities_rad_s"]
                        or frame.camera_state_payload["qvel"][7:9]
                        != snapshot["finger_velocities_m_s"]
                    ):
                        issue("camera_state_physics_join_mismatch")
        expected_bytes = [
            base64.b64decode(obs.rgb_png_base64),
            base64.b64decode(obs.depth_float32_base64),
            obs.valid_mask_bytes(),
        ]
        expected_digests = {hashlib.sha256(v).hexdigest() for v in expected_bytes}
        if not expected_digests <= set(frame.file_hashes.values()):
            issue("frame_original_rgb_depth_mask_inventory_missing", missing=True)
        for name, digest in frame.file_hashes.items():
            if name in file_inventory and file_inventory[name] != digest:
                issue("frame_file_path_changed_bytes")
            file_inventory[name] = digest
            if envelope.original_file_hashes.get(name) != digest:
                issue("frame_file_inventory_mismatch")
        if frame.source_acquisition_id is not None:
            if any(
                identity.source_hashes.get(k) != v for k, v in frame.transform_source_hashes.items()
            ):
                issue("transform_current_source_inventory_mismatch")
            source = frames.get(frame.source_acquisition_id)
            if source is None or source.observation_payload is None:
                issue("derived_frame_original_source_missing", missing=True)
            elif (
                source.input_role != "SOURCE"
                or source.source_acquisition_id is not None
                or source.acquisition_id == frame.acquisition_id
            ):
                issue("derived_frame_source_role_invalid")
            else:
                src = source.observation_payload
                if any(
                    src[k] != frame.observation_payload[k]
                    for k in (
                        "frame_id",
                        "captured_at",
                        "sim_time_s",
                        "episode_id",
                        "calibration_version",
                        "width",
                        "height",
                        "intrinsics",
                        "camera_to_world",
                    )
                ):
                    issue("derived_frame_source_identity_mismatch")
                if source.interval_id != frame.interval_id:
                    issue("derived_frame_acquisition_interval_mismatch")
                try:
                    expected = _replay_transform(src, frame.transform_payload or {})
                except (ValueError, FloatingPointError, OverflowError):
                    issue("derived_online_transform_numerical_invalid")
                else:
                    if _json(expected) != _json(frame.observation_payload):
                        issue("derived_online_transform_bytes_mismatch")
    join_ids: set[tuple[str, str, str]] = set()
    for join in records.joins:
        key = (join.span_id, join.acquisition_id, join.relation)
        if key in join_ids:
            issue("duplicate_action_frame_join")
        join_ids.add(key)
        joined_frame, joined_action = frames.get(join.acquisition_id), actions.get(join.span_id)
        if joined_frame is None or joined_action is None:
            issue("action_frame_join_source_missing", missing=True)
            continue
        if joined_frame.observation_payload is None:
            issue("joined_acquisition_failed", missing=True)
            continue
        joined_observation = joined_frame.observation_payload
        if (
            joined_frame.input_role != "ONLINE"
            or joined_observation["observation_id"] != join.observation_id
            or joined_observation["checksum_sha256"] != join.checksum_sha256
        ):
            issue("action_frame_exact_online_input_mismatch")
        acquisition, attempt = (
            intervals.get(joined_frame.interval_id),
            intervals.get(joined_action.interval_id),
        )
        if join.relation == "TERMINAL" and acquisition is not None:
            if acquisition.start_step != terminal or acquisition.end_step not in {None, terminal}:
                issue("terminal_frame_physics_identity_mismatch")
            if acquisition.end is None:
                issue("terminal_capture_boundary_unavailable", missing=True)
            if joined_frame.joined_physics_observation_hash is None:
                issue("terminal_frame_state_binding_unavailable", missing=True)
            elif joined_frame.joined_physics_observation_hash != _digest(
                envelope.terminal_state_payload
            ):
                issue("terminal_frame_state_identity_mismatch")
            if (
                terminal_boundary_ns is not None
                and acquisition.start.mono_before_ns < terminal_boundary_ns
            ):
                issue("terminal_capture_precedes_final_boundary")
        if acquisition and attempt:
            if join.relation == "BEFORE_SUBMIT" and (
                acquisition.end is None
                or acquisition.end.mono_after_ns > attempt.start.mono_before_ns
                or acquisition.start_step != attempt.start_step
            ):
                issue("before_frame_not_fresh_action_boundary")
            if join.relation == "AFTER_RETURN" and (
                attempt.end is None
                or acquisition.start.mono_before_ns < attempt.end.mono_after_ns
                or acquisition.start_step != attempt.end_step
            ):
                if attempt.end is None:
                    issue("partial_action_after_frame_unknown", missing=True)
                else:
                    issue("after_frame_precedes_actual_return")
            if join.relation == "DURING_ACTION" and not within(acquisition, attempt):
                issue("supervision_frame_outside_action")
        if (
            attempt
            and join.relation == "BEFORE_SUBMIT"
            and (
                attempt.start.utc_at - datetime.fromisoformat(joined_observation["captured_at"])
            ).total_seconds()
            > joined_action.original_plan.requirements[joined_action.step_id].ordinary_ttl_s
        ):
            issue("action_frame_original_ttl_expired")
        if (
            joined_action.grounding
            and join.relation == "BEFORE_SUBMIT"
            and (
                join.observation_id != joined_action.grounding.observation_id
                or join.checksum_sha256 != joined_action.grounding.observation_checksum_sha256
                or joined_observation["calibration_version"]
                != joined_action.grounding.calibration_version
            )
        ):
            issue("grounding_exact_frame_join_mismatch")
    for action in records.actions:
        for relation in ("BEFORE_SUBMIT", "AFTER_RETURN"):
            matches = [
                j for j in records.joins if j.span_id == action.span_id and j.relation == relation
            ]
            if not matches and (relation == "BEFORE_SUBMIT" or action.disposition == "RETURNED"):
                issue("action_boundary_frame_join_missing", missing=True)
            elif len(matches) > 1:
                issue("ambiguous_action_boundary_frame_join")
    return RawV3ConsistencyView(
        "INVALID" if invalid else "INCOMPLETE" if incomplete else "COMPLETE",
        counts,
        tuple(reasons),
        "INCOMPLETE" if invalid or incomplete else "COMPLETE",
        utc_mapping,
        _digest({"envelope": envelope.to_payload(), "records": records.to_payload()}),
    )
