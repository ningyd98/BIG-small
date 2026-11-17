"""Bounded continuous RGBD feedback inside MuJoCo actuator motion.

The episode owner supplies synchronous measurements and safety checks. No models,
object truth, background simulation thread or direct physics-state writes occur.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.models import JointCommand
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.clearance_control import CartesianMotionReference
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
    MotionResult,
    MotionTarget,
    MuJoCoMotionController,
)


@dataclass(frozen=True)
class VisualServoConfig:
    vision_period_s: float = 1 / 30
    max_sample_latency_s: float = 0.1
    max_frame_delta_m: float = 0.01
    max_correction_m: float = 0.05
    stable_samples: int = 3

    def __post_init__(self) -> None:
        for name in ("vision_period_s", "max_sample_latency_s", "max_frame_delta_m",
                     "max_correction_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError("servo limits must be finite and positive")
        if self.vision_period_s > 0.1 or self.max_sample_latency_s > 0.1:
            raise ValueError("servo sampling gap/latency must not exceed 0.1 s")
        if self.max_frame_delta_m > 0.01 or self.max_correction_m > 0.05:
            raise ValueError("servo correction bounds exceed development policy")
        if type(self.stable_samples) is not int or not 3 <= self.stable_samples <= 30:
            raise ValueError("servo requires at least three fresh stable samples")


@dataclass
class VisualServoSession:
    sample: Callable[[MotionTarget], MotionTarget]
    config: VisualServoConfig = field(default_factory=VisualServoConfig)
    vertical_clearance: VerticalClearancePath | None = None
    records: list[dict[str, Any]] = field(default_factory=list, init=False)
    started: bool = field(default=False, init=False)
    terminal_reason: str | None = field(default=None, init=False)
    started_at_monotonic: float | None = field(default=None, init=False)


class MuJoCoVisualServoController:
    def __init__(self, backend: MuJoCoPhysicsBackend) -> None:
        self.backend = backend
        self.kinematics = MuJoCoMotionController(backend)

    @staticmethod
    def _validate_target(target: MotionTarget) -> np.ndarray:
        values = np.array([target.position.x, target.position.y, target.position.z])
        quat = np.array(target.orientation_wxyz)
        if (not np.isfinite(values).all() or quat.shape != (4,)
                or not np.isfinite(quat).all() or abs(np.linalg.norm(quat) - 1) > 1e-3):
            raise ValueError("invalid visual servo position or unit quaternion")
        return values

    def monitor_hold(self, target: MotionTarget, session: VisualServoSession) -> None:
        """Refresh evidence during a fixed contact hold without moving its endpoint."""
        sampled_at = time.perf_counter()
        try:
            measured = session.sample(target)
            position = self._validate_target(measured)
            if measured != target:
                raise ValueError("visual servo hold endpoint changed")
            latency = time.perf_counter() - sampled_at
            if latency > session.config.max_sample_latency_s:
                raise ValueError("visual servo hold sample deadline exceeded")
            assert self.backend._model is not None
            error, angle = self.kinematics._pose_error(
                position, np.asarray(target.orientation_wxyz), self.backend._model.site("tcp").id
            )
            session.records.append({
                "phase": "HOLD", "physics_step": self.backend.total_physics_steps,
                "sim_time_s": self.backend.get_sim_time(),
                "wall_elapsed_s": time.monotonic() - (session.started_at_monotonic or sampled_at),
                "sample_and_ik_s": latency, "target_pose": measured.position.model_dump(),
                "position_error_m": error, "orientation_error_deg": angle,
                "max_command_acceleration_rad_s2": 0.0,
            })
        except BaseException as error:
            session.terminal_reason = f"{type(error).__name__}:{error}"
            self.backend.hold_current_joints()
            raise

    def move_tcp(
        self,
        target: MotionTarget,
        timeout_s: float,
        *,
        session: VisualServoSession,
        max_joint_velocity_rad_s: float = 1.5,
        max_joint_acceleration_rad_s2: float = 4.0,
        state_guard: Callable[[], None] | None = None,
        keep_cartesian_attitude: bool = False,
    ) -> MotionResult:
        with self.backend.sensor_capture_on_demand():
            return self._move_tcp(
                target, timeout_s, session=session,
                max_joint_velocity_rad_s=max_joint_velocity_rad_s,
                max_joint_acceleration_rad_s2=max_joint_acceleration_rad_s2,
                state_guard=state_guard,
                keep_cartesian_attitude=keep_cartesian_attitude,
            )

    def _move_tcp(
        self,
        target: MotionTarget,
        timeout_s: float,
        *,
        session: VisualServoSession,
        max_joint_velocity_rad_s: float = 1.5,
        max_joint_acceleration_rad_s2: float = 4.0,
        state_guard: Callable[[], None] | None = None,
        keep_cartesian_attitude: bool = False,
    ) -> MotionResult:
        backend = self.backend
        model, data, config = backend._model, backend._data, backend._config
        if model is None or data is None or config is None:
            raise RuntimeError("MuJoCo backend is not initialized")
        start = backend.total_physics_steps
        wall_start = time.monotonic()
        status = "TIMED_OUT"
        retain_reference_hold = False
        try:
            for value in (timeout_s, max_joint_velocity_rad_s, max_joint_acceleration_rad_s2):
                if not math.isfinite(value) or value <= 0:
                    raise ValueError("motion limits must be finite and positive")
            if session.started:
                raise ValueError("visual servo session was already used")
            session.started = True
            session.started_at_monotonic = wall_start
            initial = self._validate_target(target)
            path = session.vertical_clearance
            peak_z = backend.get_tcp_pose().z

            def guard() -> None:
                nonlocal peak_z
                if state_guard is not None:
                    state_guard()
                if path is not None:
                    pose = backend.get_tcp_pose()
                    path.check_position((pose.x, pose.y, pose.z), peak_z=peak_z)
                    peak_z = max(peak_z, pose.z)

            if path is not None:
                path.check_binding(
                    task_id=path.task_id, step_id=path.step_id, skill=path.skill,
                    target=target.position.model_dump(), minimum_height_m=path.minimum_height_m,
                )
            guard()
            if backend.estop_engaged:
                error, angle = self.kinematics._pose_error(
                    initial, np.asarray(target.orientation_wxyz), model.site("tcp").id
                )
                return MotionResult("EMERGENCY_STOP", error, angle, 0)
            max_steps = math.floor(timeout_s / config.physics_dt_s)
            if max_steps < 1:
                raise ValueError("timeout must allow at least one physics step")
            control_steps = max(1, round(config.control_dt_s / config.physics_dt_s))
            vision_steps = max(1, math.ceil(session.config.vision_period_s / config.physics_dt_s))
            next_vision = 0
            sent = backend.get_joint_command_state()
            command = np.array(sent.positions_rad if sent.retained_target else data.qpos[:7])
            velocity = np.array(sent.velocity_rad_s) if sent.retained_target else np.zeros(7)
            held_s = backend.get_sim_time() - sent.sim_time_s
            if held_s < -1e-9 or np.max(np.abs(velocity)) > max_joint_velocity_rad_s + 1e-8:
                raise ValueError("joint command handoff exceeds the requested limits")
            reaffirm_hold = sent.retained_target and held_s > 1e-9
            if reaffirm_hold:
                # Explicitly reaffirm the retained equilibrium before restarting
                # the fixed grid. The preceding finite-difference velocity must
                # be able to reach zero over the actual handoff interval.
                if np.max(np.abs(velocity)) > max_joint_acceleration_rad_s2 * held_s + 1e-8:
                    raise ValueError("joint command handoff cannot settle within acceleration")
                velocity = np.zeros(7)
            next_control = control_steps if sent.retained_target and not reaffirm_hold else 0
            previous = initial.copy()
            goal = command.copy()
            current = target
            settled = 0
            max_acceleration = 0.0
            lower = np.array([model.jnt_range[model.joint(n).id, 0]
                              for n in backend._joint_names]) + 0.001
            upper = np.array([model.jnt_range[model.joint(n).id, 1]
                              for n in backend._joint_names]) - 0.001
            site = model.site("tcp").id
            clearance_quat = np.asarray(target.orientation_wxyz)
            if path is not None:
                # The grasp has already converged within the registered 5 deg
                # tolerance. Preserve that measured tool attitude while leaving
                # the table; aligning it more tightly here pushes the held cube
                # sideways before it has cleared the support.
                _, initial_angle = self.kinematics._pose_error(initial, clearance_quat, site)
                if initial_angle > 5:
                    raise ValueError("clearance requires an already aligned tool attitude")
                assert backend._mujoco is not None
                clearance_quat = np.empty(4)
                backend._mujoco.mju_mat2Quat(clearance_quat, data.site_xmat[site])
            start_pose = backend.get_tcp_pose()
            reference = CartesianMotionReference(
                backend, path.start_m if path else (start_pose.x, start_pose.y, start_pose.z),
                path.target_m if path else (
                    target.position.x, target.position.y, target.position.z,
                ),
                clearance_quat, control_steps=control_steps,
                timeout_s=timeout_s, max_velocity=max_joint_velocity_rad_s,
                max_acceleration=max_joint_acceleration_rad_s2,
                initialize_load_from_feedback=path is None,
            ) if path is not None or keep_cartesian_attitude else None
            while backend.total_physics_steps - start < max_steps:
                guard()
                elapsed = backend.total_physics_steps - start
                if backend.estop_engaged:
                    status = "EMERGENCY_STOP"
                    break
                if time.monotonic() - wall_start >= timeout_s:
                    break
                if elapsed >= next_vision:
                    sampled_at = time.perf_counter()
                    current = session.sample(current)
                    position = self._validate_target(current)
                    if path is not None:
                        path.check_binding(
                            task_id=path.task_id, step_id=path.step_id, skill=path.skill,
                            target=current.position.model_dump(),
                            minimum_height_m=path.minimum_height_m,
                        )
                    elif reference is not None and not np.array_equal(position, initial):
                        raise ValueError("Cartesian reference endpoint changed")
                    if np.linalg.norm(position - previous) > session.config.max_frame_delta_m:
                        raise ValueError("visual servo target jump")
                    if np.linalg.norm(position - initial) > session.config.max_correction_m:
                        raise ValueError("visual servo correction envelope exceeded")
                    if current.orientation_wxyz != target.orientation_wxyz:
                        raise ValueError("visual servo orientation changes are unsupported")
                    solved = goal if reference is not None else self.kinematics._inverse_kinematics(
                        position, np.asarray(current.orientation_wxyz), site,
                    )
                    latency = time.perf_counter() - sampled_at
                    if latency > session.config.max_sample_latency_s:
                        raise ValueError(
                            f"visual servo sample/IK deadline exceeded ({latency:.6f}s)"
                        )
                    if solved is None:
                        status = "UNREACHABLE"
                        break
                    goal = solved
                    error, angle = self.kinematics._pose_error(
                        position, np.asarray(current.orientation_wxyz), site
                    )
                    settled = settled + 1 if error <= 0.005 and angle <= 5 else 0
                    session.records.append({
                        "physics_step": backend.total_physics_steps,
                        "sim_time_s": backend.get_sim_time(),
                        "wall_elapsed_s": time.monotonic() - wall_start,
                        "sample_and_ik_s": latency,
                        "target_pose": current.position.model_dump(),
                        "position_error_m": error,
                        "orientation_error_deg": angle,
                        "max_command_acceleration_rad_s2": max_acceleration,
                    })
                    if len(session.records) >= 2048:
                        raise ValueError("visual servo feedback budget exhausted")
                    previous = position
                    next_vision += vision_steps
                    if settled >= session.config.stable_samples and reference is None:
                        status = "SUCCEEDED"
                        break
                if elapsed >= next_control:
                    guard()
                    dt = control_steps * config.physics_dt_s
                    if reference is not None:
                        goal = reference.joint_target(elapsed, control_steps)
                        if (
                            elapsed * config.physics_dt_s >= (
                                reference.duration_s + reference.settle_s
                            )
                            and settled >= session.config.stable_samples
                            and np.max(np.abs(velocity)) <= max_joint_acceleration_rad_s2 * dt
                        ):
                            # A duplicate final command explicitly sets command
                            # velocity to zero on the original control grid.
                            backend.apply_joint_targets(JointCommand(
                                positions=command.tolist(), max_velocity=max_joint_velocity_rad_s,
                            ))
                            retain_reference_hold = True
                            status = "SUCCEEDED"
                            break
                    if reaffirm_hold:
                        reaffirm_hold = False
                    else:
                        desired = np.clip((goal - command) / dt,
                                          -max_joint_velocity_rad_s, max_joint_velocity_rad_s)
                        change = np.clip(desired - velocity,
                                         -max_joint_acceleration_rad_s2 * dt,
                                         max_joint_acceleration_rad_s2 * dt)
                        velocity += change
                        max_acceleration = max(
                            max_acceleration, float(np.max(np.abs(change))) / dt,
                        )
                        command += velocity * dt
                    if np.any(command < lower) or np.any(command > upper):
                        raise ValueError("visual servo joint target outside physical range")
                    backend.apply_joint_targets(JointCommand(
                        positions=command.tolist(), max_velocity=max_joint_velocity_rad_s
                    ))
                    next_control += control_steps
                # Independent deadlines keep 30 Hz vision and the original
                # control grid. Splitting physics must not change command dt.
                chunk = min(next_control - elapsed, next_vision - elapsed, max_steps - elapsed)
                if state_guard is None and reference is None:
                    backend.step(chunk)
                else:
                    for _ in range(chunk):
                        backend.step(1)
                        if reference is not None:
                            reference.observe_step()
                        guard()
            position = self._validate_target(current)
            error, angle = self.kinematics._pose_error(
                position, np.asarray(current.orientation_wxyz), site
            )
            session.terminal_reason = status
            return MotionResult(
                status, error, angle, backend.total_physics_steps - start,
                reference.max_compensation_rad if reference is not None else 0.0,
            )
        except BaseException as error:
            session.terminal_reason = f"{type(error).__name__}:{error}"
            raise
        finally:
            # Also cancel queued trajectories after camera, safety, lease or step
            # callbacks throw. Holding never advances the simulation.
            if not retain_reference_hold:
                backend.hold_current_joints()
