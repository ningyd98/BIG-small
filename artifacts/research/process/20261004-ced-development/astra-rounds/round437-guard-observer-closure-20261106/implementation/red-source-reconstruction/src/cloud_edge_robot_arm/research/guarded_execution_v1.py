"""Live OC1 execution checks and a fixed, excluded MuJoCo diagnostic.

This seam does not issue worker, lease, calibration or native action authority.
Its counter measures checkpoint deadlines, not a hard preemption guarantee.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from cloud_edge_robot_arm.research.operational_time_v1 import (
    OperationalClockOwner,
    OperationalDeadline,
    OperationalEventToken,
    open_operational_clock,
)
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    GripperCommand,
    JointCommand,
    PhysicalScenarioConfig,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    BackendOperationBoundary,
    ExecutionGuardBoundaryV1,
    MuJoCoPhysicsBackend,
)

_ROOT = Path(__file__).resolve().parents[3]
_PLAN = (
    "artifacts/research/process/20261004-ced-development/astra-rounds/"
    "round435-t7b-guarded-execution-20261105/plan.json"
)


class OperationalExecutionGuardV1:
    """Bind a live original deadline to exactly one backend and reset episode."""

    def __init__(
        self,
        owner: OperationalClockOwner,
        *,
        origin_token: OperationalEventToken,
        deadline: OperationalDeadline,
        backend: MuJoCoPhysicsBackend,
    ) -> None:
        if (
            type(owner) is not OperationalClockOwner
            or type(origin_token) is not OperationalEventToken
            or type(deadline) is not OperationalDeadline
            or deadline.origin.event_identity != origin_token.event_identity
        ):
            raise RuntimeError("live owner and matching original allocation required")
        current = owner.read_current(after=origin_token)
        if not owner.before_deadline(deadline, current):
            raise TimeoutError("original execution deadline expired before binding")
        episode = backend.current_physics_observation().episode_id
        if not episode:
            raise RuntimeError("reset backend required")
        self._owner = owner
        self._origin_token = origin_token
        self._deadline = deadline
        self._backend = backend
        self._episode = episode
        self._cancelled: str | None = None
        self._readings: list[dict[str, Any]] = []

    @property
    def bound_backend(self) -> MuJoCoPhysicsBackend:
        return self._backend

    @property
    def evidence_scope(self) -> str:
        return "EXCLUDED_GUARDED_EXECUTION_DIAGNOSTIC"

    @property
    def native_authority(self) -> str:
        return "UNAVAILABLE"

    @property
    def qualification(self) -> str:
        return "UNKNOWN"

    @property
    def readings(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._readings]

    def cancel(self, reason: str) -> None:
        if type(reason) is not str or not reason:
            raise ValueError("nonempty cancellation reason required")
        if self._cancelled is None:
            self._cancelled = reason

    def __call__(self, boundary: ExecutionGuardBoundaryV1) -> None:
        row: dict[str, Any] = {
            "sequence": len(self._readings) + 1,
            "kind": boundary.kind,
            "phase": boundary.phase,
            "physics_step": boundary.physics_step,
            "deadline_ns": self._deadline.deadline_ns,
            "deadline_identity": self._deadline.issuance_identity,
        }
        if len(self._readings) >= 1024:
            raise RuntimeError("operational guard reading limit exceeded")
        self._readings.append(row)
        try:
            if self._cancelled is not None:
                raise RuntimeError("execution cancelled: " + self._cancelled)
            if (
                self._backend._execution_guard is not self
                or self._backend._episode_id != self._episode
                or boundary.episode_id != self._episode
            ):
                raise RuntimeError("execution backend or episode changed")
            current = self._owner.read_current(after=self._origin_token)
            row.update(current_lower_ns=current.lower_ns, current_upper_ns=current.upper_ns)
            if not self._owner.before_deadline(self._deadline, current):
                raise TimeoutError("original execution deadline expired")
            row["outcome"] = "ALLOWED"
        except BaseException as error:
            row.update(outcome="REJECTED", error_type=type(error).__name__, error=_error(error))
            raise


def _error(error: BaseException) -> str:
    try:
        return str(error)
    except BaseException:
        return "exception message unavailable"


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _save(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as out:
        json.dump(_plain(value), out, ensure_ascii=False, allow_nan=False, indent=2)
        out.write("\n")


def run_guarded_execution_diagnostic_v1(output: Path) -> dict[str, object]:
    """Run exactly one bounded, non-rendering two-step diagnostic with real time."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(output).free < 1024**3:
        raise RuntimeError("diagnostic needs at least 1 GiB free")
    config = SimulatorConfig(
        physics_dt_s=1 / 240,
        headless=True,
        render_rgb=False,
        render_depth=False,
        record_video=False,
        domain_randomization=False,
        seed=0,
    )
    paths = (
        _PLAN,
        "src/cloud_edge_robot_arm/research/guarded_execution_v1.py",
        "src/cloud_edge_robot_arm/research/operational_time_v1.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
        "src/cloud_edge_robot_arm/simulation/config.py",
        "src/cloud_edge_robot_arm/simulation/models.py",
        config.model_path,
    )
    pins = {}
    for name in paths:
        raw = (_ROOT / name).read_bytes()
        pins[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assignment = uuid4().hex
    _save(
        output / "preregistration.json",
        {
            "schema_version": "guarded-execution-diagnostic-preregistration.v1",
            "assignment": assignment,
            "config": config.model_dump(mode="json"),
            "scene": "S01_NORMAL_STATIC",
            "max_physics_steps": 2,
            "budget_ns": 10_000_000_000,
            "source_pins": pins,
        },
    )
    backend = MuJoCoPhysicsBackend()
    owner: OperationalClockOwner | None = None
    guard: OperationalExecutionGuardV1 | None = None
    operations: list[dict[str, Any]] = []
    refusals: list[str] = []
    secondary: list[dict[str, str]] = []
    primary: dict[str, str] | None = None
    final_state: Any = None
    deadline_payload: Any = None

    def observe(event: BackendOperationBoundary) -> None:
        operations.append(_plain(event))

    try:
        owner = open_operational_clock()
        token = owner.begin_event("diagnostic_allocation")
        _save(output / "allocation.json", {"assignment": assignment, "origin_token": token})
        owner.mark_event(token)
        origin = owner.end_event(token)
        deadline = owner.start_deadline(
            task_key=assignment, origin=origin, budget_ns=10_000_000_000
        )
        deadline_payload = _plain(deadline)
        _save(output / "deadline.json", deadline_payload)
        backend.initialize(config)
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
        _save(output / "reset-state.json", backend.current_physics_observation())
        guard = OperationalExecutionGuardV1(
            owner, origin_token=token, deadline=deadline, backend=backend
        )
        with backend.observe_operation_boundaries(observe):
            with backend.enforce_execution_guard(guard):
                joints = backend.get_joint_state().positions
                backend.apply_joint_targets(JointCommand(positions=joints))
                backend.apply_gripper_command(GripperCommand(open=True))
                backend.step(2)
                if backend.total_physics_steps != 2:
                    raise RuntimeError("unexpected diagnostic physical step count")
                while True:
                    current = owner.read_current(after=token)
                    if current.upper_ns >= deadline.deadline_ns:
                        if current.upper_ns > origin.lower_ns + 11_000_000_000:
                            raise RuntimeError(
                                "real deadline wait exceeded original 11-second limit"
                            )
                        break
                    time.sleep(min(0.02, (deadline.deadline_ns - current.upper_ns) / 1e9))
                try:
                    backend.apply_joint_targets(JointCommand(positions=joints))
                except TimeoutError:
                    refusals.append("expired_command")
                else:
                    raise RuntimeError("expired command was not refused")
                try:
                    backend.step()
                except RuntimeError:
                    refusals.append("expired_step")
                else:
                    raise RuntimeError("expired physics was not refused")
            try:
                backend.step()
            except RuntimeError:
                refusals.append("closed_step")
            else:
                raise RuntimeError("closed session resumed")
            backend.emergency_stop()
        if backend.operation_observer_failures or backend.total_physics_steps != 2:
            raise RuntimeError("diagnostic observer failed or extra physics occurred")
        for name, pin in pins.items():
            if hashlib.sha256((_ROOT / name).read_bytes()).hexdigest() != pin["sha256"]:
                raise RuntimeError("diagnostic source changed: " + name)
    except BaseException as error:
        primary = {"type": type(error).__name__, "message": _error(error)}
    finally:
        try:
            if backend._data is not None:
                final_state = backend.current_physics_observation()
        except BaseException as error:
            secondary.append(
                {"stage": "snapshot", "type": type(error).__name__, "message": _error(error)}
            )
        for name, value in (
            ("operations.json", operations),
            ("guard-events.json", backend.execution_guard_events),
            ("clock-readings.json", [] if guard is None else guard.readings),
            ("command-records.json", backend.command_records),
            ("observer-failures.json", backend.operation_observer_failures),
            ("final-state.json", final_state),
        ):
            try:
                _save(output / name, value)
            except BaseException as error:
                secondary.append(
                    {"stage": name, "type": type(error).__name__, "message": _error(error)}
                )
        for name, cleanup in (
            ("shutdown", backend.shutdown),
            ("clock_close", owner.close if owner is not None else lambda: None),
        ):
            try:
                cleanup()
            except BaseException as error:
                secondary.append(
                    {"stage": name, "type": type(error).__name__, "message": _error(error)}
                )
    result: dict[str, object] = {
        "schema_version": "guarded-execution-diagnostic.v1",
        "status": "PASS" if primary is None and not secondary else "FAIL",
        "assignment": assignment,
        "evidence_scope": "EXCLUDED_GUARDED_EXECUTION_DIAGNOSTIC",
        "native_authority": "UNAVAILABLE",
        "qualification": "UNKNOWN",
        "full_horizon_producer": "UNAVAILABLE",
        "physics_steps": backend.total_physics_steps,
        "expected_refusals": refusals,
        "original_deadline": deadline_payload,
        "primary_error": primary,
        "secondary_errors": secondary,
    }
    _save(output / "result.json", result)
    return result
