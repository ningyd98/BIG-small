"""Bounded task-space motion on the real MuJoCo arm actuators."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.models import JointCommand
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


@dataclass(frozen=True)
class MotionTarget:
    position: Pose
    orientation_wxyz: tuple[float, float, float, float]


@dataclass(frozen=True)
class MotionResult:
    status: str
    position_error_m: float
    orientation_error_deg: float
    physics_steps: int
    max_load_compensation_rad: float = 0.0


def _rotation_error(target: np.ndarray, current: np.ndarray) -> np.ndarray:
    """World-frame logarithmic rotation error, in radians."""
    import mujoco

    current_quat = np.empty(4, dtype=float)
    mujoco.mju_mat2Quat(current_quat, current.reshape(9))
    inverse = current_quat * np.array([1.0, -1.0, -1.0, -1.0])
    difference = np.empty(4, dtype=float)
    mujoco.mju_mulQuat(difference, target, inverse)
    if difference[0] < 0:
        difference *= -1.0
    sine = float(np.linalg.norm(difference[1:]))
    if sine < 1e-12:
        return np.zeros(3, dtype=float)
    angle = 2.0 * math.atan2(sine, float(difference[0]))
    return difference[1:] * (angle / sine)


class MuJoCoMotionController:
    """Solve IK on scratch data, then move only through joint actuators and mj_step."""

    def __init__(self, backend: MuJoCoPhysicsBackend) -> None:
        self._backend = backend

    def move_tcp(
        self,
        target: MotionTarget,
        timeout_s: float,
        *,
        max_joint_velocity_rad_s: float = 1.5,
        max_joint_acceleration_rad_s2: float = 4.0,
    ) -> MotionResult:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be positive and finite")
        if not math.isfinite(max_joint_velocity_rad_s) or max_joint_velocity_rad_s <= 0:
            raise ValueError("max_joint_velocity_rad_s must be positive and finite")
        if not math.isfinite(max_joint_acceleration_rad_s2) or max_joint_acceleration_rad_s2 <= 0:
            raise ValueError("max_joint_acceleration_rad_s2 must be positive and finite")
        quat = np.asarray(target.orientation_wxyz, dtype=float)
        if (
            quat.shape != (4,)
            or not np.isfinite(quat).all()
            or abs(np.linalg.norm(quat) - 1) > 1e-3
        ):
            raise ValueError("orientation quaternion must be finite and unit length")
        model = self._backend._model
        data = self._backend._data
        mujoco = self._backend._mujoco
        config = self._backend._config
        if model is None or data is None or mujoco is None or config is None:
            raise RuntimeError("MuJoCo backend is not initialized")
        site_id = model.site("tcp").id
        desired_position = np.array(
            [target.position.x, target.position.y, target.position.z], dtype=float
        )
        start_steps = self._backend.total_physics_steps
        initial_position_error, initial_orientation_error = self._pose_error(
            desired_position, quat, site_id
        )
        if self._backend.estop_engaged:
            return MotionResult(
                "EMERGENCY_STOP", initial_position_error, initial_orientation_error, 0
            )
        goal = self._inverse_kinematics(desired_position, quat, site_id)
        if goal is None:
            self._backend.hold_current_joints()
            return MotionResult("UNREACHABLE", initial_position_error, initial_orientation_error, 0)

        max_steps = max(1, int(timeout_s / config.physics_dt_s))
        control_steps = max(1, int(round(config.control_dt_s / config.physics_dt_s)))
        command = np.array(data.qpos[:7], dtype=float)
        command_velocity = np.zeros(7, dtype=float)
        effective_goal = np.array(goal, copy=True)
        load_compensated = False
        max_load_compensation_rad = 0.0
        settled_time_s = 0.0
        while self._backend.total_physics_steps - start_steps < max_steps:
            if self._backend.estop_engaged:
                status = "EMERGENCY_STOP"
                break
            position_error, orientation_error = self._pose_error(
                desired_position, quat, site_id
            )
            if position_error <= 0.005 and orientation_error <= 5.0:
                # The last trajectory command can still be far from measured
                # joints. Cancel it before a gripper-only action advances physics.
                self._backend.hold_current_joints()
                return MotionResult(
                    "SUCCEEDED",
                    position_error,
                    orientation_error,
                    self._backend.total_physics_steps - start_steps,
                    max_load_compensation_rad,
                )
            remaining = max_steps - (self._backend.total_physics_steps - start_steps)
            chunk = min(control_steps, remaining)
            dt = chunk * config.physics_dt_s
            if not load_compensated:
                if (
                    float(np.max(np.abs(goal - command))) <= 0.005
                    and float(np.max(np.abs(data.qvel[:7]))) <= 0.02
                ):
                    settled_time_s += dt
                else:
                    settled_time_s = 0.0
                if settled_time_s >= 0.1:
                    # A grasped payload may hold the physical joints a few
                    # milliradians off the unloaded IK solution. Add one
                    # bounded actuator-target correction after motion settles.
                    correction = np.clip(goal - data.qpos[:7], -0.03, 0.03)
                    lower = np.array([
                        model.jnt_range[model.joint(name).id, 0]
                        for name in self._backend._joint_names
                    ]) + 0.001
                    upper = np.array([
                        model.jnt_range[model.joint(name).id, 1]
                        for name in self._backend._joint_names
                    ]) - 0.001
                    effective_goal = np.clip(goal + correction, lower, upper)
                    max_load_compensation_rad = float(
                        np.max(np.abs(effective_goal - goal))
                    )
                    load_compensated = True
            desired_velocity = np.clip(
                (effective_goal - command) / dt,
                -max_joint_velocity_rad_s,
                max_joint_velocity_rad_s,
            )
            command_velocity += np.clip(
                desired_velocity - command_velocity,
                -max_joint_acceleration_rad_s2 * dt,
                max_joint_acceleration_rad_s2 * dt,
            )
            command += command_velocity * dt
            self._backend.apply_joint_targets(
                JointCommand(positions=command.tolist(), max_velocity=max_joint_velocity_rad_s)
            )
            self._backend.step(steps=chunk)
        else:
            status = "TIMED_OUT"
        if status == "TIMED_OUT":
            self._backend.hold_current_joints()
        position_error, orientation_error = self._pose_error(desired_position, quat, site_id)
        return MotionResult(
            status,
            position_error,
            orientation_error,
            self._backend.total_physics_steps - start_steps,
            max_load_compensation_rad,
        )

    def _pose_error(
        self, desired_position: np.ndarray, desired_quat: np.ndarray, site_id: int
    ) -> tuple[float, float]:
        data = self._backend._data
        assert data is not None
        position_error = float(np.linalg.norm(desired_position - data.site_xpos[site_id]))
        orientation_error = float(
            np.degrees(
                np.linalg.norm(
                    _rotation_error(desired_quat, data.site_xmat[site_id])
                )
            )
        )
        return position_error, orientation_error

    def _inverse_kinematics(
        self, desired_position: np.ndarray, desired_quat: np.ndarray, site_id: int
    ) -> np.ndarray | None:
        model = self._backend._model
        actual = self._backend._data
        mujoco = self._backend._mujoco
        assert model is not None and actual is not None and mujoco is not None
        joint_ids = [model.joint(f"joint{index}").id for index in range(1, 8)]
        qpos_addrs = np.array([model.jnt_qposadr[joint_id] for joint_id in joint_ids], dtype=int)
        qvel_addrs = np.array([model.jnt_dofadr[joint_id] for joint_id in joint_ids], dtype=int)
        lower = np.array([model.jnt_range[joint_id, 0] for joint_id in joint_ids]) + 0.001
        upper = np.array([model.jnt_range[joint_id, 1] for joint_id in joint_ids]) - 0.001
        starts = [
            np.array(actual.qpos[qpos_addrs], dtype=float),
            np.array([0.0, 0.5, -1.0, 0.0, 1.0, 0.0, 0.0]),
            np.array([0.0, -0.5, 1.0, 0.0, 1.0, 0.0, 0.0]),
        ]
        best: tuple[float, np.ndarray] | None = None
        for start in starts:
            scratch = mujoco.MjData(model)
            # IK needs only the robot joint state. In particular it must not
            # import hidden object qpos from the episode into online control.
            scratch.qpos[qpos_addrs] = np.clip(start, lower, upper)
            for _ in range(250):
                mujoco.mj_forward(model, scratch)
                position_error = desired_position - scratch.site_xpos[site_id]
                rotation_error = _rotation_error(
                    desired_quat, scratch.site_xmat[site_id]
                )
                position_norm = float(np.linalg.norm(position_error))
                rotation_norm = float(np.linalg.norm(rotation_error))
                score = position_norm + 0.12 * rotation_norm
                if best is None or score < best[0]:
                    best = (score, np.array(scratch.qpos[qpos_addrs], copy=True))
                if position_norm <= 0.002 and rotation_norm <= math.radians(2.0):
                    return np.array(scratch.qpos[qpos_addrs], copy=True)
                jacp = np.zeros((3, model.nv), dtype=float)
                jacr = np.zeros((3, model.nv), dtype=float)
                mujoco.mj_jacSite(model, scratch, jacp, jacr, site_id)
                jacobian = np.vstack((jacp[:, qvel_addrs], 0.12 * jacr[:, qvel_addrs]))
                error = np.concatenate((position_error, 0.12 * rotation_error))
                damping = 0.025
                step = jacobian.T @ np.linalg.solve(
                    jacobian @ jacobian.T + damping**2 * np.eye(6), error
                )
                scratch.qpos[qpos_addrs] = np.clip(
                    scratch.qpos[qpos_addrs] + np.clip(step, -0.10, 0.10),
                    lower,
                    upper,
                )
        if best is not None and best[0] <= 0.015:
            return best[1]
        return None
