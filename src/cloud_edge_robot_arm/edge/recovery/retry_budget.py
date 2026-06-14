"""RetryBudgetService — repository-driven, CAS-safe retry budget management.

Replaces the in-memory RetryBudgetManager with persistent CAS semantics.
Effective limit = min(current_step.retry_limit, skill_policy.limit,
                      task_remaining_limit, safety_policy.limit)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts.models import RecoveryBudget, TaskContract
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    EventAutonomyRepository,
)


class RetryBudgetService:
    """Manages retry budgets with repository-backed CAS consumption.

    Atomic consumption prevents:
    - Double-consumption from concurrent retries
    - Budget forgery on restart (persisted in repository)
    - Exceeding any applicable limit (step, skill, task, safety)
    """

    def __init__(
        self,
        *,
        repository: EventAutonomyRepository,
        safety_max_retry_limit: int = 10,
    ) -> None:
        self._repo = repository
        self._safety_max = safety_max_retry_limit
        self._contracts: dict[str, TaskContract] = {}

    def initialize(self, task_id: str, contract: TaskContract) -> RecoveryBudget:
        """Create and persist a retry budget for a new task."""
        self._contracts[task_id] = contract
        step_limits = [s.retry_limit for s in contract.steps]
        per_skill = contract.failure_policy.local_retry_limit
        task_total = min(per_skill, self._safety_max)
        effective = task_total
        now = datetime.now(UTC)
        deadline = None
        if contract.command_ttl_ms is not None:
            deadline = now + timedelta(milliseconds=contract.command_ttl_ms)
        budget = RecoveryBudget(
            budget_id=f"budget-{task_id}",
            task_id=task_id,
            per_step_retry_limit=max(step_limits) if step_limits else 0,
            per_skill_retry_limit=per_skill,
            task_total_retry_limit=task_total,
            retry_count_used=0,
            task_retry_count=0,
            step_retry_counts={},
            skill_retry_counts={},
            event_retry_counts={},
            retry_cooldown_ms=500,
            retry_deadline=deadline,
            retry_backoff_policy="exponential",
            effective_retry_limit=effective,
            remaining_retries=effective,
            scene_version=contract.scene_version,
            created_at=now,
            updated_at=now,
        )
        return self._repo.save_retry_budget(budget)

    def can_attempt(
        self,
        task_id: str,
        step_id: str = "",
        skill: str = "",
        event_id: str = "",
    ) -> tuple[bool, str]:
        """Check if a retry is allowed for the given task/step/skill/event."""
        budget = self._repo.get_retry_budget(task_id)
        if budget is None:
            return False, "NO_BUDGET_INITIALIZED"
        if event_id and budget.event_retry_counts.get(event_id, 0) > 0:
            return False, "EVENT_RETRY_ALREADY_CONSUMED"
        effective_limit = self._effective_limit(task_id, step_id, skill, budget)
        step_used = budget.step_retry_counts.get(step_id, 0) if step_id else 0
        skill_used = budget.skill_retry_counts.get(skill, 0) if skill else 0
        task_remaining = max(0, budget.task_total_retry_limit - budget.task_retry_count)
        step_remaining = max(0, effective_limit - step_used)
        skill_remaining = max(0, budget.per_skill_retry_limit - skill_used)
        effective_remaining = min(
            task_remaining,
            step_remaining,
            skill_remaining,
            budget.remaining_retries,
        )
        if effective_remaining <= 0:
            return False, "RETRY_BUDGET_EXHAUSTED"
        if budget.retry_deadline is not None and datetime.now(UTC) >= budget.retry_deadline:
            return False, "RETRY_DEADLINE_EXCEEDED"
        return True, "OK"

    def consume_if_available(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        event_id: str = "",
    ) -> tuple[bool, RecoveryBudget | None]:
        """Atomically consume one retry via CAS in the repository.

        Only succeeds if the caller's expected retry_count matches the
        persisted value, preventing double-consumption.
        """
        budget = self._repo.get_retry_budget(task_id)
        if budget is None:
            return False, None
        allowed, _ = self.can_attempt(task_id, step_id, skill, event_id)
        if not allowed:
            return False, budget
        return self._repo.consume_retry_if_available(
            task_id=task_id,
            step_id=step_id,
            skill=skill,
            expected_count=budget.retry_count_used,
            event_id=event_id,
        )

    def consume(self, task_id: str, step_id: str = "", skill: str = "") -> RecoveryBudget | None:
        """Backward-compatible single retry consume helper."""
        consumed, budget = self.consume_if_available(task_id, step_id, skill)
        if not consumed:
            return None
        return budget

    def record_result(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        *,
        success: bool,
        error_code: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Record retry result metadata for audit and recovery traceability."""
        self._repo.record_audit_event(
            task_id,
            "LOCAL_RETRY_RESULT",
            {
                "step_id": step_id,
                "skill": skill,
                "success": success,
                "error_code": error_code,
                "duration_ms": duration_ms,
            },
        )

    def get_budget(self, task_id: str) -> RecoveryBudget | None:
        """Get the current retry budget for a task from the repository."""
        return self._repo.get_retry_budget(task_id)

    def reset(self) -> None:
        """No-op — repository manages lifecycle."""
        return

    def _effective_limit(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        budget: RecoveryBudget,
    ) -> int:
        contract = self._contracts.get(task_id)
        current_step_limit = budget.per_step_retry_limit
        if contract is not None and step_id:
            for step in contract.steps:
                if step.step_id == step_id:
                    current_step_limit = step.retry_limit
                    break
        skill_policy_limit = budget.per_skill_retry_limit
        if contract is not None and skill:
            skill_policy_limit = contract.failure_policy.local_retry_limit
        return min(
            current_step_limit,
            skill_policy_limit,
            budget.task_total_retry_limit,
            self._safety_max,
        )
