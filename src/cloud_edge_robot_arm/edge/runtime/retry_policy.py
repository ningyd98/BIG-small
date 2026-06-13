from __future__ import annotations

from dataclasses import dataclass

from cloud_edge_robot_arm.contracts import FailurePolicy, TaskStep

RETRYABLE_ERROR_CODES = frozenset(
    {
        "GRASP_FAILED",
        "ACTION_TIMEOUT",
        "RESULT_NOT_VERIFIED",
    }
)

NON_RETRYABLE_ERROR_CODES = frozenset(
    {
        "COLLISION_DETECTED",
        "EMERGENCY_STOP_ACTIVE",
        "ROBOT_DISCONNECTED",
        "INVALID_TARGET_POSE",
        "TARGET_UNREACHABLE",
    }
)

SAFETY_STOP_ERROR_CODES = frozenset(
    {
        "COLLISION_DETECTED",
        "EMERGENCY_STOP_ACTIVE",
    }
)


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    max_attempts: int


class RetryPolicy:
    def max_attempts(self, step: TaskStep, failure_policy: FailurePolicy) -> int:
        return min(step.retry_limit, failure_policy.local_retry_limit) + 1

    def decide(
        self,
        *,
        step: TaskStep,
        failure_policy: FailurePolicy,
        error_code: str | None,
        attempt: int,
    ) -> RetryDecision:
        max_attempts = self.max_attempts(step, failure_policy)
        should_retry = (
            error_code in RETRYABLE_ERROR_CODES
            and error_code not in NON_RETRYABLE_ERROR_CODES
            and attempt < max_attempts
        )
        return RetryDecision(should_retry=should_retry, max_attempts=max_attempts)
