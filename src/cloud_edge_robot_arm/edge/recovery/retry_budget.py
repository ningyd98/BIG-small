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

    def initialize(self, task_id: str, contract: TaskContract) -> RecoveryBudget:
        """Create and persist a retry budget for a new task."""
        step_limits = [s.retry_limit for s in contract.steps]
        per_skill = contract.failure_policy.local_retry_limit
        task_total = per_skill * len(contract.steps)
        effective = min(
            max(step_limits) if step_limits else 3,
            per_skill,
            task_total,
            self._safety_max,
        )
        now = datetime.now(UTC)
        deadline = None
        if contract.command_ttl_ms is not None:
            deadline = now + timedelta(milliseconds=contract.command_ttl_ms)
        budget = RecoveryBudget(
            budget_id=f"budget-{task_id}",
            task_id=task_id,
            per_step_retry_limit=max(step_limits) if step_limits else 3,
            per_skill_retry_limit=per_skill,
            task_total_retry_limit=task_total,
            retry_count_used=0,
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
        self, task_id: str, step_id: str = "", skill: str = ""
    ) -> tuple[bool, str]:
        """Check if a retry is allowed for the given task."""
        budget = self._repo.get_retry_budget(task_id)
        if budget is None:
            return False, "NO_BUDGET_INITIALIZED"
        if budget.remaining_retries <= 0:
            return False, "RETRY_BUDGET_EXHAUSTED"
        if budget.retry_deadline is not None and datetime.now(UTC) >= budget.retry_deadline:
            return False, "RETRY_DEADLINE_EXCEEDED"
        return True, "OK"

    def consume_if_available(
        self, task_id: str, step_id: str, skill: str
    ) -> tuple[bool, RecoveryBudget | None]:
        """Atomically consume one retry via CAS in the repository.

        Only succeeds if the caller's expected retry_count matches the
        persisted value, preventing double-consumption.
        """
        budget = self._repo.get_retry_budget(task_id)
        if budget is None:
            return False, None
        allowed, _ = self.can_attempt(task_id, step_id, skill)
        if not allowed:
            return False, budget
        return self._repo.consume_retry_if_available(
            task_id=task_id,
            step_id=step_id,
            skill=skill,
            expected_count=budget.retry_count_used,
        )

    def get_budget(self, task_id: str) -> RecoveryBudget | None:
        """Get the current retry budget for a task from the repository."""
        return self._repo.get_retry_budget(task_id)

    def reset(self) -> None:
        """No-op — repository manages lifecycle."""
        return
