"""LocalRecoveryExecutor — authorization only.

This service no longer pretends to execute motion. It only authorizes or
rejects recovery based on budget and safety recheck. The TaskExecutor remains
responsible for re-running the real step.
本地恢复授权器。

该服务只判断恢复是否被预算和安全复检允许，不假装执行运动；真正步骤执行由 TaskExecutor 完成。

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
    """Authorizes local recovery; real skill execution stays in TaskExecutor."""

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
                event_id=decision.event_id,
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
            if safety_check is None:
                self._repo.record_audit_event(
                    task_id=task_id,
                    event_type="RECOVERY_SAFETY_REJECTED",
                    details={"safety_decision": "UNAVAILABLE"},
                )
                return LocalRecoveryResult(
                    result_id=f"res-{now.strftime('%Y%m%d%H%M%S%f')}",
                    decision_id=decision.decision_id,
                    success=False,
                    error_code="SAFETY_RECHECK_UNAVAILABLE",
                    budget_after=decision.retry_count_after,
                    safety_decision="REJECT",
                    details={"reason": "Safety recheck unavailable"},
                )
            safety_result = safety_check(task_id, step_id, skill)
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
        else:
            return LocalRecoveryResult(
                result_id=f"res-{now.strftime('%Y%m%d%H%M%S%f')}",
                decision_id=decision.decision_id,
                success=False,
                error_code="REAL_RECOVERY_EXECUTION_REQUIRED",
                budget_after=decision.retry_count_after,
                safety_decision="REJECT",
                details={"reason": "LocalRecoveryExecutor only authorizes recovery"},
            )

        self._repo.record_audit_event(
            task_id=task_id,
            event_type="RECOVERY_AUTHORIZED",
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
