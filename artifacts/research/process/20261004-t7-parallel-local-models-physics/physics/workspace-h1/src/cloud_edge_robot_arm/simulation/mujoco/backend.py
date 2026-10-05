"""仿真后端抽象或具体实现，区分 Mock、MuJoCo、Isaac 和 dry-run。"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any
from uuid import uuid4

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
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.spec_randomization import (
    compile_randomized_mjspec_model,
)

# Arm collision geometry is ordered along its kinematic chain. Adjacent links
# intentionally meet; fingers intentionally approach each other and the hand.
_SELF_COLLISION_ARM_GEOMS = (
    "base", "link1", "link2", "link3", "link4", "link5", "link6", "hand"
)
_SELF_COLLISION_FINGER_GEOMS = ("left_finger_geom", "right_finger_geom")
_TARGET_FINGER_CONTACTS = frozenset(
    frozenset((finger, "object_geom")) for finger in _SELF_COLLISION_FINGER_GEOMS
)
_TABLE_SUPPORT_GEOMS = frozenset(
    ("object_geom", *(f"dataset_distractor_{index}_geom" for index in range(3)))
)


def _classify_contact_pair(geom1: str, geom2: str) -> tuple[bool, bool]:
    """Return (target-grasp contact, illegal contact) for known scene geoms."""
    pair = frozenset((geom1, geom2))
    expected = pair in _TARGET_FINGER_CONTACTS
    table_support = (
        geom1 == "table" and geom2 in _TABLE_SUPPORT_GEOMS
        or geom2 == "table" and geom1 in _TABLE_SUPPORT_GEOMS
    )
    return expected, not (expected or table_support)


@dataclass(frozen=True, slots=True)
class PhysicsStepObservation:
    """Detached physical state for the independent evaluator, never for control."""

    episode_id: str
    physics_step: int
    sim_time_s: float
    object_position_m: tuple[float, float, float]
    object_geom_position_m: tuple[float, float, float]
    object_geom_rotation_row_major: tuple[float, ...]
    object_half_extent_m: tuple[float, float, float]
    object_bottom_z_m: float
    object_linear_velocity_m_s: tuple[float, float, float]
    object_angular_velocity_rad_s: tuple[float, float, float]
    region_center_m: tuple[float, float, float]
    region_half_extent_m: tuple[float, float, float]
    table_top_m: float
    tcp_position_m: tuple[float, float, float]
    gripper_open: bool
    finger_positions_m: tuple[float, float]
    finger_velocities_m_s: tuple[float, float]
    finger_ranges_m: tuple[tuple[float, float], tuple[float, float]]
    joint_positions_rad: tuple[float, ...]
    joint_velocities_rad_s: tuple[float, ...]
    joint_ranges_rad: tuple[tuple[float, float], ...]
    contact_pairs: tuple[tuple[str, str], ...]
    self_collision_distances_m: tuple[tuple[str, str, float], ...]
    estop_engaged: bool


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
        self._command_records: list[dict[str, object]] = []
        self._model_parameters: dict[str, float] = {}
        self._model_parameter_evidence: list[dict[str, object]] = []
        self._mjspec_xml_sha256 = ""
        self._sensor_noise_std_m = 0.001
        self._actuator_delay_steps = 0
        self._pending_joint_targets: list[tuple[int, np.ndarray[Any, Any]]] = []
        self._camera: MuJoCoRGBDCamera | None = None
        self._episode_id: str | None = None
        self._step_observer: Callable[[PhysicsStepObservation], None] | None = None
        self._in_observer_callback = False
        self._self_collision_geom_pairs: tuple[tuple[str, str, int, int], ...] = ()
        self._target_motion: tuple[float, float, float] | None = None
        self._fault_records: list[dict[str, object]] = []

    @property
    def fault_records(self) -> list[dict[str, object]]:
        """Offline injection evidence; never passed to the online policy."""
        return [dict(row) for row in self._fault_records]

    @property
    def total_physics_steps(self) -> int:
        return self._total_physics_steps

    @property
    def estop_engaged(self) -> bool:
        return self._estop_engaged

    @property
    def command_records(self) -> list[dict[str, object]]:
        return [dict(record) for record in self._command_records]

    @property
    def model_parameter_evidence(self) -> dict[str, object]:
        physics_dt_s = self._config.physics_dt_s if self._config is not None else 0.0
        return {
            "compiler": "MuJoCo.MjSpec" if self._mjspec_xml_sha256 else "MjModel.from_xml_path",
            "spec_xml_sha256": self._mjspec_xml_sha256,
            "parameters": [dict(item) for item in self._model_parameter_evidence],
            "runtime": {
                "sensor_noise_std_m": self._sensor_noise_std_m,
                "actuator_delay_requested_ms": self._model_parameters.get("actuator_delay_ms", 0.0),
                "actuator_delay_steps": self._actuator_delay_steps,
                "actuator_delay_applied_ms": self._actuator_delay_steps * physics_dt_s * 1_000.0,
            },
        }

    def initialize(
        self,
        config: SimulatorConfig,
        *,
        model_parameters: Mapping[str, float] | None = None,
        model_xml: str | None = None,
    ) -> None:
        self._require_not_in_observer_callback()
        if find_spec("mujoco") is None:
            raise RuntimeError(
                "MuJoCo is not installed. Install with python -m pip install -e '.[sim-mujoco]'"
            )
        import mujoco

        model_path = Path(config.model_path)
        if not model_path.exists():
            raise FileNotFoundError(model_path)
        self._mujoco = mujoco
        self._model_parameters = {
            str(name): float(value) for name, value in (model_parameters or {}).items()
        }
        if model_xml is not None and self._model_parameters:
            raise ValueError("model_xml and model_parameters are mutually exclusive")
        if model_xml is not None:
            self._model = mujoco.MjModel.from_xml_string(model_xml)
            self._mjspec_xml_sha256 = ""
            self._model_parameter_evidence = []
        elif self._model_parameters:
            build = compile_randomized_mjspec_model(
                mujoco,
                model_path=model_path,
                parameters=self._model_parameters,
            )
            self._model = build.model
            self._mjspec_xml_sha256 = build.spec_xml_sha256
            self._model_parameter_evidence = [item.to_jsonable() for item in build.evidence]
        else:
            self._model = mujoco.MjModel.from_xml_path(str(model_path))
            self._mjspec_xml_sha256 = ""
            self._model_parameter_evidence = []
        self._model.opt.timestep = config.physics_dt_s
        self._data = mujoco.MjData(self._model)
        self._config = config
        self._step_observer = None
        arm_pairs = tuple(
            (
                first_name,
                second_name,
                self._model.geom(first_name).id,
                self._model.geom(second_name).id,
            )
            for index, first_name in enumerate(_SELF_COLLISION_ARM_GEOMS)
            for second_name in _SELF_COLLISION_ARM_GEOMS[index + 2 :]
        )
        finger_arm_pairs = tuple(
            (
                arm_name,
                finger_name,
                self._model.geom(arm_name).id,
                self._model.geom(finger_name).id,
            )
            for arm_name in _SELF_COLLISION_ARM_GEOMS[:6]
            for finger_name in _SELF_COLLISION_FINGER_GEOMS
        )
        self._self_collision_geom_pairs = arm_pairs + finger_arm_pairs
        self._sensor_noise_std_m = max(
            0.0, self._model_parameters.get("camera_depth_noise_m", 0.001)
        )
        delay_ms = max(0.0, self._model_parameters.get("actuator_delay_ms", 0.0))
        self._actuator_delay_steps = int(round(delay_ms / 1000.0 / config.physics_dt_s))

    def reset(self, scenario: PhysicalScenarioConfig) -> None:
        self._require_not_in_observer_callback()
        self._require_loaded()
        assert self._mujoco is not None and self._model is not None and self._data is not None
        self._scenario = scenario
        self._step_observer = None
        self._episode_id = uuid4().hex
        self._rng = np.random.default_rng(scenario.seed)
        self._mujoco.mj_resetData(self._model, self._data)
        self._target_positions = np.zeros(7, dtype=float)
        assert self._config is not None
        if self._config.render_rgb or self._config.render_depth:
            # Initial observation pose keeps the workspace visible to the overhead camera.
            joint = self._model.joint("joint1")
            self._data.qpos[joint.qposadr[0]] = -0.8
            self._target_positions[0] = -0.8
        self._estop_engaged = False
        self._gripper_open = True
        self._total_physics_steps = 0
        self._target_motion = None
        self._fault_records = []
        self._last_contacts = []
        self._command_records = []
        self._pending_joint_targets = []
        self._set_free_body_pose("object", scenario.object_pose)
        for finger_name in ("finger_left_joint", "finger_right_joint"):
            finger_id = self._model.joint(finger_name).id
            self._data.qpos[self._model.jnt_qposadr[finger_id]] = 0.04
        self._data.ctrl[7:9] = 0.04
        self._set_body_mass("object", scenario.object_mass_kg)
        self._set_geom_friction("object_geom", scenario.friction_coefficient)
        self._mujoco.mj_forward(self._model, self._data)
        self._update_sensor_frame()

    def step(self, steps: int = 1) -> SimulationStepResult:
        self._require_not_in_observer_callback()
        self._require_loaded()
        assert self._mujoco is not None and self._model is not None and self._data is not None
        if steps < 1:
            raise ValueError("steps must be positive")
        observer = self._step_observer
        executed = 0
        if observer is None:
            for _ in range(steps):
                # Emergency stop blocks new commands but actively holds joints.
                self._apply_control()
                self._mujoco.mj_step(self._model, self._data)
                executed += 1
                self._total_physics_steps += 1
            self._last_contacts = self._read_contacts()
        else:
            for _ in range(steps):
                self._apply_control()
                self._mujoco.mj_step(self._model, self._data)
                executed += 1
                self._total_physics_steps += 1
                self._last_contacts = self._read_contacts()
                snapshot = self._build_physics_observation(self._last_contacts)
                self._in_observer_callback = True
                try:
                    observer(snapshot)
                except BaseException:
                    self._step_observer = None
                    raise
                finally:
                    self._in_observer_callback = False
        self._update_sensor_frame()
        return SimulationStepResult(
            sim_time_s=self.get_sim_time(),
            physics_steps=executed,
            contacts=list(self._last_contacts),
            sensor_frame=self._sensor_frame,
        )

    def shutdown(self) -> None:
        self._require_not_in_observer_callback()
        self._step_observer = None
        if self._camera is not None:
            self._camera.close()
            self._camera = None
        self._data = None
        self._model = None
        self._mujoco = None
        self._episode_id = None
        self._self_collision_geom_pairs = ()

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

    def current_physics_observation(self) -> PhysicsStepObservation:
        """Read step 0 or the current step without advancing physics."""
        self._require_loaded()
        if self._episode_id is None:
            raise RuntimeError("MuJoCo scenario is not reset")
        return self._build_physics_observation(self._read_contacts())

    @contextmanager
    def observe_physics_steps(
        self, callback: Callable[[PhysicsStepObservation], None]
    ) -> Iterator[None]:
        """Observe every mj_step for one episode; never retain a step history."""
        self._require_not_in_observer_callback()
        self._require_loaded()
        if self._episode_id is None:
            raise RuntimeError("MuJoCo scenario is not reset")
        if self._step_observer is not None:
            raise RuntimeError("a physics step observer is already active")
        self._step_observer = callback
        try:
            yield
        finally:
            if self._step_observer is callback:
                self._step_observer = None

    def get_sensor_frame(self) -> SensorFrame:
        return self._sensor_frame

    def capture_sensor_frame_with_instances(
        self,
    ) -> tuple[SensorFrame, tuple[int, ...], dict[int, str], tuple[str, ...]]:
        """Render a new frame without advancing physics or replacing the cached step frame."""
        self._require_loaded()
        if self._scenario is None or self._config is None:
            raise RuntimeError("MuJoCo scenario is not reset")
        if not (self._config.render_rgb and self._config.render_depth):
            raise RuntimeError("RGB-D rendering is not enabled")
        if self._camera is None:
            self._camera = MuJoCoRGBDCamera(
                self._mujoco, self._model,
                width=self._config.camera_width, height=self._config.camera_height,
            )
        return self._camera.capture_with_instances(
            self._data, rng=self._rng, noise_std_m=self._sensor_noise_std_m,
            scene_id=self._scenario.scenario_id, episode_id=self._episode_id,
        )

    def apply_joint_targets(self, targets: JointCommand) -> None:
        self._require_not_in_observer_callback()
        if self._estop_engaged:
            self._record_command("joint_target", accepted=False, reason="emergency_stop")
            return
        if len(targets.positions) != 7:
            raise ValueError("Franka Panda profile requires exactly 7 joint targets")
        clipped = np.clip(np.array(targets.positions, dtype=float), -2.8, 2.8)
        if self._actuator_delay_steps:
            available_step = self._total_physics_steps + self._actuator_delay_steps
            self._pending_joint_targets.append((available_step, clipped))
            self._record_command(
                "joint_target",
                accepted=True,
                reason=f"queued_until_physics_step={available_step}",
            )
        else:
            self._target_positions = clipped
            self._record_command("joint_target", accepted=True, reason="")

    def apply_gripper_command(self, command: GripperCommand) -> None:
        self._require_not_in_observer_callback()
        if self._estop_engaged:
            self._record_command("gripper", accepted=False, reason="emergency_stop")
            return
        self._gripper_open = command.open
        assert self._data is not None
        target = 0.04 if command.open else 0.0
        if self._data.ctrl.shape[0] >= 9:
            self._data.ctrl[7] = target
            self._data.ctrl[8] = target
        self._record_command("gripper", accepted=True, reason="")

    def emergency_stop(self) -> None:
        self._require_not_in_observer_callback()
        self.hold_current_joints()
        self._estop_engaged = True
        self._record_command("emergency_stop", accepted=True, reason="")
        self._apply_control()

    def hold_current_joints(self) -> None:
        """Cancel queued arm motion and actively hold measured joints."""
        self._require_not_in_observer_callback()
        self._require_loaded()
        assert self._data is not None
        self._pending_joint_targets.clear()
        self._target_positions = np.array(self._data.qpos[:7], dtype=float)
        self._record_command("hold_current_joints", accepted=True, reason="motion_terminated")

    def inject_fault(self, fault: PhysicalFault) -> None:
        self._require_not_in_observer_callback()
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
        elif fault.fault_type == PhysicalFaultType.TARGET_MOTION:
            speed = float(fault.parameters["speed_m_s"])
            duration = float(fault.parameters.get("duration_s", 5.))
            direction = float(fault.parameters.get("direction_y", 1.))
            if not math.isfinite(speed + duration + direction) or not 0 <= speed <= .04 or (
                duration <= 0 or direction not in (-1., 1.)
            ):
                raise ValueError("target motion requires speed in [0,.04], duration>0, direction ±1")
            self._target_motion = (speed, direction, self.get_sim_time() + duration)
            self._fault_records.append({"event": "TARGET_MOTION_STARTED",
                "physics_step": self.total_physics_steps, "sim_time_s": self.get_sim_time(),
                "speed_m_s": speed, "direction_y": direction, "duration_s": duration,
                "mechanism": "external horizontal force with velocity feedback; no pose writes"})

    def _require_loaded(self) -> None:
        if self._model is None or self._data is None:
            raise RuntimeError("MuJoCo backend is not initialized")

    def _require_not_in_observer_callback(self) -> None:
        if self._in_observer_callback:
            raise RuntimeError("observer callback cannot mutate or step the backend")

    def _build_physics_observation(
        self, contacts: list[ContactSnapshot]
    ) -> PhysicsStepObservation:
        assert self._mujoco is not None and self._model is not None and self._data is not None
        assert self._episode_id is not None
        model = self._model
        data = self._data

        def xyz(values: Any) -> tuple[float, float, float]:
            return (float(values[0]), float(values[1]), float(values[2]))

        object_body_id = model.body("object").id
        object_geom_id = model.geom("object_geom").id
        region_geom_id = model.geom("target_region_geom").id
        table_geom_id = model.geom("table").id
        object_joint_id = model.joint("object_free").id
        object_dof_addr = int(model.jnt_dofadr[object_joint_id])
        object_half_extent = xyz(model.geom_size[object_geom_id])
        rotation = tuple(float(value) for value in data.geom_xmat[object_geom_id])
        object_geom_position = xyz(data.geom_xpos[object_geom_id])
        vertical_radius = sum(
            abs(rotation[6 + axis]) * object_half_extent[axis] for axis in range(3)
        )
        joint_ids = [model.joint(name).id for name in self._joint_names]
        finger_ids = [
            model.joint(name).id for name in ("finger_left_joint", "finger_right_joint")
        ]
        finger_positions = tuple(
            float(data.qpos[model.jnt_qposadr[joint_id]]) for joint_id in finger_ids
        )
        return PhysicsStepObservation(
            episode_id=self._episode_id,
            physics_step=self._total_physics_steps,
            sim_time_s=float(data.time),
            object_position_m=xyz(data.xpos[object_body_id]),
            object_geom_position_m=object_geom_position,
            object_geom_rotation_row_major=rotation,
            object_half_extent_m=object_half_extent,
            object_bottom_z_m=object_geom_position[2] - vertical_radius,
            object_linear_velocity_m_s=xyz(data.qvel[object_dof_addr : object_dof_addr + 3]),
            object_angular_velocity_rad_s=xyz(data.qvel[object_dof_addr + 3 : object_dof_addr + 6]),
            region_center_m=xyz(data.geom_xpos[region_geom_id]),
            region_half_extent_m=xyz(model.geom_size[region_geom_id]),
            table_top_m=float(data.geom_xpos[table_geom_id][2] + model.geom_size[table_geom_id][2]),
            tcp_position_m=xyz(data.site_xpos[model.site("tcp").id]),
            gripper_open=min(finger_positions) >= 0.035,
            finger_positions_m=(finger_positions[0], finger_positions[1]),
            finger_velocities_m_s=(
                float(data.qvel[model.jnt_dofadr[finger_ids[0]]]),
                float(data.qvel[model.jnt_dofadr[finger_ids[1]]]),
            ),
            finger_ranges_m=(
                (
                    float(model.jnt_range[finger_ids[0], 0]),
                    float(model.jnt_range[finger_ids[0], 1]),
                ),
                (
                    float(model.jnt_range[finger_ids[1], 0]),
                    float(model.jnt_range[finger_ids[1], 1]),
                ),
            ),
            joint_positions_rad=tuple(
                float(data.qpos[model.jnt_qposadr[joint_id]]) for joint_id in joint_ids
            ),
            joint_velocities_rad_s=tuple(
                float(data.qvel[model.jnt_dofadr[joint_id]]) for joint_id in joint_ids
            ),
            joint_ranges_rad=tuple(
                (float(model.jnt_range[joint_id, 0]), float(model.jnt_range[joint_id, 1]))
                for joint_id in joint_ids
            ),
            contact_pairs=tuple((contact.geom1, contact.geom2) for contact in contacts),
            self_collision_distances_m=tuple(
                (
                    first_name,
                    second_name,
                    float(
                        self._mujoco.mj_geomDistance(
                            model, data, first_id, second_id, float("inf"), None
                        )
                    ),
                )
                for first_name, second_name, first_id, second_id
                in self._self_collision_geom_pairs
            ),
            estop_engaged=self._estop_engaged,
        )

    def _apply_control(self) -> None:
        assert self._data is not None and self._model is not None
        self._apply_target_motion()
        while (
            self._pending_joint_targets
            and self._pending_joint_targets[0][0] <= self._total_physics_steps
        ):
            _, self._target_positions = self._pending_joint_targets.pop(0)
        current = np.array(self._data.qpos[:7], dtype=float)
        error = self._target_positions - current
        control = current + np.clip(error, -0.10, 0.10)
        # Position actuators still drive every arm movement. Their command is
        # offset by the measured generalized gravity/Coriolis load so a slow
        # trajectory does not let this reference arm fold under its own weight.
        gains = self._model.actuator_gainprm[:7, 0]
        feedforward = self._data.qfrc_bias[:7] / gains
        self._data.ctrl[:7] = np.clip(
            control + feedforward,
            self._model.actuator_ctrlrange[:7, 0],
            self._model.actuator_ctrlrange[:7, 1],
        )

    def _apply_target_motion(self) -> None:
        if self._target_motion is None:
            return
        assert self._model is not None and self._data is not None
        speed, direction, end_time = self._target_motion
        dof = self._model.joint("object_free").dofadr[0]
        body = self._model.body("object").id
        # This is an offline physical disturbance actuator, not robot control.
        finger_contact = any("object_geom" in (c.geom1, c.geom2) and
                             ("left_finger_geom" in (c.geom1, c.geom2) or
                              "right_finger_geom" in (c.geom1, c.geom2))
                             for c in self._last_contacts)
        if self.get_sim_time() >= end_time or finger_contact:
            self._data.qfrc_applied[dof + 1] = 0
            self._target_motion = None
            self._fault_records.append({"event": "TARGET_MOTION_FINISHED",
                "physics_step": self.total_physics_steps, "sim_time_s": self.get_sim_time(),
                "reason": "finger_contact" if finger_contact else "scheduled_end"})
            return
        mass = self._model.body_mass[body]
        friction = self._model.geom("object_geom").friction[0]
        feedforward = direction * friction * mass * 9.81 if speed else 0.
        self._data.qfrc_applied[dof + 1] = np.clip(
            feedforward + mass * (direction * speed - self._data.qvel[dof + 1]) / .02,
            -2., 2.,
        )

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
            expected, illegal = _classify_contact_pair(g1, g2)
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
        if self._config is not None and (self._config.render_rgb or self._config.render_depth):
            if self._camera is None:
                self._camera = MuJoCoRGBDCamera(
                    self._mujoco, self._model,
                    width=self._config.camera_width, height=self._config.camera_height,
                )
            self._sensor_frame = self._camera.capture(
                self._data, rng=self._rng, noise_std_m=self._sensor_noise_std_m,
                scene_id=self._scenario.scenario_id if self._scenario else None,
                episode_id=self._episode_id,
            )
            return
        tcp = self.get_tcp_pose()
        noise = float(self._rng.normal(0.0, self._sensor_noise_std_m))
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

    def _record_command(self, command_type: str, *, accepted: bool, reason: str) -> None:
        self._command_records.append(
            {
                "type": command_type,
                "accepted": accepted,
                "reason": reason,
                "after_emergency_stop": self._estop_engaged and command_type != "emergency_stop",
                "sim_time_s": self.get_sim_time() if self._data is not None else 0.0,
            }
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
