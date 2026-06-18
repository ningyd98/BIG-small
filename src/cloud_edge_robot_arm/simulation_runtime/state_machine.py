from __future__ import annotations

from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus

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
