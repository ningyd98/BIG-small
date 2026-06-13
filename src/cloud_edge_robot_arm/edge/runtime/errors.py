from __future__ import annotations

from cloud_edge_robot_arm.errors import StructuredError


def runtime_error(
    code: str,
    message: str,
    *,
    details: dict[str, object] | None = None,
) -> StructuredError:
    return StructuredError(
        code=code,
        message=message,
        category="EDGE_RUNTIME",
        details=dict(details or {}),
    )


INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
PRECONDITION_FAILED = "PRECONDITION_FAILED"
INVALID_SKILL_PARAMETERS = "INVALID_SKILL_PARAMETERS"
SUCCESS_CONDITION_FAILED = "RESULT_NOT_VERIFIED"
TASK_TIMEOUT = "TASK_TIMEOUT"
