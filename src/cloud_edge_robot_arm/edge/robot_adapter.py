from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable
from uuid import uuid4

from cloud_edge_robot_arm.contracts import ActionResult, Pose, RobotState
from cloud_edge_robot_arm.errors import StructuredError


@runtime_checkable
class RobotAdapter(Protocol):
    def connect(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def disconnect(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def home(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def move_to_pose(self, pose: Pose, *, timeout_ms: int | None = None) -> ActionResult: ...

    def open_gripper(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def close_gripper(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def get_state(self) -> RobotState: ...

    def stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...


def build_action_result(
    *,
    action_type: str,
    success: bool,
    state_before: dict[str, object],
    state_after: dict[str, object],
    duration_ms: int,
    error_code: str | None = None,
    error_message: str | None = None,
    error_category: str = "ROBOT_ADAPTER",
    details: dict[str, object] | None = None,
    started_at: datetime | None = None,
) -> ActionResult:
    started = started_at if started_at is not None else datetime.now(UTC)
    finished = started + timedelta(milliseconds=duration_ms)
    error = None
    if error_code is not None:
        error = StructuredError(
            code=error_code,
            message=error_message or error_code,
            category=error_category,
            details=dict(details or {}),
        )
    return ActionResult(
        success=success,
        action_id=str(uuid4()),
        action_type=action_type,
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        error_code=error_code,
        error_message=error_message,
        state_before=state_before,
        state_after=state_after,
        error=error,
        details=dict(details or {}),
    )
