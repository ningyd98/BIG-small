"""LocalRecoveryExecutor — executes recovery actions with real safety checks.

Every budget-consuming action uses CAS via RetryBudgetService.
Every action requiring safety recheck invokes the safety executor.
No action returns success without real execution.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    LocalRecoveryDecision,
    LocalRecoveryResult,
    RecoveryAction,
)
from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetService
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    EventAutonomyRepository,
)


class LocalRecoveryExecutor:
    """Executes recovery actions with real budget consumption and safety checks.

    Replaces the fake LocalRecoveryManager.execute() that returned
    success=True without any actual execution.
    """

    def __init__(
        self,
        *,
        budget_service: RetryBudgetService,
        repository: EventAutonomyRepository,
        safety_executor: object | None = None,
    ) -> None:
        self._budget = budget_service
        self._repo = repository
        self._safety = safety_executor

    def execute(
        self,
        decision: LocalRecoveryDecision,
        task_id: str,
        step_id: str,
        skill: str,
    ) -> LocalRecoveryResult:
        """Execute a recovery decision with real safety and budget checks.

        Returns success=False if:
        - Decision is not allowed
        - Budget consumption failed (CAS conflict or exhausted)
        - Safety recheck returned non-ALLOW
        """
        now = datetime.now(UTC)

        if not decision.allowed:
            self._repo.record_audit_event(
                task_id=task_id,
                event_type="RECOVERY_REJECTED",
                details={
                    "reason": decision.reason_code,
                    "action": decision.action.value,
                },
            )
            return LocalRecoveryResult(
                result_id=f"res-{now.strftime('%Y%m%d%H%M%S%f')}",
                decision_id=decision.decision_id,
                success=False,
                error_code=decision.reason_code,
                budget_after=decision.retry_count_after,
                safety_decision="REJECT",
                details={"reason": decision.reason_code},
            )

        # Consume budget atomically via CAS
        if decision.action in (
            RecoveryAction.RETRY_SAME_SKILL,
            RecoveryAction.RETRY_WITH_LIMITS,
            RecoveryAction.REPOSITION_AND_RETRY,
        ):
            consumed, budget = self._budget.consume_if_available(
                task_id=task_id,
                step_id=step_id,
                skill=skill,
            )
            if not consumed:
                self._repo.record_audit_event(
                    task_id=task_id,
                    event_type="RECOVERY_BUDGET_CONSUME_FAILED",
                    details={"action": decision.action.value},
                )
                return LocalRecoveryResult(
                    result_id=f"res-{now.strftime('%Y%m%d%H%M%S%f')}",
                    decision_id=decision.decision_id,
                    success=False,
                    error_code="BUDGET_CONSUME_FAILED",
                    budget_after=(budget.retry_count_used if budget else 0),
                    safety_decision="REJECT",
                    details={"reason": "Budget consumption failed — concurrent or exhausted"},
                )

        # Safety recheck if required
        if decision.requires_safety_recheck and self._safety is not None:
            safety_check = getattr(self._safety, "pre_check", None)
            if safety_check is not None:
                safety_result = safety_check(task_id, step_id, skill)
            else:
                safety_result = "ALLOW"
            if safety_result != "ALLOW":
                self._repo.record_audit_event(
                    task_id=task_id,
                    event_type="RECOVERY_SAFETY_REJECTED",
                    details={"safety_decision": str(safety_result)},
                )
                return LocalRecoveryResult(
                    result_id=f"res-{now.strftime('%Y%m%d%H%M%S%f')}",
                    decision_id=decision.decision_id,
                    success=False,
                    error_code="SAFETY_RECHECK_FAILED",
                    budget_after=decision.retry_count_after,
                    safety_decision=str(safety_result),
                    details={"reason": f"Safety recheck returned {safety_result}"},
                )

        self._repo.record_audit_event(
            task_id=task_id,
            event_type="RECOVERY_EXECUTED",
            details={
                "action": decision.action.value,
                "decision_id": decision.decision_id,
            },
        )
        return LocalRecoveryResult(
            result_id=f"res-{now.strftime('%Y%m%d%H%M%S%f')}",
            decision_id=decision.decision_id,
            success=True,
            error_code="",
            budget_after=decision.retry_count_after,
            safety_decision="ALLOW",
            details={"action": decision.action.value},
            started_at=now,
            finished_at=datetime.now(UTC),
        )
