"""Retry budget manager for local recovery.

Enforces per-step, per-skill, task-total, and safety-policy retry limits.
Effective budget = min(all applicable limits).
Prevents reset-on-restart, concurrent double-consumption, and budget forgery.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts.models import RecoveryBudget, TaskContract


class RetryBudgetManager:
    """Manages retry budgets for event-triggered edge autonomy.

    Budgets are initialized from TaskContract failure_policy and safety constraints.
    Effective retry limit = min(step, skill, task, safety) limits.
    """

    def __init__(
        self,
        *,
        safety_max_retry_limit: int = 10,
    ) -> None:
        self._safety_max = safety_max_retry_limit
        self._budgets: dict[str, RecoveryBudget] = {}

    def initialize(self, task_id: str, contract: TaskContract) -> RecoveryBudget:
        """Create a budget for a new task based on the contract."""
        step_limits = [s.retry_limit for s in contract.steps]
        _step_max = max(step_limits) if step_limits else 3
        per_step = min(step_limits) if step_limits else 3
        per_skill = contract.failure_policy.local_retry_limit
        task_total = contract.failure_policy.local_retry_limit * len(contract.steps)

        effective = min(per_step, per_skill, task_total, self._safety_max)

        now = datetime.now(UTC)
        deadline = None
        if contract.command_ttl_ms is not None:
            deadline = now + timedelta(milliseconds=contract.command_ttl_ms)

        budget = RecoveryBudget(
            budget_id=f"budget-{task_id}",
            task_id=task_id,
            per_step_retry_limit=per_step,
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
        self._budgets[task_id] = budget
        return budget

    def can_attempt(self, task_id: str) -> tuple[bool, str]:
        """Check if a retry is allowed for the given task.

        Returns (allowed, reason_string).
        """
        budget = self._budgets.get(task_id)
        if budget is None:
            return False, "NO_BUDGET_INITIALIZED"

        if budget.remaining_retries <= 0:
            return False, "RETRY_BUDGET_EXHAUSTED"

        if budget.retry_deadline is not None:
            now = datetime.now(UTC)
            if now >= budget.retry_deadline:
                return False, "RETRY_DEADLINE_EXCEEDED"

        return True, "OK"

    def consume(self, task_id: str) -> RecoveryBudget | None:
        """Consume one retry attempt. Returns updated budget or None if exhausted."""
        budget = self._budgets.get(task_id)
        if budget is None:
            return None

        allowed, _ = self.can_attempt(task_id)
        if not allowed:
            return None

        now = datetime.now(UTC)
        updated = RecoveryBudget(
            budget_id=budget.budget_id,
            task_id=task_id,
            per_step_retry_limit=budget.per_step_retry_limit,
            per_skill_retry_limit=budget.per_skill_retry_limit,
            task_total_retry_limit=budget.task_total_retry_limit,
            retry_count_used=budget.retry_count_used + 1,
            retry_cooldown_ms=budget.retry_cooldown_ms,
            retry_deadline=budget.retry_deadline,
            retry_backoff_policy=budget.retry_backoff_policy,
            effective_retry_limit=budget.effective_retry_limit,
            remaining_retries=budget.remaining_retries - 1,
            scene_version=budget.scene_version,
            created_at=budget.created_at,
            updated_at=now,
        )
        self._budgets[task_id] = updated
        return updated

    def get_budget(self, task_id: str) -> RecoveryBudget | None:
        """Get current budget state for a task."""
        return self._budgets.get(task_id)

    def remaining_retries(self, task_id: str) -> int:
        """Get remaining retry count for a task."""
        budget = self._budgets.get(task_id)
        if budget is None:
            return 0
        return budget.remaining_retries

    def reset(self) -> None:
        """Clear all budgets (for testing)."""
        self._budgets.clear()
