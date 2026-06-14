"""Apply validated local replan results to the active TaskContract."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from cloud_edge_robot_arm.cloud.replanning.merge import (
    ReplanContractAssembler,
    ReplanMergeValidator,
)
from cloud_edge_robot_arm.contracts.models import (
    ActiveTaskContractRecord,
    CommandAck,
    CommandAckStatus,
    ExecutionCheckpoint,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
    ReplanApplyRecord,
    ReplanApplyStatus,
    ReplanScope,
    TaskContract,
)
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator
from cloud_edge_robot_arm.errors import StructuredError
from cloud_edge_robot_arm.repositories.event_autonomy.hashing import stable_payload_hash
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import EventAutonomyRepository


class ReplanDispatchGateway(Protocol):
    def dispatch(self, contract: TaskContract) -> object: ...


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
    ) -> None:
        self._repo = repository
        self._dispatcher = dispatcher
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
                status=ReplanApplyStatus.VERSION_CONFLICT.value,
                reason="active contract version changed before apply",
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
                status=ReplanApplyStatus.WAITING_FOR_NEW_OBSERVATION.value,
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
                status=ReplanApplyStatus.SAFETY_STOPPED.value,
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

        updated = self._repo.advance_active_contract_if_current(
            task_id=request.task_id,
            expected_plan_version=request.current_plan_version,
            expected_command_seq=request.current_command_seq,
            new_contract=new_contract,
            plan_id=request.plan_id or active_record.plan_id,
            robot_id=request.robot_id,
            based_on_plan_version=checkpoint.plan_version,
            correlation_id=request.correlation_id,
        )
        if updated is None:
            record = self._record(
                request,
                response,
                active_record,
                checkpoint,
                status=ReplanApplyStatus.VERSION_CONFLICT.value,
                reason="active contract version changed before apply",
                contract=None,
                ack=None,
            )
            return ReplanApplyResult(False, record, None, None, [record.reason])

        ack = self._edge_ack(request, updated.contract, checkpoint, dispatch=dispatch)
        status = (
            ReplanApplyStatus.APPLIED.value if ack.accepted else ReplanApplyStatus.REJECTED.value
        )
        record = self._record(
            request,
            response,
            active_record,
            checkpoint,
            status=status,
            reason="applied" if ack.accepted else ack.status,
            contract=updated.contract,
            ack=ack,
        )
        self._repo.save_state_transition(
            request.task_id,
            "WAITING_CLOUD_REPLAN",
            "REPLAN_RECEIVED",
            "replan result received",
            request.trigger_event_id,
        )
        self._repo.save_state_transition(
            request.task_id,
            "REPLAN_RECEIVED",
            "VALIDATING_REPLAN",
            "validating replan",
            request.trigger_event_id,
        )
        self._repo.save_state_transition(
            request.task_id,
            "VALIDATING_REPLAN",
            "APPLYING_REPLAN",
            "applying replan",
            request.trigger_event_id,
        )
        self._repo.save_state_transition(
            request.task_id,
            "APPLYING_REPLAN",
            "WAITING_EDGE_ACK",
            "waiting edge ack",
            request.trigger_event_id,
        )
        if ack.accepted:
            self._repo.save_state_transition(
                request.task_id,
                "WAITING_EDGE_ACK",
                "READY_TO_RESUME",
                "edge ack accepted",
                request.trigger_event_id,
            )
            return ReplanApplyResult(True, record, updated.contract, ack, [])
        return ReplanApplyResult(False, record, None, ack, [ack.status])

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

    def _edge_ack(
        self,
        request: LocalReplanningRequest,
        contract: TaskContract,
        checkpoint: ExecutionCheckpoint,
        *,
        dispatch: bool,
    ) -> CommandAck:
        now = self._clock()
        status = CommandAckStatus.ACCEPTED.value
        accepted = True
        if not dispatch:
            status = CommandAckStatus.ACCEPTED.value
        elif self._dispatcher is None:
            status = CommandAckStatus.REJECTED_SAFETY_CONFLICT.value
            accepted = False
        else:
            result = self._dispatcher.dispatch(contract)
            edge_accepted = bool(
                getattr(result, "edge_accepted", getattr(result, "accepted", False))
            )
            dispatched = bool(getattr(result, "dispatched", edge_accepted))
            accepted = dispatched and edge_accepted
            status = (
                CommandAckStatus.ACCEPTED.value
                if accepted
                else CommandAckStatus.REJECTED_SAFETY_CONFLICT.value
            )
        ack = CommandAck(
            task_id=request.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            timestamp=now,
            accepted=accepted,
            status=status,
            request_id=request.request_id,
            checkpoint_id=checkpoint.checkpoint_id,
            correlation_id=request.correlation_id,
            details={"plan_id": request.plan_id},
        )
        return self._repo.save_command_ack(ack)

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
        )
        record = record.model_copy(
            update={"apply_hash": stable_payload_hash(record, ignore_fields={"apply_hash"})},
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
        now = self._clock()
        ack = None
        if checkpoint is not None:
            ack = self._repo.save_command_ack(
                CommandAck(
                    task_id=request.task_id,
                    plan_version=response.new_plan_version or request.current_plan_version,
                    command_seq=response.new_command_seq or request.current_command_seq,
                    timestamp=now,
                    accepted=False,
                    status=CommandAckStatus.REJECTED_SEMANTIC_INVALID.value,
                    error=StructuredError(
                        code="REPLAN_APPLY_REJECTED",
                        message="; ".join(errors),
                        category="REPLAN_APPLY",
                    ),
                    request_id=request.request_id,
                    checkpoint_id=checkpoint.checkpoint_id,
                    correlation_id=request.correlation_id,
                )
            )
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
