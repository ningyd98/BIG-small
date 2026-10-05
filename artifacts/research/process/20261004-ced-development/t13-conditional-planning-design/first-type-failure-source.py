"""Immutable future repair intentions; no task, command or execution authority."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import (
    RepairWindow,
    StepDependency,
    find_repair_window,
)
from cloud_edge_robot_arm.contracts import ExecutionCheckpoint, SkillName
from cloud_edge_robot_arm.edge.evidence.conditions import (
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    OriginalActionRequirements,
    VisualOriginalPlan,
    VisualOwnerIdentity,
    _aware,
    _counter,
    _digest,
    _model_json,
    _plain,
    freeze_original_visual_plan,
)

SCHEMA = "conditional.visual-repair-planning-intent.v1"


class _Replacement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    step_id: str = Field(min_length=1, max_length=100)
    skill: SkillName
    target_pixel: tuple[int, int] | None
    destination_pixel: tuple[int, int] | None


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal["conditional.visual-repair-planning-intent.v1"]
    binding_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    replacements: list[_Replacement] = Field(min_length=1, max_length=100)


@dataclass(frozen=True)
class ConditionalReplacement:
    step_id: str
    target_pixel: tuple[int, int] | None
    destination_pixel: tuple[int, int] | None
    original_requirements: OriginalActionRequirements
    current_preconditions: tuple[tuple[str, str, str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        r = self.original_requirements
        copied = OriginalActionRequirements(
            r.original_step,
            r.preconditions,
            r.postconditions,
            r.allowed_error_m,
            r.sensor_requirements,
            r.ordinary_ttl_s,
            r.expected_duration_s,
            r.policy_source_hashes,
        )
        if self.step_id != copied.original_step.step_id:
            raise ValueError("planning step identity mismatch")
        object.__setattr__(self, "original_requirements", copied)
        for name in ("target_pixel", "destination_pixel"):
            value = getattr(self, name)
            if value is not None:
                if len(value) != 2 or any(type(v) is not int or v < 0 for v in value):
                    raise ValueError("pixel intentions require nonnegative strict integers")
                object.__setattr__(self, name, tuple(value))
        checks = tuple(
            (name, status, frame, tuple(reasons))
            for name, status, frame, reasons in self.current_preconditions
        )
        if tuple(c[0] for c in checks) != tuple(c.name for c in copied.preconditions) or any(
            status not in {"PASS", "FAIL", "UNKNOWN"} or not frame for _, status, frame, _ in checks
        ):
            raise ValueError("complete current condition diagnostics required")
        object.__setattr__(self, "current_preconditions", checks)

    def to_payload(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "target_pixel": _plain(self.target_pixel),
            "destination_pixel": _plain(self.destination_pixel),
            "original_requirements": self.original_requirements.to_payload(),
            "current_preconditions": _plain(self.current_preconditions),
            "recheck_before_execution": True,
        }


@dataclass(frozen=True)
class ConditionalRepairPlanningIntent:
    binding_hash: str
    original_plan_hash: str
    source_checkpoint_hash: str
    observation_id: str
    observation_checksum_sha256: str
    owner_revision: int
    state_generation: int
    valid_until: datetime
    replacements: tuple[ConditionalReplacement, ...]
    _preserved_steps_json: str
    scope: Literal["PLANNING_ONLY"] = field(default="PLANNING_ONLY", init=False)
    execution_admitted: Literal[False] = field(default=False, init=False)
    method_admitted: Literal[False] = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "replacements", tuple(self.replacements))
        _counter(self.owner_revision)
        _counter(self.state_generation)
        _aware(self.valid_until)
        # The detached JSON view cannot mutate the original or this carrier.
        stored = json.loads(self._preserved_steps_json)
        if not isinstance(stored, dict):
            raise ValueError("preserved original steps must be a mapping")

    @property
    def preserved_original_steps(self) -> dict[str, Any]:
        return json.loads(self._preserved_steps_json)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA,
            "scope": self.scope,
            "execution_admitted": self.execution_admitted,
            "method_admitted": self.method_admitted,
            "binding_hash": self.binding_hash,
            "original_plan_hash": self.original_plan_hash,
            "source_checkpoint_hash": self.source_checkpoint_hash,
            "observation_id": self.observation_id,
            "observation_checksum_sha256": self.observation_checksum_sha256,
            "owner_revision": self.owner_revision,
            "state_generation": self.state_generation,
            "valid_until": self.valid_until.isoformat(),
            "replacements": [r.to_payload() for r in self.replacements],
            "preserved_original_steps": self.preserved_original_steps,
        }

    def digest(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True)
class _Context:
    original: VisualOriginalPlan
    checkpoint: ExecutionCheckpoint
    online: OnlineEvidenceSnapshot
    window: RepairWindow
    binding_hash: str
    expires: datetime


def _context(
    *,
    original: VisualOriginalPlan,
    current_identity: VisualOwnerIdentity,
    source_checkpoint: ExecutionCheckpoint,
    online: OnlineEvidenceSnapshot,
    owner_revision: int,
    state_generation: int,
    invalid_evidence_ids: Sequence[str] | set[str],
    now: datetime,
) -> _Context:
    original = freeze_original_visual_plan(**original.freeze_inputs())
    _aware(now)
    _counter(owner_revision)
    _counter(state_generation)
    if current_identity != original.identity:
        raise ValueError("foreign planning owner identity")
    cp = ExecutionCheckpoint.model_validate_json(
        _model_json(source_checkpoint, ExecutionCheckpoint)
    )
    observation = RGBDObservation.model_validate_json(
        _model_json(online.observation, RGBDObservation)
    )
    robot = type(online.robot_state).model_validate_json(
        _model_json(online.robot_state, type(online.robot_state))
    )
    contract = original.contract
    ids = [step.step_id for step in contract.steps]
    completed = cp.completed_step_ids
    if (
        cp.checkpoint_hash != checkpoint_digest(cp)
        or online.context_hash != cp.checkpoint_hash
        or cp.task_id != current_identity.task_id
        or cp.plan_id != current_identity.plan_id
        or cp.robot_id != current_identity.robot_id
        or (cp.plan_version, cp.command_seq) != (contract.plan_version, contract.command_seq)
        or type(online.plan_version) is not int
        or type(online.command_seq) is not int
        or (online.plan_version, online.command_seq)
        != (contract.plan_version, contract.command_seq)
        or ids[: len(completed)] != completed
        or cp.pending_step_ids != ids[len(completed) :]
        or cp.current_step_index != len(completed)
        or not cp.pending_step_ids
        or cp.current_step_id != cp.pending_step_ids[0]
        or cp.execution_state in {"COMPLETED", "SAFETY_STOPPED"}
        or not _aware(cp.created_at) <= _aware(cp.updated_at) <= now
        or observation.episode_id != current_identity.episode_id
        or not observation.calibration_version
    ):
        raise ValueError("current planning checkpoint/frame/version mismatch")
    invalid = set(invalid_evidence_ids)
    graph = tuple(
        StepDependency(
            d.step_id, d.depends_on, d.evidence_ids, d.physical_effect_id, d.step_id in completed
        )
        for d in original.dependencies
    )
    if any(d.completed and d.step_id not in completed for d in original.dependencies):
        raise ValueError("planning cannot undo a previously completed effect")
    window = find_repair_window(
        graph,
        invalid,
        expected_plan_version=contract.plan_version,
        expected_command_seq=contract.command_seq,
    )
    if not window.replace_step_ids:
        raise ValueError("conditional planning window is empty")
    ages = []
    for name in window.replace_step_ids:
        requirement = original.requirements[name]
        ages.append(requirement.ordinary_ttl_s)
        for c in (*requirement.preconditions, *requirement.postconditions):
            age = c.tolerances.get("max_age_s", requirement.ordinary_ttl_s)
            if type(age) not in {int, float} or age <= 0:
                raise ValueError("invalid registered requirement TTL")
            ages.append(age)
            if (
                c.tolerances.get("calibration_version", observation.calibration_version)
                != observation.calibration_version
            ):
                raise ValueError("registered planning calibration mismatch")
    expires = min(
        original.effective_deadline_at, observation.captured_at + timedelta(seconds=min(ages))
    )
    if not original.registered_at <= observation.captured_at <= now < expires:
        raise ValueError("conditional planning source is stale, future or expired")
    facts = json.loads(json.dumps(_plain(online.visual_facts), allow_nan=False))
    detached = OnlineEvidenceSnapshot(
        observation, robot, facts, online.plan_version, online.command_seq, online.context_hash
    )
    binding = _digest(
        {
            "schema": SCHEMA,
            "original_plan": original.to_payload(),
            "checkpoint": cp.model_dump(mode="json"),
            "observation": observation.model_dump(mode="json"),
            "robot_state": robot.model_dump(mode="json"),
            "visual_facts": facts,
            "owner_revision": owner_revision,
            "state_generation": state_generation,
            "invalid_evidence_ids": sorted(invalid),
            "window": list(window.replace_step_ids),
            "valid_until": expires,
        }
    )
    return _Context(original, cp, detached, window, binding, expires)


def conditional_planning_binding(**context: Any) -> str:
    """Bind locally supplied source data; never authenticate an actual owner."""
    return _context(**context).binding_hash


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate planning response key")
        result[name] = value
    return result


def build_conditional_repair_intent(
    *, intent_json: str | bytes, **context: Any
) -> ConditionalRepairPlanningIntent:
    local = _context(**context)
    decoded = json.loads(intent_json, object_pairs_hook=_unique)
    # JSON-mode validation accepts enum wire strings while preserving strict ints.
    wire = _Wire.model_validate_json(json.dumps(decoded, allow_nan=False))
    if wire.binding_hash != local.binding_hash or [r.step_id for r in wire.replacements] != list(
        local.window.replace_step_ids
    ):
        raise ValueError("response binding or exact replacement window mismatch")
    replacements = []
    observation = local.online.observation
    for intent in wire.replacements:
        requirement = local.original.requirements[intent.step_id]
        if intent.skill != requirement.original_step.skill:
            raise ValueError("conditional repair cannot change original skill")
        for pixel in (intent.target_pixel, intent.destination_pixel):
            if pixel is not None and not (
                0 <= pixel[0] < observation.width and 0 <= pixel[1] < observation.height
            ):
                raise ValueError("pixel intention outside current frame")
        checks = tuple(
            (v.condition_name, v.status.value, v.observation_id, tuple(v.reasons))
            for v in evaluate_conditions(
                requirement.preconditions, local.online, now=context["now"]
            )
        )
        replacements.append(
            ConditionalReplacement(
                intent.step_id, intent.target_pixel, intent.destination_pixel, requirement, checks
            )
        )
    preserved = {
        step.step_id: step.model_dump(mode="json")
        for step in local.original.contract.steps
        if step.step_id in local.window.preserved_step_ids
    }
    return ConditionalRepairPlanningIntent(
        local.binding_hash,
        local.original.digest(),
        local.checkpoint.checkpoint_hash,
        observation.observation_id,
        observation.checksum_sha256,
        context["owner_revision"],
        context["state_generation"],
        local.expires,
        tuple(replacements),
        json.dumps(preserved, sort_keys=True, separators=(",", ":")),
    )
