"""Robot-only Cartesian reference and load estimation for held-object motion.

All corrections are sent as ordinary, rate-limited joint targets. No backend
control override or object free-joint state is used.
"""

from __future__ import annotations

import math

import numpy as np

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import _rotation_error


class CartesianMotionReference:
    duration_s = 4.0
    settle_s = 0.5

    def __init__(
        self, backend: MuJoCoPhysicsBackend, start_m: tuple[float, float, float],
        target_m: tuple[float, float, float], orientation: np.ndarray, *,
        control_steps: int, timeout_s: float, max_velocity: float, max_acceleration: float,
        initialize_load_from_feedback: bool = False,
    ) -> None:
        self.backend = backend
        model, data, mj, config = backend._model, backend._data, backend._mujoco, backend._config
        assert model is not None and data is not None and mj is not None and config is not None
        if np.max(np.abs(data.qvel[:7])) > 0.02:
            raise ValueError("Cartesian reference requires settled arm joints before motion")
        if timeout_s <= self.duration_s + self.settle_s:
            raise ValueError("Cartesian reference does not fit the original motion budget")
        self.control_dt = control_steps * config.physics_dt_s
        self.start_step = backend.total_physics_steps
        self.previous_velocity = np.array(data.qvel[:7], copy=True)
        self.previous_time = float(data.time)
        self.disturbance = (
            data.qfrc_bias[:7] - data.qfrc_actuator[:7] - data.qfrc_passive[:7]
        ).copy() if initialize_load_from_feedback else np.zeros(7)
        self.mass = np.zeros((model.nv, model.nv))
        self.gains = model.actuator_gainprm[:7, 0].copy()
        self.damping = -model.actuator_biasprm[:7, 2] + model.dof_damping[:7]
        self.max_compensation_rad = 0.0
        scratch = mj.MjData(model)
        q = np.array(data.qpos[:7], copy=True)
        lower = np.array([model.jnt_range[model.joint(n).id, 0]
                          for n in backend._joint_names]) + 0.001
        upper = np.array([model.jnt_range[model.joint(n).id, 1]
                          for n in backend._joint_names]) - 0.001
        site = model.site("tcp").id
        references = []
        for index in range(math.ceil(self.duration_s / self.control_dt) + 4):
            phase = min(index * self.control_dt / self.duration_s, 1.0)
            blend = 10 * phase**3 - 15 * phase**4 + 6 * phase**5
            position = np.array(start_m, dtype=float)
            position += (np.array(target_m) - np.array(start_m)) * blend
            for _ in range(50):
                # Only robot arm coordinates are copied into this FK scratch data.
                scratch.qpos[:7] = q
                mj.mj_forward(model, scratch)
                error = np.concatenate((
                    position - scratch.site_xpos[site],
                    0.12 * _rotation_error(orientation, scratch.site_xmat[site]),
                ))
                if np.linalg.norm(error) < 1e-10:
                    break
                jp = np.zeros((3, model.nv))
                jr = np.zeros((3, model.nv))
                mj.mj_jacSite(model, scratch, jp, jr, site)
                jacobian = np.vstack((jp[:, :7], 0.12 * jr[:, :7]))
                delta = jacobian.T @ np.linalg.solve(
                    jacobian @ jacobian.T + 1e-10 * np.eye(6), error,
                )
                q = np.clip(q + delta, lower, upper)
            else:
                raise ValueError("Cartesian reference is unreachable")
            references.append(q.copy())
        self.positions = np.array(references)
        self.velocities = np.gradient(self.positions, self.control_dt, axis=0, edge_order=2)
        self.accelerations = np.gradient(self.velocities, self.control_dt, axis=0, edge_order=2)
        if (
            np.max(np.abs(self.velocities)) > max_velocity
            or np.max(np.abs(self.accelerations)) > max_acceleration
        ):
            raise ValueError("Cartesian reference exceeds requested joint velocity/acceleration")

    def observe_step(self) -> None:
        model, data, mj = self.backend._model, self.backend._data, self.backend._mujoco
        assert model is not None and data is not None and mj is not None
        delta = float(data.time) - self.previous_time
        if delta <= 0:
            return
        mj.mj_fullM(model, self.mass, data.qM)
        acceleration = (data.qvel[:7] - self.previous_velocity) / delta
        external = (
            self.mass[:7, :7] @ acceleration + data.qfrc_bias[:7]
            - data.qfrc_actuator[:7] - data.qfrc_passive[:7]
        )
        self.disturbance += min(1.0, delta / 0.03) * (external - self.disturbance)
        self.previous_velocity = np.array(data.qvel[:7], copy=True)
        self.previous_time = float(data.time)

    def joint_target(self, elapsed_steps: int, control_steps: int) -> np.ndarray:
        model, data, mj = self.backend._model, self.backend._data, self.backend._mujoco
        assert model is not None and data is not None and mj is not None
        index = min(elapsed_steps // control_steps, len(self.positions) - 1)
        mj.mj_fullM(model, self.mass, data.qM)
        offset = (
            self.damping * self.velocities[index]
            + self.mass[:7, :7] @ self.accelerations[index] - self.disturbance
        ) / self.gains
        if not np.isfinite(offset).all():
            raise ValueError("Cartesian dynamics feedback is not finite")
        self.max_compensation_rad = max(self.max_compensation_rad, float(np.max(np.abs(offset))))
        return np.asarray(self.positions[index] + offset)
