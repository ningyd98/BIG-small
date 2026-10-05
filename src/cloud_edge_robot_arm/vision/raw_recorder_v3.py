"""Record actual visual-worker sources without changing control or authorizing action.

The recorder borrows the existing backend, camera and SkillExecutor. Paired clock
samples only bracket the local calls; external UTC uncertainty remains unknown.
Raw geometry is written for offline evaluation and is never returned to a policy.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import struct
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import get_ident
from typing import Any
from uuid import uuid4

from cloud_edge_robot_arm.contracts import TaskContract, TaskStep
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor, StepExecutionResult
from cloud_edge_robot_arm.research.raw_episode_v3 import (
    ActionFrameJoinV3,
    ClockDescriptorV3,
    ClockPairV3,
    FrameAcquisitionV3,
    RawCommandV3,
    RawEpisodeEnvelopeV3,
    RawEpisodeIdentityV3,
    RawEpisodeRecordsV3,
    RawIntervalV3,
    RawPhysicsStepV3,
    TypedActionSpanV3,
    _replay_transform,
    validate_raw_episode_v3,
)
from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    BackendOperationBoundary,
    MuJoCoPhysicsBackend,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.vision.capture import CapturedFrame, MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame
from cloud_edge_robot_arm.vision.owner_registration import StepGroundingBinding, VisualOriginalPlan
from cloud_edge_robot_arm.vision.worker_owner import (
    pin_worker_source_inventory,
    read_visual_worker_lease,
)

RECORDER_SOURCE_PATHS = frozenset(
    {
        "src/cloud_edge_robot_arm/vision/raw_recorder_v3.py",
        "src/cloud_edge_robot_arm/research/raw_episode_v3.py",
        "src/cloud_edge_robot_arm/vision/capture.py",
        "src/cloud_edge_robot_arm/vision/observations.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
        "src/cloud_edge_robot_arm/edge/runtime/skill_executor.py",
    }
)
_KINDS = {
    "CONTROL": "CONTROL_APPLY",
    "PHYSICS": "PHYSICS_STEP",
    "COMMAND": "COMMAND",
    "CAPTURE": "ACQUISITION",
}
_PURPOSES = {"SETTLE", "WAIT", "VERIFY_ADVANCE", "HOLD", "TERMINATION"}


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _error(error: BaseException) -> str:
    try:
        message = str(error)
    except BaseException:
        message = "exception message unavailable"
    return f"{type(error).__name__}: {message}"


class VisualRawRecorderV3:
    """One owner-thread source recorder; never a third executor or safety gate."""

    def __init__(
        self,
        backend: MuJoCoPhysicsBackend,
        capture: MuJoCoCaptureSession,
        executor: SkillExecutor,
        *,
        directory: Path,
        source_root: Path,
        source_hashes: Mapping[str, str],
    ) -> None:
        if (
            not isinstance(backend, MuJoCoPhysicsBackend)
            or not isinstance(capture, MuJoCoCaptureSession)
            or not isinstance(executor, SkillExecutor)
        ):
            raise TypeError(
                "concrete existing backend, borrowed capture and SkillExecutor required"
            )
        if (
            capture._owns_backend
            or capture._backend is not backend
            or not isinstance(executor._robot, MuJoCoSkillRobot)
            or executor._robot._backend is not backend
        ):
            raise ValueError("recorder must borrow the same backend for capture and sole executor")
        self.backend, self.capture_session, self.executor = backend, capture, executor
        self.directory, self.source_root = Path(directory), Path(source_root)
        self.source_hashes = pin_worker_source_inventory(
            self.source_root, source_hashes, required_paths=RECORDER_SOURCE_PATHS
        )
        self._thread_id = get_ident()
        self._open = False
        self._entered = False
        self._observer_context: Any = None
        self._identity: RawEpisodeIdentityV3 | None = None
        self._original: VisualOriginalPlan | None = None
        self._descriptor: ClockDescriptorV3 | None = None
        self._record_seq = self._clock_seq = self._purpose_seq = 0
        self._intervals: list[dict[str, Any]] = []
        self._operations: dict[int, dict[str, Any]] = {}
        self._purpose_stack: list[str] = []
        self._purpose_allocations: list[str] = []
        self._action_stack: list[str] = []
        self._physics: list[dict[str, Any]] = []
        self._commands: list[dict[str, Any]] = []
        self._actions: list[dict[str, Any]] = []
        self._frames: list[dict[str, Any]] = []
        self._frame_aux: dict[str, dict[str, Any]] = {}
        self._joins: list[dict[str, Any]] = []
        self._allocated_actions: list[str] = []
        self._allocated_frames: list[str] = []
        self._controls: dict[int, tuple[str, dict[str, Any]]] = {}
        self._reset_result: dict[str, Any] | None = None
        self._reset_metadata: dict[str, Any] | None = None
        self._reset_count = 0
        self._clock_domain_id = f"clock-{os.getpid()}-{uuid4().hex}"
        self._worker_source_metadata: dict[str, Any] | None = None
        self._previous_state: dict[str, Any] | None = None
        self._explicit_capture = False
        self._derived_capture = False
        self._last_online_id: str | None = None
        self._last_returned_span: str | None = None
        self._audit_failures: list[str] = []
        self.last_captured_frame: CapturedFrame | None = None

    @property
    def allocated_action_span_ids(self) -> tuple[str, ...]:
        return tuple(self._allocated_actions)

    @property
    def allocated_acquisition_ids(self) -> tuple[str, ...]:
        return tuple(self._allocated_frames)

    def _require_open(self) -> None:
        if not self._open or get_ident() != self._thread_id:
            raise RuntimeError("recorder requires its active actual owner thread")

    def __enter__(self) -> VisualRawRecorderV3:
        if self._entered or get_ident() != self._thread_id:
            raise RuntimeError("recorder lifetime cannot be reused or transferred")
        self._observer_context = self.backend.observe_operation_boundaries(self._on_boundary)
        self._observer_context.__enter__()
        self._entered = self._open = True
        # A missing observed RESET remains INCOMPLETE, but subsequent partial
        # calls can still be recorded against their actual available state.
        if self.backend._episode_id is not None:
            try:
                self._previous_state = _plain(self.backend.current_physics_observation())
            except BaseException as audit_error:
                self._audit_failures.append(_error(audit_error))
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            self.flush()
        except BaseException as audit_error:
            self._audit_failures.append(_error(audit_error))
        finally:
            self._observer_context.__exit__(exc_type, exc, traceback)
            self._open = False

    def bind_source(
        self, identity: RawEpisodeIdentityV3, original_plan: VisualOriginalPlan
    ) -> None:
        self._require_open()
        if self._identity is not None:
            raise RuntimeError("recorder source is already bound")
        if (
            type(identity) is not RawEpisodeIdentityV3
            or type(original_plan) is not VisualOriginalPlan
        ):
            raise TypeError("typed detached original episode and plan source required")
        identity = RawEpisodeIdentityV3.from_json(json.dumps(identity.to_payload()))
        original_plan = VisualOriginalPlan(**{**original_plan.__dict__})
        if (
            identity.episode_id != self.backend._episode_id
            or identity.owner_identity != original_plan.identity
            or identity.role_bundle_hash != original_plan.role_bundle_hash
        ):
            raise ValueError("actual episode, original owner and role source must match")
        if dict(identity.source_hashes) != dict(self.source_hashes) or any(
            self.source_hashes.get(name) != digest
            for name, digest in original_plan.source_hashes.items()
        ):
            raise ValueError("complete current recorder/original source inventory must match")
        pin_worker_source_inventory(
            self.source_root, self.source_hashes, required_paths=RECORDER_SOURCE_PATHS
        )
        info = time.get_clock_info("monotonic")
        self._descriptor = ClockDescriptorV3(
            identity.clock_domain_id,
            identity.owner_identity.owner_epoch,
            "python.time.monotonic_ns",
            "python.datetime.now.UTC",
            max(1, math.ceil(info.resolution * 10**9)),
            1000,
            None,
            self.source_hashes,
        )
        self._identity, self._original = identity, original_plan

    def bind_worker_source(self, runtime: Any) -> RawEpisodeIdentityV3:
        """Derive source IDs from the current concrete job/attempt and actual reset.

        The simulation-job join and event publication are rechecked separately.
        This does not claim a transaction spanning their separate repositories.
        """
        from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime

        self._require_open()
        if type(runtime) is not VisualWorkerRuntime:
            raise TypeError("concrete adopted VisualWorkerRuntime required")
        if self._reset_count != 1 or self._reset_result is None or self._reset_metadata is None:
            raise RuntimeError(
                "single actual observed reset and full scene/config/asset source required"
            )
        source = runtime.source
        original = runtime.original
        definition = runtime.bootstrap.definition
        if (
            self._reset_metadata["config"] != _plain(self.backend._config)
            or self._reset_metadata["scenario"] != _plain(self.backend._scenario)
            or self._reset_metadata["asset_hash"] != self._current_asset_hash()
        ):
            raise ValueError("actual scene/config/asset source changed since observed reset")
        if runtime.episode_id != self.backend._episode_id or dict(source.source_hashes) != dict(
            self.source_hashes
        ):
            raise ValueError("actual worker episode and original recorder source inventory differ")
        with source.job_repository.publication_guard():
            lease = read_visual_worker_lease(
                source.job_repository,
                job_id=source.job_id,
                run_id=source.run_id,
                worker_id=source.worker_id,
                lease_id=source.lease_id,
            )
            current_owner = lease.identity(
                episode_id=self.backend._episode_id,
                task_id=original.contract.task_id,
                plan_id=source.plan_id,
                robot_id=source.robot_id,
            )
            if current_owner != original.identity:
                raise ValueError(
                    "current actual worker lease/attempt differs from adopted original"
                )
            job = SQLiteSimulationJobRepository.get_job(source.job_repository, source.job_id)
            attempts = [
                row
                for row in SQLiteSimulationJobRepository.list_attempts(
                    source.job_repository, source.run_id
                )
                if row.job_id == source.job_id
                and row.attempt == lease.attempt
                and row.ended_at is None
            ]
            if len(attempts) != 1:
                raise ValueError("unique actual open attempt source required")
            attempt = attempts[0]
            assignment = {
                name: getattr(job, name)
                for name in (
                    "job_id",
                    "run_id",
                    "batch_id",
                    "backend",
                    "scenario_id",
                    "control_mode",
                    "seed",
                    "manifest_id",
                    "reproducibility_hash",
                    "draft",
                    "manifest",
                )
            }
            if (
                job.scenario_id != self._reset_metadata["scenario"]["scenario_id"]
                or job.seed != self._reset_metadata["scenario"]["seed"]
                or job.backend != "MUJOCO"
            ):
                raise ValueError("actual job assignment differs from observed reset scenario")
            attempt_source = {
                "attempt": _plain(attempt),
                "lease_id": source.lease_id,
                "lease_acquired_at": lease.acquired_at.isoformat(),
            }
            identity = RawEpisodeIdentityV3(
                "attempt-" + _digest(attempt_source),
                job.run_id,
                _digest(assignment),
                self.backend._episode_id,
                "ONLINE_CED",
                current_owner,
                _digest(self._reset_metadata["scenario"]),
                self._reset_metadata["asset_hash"],
                _digest(self._reset_metadata["config"]),
                definition.role_bundle_hash,
                definition.model_snapshot_hash,
                self.source_hashes,
                self._clock_domain_id,
            )
        self.bind_source(identity, original)
        after = read_visual_worker_lease(
            source.job_repository,
            job_id=source.job_id,
            run_id=source.run_id,
            worker_id=source.worker_id,
            lease_id=source.lease_id,
        )
        if (
            after.identity(
                episode_id=self.backend._episode_id,
                task_id=original.contract.task_id,
                plan_id=source.plan_id,
                robot_id=source.robot_id,
            )
            != original.identity
        ):
            self._audit_failures.append("worker source changed across recorder binding")
            raise ValueError("current worker changed across source binding")
        self._worker_source_metadata = {
            "scope": "SOURCE_CONSISTENCY_ONLY",
            "assignment_hash_basis": "simulation_job_assignment.v1",
            "attempt_id_basis": "sha256.unique_open_simulation_attempt_and_lease.v1",
            "assignment": _plain(assignment),
            "attempt_source": attempt_source,
            "reset_metadata": self._reset_metadata,
            "identity": identity.to_payload(),
            "cross_repository_atomicity": False,
        }
        return identity

    def _current_asset_hash(self) -> str:
        if self.backend._mjspec_xml_sha256:
            return self.backend._mjspec_xml_sha256
        assert self.backend._config is not None
        path = Path(self.backend._config.model_path)
        if any(part.is_symlink() for part in (path.absolute(), *path.absolute().parents)):
            raise ValueError("actual model source lexical symlink rejected")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _next_seq(self) -> int:
        self._record_seq += 1
        return self._record_seq

    def _clock_pair(self) -> tuple[int, int, datetime, int]:
        self._clock_seq += 1
        before = time.monotonic_ns()
        utc_at = datetime.now(UTC)
        after = time.monotonic_ns()
        return self._clock_seq, before, utc_at, after

    def _new_interval(
        self, interval_id: str, kind: str, step: int, sim_time: float
    ) -> dict[str, Any]:
        row = dict(
            interval_id=interval_id,
            record_seq=self._next_seq(),
            kind=kind,
            start=self._clock_pair(),
            end=None,
            start_step=step,
            end_step=None,
            start_sim_time_s=sim_time,
            end_sim_time_s=None,
            disposition="PARTIAL",
            error="return boundary unavailable",
        )
        self._intervals.append(row)
        return row

    def _close_interval(self, row: dict[str, Any], error: str | None = None) -> None:
        row.update(
            end=self._clock_pair(),
            end_step=self.backend.total_physics_steps,
            end_sim_time_s=self.backend.get_sim_time(),
            disposition="ABORTED" if error else "COMPLETE",
            error=error,
        )

    @contextmanager
    def purpose(self, kind: str) -> Iterator[str]:
        self._require_open()
        if kind not in _PURPOSES:
            raise ValueError(
                "explicit existing settle/wait/verify/hold/termination purpose required"
            )
        self._purpose_seq += 1
        interval_id = f"purpose-{self._purpose_seq}"
        self._purpose_allocations.append(interval_id)
        row = None
        try:
            row = self._new_interval(
                interval_id, kind, self.backend.total_physics_steps, self.backend.get_sim_time()
            )
        except BaseException as audit_error:
            self._audit_failures.append(_error(audit_error))
        self._purpose_stack.append(interval_id)
        error = None
        try:
            yield interval_id
        except BaseException as operation_error:
            error = _error(operation_error)
            raise
        finally:
            self._purpose_stack.pop()
            try:
                if row is not None:
                    self._close_interval(row, error)
            except BaseException as audit_error:
                self._audit_failures.append(_error(audit_error))

    def _on_boundary(self, event: BackendOperationBoundary) -> None:
        if event.kind == "RESET":
            if event.phase == "BEGIN":
                self._reset_count += 1
                self._reset_metadata = {
                    "config": _plain(self.backend._config),
                    "scenario": _plain(event.parameters.get("requested")),
                    "asset_hash": self._current_asset_hash(),
                }
            if event.phase == "END" and event.result is not None and event.error_type is None:
                self._reset_result = _plain(event.result)
                self._previous_state = self._reset_result["physics_state"]
                if (
                    self._reset_metadata is None
                    or self._reset_metadata["asset_hash"] != self._current_asset_hash()
                    or self._reset_metadata["config"] != _plain(self.backend._config)
                    or self._reset_metadata["scenario"] != _plain(self.backend._scenario)
                ):
                    self._reset_metadata = None
                    self._audit_failures.append(
                        "actual reset scene/config/asset changed across boundaries"
                    )
            return
        if event.phase == "BEGIN":
            # Allocation precedes clock, conversion or persistence work.
            acquisition_id = None
            if event.kind == "CAPTURE":
                acquisition_id = f"acquisition-{len(self._allocated_frames) + 1}"
                self._allocated_frames.append(acquisition_id)
            allocated_operation: dict[str, Any] = dict(
                parameters=event.parameters,
                acquisition_id=acquisition_id,
                parent=self._purpose_stack[-1] if self._purpose_stack else "unbracketed-operations",
                action=self._action_stack[-1] if self._action_stack else None,
                input_role=(
                    "ONLINE" if self._explicit_capture and not self._derived_capture else "SOURCE"
                ),
                row=None,
            )
            self._operations[event.operation_id] = allocated_operation
            allocated_operation["row"] = self._new_interval(
                f"operation-{event.operation_id}",
                _KINDS[event.kind],
                event.physics_step,
                event.sim_time_s or 0.0,
            )
            return
        operation = self._operations.get(event.operation_id)
        if operation is None or operation["row"] is None:
            return
        row = operation["row"]
        self._close_interval(
            row, f"{event.error_type}: {event.error}" if event.error_type else None
        )
        result = event.result or {}
        if event.kind == "CONTROL" and "control_state" in result:
            payload = _plain(result["control_state"])
            self._controls[payload["physics_step"]] = (row["interval_id"], payload)
        elif event.kind == "PHYSICS" and "physics_state" in result:
            payload = _plain(result["physics_state"])
            control = self._controls.get(payload["physics_step"])
            if control is not None and self._previous_state is not None:
                self._physics.append(
                    dict(
                        record_seq=self._next_seq(),
                        physics_step=payload["physics_step"],
                        previous_state_hash=_digest(self._previous_state),
                        post_state_payload=payload,
                        control_payload=control[1],
                        physics_interval_id=row["interval_id"],
                        control_interval_id=control[0],
                        purpose_interval_id=operation["parent"],
                    )
                )
            self._previous_state = payload
        elif event.kind == "COMMAND":
            known = {command["command_seq"] for command in self._commands}
            for command in result.get("command_records", ()):
                if command["command_seq"] in known:
                    continue
                payload = _plain(command)
                effective = None
                if payload["accepted"]:
                    effective = payload["physics_step"] + 1
                    if payload["type"] == "joint_target" and payload["reason"].startswith(
                        "queued_until_physics_step="
                    ):
                        effective = max(effective, int(payload["reason"].split("=", 1)[1]) + 1)
                self._commands.append(
                    dict(
                        record_seq=self._next_seq(),
                        command_seq=payload["command_seq"],
                        command_payload=payload,
                        interval_id=row["interval_id"],
                        parent_interval_id=operation["parent"],
                        owner_action_span_id=operation["action"],
                        effective_from_step=effective,
                    )
                )
        elif event.kind == "CAPTURE":
            self._record_frame(event, operation)

    def _record_frame(self, event: BackendOperationBoundary, operation: dict[str, Any]) -> None:
        result = event.result or {}
        self._frame_aux[operation["acquisition_id"]] = {
            "instance_ids": tuple(result.get("instance_ids", ())),
            "instance_labels": _plain(result.get("instance_labels", {})),
        }
        observation = None
        if result.get("sensor_frame") is not None:
            try:
                observation = observation_from_sensor_frame(
                    _sensor_frame(result["sensor_frame"]), source="mujoco_camera"
                ).model_dump(mode="json")
            except BaseException as source_error:
                operation["row"].update(disposition="ABORTED", error=_error(source_error))
        camera_state = operation["parameters"].get("camera_state")
        physics = operation["parameters"].get("physics_state")
        self._frames.append(
            dict(
                record_seq=self._next_seq(),
                acquisition_id=operation["acquisition_id"],
                interval_id=operation["row"]["interval_id"],
                observation_payload=observation,
                camera_state_payload=_plain(camera_state) if camera_state else None,
                joined_physics_observation_hash=_digest(physics) if physics else None,
                pass_state_hashes=tuple(result.get("pass_state_hashes", ())),
                file_hashes={},
                input_role=operation["input_role"],
                source_acquisition_id=None,
                transform_payload=None,
                transform_source_hashes={},
            )
        )
        if observation is not None and operation["input_role"] == "ONLINE":
            self._last_online_id = operation["acquisition_id"]
            span = operation["action"] or self._last_returned_span
            if span is not None:
                self._add_join(
                    span,
                    self._frames[-1],
                    "DURING_ACTION" if operation["action"] else "AFTER_RETURN",
                )
                if operation["action"] is None:
                    self._last_returned_span = None

    def capture(self) -> RGBDObservation:
        self._require_open()
        if self._explicit_capture:
            raise RuntimeError("nested acquisition forbidden")
        transform = getattr(self.capture_session, "transform_observation", None)
        self._explicit_capture = True
        self._derived_capture = callable(transform)
        try:
            frame = self.capture_session.capture_with_instances()
            self.last_captured_frame = frame
            if self._derived_capture:
                return self._record_transformed_observation(frame.observation, transform)
            return frame.observation
        finally:
            self._explicit_capture = False
            self._derived_capture = False

    def _record_transformed_observation(
        self, observation: RGBDObservation, transform: Any
    ) -> RGBDObservation:
        """Keep the one actual camera source and its replayable online derivative."""
        if not self._frames or self._frames[-1]["observation_payload"] != observation.model_dump(
            mode="json"
        ):
            raise RuntimeError("derived input requires the recorded exact camera source")
        source = self._frames[-1]
        acquisition_id = f"acquisition-{len(self._allocated_frames) + 1}"
        self._allocated_frames.append(acquisition_id)
        row = {
            **source,
            "record_seq": self._next_seq(),
            "acquisition_id": acquisition_id,
            "input_role": "ONLINE",
            "observation_payload": None,
            "file_hashes": {},
            "source_acquisition_id": None,
            "transform_payload": None,
            "transform_source_hashes": {},
        }
        self._frames.append(row)
        self._last_online_id = None
        try:
            before = (
                self.backend._episode_id,
                self.backend.total_physics_steps,
                len(self.backend.command_records),
            )
            derived, policy, hashes = transform(observation.model_copy(deep=True))
            if (
                type(derived) is not RGBDObservation
                or not isinstance(hashes, Mapping)
                or not hashes
            ):
                raise ValueError("typed derived observation and pinned transform sources required")
            if any(self.source_hashes.get(name) != value for name, value in hashes.items()):
                raise ValueError("transform source differs from original pinned inventory")
            verified = pin_worker_source_inventory(
                self.source_root, hashes, required_paths=frozenset(hashes)
            )
            policy = _plain(policy)
            expected = _replay_transform(observation.model_dump(mode="json"), policy)
            if derived.model_dump(mode="json") != expected:
                raise ValueError("derived online pixels differ from the fixed corruption recipe")
            after = (
                self.backend._episode_id,
                self.backend.total_physics_steps,
                len(self.backend.command_records),
            )
            if after != before:
                raise RuntimeError(
                    "sensor transform changed the actual camera episode or control state"
                )
            pin_worker_source_inventory(
                self.source_root, verified, required_paths=frozenset(verified)
            )
            row.update(
                observation_payload=derived.model_dump(mode="json"),
                source_acquisition_id=source["acquisition_id"],
                transform_payload=policy,
                transform_source_hashes=verified,
            )
            self._frame_aux[acquisition_id] = dict(
                self._frame_aux.get(source["acquisition_id"], {})
            )
            self._last_online_id = acquisition_id
            span = self._action_stack[-1] if self._action_stack else self._last_returned_span
            if span is not None:
                self._add_join(span, row, "DURING_ACTION" if self._action_stack else "AFTER_RETURN")
                if not self._action_stack:
                    self._last_returned_span = None
            return derived
        except BaseException as transform_error:
            self._audit_failures.append(_error(transform_error))
            raise

    def execute_attempt(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
        grounding: StepGroundingBinding | None = None,
    ) -> StepExecutionResult:
        self._require_open()
        if self._original is None:
            raise RuntimeError("executor recording requires adopted original plan source")
        span_id = f"action-span-{len(self._allocated_actions) + 1}"
        self._allocated_actions.append(span_id)
        interval_id = f"attempt-{len(self._allocated_actions)}"
        start_step = self.backend.total_physics_steps
        row = None
        try:
            row = self._new_interval(
                interval_id, "EXECUTOR_ATTEMPT", start_step, self.backend.get_sim_time()
            )
        except BaseException as audit_error:
            self._audit_failures.append(_error(audit_error))
        command_start = len(self.backend.command_records) + 1
        self._purpose_stack.append(interval_id)
        self._action_stack.append(span_id)
        if self._last_online_id is not None:
            try:
                before = next(
                    frame
                    for frame in self._frames
                    if frame["acquisition_id"] == self._last_online_id
                )
                self._add_join(span_id, before, "BEFORE_SUBMIT")
            except BaseException as audit_error:
                self._audit_failures.append(_error(audit_error))
        result = None
        error = None
        try:
            result = self.executor.execute_attempt(contract=contract, step=step, attempt=attempt)
            return result
        except BaseException as operation_error:
            error = _error(operation_error)
            raise
        finally:
            self._action_stack.pop()
            self._purpose_stack.pop()
            if row is not None:
                try:
                    self._close_interval(row, error)
                except BaseException as audit_error:
                    self._audit_failures.append(_error(audit_error))
            try:
                action_result = result.action_result if result is not None else None
                changed = (
                    self.backend.total_physics_steps != start_step
                    or len(self.backend.command_records) + 1 != command_start
                )
                disposition = (
                    "PARTIAL"
                    if error is not None and changed
                    else "ABORTED"
                    if error is not None
                    else "RETURNED"
                    if action_result is not None
                    else "PARTIAL"
                    if changed
                    else "REJECTED"
                )
                reason = (
                    error
                    or (result.error_code if result is not None else None)
                    or ("actual action result unavailable" if action_result is None else None)
                )
                self._actions.append(
                    dict(
                        record_seq=self._next_seq(),
                        span_id=span_id,
                        original_plan=self._original,
                        step_id=step.step_id,
                        attempt=attempt,
                        grounding=grounding,
                        interval_id=interval_id,
                        command_seq_start=command_start,
                        command_seq_end=len(self.backend.command_records) + 1,
                        returned_result=action_result.model_dump(mode="json")
                        if action_result is not None
                        else None,
                        disposition=disposition,
                        error=reason,
                        executed_step_payload=step.model_dump(mode="json"),
                    )
                )
                self._last_returned_span = span_id
            except BaseException as audit_error:
                self._audit_failures.append(_error(audit_error))

    def _add_join(self, span_id: str, frame: dict[str, Any], relation: str) -> None:
        observation = frame["observation_payload"]
        self._joins.append(
            dict(
                record_seq=self._next_seq(),
                span_id=span_id,
                acquisition_id=frame["acquisition_id"],
                relation=relation,
                observation_id=observation["observation_id"],
                checksum_sha256=observation["checksum_sha256"],
            )
        )

    def join_frame(self, span_id: str, observation: RGBDObservation, relation: str) -> None:
        self._require_open()
        if span_id not in self._allocated_actions or relation not in {
            "BEFORE_SUBMIT",
            "DURING_ACTION",
            "AFTER_RETURN",
            "TERMINAL",
        }:
            raise ValueError("existing actual span and explicit frame relation required")
        frame = next(
            (
                item
                for item in self._frames
                if item["observation_payload"] is not None
                and item["observation_payload"]["observation_id"] == observation.observation_id
                and item["observation_payload"]["checksum_sha256"] == observation.checksum_sha256
            ),
            None,
        )
        if frame is None:
            raise ValueError("join requires exact original captured observation")
        self._add_join(span_id, frame, relation)

    def _paired(self, value: tuple[int, int, datetime, int]) -> ClockPairV3:
        assert self._identity is not None and self._descriptor is not None
        return ClockPairV3(self._identity.clock_domain_id, self._descriptor.digest(), *value)

    def _save_frames(self) -> dict[str, str]:
        inventory = {}
        for frame in self._frames:
            if frame["observation_payload"] is None:
                continue
            observation = RGBDObservation.model_validate(frame["observation_payload"])
            blobs = {
                "rgb.png": base64.b64decode(observation.rgb_png_base64),
                "depth.f32": base64.b64decode(observation.depth_float32_base64),
                "mask.u8": observation.valid_mask_bytes(),
            }
            aux = self._frame_aux.get(frame["acquisition_id"], {})
            ids = aux.get("instance_ids", ())
            blobs["instances.i32"] = struct.pack(f"<{len(ids)}i", *ids)
            metadata = {
                "scope": "OFFLINE_SOURCE_ONLY",
                "online_geometry_source": False,
                "observation": frame["observation_payload"],
                "camera_state": frame["camera_state_payload"],
                "pass_state_hashes": frame["pass_state_hashes"],
                "instance_labels": aux.get("instance_labels", {}),
                "instances_available": len(ids) == observation.width * observation.height,
                "instance_id_count": len(ids),
            }
            blobs["source-frame.json"] = (
                json.dumps(metadata, sort_keys=True, allow_nan=False) + "\n"
            ).encode()
            hashes = {}
            for filename, content in blobs.items():
                name = f"frames/{frame['acquisition_id']}/{filename}"
                target = self.directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                hashes[name] = hashlib.sha256(content).hexdigest()
            frame["file_hashes"] = hashes
            inventory.update(hashes)
        return inventory

    def build_records(self) -> RawEpisodeRecordsV3:
        self._require_open()
        if self._identity is None:
            raise RuntimeError("typed records require bound actual episode source")
        intervals = tuple(
            RawIntervalV3(
                identity=self._identity,
                **{
                    **row,
                    "start": self._paired(row["start"]),
                    "end": self._paired(row["end"]) if row["end"] else None,
                },
            )
            for row in self._intervals
        )
        return RawEpisodeRecordsV3(
            intervals,
            tuple(RawPhysicsStepV3(identity=self._identity, **row) for row in self._physics),
            tuple(RawCommandV3(identity=self._identity, **row) for row in self._commands),
            tuple(TypedActionSpanV3(identity=self._identity, **row) for row in self._actions),
            tuple(FrameAcquisitionV3(identity=self._identity, **row) for row in self._frames),
            tuple(ActionFrameJoinV3(identity=self._identity, **row) for row in self._joins),
        )

    def build_envelope(self, original_file_hashes: Mapping[str, str]) -> RawEpisodeEnvelopeV3:
        self._require_open()
        if (
            self._identity is None
            or self._descriptor is None
            or self._original is None
            or self._reset_result is None
        ):
            raise RuntimeError("complete bound source and actual observed RESET required")
        return RawEpisodeEnvelopeV3(
            self._identity,
            self._descriptor,
            self._reset_result["physics_state"],
            _plain(self.backend.current_physics_observation()),
            120,
            self._reset_result["physics_dt_s"],
            len(self.backend.command_records),
            self.allocated_action_span_ids,
            self.allocated_acquisition_ids,
            original_file_hashes,
            self._original.task_deadline_at,
            self._original.verification_deadline_at,
            self._original.contract.valid_until,
            self._reset_result["initial_controller_targets"],
            self._reset_result["actuator_delay_steps"],
        )

    def _write_json(self, name: str, value: Any) -> str:
        content = (
            json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n"
        ).encode()
        (self.directory / name).write_bytes(content)
        return hashlib.sha256(content).hexdigest()

    def flush(self) -> dict[str, Any]:
        self._require_open()
        self.directory.mkdir(parents=True, exist_ok=True)
        ledger = {
            "scope": "SOURCE_CONSISTENCY_ONLY",
            "source_binding": "BOUND" if self._identity else "UNBOUND",
            "allocated_action_span_ids": list(self._allocated_actions),
            "allocated_acquisition_ids": list(self._allocated_frames),
            "allocated_purpose_interval_ids": list(self._purpose_allocations),
            "backend_operation_allocations": len(
                {row["operation_id"] for row in self.backend.operation_ledger}
            ),
            "backend_operation_ledger": _plain(self.backend.operation_ledger),
            "observer_failures": [
                *_plain(self.backend.operation_observer_failures),
                *self._audit_failures,
            ],
            "observer_overhead_ns": self.backend.operation_observer_overhead_ns,
            "actual_observed_reset": self._reset_result is not None,
            "monotonic_implementation": time.get_clock_info("monotonic").implementation,
            "continuous_motion": "NOT_CERTIFIED",
            "utc_mapping": "UNAVAILABLE",
        }
        hashes = {"allocation-ledger.json": self._write_json("allocation-ledger.json", ledger)}
        if self._worker_source_metadata is not None:
            hashes["worker-source.json"] = self._write_json(
                "worker-source.json", self._worker_source_metadata
            )
        status, reasons = "INCOMPLETE", []
        try:
            pin_worker_source_inventory(
                self.source_root, self.source_hashes, required_paths=RECORDER_SOURCE_PATHS
            )
        except (ValueError, TypeError, OSError) as source_error:
            status = "INVALID"
            reasons.append("source_inventory: " + _error(source_error))
        try:
            frame_hashes = self._save_frames()
            hashes.update(frame_hashes)
            if self._identity is not None:
                records = self.build_records()
                hashes["raw-records.json"] = self._write_json(
                    "raw-records.json", records.to_payload()
                )
                envelope = self.build_envelope(frame_hashes)
                hashes["raw-envelope.json"] = self._write_json(
                    "raw-envelope.json", envelope.to_payload()
                )
                view = validate_raw_episode_v3(envelope, records)
                hashes["raw-consistency.json"] = self._write_json(
                    "raw-consistency.json", view.to_payload()
                )
                if status != "INVALID":
                    status = view.status
                reasons.extend(view.reasons)
                if ledger["observer_failures"] and status == "COMPLETE":
                    status, reasons = "INCOMPLETE", ["actual_observer_failure"]
        except BaseException as source_error:
            reasons.append(_error(source_error))
        report = {
            "scope": "SOURCE_CONSISTENCY_ONLY",
            "source_consistency": status,
            "continuous_motion": "NOT_CERTIFIED",
            "utc_mapping": "UNAVAILABLE",
            "reasons": reasons,
            "file_hashes": hashes,
            "allocated_actions": len(self._allocated_actions),
            "allocated_acquisitions": len(self._allocated_frames),
        }
        self._write_json("raw-artifacts.json", report)
        return report


def _sensor_frame(payload: Mapping[str, Any]) -> SensorFrame:
    return SensorFrame(**dict(payload))
