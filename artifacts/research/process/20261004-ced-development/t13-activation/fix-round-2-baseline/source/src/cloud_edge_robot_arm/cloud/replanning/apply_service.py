"""重规划应用服务，负责版本、检查点和安全前置条件校验。

Apply validated local replan results to the active TaskContract.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Protocol, cast
from uuid import uuid4

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
from cloud_edge_robot_arm.cloud.replanning.merge import (
    ReplanContractAssembler,
    ReplanMergeValidator,
)
from cloud_edge_robot_arm.contracts.models import (
    ActiveTaskContractRecord,
    CommandAck,
    ExecutionCheckpoint,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
    ReplanApplyRecord,
    ReplanApplyStatus,
    ReplanExecutionReceipt,
    ReplanScope,
    TaskContract,
    replan_payload_hash,
)
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.evidence.models import (
    ActionEvidenceContract,
    CommitContext,
    DecisionEnvelope,
    EvidenceVerdict,
)
from cloud_edge_robot_arm.edge.evidence.validator import validate_decision_commit, validate_evidence
from cloud_edge_robot_arm.repositories.event_autonomy.hashing import stable_payload_hash
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import EventAutonomyRepository


def _checkpoint_digest(checkpoint: ExecutionCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json")
    payload["checkpoint_hash"] = ""
    return replan_payload_hash(payload)


class ReplanDispatchGateway(Protocol):
    """Actual edge staging, distinct from legacy execute-on-dispatch gateways."""

    def stage(self, contract: TaskContract, repair_id: str) -> CommandAck: ...
    def resume(self, repair_id: str, activation_token: str) -> CommandAck: ...


def _freeze_mapping(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_mapping(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_mapping(item) for item in value)
    return deepcopy(value)


@dataclass(frozen=True)
class ReplanSubmitEvidence:
    """Typed canonical T10 inputs, not a caller-supplied VALID assertion.

    In this v1 boundary candidate_set_hash identifies the complete candidate
    TaskContract payload. A T12 adapter must map its own candidate-set/choice ID
    explicitly; its candidate-set hash must never be overwritten or conflated.
    """

    decision: DecisionEnvelope
    current: CommitContext
    action: ActionEvidenceContract
    online_evidence: OnlineEvidenceSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.online_evidence, OnlineEvidenceSnapshot):
            raise ValueError("actual online evidence snapshot required")
        facts = _freeze_mapping(self.online_evidence.visual_facts)
        object.__setattr__(
            self,
            "online_evidence",
            replace(
                self.online_evidence,
                robot_state=self.online_evidence.robot_state.model_copy(deep=True),
                visual_facts=cast(Mapping[str, Any], facts),
            ),
        )


ReplanSubmitGuard = Callable[
    [ReplanApplyRecord, TaskContract, ExecutionCheckpoint], ReplanSubmitEvidence
]


@dataclass(frozen=True)
class ReplanApplyResult:
    applied: bool
    record: ReplanApplyRecord
    contract: TaskContract | None
    ack: CommandAck | None
    errors: list[str]


class ReplanApplyService:
    """Single writer that applies cloud replanning output to active contracts."""

    def __init__(
        self,
        *,
        repository: EventAutonomyRepository,
        dispatcher: ReplanDispatchGateway | None = None,
        merge_validator: ReplanMergeValidator | None = None,
        assembler: ReplanContractAssembler | None = None,
        clock: Callable[[], datetime] | None = None,
        submit_guard: ReplanSubmitGuard | None = None,
    ) -> None:
        self._repo = repository
        self._dispatcher = dispatcher
        self._submit_guard = submit_guard
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._merge_validator = merge_validator or ReplanMergeValidator()
        self._assembler = assembler or ReplanContractAssembler(clock=self._clock)

    def apply(
        self,
        *,
        request: LocalReplanningRequest,
        response: LocalReplanningResponse,
        active_record: ActiveTaskContractRecord | None = None,
        failure_summary: FailureSummary | None = None,
        checkpoint: ExecutionCheckpoint | None = None,
        dispatch: bool = True,
    ) -> ReplanApplyResult:
        request = LocalReplanningRequest.model_validate(request.model_dump())
        response = LocalReplanningResponse.model_validate(response.model_dump())
        existing = self._repo.get_replan_apply_record_for_request(request.request_id)
        if existing is not None:
            if existing.request_payload_hash != stable_payload_hash(
                request
            ) or existing.response_payload_hash != stable_payload_hash(response):
                raise ValueError(
                    "replan request/response identity conflicts with durable candidate"
                )
            # Restart/retry coordinates persisted state; never replay stage/resume.
            return ReplanApplyResult(
                existing.status in {"ACTIVATED", "EXECUTION_STARTED"},
                existing,
                existing.candidate_contract.model_copy(deep=True)
                if existing.candidate_contract
                else None,
                existing.resume_ack or existing.stage_ack,
                [] if existing.status in {"ACTIVATED", "EXECUTION_STARTED"} else [existing.reason],
            )
        active_record = active_record or self._repo.get_active_contract(request.task_id)
        failure_summary = failure_summary or self._repo.get_failure_summary(
            request.failure_summary_id
        )
        checkpoint = checkpoint or self._repo.get_latest_execution_checkpoint(request.task_id)
        errors = self._validate_presence(active_record, failure_summary, checkpoint)
        if errors:
            return self._reject(request, response, None, None, errors)
        assert active_record is not None
        assert failure_summary is not None
        assert checkpoint is not None
        active_contract = active_record.contract

        if (
            active_contract.plan_version != request.current_plan_version
            or active_contract.command_seq != request.current_command_seq
        ):
            record = self._record(
                request,
                response,
                active_record,
                checkpoint,
                status=ReplanApplyStatus.REJECTED.value,
                reason="VERSION_CONFLICT: active contract version changed before apply",
                contract=None,
                ack=None,
            )
            return ReplanApplyResult(False, record, None, None, [record.reason])

        errors = self._validate_identity_and_versions(
            request=request,
            response=response,
            active_record=active_record,
            active_contract=active_contract,
            failure_summary=failure_summary,
            checkpoint=checkpoint,
        )
        if response.outcome in {"REQUEST_MORE_OBSERVATION", "MORE_OBSERVATION_REQUIRED"}:
            record = self._record(
                request,
                response,
                active_record,
                checkpoint,
                status=ReplanApplyStatus.REJECTED.value,
                reason="more observation required",
                contract=None,
                ack=None,
            )
            self._repo.save_state(
                request.task_id,
                "WAITING_FOR_NEW_OBSERVATION",
                record.reason,
                request.trigger_event_id,
            )
            return ReplanApplyResult(False, record, None, None, [])
        if (
            request.requested_replan_scope == ReplanScope.NO_REPLAN_SAFETY_STOP.value
            or response.outcome == "NO_REPLAN_SAFETY_STOP"
        ):
            record = self._record(
                request,
                response,
                active_record,
                checkpoint,
                status=ReplanApplyStatus.REJECTED.value,
                reason="safety stop requested",
                contract=None,
                ack=None,
            )
            self._repo.save_state(
                request.task_id, "SAFETY_STOPPED", record.reason, request.trigger_event_id
            )
            return ReplanApplyResult(False, record, None, None, [])
        if response.outcome != "REPLANNED":
            errors.append(f"response outcome {response.outcome} is not executable")
        if errors:
            return self._reject(request, response, active_record, checkpoint, errors)

        candidate_ok, candidate_errors = self._merge_validator.validate_candidate(
            request=request,
            response=response,
            active_contract=active_contract,
            checkpoint=checkpoint,
        )
        if not candidate_ok:
            return self._reject(request, response, active_record, checkpoint, candidate_errors)

        new_contract = self._assembler.assemble(
            active_contract=active_contract,
            request=request,
            response=response,
            checkpoint=checkpoint,
        )
        contract_errors = self._validate_new_contract(new_contract, checkpoint)
        if contract_errors:
            return self._reject(request, response, active_record, checkpoint, contract_errors)

        prepared = self._record(
            request,
            response,
            active_record,
            checkpoint,
            status="PREPARED",
            reason="candidate prepared; awaiting guarded edge staging",
            contract=new_contract,
            ack=None,
        )
        if (
            not dispatch
            or self._submit_guard is None
            or self._dispatcher is None
            or not callable(getattr(self._dispatcher, "stage", None))
            or not callable(getattr(self._dispatcher, "resume", None))
        ):
            return ReplanApplyResult(False, prepared, new_contract, None, [])
        active_now = self._repo.get_active_contract(request.task_id)
        if (
            active_now is None
            or active_now.plan_version != prepared.previous_plan_version
            or active_now.command_seq != prepared.previous_command_seq
            or active_now.plan_id != prepared.plan_id
            or active_now.robot_id != prepared.robot_id
        ):
            return ReplanApplyResult(
                False, prepared, new_contract, None, ["active contract changed before stage"]
            )
        try:
            prepared = self._transition(
                prepared, status="PREPARED", reason=prepared.reason, stage_attempt_id=uuid4().hex
            )
            current_checkpoint = self._repo.get_latest_execution_checkpoint(request.task_id)
            active_now = self._repo.get_active_contract(request.task_id)
            if (
                current_checkpoint is None
                or active_now is None
                or active_now.plan_version != prepared.previous_plan_version
                or active_now.command_seq != prepared.previous_command_seq
            ):
                return ReplanApplyResult(
                    False,
                    prepared,
                    new_contract,
                    None,
                    ["checkpoint/active version unavailable after stage claim"],
                )
            verdict = self._submit_verdict(
                prepared, current_checkpoint, self._cancelled(request.task_id)
            )
            if verdict.status != "VALID":
                return ReplanApplyResult(False, prepared, new_contract, None, list(verdict.reasons))
            stage_ack = self._dispatcher.stage(
                new_contract.model_copy(deep=True), prepared.repair_id
            )
            if not isinstance(stage_ack, CommandAck):
                raise ValueError("stage gateway did not return an actual CommandAck")
            stage_ack = CommandAck.model_validate(stage_ack.model_dump(), strict=True)
        except (ValueError, TimeoutError, OSError) as exc:
            durable = self._repo.get_replan_apply_record(prepared.apply_id) or prepared
            return ReplanApplyResult(False, durable, new_contract, None, [str(exc)])
        try:
            prepared.validate_ack(stage_ack)
            if stage_ack.timestamp > self._clock():
                raise ValueError("future stage acknowledgement")
        except ValueError as exc:
            rejected = self._transition(
                prepared,
                status="REJECTED",
                reason=str(exc),
                stage_ack=stage_ack,
                ack_status=stage_ack.status,
            )
            return ReplanApplyResult(False, rejected, new_contract, stage_ack, [str(exc)])
        accepted = self._transition(
            prepared,
            status="EDGE_ACCEPTED",
            reason="edge staged candidate",
            stage_ack=stage_ack,
            activation_token=stage_ack.details["activation_token"],
            accepted_plan_version=new_contract.plan_version,
            accepted_command_seq=new_contract.command_seq,
            ack_status=stage_ack.status,
        )
        activated = self._updated(
            accepted, status="ACTIVATED", reason="active contract advanced after guarded stage"
        )
        updated = self._repo.advance_active_contract_if_current(
            task_id=request.task_id,
            expected_plan_version=request.current_plan_version,
            expected_command_seq=request.current_command_seq,
            new_contract=new_contract,
            plan_id=prepared.plan_id,
            robot_id=prepared.robot_id,
            based_on_plan_version=checkpoint.plan_version,
            correlation_id=request.correlation_id,
            replan_record=activated,
            activation_guard=self._submit_verdict,
        )
        if updated is None:
            return ReplanApplyResult(
                False,
                accepted,
                new_contract,
                stage_ack,
                ["activation guard/checkpoint/version/cancellation conflict"],
            )
        activated_record = self._repo.get_replan_apply_record(prepared.apply_id)
        assert activated_record is not None
        durable = activated_record
        # Resume is a second physical boundary: re-read checkpoint, cancel and proof.
        current_checkpoint = self._repo.get_latest_execution_checkpoint(request.task_id)
        active_now = self._repo.get_active_contract(request.task_id)
        if (
            current_checkpoint is None
            or active_now is None
            or active_now.contract_hash != durable.payload_hash
        ):
            return ReplanApplyResult(
                True,
                durable,
                new_contract,
                stage_ack,
                ["activation awaits edge checkpoint coordination"],
            )
        verdict = self._submit_verdict(
            durable, current_checkpoint, self._cancelled(request.task_id)
        )
        if verdict.status != "VALID":
            return ReplanApplyResult(True, durable, new_contract, stage_ack, list(verdict.reasons))
        try:
            resume_ack = self._dispatcher.resume(durable.repair_id, durable.activation_token)
            if not isinstance(resume_ack, CommandAck):
                raise ValueError("resume gateway did not return an actual CommandAck")
            resume_ack = CommandAck.model_validate(resume_ack.model_dump(), strict=True)
            durable.validate_ack(
                resume_ack, token=durable.activation_token, require_acceptance=False
            )
            if resume_ack.timestamp > self._clock():
                raise ValueError("future resume acknowledgement")
            durable = self._transition(
                durable, status="ACTIVATED", reason=durable.reason, resume_ack=resume_ack
            )
            return ReplanApplyResult(
                True,
                durable,
                new_contract,
                resume_ack,
                []
                if resume_ack.accepted and resume_ack.status == "ACCEPTED"
                else ["actual resume acknowledgement rejected; coordination required"],
            )
        except (ValueError, TimeoutError, OSError) as exc:
            # The activated version is durable. No rollback or automatic replay.
            return ReplanApplyResult(True, durable, new_contract, stage_ack, [str(exc)])

    def _cancelled(self, task_id: str) -> bool:
        return self._repo.get_state(task_id) in {
            "CANCELLED",
            "ABORTED",
            "STOPPED",
            "SAFETY_STOPPED",
            "COMPLETED",
        } or any(
            event.severity == "CRITICAL" or event.event_type.value == "MANUAL_INTERRUPT"
            for event in self._repo.list_events(task_id)
        )

    def _submit_verdict(
        self,
        record: ReplanApplyRecord,
        checkpoint: ExecutionCheckpoint,
        cancelled: bool,
    ) -> EvidenceVerdict:
        """Pure repository-CAS callback: no repository reads or writes inside it."""
        if self._submit_guard is None or record.candidate_contract is None or cancelled:
            return EvidenceVerdict("INVALID", ("submit_guard_missing_or_cancelled",))
        checkpoint_hash = _checkpoint_digest(checkpoint)
        if (
            checkpoint.checkpoint_id != record.checkpoint_id
            or checkpoint_hash != record.checkpoint_hash
            or checkpoint.execution_state in {"COMPLETED", "SAFETY_STOPPED"}
            or checkpoint.task_id != record.task_id
            or checkpoint.plan_id != record.plan_id
            or checkpoint.robot_id != record.robot_id
            or checkpoint.plan_version != record.previous_plan_version
            or checkpoint.command_seq != record.previous_command_seq
        ):
            return EvidenceVerdict("INVALID", ("current_checkpoint_changed",))
        candidate = record.candidate_contract.model_copy(deep=True)
        guard_record = record.model_copy(deep=True)
        guard_checkpoint = checkpoint.model_copy(deep=True)
        try:
            proof = self._submit_guard(guard_record, candidate, guard_checkpoint)
            if (
                not isinstance(proof, ReplanSubmitEvidence)
                or stable_payload_hash(candidate) != record.payload_hash
                or guard_record.content_hash() != record.content_hash()
                or _checkpoint_digest(guard_checkpoint) != checkpoint_hash
            ):
                return EvidenceVerdict("INVALID", ("typed_submit_proof_missing_or_input_mutated",))
            current, decision, action, online = (
                proof.current,
                proof.decision,
                proof.action,
                proof.online_evidence,
            )
            pending = [
                step for step in candidate.steps if step.step_id not in record.completed_step_ids
            ]
            if (
                not pending
                or current.task_id != record.task_id
                or current.candidate_set_hash != record.payload_hash
                or current.context_hash != checkpoint_hash
                or current.cancelled
                or current.plan_version != candidate.plan_version
                or current.command_seq != candidate.command_seq
                or decision.action != DecisionAction.LOCAL_RECOVER
                or current.episode_id != online.observation.episode_id
                or current.observation_id != online.observation.observation_id
                or action.plan_version != candidate.plan_version
                or action.command_seq != candidate.command_seq
                or action.context_hash != checkpoint_hash
                or tuple(spec.name for spec in action.preconditions)
                != tuple(pending[0].preconditions)
                or tuple(spec.name for spec in action.postconditions)
                != tuple(pending[0].success_conditions)
                or action.expected_duration_s
                < sum(step.expected_duration_ms for step in pending) / 1000
            ):
                return EvidenceVerdict(
                    "INVALID", ("submit_proof_candidate_context_action_binding_mismatch",)
                )
            object_target = pending[0].parameters.get("object_id", candidate.task_target.object_id)
            region_target = pending[0].parameters.get(
                "region_id", candidate.task_target.target_region_id
            )
            for condition in (*action.preconditions, *action.postconditions):
                if condition.target_id is not None:
                    expected_target = (
                        region_target if condition.name == "tcp_above_region" else object_target
                    )
                    if not expected_target or condition.target_id != expected_target:
                        return EvidenceVerdict(
                            "INVALID", ("condition_target_not_bound_to_candidate",)
                        )
                elif condition.name in {
                    "target_visible",
                    "target_reachable",
                    "tcp_above_target",
                    "tcp_near_target",
                    "tcp_above_region",
                    "object_inside_target_region",
                    "object_grasped",
                    "object_held",
                    "object_attached",
                    "object_lifted",
                    "object_stable",
                    "robot_clear_of_object",
                }:
                    return EvidenceVerdict(
                        "INVALID", ("candidate_visual_condition_target_missing",)
                    )
            now = self._clock()
            if now >= candidate.valid_until:
                return EvidenceVerdict("INVALID", ("candidate_expired",))
            verdict = validate_decision_commit(decision, current, now)
            if verdict.status != "VALID":
                return verdict
            return validate_evidence(
                action,
                now,
                checkpoint_hash,
                online.observation.calibration_version or "",
                online_evidence=online,
            )
        except (ValueError, TypeError, AttributeError, KeyError):
            return EvidenceVerdict("INVALID", ("submit_proof_invalid",))

    @staticmethod
    def _updated(record: ReplanApplyRecord, **changes: object) -> ReplanApplyRecord:
        payload = {**record.model_dump(), **changes, "apply_hash": ""}
        return ReplanApplyRecord.model_validate(payload)

    def _transition(self, record: ReplanApplyRecord, **changes: object) -> ReplanApplyRecord:
        updated = self._updated(record, **changes)
        saved = self._repo.update_replan_apply_record_if_current(
            updated, expected_status=record.status
        )
        if saved is None:
            raise ValueError("replan stage transition conflict")
        return saved

    def confirm_execution_started(self, receipt: ReplanExecutionReceipt) -> ReplanApplyResult:
        receipt = ReplanExecutionReceipt.model_validate(receipt.model_dump())
        record = self._repo.get_replan_apply_record(receipt.repair_id)
        if record is None or record.repair_id != receipt.repair_id:
            raise ValueError("unknown repair execution receipt")
        active = self._repo.get_active_contract(receipt.task_id)
        if (
            active is None
            or active.plan_version != receipt.plan_version
            or active.command_seq != receipt.command_seq
            or active.contract_hash != receipt.payload_hash
        ):
            raise ValueError("execution receipt references an old active contract")
        if record.start_receipt is not None:
            if record.start_receipt == receipt:
                saved = self._repo.update_replan_apply_record_if_current(
                    record, expected_status=record.status
                )
                if saved is None:
                    raise ValueError("execution receipt references an old active contract")
                return self._started_result(saved)
            raise ValueError("conflicting execution start receipt")
        if (
            record.status != "ACTIVATED"
            or receipt.started_at < record.created_at
            or receipt.started_at > self._clock()
        ):
            raise ValueError("execution receipt is not current activated start")
        started = self._transition(
            record,
            status="EXECUTION_STARTED",
            reason="edge execution start received",
            start_receipt=receipt,
            executing_plan_version=receipt.plan_version,
            executing_command_seq=receipt.command_seq,
        )
        return self._started_result(started)

    @staticmethod
    def _started_result(record: ReplanApplyRecord) -> ReplanApplyResult:
        return ReplanApplyResult(
            True, record,
            record.candidate_contract.model_copy(deep=True) if record.candidate_contract else None,
            record.resume_ack or record.stage_ack, [],
        )

    def _validate_presence(
        self,
        active_record: ActiveTaskContractRecord | None,
        failure_summary: FailureSummary | None,
        checkpoint: ExecutionCheckpoint | None,
    ) -> list[str]:
        errors: list[str] = []
        if active_record is None:
            errors.append("active contract not found")
        if failure_summary is None:
            errors.append("failure summary not found")
        if checkpoint is None:
            errors.append("checkpoint not found")
        return errors

    def _validate_identity_and_versions(
        self,
        *,
        request: LocalReplanningRequest,
        response: LocalReplanningResponse,
        active_record: ActiveTaskContractRecord,
        active_contract: TaskContract,
        failure_summary: FailureSummary,
        checkpoint: ExecutionCheckpoint,
    ) -> list[str]:
        errors: list[str] = []
        event = self._repo.get_event(request.trigger_event_id)
        if event is None:
            errors.append("trigger event not found")
        elif event.task_id != request.task_id:
            errors.append("event task_id mismatch")
        if event is not None and (
            event.plan_version != request.current_plan_version
            or event.command_seq != request.current_command_seq
            or event.step_id != request.failed_step_id
        ):
            errors.append("trigger event version/step mismatch")
        if (
            failure_summary.plan_version != request.current_plan_version
            or failure_summary.command_seq != request.current_command_seq
            or failure_summary.failed_step_id != request.failed_step_id
            or list(failure_summary.completed_step_ids) != list(checkpoint.completed_step_ids)
        ):
            errors.append("failure summary version/step/completed-prefix mismatch")
        if failure_summary.task_id != request.task_id:
            errors.append("failure summary task_id mismatch")
        if failure_summary.failure_event_id != request.trigger_event_id:
            errors.append("failure summary event mismatch")
        if active_contract.task_id != request.task_id:
            errors.append("active contract task_id mismatch")
        if active_record.robot_id != request.robot_id:
            errors.append("robot_id mismatch")
        if active_record.plan_id != request.plan_id:
            errors.append("plan_id mismatch")
        if checkpoint.task_id != request.task_id:
            errors.append("checkpoint task_id mismatch")
        if checkpoint.robot_id != request.robot_id:
            errors.append("checkpoint robot_id mismatch")
        if checkpoint.plan_id != request.plan_id:
            errors.append("checkpoint plan_id mismatch")
        if checkpoint.plan_version != request.current_plan_version:
            errors.append("checkpoint plan_version mismatch")
        if checkpoint.command_seq != request.current_command_seq:
            errors.append("checkpoint command_seq mismatch")
        if list(request.completed_step_ids) != list(checkpoint.completed_step_ids):
            errors.append("completed_step_ids mismatch")
        if request.failed_step_id and request.failed_step_id not in {
            s.step_id for s in active_contract.steps
        }:
            errors.append("failed step not in active contract")
        if request.current_scene_version < checkpoint.scene_version:
            errors.append("scene_version regressed")
        if response.request_id != request.request_id:
            errors.append("response request_id mismatch")
        if response.created_at >= active_contract.valid_until:
            errors.append("replan result expired")
        if checkpoint.execution_state in {"COMPLETED", "SAFETY_STOPPED"}:
            errors.append("checkpoint is terminal")
        critical = [
            event
            for event in self._repo.list_events(request.task_id)
            if event.severity == "CRITICAL"
        ]
        if critical:
            errors.append("unhandled critical event exists")
        return errors

    def _validate_new_contract(
        self,
        contract: TaskContract,
        checkpoint: ExecutionCheckpoint,
    ) -> list[str]:
        errors: list[str] = []
        validation = EdgeContractValidator(min_plan_version=1).accept_payload(
            contract.model_dump(mode="json"),
            now=self._clock(),
        )
        if not validation.accepted:
            errors.append(
                validation.error.code if validation.error else "contract validation failed"
            )
        if contract.scene_version < checkpoint.scene_version:
            errors.append("new contract scene_version is older than checkpoint")
        completed = set(checkpoint.completed_step_ids)
        prefix = [step.step_id for step in contract.steps[: len(completed)]]
        if not completed.issubset({step.step_id for step in contract.steps}):
            errors.append("completed step missing from new contract")
        if completed and prefix != checkpoint.completed_step_ids[: len(prefix)]:
            errors.append("completed step prefix changed")
        return errors

    def _record(
        self,
        request: LocalReplanningRequest,
        response: LocalReplanningResponse,
        active_record: ActiveTaskContractRecord | None,
        checkpoint: ExecutionCheckpoint | None,
        *,
        status: str,
        reason: str,
        contract: TaskContract | None,
        ack: CommandAck | None,
    ) -> ReplanApplyRecord:
        record = ReplanApplyRecord(
            apply_id=f"apply-{request.request_id}",
            request_id=request.request_id,
            task_id=request.task_id,
            plan_id=request.plan_id,
            robot_id=request.robot_id,
            previous_plan_version=request.current_plan_version,
            previous_command_seq=request.current_command_seq,
            new_plan_version=response.new_plan_version,
            new_command_seq=response.new_command_seq,
            checkpoint_id=checkpoint.checkpoint_id if checkpoint else "",
            status=status,
            reason=reason,
            completed_step_ids=list(checkpoint.completed_step_ids) if checkpoint else [],
            applied_step_ids=[step.step_id for step in contract.steps] if contract else [],
            ack_status=ack.status if ack else "",
            correlation_id=request.correlation_id,
            created_at=self._clock(),
            repair_id=f"apply-{request.request_id}" if contract else "",
            candidate_contract=contract.model_copy(deep=True) if contract else None,
            candidate_plan_version=contract.plan_version if contract else None,
            candidate_command_seq=contract.command_seq if contract else None,
            payload_hash=stable_payload_hash(contract) if contract else "",
            checkpoint_hash=_checkpoint_digest(checkpoint) if checkpoint else "",
            request_payload_hash=stable_payload_hash(request),
            response_payload_hash=stable_payload_hash(response),
        )
        record = record.model_copy(
            update={"apply_hash": record.content_hash()},
            deep=True,
        )
        return self._repo.save_replan_apply_record(record)

    def _reject(
        self,
        request: LocalReplanningRequest,
        response: LocalReplanningResponse,
        active_record: ActiveTaskContractRecord | None,
        checkpoint: ExecutionCheckpoint | None,
        errors: list[str],
    ) -> ReplanApplyResult:
        ack = None
        record = self._record(
            request,
            response,
            active_record,
            checkpoint,
            status=ReplanApplyStatus.REJECTED.value,
            reason="; ".join(errors),
            contract=None,
            ack=ack,
        )
        return ReplanApplyResult(False, record, None, ack, errors)
