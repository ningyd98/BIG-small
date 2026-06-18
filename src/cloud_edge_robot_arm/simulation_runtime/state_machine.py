"""仿真 job 状态机。

状态转换表是运行时安全边界之一：所有 repository 状态更新都必须先经过这里。
非法转换直接抛错，避免取消、超时、恢复和重试互相覆盖。
"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus

# 只列出允许的正向转换；终态默认不可再推进，除非显式允许人工 retry。
ALLOWED_TRANSITIONS: dict[RuntimeJobStatus, set[RuntimeJobStatus]] = {
    RuntimeJobStatus.CREATED: {RuntimeJobStatus.QUEUED, RuntimeJobStatus.BLOCKED_BY_ENV},
    RuntimeJobStatus.QUEUED: {
        RuntimeJobStatus.VALIDATING,
        RuntimeJobStatus.CANCELLED,
        RuntimeJobStatus.BLOCKED_BY_ENV,
    },
    RuntimeJobStatus.VALIDATING: {
        RuntimeJobStatus.LEASED,
        RuntimeJobStatus.BLOCKED_BY_ENV,
        RuntimeJobStatus.FAILED,
        RuntimeJobStatus.CANCEL_REQUESTED,
    },
    RuntimeJobStatus.LEASED: {
        RuntimeJobStatus.STARTING,
        RuntimeJobStatus.INTERRUPTED,
        RuntimeJobStatus.CANCEL_REQUESTED,
    },
    RuntimeJobStatus.STARTING: {
        RuntimeJobStatus.RUNNING,
        RuntimeJobStatus.FAILED,
        RuntimeJobStatus.CANCEL_REQUESTED,
        RuntimeJobStatus.TIMED_OUT,
    },
    RuntimeJobStatus.RUNNING: {
        RuntimeJobStatus.FINALIZING,
        RuntimeJobStatus.CANCEL_REQUESTED,
        RuntimeJobStatus.TIMED_OUT,
        RuntimeJobStatus.FAILED,
        RuntimeJobStatus.INTERRUPTED,
        RuntimeJobStatus.BLOCKED_BY_ENV,
    },
    RuntimeJobStatus.CANCEL_REQUESTED: {RuntimeJobStatus.CANCELLING, RuntimeJobStatus.CANCELLED},
    RuntimeJobStatus.CANCELLING: {RuntimeJobStatus.CANCELLED},
    RuntimeJobStatus.FINALIZING: {
        RuntimeJobStatus.SUCCEEDED,
        RuntimeJobStatus.FAILED,
        RuntimeJobStatus.RECOVERY_PENDING,
    },
    RuntimeJobStatus.INTERRUPTED: {RuntimeJobStatus.RECOVERY_PENDING},
    RuntimeJobStatus.RECOVERY_PENDING: {RuntimeJobStatus.QUEUED, RuntimeJobStatus.FAILED},
    RuntimeJobStatus.SUCCEEDED: set(),
    RuntimeJobStatus.FAILED: {RuntimeJobStatus.QUEUED},
    RuntimeJobStatus.CANCELLED: {RuntimeJobStatus.QUEUED},
    RuntimeJobStatus.TIMED_OUT: {RuntimeJobStatus.QUEUED},
    RuntimeJobStatus.BLOCKED_BY_ENV: set(),
}


def validate_transition(previous: RuntimeJobStatus, next_status: RuntimeJobStatus) -> bool:
    """校验状态转换是否合法。

    幂等转换允许通过，方便重复 replay 或状态查询；跨状态推进必须出现在
    ALLOWED_TRANSITIONS 中。
    """

    if previous == next_status:
        return True
    if next_status not in ALLOWED_TRANSITIONS.get(previous, set()):
        raise ValueError(
            f"illegal simulation job transition: {previous.value} -> {next_status.value}"
        )
    return True


def terminal_statuses() -> set[RuntimeJobStatus]:
    return {
        RuntimeJobStatus.SUCCEEDED,
        RuntimeJobStatus.FAILED,
        RuntimeJobStatus.CANCELLED,
        RuntimeJobStatus.TIMED_OUT,
        RuntimeJobStatus.BLOCKED_BY_ENV,
    }
