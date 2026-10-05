"""Build a source-bound remaining-task candidate; never submit or execute it.

The unchanged ReplanApplyService owns activation and submit-time safety/evidence
checks. This builder cannot resolve recovery, certify a physical result or provide
compensation for a lost completed effect.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from cloud_edge_robot_arm.cloud.replanning.merge import ReplanMergeValidator
from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import (
    RepairWindow,
    StepDependency,
    find_repair_window,
)
from cloud_edge_robot_arm.contracts.models import (
    ExecutionCheckpoint,
    LocalReplanningRequest,
    LocalReplanningResponse,
    TaskContract,
    TaskStep,
)
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    ConditionStatus,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _copy_data(value: Any) -> Any:
    """Copy native frozen facts without deepcopying non-pickleable mapping proxies."""
    if isinstance(value, Mapping):
        return {key: _copy_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_copy_data(item) for item in value)
    if isinstance(value, list):
        return [_copy_data(item) for item in value]
    return deepcopy(value)


@dataclass(frozen=True)
class VisualRepairContext:
    active_contract: TaskContract
    checkpoint: ExecutionCheckpoint
    dependencies: Sequence[StepDependency]
    invalid_evidence_ids: frozenset[str]
    online_evidence: OnlineEvidenceSnapshot
    completed_effect_conditions: Mapping[str, Sequence[ConditionSpec]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_contract", self.active_contract.model_copy(deep=True))
        object.__setattr__(self, "checkpoint", self.checkpoint.model_copy(deep=True))
        object.__setattr__(self, "dependencies", tuple(replace(step) for step in self.dependencies))
        object.__setattr__(self, "invalid_evidence_ids", frozenset(self.invalid_evidence_ids))
        online = self.online_evidence
        object.__setattr__(self, "online_evidence", OnlineEvidenceSnapshot(
            online.observation.model_copy(deep=True), online.robot_state.model_copy(deep=True),
            _copy_data(online.visual_facts), online.plan_version, online.command_seq,
            online.context_hash,
        ))
        object.__setattr__(self, "completed_effect_conditions", MappingProxyType({
            identity: tuple(ConditionSpec(
                spec.name, spec.target_id, _copy_data(spec.tolerances),
                tuple(spec.sensor_requirements),
            ) for spec in specs)
            for identity, specs in self.completed_effect_conditions.items()
        }))


@dataclass(frozen=True)
class RepairProposal:
    replacements: Mapping[str, TaskStep]

    def __post_init__(self) -> None:
        object.__setattr__(self, "replacements", MappingProxyType({
            identity: TaskStep.model_validate(step.model_dump())
            for identity, step in self.replacements.items()
        }))


RepairProvider = Callable[
    [LocalReplanningRequest, RepairWindow, RGBDObservation, VisualRepairContext], RepairProposal
]


def repair_window(context: VisualRepairContext) -> RepairWindow:
    return find_repair_window(
        context.dependencies, set(context.invalid_evidence_ids),
        expected_plan_version=context.active_contract.plan_version,
        expected_command_seq=context.active_contract.command_seq,
    )


def _payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {key: _payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_payload(item) for item in value]
        return sorted(items) if isinstance(value, (set, frozenset)) else items
    if hasattr(value, "__dataclass_fields__"):
        return {key: _payload(getattr(value, key)) for key in value.__dataclass_fields__}
    return value


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        _payload(value), sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _copy(context: VisualRepairContext) -> VisualRepairContext:
    return VisualRepairContext(
        context.active_contract, context.checkpoint, context.dependencies,
        context.invalid_evidence_ids, context.online_evidence, context.completed_effect_conditions,
    )


def _inputs_valid(
    request: LocalReplanningRequest, window: RepairWindow, observation: RGBDObservation,
    context: VisualRepairContext, now: datetime,
) -> bool:
    contract, checkpoint, online = (
        context.active_contract, context.checkpoint, context.online_evidence,
    )
    if now.tzinfo is None or request.requested_at.tzinfo is None or (
        request.task_id != contract.task_id or checkpoint.task_id != contract.task_id
        or request.plan_id != checkpoint.plan_id or request.robot_id != checkpoint.robot_id
        or (request.current_plan_version, request.current_command_seq)
        != (contract.plan_version, contract.command_seq)
        or (checkpoint.plan_version, checkpoint.command_seq)
        != (contract.plan_version, contract.command_seq)
        or (online.plan_version, online.command_seq)
        != (contract.plan_version, contract.command_seq)
        or request.completed_step_ids != checkpoint.completed_step_ids
        or observation.checksum_sha256 != online.observation.checksum_sha256
        or not observation.episode_id or not observation.calibration_version
        or not request.requested_at < observation.captured_at <= now < contract.valid_until
        or (now - observation.captured_at).total_seconds() > 5
        or request.requested_replan_scope not in {
            "FAILED_STEP_AND_REMAINING", "REMAINING_STEPS", "FULL_PLAN_REQUIRED",
        }
    ):
        return False
    # Revalidate transport bytes instead of trusting model_copy's cached checksum.
    RGBDObservation.model_validate(observation.model_dump())
    RGBDObservation.model_validate(online.observation.model_dump())
    if repair_window(context) != window or not window.replace_step_ids:
        return False
    identities = [step.step_id for step in contract.steps]
    completed = set(checkpoint.completed_step_ids)
    if (
        len(identities) != len(set(identities))
        or identities[:len(completed)] != checkpoint.completed_step_ids
        or [step.step_id for step in context.dependencies] != identities
        or any(step.completed != (step.step_id in completed) for step in context.dependencies)
        or request.failed_step_id not in window.replace_step_ids
    ):
        return False
    for step, dependency in zip(contract.steps, context.dependencies, strict=True):
        if step.step_id not in completed:
            continue
        if dependency.physical_effect_id is None and step.skill.value in {
            "GRASP", "PLACE", "RELEASE",
        }:
            return False
        if dependency.physical_effect_id is None:
            continue
        specs = context.completed_effect_conditions.get(step.step_id, ())
        if not specs or tuple(spec.name for spec in specs) != tuple(step.success_conditions):
            return False
        for spec in specs:
            if spec.target_id is not None:
                target = (contract.task_target.target_region_id if spec.name == "tcp_above_region"
                          else contract.task_target.object_id)
                if spec.target_id != target:
                    return False
        verdicts = evaluate_conditions(specs, online, now=now)
        if not verdicts or any(verdict.status != ConditionStatus.PASS for verdict in verdicts):
            return False
    return True


def build_visual_repair(
    request: LocalReplanningRequest, window: RepairWindow, observation: RGBDObservation,
    *, context: VisualRepairContext | None = None, provider: RepairProvider | None = None,
    full_remaining: bool = False, clock: Callable[[], datetime] | None = None,
) -> LocalReplanningResponse:
    """Return a validated candidate or an explicit response with no executable steps.

    Provider inputs are isolated and their full hashes are rechecked. B4 changes
    only the replacement window on the same original failure/frame/context inputs.
    Canonical completed-effect verification and ordinary merge safety apply equally.
    """
    acquired_clock = clock or (lambda: datetime.now(UTC))
    request = LocalReplanningRequest.model_validate(request.model_dump())

    def unavailable(
        reason: str, outcome: str = "MORE_OBSERVATION_REQUIRED",
        *, now: datetime | None = None,
    ) -> LocalReplanningResponse:
        return LocalReplanningResponse(
            request_id=request.request_id, outcome=outcome, reason=reason,
            new_plan_version=request.current_plan_version,
            new_command_seq=request.current_command_seq, created_at=now or acquired_clock(),
            planner_name="visual-repair-unavailable", correlation_id=request.correlation_id,
        )

    if context is None or provider is None:
        return unavailable("typed_context_or_actual_provider_missing")
    try:
        current = _copy(context)
        if not _inputs_valid(request, window, observation, current, acquired_clock()):
            return unavailable("current_visual_repair_proof_unavailable")
        selected_window = replace(window)
        if full_remaining:
            pending = tuple(step.step_id for step in current.dependencies if not step.completed)
            selected_window = RepairWindow(
                pending[0], pending,
                tuple(step.step_id for step in current.dependencies if step.completed),
                window.expected_plan_version, window.expected_command_seq,
            )
        provider_request, provider_context = request.model_copy(deep=True), _copy(current)
        provider_observation = observation.model_copy(deep=True)
        before = _hash((provider_request, provider_context, selected_window, provider_observation))
        try:
            proposal = provider(
                provider_request, selected_window, provider_observation, provider_context,
            )
        except Exception:
            return unavailable("actual_provider_failed", "PLANNER_FAILED")
        after = _hash((provider_request, provider_context, selected_window, provider_observation))
        if before != after:
            return unavailable("provider_mutated_bound_inputs", "PLANNER_FAILED")
        if not _inputs_valid(request, window, observation, current, acquired_clock()):
            return unavailable("evidence_expired_after_provider")
        if not isinstance(proposal, RepairProposal) or (
            set(proposal.replacements) != set(selected_window.replace_step_ids)
        ):
            return unavailable("provider_changed_authorized_window", "PLANNER_FAILED")
        replacements = {identity: TaskStep.model_validate(step.model_dump())
                        for identity, step in proposal.replacements.items()}
        pending_steps: list[TaskStep] = []
        for step in current.active_contract.steps:
            if step.step_id in current.checkpoint.completed_step_ids:
                continue
            replacement = replacements.get(step.step_id)
            if replacement is not None and not set(step.preconditions) <= set(
                replacement.preconditions
            ):
                return unavailable("provider_removed_preconditions", "PLANNER_FAILED")
            pending_steps.append((replacement or step).model_copy(deep=True))
        published_at = acquired_clock()
        if not _inputs_valid(request, window, observation, current, published_at):
            return unavailable("evidence_expired_at_publication", now=published_at)
        response = LocalReplanningResponse(
            request_id=request.request_id, outcome="REPLANNED", new_steps=pending_steps,
            new_plan_version=request.current_plan_version + 1,
            new_command_seq=request.current_command_seq + 1, created_at=published_at,
            planner_name="visual-repair-b4" if full_remaining else "visual-repair-local",
            reason="source_bound_candidate_requires_submit_revalidation",
            correlation_id=request.correlation_id,
        )
        valid, errors = ReplanMergeValidator().validate_candidate(
            request=request, response=response, active_contract=current.active_contract,
            checkpoint=current.checkpoint,
        )
        return response if valid else unavailable(";".join(errors), "PLANNER_FAILED")
    except (ValueError, TypeError, KeyError, AttributeError):
        return unavailable("invalid_visual_repair_inputs", "PLANNER_FAILED")
