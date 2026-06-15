from __future__ import annotations

import math
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import numpy as np

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    ContactSnapshot,
    GripperCommand,
    JointCommand,
    JointStateSnapshot,
    PhysicalFault,
    PhysicalFaultType,
    PhysicalScenarioConfig,
    SensorFrame,
    SimulationStepResult,
)


class MuJoCoPhysicsBackend:
    """MuJoCo-backed deterministic physics backend for Phase 9 core validation."""

    def __init__(self) -> None:
        self._mujoco: Any | None = None
        self._model: Any | None = None
        self._data: Any | None = None
        self._config: SimulatorConfig | None = None
        self._scenario: PhysicalScenarioConfig | None = None
        self._joint_names = [f"joint{i}" for i in range(1, 8)]
        self._target_positions = np.zeros(7, dtype=float)
        self._gripper_open = True
        self._estop_engaged = False
        self._total_physics_steps = 0
        self._last_contacts: list[ContactSnapshot] = []
        self._sensor_frame = SensorFrame(frame_id="camera", sim_time_s=0.0, width=0, height=0)
        self._rng = np.random.default_rng(0)

    @property
    def total_physics_steps(self) -> int:
        return self._total_physics_steps

    @property
    def estop_engaged(self) -> bool:
        return self._estop_engaged

    def initialize(self, config: SimulatorConfig) -> None:
        if find_spec("mujoco") is None:
            raise RuntimeError(
                "MuJoCo is not installed. Install with python -m pip install -e '.[sim-mujoco]'"
            )
        import mujoco

        model_path = Path(config.model_path)
        if not model_path.exists():
            raise FileNotFoundError(model_path)
        self._mujoco = mujoco
        self._model = mujoco.MjModel.from_xml_path(str(model_path))
        self._model.opt.timestep = config.physics_dt_s
        self._data = mujoco.MjData(self._model)
        self._config = config

    def reset(self, scenario: PhysicalScenarioConfig) -> None:
        self._require_loaded()
        assert self._mujoco is not None and self._model is not None and self._data is not None
        self._scenario = scenario
        self._rng = np.random.default_rng(scenario.seed)
        self._mujoco.mj_resetData(self._model, self._data)
        self._target_positions = np.zeros(7, dtype=float)
        self._estop_engaged = False
        self._gripper_open = True
        self._total_physics_steps = 0
        self._last_contacts = []
        self._set_free_body_pose("object", scenario.object_pose)
        self._set_body_mass("object", scenario.object_mass_kg)
        self._set_geom_friction("object_geom", scenario.friction_coefficient)
        self._mujoco.mj_forward(self._model, self._data)
        self._update_sensor_frame()

    def step(self, steps: int = 1) -> SimulationStepResult:
        self._require_loaded()
        assert self._mujoco is not None and self._model is not None and self._data is not None
        if steps < 1:
            raise ValueError("steps must be positive")
        executed = 0
        for _ in range(steps):
            if not self._estop_engaged:
                self._apply_control()
            else:
                self._data.ctrl[:] = 0.0
            self._mujoco.mj_step(self._model, self._data)
            executed += 1
            self._total_physics_steps += 1
        self._last_contacts = self._read_contacts()
        self._update_sensor_frame()
        return SimulationStepResult(
            sim_time_s=self.get_sim_time(),
            physics_steps=executed,
            contacts=list(self._last_contacts),
            sensor_frame=self._sensor_frame,
        )

    def shutdown(self) -> None:
        self._data = None
        self._model = None
        self._mujoco = None

    def get_sim_time(self) -> float:
        self._require_loaded()
        assert self._data is not None
        return float(self._data.time)

    def get_joint_state(self) -> JointStateSnapshot:
        self._require_loaded()
        assert self._data is not None
        positions = [float(value) for value in self._data.qpos[:7]]
        velocities = [float(value) for value in self._data.qvel[:7]]
        efforts = [float(value) for value in self._data.ctrl[:7]]
        return JointStateSnapshot(
            names=list(self._joint_names),
            positions=positions,
            velocities=velocities,
            efforts=efforts,
            sim_time_s=self.get_sim_time(),
        )

    def get_tcp_pose(self) -> Pose:
        self._require_loaded()
        assert self._model is not None and self._data is not None
        site_id = self._model.site("tcp").id
        pos = self._data.site_xpos[site_id]
        return Pose(x=float(pos[0]), y=float(pos[1]), z=float(pos[2]))

    def get_contacts(self) -> list[ContactSnapshot]:
        return list(self._last_contacts)

    def get_sensor_frame(self) -> SensorFrame:
        return self._sensor_frame

    def apply_joint_targets(self, targets: JointCommand) -> None:
        if self._estop_engaged:
            return
        if len(targets.positions) != 7:
            raise ValueError("Franka Panda profile requires exactly 7 joint targets")
        clipped = np.clip(np.array(targets.positions, dtype=float), -2.8, 2.8)
        self._target_positions = clipped

    def apply_gripper_command(self, command: GripperCommand) -> None:
        if self._estop_engaged:
            return
        self._gripper_open = command.open
        assert self._data is not None
        target = 0.04 if command.open else 0.0
        if self._data.ctrl.shape[0] >= 9:
            self._data.ctrl[7] = target
            self._data.ctrl[8] = target

    def emergency_stop(self) -> None:
        self._estop_engaged = True
        if self._data is not None:
            self._data.ctrl[:] = 0.0

    def inject_fault(self, fault: PhysicalFault) -> None:
        if fault.fault_type == PhysicalFaultType.EMERGENCY_STOP:
            self.emergency_stop()
        elif fault.fault_type == PhysicalFaultType.OBJECT_SLIP:
            self._set_geom_friction("object_geom", 0.05)
        elif fault.fault_type == PhysicalFaultType.PAYLOAD_MASS_VARIATION:
            mass = float(fault.parameters.get("object_mass_kg", 0.25))
            self._set_body_mass("object", mass)
        elif fault.fault_type == PhysicalFaultType.FRICTION_VARIATION:
            friction = float(fault.parameters.get("friction_coefficient", 0.2))
            self._set_geom_friction("object_geom", friction)

    def _require_loaded(self) -> None:
        if self._model is None or self._data is None:
            raise RuntimeError("MuJoCo backend is not initialized")

    def _apply_control(self) -> None:
        assert self._data is not None
        current = np.array(self._data.qpos[:7], dtype=float)
        error = self._target_positions - current
        control = current + np.clip(error, -0.035, 0.035)
        self._data.ctrl[:7] = control

    def _set_free_body_pose(self, body_name: str, pose: Pose) -> None:
        assert self._model is not None and self._data is not None
        joint_id = self._model.joint(f"{body_name}_free").id
        qpos_addr = self._model.jnt_qposadr[joint_id]
        self._data.qpos[qpos_addr : qpos_addr + 3] = [pose.x, pose.y, pose.z]
        self._data.qpos[qpos_addr + 3 : qpos_addr + 7] = [1.0, 0.0, 0.0, 0.0]

    def _set_body_mass(self, body_name: str, mass_kg: float) -> None:
        assert self._model is not None
        body_id = self._model.body(body_name).id
        self._model.body_mass[body_id] = max(0.001, mass_kg)

    def _set_geom_friction(self, geom_name: str, friction: float) -> None:
        assert self._model is not None
        geom_id = self._model.geom(geom_name).id
        self._model.geom_friction[geom_id][0] = max(0.01, friction)

    def _read_contacts(self) -> list[ContactSnapshot]:
        assert self._mujoco is not None and self._model is not None and self._data is not None
        contacts: list[ContactSnapshot] = []
        for index in range(int(self._data.ncon)):
            contact = self._data.contact[index]
            geom1 = self._mujoco.mj_id2name(
                self._model, self._mujoco.mjtObj.mjOBJ_GEOM, contact.geom1
            )
            geom2 = self._mujoco.mj_id2name(
                self._model, self._mujoco.mjtObj.mjOBJ_GEOM, contact.geom2
            )
            g1 = str(geom1 or f"geom_{contact.geom1}")
            g2 = str(geom2 or f"geom_{contact.geom2}")
            expected = "finger" in g1 and "object" in g2 or "finger" in g2 and "object" in g1
            illegal = not expected and not ({"table", "object_geom"} <= {g1, g2})
            impulse = float(np.linalg.norm(contact.frame[:3])) if contact.frame.size else 0.0
            contacts.append(
                ContactSnapshot(
                    geom1=g1,
                    geom2=g2,
                    impulse=impulse,
                    position=Pose(
                        x=float(contact.pos[0]),
                        y=float(contact.pos[1]),
                        z=float(contact.pos[2]),
                    ),
                    sim_time_s=self.get_sim_time(),
                    expected=expected,
                    illegal=illegal,
                )
            )
        return contacts

    def _update_sensor_frame(self) -> None:
        tcp = self.get_tcp_pose()
        noise = float(self._rng.normal(0.0, 0.001))
        self._sensor_frame = SensorFrame(
            frame_id="camera",
            sim_time_s=self.get_sim_time(),
            width=0,
            height=0,
            depth=(max(0.0, tcp.z + noise),),
            object_detections=[
                {
                    "object_id": "object",
                    "confidence": max(0.0, min(1.0, 0.98 - abs(noise) * 10.0)),
                    "pose": {"x": tcp.x + noise, "y": tcp.y - noise, "z": tcp.z},
                }
            ],
            latency_ms=abs(noise) * 1000.0,
            ground_truth_used_for_control=False,
        )


def joint_targets_for_pose(pose: Pose) -> list[float]:
    """Small deterministic IK surrogate for the local MJCF arm.

    The command is still executed through MuJoCo actuators and physics steps; this
    maps task-space intent to reachable joint targets for the simple reference arm.
    """

    base = math.atan2(pose.y, max(0.05, pose.x))
    reach = min(0.6, math.hypot(pose.x, pose.y))
    shoulder = np.clip((0.45 - pose.z) * 1.6, -1.2, 1.2)
    elbow = np.clip((reach - 0.25) * 2.2, -1.0, 1.0)
    wrist = np.clip((pose.z - 0.25) * 1.5, -0.8, 0.8)
    return [
        float(base),
        float(shoulder),
        float(elbow),
        float(-shoulder / 2),
        float(wrist),
        0.2,
        0.0,
    ]
