"""Local replanning service — cloud-side pipeline for edge-requested replanning."""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.cloud.replanning.adapters import ReplannerAdapter
from cloud_edge_robot_arm.cloud.replanning.apply_service import (
    ReplanApplyResult,
    ReplanApplyService,
)
from cloud_edge_robot_arm.cloud.replanning.context import ReplanningContext
from cloud_edge_robot_arm.cloud.replanning.validators import ReplanScopeValidator
from cloud_edge_robot_arm.contracts.models import (
    LocalReplanningRequest,
    LocalReplanningResponse,
    SkillName,
    TaskContract,
    TaskStep,
)
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import EventAutonomyRepository


class LocalReplanningService:
    """Cloud-side service for local replanning requests from the edge."""

    def __init__(
        self,
        *,
        adapter: ReplannerAdapter,
        repository: EventAutonomyRepository | None = None,
        apply_service: ReplanApplyService | None = None,
        max_repair_attempts: int = 2,
    ) -> None:
        if repository is None:
            from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
                InMemoryEventAutonomyRepository,
            )

            repository = InMemoryEventAutonomyRepository()
        self._adapter = adapter
        self._repo = repository
        self._apply = apply_service or ReplanApplyService(repository=repository, dispatcher=None)
        self._max_repair_attempts = max_repair_attempts
        self._scope_validator = ReplanScopeValidator()

    def process(
        self,
        request: LocalReplanningRequest,
        contract: TaskContract | None = None,
        *,
        apply: bool = True,
        dispatch: bool = False,
    ) -> LocalReplanningResponse:
        """Process a local replanning request and optionally apply it."""
        existing = self._repo.get_replan_result(request.request_id)
        if existing is not None:
            return existing
        persisted_request = self._repo.save_replan_request(request)
        context, validation_error = self._load_and_validate_context(persisted_request, contract)
        if validation_error is not None:
            return self._repo.save_replan_result(validation_error)

        try:
            response = self._adapter.replan(persisted_request, context)
        except Exception:
            failed = LocalReplanningResponse(
                request_id=persisted_request.request_id,
                outcome="PLANNER_FAILED",
                reason="Replanner adapter failed",
                new_plan_version=persisted_request.current_plan_version,
                new_command_seq=persisted_request.current_command_seq,
                planner_name=getattr(self._adapter, "planner_name", "unknown"),
                created_at=datetime.now(UTC),
            )
            return self._repo.save_replan_result(failed)

        if context is not None:
            response_error = self._validate_response(persisted_request, response, context)
            if response_error is not None:
                return self._repo.save_replan_result(response_error)
        saved = self._repo.save_replan_result(response)
        if (
            apply
            and saved.outcome == "REPLANNED"
            and context is not None
            and context.checkpoint is not None
        ):
            applied = self._apply.apply(
                request=persisted_request,
                response=saved,
                active_record=self._repo.get_active_contract(persisted_request.task_id),
                failure_summary=context.failure_summary,
                checkpoint=context.checkpoint,
                dispatch=dispatch,
            )
            if not applied.applied:
                conflict = LocalReplanningResponse(
                    request_id=persisted_request.request_id,
                    outcome=(
                        "VERSION_CONFLICT"
                        if applied.record.status == "VERSION_CONFLICT"
                        else "REJECTED"
                    ),
                    reason="; ".join(applied.errors) or applied.record.reason,
                    new_plan_version=persisted_request.current_plan_version,
                    new_command_seq=persisted_request.current_command_seq,
                    validation_errors=applied.errors,
                    planner_name=saved.planner_name,
                    prompt_version=saved.prompt_version,
                    created_at=datetime.now(UTC),
                )
                return self._repo.save_replan_result(conflict)
        return saved

    def process_and_apply(
        self,
        request: LocalReplanningRequest,
        *,
        dispatch: bool = False,
    ) -> tuple[LocalReplanningResponse, ReplanApplyResult | None]:
        response = self.process(request, apply=False)
        if response.outcome != "REPLANNED":
            return response, None
        active = self._repo.get_active_contract(request.task_id)
        summary = self._repo.get_failure_summary(request.failure_summary_id)
        checkpoint = self._repo.get_latest_execution_checkpoint(request.task_id)
        applied = self._apply.apply(
            request=request,
            response=response,
            active_record=active,
            failure_summary=summary,
            checkpoint=checkpoint,
            dispatch=dispatch,
        )
        return response, applied

    def get_result(self, request_id: str) -> LocalReplanningResponse | None:
        """Retrieve the result of a previous replanning request."""
        return self._repo.get_replan_result(request_id)

    def _load_and_validate_context(
        self,
        request: LocalReplanningRequest,
        contract_override: TaskContract | None,
    ) -> tuple[ReplanningContext | None, LocalReplanningResponse | None]:
        errors: list[str] = []
        event = self._repo.get_event(request.trigger_event_id)
        summary = self._repo.get_failure_summary(request.failure_summary_id)
        active_record = self._repo.get_active_contract(request.task_id)
        checkpoint = self._repo.get_latest_execution_checkpoint(request.task_id)
        if (
            event is None
            and summary is None
            and active_record is None
            and checkpoint is None
            and contract_override is not None
        ):
            context = self._lightweight_context(request, contract_override)
            if context is None:
                return None, self._reject(request, ["failed_step_id not found in contract"])
            return context, None
        if (
            event is None
            and summary is None
            and active_record is None
            and checkpoint is None
            and contract_override is None
        ):
            return None, None
        if event is None:
            errors.append("trigger_event_id not found")
        if summary is None:
            errors.append("failure_summary_id not found")
        if active_record is None and contract_override is None:
            errors.append("active contract not found")
        if checkpoint is None:
            errors.append("checkpoint not found")
        if errors:
            return None, self._reject(request, errors)
        assert summary is not None
        assert checkpoint is not None
        active_contract = contract_override or active_record.contract  # type: ignore[union-attr]
        if event is not None and event.task_id != request.task_id:
            errors.append("event.task_id mismatch")
        if summary.task_id != request.task_id:
            errors.append("summary.task_id mismatch")
        if summary.plan_id and summary.plan_id != request.plan_id:
            errors.append("summary.plan_id mismatch")
        if active_contract.task_id != request.task_id:
            errors.append("active contract task_id mismatch")
        if active_record is not None and active_record.robot_id != request.robot_id:
            errors.append("robot_id mismatch")
        if active_record is not None and active_record.plan_id != request.plan_id:
            errors.append("plan_id mismatch")
        if active_contract.plan_version != request.current_plan_version:
            errors.append("current_plan_version is not active")
        if active_contract.command_seq != request.current_command_seq:
            errors.append("current_command_seq is not active")
        if checkpoint.plan_version != request.current_plan_version:
            errors.append("checkpoint.plan_version mismatch")
        if checkpoint.command_seq != request.current_command_seq:
            errors.append("checkpoint.command_seq mismatch")
        if request.completed_step_ids != checkpoint.completed_step_ids:
            errors.append("completed_step_ids mismatch checkpoint")
        if request.current_scene_version < checkpoint.scene_version:
            errors.append("scene_version regressed")
        failed_step = self._find_step(
            active_contract, request.failed_step_id or checkpoint.failed_step_id
        )
        if failed_step is None:
            errors.append("failed_step_id not found in active contract")
        if errors:
            return None, self._reject(request, errors)
        assert failed_step is not None
        completed_steps = [
            step
            for step in active_contract.steps
            if step.step_id in set(checkpoint.completed_step_ids)
        ]
        context = ReplanningContext(
            active_contract=active_contract,
            failed_step=failed_step,
            completed_steps=completed_steps,
            checkpoint=checkpoint,
            failure_summary=summary,
            allowed_skills=set(SkillName),
            safety_constraints=active_contract.safety_constraints.model_dump(mode="json"),
        )
        return context, None

    def _validate_response(
        self,
        request: LocalReplanningRequest,
        response: LocalReplanningResponse,
        context: ReplanningContext,
    ) -> LocalReplanningResponse | None:
        errors: list[str] = []
        if response.request_id != request.request_id:
            errors.append("response.request_id mismatch")
        scope_valid, scope_error = self._scope_validator.validate(
            scope=request.requested_replan_scope,
            reason=response.reason,
            new_steps=response.new_steps,
        )
        if not scope_valid:
            errors.append(scope_error)
        if response.outcome == "REPLANNED":
            if response.new_plan_version != request.current_plan_version + 1:
                errors.append("new_plan_version must be current + 1")
            if response.new_command_seq <= request.current_command_seq:
                errors.append("new_command_seq must increase")
            if not response.new_steps:
                errors.append("REPLANNED response must include new_steps")
        elif response.new_steps:
            errors.append("non-executable outcome must not include new_steps")
        for step in response.new_steps:
            if step.skill not in context.allowed_skills:
                errors.append(f"skill {step.skill.value} is not allowed")
            bad_keys = {
                "joint_angles",
                "joint_positions",
                "trajectory",
                "pwm",
                "disable_safety",
                "bypass_safety",
                "ignore_collision",
                "force_execute",
            }.intersection(step.parameters)
            if bad_keys:
                errors.append(
                    f"step {step.step_id} contains forbidden parameters: {sorted(bad_keys)}"
                )
        if errors:
            return self._reject(request, errors, planner_name=response.planner_name)
        return None

    def _reject(
        self,
        request: LocalReplanningRequest,
        errors: list[str],
        *,
        planner_name: str = "",
    ) -> LocalReplanningResponse:
        return LocalReplanningResponse(
            request_id=request.request_id,
            outcome="REJECTED",
            reason="; ".join(errors),
            validation_errors=list(errors),
            new_plan_version=request.current_plan_version,
            new_command_seq=request.current_command_seq,
            planner_name=planner_name or getattr(self._adapter, "planner_name", "unknown"),
            created_at=datetime.now(UTC),
        )

    def _lightweight_context(
        self,
        request: LocalReplanningRequest,
        contract: TaskContract,
    ) -> ReplanningContext | None:
        failed_step_id = request.failed_step_id or (
            request.completed_step_ids[-1] if request.completed_step_ids else ""
        )
        failed_step = self._find_step(contract, failed_step_id)
        if failed_step is None:
            return None
        completed_ids = set(request.completed_step_ids)
        return ReplanningContext(
            active_contract=contract,
            failed_step=failed_step,
            completed_steps=[step for step in contract.steps if step.step_id in completed_ids],
            allowed_skills=set(SkillName),
            safety_constraints=contract.safety_constraints.model_dump(mode="json"),
        )

    @staticmethod
    def _find_step(contract: TaskContract, step_id: str) -> TaskStep | None:
        return next((step for step in contract.steps if step.step_id == step_id), None)
