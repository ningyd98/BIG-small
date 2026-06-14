"""Local replanning service — cloud-side pipeline for edge-requested replanning.

Data flow:
LocalReplanningRequest → Request Validation → FailureSummary Validation →
Current Plan Validation → Completed Steps Protection → Scene Sufficiency →
ReplannerAdapter → Schema Validation → Semantic Validation →
Replan Scope Validation → Safety Validation → Trusted Field Injection →
CAS Version Update → Persistence → Response
"""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.cloud.replanning.adapters import ReplannerAdapter
from cloud_edge_robot_arm.cloud.replanning.validators import (
    CompletedStepsProtectionValidator,
    ReplanScopeValidator,
)
from cloud_edge_robot_arm.contracts.models import (
    LocalReplanningRequest,
    LocalReplanningResponse,
    TaskContract,
)
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import EventAutonomyRepository


class LocalReplanningService:
    """Cloud-side service for local replanning requests from the edge.

    Reuses the planning pipeline pattern but with additional constraints:
    - Completed steps are immutable
    - Only the requested scope may be modified
    - CAS version management
    - All standard validation chain (schema → semantic → safety)
    """

    def __init__(
        self,
        *,
        adapter: ReplannerAdapter,
        repository: EventAutonomyRepository | None = None,
        max_repair_attempts: int = 2,
    ) -> None:
        if repository is None:
            from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
                InMemoryEventAutonomyRepository,
            )

            repository = InMemoryEventAutonomyRepository()
        self._adapter = adapter
        self._repo = repository
        self._max_repair_attempts = max_repair_attempts
        self._steps_validator = CompletedStepsProtectionValidator()
        self._scope_validator = ReplanScopeValidator()

    def process(
        self,
        request: LocalReplanningRequest,
        contract: TaskContract | None = None,
    ) -> LocalReplanningResponse:
        """Process a local replanning request.

        Args:
            request: The replanning request from the edge.
            contract: The current active contract (for completed step validation).

        Returns:
            LocalReplanningResponse with outcome and new steps.
        """
        existing = self._repo.get_replan_result(request.request_id)
        if existing is not None:
            return existing

        persisted_request = self._repo.save_replan_request(request)

        # 1. Validate request
        validation_error = self._validate_request(persisted_request)
        if validation_error is not None:
            return self._repo.save_replan_result(validation_error)

        # 2. Call replanner adapter
        try:
            response = self._adapter.replan(persisted_request)
        except Exception:
            now = datetime.now(UTC)
            failed = LocalReplanningResponse(
                request_id=persisted_request.request_id,
                outcome="PLANNER_FAILED",
                reason="Replanner adapter failed",
                new_plan_version=persisted_request.current_plan_version,
                new_command_seq=persisted_request.current_command_seq,
                planner_name=getattr(self._adapter, "planner_name", "unknown"),
                created_at=now,
            )
            return self._repo.save_replan_result(failed)

        # 3. Validate completed steps protection
        if contract is not None and response.outcome == "REPLANNED":
            orig_steps = contract.steps
            valid, errors = self._steps_validator.validate(
                completed_ids=persisted_request.completed_step_ids,
                original_steps=orig_steps,
                new_steps=response.new_steps,
                last_successful_step_id=persisted_request.last_successful_step_id,
            )
            if not valid:
                now = datetime.now(UTC)
                rejected = LocalReplanningResponse(
                    request_id=persisted_request.request_id,
                    outcome="REJECTED",
                    reason=f"Completed steps validation failed: {'; '.join(errors)}",
                    validation_errors=errors,
                    new_plan_version=persisted_request.current_plan_version,
                    new_command_seq=persisted_request.current_command_seq,
                    planner_name=response.planner_name,
                    created_at=now,
                )
                return self._repo.save_replan_result(rejected)

        # 4. Validate replan scope
        scope_valid, scope_error = self._scope_validator.validate(
            scope=persisted_request.requested_replan_scope,
            reason=response.reason,
            new_steps=response.new_steps,
        )
        if not scope_valid:
            now = datetime.now(UTC)
            rejected = LocalReplanningResponse(
                request_id=persisted_request.request_id,
                outcome="REJECTED",
                reason=scope_error,
                new_plan_version=persisted_request.current_plan_version,
                new_command_seq=persisted_request.current_command_seq,
                planner_name=response.planner_name,
                created_at=now,
            )
            return self._repo.save_replan_result(rejected)

        # 5. CAS version upgrade and persist response
        if response.outcome == "REPLANNED":
            advanced = self._repo.advance_plan_version_if_current(
                persisted_request.task_id,
                persisted_request.current_plan_version,
                persisted_request.current_command_seq,
                response.new_plan_version,
                response.new_command_seq,
            )
            if not advanced:
                conflict = LocalReplanningResponse(
                    request_id=persisted_request.request_id,
                    outcome="VERSION_CONFLICT",
                    reason="Plan version changed before replanning result could be applied",
                    new_plan_version=persisted_request.current_plan_version,
                    new_command_seq=persisted_request.current_command_seq,
                    planner_name=response.planner_name,
                    created_at=datetime.now(UTC),
                )
                return self._repo.save_replan_result(conflict)

        return self._repo.save_replan_result(response)

    def get_result(self, request_id: str) -> LocalReplanningResponse | None:
        """Retrieve the result of a previous replanning request."""
        return self._repo.get_replan_result(request_id)

    @staticmethod
    def _validate_request(
        request: LocalReplanningRequest,
    ) -> LocalReplanningResponse | None:
        """Validate the incoming request. Returns error response if invalid."""
        now = datetime.now(UTC)

        if not request.request_id:
            return LocalReplanningResponse(
                request_id=request.request_id or "unknown",
                outcome="REJECTED",
                reason="Missing request_id",
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                created_at=now,
            )

        if not request.trigger_event_id:
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="REJECTED",
                reason="Missing trigger_event_id",
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                created_at=now,
            )

        if request.current_plan_version < 0:
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="REJECTED",
                reason="Invalid plan_version",
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                created_at=now,
            )

        return None
