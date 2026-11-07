"""Shared full-S execution mechanics. Only a live application can issue a session.

The internal runner is not an admission API. Receipts describe actual execution;
they neither establish a calibration bound nor grant online native authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from pydantic_core import to_jsonable_python

from cloud_edge_robot_arm.contracts import TaskContract, TaskStep
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.native_completion_horizon import RationalCompletionHorizonV1


def _json(value: Any) -> str:
    return json.dumps(
        to_jsonable_python(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _error_text(error: BaseException) -> str:
    try:
        return str(error)
    except BaseException:
        return "exception message unavailable"


@dataclass(frozen=True, slots=True)
class FullHorizonExecutionReceipt:
    step_id: str
    skill: str
    original_plan_sha256: str
    executed_step_sha256: str
    horizon_json: str
    dispatch_step: int
    controller_return_step: int | None
    terminal_step: int
    controller_result_json: str | None
    padding_interval_id: str | None
    terminal_acquisition_id: str | None
    complete: bool
    reasons: tuple[str, ...]
    failure_type: str | None = None
    failure_message: str | None = None
    schema_version: str = "native.full-horizon.execution.v1"
    native_authority: str = "UNAVAILABLE"


class _Recorder(Protocol):
    backend: MuJoCoPhysicsBackend
    executor: SkillExecutor
    _original: Any

    @property
    def allocated_acquisition_ids(self) -> tuple[str, ...]: ...

    def execute_attempt(self, **kwargs: Any) -> Any: ...
    def purpose(self, kind: str) -> Any: ...
    def capture(self) -> Any: ...
    def record_horizon(self, receipt: FullHorizonExecutionReceipt) -> None: ...


class NativeHorizonSession:
    """Reserved private application capability; public construction is forbidden."""

    def __init__(self) -> None:
        raise TypeError("a live collection application must issue the execution session")

    def __copy__(self) -> Any:
        raise RuntimeError("live horizon session cannot be copied")

    def __deepcopy__(self, memo: Any) -> Any:
        raise RuntimeError("live horizon session cannot be copied")

    def __reduce_ex__(self, protocol: Any) -> Any:
        raise RuntimeError("live horizon session cannot be serialized")

    def execute(self, *, index: int, contract: Any, step: Any, binding: Any) -> Any:
        application = _SESSIONS.get(self)
        if type(self) is not NativeHorizonSession or application is None:
            raise RuntimeError("unissued horizon session")
        return application._execute_horizon(
            self, index=index, contract=contract, step=step, binding=binding
        )


_SESSIONS: dict[NativeHorizonSession, Any] = {}


def _issue_collection_session(application: Any) -> NativeHorizonSession:
    from cloud_edge_robot_arm.research.native_collection_application import _live

    live = _live(application)
    application.check_active()
    if (
        not live.entered
        or live.original is None
        or live.recorder is None
        or live.recorder._original is None
        or live.session is not None
    ):
        raise RuntimeError("same original live worker source required")
    session = object.__new__(NativeHorizonSession)
    _SESSIONS[session] = application
    return session


def _run_registered_horizon(
    *,
    backend: MuJoCoPhysicsBackend,
    robot: MuJoCoSkillRobot,
    executor: SkillExecutor,
    recorder: _Recorder,
    contract: TaskContract,
    step: TaskStep,
    grounding: Any,
    horizon: RationalCompletionHorizonV1,
    check_active: Callable[[], Any],
) -> FullHorizonExecutionReceipt:
    """Retain controller return and then hold its existing target through full H.

    No replacement target is issued during padding. The application's exact live
    guard supplies deadline, lease and cancellation checks at every backend effect.
    """
    if (
        recorder.backend is not backend
        or recorder.executor is not executor
        or executor._robot is not robot
        or robot._backend is not backend
        or recorder._original is None
        or backend._execution_guard is None
        or backend._execution_guard_closed
        or not backend._step_capture_active
    ):
        raise RuntimeError(
            "same guarded backend, sole executor, original recorder and sampler required"
        )
    if type(horizon) is not RationalCompletionHorizonV1 or horizon.skill != step.skill.value:
        raise ValueError("exact registered skill horizon required")
    dispatch = backend.total_physics_steps
    terminal = dispatch + horizon.total_steps
    original_hash = recorder._original.digest()
    executed_hash = _sha(step.model_dump(mode="json"))
    horizon_json = _json(asdict(horizon))
    returned = None
    result_json = None
    padding = terminal_acquisition = None
    reasons: list[str] = []
    primary: BaseException | None = None
    complete = False

    def check_hold() -> None:
        state = robot.get_state()
        if step.skill.value in {"GRASP", "LIFT", "MOVE_TO_REGION", "PLACE"}:
            if state.holding_object_id != contract.task_target.object_id:
                raise RuntimeError("bilateral grasp lost during registered hold")
        if step.skill.value == "RELEASE" and not state.gripper_open:
            raise RuntimeError("gripper closed during registered release hold")

    try:
        check_active()
        result = recorder.execute_attempt(
            contract=contract, step=step, attempt=1, grounding=grounding
        )
        returned = backend.total_physics_steps
        result_json = _json(result)
        check_active()
        if not result.success or result.action_result is None:
            reasons.append("controller_unsuccessful")
        elif returned > terminal:
            reasons.append("controller_exceeded_registered_horizon")
        elif step.skill.value == "RELEASE" and terminal - returned < horizon.builtin_tail_steps:
            reasons.append("release_open_return_leaves_insufficient_tail")
        elif (
            step.skill.value == "LIFT"
            and result.action_result.details.get("contact_hold_s", 0) < 0.5
        ):
            reasons.append("controller_lift_hold_incomplete")
        if reasons:
            backend._close_execution_guard(RuntimeError(reasons[0]))
        else:
            check_hold()
            with recorder.purpose("FULL_HORIZON_HOLD") as padding:
                while backend.total_physics_steps < terminal:
                    check_active()
                    check_hold()
                    backend.step(1)
                    check_active()
                    check_hold()
            check_active()
            recorder.capture()
            terminal_acquisition = recorder.allocated_acquisition_ids[-1]
            check_active()
            if backend.total_physics_steps != terminal:
                raise RuntimeError("terminal capture advanced the registered horizon")
            complete = True
    except BaseException as error:
        primary = error
        reasons.append("execution_or_hold_failed")
        backend._close_execution_guard(error)
        raise
    finally:
        receipt = FullHorizonExecutionReceipt(
            step.step_id,
            step.skill.value,
            original_hash,
            executed_hash,
            horizon_json,
            dispatch,
            returned,
            backend.total_physics_steps,
            result_json,
            padding,
            terminal_acquisition,
            complete,
            tuple(reasons),
            type(primary).__name__ if primary is not None else None,
            _error_text(primary) if primary is not None else None,
        )
        try:
            recorder.record_horizon(receipt)
        except BaseException as evidence_error:
            backend._close_execution_guard(primary or evidence_error)
            if primary is None:
                raise
            primary.add_note(
                "full-horizon receipt persistence failed: " + type(evidence_error).__name__
            )
    return receipt
