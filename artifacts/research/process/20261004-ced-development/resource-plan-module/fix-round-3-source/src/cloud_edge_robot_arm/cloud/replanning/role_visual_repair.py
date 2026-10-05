"""Role-bound visual repair intents; actual local proof is required for each candidate.

This module never submits, activates, dispatches or certifies physical success.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import RepairWindow
from cloud_edge_robot_arm.cloud.replanning.visual_repair import (
    RepairProposal,
    VisualRepairContext,
    _inputs_valid,
    repair_window,
)
from cloud_edge_robot_arm.contracts.models import (
    LocalReplanningRequest,
    SkillName,
    TaskStep,
    replan_payload_hash,
)
from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract
from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
from cloud_edge_robot_arm.research.cost_ledger import CostLedger
from cloud_edge_robot_arm.vision.messages import build_visual_messages, model_to_observation_pixel
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

PROMPT_VERSION = "role.visual-repair-intent.v1"
REQUIRED_SOURCES = frozenset(
    {
        "src/cloud_edge_robot_arm/cloud/replanning/role_visual_repair.py",
        "src/cloud_edge_robot_arm/cloud/replanning/role_visual_adapter.py",
        "src/cloud_edge_robot_arm/cloud/replanning/visual_repair.py",
        "src/cloud_edge_robot_arm/cloud/replanning/visual_dependencies.py",
        "src/cloud_edge_robot_arm/vision/planner.py",
        "src/cloud_edge_robot_arm/vision/messages.py",
    }
)


def plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        items = [plain(item) for item in value]
        return sorted(items) if isinstance(value, (set, frozenset)) else items
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {item.name: plain(getattr(value, item.name)) for item in fields(value)}
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def checkpoint_hash(context: VisualRepairContext) -> str:
    data = context.checkpoint.model_dump(mode="json")
    data["checkpoint_hash"] = ""
    return replan_payload_hash(data)


@dataclass(frozen=True)
class RoleVisualRepairSource:
    context: VisualRepairContext
    action_evidence: Mapping[str, ActionEvidenceContract]
    evidence_scope: Literal["UNAVAILABLE", "SOFTWARE_ONLY", "ACTUAL_SOURCE"] = "UNAVAILABLE"
    source_hash: str = field(init=False)

    def __post_init__(self) -> None:
        current = self.context
        object.__setattr__(
            self,
            "context",
            VisualRepairContext(
                current.active_contract,
                current.checkpoint,
                current.dependencies,
                current.invalid_evidence_ids,
                current.online_evidence,
                current.completed_effect_conditions,
            ),
        )
        object.__setattr__(
            self,
            "action_evidence",
            MappingProxyType(
                {
                    identity: replace(proof, evidence=replace(proof.evidence))
                    for identity, proof in self.action_evidence.items()
                }
            ),
        )
        object.__setattr__(self, "source_hash", digest(self.payload()))

    def payload(self) -> dict[str, Any]:
        return {
            "context": plain(self.context),
            "action_evidence": plain(self.action_evidence),
            "evidence_scope": self.evidence_scope,
        }


class RepairReplacementIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str = Field(min_length=1, max_length=100)
    skill: SkillName
    target_pixel: tuple[int, int] | None
    destination_pixel: tuple[int, int] | None


class VisualRepairIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["role.visual-repair-intent.v1"]
    binding_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    replacements: list[RepairReplacementIntent] = Field(min_length=1, max_length=100)


@dataclass(frozen=True)
class GroundedRepairStep:
    step: TaskStep
    action_evidence: ActionEvidenceContract
    source_binding_hash: str
    payload_hash: str

    def __post_init__(self) -> None:
        step = TaskStep.model_validate(self.step.model_dump())
        object.__setattr__(self, "step", step)
        object.__setattr__(
            self,
            "action_evidence",
            replace(self.action_evidence, evidence=replace(self.action_evidence.evidence)),
        )
        if self.payload_hash != replan_payload_hash(step):
            raise ValueError("grounded step payload hash mismatch")


GroundingProvider = Callable[
    [RepairReplacementIntent, TaskStep, RGBDObservation, VisualRepairContext, str],
    GroundedRepairStep,
]


class RoleVisualRepairUnavailable(RuntimeError):
    """Constant local reason codes; never expose a credential/remote response body."""


def _request_visual_json(
    planner: RGBDPlannerAdapter, messages: list[dict[str, Any]], schema: dict[str, Any]
) -> dict[str, Any]:
    """The sole private reuse seam, frozen with the existing planner implementation."""
    return planner._request_visual(messages, schema)


def authorized_window(context: VisualRepairContext, full_remaining: bool) -> RepairWindow:
    base = repair_window(context)
    if not full_remaining:
        return base
    pending = tuple(step.step_id for step in context.dependencies if not step.completed)
    if not pending:
        raise RoleVisualRepairUnavailable("pending_repair_window_empty")
    return RepairWindow(
        pending[0],
        pending,
        tuple(step.step_id for step in context.dependencies if step.completed),
        base.expected_plan_version,
        base.expected_command_seq,
    )


def _contains_execution_command(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            name
            in {
                "joint_angles",
                "joint_positions",
                "trajectory",
                "pwm",
                "servo_pulse",
                "trajectory_points",
                "disable_safety",
                "bypass_safety",
                "ignore_collision",
            }
            or _contains_execution_command(item)
            for name, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_execution_command(item) for item in value)
    return False


class RoleVisualRepairProvider:
    def __init__(
        self,
        *,
        planner: RGBDPlannerAdapter,
        binding: RoleRuntimeBinding | None,
        source: RoleVisualRepairSource,
        grounding_provider: GroundingProvider | None,
        clock: Callable[[], datetime] | None = None,
        full_remaining: bool = False,
    ) -> None:
        self.planner = planner
        self.binding = binding
        self.source = source
        self.grounding_provider = grounding_provider
        self.clock = clock or (lambda: datetime.now(UTC))
        if type(full_remaining) is not bool:
            raise ValueError("full_remaining must be a boolean")
        self.full_remaining = full_remaining
        self.last_binding_hash: str | None = None

    def validate(
        self,
        request: LocalReplanningRequest,
        window: RepairWindow,
        observation: RGBDObservation,
        context: VisualRepairContext,
    ) -> None:
        if self.binding is None or self.grounding_provider is None:
            raise RoleVisualRepairUnavailable("role_binding_or_grounding_source_missing")
        if (
            self.planner.provider != "openai_compatible"
            or self.planner.model_role != "REPLANNER"
            or not self.planner._api_key
            or not self.planner.allow_paid
            or not isinstance(self.planner.cost_ledger, CostLedger)
            or self.planner.model_snapshot is None
            or "max" not in self.planner.model_name.lower()
        ):
            raise RoleVisualRepairUnavailable("chosen_max_profile_key_or_transport_unavailable")
        self.binding.validate(self.planner)
        if not REQUIRED_SOURCES <= self.binding.bundle.cloud_snapshot.source_hashes.keys():
            raise RoleVisualRepairUnavailable("repair_source_inventory_missing")
        if self.source.source_hash != digest(self.source.payload()):
            raise RoleVisualRepairUnavailable("repair_source_mutated")
        if self.source.evidence_scope not in {"SOFTWARE_ONLY", "ACTUAL_SOURCE"}:
            raise RoleVisualRepairUnavailable("actual_source_unavailable")
        if (
            digest(context) != digest(self.source.context)
            or observation.checksum_sha256 != context.online_evidence.observation.checksum_sha256
            or request.task_id != context.active_contract.task_id
            or request.current_plan_version != context.active_contract.plan_version
            or request.current_command_seq != context.active_contract.command_seq
            or window.expected_plan_version != request.current_plan_version
            or window.expected_command_seq != request.current_command_seq
        ):
            raise RoleVisualRepairUnavailable("request_frame_or_current_context_mismatch")
        if window != authorized_window(context, self.full_remaining):
            raise RoleVisualRepairUnavailable("unauthorized_repair_window")
        try:
            complete = _inputs_valid(
                request, repair_window(context), observation, context, self.clock()
            )
        except Exception:
            complete = False
        if not complete:
            raise RoleVisualRepairUnavailable("complete_current_repair_proof_unavailable")
        online = context.online_evidence
        robot = online.robot_state
        if not robot.connected or robot.estop_engaged or robot.collision_detected:
            raise RoleVisualRepairUnavailable("actual_robot_hard_stop")
        if online.context_hash != checkpoint_hash(context):
            raise RoleVisualRepairUnavailable("current_checkpoint_context_mismatch")
        steps = {item.step_id: item for item in context.active_contract.steps}
        if set(window.replace_step_ids) & set(context.checkpoint.completed_step_ids):
            raise RoleVisualRepairUnavailable("completed_effect_replay_prohibited")
        for identity in window.replace_step_ids:
            step = steps.get(identity)
            proof = self.source.action_evidence.get(identity)
            if step is None or proof is None:
                raise RoleVisualRepairUnavailable("complete_grounding_conditions_missing")
            if self.source.evidence_scope == "ACTUAL_SOURCE" and (
                not step.preconditions or not step.success_conditions
            ):
                raise RoleVisualRepairUnavailable("actual_frozen_requirements_unavailable")
            self._validate_action(step, proof, context)

    def _validate_action(
        self, step: TaskStep, proof: ActionEvidenceContract, context: VisualRepairContext
    ) -> None:
        online = context.online_evidence
        for specs in (proof.preconditions, proof.postconditions):
            names = [spec.name for spec in specs]
            if len(names) != len(set(names)):
                raise RoleVisualRepairUnavailable("ambiguous_frozen_action_conditions")
        if (
            proof.plan_version != context.active_contract.plan_version
            or proof.command_seq != context.active_contract.command_seq
            or proof.context_hash != checkpoint_hash(context)
            or proof.evidence.observation_id != online.observation.observation_id
            or proof.expected_duration_s < max(step.timeout_ms, step.expected_duration_ms) / 1000
            or (
                step.preconditions
                and not set(step.preconditions) <= {item.name for item in proof.preconditions}
            )
            or (
                step.success_conditions
                and set(step.success_conditions) != {item.name for item in proof.postconditions}
            )
        ):
            raise RoleVisualRepairUnavailable("frozen_action_requirements_mismatch")
        for condition in (*proof.preconditions, *proof.postconditions):
            target = (
                context.active_contract.task_target.target_region_id
                if condition.name == "tcp_above_region"
                else context.active_contract.task_target.object_id
            )
            if condition.target_id is not None and condition.target_id != target:
                raise RoleVisualRepairUnavailable("condition_target_not_bound")
        verdict = validate_evidence(
            proof,
            self.clock(),
            checkpoint_hash(context),
            online.observation.calibration_version or "",
            online_evidence=online,
        )
        if verdict.status != "VALID" or not proof.postconditions:
            raise RoleVisualRepairUnavailable("actual_geometry_or_canonical_proof_unavailable")

    def __call__(
        self,
        request: LocalReplanningRequest,
        window: RepairWindow,
        observation: RGBDObservation,
        context: VisualRepairContext,
    ) -> RepairProposal:
        self.validate(request, window, observation, context)
        assert self.binding is not None and self.grounding_provider is not None
        originals = {step.step_id: step for step in context.active_contract.steps}
        bound = {
            "schema_version": PROMPT_VERSION,
            "request": plain(request),
            "window": plain(window),
            "frame": observation.evidence(),
            "context_hash": digest(context),
            "source_hash": self.source.source_hash,
            "bundle_hash": self.binding.bundle.digest(),
            "prompt_schema_hash": digest(VisualRepairIntent.model_json_schema()),
        }
        binding_hash = digest(bound)
        self.last_binding_hash = binding_hash
        envelope = {
            "schema_version": PROMPT_VERSION,
            "binding_hash": binding_hash,
            "request": {"binding_hash": digest(request)},
            "window": {"binding_hash": digest(window)},
            "frame": {"binding_hash": digest(observation.evidence())},
            "context_hash": bound["context_hash"],
            "source_hash": bound["source_hash"],
            "bundle_hash": bound["bundle_hash"],
            "prompt_schema_hash": bound["prompt_schema_hash"],
            "failure_kind": "STEP_REPAIR_REQUIRED",
            "authorized_steps": [
                {"step_id": identity, "skill": originals[identity].skill.value}
                for identity in window.replace_step_ids
            ],
        }
        instruction = (
            context.active_contract.user_instruction
            + "\nROLE_REPAIR_CONTEXT="
            + json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        )
        snapshot = self.planner.model_snapshot
        assert snapshot is not None
        messages = build_visual_messages(
            instruction,
            observation,
            image_size=snapshot.image_size,
            coordinate_system=snapshot.coordinate_system,
            decision_schema=VisualRepairIntent.model_json_schema(),
        )
        messages[0]["content"] = (
            "Inspect only the paired current RGB and depth images and supplied observable context. "
            "Return the supplied JSON schema with the binding_hash copied exactly and one "
            "replacement intent for every authorized step ID. Preserve each supplied skill. "
            "Never replay completed steps or emit joint angles, PWM, trajectories, world poses, "
            "completion or admission. Select image pixels only; local current source proof "
            "must ground them. Schema: " + json.dumps(VisualRepairIntent.model_json_schema())
        )
        response = _request_visual_json(
            self.planner,
            cast("list[dict[str, Any]]", messages),
            VisualRepairIntent.model_json_schema(),
        )
        # Do not persist or expose model text, JSON errors, headers, or credentials.
        try:
            text = response["choices"][0]["message"]["content"]
            decision = VisualRepairIntent.model_validate_json(text, strict=True)
        except Exception:
            raise RoleVisualRepairUnavailable("invalid_remote_repair_intent") from None
        self.validate(request, window, observation, context)
        if (
            decision.binding_hash != binding_hash
            or len(decision.replacements) != len(window.replace_step_ids)
            or {item.step_id for item in decision.replacements} != set(window.replace_step_ids)
        ):
            raise RoleVisualRepairUnavailable("remote_authorized_window_or_binding_changed")
        replacements = {}
        before = digest((request, window, observation, context, self.source.payload()))
        for intent in decision.replacements:
            original = originals[intent.step_id]
            if intent.skill != original.skill:
                raise RoleVisualRepairUnavailable("remote_changed_frozen_skill")
            for pixel in (intent.target_pixel, intent.destination_pixel):
                if pixel is not None:
                    model_to_observation_pixel(
                        pixel,
                        observation,
                        image_size=snapshot.image_size,
                        coordinate_system=snapshot.coordinate_system,
                    )
            if original.skill in {SkillName.GRASP, SkillName.APPROACH, SkillName.LIFT} and (
                intent.target_pixel is None
            ):
                raise RoleVisualRepairUnavailable("observed_target_pixel_missing")
            grounding_args = (
                intent.model_copy(deep=True),
                original.model_copy(deep=True),
                observation.model_copy(deep=True),
                VisualRepairContext(
                    context.active_contract,
                    context.checkpoint,
                    context.dependencies,
                    context.invalid_evidence_ids,
                    context.online_evidence,
                    context.completed_effect_conditions,
                ),
                binding_hash,
            )
            grounding_hash = digest(grounding_args)
            grounded = self.grounding_provider(*grounding_args)
            if digest(grounding_args) != grounding_hash:
                raise RoleVisualRepairUnavailable("grounding_mutated_bound_inputs")
            if not isinstance(grounded, GroundedRepairStep):
                raise RoleVisualRepairUnavailable("typed_grounding_proof_missing")
            step = grounded.step
            original_proof = self.source.action_evidence[original.step_id]
            if (
                grounded.source_binding_hash != binding_hash
                or grounded.payload_hash != replan_payload_hash(step)
                or step.step_id != original.step_id
                or step.skill != original.skill
                or step.preconditions != original.preconditions
                or step.success_conditions != original.success_conditions
                or step.expected_duration_ms != original.expected_duration_ms
                or step.timeout_ms != original.timeout_ms
                or step.retry_limit != original.retry_limit
                or digest(grounded.action_evidence.preconditions)
                != digest(original_proof.preconditions)
                or digest(grounded.action_evidence.postconditions)
                != digest(original_proof.postconditions)
                or grounded.action_evidence.allowed_error_m != original_proof.allowed_error_m
                or grounded.action_evidence.sensor_requirements
                != original_proof.sensor_requirements
                or grounded.action_evidence.ordinary_ttl_s != original_proof.ordinary_ttl_s
                or grounded.action_evidence.expected_duration_s
                != original_proof.expected_duration_s
            ):
                raise RoleVisualRepairUnavailable("grounding_changed_frozen_requirements")
            self._validate_action(step, grounded.action_evidence, context)
            if _contains_execution_command(step.parameters):
                raise RoleVisualRepairUnavailable("low_level_execution_output_prohibited")
            replacements[step.step_id] = step.model_copy(deep=True)
        if before != digest((request, window, observation, context, self.source.payload())):
            raise RoleVisualRepairUnavailable("grounding_mutated_bound_inputs")
        self.validate(request, window, observation, context)
        return RepairProposal(replacements)
